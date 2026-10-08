"""FinQA (Chen et al., 2021; MIT licence) as FaithGuard Examples.

Each example: an S&P 500 10-K page with one table, its text, a question, a gold
program such as "subtract(5829, 5735), divide(#0, 5735)" and its executed answer.
The program is converted into the cell expression language, with each number
mapped to the cell that printed it, and kept only if it reproduces the answer.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Iterator

from faithguard.data.example import Example, base_value, classify, evaluates_to, is_grounded, match_cell
from faithguard.gold import GoldQuestion, GoldValue
from faithguard.records import Evidence, Passage, Question
from faithguard.tables import normalise_metric, table_from_grid

_STEP = re.compile(r"(\w+)\(([^()]*)\)")
_OPS = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}


def convert_program(program: str, evidence: Evidence, gold_rows: set[int], question: str) -> tuple[str | None, list[str]]:
    """FinQA program -> (expression, cells used), or (None, []) if it uses an unsupported operation."""
    cells = evidence.cells()
    exprs: list[str] = []
    used: list[str] = []
    for op, argtext in _STEP.findall(program):
        args = [a.strip() for a in argtext.split(",")]
        if op in ("table_sum", "table_average"):
            row = normalise_metric(args[0])
            row_cells = [c for c in cells if c.metric == row and c.raw is not None]
            if not row_cells:
                return None, []
            used += [c.id for c in row_cells]
            exprs.append(f"{'sum' if op == 'table_sum' else 'avg'}({', '.join(c.id for c in row_cells)})")
            continue
        if op not in _OPS or len(args) != 2:
            return None, []  # exp, greater, table_max, table_min
        parts = []
        for a in args:
            if a.startswith("#"):
                parts.append(f"({exprs[int(a[1:])]})")
            elif a.startswith("const_"):
                parts.append("-1" if a == "const_m1" else a[6:])
            else:
                try:
                    value = Decimal(a.replace("%", ""))
                except ArithmeticError:
                    return None, []
                cell, by_abs = match_cell(value, cells, gold_rows, question)
                if cell is None:
                    parts.append(f"{abs(value)}" if value >= 0 else f"(-{abs(value)})")
                else:
                    used.append(cell.id)
                    parts.append(f"abs({cell.id})" if by_abs and cell.raw < 0 else cell.id)
        exprs.append(f"{parts[0]} {_OPS[op]} {parts[1]}")
    if not exprs:
        return None, []
    return exprs[-1], used


def load(path: str | Path, limit: int | None = None) -> Iterator[Example]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    for n, ex in enumerate(data):
        if limit is not None and n >= limit:
            break
        qa = ex["qa"]
        title = " ".join(ex["pre_text"][-3:])
        table = table_from_grid("t1", ex["table"], title=title, currency="USD", source=ex["filename"])
        passages = [Passage(id=f"p{i + 1}", text=s) for i, s in enumerate(ex["pre_text"] + ex["post_text"]) if s.strip() not in ("", ".")]
        evidence = Evidence(tables=[table], passages=passages)
        gold_rows = {int(k.split("_")[1]) for k in qa.get("gold_inds", {}) if k.startswith("table_")}
        program, used = convert_program(qa["program"], evidence, gold_rows, qa["question"])
        exe = Decimal(str(qa["exe_ans"])) if isinstance(qa["exe_ans"], (int, float)) else None
        if exe is None:
            continue
        percent = "%" in str(qa["answer"])
        already_times_100 = bool(re.search(r"multiply\(#\d+, const_100\)\s*$", qa["program"]))
        if program and not evaluates_to(program, evidence, exe):
            program, used = None, []
        if percent:
            value, kind = (exe if already_times_100 else exe * 100), "percent"
            if program and not already_times_100:
                program = f"({program}) * 100"
        elif "divide" in qa["program"] and not re.search(r"divide\([^)]*const_", qa["program"]):
            value, kind = exe, "ratio"
        else:
            value, kind = exe.scaleb(table.scale), "amount"
        if program:  # computed from the cells in base units, so it never depends on the table's scale guess
            try:
                value = base_value(program, evidence)
            except Exception:
                program, used = None, []
        operands = []
        for cid in dict.fromkeys(used):
            cell = evidence.cell(cid)
            if cell.value is not None:
                operands.append(GoldValue(value=cell.value, kind="percent" if cell.kind == "percent" else "amount", role="operand", cell=cid))
        ticker = ex["filename"].split("/")[0]
        gold = GoldQuestion(
            question_id=ex["id"],
            answer_text=str(qa["answer"]),
            values=[GoldValue(value=value, kind=kind, role="answer")] + operands,
            cells=list(dict.fromkeys(used)),
            program=program,
            source="finqa",
        )
        question = Question(
            id=ex["id"], issuer=f"finqa:{ticker}", country="US", text=qa["question"],
            question_type=classify(program), source="finqa",
        )
        yield Example(question=question, evidence=evidence, gold=gold, grounded=bool(program) and is_grounded(program))
