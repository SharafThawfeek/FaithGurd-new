"""Numeric claims in an answer, and the context (metric, entity, period) each one is about.

Shared by the rule checker (Channel B), the repairer and scoring, so all three read
an answer the same way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from faithguard.calc.numbers import MONTHS, NumberMention, find_numbers
from faithguard.records import Cell, Claim, Context, Evidence, Question
from faithguard.tables import ENTITY_WORDS, normalise_metric, normalise_period

# word -> (polarity, opposite word)
DIRECTION_WORDS: dict[str, tuple[str, str]] = {}
for up, down in [
    ("rose", "fell"), ("rise", "fall"), ("rises", "falls"), ("risen", "fallen"), ("rising", "falling"),
    ("increased", "decreased"), ("increase", "decrease"), ("increases", "decreases"), ("increasing", "decreasing"),
    ("grew", "declined"), ("growth", "decline"), ("grow", "decline"), ("grows", "declines"), ("growing", "declining"),
    ("up", "down"), ("higher", "lower"), ("gained", "lost"), ("improved", "deteriorated"),
    ("climbed", "dropped"), ("jumped", "dropped"), ("expanded", "contracted"), ("advanced", "retreated"),
    ("larger", "smaller"),
]:
    DIRECTION_WORDS[up] = ("up", down)
    DIRECTION_WORDS[down] = ("down", up)
for word in ("dropped", "drop", "drops", "shrank", "contracted", "lost", "retreated", "deteriorated"):
    DIRECTION_WORDS.setdefault(word, ("down", "rose"))

_WORD = re.compile(r"[A-Za-z]+")
_SENTENCE_END = re.compile(r"(?<=[.!?;])\s+(?=[A-Z(])|\n+")
# A period named right after a figure: "in 2024", "reported in 2025", "for the year ended 31 March 2025",
# "as of December 31, 2025".
_PERIOD_AFTER = re.compile(
    r"^\s*(?:(?:was\s+|were\s+)?(?:reported|recorded|recognised|recognized|posted)\s+)?"
    r"(?:in|for|during|at|as at|as of|at the end of|by the end of)\s+(?:the\s+)?"
    r"(?:(?:fiscal|financial)\s+)?(?:year\s+|period\s+)?(?:(?:ended|ending)\s+(?:on\s+)?)?"
    rf"(?:\d{{1,2}}(?:st|nd|rd|th)?\s+(?:{MONTHS})\s+|(?:{MONTHS})\s+\d{{1,2}},?\s+|(?:{MONTHS})\s+)?"
    r"((?:FY\s?)?(?:19|20)\d{2}(?:\s?[/-]\s?\d{2,4})?)",
    re.IGNORECASE,
)
_YEARISH = re.compile(r"(?<!\d)(?:FY\s?)?(?:19|20)\d{2}(?:\s?[/-]\s?\d{2,4})?(?!\d)", re.IGNORECASE)
_PREVIOUS_YEAR = re.compile(r"\b(?:previous|prior|preceding|last)\s+(?:financial\s+|fiscal\s+)?year\b", re.IGNORECASE)
_PREVIOUS_AFTER = re.compile(
    r"^\s*(?:(?:reported|recorded)\s+)?(?:in|for|during)\s+the\s+(?:previous|prior|preceding|last)\s+"
    r"(?:financial\s+|fiscal\s+)?(?:year|period)\b",
    re.IGNORECASE,
)
_ASIDE_AFTER = re.compile(r"^\s*\([^()]*\)|^\s*\)")  # "(Rs 18,197.4 million)" after a figure, or the end of the aside it sits in
# "owners of the company", "equity holders of the Bank" name who profit belongs to, not which entity reports it
_HOLDERS_OF = re.compile(
    r"\b(?:owners|(?:equity\s+)?holders|shareholders|stockholders)\s+of\s+the\s+(?:company|parent|bank)\b", re.IGNORECASE
)

# Common ways of naming the same line item. Keys are normalised metric names.
ALIASES: dict[str, tuple[str, ...]] = {
    "profit after tax": ("net profit", "profit for the year", "pat", "net income", "profit after taxation"),
    "profit for the year": ("net profit", "profit after tax", "pat", "net income"),
    "net income": ("net profit", "net earnings", "profit after tax", "profit for the year"),
    "profit before tax": ("pbt", "profit before taxation", "profit before income tax", "pre tax profit"),
    "profit before income tax": ("pbt", "profit before tax", "pre tax profit"),
    "revenue": ("revenues", "turnover", "net sales", "sales", "total revenue"),
    "total revenue": ("revenue", "revenues", "turnover"),
    "gross income": ("total income",),
    "total assets": ("assets",),
    "earnings per share": ("eps",),
    "basic earnings per share": ("eps", "earnings per share"),
}


@dataclass(frozen=True)
class Surface:
    text: str  # normalised surface form found in text
    metric: str  # the evidence metric it names


_STOP = {"and", "or", "of", "in", "on", "at", "to", "for", "from", "the", "a", "an", "with", "by"}


def _tail_surfaces(metrics: list[str], taken: set[str]) -> list[Surface]:
    """The distinctive ending of a long row label, as a name for it: an answer says "net investment
    in leases and hire purchase" for "Financial assets at amortised cost - Net investment in leases
    and hire purchase". Only endings of three or more words that name no other row."""
    tails: dict[str, set[str]] = {}
    for m in metrics:
        words = m.split()
        for k in range(3, len(words) - 1):
            tail = " ".join(words[-k:])
            if words[-k] not in _STOP:
                tails.setdefault(tail, set()).add(m)
    out = []
    for tail, owners in tails.items():
        clash = tail in taken or any(f" {tail} " in f" {m} " for m in metrics if m not in owners)
        if len(owners) == 1 and not clash:
            out.append(Surface(tail, next(iter(owners))))
    return out


class Vocabulary:
    """The metric, entity and period names that occur in one item's evidence."""

    def __init__(self, cells: list[Cell]):
        metrics = sorted({c.metric for c in cells if c.metric})
        surfaces = [Surface(m, m) for m in metrics]
        for m in metrics:
            surfaces += [Surface(a, m) for a in ALIASES.get(m, ()) if a not in metrics]
        surfaces += _tail_surfaces(metrics, {s.text for s in surfaces})
        # longest first, so "net interest income" wins over "interest income"
        self.surfaces = sorted(surfaces, key=lambda s: -len(s.text))
        self.entities = sorted({c.entity for c in cells if c.entity})
        self.periods = sorted({c.period for c in cells if c.period})

    def metric_in(self, text: str) -> str | None:
        norm = f" {normalise_metric(text)} "
        for s in self.surfaces:
            if f" {s.text} " in norm:
                return s.metric
        return None

    def metrics_named(self, text: str) -> set[str]:
        """Every evidence metric the text names, by any of its surfaces."""
        norm = f" {normalise_metric(text)} "
        return {s.metric for s in self.surfaces if f" {s.text} " in norm}

    def entity_in(self, text: str) -> str | None:
        if not self.entities:
            return None
        text = _HOLDERS_OF.sub(" ", text)
        found = [ENTITY_WORDS[w] for w in (x.lower() for x in _WORD.findall(text)) if w in ENTITY_WORDS]
        found = [e for e in found if e in self.entities]
        return found[-1] if found else None

    def period_in(self, text: str, base: str | None = None) -> str | None:
        period = normalise_period(text)
        if period:
            return period
        if base and _PREVIOUS_YEAR.search(text):
            return str(int(base) - 1)
        return None

    def context_of(self, text: str) -> Context:
        return Context(metric=self.metric_in(text), entity=self.entity_in(text), period=self.period_in(text))

    def latest_period(self) -> str | None:
        return self.periods[-1] if self.periods else None


def sentence_bounds(text: str, pos: int) -> tuple[int, int]:
    start = 0
    for m in _SENTENCE_END.finditer(text):
        if m.end() <= pos:
            start = m.end()
        else:
            return start, m.start()
    return start, len(text)


def _direction(text: str, mention: NumberMention, window_start: int) -> tuple[str | None, tuple[int, int] | None]:
    """A direction word governing the number: up to six words before it, or right after it ('7% higher')."""
    before = text[window_start : mention.start]
    words = list(_WORD.finditer(before))[-6:]
    for w in reversed(words):
        if w.group().lower() in DIRECTION_WORDS:
            return DIRECTION_WORDS[w.group().lower()][0], (window_start + w.start(), window_start + w.end())
    after = text[mention.end : mention.end + 20]
    m = re.match(r"\s*(?:\w+\s+)?([A-Za-z]+)", after)
    if m and m.group(1).lower() in ("increase", "decrease", "higher", "lower", "growth", "decline", "rise", "fall"):
        word = m.group(1)
        return DIRECTION_WORDS[word.lower()][0], (mention.end + m.start(1), mention.end + m.end(1))
    return None, None


def extract_claims(text: str) -> list[Claim]:
    """Every checkable number in an answer, with any direction word attached to it."""
    claims: list[Claim] = []
    previous_end = 0
    for mention in find_numbers(text):
        if mention.kind == "year":
            continue
        s_start, _ = sentence_bounds(text, mention.start)
        window_start = max(previous_end, s_start)
        direction, span = _direction(text, mention, window_start)
        claims.append(
            Claim(
                id=f"k{len(claims) + 1}",
                start=mention.start,
                end=mention.end,
                text=mention.text,
                kind=mention.kind,  # type: ignore[arg-type]
                value=mention.value,
                decimals=mention.decimals,
                scale=mention.scale,
                currency=mention.currency,
                direction=direction,  # type: ignore[arg-type]
                direction_span=span,
            )
        )
        previous_end = mention.end
    return claims


def mention_of(claim: Claim, text: str) -> NumberMention:
    """The parsed number behind a claim, with its printed style (for rendering replacements)."""
    return next(m for m in find_numbers(text) if m.start == claim.start and m.end == claim.end)


def years_in(text: str) -> list[str]:
    return [p for p in (normalise_period(m.group()) for m in _YEARISH.finditer(text)) if p]


def question_context(question: Question, vocab: Vocabulary) -> Context:
    """What the question asks about. With two years ("in 2019 from 2018"), the later one is the target."""
    ctx = vocab.context_of(question.text)
    years = years_in(question.text)
    period = question.period or (max(years) if years else None) or vocab.latest_period()
    return ctx.model_copy(update={"period": period})


def claim_context(text: str, claims: list[Claim], index: int, vocab: Vocabulary, default: Context) -> Context:
    """What a claim is about: its own clause first, then its sentence, then the question."""
    claim = claims[index]
    s_start, s_end = sentence_bounds(text, claim.start)
    clause_start = max(s_start, claims[index - 1].end if index else 0)
    clause = text[clause_start : claim.start]
    next_start = claims[index + 1].start if index + 1 < len(claims) else s_end
    after = text[claim.end : min(next_start, s_end)]
    sentence = text[s_start:s_end]

    metric = vocab.metric_in(clause) or vocab.metric_in(sentence) or default.metric
    # in "A's deposits were larger than B's by X", X is about A
    subject = re.split(r"\bthan\b", clause, maxsplit=1)[0] if re.search(r"\bthan\b", clause) else ""
    entity = (vocab.entity_in(subject) or vocab.entity_in(clause) or vocab.entity_in(text[s_start : claim.start])
              or vocab.entity_in(sentence) or default.entity)
    change = is_change_claim(text, claims, index)
    years = sorted(set(years_in(sentence)))
    # look past an aside: "Rs. 18,197,393 thousand (Rs 18,197.4 million) in 2024" gives both figures 2024
    rest = after if after.strip(" (") else text[claim.end : s_end]
    rest = _ASIDE_AFTER.sub("", rest, count=1)
    m = _PERIOD_AFTER.match(rest)
    if m and not change:
        period = normalise_period(m.group(1))
    elif not change and default.period and default.period.isdigit() and _PREVIOUS_AFTER.match(rest):
        period = str(int(default.period) - 1)
    else:
        period = vocab.period_in(clause, default.period) if not change else None
        if period is None:
            base_only = (change and len(years) == 1 and default.period is not None and years[0] < default.period
                         and years_in(text[claim.end : s_end]) == years and not years_in(text[s_start : claim.start]))
            if base_only:  # "an increase of Rs. 553,081 thousand compared to the Rs. 3,664,776 thousand reported in 2025"
                return Context(metric=metric, entity=entity, period=default.period, base_period=years[0])
            if len(years) == 1:
                period = years[0]
            elif years and change:
                period = years[-1]  # a change "from 2018 to 2019" is about 2019
            else:
                period = default.period
    base = years[0] if change and len(years) >= 2 and years[0] != period else None
    return Context(metric=metric, entity=entity, period=period, base_period=base)


_CHANGE_PREFIX = re.compile(
    r"\b(?:by|changes? of|difference of|increase of|decrease of|growth of|decline of|rise of|fall of)\s*$", re.IGNORECASE
)
_LEVEL_PREFIX = re.compile(r"\b(?:from|to|at|reached|totalled|totaled)\s*$", re.IGNORECASE)
_CHANGE_WORDS = re.compile(r"\b(?:change[sd]?|growth|grew|movement|variation|year[- ]on[- ]year|yoy)\b", re.IGNORECASE)


def is_change_claim(text: str, claims: list[Claim], index: int) -> bool:
    """Is this number a change (difference or growth rate) rather than a level?

    "a change of 4.0%", "rose 7.0%", "the percentage change was 9.3%" are changes;
    "from 66.0% in 2017", "to Rs. 12,450 million" are levels, even in a sentence about change.
    """
    claim = claims[index]
    s_start, _ = sentence_bounds(text, claim.start)
    before = text[s_start : claim.start]
    if _CHANGE_PREFIX.search(before):
        return True
    if _LEVEL_PREFIX.search(before):
        return False
    if claim.direction is not None:
        return True
    clause = text[max(s_start, claims[index - 1].end if index else 0) : claim.start]
    return bool(_CHANGE_WORDS.search(clause))


def prefers_difference(text: str, claim: Claim) -> bool:
    """'by 2.1%' or 'a change of 2.1%' on a rate means percentage points, not relative growth."""
    s_start, _ = sentence_bounds(text, claim.start)
    return bool(_CHANGE_PREFIX.search(text[s_start : claim.start]))


def evidence_vocabulary(evidence: Evidence) -> Vocabulary:
    return Vocabulary(evidence.cells())
