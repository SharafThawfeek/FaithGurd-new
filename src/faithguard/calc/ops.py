"""Exact Decimal arithmetic for financial calculations.

Each function raises CalcError instead of returning a misleading number (for
example, growth from a zero base).
"""

from __future__ import annotations

from decimal import Context, Decimal, DivisionByZero, InvalidOperation

CONTEXT = Context(prec=34)


class CalcError(ValueError):
    pass


def _div(a: Decimal, b: Decimal) -> Decimal:
    if b == 0:
        raise CalcError("division by zero")
    try:
        return CONTEXT.divide(a, b)
    except (DivisionByZero, InvalidOperation) as err:
        raise CalcError(str(err)) from err


def diff(a: Decimal, b: Decimal) -> Decimal:
    """a minus b."""
    return CONTEXT.subtract(a, b)


def growth(current: Decimal, previous: Decimal) -> Decimal:
    """Percentage change from previous to current, on the size of the previous value."""
    return CONTEXT.multiply(_div(diff(current, previous), abs(previous)), Decimal(100))


def share(part: Decimal, whole: Decimal) -> Decimal:
    """part as a percentage of whole."""
    return CONTEXT.multiply(_div(part, whole), Decimal(100))


def ratio(a: Decimal, b: Decimal) -> Decimal:
    return _div(a, b)


def total(*values: Decimal) -> Decimal:
    result = Decimal(0)
    for v in values:
        result = CONTEXT.add(result, v)
    return result


def mean(*values: Decimal) -> Decimal:
    if not values:
        raise CalcError("average of nothing")
    return _div(total(*values), Decimal(len(values)))


def absolute(value: Decimal) -> Decimal:
    return abs(value)


# name -> (function, number of arguments; -1 means one or more)
FUNCTIONS = {
    "growth": (growth, 2),
    "share": (share, 2),
    "ratio": (ratio, 2),
    "diff": (diff, 2),
    "sum": (total, -1),
    "avg": (mean, -1),
    "abs": (absolute, 1),
}
