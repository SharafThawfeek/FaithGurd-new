"""TAT-QA (Zhu et al., 2021; CC BY 4.0) as FaithGuard Examples.

Each document: one table from an annual report, its paragraphs and several
questions. Arithmetic questions carry a derivation such as "(44.1-56.7)/56.7";
numeric span answers are lookups. Both are converted into cell expressions.
"""

from __future__ import annotations

import collections
import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from faithguard.data.example import Example, base_value, classify, evaluates_to, is_grounded, match_cell
from faithguard.gold import GoldQuestion, GoldValue
from faithguard.records import Evidence, Passage, Question
from faithguard.tables import parse_table_cell, table_from_grid

SCALES = {"thousand": 3, "million": 6, "billion": 9}
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def convert_derivation(derivation: str, evidence: Evidence, question: str) -> tuple[str | None, list[str]]:
    cells = evidence.cells()
    used: list[str] = []
    out, pos = [], 0
    text = derivation.replace("%", "").replace("$", "")
    for m in _NUMBER.finditer(text):
        out.append(text[pos : m.start()])
        try:
            value = Decimal(m.group().replace(",", ""))
        except InvalidOperation:
            return None, []
        cell, by_abs = match_cell(value, cells, question=question)
        if cell is None:
            out.append(m.group().replace(",", ""))
        else:
            used.append(cell.id)
            out.append(f"abs({cell.id})" if by_abs and cell.raw < 0 else cell.id)
        pos = m.end()
    out.append(text[pos:])
    program = "".join(out).strip()
    if not program or re.search(r"[^\w\s.+\-*/(),]", program):
        return None, []
    return program, used


def _answer_number(answer) -> Decimal | None:
    if isinstance(answer, (int, float)):
        return Decimal(str(answer))
    if isinstance(answer, list) and len(answer) == 1:
        mention = parse_table_cell(str(answer[0]))
        return mention.raw if mention else None
    return None


def load(path: str | Path, limit: int | None = None) -> Iterator[Example]:
    docs = json.loads(Path(path).read_text(encoding="utf-8"))
    n = 0
    for doc in docs:
        grid = doc["table"]["table"]
        table = table_from_grid("t1", grid)
        if table.scale == 0:
            scales = collections.Counter(
                q["scale"] for q in doc["questions"] if q["scale"] in SCALES and "table" in q["answer_from"]
            )
            if scales:
                table = table_from_grid("t1", grid, scale=SCALES[scales.most_common(1)[0][0]])
        passages = [Passage(id=f"p{p['order']}", text=p["text"]) for p in sorted(doc["paragraphs"], key=lambda p: p["order"])]
        evidence = Evidence(tables=[table], passages=passages)
        issuer = "tatqa:" + doc["table"]["uid"][:8]
        for q in doc["questions"]:
            if limit is not None and n >= limit:
                return
            if q["answer_type"] not in ("arithmetic", "span"):
                continue
            target = _answer_number(q["answer"])
            if target is None:
                continue
            if q["answer_type"] == "arithmetic":
                program, used = convert_derivation(q["derivation"], evidence, q["question"])
            else:
                cell, _ = match_cell(target, evidence.cells(), question=q["question"])
                program, used = (cell.id, [cell.id]) if cell is not None else (None, [])
            if program and not evaluates_to(program, evidence, target):
                if q["scale"] == "percent" and evaluates_to(f"({program}) * 100", evidence, target):
                    program = f"({program}) * 100"
                else:
                    program, used = None, []
            single = evidence.cell(program) if program and re.fullmatch(r"[A-Za-z]\w*", program) else None
            if q["scale"] == "percent" or (single is not None and single.kind == "percent") or (program or "").endswith("* 100"):
                kind = "percent"
            elif program and "/" in program:
                kind = "ratio"
            else:
                kind = "amount"
            if program:  # computed from the cells in base units, so it never depends on the dataset's scale label
                value = base_value(program, evidence)
            elif q["scale"] in SCALES and kind == "amount":
                value = target.scaleb(SCALES[q["scale"]])
            else:
                value = target
            operands = [
                GoldValue(value=evidence.cell(cid).value, kind="percent" if evidence.cell(cid).kind == "percent" else "amount", role="operand", cell=cid)
                for cid in dict.fromkeys(used)
                if evidence.cell(cid).value is not None
            ]
            gold = GoldQuestion(
                question_id=q["uid"],
                answer_text=str(q["answer"]),
                values=[GoldValue(value=value, kind=kind, role="answer")] + operands,
                cells=list(dict.fromkeys(used)),
                program=program,
                source="tatqa",
            )
            question = Question(
                id=q["uid"], issuer=issuer, text=q["question"], question_type=classify(program), source="tatqa"
            )
            n += 1
            yield Example(question=question, evidence=evidence, gold=gold, grounded=bool(program) and is_grounded(program))
