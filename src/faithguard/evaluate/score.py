"""Scoring answers against the gold store (evaluation only; never used at decision time).

An answer's state:
    unsupported          some number matches no gold value
    supported_unhelpful  every number matches a gold value, but none is the answer
    supported_useful     every number matches, and one of them is the answer
    abstained            nothing was sent
"""

from __future__ import annotations

from typing import Literal

from faithguard.calc.numbers import NumberMention, find_numbers
from faithguard.claims import extract_claims, is_change_claim
from faithguard.gold import GoldQuestion, GoldValue
from faithguard.records import Claim

State = Literal["unsupported", "supported_unhelpful", "supported_useful", "abstained"]
STATES: tuple[str, ...] = State.__args__  # type: ignore[attr-defined]


def _close(mention: NumberMention, value, target) -> bool:
    return abs(value - target) <= mention.half_unit() + type(target)("1e-9")


def claim_matches(claim: Claim, mention: NumberMention, gold: GoldValue, change: bool = False) -> bool:
    """Does a claim state this gold value? A change ("down 9.3%") must match with its sign;
    a level ("fell to Rs. 5 million") is compared as written."""
    # A bare number may be a percentage printed without its sign, so only labelled kinds must agree.
    if claim.kind != "number" and (claim.kind == "percent") != (gold.kind == "percent"):
        return False
    if change and claim.direction and claim.value >= 0:
        candidates = [claim.value if claim.direction == "up" else -claim.value]
    else:
        candidates = [claim.value]
    if claim.kind == "number":  # a bare number may be printed in the table's unit
        candidates += [c.scaleb(s) for c in list(candidates) for s in (3, 6, 9)]
    return any(_close(mention, c, gold.value) for c in candidates)


def claims_with_change(text: str) -> list[tuple[Claim, bool]]:
    claims = extract_claims(text)
    return [(c, is_change_claim(text, claims, i)) for i, c in enumerate(claims)]


def wrong_numbers(text: str | None, gold: GoldQuestion) -> list[str]:
    """The printed numbers in `text` that match no gold value (empty for an abstention)."""
    if text is None:
        return []
    mentions = {(m.start, m.end): m for m in find_numbers(text)}
    return [
        c.text for c, change in claims_with_change(text)
        if not any(claim_matches(c, mentions[(c.start, c.end)], g, change) for g in gold.values)
    ]


def score_text(text: str | None, gold: GoldQuestion) -> State:
    if text is None:
        return "abstained"
    claims = claims_with_change(text)
    if not claims:
        return "supported_unhelpful"
    mentions = {(m.start, m.end): m for m in find_numbers(text)}
    useful = False
    for claim, change in claims:
        mention = mentions[(claim.start, claim.end)]
        hits = [g for g in gold.values if claim_matches(claim, mention, g, change)]
        if not hits:
            return "unsupported"
        useful = useful or any(g.role == "answer" for g in hits)
    return "supported_useful" if useful else "supported_unhelpful"
