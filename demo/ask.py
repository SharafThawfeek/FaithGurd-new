"""Ask your own question: any question on one of the demo's reports, then errors planted in its answer.

The answer comes from the AI live on this laptop (demo.models), from a template written from the cells
the question names, or from the presenter's keyboard. Nothing here reads gold: a typed question has
none. The checker reads the metric, entity and period from the question's own words
(faithguard.claims.question_context); the question's type, one of the policy's features, is read from
its wording here, as the benchmark's writers set it by hand.

Planted errors are written by the executor: a COPY or CALCULATE that points at the wrong cells (another
entity, year or line) puts the wrong figure in the answer's own printed style, the way real slips look (a direction
word it swaps is then written grammatically: "a growth of", not its "a grow of").
The rule checker, policy and repairers are the frozen research system; nothing here changes them.
"""

from __future__ import annotations

import csv
import difflib
import re
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from faithguard.calc import expr, ops
from faithguard.calc.numbers import NumberStyle, default_style, render
from faithguard.claims import (_ASIDE_AFTER, _PERIOD_AFTER, _PREVIOUS_AFTER, _PREVIOUS_YEAR, DIRECTION_WORDS, Vocabulary,
                               mention_of, question_context, sentence_bounds, years_in)
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


def _masked(text: str, vocab: Vocabulary) -> str:
    """The question with the line items it names replaced by "_", longest first."""
    norm = f" {normalise_metric(text.replace('%', ' percent '))} "
    for s in vocab.surfaces:  # longest first
        norm = norm.replace(f" {s.text} ", " _ ")
    return norm


def question_type(text: str, vocab: Vocabulary | None = None) -> str:
    if vocab is not None:
        text = _masked(text, vocab)
    return next((name for name, pattern in QUESTION_TYPES if pattern.search(text)), "lookup")


# a figure the template does not compute: matched on the masked question, so a line called "Net interest margin" is a lookup
_RATIO_WORDS = re.compile(r"\b(margins?|ratios?|return on|roe|roa|yields?|cover|coverage)\b", re.I)
_COMPARE = re.compile(r"\bcompared?\b", re.I)


_NAME = r"[A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*)*"
_POSSESSIVE = re.compile(rf"\b({_NAME})['’]s\b")
_NAMED_AFTER = re.compile(rf"\b(?:of|for|at|from|did|does|do|has|have|is|was|were)\s+({_NAME})")  # "the profit of Insee
# Cement", "How did Commercial Bank of Ceylon perform"
_SUBJECT = re.compile(rf"\b(?:did|does|do|has|have|had)\s+({_NAME})\s+(?:report|make|made|earn|post|record|generate|pay|paid|"
                      r"declare|achieve|perform|announce)\w*\b")  # "What revenue did John Keells report"
# capitalised words that name no other company: the report's parts, question words, people and bodies inside the company,
# months, currencies and accounting terms ("the CEO's salary", "as of December 31", "for FY2025/26")
NOT_A_COMPANY = set(
    "group groups bank banks company companies parent subsidiary subsidiaries consolidated standalone the a an fy q h "
    "what whats who how why when which where did does do was were is are has had have will would can could should "
    "in for by of on at from to and or it its that this these those year years sri lanka plc holdings ltd limited inc "
    "ceo cfo coo cto md chairman chairperson chair board director directors management auditor auditors shareholder "
    "shareholders stockholder stockholders employee employees staff secretary they we you it ebitda ebit "
    "january february march april may june july august september october november december "
    "jan feb mar apr jun jul aug sep sept oct nov dec rs lkr usd us ifrs slfrs gaap note eps roe roa nii pat pbt nav dps".split())
# a word that makes a capitalised name after "of" or "from" a company's: "the profit of Insee Cement"
COMPANY_WORDS = set("plc ltd limited holdings group bank company co cement capital finance inc corporation corp lanka ceylon "
                    "industries insurance telecom hotels plantations motors mills brewery breweries enterprises".split())


def other_company(report: "Report", text: str) -> str | None:
    """Why a question about another company cannot be checked against this report, or None. A capitalised name is
    another company's when it holds a word that is neither in the report's own name nor in NOT_A_COMPANY: "Commercial
    Bank's" on Sampath Bank's report, "Insee Cement's" on Tokyo Cement's (a shared word is not enough). After "of", "for",
    "at", "from" or a verb ("the profit of Insee Cement", "How did Commercial Bank of Ceylon perform"), a COMPANY_WORDS word
    after its first word is needed too, and words of the report's line items do not count: "Revenue from Contracts with
    Customers", "Group Revenue". A name between "did" and a verb a company does needs no company word ("What revenue did
    John Keells report"), but line-item words still do not count."""
    own = {w.lower() for w in re.findall(r"[A-Za-z]+", report.name)}
    lines = {w for s in report.vocab().surfaces for w in s.text.split()}
    names = ([(n, False, False) for n in _POSSESSIVE.findall(text or "")]
             + [(n, True, False) for n in _NAMED_AFTER.findall(text or "")] + [(n, True, True) for n in _SUBJECT.findall(text or "")])
    for name, after, subject in names:
        words = name.split()
        while words and {w.lower() for w in re.findall(r"[A-Za-z]+", words[0])} <= NOT_A_COMPANY:
            words = words[1:]  # "Did Commercial Bank's" names Commercial Bank
        if not {w.lower() for w in re.findall(r"[A-Za-z]+", " ".join(words))} - NOT_A_COMPANY - own - (lines if after else set()):
            continue
        if after and not subject and not {w.lower() for w in words[1:]} & COMPANY_WORDS:
            continue  # capitals are more often a line's ("Amounts Due from Related Parties", "Group Revenue") than a company's
        return (f"This is {report.name}'s report, and the question asks about {' '.join(words)}. FaithGuard checks answers "
                "against the chosen report only: pick that company's report, or ask about this one.")
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
    """'Total Assets' -> 'total assets', keeping acronyms and currencies: 'Net income from FVTPL', 'Dividend per share - Rs.';
    'Due to banks' -> 'amounts due to banks'."""
    words = " ".join(w if (len(w) > 1 and w.isupper()) or _CURRENCY.fullmatch(w) else w.lower() for w in label.split())
    return f"amounts {words}" if _DUE.match(words) else words


_DUE = re.compile(r"\s*due\s+(?:to|from)\b", re.I)
_CURRENCY = re.compile(r"\(?(?:Rs\.?|US\$|LKR|USD)\)?")
_UNIT_AFTER = re.compile(r"\s*[-–]\s*(Rs\.?|US\$|\$)\s*$")


def _display_label(label: str) -> str:
    """A line's name for the screen, its unit in brackets: 'Dividend per share - Rs.' -> 'Dividend per share (Rs.)'. The
    checker reads the line only with the printed ' - Rs.', so the text it gets keeps that."""
    return _UNIT_AFTER.sub(r" (\1)", label)


def _verb(label: str) -> str:
    """'was' or 'were' for the head of the label: 'revenue from contracts with customers was', 'total assets were',
    'amounts due to related parties were'."""
    if _DUE.match(label):
        return "were"
    head = re.split(r"\s+(?:due|from|of|on|in|with|for|to|at|attributable|net of)\s+", label.strip(), maxsplit=1, flags=re.I)[0]
    last = head.split()[-1].lower() if head.split() else ""
    return "were" if last.endswith("s") and not last.endswith(("ss", "us", "is")) else "was"


def named_metrics(vocab: Vocabulary, text: str) -> set[str]:
    """The metrics the question names, by surfaces that are not part of a longer one it names ("sales" in "cost of sales")."""
    norm = f" {normalise_metric(text)} "
    found = [s for s in vocab.surfaces if f" {s.text} " in norm]
    return {s.metric for s in found if not any(o.text != s.text and f" {s.text} " in f" {o.text} " for o in found)}


def _subject(cell: Cell, name: str, vocab: Vocabulary | None = None, shown: bool = False) -> str:
    """'the Group's total assets'; shown, for an answer rather than a question, with the unit in brackets."""
    label = clean_label(cell, vocab)
    label = _in_sentence(_display_label(label) if shown else label)
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
    own_name = _own_words(report)
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
                shown = text[:start] + _in_sentence(_display_label(line)) + text[end:]
                note = (note + " " if note else "") + (
                    f"Read “{text[start:end]}” as the report's line “{line}”." if re.search(r"\bmany\s+$", text[:start], re.I)
                    else f"Read as “{shown}”: the report calls this line “{line}”.")  # not "How many number of employees"
                text = rewritten
    years = [y for y in years_in(text) if y in vocab.periods]
    period = None
    if not years:
        short_year = normalise_period(text)
        latest = vocab.latest_period()
        previous = [p for p in vocab.periods if p < (latest or "")]
        m = _PREVIOUS.search(text)
        if short_year in vocab.periods:
            period = short_year
        elif m and previous:
            if question_type(text, vocab) != "lookup" or _BASE_BEFORE.search(text[:m.start()]):
                period = latest  # "How did X change compared with last year?": the change into the latest year
            elif m.group(1).lower() == "last":
                # "last year" is the latest year the report covers (its previous year is "the previous year")
                period = latest
                note = (note + " " if note else "") + f"Read “{m.group(0)}” as {latest}, the report's latest year; give the year to be sure."
            else:
                period = previous[-1]
    return text, period, note


_BASE_BEFORE = re.compile(r"\b(?:compared\s+(?:with|to)|than|versus|vs\.?|from|since|over|against)\s+(?:the\s+)?$", re.I)
QUESTION_WORDS = {"percentage", "percent", "grow", "grew", "growth", "change", "changed", "increase", "decrease", "rise", "fall",
                  "compare", "compared", "last", "previous", "prior", "preceding", "many", "have", "has", "had"}


def _own_words(report: Report) -> set[str]:
    """The report's own name and the words of a question's type: not words that name a line item."""
    return {w.lower() for w in re.findall(r"[A-Za-z]+", report.name)} | QUESTION_WORDS


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
    words = {w for w in words if w and not re.fullmatch(r"(?:fy|q|h)?\d+", w)}  # also "FY26", which normalise_metric keeps
    shared = {m: words & {_stem(w) for w in m.split()} for m in {s.metric for s in vocab.surfaces}}
    best = max((len(w) for w in shared.values()), default=0)
    found = [m for m, w in shared.items() if w and len(w) == best]
    if not best or len(found) != 1 or (strict and shared[found[0]] != words):
        return None
    return found[0]


def _percent_style(value: Decimal):
    return default_style("percent", decimals=2 if abs(value) < 1 else 1)


def missing_year(report: Report, question: str) -> str | None:
    """Why a question about a year the report has no figures for cannot be answered from it, or None. The same refusal
    for the table answer and, before it is asked, for the AI: the checker would read the figure as another year's."""
    vocab = report.vocab()
    text = read_question(report, question)[0]
    years = set(years_in(text))
    if not years and _SHORT_FY.search(text):  # "FY23", which the checker's year reader skips
        years = {normalise_period(_SHORT_FY.search(text).group())}
    missing = sorted(y for y in years if y and y not in vocab.periods)
    if missing:
        return f"The report covers {_covered(vocab.periods)} only; it has no figures for {', '.join(missing)}."
    return None


def _covered(periods: list[str]) -> str:
    return ", ".join(periods[:-1]) + f" and {periods[-1]}" if len(periods) > 1 else "".join(periods)


_SHORT_FY = re.compile(r"\bFY\s?\d{2}\b", re.I)
# a row that counts people or places, printed in a table headed in money ("Number of employees" under Rs. '000)
_COUNT_ROW = re.compile(r"^\s*(?:number|no\.?)\s+of\b|\b(?:employees|branches|staff|outlets|headcount)\b", re.I)
# words beside a line's name that do not make it a longer name: "the Group's annual revenue" is still revenue
_HARMLESS = {"reported", "annual", "yearly", "full", "overall", "total", "consolidated", "standalone", "approximately", "amounts"}


def _longer_name(vocab: Vocabulary, text: str, metric: str, extra_stop: set[str]) -> str | None:
    """The longer name the question gives a line, when the line the checker reads is only part of it: "net interst income"
    (a typo) read as the line "Income". The words right beside the line's name are taken with it while they are content
    words, so the template asks instead of answering about a shorter line."""
    tokens = normalise_metric(text).split()
    surface = next((s.text.split() for s in vocab.surfaces if s.metric == metric and f" {s.text} " in f" {' '.join(tokens)} "), None)
    if surface is None:
        return None
    at = next(i for i in range(len(tokens)) if tokens[i:i + len(surface)] == surface)
    skip = {_stem(w) for w in STOPWORDS | extra_stop | _HARMLESS} | set(ENTITY_WORDS)

    def content(word: str) -> bool:
        w = _stem(word)
        return bool(w) and not re.fullmatch(r"(?:fy|q|h)?\d+", w) and w not in skip

    start, end = at, at + len(surface)
    while start > 0 and content(tokens[start - 1]):
        start -= 1
    while end < len(tokens) and content(tokens[end]):
        end += 1
    if {_stem(w) for w in tokens[start:end]} <= {_stem(w) for w in metric.split()}:
        return None  # more of the same line's name ("value added tax on financial services" for "Less: Value added tax ...")
    return " ".join(tokens[start:end]) if (start, end) != (at, at + len(surface)) else None


def draft(report: Report, question: str) -> str:
    """A correct answer written from the cells the question names: a lookup, a growth rate or a change."""
    vocab = report.vocab()
    text, period, _ = read_question(report, question)
    ctx = question_context(Question(id="q", issuer=report.id, text=text, period=period), vocab)
    kind = question_type(text, vocab)
    if (missing := missing_year(report, question)):
        raise Unanswerable(missing)
    years = sorted(y for y in set(years_in(text)) if y in vocab.periods)
    if kind == "comparison" and (len(years) > 1 or (_COMPARE.search(text) and (years or period))):
        kind = "growth"  # "in 2026 compared with 2025", "compared with last year": the change from the year before
    if _RATIO_WORDS.search(_masked(text, vocab)):
        raise Unanswerable("The template writes lookups, growth rates and changes only; it does not work out a margin, ratio or "
                           "return. Ask the AI or type an answer.")
    if kind not in ("lookup", "growth", "difference"):
        raise Unanswerable("The template writes lookups, growth rates and changes only. Ask the AI or type an answer.")
    entities = {ENTITY_WORDS[w] for w in re.findall(r"[a-z]+", text.lower()) if w in ENTITY_WORDS} & set(vocab.entities)
    if len(entities) > 1:
        raise Unanswerable("The question compares two entities; the template writes one entity's figures only. "
                           "Ask the AI or type an answer.")
    named = named_metrics(vocab, text)
    if len(named) > 1:
        raise Unanswerable(f"The question names more than one line item ({', '.join(sorted(named))}), so the template "
                           "does not guess which one. Name one line item, ask the AI, or type an answer.")
    # strict: a short name only when every content word of the question is in the line's name, so "What dividend per
    # share did the Company pay?" is not answered with net asset value per share
    metric = ctx.metric or _metric_from_words(vocab, text, _own_words(report), strict=True)
    if metric is None:
        raise Unanswerable("The tables have no line item that this question names, so there is no cell to write an answer from. "
                           "Try a line item listed under the question, ask the AI, or type an answer.")
    if ctx.metric and (longer := _longer_name(vocab, text, metric, _own_words(report))):
        label = next((clean_label(c, vocab) for c in report.evidence.cells() if c.metric == metric and c.row_label.strip()), metric)
        close = difflib.get_close_matches(longer, sorted({c.metric for c in report.evidence.cells() if c.metric}), n=1, cutoff=0.8)
        meant = next((clean_label(c, vocab) for c in report.evidence.cells() if close and c.metric == close[0] and c.row_label.strip()), None)
        raise Unanswerable(f"The question names “{longer}”, which is not a line of the tables; the checker would read it as "
                           f"“{_display_label(label)}”, so the template does not answer it."
                           + (f" Did you mean “{_display_label(meant)}”?" if meant else "")
                           + " Name the line as the report prints it, ask the AI, or type an answer.")
    a = _find(report, metric, ctx.entity, years[-1] if years else ctx.period, text)
    if a is None:
        raise Unanswerable(f"No figure for {metric}{f' ({ctx.entity})' if ctx.entity else ''} in {years[-1] if years else ctx.period}: "
                           "the template has nothing to copy. Ask the AI or type an answer.")
    if a.value < 0:
        raise Unanswerable(f"{clean_label(a)} is printed in brackets, so the tables store it as a negative number, and the frozen "
                           "checker reads a positive figure for it as a sign error: the template does not write it. Ask the AI or type an answer.")
    subject = _cap(_subject(a, report.name, vocab, shown=True))

    def style(cell: Cell):
        # a count ("Number of employees") sits in a money table: write it as the number printed, not as rupees
        return NumberStyle(kind="number", scale=cell.scale) if _COUNT_ROW.search(_label(cell)) else _style(cell)

    A = render(a.value, style(a))
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
        B = render(b.value, style(b))
        if a.value == b.value:
            return f"{subject} {_verb(clean_label(a, vocab))} unchanged at {A} in {a.period}."
        if kind == "growth":
            g = ops.growth(a.value, b.value)
            return f"{subject} {'rose' if g >= 0 else 'fell'} {render(abs(g), _percent_style(g))} from {B} in {b.period} to {A} in {a.period}."
        d = ops.diff(a.value, b.value)
        return (f"{subject} {'increased' if d >= 0 else 'decreased'} by {render(abs(d), style(a))} "
                f"from {B} in {b.period} to {A} in {a.period}.")
    return f"{subject} {_verb(clean_label(a, vocab))} {A} in {a.period}."


def caveats(item: Item, det: DetectorOutput, action: str) -> list[str]:
    """Known limitations of the frozen system that this question or answer runs into, said on screen."""
    vocab = Vocabulary(item.evidence.cells())
    metric = question_context(item.question, vocab).metric
    by_id = {c.id: c for c in item.evidence.cells()}
    supported = [c for c in det.checks if c.verdict == "supported"]
    # the cells the checker read for the answer: not those a computed figure matched by chance (views' loose_match)
    traced = {cid for check in det.checks if not _loose(check) for cid in check.cells}
    bracketed = [c for c in item.evidence.cells() if c.kind == "amount" and c.value is not None and c.value < 0
                 and ((metric is not None and c.metric == metric) or c.id in traced)]
    out = []
    if bracketed:
        out.append(f"{_label(bracketed[0])} is printed in brackets, so the tables store it as a negative number. The rule checker "
                   "reads a positive figure for it as a sign error, and the direction of a change in it by the stored sign.")
    if any(c.value == 0 and "000" in c.text for c in det.claims):
        out.append("“000” in the answer is a units note, but the rule checker reads it as a number.")
    asked = vocab.entity_in(_singular(item.question.text))
    m = re.search(r"\b\w+(?:\s+\w+)?\s+(Bank|Company)\b", item.answer.text)
    name_word = _ENTITY_IN_NAME.search(issuer_names().get(item.question.issuer, ""))
    if (m and name_word and name_word.group(1).lower() == m.group(1).lower()
            and m.group(0).split()[0].lower() in issuer_names().get(item.question.issuer, "").lower()
            and any(c.intended.entity == m.group(1).lower() for c in det.checks) and asked != m.group(1).lower()):
        # only when the checker did read that column, and the question asks about another part (or names none)
        out.append(f"The answer says “{m.group(0)}”: the rule checker reads the “{m.group(1)}” in the company's name as the "
                   f"{m.group(1)} column, not the Group's.")
    if action == "abstain" and det.checks and len(supported) == len(det.checks):
        if item.question.question_type == "lookup" and any(  # "X in 2025, up from Y in 2024"
                c.direction is not None and c.kind == "amount" and det.check(c.id).relation == "cell" for c in det.claims):
            out.append("Every number is supported, yet the policy withholds the answer: a direction word (“up”, “down”) beside a "
                       "looked-up figure raises its P(unsafe), because it counts the figures that carry one, a feature it learned on "
                       "the controlled track. Writing “compared with” instead of “up from” may let the answer through.")
        else:
            out.append("Every number is supported, yet the policy withholds the answer: it was certified on the controlled track's small "
                       "tables, and on large real reports (and on “by how much” questions) its P(unsafe) runs high, so it errs on the safe side.")
    if metric is None and any(c.intended.metric is None for c in supported):
        out.append(f"{UNKNOWN_LINE} FaithGuard could not tell which line of the report the question is about, so it only checked "
                   "that each figure appears somewhere in the tables (a known limitation). Name the line as the report prints it.")
    elif metric is None and supported:
        # the question names no line, so the answer's own words chose the line each figure was checked against
        lines = list(dict.fromkeys(clean_label(by_id[c.cells[0]], vocab) for c in supported if c.cells and c.cells[0] in by_id))
        out.append(f"{UNKNOWN_LINE} the question names no line of the report, so FaithGuard checked each figure against the line the "
                   f"answer names ({', '.join(lines[:3])}), not against what the question asks (a known limitation). "
                   "Name the line as the report prints it.")
    if re.search(r"\battributable\b", item.question.text, re.I):
        out.append("“Attributable to” is a breakdown the checker can confuse with the total row (profit for the year, including "
                   "non-controlling interests): check the owners' share against the report yourself (a known limitation).")
    words = EXPLAIN.search(item.answer.text)
    if words:
        out.append(f"FaithGuard checks the numbers, not the words around them: “{words.group(0)}” was not checked.")
    given = {e for c in supported if (e := _entity_of(c, by_id))}
    if asked and given and asked not in given:
        other = sorted(given)[0]
        out.append(f"The question asks about the {ENTITY_WORD.get(asked, asked)}, but the answer gives the "
                   f"{ENTITY_WORD.get(other, other)}'s figure. FaithGuard checks each number against what the answer says it is, "
                   "not whether it answers the question asked.")
    elif asked is None and len(vocab.entities) > 1 and given:
        out.append("The question names no part of the company, so FaithGuard accepts either the Group's or the "
                   f"{'Bank' if 'bank' in vocab.entities else 'Company'}'s figure. Say which one you mean.")
    lacking = sorted({y for y in years_in(item.question.text) if y not in vocab.periods})
    if lacking and vocab.periods:  # a typed answer (the table answer and the AI refuse such a question)
        out.append(f"The report covers {_covered(vocab.periods)} only; it has no figures for {', '.join(lacking)}, so FaithGuard "
                   "cannot check a figure for that year.")
    year = item.question.period or max((y for y in years_in(item.question.text) if y in vocab.periods), default=None)
    years = {p for c in supported for p in ({by_id[x].period for x in c.cells if x in by_id} if c.relation == "cell"
                                             else {c.intended.period})} - {None}
    if year and years and year not in years and len(supported) == len(det.checks):  # a misread figure may be the year asked
        out.append(f"The question asks about {year}, but the answer gives the {max(years)} figure. FaithGuard checks each number "
                   "against what the answer says it is, not whether it answers the question asked.")
    if action != "repair" and any("restated" in (by_id[cid].column_label or "").lower() for cid in traced if cid in by_id):
        out.append(RESTATED)  # for a repair, released_problems says it of the cells behind the released text
    counts = [c for c in det.claims if c.kind == "number" and c.currency is None and COUNT_AFTER.match(item.answer.text[c.end:c.end + 25])
              and not (det.check(c.id).verdict == "supported"  # the report's own count: "Number of employees"
                       and any(_COUNT_ROW.search(_label(by_id[x])) for x in det.check(c.id).cells if x in by_id))]
    if counts:
        out.append(f"“{counts[0].text}” is a count, not a report figure, but FaithGuard reads every number as a figure of the line asked "
                   "about (a known limitation): ignore what it does with it.")
    kind = item.question.question_type
    unchecked = [c for c in det.claims if c.kind in ("amount", "number") and det.check(c.id).verdict != "supported"]
    if kind in ("sum", "average") and unchecked and action != "repair":  # for a repair, released_problems says it
        total = max(unchecked, key=lambda c: abs(c.value))
        out.append(f"{SUM} “{total.text}” {'adds up' if kind == 'sum' else 'averages'} several lines, and FaithGuard compares a "
                   "figure with one line only (a known limitation).")
    if action != "repair":  # for a repair, released_problems says it of the figure the fix changed
        for i, claim in enumerate(det.claims):  # one note per figure, each quoting its figure first (the pages key on it)
            check = det.check(claim.id)
            if check.verdict != "supported" and set(check.slots) == {"period"} and not _own_year(item.answer.text, det.claims, i):
                source = "the clause's year" if years_in(item.answer.text[slice(*sentence_bounds(item.answer.text, claim.start))]) \
                    else "the question's year"
                out.append(f"{ONE_YEAR} “{claim.text}” has no year of its own, so FaithGuard read it as {check.intended.period}, "
                           f"{source} (a known limitation); it may be right.")
    return out


def _singular(text: str) -> str:
    """'the groups' and 'the companys' as the entity words the checker knows ("what was the groups proft"); not a line's
    own plural ("placements with banks", "amounts due to group companies")."""
    return re.sub(r"\b(the\s+)(?:(group|bank)s|compan(?:ys|ies))\b", lambda m: m.group(1) + (m.group(2) or "company"), text, flags=re.I)


def _entity_of(check, by_id: dict) -> str | None:
    """The entity a supported figure is about: the one the checker read, else that of every cell it traced to."""
    entities = {by_id[x].entity for x in check.cells if x in by_id}
    return check.intended.entity or (entities.pop() if len(entities) == 1 else None)


def _refs(expression: str | None) -> list[str]:
    try:
        return expr.refs(expr.parse(expression)) if expression else []
    except Exception:
        return []


def _loose(check) -> bool:
    """An unsupported computed figure whose cells are only what it matched by chance, over other lines or with no line
    named (views.claim_views' loose_match)."""
    return (check.verdict != "supported" and check.relation in ("growth", "diff", "share", "ratio")
            and ("metric" in check.slots or check.intended.metric is None) and set(check.slots) != {"value"}
            and not set(check.cells) <= set(_refs(check.fix)))


def _own_year(text: str, claims: list, index: int) -> bool:
    """Whether the answer gives this figure a year of its own: one right after it ("in 2025", "as at 31 March 2026"), or in
    the words before it that are not the previous figure's ("up from" in "$6.04 billion as of December 31, 2025, up from
    $4.89 billion a year earlier" has none). Else the checker borrowed the clause's year (claims.claim_context), or the
    question's."""
    claim = claims[index]
    s_start, s_end = sentence_bounds(text, claim.start)
    clause = text[max(s_start, claims[index - 1].end if index else 0):claim.start]
    if index and claims[index - 1].end >= s_start and (m := _PERIOD_AFTER.match(_ASIDE_AFTER.sub("", clause, count=1))):
        clause = _ASIDE_AFTER.sub("", clause, count=1)[m.end():]  # the previous figure's year
    if normalise_period(clause) or _PREVIOUS_YEAR.search(clause):
        return True
    next_start = claims[index + 1].start if index + 1 < len(claims) else s_end
    after = text[claim.end:min(next_start, s_end)]
    rest = _ASIDE_AFTER.sub("", after if after.strip(" (") else text[claim.end:s_end], count=1)
    return bool(_PERIOD_AFTER.match(rest) or _PREVIOUS_AFTER.match(rest))


UNKNOWN_LINE = "Unknown line item:"
UNTRUSTED = "Careful, this fix is not trustworthy:"
ROUNDED = "Rounded:"
ONE_YEAR = "One year per clause:"
SUM = "Not checkable:"
WORDING = "Wording:"
RESTATED = "A figure comes from a restated comparative column (Restated*); the figure as originally reported is not in the tables."
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


def _same_name_row(item: Item, old, copied: list[str]) -> tuple[str, str, str] | None:
    """The row label and table title of another cell holding exactly the figure a repair replaced, in the copied cell's
    column, whose row has the copied row's name, and the copied cell's table title: the figure was right, and the
    checker read a row of the same name in another statement (Sunshine's balance-sheet "Non-controlling interests" read
    as the comprehensive income attributable to them)."""
    ids = {c.id for c in item.evidence.cells()}
    if old is None or old.kind not in ("amount", "number") or len(copied) != 1 or copied[0] not in ids:
        return None  # "number": the figure before a units note, "7,450,423 Rs. '000"
    read = item.evidence.cell(copied[0])
    titles ={t.id: t.title or "another table" for t in item.evidence.tables}
    # a bare number has no unit to compare, so its printed digits are; "Rs. 5,140,154 million" is a scale slip, not this
    digits = re.sub(r"\D", "", old.text) if old.currency is None and old.scale == 0 else ""
    for cell in item.evidence.cells():
        if (cell.id == read.id or cell.kind != "amount" or cell.value is None
                or (cell.period, cell.entity) != (read.period, read.entity) or _words(cell.row_label) != _words(read.row_label)):
            continue
        if cell.value == old.value or (len(digits) >= 4 and re.sub(r"\D", "", cell.text) == digits):
            return cell.row_label.strip(), titles.get(cell.table_id, "another table"), titles.get(read.table_id, "another table")
    return None


def released_problems(item: Item, final) -> list[str]:
    """For a repaired answer, what the frozen gate passes but the demo says: a count or note number overwritten with a
    figure, a figure that is another row's of the same name, a total overwritten with one line's figure, a figure read
    under the clause's year and changed, one figure
    written for two things, a repaired figure beside
    a year that is not its cell's year, a restating bracket that now disagrees, the fix giving another part of the company
    than the question asks about or mixing two parts in one sentence, the restated note for the cells behind the released
    text, and a direction word the executor swapped ungrammatically."""
    if final.action != "repair" or not final.text or not final.repair or not final.repair.program:
        return []
    from faithguard.claims import extract_claims
    from faithguard.detect import detect

    det = final.detector
    try:
        res = execute(item, det.claims, final.repair.program)
    except (ExecError, KeyError, ValueError, ops.CalcError):
        return []
    out = []
    text = item.answer.text
    claims = {c.id: c for c in det.claims}
    by_id = {c.id: c for c in item.evidence.cells()}
    for ch in res.changes:
        old = claims.get(ch.claim_id)
        if old and old.currency is None and old.scale == 0 and old.kind in ("amount", "number") and (
                _BARE.match(old.text.strip()) or COUNT_AFTER.match(text[old.end:old.end + 25])):
            out.append(f"{UNTRUSTED} “{old.text}” looks like a count or a reference, not a report figure, and FaithGuard wrote "
                       f"{ch.new} over it (it reads every number as a figure: a known limitation).")
            break
    if item.question.question_type in ("sum", "average"):
        moved = [c for c in res.changes if c.new != c.old and c.claim_id in claims]
        ch = max(moved, key=lambda c: abs(claims[c.claim_id].value), default=None)  # the total is the largest figure
        if ch is not None:
            out.append(f"{UNTRUSTED} “{ch.old}” {'adds up' if item.question.question_type == 'sum' else 'averages'} several lines, "
                       f"and FaithGuard compares a figure with one line only, so it wrote that line's {ch.new} over it (a known limitation).")
    one_year = False
    for ch in res.changes:  # one note per changed figure, each quoting it first (the pages key on it)
        i = next((k for k, c in enumerate(det.claims) if c.id == ch.claim_id), None)
        check = det.check(ch.claim_id)
        if (i is None or ch.new == ch.old or check.verdict == "supported" or set(check.slots) != {"period"}
                or _own_year(text, det.claims, i)):
            continue
        read = check.intended.period
        meant, said = _meant_year(text, det.claims, i, read, item)
        source = "the clause's year" if years_in(text[slice(*sentence_bounds(text, det.claims[i].start))]) else "the question's year"
        out.append(f"{UNTRUSTED} FaithGuard reads one year per clause, so it read “{ch.old}” as {read}, {source}, and changed it, but the "
                   + (f"answer gives it for {meant}" if said else f"answer may give it for {meant}, the year the question asks about"
                      if meant else "answer may give it for another year") + " (a known limitation).")
        one_year = True
    for ch in res.changes:
        old = claims.get(ch.claim_id)
        cell = by_id.get(ch.cells[0]) if len(ch.cells) == 1 else None
        written = extract_claims(ch.new)
        if (cell is not None and cell.kind == "amount" and cell.value and written and ch.new != cell.text
                and not (old and old.currency is None and old.scale == 0)  # a unit-less page or note number has no unit to keep
                and abs(written[0].value - cell.value) > abs(cell.value) * Decimal("0.001")):
            out.append(f"{ROUNDED} the fix keeps the answer's unit, so the report's figure {cell.text} is written as {ch.new}.")
            break
    for ch in res.changes:
        if (named := _named_line(item, claims.get(ch.claim_id), ch.cells)):
            out.append(f"{UNTRUSTED} “{claims[ch.claim_id].text}” is the report's figure for “{named}”, the line the answer "
                       f"names, but FaithGuard read a shorter line name and changed it to {ch.new} (a known limitation).")
            break
        if ch.new != ch.old and (same := _same_name_row(item, claims.get(ch.claim_id), ch.cells)):
            label, where, read_in = (s[0].lower() + s[1:] if i else s for i, s in enumerate(same))
            out.append(f"{UNTRUSTED} “{claims[ch.claim_id].text}” is the report's figure for “{label}” in the {where}, but FaithGuard "
                       + (f"read the row of the same name in the {read_in}" if where != read_in else "read another row of that name")
                       + f" and changed it to {ch.new}; rows that share a name are a known limitation.")
            break
    changed, shift = [], 0
    for start, end, new_text in sorted(res.replacements):
        changed.append((start + shift, start + shift + len(new_text)))
        shift += len(new_text) - (end - start)

    released = extract_claims(final.text)
    aligned = len(released) == len(det.claims)  # a repair swaps numbers for numbers, so the i-th figure stays the i-th
    restating = {i for i in range(len(det.claims) - 1) if _restates(text, det.claims[i], det.claims[i + 1])} if aligned else set()
    for i in sorted(restating):
        a, b = released[i], released[i + 1]
        if re.sub(r"\D", "", a.text) != re.sub(r"\D", "", b.text) and abs(a.value - b.value) > max(_unit(a), _unit(b)) / 2:
            out.append(f"{UNTRUSTED} the answer gave one figure twice, {det.claims[i].text} ({det.claims[i + 1].text}), and the fix "
                       f"changed them to two different figures, {a.text} and {b.text}.")
            break
    for i, a in enumerate(released):
        if one_year:
            break  # the same two figures: said above
        twin = next((b for j, b in enumerate(released) if j > i and not (j == i + 1 and i in restating)
                     and (a.kind == b.kind or {a.kind, b.kind} <= {"amount", "number"}) and a.value
                     and any(s <= c.start < e for c in (a, b) for s, e in changed)
                     and abs(abs(a.value) - abs(b.value)) <= max(_unit(a), _unit(b)) / 2), None)
        if twin is not None:
            out.append(f"{UNTRUSTED} the fixed answer gives the same figure ({a.text} and {twin.text}) for two different things.")
            break
    shift = 0
    for start, end, new in sorted(res.replacements):
        ch = next((c for c in res.changes if c.start == start and c.end == end), None)
        s = start + shift
        shift += len(new) - (end - start)
        if ch is None or not ch.cells:
            continue
        periods = {by_id[x].period for x in ch.cells if x in by_id}
        tail = re.split(r"[,;]|\.\s*$|\.\s+[A-Z]|\bto\b|\band\b", final.text[s + len(new): s + len(new) + 40])[0]
        if re.match(r"\s*\)", tail):
            continue  # a figure in brackets: the year after them is the sentence's ("(X thousand) from 2025 to 2026")
        years = years_in(tail) or [p for p in [normalise_period(tail)] if p]  # also "FY25", which years_in skips
        if len(periods) == 1 and years and years[0] not in periods:
            out.append(f"{UNTRUSTED} {new} is the {next(iter(periods))} figure, but the sentence says {years[0]}.")
            break

    # the released text read again: whose figures it gives, and from which columns
    rdet = detect(item.model_copy(update={"answer": item.answer.model_copy(update={"text": final.text})}))
    vocab = Vocabulary(item.evidence.cells())
    asked = vocab.entity_in(_singular(item.question.text))
    given = {e for c in rdet.checks if c.verdict == "supported" and (e := _entity_of(c, by_id))}
    written = {by_id[x].entity for ch in res.changes for x in ch.cells if x in by_id} - {None}
    if asked and given and asked not in given and written - {asked}:
        other = sorted(written - {asked})[0]
        said = re.search(rf"\b(?:the\s+)?{ENTITY_WORD.get(other, other)}\b", text, re.I)
        out.append(f"{UNTRUSTED} FaithGuard changed the figure to the {ENTITY_WORD.get(other, other)}'s "
                   + (f"because the answer says “{said.group(0)}”" if said else f"because it read the answer as about the {ENTITY_WORD.get(other, other)}")
                   + f", but the question asks about the {ENTITY_WORD.get(asked, asked)} (a known limitation).")
    kept = [c for c in det.claims if c.id not in {ch.claim_id for ch in res.changes} and det.check(c.id).verdict == "supported"]
    for ch in res.changes:
        entities = {by_id[x].entity for x in ch.cells if x in by_id} - {None}
        old = claims.get(ch.claim_id)
        if len(entities) != 1 or old is None:
            continue
        bounds = sentence_bounds(text, old.start)
        beside = {e for c in kept if sentence_bounds(text, c.start) == bounds and (e := _entity_of(det.check(c.id), by_id))}
        named = {ENTITY_WORDS[w] for w in re.findall(r"[a-z]+", text[slice(*bounds)].lower()) if w in ENTITY_WORDS}
        if beside and not entities & beside and len(named) <= 1:  # not "the Group's ... and the Company's ..."
            e, o = ENTITY_WORD.get(next(iter(entities)), "other"), ENTITY_WORD.get(sorted(beside)[0], "other")
            out.append(f"{UNTRUSTED} the fix puts the {e}'s figure ({ch.new}) beside the {o}'s in one sentence. FaithGuard checks "
                       "each figure on its own, not that the figures of a sentence belong together (a known limitation).")
            break
    behind = {x for c in det.claims for x in (next((ch.cells for ch in res.changes if ch.claim_id == c.id), None)
                                              or ([] if _loose(det.check(c.id)) else det.check(c.id).cells))}
    if any("restated" in (by_id[x].column_label or "").lower() for x in behind if x in by_id):
        out.append(RESTATED)
    for phrase, part in _bad_wording(text, det, res.replacements):
        out.append(f"{WORDING} the frozen executor swapped the direction word but not {part}, so the sentence reads “{phrase}”; "
                   "the figure is what was checked (a known limitation).")
        break
    return out


def _unit(c) -> Decimal:
    """Half of this is the rounding a printed figure carries: 1 in its last digit, at its scale."""
    return Decimal(1).scaleb(-c.decimals) * (Decimal(10) ** c.scale if c.kind == "amount" else 1)


def _restates(text: str, a, b) -> bool:
    """Whether b, in brackets right after a, gives the same figure again: "Rs. 38,702,406 (38,702,406 thousand)",
    "Rs. 65,925,260 thousand (about Rs. 65.9 billion)"."""
    if not re.fullmatch(r"\s*\(\s*(?:about|approximately|approx\.?|around|roughly|or|i\.e\.,?)?\s*", text[a.end:b.start], re.I):
        return False
    return re.sub(r"\D", "", a.text) == re.sub(r"\D", "", b.text) or abs(a.value - b.value) <= max(_unit(a), _unit(b)) / 2


_EARLIER_AFTER = re.compile(r"^[\s,]*(?:a\s+year\s+(?:earlier|before|ago)|(?:in\s+)?the\s+(?:prior|previous|preceding)\s+year|last\s+year)\b",
                            re.I)


def _meant_year(text: str, claims: list, index: int, read: str | None, item: Item) -> tuple[str | None, bool]:
    """(the year the answer gives a figure that has no year of its own, whether the answer says it). Said: "a year
    earlier", or the column of a year-headed table. Not said: the year the question asks about. (None, False) else."""
    claim = claims[index]
    s_start, s_end = sentence_bounds(text, claim.start)
    end = claims[index + 1].start if index + 1 < len(claims) else s_end
    if read and read.isdigit() and _EARLIER_AFTER.match(text[claim.end:min(end, s_end)]):
        return str(int(read) - 1), True
    line_start = text.rfind("\n", 0, claim.start) + 1
    column = text[line_start:claim.start].count("|")
    header = next((line for line in text[:line_start].splitlines() if line.count("|") >= 2 and years_in(line)), None)
    if column and header:  # a markdown table: the year in the header cell above
        cells = header.split("|")
        year = years_in(cells[column]) if column < len(cells) else []
        return (year[0], True) if year and year[0] != read else (None, False)
    asked = item.question.period or max(years_in(item.question.text), default=None)
    return (asked, False) if asked and asked != read else (None, False)


_NOUN_OPPOSITE = {"decline": "growth", "drop": "rise"}  # the executor writes the verb ("grow", "rose") for these nouns


def _direction_words(text: str, det: DetectorOutput, replacements: list) -> list[tuple]:
    """For each direction word the executor swapped: (its word, the grammatical word, the article before it, the
    replacements that write it grammatically). "a decline of" -> the executor's "a grow of", grammatically "a growth of";
    "an increase" -> "an decrease", grammatically "a decrease"."""
    spans = {tuple(c.direction_span) for c in det.claims if c.direction_span}
    out = []
    for s, e, new in replacements:
        if (s, e) not in spans:
            continue
        old = text[s:e]
        article = re.search(r"\b(an?|the)\s+$", text[:s], re.I)
        noun = bool(article) or bool(re.match(r"\s+(?:of|in)\b", text[e:], re.I))
        word = _match_case(_NOUN_OPPOSITE[old.lower()], old) if noun and old.lower() in _NOUN_OPPOSITE else new
        fixes = [(s, e, word)]
        if article and article.group(1).lower() in ("a", "an"):
            want = "an" if word[:1].lower() in "aeiou" else "a"
            if want != article.group(1).lower():
                fixes.append((article.start(1), article.end(1), _match_case(want, article.group(1))))
        out.append((new, word, article, fixes, bool(re.match(r"\s+of\b", text[e:], re.I))))
    return out


def _bad_wording(text: str, det: DetectorOutput, replacements: list) -> list[tuple[str, str]]:
    """(what the released sentence reads, what the executor left) for each direction word it swapped ungrammatically."""
    out = []
    for new, word, article, fixes, of in _direction_words(text, det, replacements):
        before = f"{article.group(1)} " if article else ""
        if word != new:
            out.append((f"{before}{new}{' of' if of else ''}", "its noun"))
        elif len(fixes) > 1:
            out.append((f"{before}{new}", "the article before it"))
    return out


def _tidy(text: str, det: DetectorOutput, replacements: list) -> list:
    """The executor's replacements with each swapped direction word written grammatically (for planted errors, which
    are the demo's own text; a released answer is the frozen executor's and is never rewritten)."""
    words = _direction_words(text, det, replacements)
    swapped = {tuple(fixes[0][:2]) for *_, fixes, _ in words}
    return [r for r in replacements if tuple(r[:2]) not in swapped] + [fix for *_, fixes, _ in words for fix in fixes]


CONTRADICTION = "The sentence contradicts itself:"


def contradictions(text: str | None, det: DetectorOutput) -> list[str]:
    """Sentences whose growth rate does not fit their own two figures of the same line item ("decreased 12.4% from
    Rs. 1.14 to Rs. 1.78"), or whose direction word does not fit the move from one figure to the other ("grew ... from
    $192,192 thousand to $150,287 thousand"). The gate checks each number against the report, not whether the numbers of
    one sentence agree, so a repair can put one entity's rate beside another entity's figures, or swap the years of a
    from-to pair (a known limitation); the demo says so."""
    if not text:
        return []
    out = []
    unchecked = ("FaithGuard checks each number against the report, not whether the numbers of one sentence agree with each "
                 "other (a known limitation).")
    by_sentence: dict[tuple[int, int], list] = {}
    for claim in det.claims:
        by_sentence.setdefault(sentence_bounds(text, claim.start), []).append(claim)
    for claims in by_sentence.values():
        rates = [c for c in claims if c.kind == "percent"]
        amounts = [c for c in claims if c.kind == "amount"]
        if len(rates) == 1 and len(amounts) == 2 and all(c.value for c in amounts):
            rate, (a, b) = rates[0], amounts
            if a.value == b.value and rate.value and re.search(r"\bfrom\b", text[min(a.start, b.start) - 12:max(a.end, b.end)], re.I):
                # "grew by 21.4% ... from $503.6 million to $503.6 million": a rate from a figure to itself
                out.append(f"{CONTRADICTION} “{rate.text}” cannot be the change from {a.text} to the same figure {b.text}. {unchecked}")
                continue
            metrics = {det.check(c.id).intended.metric for c in amounts}
            if len(metrics) == 1 and None not in metrics and all(det.check(c.id).verdict == "supported" for c in amounts):
                order = _order(text, det, a, b)  # the earlier year is the base, whatever order the sentence gives them in
                if not any(_rate_fits(rate, base, new) for base, new in ([order] if order else [(a, b), (b, a)])):
                    base, new = order or (a, b)
                    g = ops.growth(new.value, base.value)
                    out.append(f"{CONTRADICTION} “{rate.text}” does not fit its own figures (from {base.text} to {new.text} is a "
                               f"{'rise' if g >= 0 else 'fall'} of {render(abs(g), _percent_style(g))}). {unchecked}")
                continue
        pair = _from_to(text, det, amounts)
        if pair is None:
            continue
        base, new = pair
        words = [c for c in claims if c.direction and c not in pair] or [c for c in pair if c.direction]
        if words and new.value != base.value and (words[0].direction == "up") == (new.value < base.value):
            out.append(f"{CONTRADICTION} it says “{text[slice(*words[0].direction_span)]}”, but from {base.text} to {new.text} "
                       f"is a {'fall' if new.value < base.value else 'rise'}. {unchecked}")
    return out


def _order(text: str, det: DetectorOutput, a, b) -> tuple | None:
    """(base, new) of two figures of one line: by the years the checker read for them, else by "from"; None if unknown."""
    pa, pb = det.check(a.id).intended.period, det.check(b.id).intended.period
    if pa and pb and pa != pb:
        return (a, b) if pa < pb else (b, a)
    if re.search(r"\bfrom\s*$", text[max(0, a.start - 8):a.start], re.I):
        return a, b
    if re.search(r"\bfrom\s*$", text[max(0, b.start - 8):b.start], re.I):
        return b, a
    return None


def _from_to(text: str, det: DetectorOutput, amounts: list) -> tuple | None:
    """(base, new) for "from A ... to B" (or "to B ... from A") in one sentence, two positive figures of one line."""
    def after(word, c):  # not "compared to"
        return re.search(rf"(?<!compared )\b{word}\s*$", text[max(0, c.start - 20):c.start], re.I)

    base = next((c for c in amounts if after("from", c)), None)
    new = next((c for c in amounts if after("to", c) and c is not base), None)
    if base is None or new is None or base.value <= 0 or new.value <= 0:
        return None
    checks = [det.check(c.id) for c in (base, new)]
    if all(k.verdict == "supported" for k in checks) and checks[0].intended.metric != checks[1].intended.metric:
        return None  # figures of two lines
    return base, new


def _rate_fits(rate, base, new) -> bool:
    """Whether the stated rate, give or take its last printed digit, is a growth rate the two printed figures allow, each
    give or take half of its own last digit: "from Rs. 59.3 billion to Rs. 65.9 billion, up 11.2%" fits (11.0 to 11.3%)."""
    low, high = base.value - _unit(base) / 2, new.value - _unit(new) / 2
    if low <= 0:
        return True  # a base that rounds to nothing: nothing to say
    g_low = (high / (base.value + _unit(base) / 2) - 1) * 100
    g_high = ((new.value + _unit(new) / 2) / low - 1) * 100
    slack = Decimal(1).scaleb(-rate.decimals) * Decimal("0.6")
    r = abs(rate.value)
    if rate.direction is not None or rate.value < 0:
        signed = -r if rate.direction == "down" or (rate.direction is None and rate.value < 0) else r
        return signed - slack <= g_high and signed + slack >= g_low
    return any(s - slack <= g_high and s + slack >= g_low for s in (r, -r))  # "changed by 2.5%": either way


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
    """The answer with the edits applied by the executor, its swapped direction words written grammatically."""
    try:
        res = execute(item, det.claims, EditProgram(edits=edits))
    except (ExecError, KeyError, ValueError, ops.CalcError):
        return None
    text = apply(item.answer.text, _tidy(item.answer.text, det, res.replacements))
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
