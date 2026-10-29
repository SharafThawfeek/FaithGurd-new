"""Ask your own question: any question on one of the demo's reports, then errors planted in its answer.

The answer comes from the AI live on this laptop (demo.models), from a template written from the cells
the question names, or from the presenter's keyboard. Nothing here reads gold: a typed question has
none. The checker reads the metric, entity and period from the question's own words
(faithguard.claims.question_context); the question's type, one of the policy's features, is read from
its wording here, as the benchmark's writers set it by hand.

Planted errors are written by the executor: a COPY or CALCULATE that points at the wrong cells (another
entity, year or line) puts the wrong figure in the answer's own printed style, the way real slips look.
The rule checker, policy and repairers are the frozen research system; nothing here changes them.
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from faithguard.calc import ops
from faithguard.calc.numbers import default_style, render
from faithguard.claims import DIRECTION_WORDS, Vocabulary, mention_of, question_context, years_in
from faithguard.executor import ExecError, apply, execute
from faithguard.inject import _label, _style
from faithguard.records import Answer, Calculate, Cell, Copy, DetectorOutput, EditProgram, Evidence, Item, Question
from faithguard.tables import ENTITY_WORDS, normalise_metric, normalise_period

ROOT = Path(__file__).resolve().parent.parent
ISSUERS = ROOT / "manifests" / "issuers.csv"
MAX_QUESTION = 300

# first match wins; anything else is a lookup. Matched on the question with the line item it names masked,
# so "change in fair value" or "share of profit of associates" does not make a lookup a change or a share.
QUESTION_TYPES = [
    ("share", re.compile(r"\b(share of|proportion of|percentage of|per ?cent of|as a (%|percentage) of|what (%|percentage) of)", re.I)),
    ("growth", re.compile(r"\b(grow|grew|growth|by what (percentage|per ?cent)|percentage (change|increase|decrease|rise|fall)"
                          r"|how did .+ change|rate of (change|increase|decrease))", re.I)),
    ("difference", re.compile(r"\b(difference|by how much|how much (more|less|higher|lower)|change[ds]?|increase[ds]?|decrease[ds]?"
                              r"|rise|rose|fall|fell|declin\w*)\b", re.I)),
    ("ratio", re.compile(r"\bratio\b", re.I)),
    ("sum", re.compile(r"\b(sum of|total of|combined|together|plus|added to)\b", re.I)),
    ("average", re.compile(r"\b(average|mean)\b", re.I)),
    ("comparison", re.compile(r"\b(compare|compared|higher than|lower than|larger than|smaller than|more than|less than)\b", re.I)),
]
ENTITY_WORD = {"group": "Group", "bank": "Bank", "company": "Company"}
ENTITY_PREFERENCE = ("group", "company", "bank")
# a figure's scale word, and the one that reads it a thousand times too large (or small)
SCALE_SWAP = {"thousand": "million", "thousands": "millions", "million": "billion", "millions": "billions",
              "billion": "million", "billions": "millions", "mn": "bn", "bn": "mn"}
_SCALE_WORD = re.compile(r"\b(thousands?|millions?|billions?|mn|bn)\b", re.I)
# opposite direction words in the same part of speech (the checker's own table maps every "down" word to "rose")
OPPOSITE = {"drop": "rise", "drops": "rises", "dropped": "rose", "shrank": "grew", "contracted": "expanded", "lost": "gained",
            "retreated": "advanced", "deteriorated": "improved", "declined": "grew", "decline": "growth"}
_PREVIOUS = re.compile(r"\b(previous|prior|preceding|last)\s+(financial\s+|fiscal\s+)?year\b", re.I)
_ENTITY_IN_NAME = re.compile(r"\s+(Bank|Company|Group)\b(\s*\(Lanka\))?(\s+PLC)?", re.I)
STOPWORDS = set("the of in a an and for to what was were is are how much did does by from with on at year years its it "
                "group bank company s 's 'the".split())


class Unanswerable(ValueError):
    """A question the template cannot answer from the table, with a message for the screen."""


def question_type(text: str, vocab: Vocabulary | None = None) -> str:
    if vocab is not None:
        norm = f" {normalise_metric(text.replace('%', ' percent '))} "
        for s in vocab.surfaces:  # longest first
            norm = norm.replace(f" {s.text} ", " _ ")
        text = norm
    return next((name for name, pattern in QUESTION_TYPES if pattern.search(text)), "lookup")


_POSSESSIVE = re.compile(r"\b([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*)['’]s\b")


def other_company(report: "Report", text: str) -> str | None:
    """Why a question about another company cannot be checked against this report, or None."""
    own = {w.lower() for w in re.findall(r"[A-Za-z]+", report.name)}
    for name in _POSSESSIVE.findall(text or ""):
        words = [w.lower() for w in re.findall(r"[A-Za-z]+", name)]
        if not words or set(words) & ({"group", "bank", "company", "the", "fy"} | own):
            continue
        return (f"This is {report.name}'s report, and the question asks about {name}. FaithGuard checks answers against the "
                "chosen report only: pick that company's report, or ask about this one.")
    return None


def bad_question(text) -> str | None:
    """Why a typed question cannot be used, or None."""
    if not isinstance(text, str) or not text.strip():
        return "Type a question about the report first."
    if len(text) > MAX_QUESTION:
        return f"That question is too long for the demo ({MAX_QUESTION} characters at most)."
    if any(ord(ch) > 0xFFFF for ch in text):
        return "Emoji and other symbols outside the basic character set are not supported in the demo."
    return None


# ---------------------------------------------------------------------------
# Reports and one-click questions
# ---------------------------------------------------------------------------


@dataclass
class Report:
    id: str  # the issuer, e.g. "LK:SAMP"
    name: str
    country: str | None
    evidence: Evidence
    real: bool

    def vocab(self) -> Vocabulary:
        return Vocabulary(self.evidence.cells())


def issuer_names(path: Path = ISSUERS) -> dict[str, str]:
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as f:
        return {f"{r['country']}:{r['issuer']}": r["name"] for r in csv.DictReader(f)}


def reports_of(examples) -> dict[str, Report]:
    """One report per issuer among the examples, with the evidence its first example shows."""
    names = issuer_names()
    out: dict[str, Report] = {}
    for e in examples:
        q = e.item.question
        if q.issuer in out:
            continue
        real = e.group == "pilot"
        name = names.get(q.issuer, q.issuer) if real else "Fictional bank (made-up figures)"
        out[q.issuer] = Report(q.issuer, name, q.country, e.item.evidence, real)
    return out


def clean_label(cell: Cell, vocab: Vocabulary | None = None) -> str:
    """The row label without the leftovers of the printed table: 'Net finance income /' -> 'Net finance income',
    'Less: Interest expense' -> 'Interest expense'. With the vocabulary, a cleaning is kept only if the checker still
    reads the cell's metric in it (it does not in 'interest expense'), else the label stays as printed."""
    label = re.sub(r"^less\s*:\s*", "", _label(cell), flags=re.I)
    label = re.sub(r"\s*[-–]\s*(Rs\.?|US\$|\$)\s*$", "", label)
    label = re.sub(r"[\s/:;,\-]+$", "", label) or _label(cell)
    if vocab is not None and vocab.metric_in(label) != cell.metric:
        return re.sub(r"[\s/:;,\-]+$", "", _label(cell)) if vocab.metric_in(re.sub(r"[\s/:;,\-]+$", "", _label(cell))) == cell.metric else _label(cell)
    return label


def _in_sentence(label: str) -> str:
    """'Total Assets' -> 'total assets', keeping acronyms: 'Net income from FVTPL'."""
    return " ".join(w if len(w) > 1 and w.isupper() else w.lower() for w in label.split())


def _verb(label: str) -> str:
    """'was' or 'were' for the head of the label: 'revenue from contracts with customers was', 'total assets were',
    'amounts due to related parties were'."""
    head = re.split(r"\s+(?:due|from|of|on|in|with|for|to|at|attributable|net of)\s+", label.strip(), maxsplit=1, flags=re.I)[0]
    last = head.split()[-1].lower() if head.split() else ""
    return "were" if last.endswith("s") and not last.endswith(("ss", "us", "is")) else "was"


def named_metrics(vocab: Vocabulary, text: str) -> set[str]:
    """The metrics the question names, by surfaces that are not part of a longer one it names ("sales" in "cost of sales")."""
    norm = f" {normalise_metric(text)} "
    found = [s for s in vocab.surfaces if f" {s.text} " in norm]
    return {s.metric for s in found if not any(o.text != s.text and f" {s.text} " in f" {o.text} " for o in found)}


def _subject(cell: Cell, name: str, vocab: Vocabulary | None = None) -> str:
    label = _in_sentence(clean_label(cell, vocab))
    if cell.entity in ENTITY_WORD:
        return f"the {ENTITY_WORD[cell.entity]}'s {label}"
    return f"{name.split()[0]}'s {label}"


def read_question(report: Report, text: str) -> tuple[str, str | None, str]:
    """(the question as the checker gets it, its period, a note for the screen when it was rewritten).

    The benchmark's writers set a question's period by hand; here it is read from short forms the checker's year
    reader skips ("FY25", "the previous year"). A company name with "Bank" or "Company" in it would read as that
    column ("Sampath Bank's profit" as the Bank's, not the Group's), so it is shortened to the name before it."""
    text = typography(" ".join(text.split()))
    note = ""
    if report.real:
        short = _ENTITY_IN_NAME.split(report.name, maxsplit=1)[0]
        if short != report.name:
            rewritten = re.sub(re.escape(short) + _ENTITY_IN_NAME.pattern, short, text, flags=re.I)
            if rewritten != text:
                note = f"Read as “{rewritten}”: the “{_ENTITY_IN_NAME.search(report.name).group(1)}” in the company's name is not that column."
                text = rewritten
    vocab = report.vocab()
    own_name = {w.lower() for w in re.findall(r"[A-Za-z]+", report.name)} | {"percentage", "percent", "grow", "grew", "growth",
                                                                         "change", "changed", "increase", "decrease", "rise", "fall"}
    if vocab.metric_in(text) is None and (metric := _metric_from_words(vocab, text, own_name, strict=True)):
        # a short name the checker does not know ("revenue" for "revenue from contracts with customers"): without the
        # line's own name, any figure of that year would pass, so the question is read with the report's name for it
        line = next((clean_label(c, vocab) for c in report.evidence.cells() if c.metric == metric and c.row_label.strip()), None)
        shared = {_stem(w) for w in metric.split()}
        words = list(re.finditer(r"[A-Za-z][A-Za-z'’&-]*", text))
        spans = [w for w in words if _stem(normalise_metric(w.group())) in shared and w.group().lower() not in own_name]
        if line and spans and vocab.metric_in(line) == metric:
            start, end = spans[0].start(), spans[-1].end()
            rewritten = text[:start] + _in_sentence(line) + text[end:]
            if vocab.metric_in(rewritten) == metric:
                note = (note + " " if note else "") + f"Read as “{rewritten}”: the report calls this line “{line}”."
                text = rewritten
    years = [y for y in years_in(text) if y in vocab.periods]
    period = None
    if not years:
        short_year = normalise_period(text)
        previous = [p for p in vocab.periods if p < (vocab.latest_period() or "")]
        if short_year in vocab.periods:
            period = short_year
        elif _PREVIOUS.search(text) and previous:
            period = previous[-1]
    return text, period, note


def _cap(s: str) -> str:
    return s[:1].upper() + s[1:]


def _negative_rows(report: Report) -> set[tuple[str, int]]:
    """Rows with an amount printed in brackets (expenses, costs, tax): the tables store them as negative numbers, so
    the rule checker reads an expense given as a positive amount as a sign error. One-click questions leave them out."""
    return {(c.table_id, c.row) for c in report.evidence.cells() if c.kind == "amount" and c.value is not None and c.value < 0}


def _row_cells(report: Report) -> list[Cell]:
    """For each row with positive amounts in the latest period, the cell of the preferred entity there."""
    vocab = report.vocab()
    latest = vocab.latest_period()
    negative = _negative_rows(report)
    order = {e: i for i, e in enumerate(ENTITY_PREFERENCE)}
    rows: dict[tuple[str, int], Cell] = {}
    values_of: dict[tuple, set] = {}  # (metric, entity, period) -> the figures printed under that name
    for c in report.evidence.cells():
        if c.metric and c.value is not None:
            values_of.setdefault((c.metric, c.entity, c.period), set()).add(c.value)
    for c in report.evidence.cells():
        if (c.value is None or c.kind != "amount" or c.period != latest or not c.metric or (c.table_id, c.row) in negative
                or not c.row_label.strip() or re.search(r"\d|\$", _label(c)) or re.search(r"\b(to|of|for|from|by)$", clean_label(c), re.I)
                or vocab.metric_in(clean_label(c)) != c.metric or c.row_label.strip()[:1] in "-–"
                or re.search(r"owners of|non-?controlling|equity holders|attributable", c.row_label, re.I)
                or len(values_of.get((c.metric, c.entity, c.period), ())) > 1):
            continue  # also subtotal headers ("Profit attributable to"), continuation rows ("- Voting"), attribution
            # breakdowns, rows sharing a name, and labels the checker would not read back
        key = (c.table_id, c.row)
        if key not in rows or order.get(c.entity, len(order)) < order.get(rows[key].entity, len(order)):
            rows[key] = c
    seen, out = set(), []
    for c in rows.values():
        if c.metric not in seen:
            seen.add(c.metric)
            out.append(c)
    return out


PREFERRED_METRICS = ("profit after tax", "profit for the year", "net interest income", "revenue", "net earned premiums",
                     "total assets", "due to depositors", "deposits", "net income", "gross written premiums", "total equity")


def candidate_questions(report: Report) -> tuple[list[str], list[tuple[str, str]]]:
    """(suggestions, [(line item, question)]) before checking that the template answers them and the pipeline sends it."""
    cells = _row_cells(report)
    vocab = report.vocab()
    latest = vocab.latest_period()
    previous = [p for p in vocab.periods if p < (latest or "")]
    rank = {m: i for i, m in enumerate(PREFERRED_METRICS)}
    main = sorted([c for c in cells if c.entity == cells[0].entity] if cells else [],
                  key=lambda c: min((i for m, i in rank.items() if m in c.metric), default=len(rank)))
    out = []
    for a in main[:3]:
        out.append(f"What {_verb(clean_label(a, vocab))} {_subject(a, report.name, vocab)} in {latest}?")
        if previous:
            out.append(f"By what percentage did {_subject(a, report.name, vocab)} grow in {latest}?")
    other = next((e for e in ENTITY_PREFERENCE if e in vocab.entities and main and e != main[0].entity), None)
    if other and previous:
        for a in main[:3]:
            b = next((c for c in report.evidence.cells() if c.metric == a.metric and c.entity == other and c.period == latest), None)
            if b is not None:
                out.append(f"How did {_subject(b, report.name, vocab)} change in {latest} compared with {previous[-1]}?")
    items = [(clean_label(c, vocab), _cap(f"What {_verb(clean_label(c, vocab))} {_subject(c, report.name, vocab)} in {latest}?"))
             for c in cells]
    return [_cap(s) for s in dict.fromkeys(out)], items


# ---------------------------------------------------------------------------
# The item, and a template answer
# ---------------------------------------------------------------------------


_PLURAL_POSSESSIVE = re.compile(r"(?<=[sS])'(?=\s|$)")


def typography(text: str) -> str:
    """A plural possessive with a straight apostrophe written as the reports print it: the frozen checker drops "’" but
    keeps "'", so "stockholders' equity" would not match the line "Stockholders’ equity" and read as a shorter one."""
    return _PLURAL_POSSESSIVE.sub("’", text)


def make_item(report: Report, item_id: str, question: str, answer: str, generator: str) -> Item:
    text, period, _ = read_question(report, question)
    q = Question(id=item_id, issuer=report.id, country=report.country, text=text, period=period,
                 question_type=question_type(text, report.vocab()), source="demo")
    return Item(id=item_id, question=q, evidence=report.evidence,
                answer=Answer(id=item_id, question_id=item_id, generator=generator, text=typography(answer)))


def _find(report: Report, metric: str | None, entity: str | None, period: str | None, question: str = "") -> Cell | None:
    """The cell for a metric, entity and period. When rows share the metric's name with different figures (current and
    non-current, an impairment line and a balance-sheet line), the row whose label or statement the question names."""
    cells = [c for c in report.evidence.cells() if c.value is not None and c.metric == metric and c.period == period
             and (entity is None or c.entity == entity)]
    if not cells:
        return None
    order = {e: i for i, e in enumerate(ENTITY_PREFERENCE)}
    first = min(order.get(c.entity, len(order)) for c in cells)
    cells = [c for c in cells if order.get(c.entity, len(order)) == first]
    if len({c.value for c in cells}) == 1:
        return cells[0]
    titles = {t.id: t.title for t in report.evidence.tables}
    words = set(normalise_metric(question).split()) - STOPWORDS
    score = {c.id: len(words & set(normalise_metric(f"{c.row_label} {titles.get(c.table_id, '')}").split())) for c in cells}
    best = max(score.values())
    top = [c for c in cells if score[c.id] == best]
    if len({c.value for c in top}) == 1:
        return top[0]
    raise Unanswerable(f"The tables have {len(cells)} rows called “{clean_label(cells[0])}” with different figures; "
                       "say which one you mean (for example current or non-current, or the statement it is in).")


def _stem(word: str) -> str:
    word = word.strip("'’")
    return word[:-2] if word.endswith("'s") else word[:-1] if word.endswith("s") and not word.endswith("ss") else word


def _metric_from_words(vocab: Vocabulary, question: str, extra_stop: set[str] = frozenset(), strict: bool = False) -> str | None:
    """A short name the checker's vocabulary does not know ("revenue" for "revenue from contracts with customers",
    "revenue" for "total revenues"): the one metric holding the most content words the question shares with the
    metrics, if there is just one. Strict: only if every content word of the question is in that metric's name (so
    "What dividend did Sunshine pay?" is not read as dividend income)."""
    words = {_stem(w) for w in normalise_metric(question).split()} - {_stem(w) for w in STOPWORDS | set(extra_stop)}
    words = {w for w in words if w and not w.isdigit()}
    shared = {m: words & {_stem(w) for w in m.split()} for m in {s.metric for s in vocab.surfaces}}
    best = max((len(w) for w in shared.values()), default=0)
    found = [m for m, w in shared.items() if w and len(w) == best]
    if not best or len(found) != 1 or (strict and shared[found[0]] != words):
        return None
    return found[0]


def _percent_style(value: Decimal):
    return default_style("percent", decimals=2 if abs(value) < 1 else 1)


def draft(report: Report, question: str) -> str:
    """A correct answer written from the cells the question names: a lookup, a growth rate or a change."""
    vocab = report.vocab()
    text, period, _ = read_question(report, question)
    ctx = question_context(Question(id="q", issuer=report.id, text=text, period=period), vocab)
    kind = question_type(text, vocab)
    missing_years = sorted(y for y in set(years_in(text)) if y not in vocab.periods)
    if missing_years:
        raise Unanswerable(f"The report covers {' and '.join(vocab.periods)} only; it has no figures for {', '.join(missing_years)}.")
    years = sorted(y for y in set(years_in(text)) if y in vocab.periods)
    if kind == "comparison" and len(years) > 1:
        kind = "growth"
    if kind not in ("lookup", "growth", "difference", "comparison"):
        raise Unanswerable("The template writes lookups, growth rates and changes only. Ask the AI or type an answer.")
    entities = {ENTITY_WORDS[w] for w in re.findall(r"[a-z]+", text.lower()) if w in ENTITY_WORDS} & set(vocab.entities)
    if len(entities) > 1:
        raise Unanswerable("The question compares two entities; the template writes one entity's figures only. "
                           "Ask the AI or type an answer.")
    named = named_metrics(vocab, text)
    if len(named) > 1:
        raise Unanswerable(f"The question names more than one line item ({', '.join(sorted(named))}), so the template "
                           "does not guess which one. Name one line item, ask the AI, or type an answer.")
    metric = ctx.metric or _metric_from_words(vocab, text)
    if metric is None:
        raise Unanswerable("The tables have no line item that this question names, so there is no cell to write an answer from. "
                           "Try a line item listed under the question, ask the AI, or type an answer.")
    a = _find(report, metric, ctx.entity, years[-1] if years else ctx.period, text)
    if a is None:
        raise Unanswerable(f"No figure for {metric}{f' ({ctx.entity})' if ctx.entity else ''} in {years[-1] if years else ctx.period}: "
                           "the template has nothing to copy. Ask the AI or type an answer.")
    if a.value < 0:
        raise Unanswerable(f"{clean_label(a)} is printed in brackets, so the tables store it as a negative number, and the frozen "
                           "checker reads a positive figure for it as a sign error: the template does not write it. Ask the AI or type an answer.")
    subject = _cap(_subject(a, report.name, vocab))
    A = render(a.value, _style(a))
    if kind in ("growth", "difference"):
        base = years[0] if len(years) > 1 else max((p for p in vocab.periods if p < (a.period or "")), default=None)
        b = next((c for c in report.evidence.cells() if c.table_id == a.table_id and c.row == a.row and c.entity == a.entity
                  and c.period == base and c.value is not None), None) if base and base != a.period else None
        if b is None or not b.value:
            raise Unanswerable(f"The tables have no earlier year to measure the change in {metric} from. "
                               "Ask the AI or type an answer.")
        if a.value < 0 or b.value < 0:
            raise Unanswerable(f"{clean_label(a)} is printed in brackets, so the tables store it as a negative number, and the "
                               "frozen checker reads a change in it by that sign: the template does not write one. Ask the AI or type an answer.")
        B = render(b.value, _style(b))
        if a.value == b.value:
            return f"{subject} {_verb(clean_label(a, vocab))} unchanged at {A} in {a.period}."
        if kind == "growth":
            g = ops.growth(a.value, b.value)
            return f"{subject} {'rose' if g >= 0 else 'fell'} {render(abs(g), _percent_style(g))} from {B} in {b.period} to {A} in {a.period}."
        d = ops.diff(a.value, b.value)
        return (f"{subject} {'increased' if d >= 0 else 'decreased'} by {render(abs(d), _style(a))} "
                f"from {B} in {b.period} to {A} in {a.period}.")
    return f"{subject} {_verb(clean_label(a, vocab))} {A} in {a.period}."


def caveats(item: Item, det: DetectorOutput, action: str) -> list[str]:
    """Known limitations of the frozen system that this question or answer runs into, said on screen."""
    vocab = Vocabulary(item.evidence.cells())
    metric = question_context(item.question, vocab).metric
    traced = {cid for check in det.checks for cid in check.cells}
    bracketed = [c for c in item.evidence.cells() if c.kind == "amount" and c.value is not None and c.value < 0
                 and ((metric is not None and c.metric == metric) or c.id in traced)]
    out = []
    if bracketed:
        out.append(f"{_label(bracketed[0])} is printed in brackets, so the tables store it as a negative number. The rule checker "
                   "reads a positive figure for it as a sign error, and the direction of a change in it by the stored sign.")
    if any(c.value == 0 and "000" in c.text for c in det.claims):
        out.append("“000” in the answer is a units note, but the rule checker reads it as a number.")
    m = re.search(r"\b\w+(?:\s+\w+)?\s+(Bank|Company)\b", item.answer.text)
    name_word = _ENTITY_IN_NAME.search(issuer_names().get(item.question.issuer, ""))
    if m and name_word and name_word.group(1).lower() == m.group(1).lower() and m.group(0).split()[0].lower() in issuer_names().get(item.question.issuer, "").lower():
        out.append(f"The answer says “{m.group(0)}”: the rule checker reads the “{m.group(1)}” in the company's name as the "
                   f"{m.group(1)} column, not the Group's.")
    if action == "abstain" and det.checks and all(c.verdict == "supported" for c in det.checks):
        out.append("Every number is supported, yet the policy withholds the answer: it was certified on the controlled track's small "
                   "tables, and on large real reports (and on “by how much” questions) its P(unsafe) runs high, so it errs on the safe side.")
    by_id = {c.id: c for c in item.evidence.cells()}
    if metric is None and any(c.verdict == "supported" and c.intended.metric is None for c in det.checks):
        out.append(f"{UNKNOWN_LINE} FaithGuard could not tell which line of the report the question is about, so it only checked "
                   "that each figure appears somewhere in the tables (a known limitation). Name the line as the report prints it.")
    if re.search(r"\battributable\b", item.question.text, re.I):
        out.append("“Attributable to” is a breakdown the checker can confuse with the total row (profit for the year, including "
                   "non-controlling interests): check the owners' share against the report yourself (a known limitation).")
    words = EXPLAIN.search(item.answer.text)
    if words:
        out.append(f"FaithGuard checks the numbers, not the words around them: “{words.group(0)}” was not checked.")
    asked = vocab.entity_in(item.question.text)
    given = {c.intended.entity for c in det.checks if c.verdict == "supported" and c.intended.entity}
    if asked and given and asked not in given:
        other = sorted(given)[0]
        out.append(f"The question asks about the {ENTITY_WORD.get(asked, asked)}, but the answer gives the "
                   f"{ENTITY_WORD.get(other, other)}'s figure. FaithGuard checks each number against what the answer says it is, "
                   "not whether it answers the question asked.")
    elif asked is None and len(vocab.entities) > 1 and given:
        out.append("The question names no part of the company, so FaithGuard accepts either the Group's or the "
                   f"{'Bank' if 'bank' in vocab.entities else 'Company'}'s figure. Say which one you mean.")
    if any("restated" in (by_id[cid].column_label or "").lower() for check in det.checks for cid in check.cells if cid in by_id):
        out.append("A figure comes from a restated comparative column (Restated*); the figure as originally reported is not in the tables.")
    counts = [c for c in det.claims if c.kind == "number" and c.currency is None and COUNT_AFTER.match(item.answer.text[c.end:c.end + 25])]
    if counts:
        out.append(f"“{counts[0].text}” is a count, not a report figure, but FaithGuard reads every number as a figure of the line asked "
                   "about (a known limitation): ignore what it does with it.")
    return out


UNKNOWN_LINE = "Unknown line item:"
UNTRUSTED = "Careful, this fix is not trustworthy:"
ROUNDED = "Rounded:"
EXPLAIN = re.compile(r"\b(driven by|due to(?! (?:depositors|banks|other banks|customers|related|subsidiar|the group|the parent|holding))|"
                     r"because of|because|as a result of|owing to|thanks to|reflecting|on the back of|"
                     r"supported by|led by|record (?:year|profit|high|growth)|strong demand|higher demand|lower costs)\b[^.]*", re.I)
COUNT_AFTER = re.compile(r"\s*(people|employees|staff|years?|factories|branches|stores|outlets|customers|countries|shareholders|"
                         r"plants|offices|members|directors|times)\b", re.I)
_BARE = re.compile(r"^\d{1,3}(st|nd|rd|th)?$")


SYNONYMS = {"shareholder": "stockholder", "equityholder": "stockholder"}


def _words(text: str) -> set[str]:
    words = {_stem(w) for w in normalise_metric(text).split()} - {_stem(w) for w in STOPWORDS}
    return {SYNONYMS.get(w, w) for w in words if w}


def _named_line(item: Item, old, copied: list[str]) -> str | None:
    """The row label of a cell holding exactly the figure a repair replaced, in the copied cell's column, when the
    sentence names that whole line and the copied line's name is part of it: the figure was right, and the checker read
    a shorter line ("total liabilities" in "total liabilities and shareholders' equity")."""
    ids = {c.id for c in item.evidence.cells()}
    if old is None or old.kind != "amount" or len(copied) != 1 or copied[0] not in ids:
        return None
    read = item.evidence.cell(copied[0])
    text = item.answer.text
    start = max(text.rfind(". ", 0, old.start) + 1, 0)
    end = text.find(". ", old.end)
    sentence = _words(text[start:end if end >= 0 else len(text)])
    for cell in item.evidence.cells():
        if (cell.id == read.id or cell.kind != "amount" or cell.value is None or cell.value != old.value
                or (cell.period, cell.entity) != (read.period, read.entity)):
            continue
        label = _words(cell.row_label)
        if len(label) >= 2 and _words(read.row_label) < label <= sentence:
            return cell.row_label.strip()
    return None


def released_problems(item: Item, final) -> list[str]:
    """For a repaired answer: a count or note number overwritten with a figure, one figure written for two things, or a
    repaired figure beside a year that is not its cell's year. The frozen gate passes all three; the demo says so."""
    if final.action != "repair" or not final.text or not final.repair or not final.repair.program:
        return []
    from faithguard.claims import extract_claims

    det = final.detector
    try:
        res = execute(item, det.claims, final.repair.program)
    except (ExecError, KeyError, ValueError, ops.CalcError):
        return []
    out = []
    claims = {c.id: c for c in det.claims}
    for ch in res.changes:
        old = claims.get(ch.claim_id)
        if old and old.currency is None and old.scale == 0 and old.kind in ("amount", "number") and (
                _BARE.match(old.text.strip()) or COUNT_AFTER.match(item.answer.text[old.end:old.end + 25])):
            out.append(f"{UNTRUSTED} “{old.text}” looks like a count or a reference, not a report figure, and FaithGuard wrote "
                       f"{ch.new} over it (it reads every number as a figure: a known limitation).")
            break
    for ch in res.changes:
        cell = item.evidence.cell(ch.cells[0]) if len(ch.cells) == 1 and ch.cells[0] in {c.id for c in item.evidence.cells()} else None
        written = extract_claims(ch.new)
        if (cell is not None and cell.kind == "amount" and cell.value and written
                and abs(written[0].value - cell.value) > abs(cell.value) * Decimal("0.001")):
            out.append(f"{ROUNDED} the fix keeps the answer's unit, so the report's figure {cell.text} is written as {ch.new}.")
            break
    for ch in res.changes:
        if (named := _named_line(item, claims.get(ch.claim_id), ch.cells)):
            out.append(f"{UNTRUSTED} “{claims[ch.claim_id].text}” is the report's figure for “{named}”, the line the answer "
                       f"names, but FaithGuard read a shorter line name and changed it to {ch.new} (a known limitation).")
            break
    changed, shift = [], 0
    for start, end, new_text in sorted(res.replacements):
        changed.append((start + shift, start + shift + len(new_text)))
        shift += len(new_text) - (end - start)

    def unit(c):
        return Decimal(1).scaleb(-c.decimals) * (Decimal(10) ** c.scale if c.kind == "amount" else 1)

    released = extract_claims(final.text)
    for i, a in enumerate(released):
        twin = next((b for b in released[i + 1:] if (a.kind == b.kind or {a.kind, b.kind} <= {"amount", "number"}) and a.value
                     and any(s <= c.start < e for c in (a, b) for s, e in changed)
                     and abs(abs(a.value) - abs(b.value)) <= max(unit(a), unit(b)) / 2), None)
        if twin is not None:
            out.append(f"{UNTRUSTED} the fixed answer gives the same figure ({a.text} and {twin.text}) for two different things.")
            break
    cell_ids = {c.id for c in item.evidence.cells()}
    shift = 0
    for start, end, new in sorted(res.replacements):
        ch = next((c for c in res.changes if c.start == start and c.end == end), None)
        s = start + shift
        shift += len(new) - (end - start)
        if ch is None or not ch.cells:
            continue
        periods = {item.evidence.cell(x).period for x in ch.cells if x in cell_ids}
        tail = re.split(r"[,;]|\.\s*$|\.\s+[A-Z]|\bto\b|\band\b", final.text[s + len(new): s + len(new) + 40])[0]
        years = years_in(tail)
        if len(periods) == 1 and years and years[0] not in periods:
            out.append(f"{UNTRUSTED} {new} is the {next(iter(periods))} figure, but the sentence says {years[0]}.")
            break
    return out


CONTRADICTION = "The sentence contradicts itself:"


def contradictions(text: str | None, det: DetectorOutput) -> list[str]:
    """Sentences whose growth rate does not fit their own two figures of the same line item ("decreased 12.4% from
    Rs. 1.14 to Rs. 1.78"). The gate checks each number against the report, not whether the numbers of one sentence
    agree, so a repair can put one entity's rate beside another entity's figures (a known limitation); the demo says so."""
    from faithguard.claims import sentence_bounds

    if not text:
        return []
    out = []
    by_sentence: dict[tuple[int, int], list] = {}
    for claim in det.claims:
        by_sentence.setdefault(sentence_bounds(text, claim.start), []).append(claim)
    for claims in by_sentence.values():
        rates = [c for c in claims if c.kind == "percent"]
        amounts = [c for c in claims if c.kind == "amount"]
        if len(rates) != 1 or len(amounts) != 2:
            continue
        rate, (a, b) = rates[0], amounts
        if not a.value or not b.value:
            continue
        if a.value == b.value and rate.value and re.search(r"\bfrom\b", text[min(a.start, b.start) - 12:max(a.end, b.end)], re.I):
            # "grew by 21.4% ... from $503.6 million to $503.6 million": a rate from a figure to itself
            out.append(f"{CONTRADICTION} “{rate.text}” cannot be the change from {a.text} to the same figure {b.text}. "
                       "FaithGuard checks each number against the report, not whether the numbers of one sentence agree "
                       "with each other (a known limitation).")
            continue
        metrics = {det.check(c.id).intended.metric for c in amounts}
        if len(metrics) != 1 or None in metrics or any(det.check(c.id).verdict != "supported" for c in amounts):
            continue  # two figures of different things, or not traced: nothing to compare
        tolerance = Decimal(1).scaleb(-rate.decimals) * Decimal("0.6")
        fits = []
        for base, new in ((a, b), (b, a)):
            g = ops.growth(new.value, base.value)
            direction_ok = rate.direction is None or (g >= 0) == (rate.direction == "up")
            fits.append(direction_ok and abs(abs(g) - abs(rate.value)) <= tolerance)
        if not any(fits):
            g = ops.growth(b.value, a.value)
            shown = render(abs(g), _percent_style(g))
            out.append(f"{CONTRADICTION} “{rate.text}” does not fit its own figures ({a.text} to {b.text} is a "
                       f"{'rise' if g >= 0 else 'fall'} of {shown}). FaithGuard checks each number against the report, "
                       "not whether the numbers of one sentence agree with each other (a known limitation).")
    return out


# ---------------------------------------------------------------------------
# Planted errors
# ---------------------------------------------------------------------------


def figures_match(text: str | None, reference: str) -> bool:
    """Each number equals the reference's to the coarser of the two printed precisions, with the same direction
    (a repair may print a figure at another scale: "Rs. 14,213 million" for "Rs. 14,212,560 thousand")."""
    from faithguard.claims import extract_claims

    if text is None:
        return False
    got, want = extract_claims(text), extract_claims(reference)
    if len(got) != len(want):
        return False
    for a, b in zip(got, want):
        unit = max(Decimal(1).scaleb(-c.decimals) * (Decimal(10) ** c.scale if c.kind == "amount" else 1) for c in (a, b))
        if a.direction != b.direction or abs(a.value - b.value) > unit / 2:
            return False
    return True


def _sibling(cells: list[Cell], a: Cell, same: tuple[str, ...], differ: str, prefer=None) -> Cell | None:
    found = [c for c in cells if c.id != a.id and c.value is not None and c.kind == a.kind and c.value != a.value
             and all(getattr(c, f) == getattr(a, f) for f in same) and getattr(c, differ) not in (None, getattr(a, differ))]
    if prefer is not None:
        found.sort(key=prefer)
    return found[0] if found else None


def _run_program(item: Item, det: DetectorOutput, edits: list) -> str | None:
    try:
        text = execute(item, det.claims, EditProgram(edits=edits)).text
    except (ExecError, KeyError, ValueError, ops.CalcError):
        return None
    return text if text != item.answer.text else None


def _match_case(word: str, like: str) -> str:
    return word.upper() if like.isupper() else word.capitalize() if like[:1].isupper() else word


def _swap(item: Item, det: DetectorOutput, supported, claim_id: str, old: Cell, new: Cell) -> str | None:
    """COPY the wrong cell into one figure, and recompute every change built on it, as a real slip carries through."""
    edits = [Copy(claim=claim_id, cell=new.id)]
    for claim, check in supported:
        if claim.id != claim_id and check.relation in ("growth", "diff") and old.id in check.cells:
            cells = [new.id if c == old.id else c for c in check.cells]
            edits.append(Calculate(claim=claim.id, expr=f"{check.relation}({', '.join(cells)})"))
    return _run_program(item, det, edits)


def plant(item: Item, det: DetectorOutput) -> list[tuple[str, str]]:
    """(label, answer text) for each kind of error that can be planted in this answer's supported figures, one of each."""
    from faithguard.detect import detect

    text = item.answer.text
    vocab = Vocabulary(item.evidence.cells())
    cells = [c for c in item.evidence.cells() if c.value is not None]
    by_id = {c.id: c for c in item.evidence.cells()}
    supported = [(claim, det.check(claim.id)) for claim in det.claims if det.check(claim.id).verdict == "supported"]
    traced = [(claim, check) for claim, check in supported if check.cells and all(c in by_id for c in check.cells)]
    out: list[tuple[str, str]] = []

    # wrong entity: every traced figure taken from another entity's column (Bank for Group), where the
    # question or answer names the entity (without one, the other column's figure is a fair reading)
    edits, other = [], None
    for claim, check in traced:
        if check.relation not in ("cell", "growth", "diff") or not check.intended.entity:
            continue
        swapped = []
        for cid in check.cells:
            s = _sibling(cells, by_id[cid], ("metric", "period", "table_id", "row"), "entity")
            if s is None or (other is not None and s.entity != other):
                break
            swapped.append(s)
            other = s.entity
        if len(swapped) != len(check.cells):
            continue
        ids = [s.id for s in swapped]
        edits.append(Copy(claim=claim.id, cell=ids[0]) if check.relation == "cell" else Calculate(claim=claim.id, expr=f"{check.relation}({', '.join(ids)})"))
    if edits and (planted := _run_program(item, det, edits)):
        out.append((f"Wrong entity: the {ENTITY_WORD.get(other, other)}'s figures", planted))

    # wrong year: the asked-for (latest) figure from an earlier year, carried into the change
    lookups = sorted([(claim, check) for claim, check in traced if check.relation == "cell"],
                     key=lambda x: by_id[x[1].cells[0]].period or "", reverse=True)
    in_answer = {by_id[check.cells[0]].id for _, check in lookups}
    for claim, check in lookups:
        a = by_id[check.cells[0]]
        s = _sibling([c for c in cells if c.id not in in_answer], a, ("metric", "entity", "table_id"), "period",
                     prefer=lambda c: (c.period or "") > (a.period or ""))
        if s is not None and (planted := _swap(item, det, traced, claim.id, a, s)):
            out.append((f"Wrong year: the {s.period} figure", planted))
            break

    # wrong line item: a neighbouring row of the same column, sign, unit and rough size (not EPS for an amount)
    for claim, check in lookups:
        a = by_id[check.cells[0]]
        column = [c for c in cells if c.table_id == a.table_id and c.col == a.col and c.metric and c.metric != a.metric
                  and c.kind == a.kind and c.value != a.value and (c.value < 0) == (a.value < 0)
                  and c.scale == a.scale and c.currency == a.currency]
        s = min(column, key=lambda c: (not (abs(a.value) / 10 <= abs(c.value) <= abs(a.value) * 10), abs(c.row - a.row)), default=None)
        if s is not None and (planted := _swap(item, det, traced, claim.id, a, s)):
            out.append((f"Wrong line item: {clean_label(s, vocab)}", planted))
            break

    def still_supported(new_text: str, start: int) -> bool:
        """Whether the checker still supports the figure at `start` after the change (it can match another ratio by chance)."""
        variant = item.model_copy(update={"answer": item.answer.model_copy(update={"text": new_text})})
        d = detect(variant)
        return any(c.start == start and d.check(c.id).verdict == "supported" for c in d.claims)

    figures = [claim for claim, _ in supported]
    # wrong scale: thousand read as million, million as billion
    for claim in figures:
        m = _SCALE_WORD.search(claim.text) if claim.kind == "amount" else None
        if m:
            new = _match_case(SCALE_SWAP[m.group(1).lower()], m.group(1))
            start = claim.start + m.start(1)
            out.append((f"Wrong scale: “{m.group(1)}” → “{new}”", apply(text, [(start, start + len(m.group(1)), new)])))
            break

    # wrong direction: rose for a fall, on a change (the checker reads direction on changes only, not on "rose to X")
    relation = {claim.id: check.relation for claim, check in supported}
    for claim in figures:
        if claim.direction_span and relation.get(claim.id) in ("growth", "diff") and claim.value != 0:
            s, e = claim.direction_span
            word = text[s:e]
            if word.lower() in DIRECTION_WORDS:
                new = _match_case(OPPOSITE.get(word.lower()) or DIRECTION_WORDS[word.lower()][1], word)
                edits = [(s, e, new)]
                article = re.search(r"\b(an?)\s+$", text[:s])
                if article:  # "a rise" -> "a fall", "an increase" -> "a decrease"
                    a_or_an = "an" if new[:1].lower() in "aeiou" else "a"
                    edits.insert(0, (article.start(1), article.end(1), _match_case(a_or_an, article.group(1))))
                planted = apply(text, edits)
                shift = sum(len(n) - (e0 - s0) for s0, e0, n in edits if e0 <= claim.start)  # edits before the figure move it
                if not still_supported(planted, claim.start + shift):
                    out.append((f"Flip the direction: “{word}” → “{new}”", planted))
                    break

    # a maths slip: the growth rate or figure off by a few units in its last printed digit (the commonest real error)
    for claim in sorted(figures, key=lambda c: c.kind != "percent"):
        if claim.kind not in ("percent", "amount") or claim.value == 0:
            continue
        try:
            style = mention_of(claim, text).style
            unit = Decimal(1).scaleb(-claim.decimals) * (Decimal(10) ** claim.scale if claim.kind == "amount" else 1)
            value = abs(claim.value) if claim.direction is not None else claim.value
        except Exception:
            continue
        for k in (3, -3, 4, -4, 7):  # a slip that happens to equal another ratio in the tables is no planted error
            try:
                new = render(value + k * unit, style)
            except Exception:
                break
            planted = apply(text, [(claim.start, claim.end, new)])
            if new != claim.text and not still_supported(planted, claim.start):
                out.append((f"Maths slip: {claim.text} → {new}", planted))
                break
        else:
            continue
        break
    seen, unique = {text}, []
    for label, planted in out:
        if planted not in seen:
            seen.add(planted)
            unique.append((label, planted))
    return unique
