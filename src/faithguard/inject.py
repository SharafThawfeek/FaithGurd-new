"""The error injector: answers with known errors, for the controlled track.

From a grounded gold example (lookup, difference, growth or share), write a
correct answer from a template, then variants with one planted error:

    period           a figure from the wrong year
    metric           a figure from the wrong line item
    entity           a figure from the wrong entity (Bank instead of Group)
    scale            the right digits with the wrong unit word (thousand vs million)
    sign             the direction word reversed ("rose" for a fall)
    basis            growth computed on the wrong base
    missing_operand  a wrong figure, and the cell needed to fix it removed from the evidence

Errors propagate the way real ones do: a wrong figure changes the growth rate
computed from it. Every item records the action it should receive (send, repair
or abstain), so outcomes can be scored automatically.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from decimal import Decimal

from faithguard.calc import expr, ops
from faithguard.calc.numbers import NumberStyle, default_style, render
from faithguard.data.example import Example
from faithguard.gold import Injection
from faithguard.records import Answer, Cell, Item
from faithguard.tables import parse_table_cell

ERRORS = ("none", "period", "metric", "entity", "scale", "sign", "basis", "missing_operand")


@dataclass
class Shape:
    kind: str  # lookup, difference, growth, share
    a: Cell
    b: Cell | None = None


def shape_of(example: Example) -> Shape | None:
    """Recognise the gold programs the templates can express."""
    if not example.grounded or not example.gold.program:
        return None
    tree = expr.parse(example.gold.program)
    cell = example.evidence.cell
    times100 = isinstance(tree, expr.BinOp) and tree.op == "*" and isinstance(tree.right, expr.Num) and tree.right.value == 100
    if times100:
        tree = tree.left
    R = expr.Ref
    shape = None
    if isinstance(tree, R) and not times100:
        shape = Shape("lookup", cell(tree.cell))
    elif isinstance(tree, expr.BinOp):
        l, r = tree.left, tree.right
        if tree.op == "-" and isinstance(l, R) and isinstance(r, R) and not times100:
            shape = Shape("difference", cell(l.cell), cell(r.cell))
        elif tree.op == "/" and times100:
            if isinstance(l, expr.BinOp) and l.op == "-" and isinstance(l.left, R) and isinstance(l.right, R) and isinstance(r, R) and r.cell == l.right.cell:
                shape = Shape("growth", cell(l.left.cell), cell(l.right.cell))
            elif isinstance(l, R) and isinstance(r, R):
                shape = Shape("share", cell(l.cell), cell(r.cell))
    elif isinstance(tree, expr.Call) and all(isinstance(a, R) for a in tree.args) and len(tree.args) == 2:
        a, b = (cell(x.cell) for x in tree.args)
        shape = Shape({"growth": "growth", "diff": "difference"}.get(tree.fn, ""), a, b) if tree.fn in ("growth", "diff") else None
    if shape is None:
        return None
    for c in (shape.a, shape.b):
        if c is None:
            continue
        label = _label(c)
        if re.search(r"\d", label) or label == "the figure" or not c.row_label:
            return None  # numbers in a label ("member aged 65") read as claims; blank labels cannot be named
        # several columns for the same row and year (e.g. "amount" and "per share") cannot be told apart in text
        twins = [x for x in example.evidence.cells() if x.row == c.row and x.period == c.period and x.entity == c.entity]
        if len(twins) > 1:
            return None
    if shape.kind in ("difference", "growth"):
        # The templates describe a change over time: same line item, later period minus earlier period.
        a, b = shape.a, shape.b
        if a.metric != b.metric or a.entity != b.entity or not a.period or not b.period or a.period <= b.period:
            return None
    if shape.kind == "share" and shape.a.metric == shape.b.metric:
        return None
    return shape


def _style(cell: Cell) -> NumberStyle:
    mention = parse_table_cell(cell.text)
    decimals = mention.decimals if mention else 0
    if cell.kind == "percent":
        return default_style("percent", decimals=decimals or 1)
    return default_style("amount", cell.scale, cell.currency, decimals)


def _label(cell: Cell) -> str:
    text = re.sub(r"\s*\(.*?\)\s*", " ", cell.row_label).strip(" :;-") or (cell.metric or "the figure")
    text = re.sub(r"\s+", " ", text)
    return text


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _in(period: str | None) -> str:
    return f" in {period}" if period else ""


def _pct(value: Decimal) -> str:
    return render(value, default_style("percent", decimals=2 if abs(value) < 1 else 1))


def _sibling(cells: list[Cell], a: Cell, same: tuple[str, ...], differ: str, exclude: set[str]) -> Cell | None:
    """Another cell sharing the `same` context fields with `a` but differing in `differ`, with a different value."""
    for c in cells:
        if c.id == a.id or c.id in exclude or c.value is None or c.kind != a.kind or c.value == a.value:
            continue
        if all(getattr(c, f) == getattr(a, f) for f in same) and getattr(c, differ) not in (None, getattr(a, differ)):
            return c
    return None


def _wrong_cell(cells: list[Cell], s: Shape, error: str) -> Cell | None:
    exclude = {s.a.id} | ({s.b.id} if s.b else set())
    if error == "period":
        return _sibling(cells, s.a, ("metric", "entity"), "period", exclude)
    if error == "metric":
        same_column = [c for c in cells if c.table_id == s.a.table_id and c.col == s.a.col]
        return _sibling(same_column, s.a, ("entity", "period"), "metric", exclude)
    if error == "entity":
        return _sibling(cells, s.a, ("metric", "period"), "entity", exclude)
    return None


def _write(s: Shape, a_value: Decimal, b_value: Decimal | None, variant: int, a_text: str | None = None,
           flip: bool = False, basis: bool = False) -> str | None:
    A = a_text or render(a_value, _style(s.a))
    label = _label(s.a)
    if s.kind == "lookup":
        return f"{_cap(label)} was {A}{_in(s.a.period)}." if variant == 0 or not s.a.period else f"In {s.a.period}, {label} was {A}."
    B = render(b_value, _style(s.b))
    if s.kind == "share":
        try:
            share = ops.share(a_value, b_value)
        except ops.CalcError:
            return None
        return f"{_cap(label)} was {_pct(share)} of {_label(s.b)}{_in(s.a.period)}."
    if not (s.a.period and s.b.period):
        return None
    if s.kind == "difference":
        delta = ops.diff(a_value, b_value)
        if variant == 0 and not flip:
            return f"{_cap(label)} changed from {B} in {s.b.period} to {A} in {s.a.period}, a change of {render(delta, _style(s.a))}."
        up = (delta >= 0) != flip
        return f"{_cap(label)} {'increased' if up else 'decreased'} by {render(abs(delta), _style(s.a))} from {B} in {s.b.period} to {A} in {s.a.period}."
    try:
        g = ops.share(ops.diff(a_value, b_value), abs(a_value)) if basis else ops.growth(a_value, b_value)
    except ops.CalcError:
        return None
    up = (g >= 0) != flip
    if variant == 0:
        return f"{_cap(label)} {'rose' if up else 'fell'} {_pct(abs(g))} from {B} in {s.b.period} to {A} in {s.a.period}."
    return f"{_cap(label)} was {A} in {s.a.period}, {'up' if up else 'down'} {_pct(abs(g))} from {B} in {s.b.period}."


def inject(example: Example, errors: tuple[str, ...] = ERRORS, seed: int = 13) -> list[tuple[Item, Injection]]:
    s = shape_of(example)
    if s is None or s.a.value is None or (s.b is not None and s.b.value is None):
        return []
    rng = random.Random(f"{seed}:{example.question.id}")
    variant = rng.randint(0, 1)
    cells = example.evidence.cells()
    a, b = s.a.value, s.b.value if s.b else None
    correct = _write(s, a, b, variant)
    if correct is None:
        return []
    out = []
    for error in errors:
        evidence, changed, removed, expected = example.evidence, [], [], "repair"
        if error == "none":
            text, expected = correct, "send"
        elif error in ("period", "metric", "entity"):
            wrong = _wrong_cell(cells, s, error)
            text = _write(s, wrong.value, b, variant) if wrong else None
            changed = [wrong.id] if wrong else []
        elif error == "scale":
            if s.kind != "lookup" or s.a.kind != "amount":
                continue
            style = _style(s.a)
            wrong_style = default_style("amount", style.scale + 3, s.a.currency, style.decimals)
            text = _write(s, a, b, variant, a_text=render(a.scaleb(3), wrong_style))
        elif error == "sign":
            text = _write(s, a, b, variant, flip=True) if s.kind in ("growth", "difference") else None
        elif error == "basis":
            text = _write(s, a, b, variant, basis=True) if s.kind == "growth" else None
        elif error == "missing_operand":
            wrong = _wrong_cell(cells, s, "period") or _wrong_cell(cells, s, "metric")
            text = _write(s, wrong.value, b, variant) if wrong else None
            evidence, changed, removed, expected = example.evidence.without([s.a.id]), [wrong.id] if wrong else [], [s.a.id], "abstain"
        else:
            raise ValueError(error)
        if text is None or (error != "none" and text == correct):
            continue
        item_id = f"{example.question.id}:{error}"
        question = example.question.model_copy(update={"question_type": "growth" if s.kind == "growth" else s.kind})
        item = Item(
            id=item_id,
            question=question,
            evidence=evidence,
            answer=Answer(id=item_id, question_id=example.question.id, generator="template" if error == "none" else f"injected:{error}", text=text),
        )
        out.append((item, Injection(item_id=item_id, error=error, expected_action=expected, changed_cells=changed, removed_cells=removed)))
    return out
