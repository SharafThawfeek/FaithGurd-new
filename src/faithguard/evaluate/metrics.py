"""Policy metrics: what reaches the user, and how often it is wrong.

    emission coverage  share of items where an answer was sent (original or fixed)
    residual risk      share of sent answers that are unsupported (the quantity certified at alpha)
    useful coverage    share of items where a supported, useful answer was sent
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable


def policy_metrics(states: Iterable[str]) -> dict[str, float]:
    states = list(states)
    n = len(states)
    emitted = [s for s in states if s != "abstained"]
    unsafe = sum(s == "unsupported" for s in emitted)
    useful = sum(s == "supported_useful" for s in emitted)
    return {
        "items": n,
        "emitted": len(emitted),
        "emission_coverage": len(emitted) / n if n else 0.0,
        "residual_risk": unsafe / len(emitted) if emitted else 0.0,
        "useful_coverage": useful / n if n else 0.0,
        "unsafe_emitted": unsafe,
    }


def flip_matrix(pairs: Iterable[tuple[str, str]]) -> dict[str, dict[str, int]]:
    """Counts of (state of the original, state after repair), so harm from repair is visible."""
    counts = Counter(pairs)
    rows = ("unsupported", "supported_unhelpful", "supported_useful")
    cols = rows + ("abstained",)
    return {r: {c: counts.get((r, c), 0) for c in cols} for r in rows}
