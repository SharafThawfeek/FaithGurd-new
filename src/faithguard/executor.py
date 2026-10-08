"""The deterministic executor: runs an edit program against an answer.

KEEP leaves a claim alone, COPY writes a cell's value, CALCULATE writes the result
of a cell expression, CANNOT_FIX stops. New numbers are written in the original
claim's printed style, and only claim spans (and their direction words) change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from faithguard.calc import expr
from faithguard.calc.numbers import render
from faithguard.calc.ops import CalcError
from faithguard.claims import DIRECTION_WORDS, mention_of
from faithguard.records import Calculate, CannotFix, Claim, Copy, EditProgram, Item, Keep


class ExecError(ValueError):
    """The program is invalid for this item: unknown claim or cell, bad expression, or a type mismatch."""


@dataclass
class Change:
    claim_id: str
    start: int
    end: int
    old: str
    new: str
    value: Decimal
    cells: list[str]


@dataclass
class ExecResult:
    text: str
    changes: list[Change] = field(default_factory=list)
    cannot_fix: CannotFix | None = None
    replacements: list[tuple[int, int, str]] = field(default_factory=list)  # (start, end, new) in the original text


def apply(text: str, replacements: list[tuple[int, int, str]]) -> str:
    for start, end, new in sorted(replacements, reverse=True):
        text = text[:start] + new + text[end:]
    return text


def _match_case(word: str, like: str) -> str:
    if like.isupper():
        return word.upper()
    if like[:1].isupper():
        return word[:1].upper() + word[1:]
    return word


def execute(item: Item, claims: list[Claim], program: EditProgram) -> ExecResult:
    text = item.answer.text
    by_id = {c.id: c for c in claims}
    seen: set[str] = set()
    for edit in program.edits:
        if isinstance(edit, CannotFix):
            return ExecResult(text=text, cannot_fix=edit)
        if edit.claim not in by_id:
            raise ExecError(f"unknown claim {edit.claim}")
        if edit.claim in seen:
            raise ExecError(f"claim {edit.claim} edited twice")
        seen.add(edit.claim)

    replacements: list[tuple[int, int, str]] = []
    changes: list[Change] = []
    for edit in program.edits:
        if isinstance(edit, Keep):
            continue
        claim = by_id[edit.claim]
        mention = mention_of(claim, text)
        bare = claim.kind == "number"  # no unit printed: work in the table's printed units

        def resolve(cell_id: str) -> Decimal:
            try:
                cell = item.evidence.cell(cell_id)
            except KeyError as err:
                raise ExecError(f"unknown cell {cell_id}") from err
            value = cell.raw if bare else cell.value
            if value is None:
                raise ExecError(f"cell {cell_id} holds no number")
            return value

        if isinstance(edit, Copy):
            cell = item.evidence.cell(edit.cell) if _has_cell(item, edit.cell) else None
            if cell is None:
                raise ExecError(f"unknown cell {edit.cell}")
            if (claim.kind == "percent") != (cell.kind == "percent"):
                raise ExecError(f"COPY of a {cell.kind} cell into a {claim.kind} claim")
            value, used, is_change = resolve(edit.cell), [edit.cell], False
        elif isinstance(edit, Calculate):
            try:
                tree = expr.parse(edit.expr)
                value = expr.evaluate(tree, resolve)
            except (expr.ExprError, CalcError) as err:
                raise ExecError(str(err)) from err
            used, is_change = expr.refs(tree), claim.direction is not None
        else:
            continue

        shown = value
        if is_change and claim.direction_span:
            polarity = "down" if value < 0 else "up"
            shown = abs(value)
            ds, de = claim.direction_span
            word = text[ds:de]
            current, opposite = DIRECTION_WORDS[word.lower()]
            if current != polarity:
                replacements.append((ds, de, _match_case(opposite, word)))
        new = render(shown, mention.style)
        if new != claim.text:
            replacements.append((claim.start, claim.end, new))
        changes.append(Change(claim.id, claim.start, claim.end, claim.text, new, value, used))

    replacements.sort()
    for (s1, e1, _), (s2, _, _) in zip(replacements, replacements[1:]):
        if s2 < e1:
            raise ExecError("edits overlap")
    return ExecResult(text=apply(text, replacements), changes=changes, replacements=replacements)


def _has_cell(item: Item, cell_id: str) -> bool:
    try:
        item.evidence.cell(cell_id)
        return True
    except KeyError:
        return False
