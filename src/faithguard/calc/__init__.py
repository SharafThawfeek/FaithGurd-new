"""The shared calculation API: numbers in text, Decimal arithmetic, and the cell expression language."""

from faithguard.calc.expr import ExprError, calculate, evaluate, parse, refs
from faithguard.calc.numbers import (
    NumberMention,
    NumberStyle,
    default_style,
    detect_scale,
    find_numbers,
    matches,
    parse_cell,
    parse_number,
    render,
)
from faithguard.calc.ops import CalcError, diff, growth, ratio, share

__all__ = [
    "CalcError",
    "ExprError",
    "NumberMention",
    "NumberStyle",
    "calculate",
    "default_style",
    "detect_scale",
    "diff",
    "evaluate",
    "find_numbers",
    "growth",
    "matches",
    "parse",
    "parse_cell",
    "parse_number",
    "ratio",
    "refs",
    "render",
    "share",
]
