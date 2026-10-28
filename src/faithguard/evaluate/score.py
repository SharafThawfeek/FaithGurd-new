"""Scoring answers against the gold store (evaluation only; never used at decision time).

An answer's state:
    unsupported          some number matches no gold value
    supported_unhelpful  every number matches a gold value, but none is the answer
    supported_useful     every number matches, and one of them is the answer
    abstained            nothing was sent

Template answers (the controlled track) are scored from the gold values alone. Natural
answers are scored with their evidence as well (D-100), which reads four ways people
write a correct number that the gold values alone would reject:

- a change by its size and its direction word ("fell by $172,387 thousand" when the
  gold answer is the size of the fall); the word must say what the two cells did. For a
  change between two losses that the sentence calls a loss, a size word ("narrowed",
  "decreased") follows the size of the loss; a word that judges ("improved") is not read;
- a loss as a positive figure right after "loss" ("net loss of $64,907 thousand",
  "loss per share was 1.98") when the gold value is negative, unless the clause also
  speaks of profit, income or earnings, or of a loss turned, avoided or recovered from.
  After such a loss word, a positive gold figure matches only if its cell is a loss line
  printed positive. A bare figure in accounting brackets ("$(1.98)") reads as negative;
- a ratio written as a percentage ("208%" for 2.08), for a level figure only;
- the constants of a worked calculation ("× 100", the "1" of "2.08:1"), which are skipped.

None of this reads a detector's output, but the scorer reads numbers with the same code as
the rule checker (calc/numbers, claims), so an error that code cannot see escapes both.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from faithguard.calc.expr import BinOp, Call, ExprError, Ref, parse
from faithguard.calc.numbers import NumberMention, find_numbers
from faithguard.claims import extract_claims, is_change_claim
from faithguard.gold import GoldQuestion, GoldValue
from faithguard.records import Claim, Evidence

State = Literal["unsupported", "supported_unhelpful", "supported_useful", "abstained"]
STATES: tuple[str, ...] = State.__args__  # type: ignore[attr-defined]

# "loss" naming a loss, not a statement or a pair ("profit or loss", "gains and losses", "income (loss)", "loss-making")
LOSS = re.compile(r"(?<!\bor )(?<!\band )(?<![(/&])\b(?:loss|losses|deficit|deficits)\b(?!-)", re.IGNORECASE)
# a clause that turns or denies the loss, or speaks of a profit, cannot make a figure negative
_NOT_A_LOSS = re.compile(
    r"\b(?:profits?|income|earn\w*|gains?|surplus|turned|turning|swung|swing|avoid\w*|without|no longer|recover\w*|revers\w*|instead)\b",
    re.IGNORECASE,
)
_LOSS_WORDS_BEFORE = 4  # "loss" must sit among the last few words before the figure
_FIGURE_TOKEN = re.compile(r"^(?:US\$|Rs\.?|LKR|USD|\$|€|£)?\(?[\d,.]+\)?%?$|^(?:thousand|million|billion|bn|mn|'000)$", re.IGNORECASE)
_BREAK = re.compile(r"[;:\n]|[.!?,](?=\s)")
_SENTENCE_BREAK = re.compile(r"\n|[.!?](?=\s)")
_ABBREVIATION = re.compile(r"(?:\b(?:Rs|approx|No|Co|Ltd|Inc|Plc|Corp|vs|Mr|Ms|Dr|St|FY|U\.S|e\.g|i\.e))$", re.IGNORECASE)
# judging words: for a loss, "improved" means it shrank, so the size of the loss cannot check them
_JUDGING = {"improved", "improve", "improves", "improving", "deteriorated", "deteriorate", "deteriorating",
            "strengthened", "weakened", "worsened", "recovered", "gained", "lost", "advanced", "retreated"}
_TIMES = re.compile(r"(?:(?<![A-Za-z])[x×*·]|\btimes)\s*$", re.IGNORECASE)
_BARE = re.compile(r"[\d,]+(?:\.\d+)?")


@dataclass(frozen=True)
class Natural:
    """What a natural answer's evidence says about its gold question."""

    text: str
    change: tuple[str | None, str | None, bool] | None  # (signed direction, size direction, both losses) of a two-period change
    loss_line: bool  # a gold cell is a loss line printed as a positive figure


def _direction(delta: Decimal) -> str | None:
    return "up" if delta > 0 else "down" if delta < 0 else None


def is_change_program(program: str | None) -> bool:
    try:
        node = parse(program) if program else None
    except ExprError:
        return False
    if isinstance(node, Call):
        return node.fn in ("growth", "diff") and len(node.args) == 2 and all(isinstance(a, Ref) for a in node.args)
    return isinstance(node, BinOp) and node.op == "-" and isinstance(node.left, Ref) and isinstance(node.right, Ref)


def natural_context(text: str, gold: GoldQuestion, evidence: Evidence) -> Natural:
    cells = {c.id: c for c in evidence.cells()}
    gold_cells = [cells[v.cell] for v in gold.values if v.cell in cells]
    operands = [cells[v.cell] for v in gold.values if v.role == "operand" and v.cell in cells]
    change = None
    if len(operands) == 2 and is_change_program(gold.program):
        a, b = operands
        if (a.metric, a.entity) == (b.metric, b.entity) and a.period and b.period and a.period != b.period and None not in (a.raw, b.raw):
            later, earlier = (a, b) if (len(a.period), a.period) > (len(b.period), b.period) else (b, a)
            change = (_direction(later.value - earlier.value), _direction(abs(later.value) - abs(earlier.value)),
                      later.value < 0 and earlier.value < 0)
    loss_line = any(LOSS.search(c.metric or c.row_label) and c.raw is not None and c.raw > 0 for c in gold_cells)
    return Natural(text=text, change=change, loss_line=loss_line)


def _breaks(text: str, pattern: re.Pattern, end: int) -> list[int]:
    """Where clauses or sentences break before `end`; the full stop of "Rs." or "approx." does not break."""
    return [m.end() for m in pattern.finditer(text, 0, end) if not (m.group() == "." and _ABBREVIATION.search(text, 0, m.start()))]


def clause_before(text: str, start: int) -> str:
    breaks = _breaks(text, _BREAK, start)
    return text[(breaks[-1] if breaks else 0) : start]


def sentence_of(text: str, start: int, end: int) -> str:
    breaks = _breaks(text, _SENTENCE_BREAK, start)
    ends = [b for b in _breaks(text, _SENTENCE_BREAK, len(text)) if b > end]
    return text[(breaks[-1] if breaks else 0) : (ends[0] if ends else len(text))]


def _loss_cue(natural: Natural, claim: Claim) -> str | None:
    """"word" when "loss" names the figure, "brackets" for a bare figure in accounting brackets."""
    clause = clause_before(natural.text, claim.start)
    words = [w for w in clause.split() if not _FIGURE_TOKEN.match(w)]  # "from US$165,490 thousand to" skips the figure
    if LOSS.search(" ".join(words[-_LOSS_WORDS_BEFORE:])) and not _NOT_A_LOSS.search(clause):
        return "word"
    text = natural.text
    if _BARE.fullmatch(claim.text) and text[claim.start - 1 : claim.start] == "(" and text[claim.end : claim.end + 1] == ")":
        return "brackets"
    return None


def _constant(text: str, claim: Claim) -> bool:
    """A worked calculation's constant: the 100 of "× 100", the 1 of "2.08:1"."""
    if claim.kind != "number":
        return False
    before = text[: claim.start]
    return (claim.value == 100 and bool(_TIMES.search(before))) or (claim.value == 1 and before.endswith(":"))


def _close(mention: NumberMention, value, target) -> bool:
    return abs(value - target) <= mention.half_unit() + type(target)("1e-9")


def _in_units(claim: Claim, values: list[Decimal]) -> list[Decimal]:
    """A bare number may be printed in the table's unit."""
    return values + ([v.scaleb(s) for v in values for s in (3, 6, 9)] if claim.kind == "number" else [])


def _change_matches(claim: Claim, mention: NumberMention, gold: GoldValue, natural: Natural) -> bool | None:
    """A directional change against the answer of a two-period change: None when this rule does not apply."""
    if claim.value < 0:
        return False  # "increased by -11.2%": a minus sign beside a direction word is a sign error (guide v2)
    signed, size, losses = natural.change
    word = natural.text[claim.direction_span[0] : claim.direction_span[1]].lower() if claim.direction_span else ""
    if losses and LOSS.search(sentence_of(natural.text, claim.start, claim.end)):
        if word in _JUDGING:
            return False  # "the loss improved": the size of the loss cannot check a judging word
        moved = size
    else:
        moved = signed
    if moved is None:
        return None
    return claim.direction == moved and any(_close(mention, v, abs(gold.value)) for v in _in_units(claim, [abs(claim.value)]))


def claim_matches(claim: Claim, mention: NumberMention, gold: GoldValue, change: bool = False, natural: Natural | None = None) -> bool:
    """Does a claim state this gold value? A change ("down 9.3%") must match with its sign;
    a level ("fell to Rs. 5 million") is compared as written. `natural` adds the readings above."""
    if natural is not None and claim.kind == "percent" and gold.kind == "ratio":
        level = not change and not claim.direction and claim.value > 0 and gold.value > 0
        return level and _close(mention, claim.value, gold.value * 100)
    # A bare number may be a percentage printed without its sign, so only labelled kinds must agree.
    if claim.kind != "number" and (claim.kind == "percent") != (gold.kind == "percent"):
        return False
    if natural is not None and natural.change and change and claim.direction and gold.role == "answer":
        matched = _change_matches(claim, mention, gold, natural)
        if matched is not None:
            return matched
    if change and claim.direction and claim.value >= 0:
        candidates = [claim.value if claim.direction == "up" else -claim.value]
    elif natural is not None and not change and claim.value >= 0 and (cue := _loss_cue(natural, claim)):
        candidates = [-claim.value] + ([claim.value] if cue == "word" and natural.loss_line else [])
    else:
        candidates = [claim.value]
    return any(_close(mention, c, gold.value) for c in _in_units(claim, candidates))


def claims_with_change(text: str) -> list[tuple[Claim, bool]]:
    claims = extract_claims(text)
    return [(c, is_change_claim(text, claims, i)) for i, c in enumerate(claims)]


def scored_claims(text: str, natural: Natural | None) -> list[tuple[Claim, bool]]:
    return [(c, change) for c, change in claims_with_change(text) if natural is None or not _constant(text, c)]


def wrong_numbers(text: str | None, gold: GoldQuestion, evidence: Evidence | None = None) -> list[str]:
    """The printed numbers in `text` that match no gold value (empty for an abstention)."""
    if text is None:
        return []
    natural = natural_context(text, gold, evidence) if evidence is not None else None
    mentions = {(m.start, m.end): m for m in find_numbers(text)}
    return [
        c.text for c, change in scored_claims(text, natural)
        if not any(claim_matches(c, mentions[(c.start, c.end)], g, change, natural) for g in gold.values)
    ]


def score_text(text: str | None, gold: GoldQuestion, evidence: Evidence | None = None) -> State:
    """Pass a natural answer's evidence; template answers are scored without it."""
    if text is None:
        return "abstained"
    natural = natural_context(text, gold, evidence) if evidence is not None else None
    claims = scored_claims(text, natural)
    if not claims:
        return "supported_unhelpful"
    mentions = {(m.start, m.end): m for m in find_numbers(text)}
    useful = False
    for claim, change in claims:
        mention = mentions[(claim.start, claim.end)]
        hits = [g for g in gold.values if claim_matches(claim, mention, g, change, natural)]
        if not hits:
            return "unsupported"
        useful = useful or any(g.role == "answer" for g in hits)
    return "supported_useful" if useful else "supported_unhelpful"
