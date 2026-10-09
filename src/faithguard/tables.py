"""Turn a raw table grid (rows of strings) into a Table of typed, context-labelled cells.

Handles the shapes seen in FinQA, TAT-QA and annual reports: several header rows,
years in the column headers or in the row labels, scale notes such as
"(in millions)" or "Rs. '000", Group/Bank/Company columns, section rows with no
numbers, and FinQA's "-0.3 ( 0.3 )" negatives.
"""

from __future__ import annotations

import re
from decimal import Decimal

from faithguard.calc.numbers import NumberMention, detect_scale, find_numbers, parse_number
from faithguard.records import Cell, Table

ENTITY_WORDS = {
    "group": "group",
    "consolidated": "group",
    "bank": "bank",
    "company": "company",
    "parent": "company",
    "standalone": "company",
}

_YEAR = re.compile(r"(?<!\d)(?:FY\s?)?((?:19|20)\d{2})(?:\s?[/-]\s?(\d{2,4}))?(?!\d)", re.IGNORECASE)
_SHORT_FY = re.compile(r"\bFY\s?(\d{2})\b", re.IGNORECASE)
_FINQA_NEGATIVE = re.compile(r"^\s*(-?[\d.,]+)\s*\(\s*[\d.,]+\s*\)\s*$")
_PERIOD_WORDS = {"", "fiscal", "year", "fy", "fiscal year", "year ended", "years ended", "as at", "as of"}
_UNIT_MARKER = re.compile(r"^(?:Rs\.?|LKR|SLR|USD|US\$|\$)?\s?['’]?000$", re.IGNORECASE)  # "Rs 000", "Rs.'000"
_PER_SHARE = re.compile(r"per (?:common |ordinary )?share|\beps\b|\(cents|\bcents\b|\bdividend per\b", re.IGNORECASE)
_SECTION_ONLY = {"basic", "diluted", "basic and diluted"}  # row labels that mean nothing without their section


def normalise_period(text: str) -> str | None:
    """The fiscal year a label refers to: 'FY2025' -> '2025', '2024/25' -> '2025', 'Dec 31, 2019' -> '2019'."""
    found = list(_YEAR.finditer(text))
    if found:
        m = found[-1]
        first, second = m.group(1), m.group(2)
        if second:
            year = int(second) + (2000 if len(second) == 2 else 0)
            if year > int(first):
                return str(year)
        return first
    short = _SHORT_FY.search(text)
    return f"20{short.group(1)}" if short else None


def normalise_metric(text: str) -> str:
    t = text.lower()
    t = re.sub(r"\([^)]*\)|\bnote\s+\d+\b", " ", t)  # footnote markers, notes, "(in millions)"
    t = re.sub(r"(?<!\d)(?:fy\s?)?(?:19|20)\d{2}(?:\s?[/-]\s?\d{2,4})?(?!\d)", " ", t)  # years belong in the period
    t = re.sub(r"[^a-z0-9&%' ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def entity_of(text: str) -> str | None:
    words = re.findall(r"[a-z]+", text.lower())
    for w in words:
        if w in ENTITY_WORDS:
            return ENTITY_WORDS[w]
    return None


def parse_table_cell(text: str) -> NumberMention | None:
    """A cell's number, if it holds exactly one (FinQA's '-0.3 ( 0.3 )' counts as one)."""
    t = text.strip().replace("$ ", "$").replace("( ", "(").replace(" )", ")")
    if t.lower() in ("", "-", "—", "–", "n/a", "nil", "none") or _UNIT_MARKER.match(t):
        return None
    fin = _FINQA_NEGATIVE.match(text)
    if fin:
        return parse_number(fin.group(1))
    return parse_number(t)


def _numeric(text: str) -> bool:
    m = parse_table_cell(text)
    return m is not None and m.kind != "year"


def is_header_row(row: list[str]) -> bool:
    """True if no cell after the label holds a number (years and units are not numbers here)."""
    return not any(_numeric(c) for c in row[1:])


def table_from_grid(
    table_id: str,
    grid: list[list[str]],
    title: str = "",
    scale: int | None = None,
    currency: str | None = None,
    entity: str | None = None,
    page: int | None = None,
    source: str | None = None,
) -> Table:
    """Build a Table. `table_id` must be a short identifier such as 't1'; cell ids are '<table>r<row>c<col>'.

    Row numbers are the grid's own row indices (blank rows included), so dataset
    references such as FinQA's 'table_3' map straight to cell ids.
    """
    rows = [[str(c).strip() for c in r] for r in grid]
    width = max((len(r) for r in rows), default=0)
    rows = [r + [""] * (width - len(r)) for r in rows]

    n_header, n_text_rows = 0, 0
    while n_header < len(rows) and is_header_row(rows[n_header]) and n_text_rows < 4:
        n_text_rows += any(rows[n_header])  # blank rows do not count towards the limit
        n_header += 1
    if n_header == len(rows):  # a table with no numbers at all
        n_header = 1 if rows else 0
    headers = rows[:n_header]
    body = rows[n_header:]
    column_labels = [" ".join(h[c] for h in headers if h[c]).strip() for c in range(width)]

    header_text = title + " " + " ".join(" ".join(h) for h in headers)
    table_scale = scale if scale is not None else detect_scale(header_text)
    column_periods = [normalise_period(label) for label in column_labels]
    # Transposed tables have periods as row labels ("2019", "Fiscal 2018"), not "2009 net revenue".
    pure_period_rows = [
        normalise_period(r[0]) is not None and normalise_metric(r[0]) in _PERIOD_WORDS for r in body
    ]
    transposed = not any(column_periods[1:]) and sum(pure_period_rows) >= 2

    cells: list[Cell] = []
    section = ""  # the last label row with no numbers; unlabelled data rows below it inherit it
    for r, row in enumerate(body, start=n_header):
        row_label = row[0]
        if row_label and not any(row[1:]):
            section = row_label
        metric_source = row_label or section
        per_share = bool(_PER_SHARE.search(metric_source))
        if section and row_label.lower().rstrip(":").strip() in _SECTION_ONLY:
            per_share = per_share or bool(_PER_SHARE.search(section))  # "Basic" under "Earnings per share:"
        for c in range(1, width):
            text = row[c]
            if not text:
                continue
            mention = parse_table_cell(text)
            column_label = column_labels[c]
            if mention is None or mention.kind == "year":
                kind, raw, cell_scale, cell_currency = "text", None, 0, None
            else:
                kind = mention.kind if mention.kind != "year" else "number"
                if kind == "number":
                    kind = "amount"  # numbers in financial tables are amounts in the table's unit
                raw = mention.raw
                # per-share figures are in currency units, never in the table's thousands or millions
                cell_scale = mention.scale or (table_scale if kind == "amount" and not per_share else 0)
                cell_currency = mention.currency or currency
            if kind == "amount" and ("%" in column_label or re.search(r"%|\bper ?cent\b", metric_source)):
                kind, cell_scale = "percent", 0
            if transposed:
                metric_label, period = column_label, normalise_period(row_label)
            else:
                metric_label = metric_source
                period = column_periods[c] or normalise_period(row_label)
            cells.append(
                Cell(
                    id=f"{table_id}r{r}c{c}",
                    table_id=table_id,
                    row=r,
                    col=c,
                    row_label=row_label,
                    column_label=column_label,
                    text=text,
                    raw=raw,
                    kind=kind,
                    scale=cell_scale,
                    currency=cell_currency,
                    metric=normalise_metric(metric_label) or None,
                    entity=entity_of(column_label) or entity_of(row_label) or entity,
                    period=period,
                )
            )
    return Table(
        id=table_id, title=title, page=page, source=source, scale=table_scale, currency=currency, cells=cells
    )


def cells_matching(cells: list[Cell], value: Decimal, tolerance: Decimal = Decimal("0")) -> list[Cell]:
    """Cells whose printed number equals `value` (used to map program operands back to cells)."""
    return [c for c in cells if c.raw is not None and abs(c.raw - value) <= tolerance]


def numbers_in(text: str) -> list[NumberMention]:
    return find_numbers(text, include_years=False)
