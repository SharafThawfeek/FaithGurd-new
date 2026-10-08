"""A dataset example before any answer exists: question, evidence and gold.

Loaders produce Examples; the error injector turns them into Items (with answers)
plus gold-store records. Examples carry gold, so decision-time code never sees them.
"""

from __future__ import annotations

import re
from decimal import Decimal

from faithguard.calc import expr
from faithguard.gold import GoldQuestion
from faithguard.records import Cell, Evidence, Question, QuestionType, Record


class Example(Record):
    question: Question
    evidence: Evidence
    gold: GoldQuestion
    grounded: bool  # the gold program uses only cell references and constants


def classify(program: str | None) -> QuestionType:
    """The question type implied by the shape of a gold program."""
    if not program:
        return "other"
    try:
        tree = expr.parse(program)
    except expr.ExprError:
        return "other"
    if isinstance(tree, expr.Ref):
        return "lookup"
    if isinstance(tree, expr.Call):
        return {"growth": "growth", "diff": "difference", "sum": "sum", "avg": "average", "share": "share", "ratio": "ratio"}.get(tree.fn, "other")
    if isinstance(tree, expr.BinOp):
        if tree.op == "*" and isinstance(tree.right, expr.Num) and tree.right.value == 100:
            inner = tree.left
            if isinstance(inner, expr.BinOp) and inner.op == "/":
                return "growth" if isinstance(inner.left, expr.BinOp) and inner.left.op == "-" else "share"
            return "other"
        if tree.op == "-" and isinstance(tree.left, expr.Ref) and isinstance(tree.right, expr.Ref):
            return "difference"
        if tree.op == "/":
            return "growth" if isinstance(tree.left, expr.BinOp) and tree.left.op == "-" else "ratio"
        if tree.op == "+":
            return "sum"
    return "other"


def match_cell(value: Decimal, cells: list[Cell], prefer_rows: set[int] | None = None, question: str = "") -> tuple[Cell | None, bool]:
    """The cell that printed `value` (or its absolute value). Returns (cell, matched_by_absolute_value)."""
    exact = [c for c in cells if c.raw is not None and c.raw == value]
    by_abs = [c for c in cells if c.raw is not None and abs(c.raw) == abs(value) and c not in exact]
    for pool, absolute in ((exact, False), (by_abs, True)):
        if not pool:
            continue
        if prefer_rows:
            preferred = [c for c in pool if c.row in prefer_rows]
            if preferred:
                pool = preferred
        if len(pool) > 1 and question:
            q = question.lower()
            scored = sorted(pool, key=lambda c: -(bool(c.period and c.period in q) + bool(c.metric and c.metric in q)))
            pool = scored
        return pool[0], absolute
    return None, False


def evaluates_to(program: str, evidence: Evidence, target: Decimal, rel: Decimal = Decimal("0.001")) -> bool:
    """Does the program, run on the cells' printed values, reproduce the dataset's answer?"""
    try:
        got = expr.evaluate(expr.parse(program), lambda cid: _raw(evidence, cid))
    except Exception:
        return False
    return abs(got - target) <= rel * max(Decimal(1), abs(target))


def base_value(program: str, evidence: Evidence) -> Decimal:
    """The program's result on the cells' base-unit values (rupees, dollars, percentage points)."""
    return expr.evaluate(expr.parse(program), lambda cid: _value(evidence, cid))


def _value(evidence: Evidence, cell_id: str) -> Decimal:
    value = evidence.cell(cell_id).value
    if value is None:
        raise KeyError(cell_id)
    return value


def _raw(evidence: Evidence, cell_id: str) -> Decimal:
    raw = evidence.cell(cell_id).raw
    if raw is None:
        raise KeyError(cell_id)
    return raw


_LITERAL = re.compile(r"(?<![A-Za-z_])\d+(?:\.\d+)?")


def is_grounded(program: str) -> bool:
    """Only cell references and the constants 1, 100 and 1000 (no copied-in numbers)."""
    return all(lit in ("1", "100", "1000", "2") for lit in _LITERAL.findall(re.sub(r"[A-Za-z_]\w*", "", program)))
