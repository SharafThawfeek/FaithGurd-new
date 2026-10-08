"""The team benchmark: hand-corrected report tables and questions with gold answers.

One YAML file per annual report, with one CSV per corrected table beside it:

    data/benchmark/<country>/<ISSUER>/<fiscal year>.yaml
    data/benchmark/<country>/<ISSUER>/<fiscal year>/<table id>.csv   (the table exactly as printed)

Each question gives its gold answer as a cell expression ("t1r3c1", "growth(t1r3c1,
t1r3c2)") and, separately, the value as the author read it in the report ("expect").
Code computes the gold value from the cells and checks the two agree: a wrong cell
id, a wrong row, or a misread number shows up as a mismatch (the plan's cross-check).
`faithguard benchmark cells` prints every cell id of a report for question writers.
"""

from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Iterable

import yaml

from faithguard.calc import expr
from faithguard.calc.numbers import find_numbers, matches
from faithguard.data.example import base_value, classify
from faithguard.gold import GoldQuestion, GoldStore, GoldValue
from faithguard.records import Country, Evidence, Question, QuestionType, Record
from faithguard.tables import table_from_grid


class TableSpec(Record):
    title: str = ""
    page: int | None = None
    currency: str | None = None
    scale: int | None = None  # power of ten; detected from the header when omitted
    entity: str | None = None  # for single-entity tables, e.g. "group"


class QuestionSpec(Record):
    id: str
    text: str
    type: QuestionType
    answer: str = ""  # cell expression for the gold answer (empty for narrative questions)
    expect: str = ""  # the answer as the author read it, e.g. "Rs. 14,212,560 thousand" or "9.3%"
    author: str = ""
    checked_by: str = ""
    pilot: bool = False
    note: str = ""


class ReportSpec(Record):
    issuer: str
    country: Country
    name: str
    fiscal_year: str  # the calendar year the financial year ends in
    year_end: str | None = None
    source: str | None = None  # where the report was downloaded from
    tables: dict[str, TableSpec]
    questions: list[QuestionSpec] = []


class BenchmarkQuestion(Record):
    """A question with its frozen evidence, before any answer is generated."""

    question: Question
    evidence: Evidence


def read_grid(path: Path) -> list[list[str]]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return [row for row in csv.reader(f)]


def load_report(path: str | Path) -> tuple[ReportSpec, Evidence]:
    path = Path(path)
    spec = ReportSpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
    folder = path.with_suffix("")
    tables = []
    for table_id, t in spec.tables.items():
        grid = read_grid(folder / f"{table_id}.csv")
        tables.append(table_from_grid(
            table_id, grid, title=t.title, scale=t.scale, currency=t.currency, entity=t.entity, page=t.page, source=spec.source,
        ))
    return spec, Evidence(tables=tables)


def report_paths(root: str | Path) -> list[Path]:
    return sorted(p for p in Path(root).rglob("*.yaml") if p.is_file())


def answer_kind(program: str, evidence: Evidence) -> str:
    tree = expr.parse(program)
    if isinstance(tree, expr.Call) and tree.fn in ("growth", "share"):
        return "percent"
    if isinstance(tree, expr.BinOp) and tree.op == "*" and isinstance(tree.right, expr.Num) and tree.right.value == 100:
        return "percent"
    cells = [evidence.cell(c) for c in expr.refs(tree)]
    if cells and all(c.kind == "percent" for c in cells):
        return "percent"
    if (isinstance(tree, expr.Call) and tree.fn == "ratio") or (isinstance(tree, expr.BinOp) and tree.op == "/"):
        return "ratio"
    return "amount"


@dataclass
class Finding:
    file: str
    question: str
    level: str  # error, warning
    message: str


def _expect_matches(expect: str, value: Decimal, kind: str, program: str, evidence: Evidence) -> bool:
    found = find_numbers(expect)
    if not found:
        return False
    m = found[0]
    if m.kind == "number":  # no unit written: read it in the units of the table the answer comes from
        cells = [evidence.cell(c) for c in expr.refs(expr.parse(program))]
        scale = next((c.scale for c in cells if c.kind == "amount"), 0) if kind == "amount" else 0
        return matches(m, value.scaleb(-scale)) or matches(m, value)
    if m.kind == "percent" and kind != "percent":
        return False
    return matches(m, value) or matches(m, -value)  # a decrease may be written without its minus


def check(paths: Iterable[Path], manifest: dict | None = None) -> tuple[list[Finding], Counter]:
    """Every problem found, and counts of checked questions by country, split and type."""
    from faithguard.splits import split_of

    findings: list[Finding] = []
    counts: Counter = Counter()
    seen: dict[str, str] = {}
    for path in paths:
        try:
            spec, evidence = load_report(path)
        except Exception as err:  # malformed YAML or CSV: report and move on
            findings.append(Finding(str(path), "-", "error", f"cannot load: {err}"))
            continue
        split = split_of(manifest, spec.country, spec.issuer) if manifest else None
        if manifest and f"{spec.country}:{spec.issuer}" not in manifest["splits"]:
            findings.append(Finding(str(path), "-", "warning", f"{spec.issuer} is not in the split manifest (treated as training data)"))
        for q in spec.questions:
            where = (str(path), q.id)
            if q.id in seen:
                findings.append(Finding(*where, "error", f"duplicate question id (also in {seen[q.id]})"))
            seen[q.id] = str(path)
            if q.type == "narrative":  # no numeric gold: labelled by people only
                if not q.expect:
                    findings.append(Finding(*where, "warning", "narrative question without a reference answer in 'expect'"))
                counts[(spec.country, split or "unassigned", q.type)] += 1
                continue
            try:
                value = base_value(q.answer, evidence)
                kind = answer_kind(q.answer, evidence)
            except Exception as err:
                findings.append(Finding(*where, "error", f"answer expression {q.answer!r} fails: {err}"))
                continue
            if not _expect_matches(q.expect, value, kind, q.answer, evidence):
                findings.append(Finding(*where, "error", f"expect {q.expect!r} does not match the cells: {q.answer} = {value.normalize():f} ({kind}, base units)"))
            implied = classify(q.answer)
            if implied not in ("other", q.type) and q.type not in ("comparison", "narrative"):
                findings.append(Finding(*where, "warning", f"type {q.type!r} but the answer expression looks like {implied!r}"))
            if not q.author or not q.checked_by:
                findings.append(Finding(*where, "warning", "not cross-checked: author and checked_by are both required"))
            elif q.author == q.checked_by:
                findings.append(Finding(*where, "warning", "checked by its own author"))
            if q.pilot and split not in (None, "dev"):
                findings.append(Finding(*where, "error", f"pilot questions must come from dev issuers; {spec.issuer} is {split}"))
            counts[(spec.country, split or "unassigned", q.type)] += 1
    return findings, counts


def gold_for(spec: ReportSpec, q: QuestionSpec, evidence: Evidence) -> GoldQuestion:
    if q.type == "narrative":
        return GoldQuestion(question_id=q.id, answer_text=q.expect, values=[], source="team")
    kind = answer_kind(q.answer, evidence)
    cells = expr.refs(expr.parse(q.answer))
    values = [GoldValue(value=base_value(q.answer, evidence), kind=kind if kind != "ratio" else "ratio", role="answer")]
    for cid in cells:
        cell = evidence.cell(cid)
        if cell.value is not None:
            values.append(GoldValue(value=cell.value, kind="percent" if cell.kind == "percent" else "amount", role="operand", cell=cid))
    return GoldQuestion(question_id=q.id, answer_text=q.expect, values=values, cells=cells, program=q.answer, source="team")


def build(paths: Iterable[Path], manifest: dict | None = None, pilot_only: bool = False) -> tuple[list[BenchmarkQuestion], GoldStore]:
    from faithguard.splits import split_of

    questions: list[BenchmarkQuestion] = []
    gold = GoldStore("unused")
    for path in paths:
        spec, evidence = load_report(path)
        split = split_of(manifest, spec.country, spec.issuer) if manifest else None
        for q in spec.questions:
            if pilot_only and not q.pilot:
                continue
            question = Question(
                id=q.id, issuer=f"{spec.country}:{spec.issuer}", country=spec.country, split=split, text=q.text,
                question_type=q.type, period=spec.fiscal_year, source="team",
            )
            questions.append(BenchmarkQuestion(question=question, evidence=evidence))
            gold.add_question(gold_for(spec, q, evidence))
    return questions, gold


def cell_listing(evidence: Evidence) -> str:
    """Every cell with its id, as question writers need it."""
    lines = []
    for t in evidence.tables:
        lines.append(f"Table {t.id}: {t.title} (scale 10^{t.scale}, {t.currency or 'no currency'})")
        for c in t.cells:
            context = " / ".join(x for x in (c.entity, c.metric, c.period) if x)
            lines.append(f"  {c.id:10} {c.text:>16}   {context}   [{c.kind}]")
    return "\n".join(lines)
