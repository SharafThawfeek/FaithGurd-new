"""Which answers code labels and which go to a person (D-100).

Every numeric benchmark question has a gold cell program, so the gold scorer can tell
whether an answer's numbers are right. Code labels an answer only when nothing else in
it could still be wrong:

- the question asks for a number (narrative and comparison questions go to a person,
  and so does a difference between two entities, whose sign the words carry);
- every number in the answer matches a gold value, read with the evidence, and one of
  them is the answer (`score_text` says supported_useful);
- every year, "this year" or "last year", Group/Company/Bank word, metric name and unit
  word belongs to the cells its figure matched, and in a change between two periods
  "from" introduces the earlier figure and "to" the later one;
- every direction word ("rose", "narrowed") says how the two cells moved;
- no negation, hedge or guess ("not", "only", "unclear", "may"), no explanation or
  judgement ("driven by", "strong", "record"), no figure in words or fraction, no
  quarter or half-year, no percentage points, no currency the report does not use, no
  currency after a bare figure, no "loss" beside a profit figure, no thinking leak.

A code label says correct and useful, with no spans. Everything else goes to a person,
along with a stratified random audit of 150 code labels hidden among the other tasks;
the code labels stand only if people overrule at most one (`audit`). Routing reads no
detector output, but it reads numbers with the same code as the rule checker, so an
error that code cannot see escapes both; the audit bounds how often.

Code labels take the gold as true, so on test and calibration questions triage runs only
once every question has a second reader, and only after the pre-registration is filed.
"""

from __future__ import annotations

import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Sequence

from faithguard.calc.numbers import find_numbers
from faithguard.claims import DIRECTION_WORDS, Vocabulary
from faithguard.evaluate.score import LOSS, claim_matches, clause_before, is_change_program, natural_context, score_text, scored_claims, sentence_of
from faithguard.gold import GoldLabel, GoldQuestion, GoldStore
from faithguard.records import Cell, Claim, Item
from faithguard.stats.certify import clopper_pearson_upper
from faithguard.tables import entity_of, normalise_metric, normalise_period

AUTO_ANNOTATOR = "code-scorer-v1"
AUDIT_SIZE = 150
AUDIT_SEED = 2026
AUDIT_MAX_WRONG = 1  # the code labels stand if people overrule at most this many (95% upper bound 3.1% at 150)
LOCKED_SPLITS = {"test", "calibration"}

NEGATION = re.compile(
    r"\b(?:not|no|never|neither|nor|cannot|unable|lacks?|lacking|unavailable|missing|absent|without|impossible|insufficient"
    r"|only|unknown|unclear|unspecified|undisclosed|fail(?:s|ed|ing)?|omit\w*|may|might|could|appears?|appeared|seems?|seemed"
    r"|assum\w*|possibly|presumably|likely|uncertain\w*|estimat\w*)\b|n't\b",
    re.IGNORECASE,
)
# a cause, an interpretation or a judgement: nothing in the tables can confirm it
EXPLANATION = re.compile(
    r"\b(?:driven|drive[sn]?|driving|due to(?!\s+(?:depositors|banks|customers|other|related|the bank|holding))|because"
    r"|reflect\w*|indicat\w*|suggest\w*|owing|thanks to|supported by|as a result|mainly|primarily|largely|partly|chiefly|record|highest|lowest|peak|strong\w*|solid|healthy|robust|weak\w*"
    r"|leverag\w*|liquidity|stable|stability|significant\w*|substantial\w*|impressive|poor|concern\w*|efficien\w*|favou?rabl\w*"
    r"|positive|negative|good|bad|more|less|fewer|most|least|above|below|outperform\w*|underperform\w*)\b",
    re.IGNORECASE,
)
# a figure written in words: "twelve percent", "three million", "doubled", "a fifth"; not "the two periods"
NUMBER_WORDS = re.compile(
    r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|"
    r"eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred)(?:[\s-]+\w+)?\s+"
    r"(?:percent|per cent|percentage points?|points?|times|thousand|million|billion|lakhs?|crores?)\b"
    r"|\b(?:half|halved|double[ds]?|doubling|twice|triple[ds]?|tripling|\w+fold|thirds?|quarters?|fifths?|sixths?|tenths?)\b"
    r"|(?<![\d%\s])\s*\b(?:percent|per cent)\b|^\s*(?:percent|per cent)\b",
    re.IGNORECASE,
)
PART_YEAR = re.compile(r"\b(?:quarter\w*|Q[1-4]|H[12]|half[- ]year\w*|interim|(?:three|six|nine|3|6|9)[- ]months?)\b", re.IGNORECASE)
POINTS = re.compile(r"\b(?:percentage points?|pp|ppts?|bps|basis points?)\b", re.IGNORECASE)
CURRENCIES = (
    (re.compile(r"\bIndian\b|\bINR\b|₹", re.IGNORECASE), "INR"),
    (re.compile(r"\bRs\b\.?|\bLKR\b|\bSLR\b|\brupees?\b", re.IGNORECASE), "LKR"),
    (re.compile(r"\$|\bUSD\b|\bdollars?\b", re.IGNORECASE), "USD"),
    (re.compile(r"€|\bEUR\b|\beuros?\b", re.IGNORECASE), "EUR"),
    (re.compile(r"£|\bGBP\b|\bsterling\b", re.IGNORECASE), "GBP"),
)
_CURRENCY_AFTER = re.compile(r"^\s*(?:Rs\b\.?|US\$|\$|SLR\b|LKR\b|USD\b)")
DIRECTION = re.compile(
    r"\b(?:" + "|".join(sorted(DIRECTION_WORDS, key=len, reverse=True)) +
    r"|narrow\w*|widen\w*|worsen\w*|deepen\w*|eas(?:ed|ing)|reduc\w*|surg\w*|soar\w*|plung\w*|plummet\w*|slump\w*|tumbl\w*"
    r"|halved|doubled|greater|exceed\w*|improve\w*|deteriorat\w*|strengthen\w*|weaken\w*|recover\w*|shr[iau]nk\w*|dip\w*|slip\w*"
    r"|sank|sink\w*|slid\w*|slide\w*|erod\w*|reced\w*|moderat\w*|contraction|rebound\w*|spik\w*|balloon\w*|accelerat\w*"
    r"|slow\w*|rall\w*|outpac\w*|climb\w*|jump\w*|rocket\w*)\b",
    re.IGNORECASE,
)
# which way a word says the figure moved, beyond the claim reader's own list; judging words cannot be checked on a loss
_MORE = re.compile(r"^(?:widen\w*|deepen\w*|surg\w*|soar\w*|doubled|rebound\w*|spik\w*|balloon\w*|rall\w*|climb\w*|jump\w*|rocket\w*)$",
                   re.IGNORECASE)
_LESS = re.compile(r"^(?:narrow\w*|reduc\w*|plung\w*|plummet\w*|slump\w*|tumbl\w*|halved|shr[iau]nk\w*|dip\w*|slip\w*|sank|sink\w*"
                   r"|slid\w*|slide\w*|erod\w*|reced\w*|contraction)$", re.IGNORECASE)
_JUDGING = re.compile(r"^(?:improve\w*|deteriorat\w*|worsen\w*|strengthen\w*|weaken\w*|recover\w*|eas(?:ed|ing)|gained|lost|advanced"
                      r"|retreated)$", re.IGNORECASE)
PERIOD = re.compile(r"\b(?:FY\s?)?(?:19|20)\d{2}(?:\s?/\s?\d{2,4})?\b|\bFY\s?\d{2}\b", re.IGNORECASE)
RELATIVE_YEAR = re.compile(r"\b(?P<this>this|current)\s+(?:fiscal\s+|financial\s+)?year\b"
                           r"|\b(?P<last>last|previous|prior|preceding)\s+(?:fiscal\s+|financial\s+)?year\b", re.IGNORECASE)
# not "the Group's Statement of profit or loss" or "the Company's annual report", which name a document
ENTITY = re.compile(r"\b(?:group|consolidated|bank|company|parent|standalone)\b(?!'s\s+(?:statements?|consolidated|financial|annual|report))",
                    re.IGNORECASE)
SCALE = re.compile(r"\b(?P<w>thousands?|millions?|billions?)\b|(?P<k>'000)")
# "owners of the company", "equity holders of the parent" name a line of the statement, not an entity
_LINE_ITEM = re.compile(r"\b(?:owners?|holders?|shareholders?|members?|stakeholders?)\s+of\s+(?:the\s+)?$", re.IGNORECASE)
_OWNED_BEFORE = re.compile(r"\b(?:in|for|during|of|at|as at|as of|ended|ending|on|year|fiscal)(?:\s+the)?\s*$", re.IGNORECASE)
_EARLIER_BEFORE = re.compile(r"\b(?:compared (?:with|to)|from|since|over|against|versus|vs\.?|relative to|than)\s+(?:the\s+)?$",
                             re.IGNORECASE)
_TO_LEVEL = re.compile(r"(?<!compared )(?<!relative )(?<!due )(?<!attributable )\bto\b", re.IGNORECASE)
# "derived from", "calculated from" name a source, not the earlier figure
_FROM_LEVEL = re.compile(r"(?<!derived )(?<!calculated )(?<!computed )(?<!taken )(?<!obtained )(?<!extracted )(?<!comes )\bfrom\b",
                         re.IGNORECASE)
_FIGURE_TOKEN = re.compile(r"^(?:US\$|Rs\.?|LKR|USD|\$|€|£)?\(?[\d,.]+\)?%?$|^(?:thousands?|millions?|billions?|bn|mn|'000)$",
                           re.IGNORECASE)
_STATE_REASON = {"unsupported": "a number the gold values do not cover", "supported_unhelpful": "no number states the answer"}


def _period_key(period: str) -> tuple[int, str]:
    return len(period), period


class _Reading:
    """One answer's figures, the cells each matched, and the two periods of a change question."""

    def __init__(self, item: Item, gold: GoldQuestion):
        self.text, self.item, self.gold = item.answer.text, item, gold
        self.natural = natural_context(self.text, gold, item.evidence)
        self.cells = {c.id: c for c in item.evidence.cells()}
        mentions = {(m.start, m.end): m for m in find_numbers(self.text)}
        self.scored = scored_claims(self.text, self.natural)
        self.claims = [c for c, _ in self.scored]
        self.matched: dict[str, list[Cell]] = {}
        self.computed: set[str] = set()  # figures matching a computed answer (a growth, a difference), not a cell
        for c, change in self.scored:
            hits = [g for g in gold.values if claim_matches(c, mentions[(c.start, c.end)], g, change, self.natural)]
            self.matched[c.id] = [self.cells[g.cell] for g in hits if g.cell in self.cells]
            if any(g.role == "answer" and not g.cell for g in hits):
                self.computed.add(c.id)
        operands = [self.cells[v.cell] for v in gold.values if v.role == "operand" and v.cell in self.cells]
        self.later = self.earlier = None
        if self.natural.change and len(operands) == 2:
            a, b = sorted(operands, key=lambda x: _period_key(x.period))
            self.earlier, self.later = a.period, b.period

    def periods(self, claim: Claim, before: str) -> set[str]:
        """The periods a word owned by this figure may name: its cells', or for a computed change the later
        period, and the earlier one after "from", "compared with" or "over"."""
        if claim.id in self.computed and self.later:
            if re.search(r"\bbetween\b", clause_before(before, len(before))):  # "between February 1, 2025 and January 31, 2026"
                return {self.earlier, self.later}
            return {self.earlier} if _EARLIER_BEFORE.search(before) else {self.later}
        cells = self.matched.get(claim.id, []) + ([self.cells[v.cell] for v in self.gold.values if v.cell in self.cells]
                                                  if claim.id in self.computed else [])
        return {c.period for c in cells if c.period}

    def all_cells(self) -> list[Cell]:
        return [c for cells in self.matched.values() for c in cells]

    def sentence_claims(self, start: int, end: int) -> list[Claim]:
        sentence = sentence_of(self.text, start, end)
        return [c for c in self.claims if sentence_of(self.text, c.start, c.end) == sentence]


def _owner(text: str, start: int, end: int, claims: list[Claim]) -> Claim | None:
    """The figure a year or entity word belongs to: the one before it after "in", "for" or "ended";
    else the next figure if it follows within three words with nothing between; else the one before."""
    before = [c for c in claims if c.end <= start]
    after = [c for c in claims if c.start >= end]
    prev, nxt = (before[-1] if before else None), (after[0] if after else None)
    if prev and _OWNED_BEFORE.search(text[:start]):
        return prev
    if nxt:
        gap = text[end : nxt.start]
        if len(gap.split()) <= 3 and not re.search(r"[;,.:]\s", gap) and not PERIOD.search(gap):
            return nxt
    return prev or nxt


def _in_the_questions_name(item: Item, start: int, end: int) -> bool:
    """"Sampath Bank Group's" in an answer to a question that says "Sampath Bank Group's": the entity word
    is part of the name the question uses, not a column."""
    text = item.answer.text
    left = re.search(r"(?:[A-Z][\w&.'-]*\s+)+$", text[:start])
    right = re.match(r"(?:\s+[A-Z][\w&.'-]*)*", text[end:])
    name = (left.group() if left else "") + text[start:end] + (right.group() if right else "")
    return name != text[start:end] and name.strip().rstrip("'s") in item.question.text


def _near_before(text: str, start: int, words: int = 4) -> str:
    """The last few words of a figure's clause, skipping other figures ("from US$165,490 thousand to")."""
    kept = [w for w in clause_before(text, start).split() if not _FIGURE_TOKEN.match(w)]
    return " ".join(kept[-words:])


def _own_words(text: str, claim: Claim, claims: list[Claim]) -> str:
    """The words a figure's clause gives it: since the clause began, or since the figure before it."""
    clause = clause_before(text, claim.start)
    prev = max((c.end for c in claims if c.end <= claim.start), default=0)
    return text[max(claim.start - len(clause), prev) : claim.start]


def _nearest_metric(vocabulary: Vocabulary, words: str) -> str | None:
    """The evidence metric named last in `words`, the longest where two end together."""
    norm = f" {normalise_metric(words)} "
    found = [(norm.rfind(f" {s.text} ") + len(s.text), len(s.text), s.metric) for s in vocabulary.surfaces if f" {s.text} " in norm]
    return max(found)[2] if found else None


def wording_mismatch(item: Item, gold: GoldQuestion) -> list[str]:
    """Years, entity words, metric names, units and "from"/"to" that do not belong to the cells the figures matched."""
    r = _Reading(item, gold)
    text, out = r.text, []
    mentions = [(m.start(), m.end(), normalise_period(m.group())) for m in PERIOD.finditer(text)]
    if r.later:
        mentions += [(m.start(), m.end(), r.later if m.group("this") else r.earlier) for m in RELATIVE_YEAR.finditer(text)]
    every_period = {c.period for c in r.all_cells() if c.period}
    for start, end, period in mentions:
        owner = _owner(text, start, end, r.sentence_claims(start, end))
        allowed = r.periods(owner, text[:start]) if owner else every_period
        if allowed and period not in allowed:
            out.append("a year that is not its figure's")
            break
    every_entity = {c.entity for c in r.all_cells() if c.entity}
    for m in ENTITY.finditer(text):
        if _LINE_ITEM.search(text[: m.start()]) or _in_the_questions_name(item, m.start(), m.end()):
            continue
        owner = _owner(text, m.start(), m.end(), r.sentence_claims(m.start(), m.end()))
        allowed = {c.entity for c in r.matched.get(owner.id, []) if c.entity} if owner else every_entity
        if allowed and entity_of(m.group()) not in allowed:
            out.append("an entity that is not its figure's")
            break
    if r.later:  # in a change between two periods, "from" brings in the earlier figure and "to" the later one
        for c in r.claims:
            periods = {x.period for x in r.matched.get(c.id, []) if x.period}
            near = _near_before(text, c.start)
            last = max([(m.start(), r.earlier) for m in _FROM_LEVEL.finditer(near)]
                       + [(m.start(), r.later) for m in _TO_LEVEL.finditer(near)], default=None)  # the nearer word decides
            wanted = last[1] if last else None
            if wanted and c.id not in r.computed and periods and wanted not in periods:
                out.append("a 'from' or 'to' figure from the wrong year")
                break
    vocabulary = Vocabulary(item.evidence.cells())
    for c in r.claims:
        if c.kind == "number":
            continue  # a bare operand of a worked calculation names no metric of its own
        named = _nearest_metric(vocabulary, _own_words(text, c, r.claims))
        metrics = {x.metric for x in r.matched.get(c.id, []) + ([r.cells[v.cell] for v in gold.values if v.cell in r.cells]
                                                                if c.id in r.computed else []) if x.metric}
        if named and metrics and named not in metrics:
            out.append("a metric name that is not its figure's")
            break
    for c in r.claims:
        cells = r.matched.get(c.id, [])
        sentence = sentence_of(text, c.start, c.end)
        since = text[max(text.index(sentence) if sentence in text else 0, max((x.end for x in r.claims if x.end <= c.start), default=0)) : c.start]
        if any(x.raw is not None and x.raw > 0 and not LOSS.search(x.metric or x.row_label) for x in cells) and LOSS.search(since):
            out.append("'loss' beside a figure that is not one")
            break
    for c in r.claims:  # "3,692,785,977 Rs." is an amount as printed only where its cell is printed in units
        if c.kind == "number" and _CURRENCY_AFTER.match(text[c.end :]) and not any(x.scale == 0 for x in r.matched.get(c.id, [])):
            out.append("a currency after a bare figure")
            break
    scales = {t.scale for t in item.evidence.tables}
    for m in SCALE.finditer(text):
        if r.sentence_claims(m.start(), m.end()):
            continue  # a figure's own unit is read with the figure
        word = (m.group("w") or "").lower()
        said = 3 if m.group("k") or word.startswith("thousand") else 6 if word.startswith("million") else 9
        if said not in scales:
            out.append("a unit the tables do not use")
            break
    return out


def unchecked_direction(item: Item, gold: GoldQuestion) -> bool:
    """A direction word that may not say how the two cells moved, or a signed change beside one.

    Only a question about a change between two periods can check one: there every direction word must
    say what the cells did ("rose" when the later figure is larger), by size where the sentence speaks
    of a change between two losses, and a judging word ("improved") cannot be checked there at all.
    """
    text = item.answer.text
    natural = natural_context(text, gold, item.evidence)
    for m in DIRECTION.finditer(text):
        if not natural.change:
            return True
        word = m.group().lower()
        signed, size, losses = natural.change
        if losses and LOSS.search(sentence_of(text, m.start(), m.end())):
            if _JUDGING.match(word):
                return True
            moved = size
        else:
            moved = signed
        said = DIRECTION_WORDS[word][0] if word in DIRECTION_WORDS else "up" if _MORE.match(word) else "down" if _LESS.match(word) else None
        if said is None or said != moved:
            return True
    return False


def entity_difference(item: Item, gold: GoldQuestion) -> bool:
    """A difference or change between two entities' cells: the words, not the number, say which is larger."""
    cells = {c.id: c for c in item.evidence.cells()}
    operands = [cells[v.cell] for v in gold.values if v.role == "operand" and v.cell in cells]
    return is_change_program(gold.program) and len(operands) == 2 and operands[0].entity != operands[1].entity


def _points_allowed(gold: GoldQuestion) -> bool:
    """Percentage points fit only a difference of two percentages."""
    primary = gold.primary
    return bool(primary and primary.kind == "percent" and is_change_program(gold.program) and not (gold.program or "").startswith("growth("))


def reasons(item: Item, gold: GoldQuestion) -> list[str]:
    """Why a person must label this answer; empty when code can."""
    qtype = item.question.question_type
    if qtype in ("narrative", "comparison"):
        return [f"{qtype} question"]
    text = item.answer.text
    if not text.strip():
        return ["empty answer"]
    out = []
    if item.answer.settings.get("thinking_leak"):
        out.append("thinking leak")
    state = score_text(text, gold, item.evidence)
    if state in _STATE_REASON:
        out.append(_STATE_REASON[state])
    if entity_difference(item, gold):
        out.append("a difference between two entities")
    for pattern, reason in ((NEGATION, "a negation, hedge or guess"), (EXPLANATION, "an explanation or judgement"),
                            (NUMBER_WORDS, "a figure in words or a fraction"), (PART_YEAR, "a quarter or part of a year")):
        if pattern.search(text):
            out.append(reason)
    if POINTS.search(text) and not _points_allowed(gold):
        out.append("percentage points")
    report = {t.currency for t in item.evidence.tables} | {c.currency for c in item.evidence.cells()}
    if {code for pattern, code in CURRENCIES if pattern.search(text)} - report:
        out.append("a currency the report does not use")
    if state == "supported_useful":
        if unchecked_direction(item, gold):
            out.append("a direction word the scorer cannot check")
        out += wording_mismatch(item, gold)
    return out


def code_label(item: Item) -> GoldLabel:
    return GoldLabel(item_id=item.id, target="original", status="correct", spans=[], useful=True,
                     annotator=AUTO_ANNOTATOR, note="every number matches the gold cells (D-100)")


def _stratum(item: Item) -> str:
    figures = len(find_numbers(item.answer.text))
    return f"{item.question.country} {item.answer.generator} {'several figures' if figures > 1 else 'one figure'}"


def draw_audit(items: Sequence[Item], size: int = AUDIT_SIZE, seed: int = AUDIT_SEED) -> list[str]:
    """A stratified random sample of code-labelled answers: by country, generator and one figure or several,
    in proportion to each stratum's size (largest remainders), each drawn with its own seeded generator."""
    strata: dict[str, list[str]] = defaultdict(list)
    for item in items:
        strata[_stratum(item)].append(item.id)
    size = min(size, len(items))
    if not size:
        return []
    shares = {k: size * len(v) / len(items) for k, v in strata.items()}
    take = {k: int(s) for k, s in shares.items()}
    for k in sorted(shares, key=lambda k: (take[k] - shares[k], k))[: size - sum(take.values())]:
        take[k] += 1
    return sorted(i for k, ids in sorted(strata.items()) for i in random.Random(f"{seed}:{k}").sample(sorted(ids), take[k]))


def triage(items: Sequence[Item], gold: GoldStore, audit_size: int = AUDIT_SIZE, seed: int = AUDIT_SEED) -> dict:
    """{"code": ids code labels, "person": ids a person labels, "audit": code-labelled ids a person also labels,
    "reasons": answers per reason (an answer can have several), "strata": audit answers per stratum,
    "audit_size" and "seed": how the audit was drawn}."""
    code, person, why = [], [], Counter()
    for item in items:
        found = reasons(item, gold.questions[item.question.id])
        (person if found else code).append(item.id)
        why.update(found)
    by_id = {item.id: item for item in items}
    audit_ids = draw_audit([by_id[i] for i in code], audit_size, seed)
    return {"code": code, "person": person, "audit": audit_ids, "reasons": dict(why.most_common()),
            "strata": dict(sorted(Counter(_stratum(by_id[i]) for i in audit_ids).items())), "audit_size": audit_size, "seed": seed}


def unchecked_questions(question_ids: set[str], benchmark_root: str | Path) -> list[str]:
    """Questions with no second reader: `checked_by` empty or the same as the author, or not found at all (R-23)."""
    from faithguard.benchmark import load_report, report_paths

    checked = set()
    for path in report_paths(benchmark_root):
        spec, _ = load_report(path)
        checked |= {q.id for q in spec.questions if q.checked_by and q.checked_by != q.author}
    return sorted(question_ids - checked)


def wrong(label: GoldLabel) -> bool:
    """Does a person's label overrule a code label (correct, useful, no spans)?"""
    return label.status != "correct" or bool(label.spans) or label.useful is False


def person_labels(gold: GoldStore, item_id: str) -> list[GoldLabel]:
    """The labels people wrote for an original answer: the adjudicated one alone if there is one, else all of them."""
    from faithguard.evaluate.pilot import AI_ANNOTATORS

    labels = [x for x in gold.labels.get(item_id, []) if x.target == "original" and x.annotator not in AI_ANNOTATORS]
    adjudicated = [x for x in labels if x.adjudicated]
    return adjudicated[:1] or labels


def audit(result: dict, gold: GoldStore, items: Sequence[Item]) -> dict:
    """The audit's verdict from people's labels: an audited answer counts as overruled if any person's label
    overrules it, unless an adjudicated label says otherwise. Until every audited answer has a person's label the
    audit is incomplete and decides nothing. If the code labels fall, every code-labelled answer goes to a person;
    if they stand, so do those whose question had an audited answer overruled (the gold may be wrong) or a
    person's ambiguous label (the question may be). Answers a person has labelled already are not sent again."""
    question = {item.id: item.question.id for item in items}
    labels = {i: person_labels(gold, i) for i in question}
    audited = [i for i in result["audit"] if labels[i]]
    overruled = sorted(i for i in audited if any(wrong(x) for x in labels[i]))
    planned, size = len(result["audit"]), result.get("audit_size", AUDIT_SIZE)
    by_stratum = Counter(_stratum(next(it for it in items if it.id == i)) for i in overruled)
    by_type = Counter(next(it for it in items if it.id == i).question.question_type for i in overruled)
    verdict = {"planned": planned, "labelled": len(audited), "overruled": overruled,
               "overruled_by_stratum": dict(by_stratum), "overruled_by_question_type": dict(by_type),
               "upper_95": clopper_pearson_upper(len(overruled), len(audited)) if audited else None}
    if len(audited) < planned:
        return verdict | {"status": "incomplete", "code_labels_stand": None, "to_person": [], "code_labels_kept": []}
    stands = planned >= min(size, len(result["code"])) and len(overruled) <= AUDIT_MAX_WRONG
    flagged = {question[i] for i in overruled}
    flagged |= {question[i] for i, xs in labels.items() if any(x.status == "ambiguous" for x in xs)}
    unlabelled = [i for i in result["code"] if not labels[i]]
    to_person = sorted(i for i in unlabelled if not stands or question[i] in flagged)
    return verdict | {"status": "complete", "code_labels_stand": stands, "to_person": to_person,
                      "code_labels_kept": sorted(i for i in unlabelled if i not in to_person) if stands else []}


def _other_label(gold: GoldStore, item_id: str) -> GoldLabel | None:
    """The deciding label among those code did not write (evaluate.pilot.label_of without code labels)."""
    from faithguard.evaluate.pilot import AI_ANNOTATORS

    labels = [x for x in gold.labels.get(item_id, []) if x.target == "original" and x.annotator != AUTO_ANNOTATOR]
    people = [x for x in labels if x.annotator not in AI_ANNOTATORS]
    return next((x for x in labels if x.adjudicated), (people or labels or [None])[0])


def report(result: dict, items: Sequence[Item], gold: GoldStore) -> str:
    """Counts only. Where the gold store already holds other labels (the pilot's), it compares them with the routing."""
    lines = [
        "# Labelling triage: code labels and a person's labels (D-100)", "",
        "Counts only. Code labels an answer correct when every number matches the gold cells and nothing else in it "
        "could still be wrong; a person labels the rest, plus a hidden, stratified audit sample of the code labels. "
        "See `faithguard.evaluate.triage`.", "",
        "| Answers | Code labels | A person labels | Audit sample (also a person) |", "| --- | --- | --- | --- |",
        f"| {len(items)} | {len(result['code'])} | {len(result['person'])} | {len(result['audit'])} |", "",
        "| Why a person labels it (an answer can have several reasons) | Answers |", "| --- | --- |",
        *[f"| {reason} | {n} |" for reason, n in result["reasons"].items()],
    ]
    others = {item.id: label for item in items if (label := _other_label(gold, item.id))}
    if others:
        statuses = {name: Counter(others[i].status for i in result[name] if i in others) for name in ("code", "person")}
        disagree = [i for i in result["code"] if i in others and wrong(others[i])]
        annotators = Counter(label.annotator for label in others.values())
        lines += [
            "", f"### Against the other labels in the gold store ({', '.join(f'{a}: {n}' for a, n in annotators.items())})", "",
            "| Routed to | Labels: correct | incorrect | unhelpful | ambiguous |", "| --- | --- | --- | --- | --- |",
            *[f"| {name} | " + " | ".join(str(statuses[name][s]) for s in ("correct", "incorrect", "unhelpful", "ambiguous")) + " |"
              for name in ("code", "person")],
            "", f"Code labels those labels overrule: {len(disagree)} of {sum(i in others for i in result['code'])}.",
        ]
    return "\n".join(lines) + "\n"
