"""Reading financial statement tables from annual report PDFs by word position.

Statements in annual reports are laid out in right-aligned number columns under
entity and year headers, and printers often shift a column's figures a few points
up or down from the row label, so reading line by line splits rows apart. This
reader instead:

1. finds the number columns from the right edges of numbers, and drops the
   note-reference column (short integers left of the first column of amounts);
2. reads the header lines (entity, year, unit) above the first amount, giving a
   spanning header such as "Group" to every column under it;
3. attaches every number to the nearest row label; numbers with no label nearby
   (unlabelled subtotals) get a row of their own;
4. joins labels that wrap onto a second line.

The result is a grid in the benchmark CSV layout: header rows, then one row per
line item, numbers exactly as printed. It is a first draft only: every table must
still be checked against the page before questions are written on it.
Needs PyMuPDF (`pip install pymupdf`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from statistics import median

NUMBER = re.compile(r"^\(?-?[\d,]+(\.\d+)?\)?%?\*?$|^[-–—]$")  # "10.30*" carries a footnote mark
YEAR = re.compile(r"^(19|20)\d{2}(/\d{2})?$")
NOTE_REF = re.compile(r"^\d{1,2}(\.\w{1,2})*$")  # "9", "11.2", "9.B"
UNIT_000 = re.compile(r"^'?000$")  # the "000" of "Rs 000" is a unit, not a value
ENTITIES = {"group", "company", "bank", "consolidated"}


@dataclass
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2


def _words(page) -> list[Word]:
    clean = {"�": "'", "’": "'", "‘": "'"}
    out = []
    for x0, y0, x1, y1, text, *_ in page.get_text("words"):
        for a, b in clean.items():
            text = text.replace(a, b)
        out.append(Word(x0, y0, x1, y1, text))
    return out


def _cluster(values: list[float], gap: float) -> list[list[float]]:
    groups: list[list[float]] = []
    for v in sorted(values):
        if groups and v - groups[-1][-1] <= gap:
            groups[-1].append(v)
        else:
            groups.append([v])
    return groups


def _lines(words: list[Word], gap: float = 2.5) -> list[list[Word]]:
    """Words grouped into text lines by vertical centre, top to bottom, each left to right."""
    lines: list[list[Word]] = []
    for w in sorted(words, key=lambda w: w.yc):
        if lines and w.yc - lines[-1][-1].yc <= gap:
            lines[-1].append(w)
        else:
            lines.append([w])
    return [sorted(line, key=lambda w: w.x0) for line in lines]


def _is_number(text: str) -> bool:
    return bool(NUMBER.match(text)) and not YEAR.match(text) and not UNIT_000.match(text)


def _y(line: list[Word]) -> float:
    return sum(w.yc for w in line) / len(line)


def extract_page(page, label_gap: float = 9.0, min_column_hits: int = 3) -> list[list[str]]:
    height = page.rect.height
    words = [w for w in _words(page) if 0.04 * height < w.yc < 0.95 * height]  # no running headers or page numbers
    numbers = [w for w in words if _is_number(w.text)]
    if not numbers:
        return []

    # 1. number columns
    clusters = _cluster([w.x1 for w in numbers], gap=12.0)
    biggest = max(len(c) for c in clusters)
    clusters = [c for c in clusters if len(c) >= max(min_column_hits, 0.3 * biggest)]
    anchors = [sum(c) / len(c) for c in clusters]

    def column_of(w: Word) -> int | None:
        best = min(range(len(anchors)), key=lambda i: abs(anchors[i] - w.x1))
        return best if abs(anchors[best] - w.x1) <= 12 else None

    members = [[w for w in numbers if column_of(w) == i] for i in range(len(anchors))]
    amounts = [i for i, m in enumerate(members) if m and sum("," in w.text for w in m) >= 0.5 * len(m)]
    if not amounts:
        return []
    first = amounts[0]
    note_cols = [
        i for i in range(first)
        if anchors[first] - anchors[i] < 150 and sum(bool(NOTE_REF.match(w.text)) for w in members[i]) >= 0.8 * len(members[i])
    ]
    value_cols = list(range(first, len(anchors)))
    columns = note_cols + value_cols
    centres = {i: median(w.xc for w in members[i]) for i in columns}
    label_right = min(w.x0 for i in value_cols for w in members[i]) - 1  # labels may run past the note column's left edge

    def nearest(x: float) -> int:
        return min(columns, key=lambda i: abs(centres[i] - x))

    # 2. header lines: the line with the most years, the lines just above it, and the lines down to the first amount
    top_value_y = min(w.yc for i in value_cols for w in members[i])
    above = _lines([w for w in words if w.yc < top_value_y - 2 and w.x1 > label_right])
    year_lines = [line for line in above if any(YEAR.match(w.text) for w in line)]
    if year_lines:
        year_line = max(year_lines, key=lambda line: (sum(bool(YEAR.match(w.text)) for w in line), _y(line)))
        header = [line for line in above if _y(line) >= _y(year_line)]
        for line in reversed([line for line in above if _y(line) < _y(year_line)]):
            if _y(header[0]) - _y(line) > 16:
                break
            header.insert(0, line)
    else:
        header = above[-2:]
    grid: list[list[str]] = []
    for line in header:
        y = _y(line)
        cells = {i: "" for i in columns}
        entities = [w for w in line if w.text.lower().strip(":") in ENTITIES]
        if entities:  # spanning entity headers: each column takes the nearest one
            for i in columns:
                cells[i] = min(entities, key=lambda w: abs(w.xc - centres[i])).text
        else:
            for w in line:
                i = nearest(w.xc)
                cells[i] = f"{cells[i]} {w.text}".strip()
        left = " ".join(
            w.text for w in sorted(words, key=lambda w: w.x0)
            if abs(w.yc - y) <= 2.5 and w.x1 <= label_right and w.text.lower() not in ("note", "notes")
        )
        grid.append([left] + [cells[i] for i in value_cols])

    # 3. rows: label lines, then numbers attached to the nearest label line
    body_top = (max(_y(line) for line in header) if header else top_value_y - 10) + 2.5
    label_words = [
        w for w in words
        if w.x1 <= label_right and w.yc > body_top and not (NOTE_REF.match(w.text) and w.x1 > label_right - 40)
    ]
    rows = [{"y": _y(line), "label": " ".join(w.text for w in line), "values": {}} for line in _lines(label_words)]
    leftovers: list[tuple[Word, int]] = []
    for w in numbers:
        col = column_of(w)
        if col is None or col not in value_cols or w.yc <= body_top:
            continue
        candidates = [r for r in rows if abs(r["y"] - w.yc) <= label_gap and col not in r["values"]]
        if candidates:
            min(candidates, key=lambda r: abs(r["y"] - w.yc))["values"][col] = w.text
        else:
            leftovers.append((w, col))
    for line in _cluster([w.yc for w, _ in leftovers], gap=4.0):
        y = sum(line) / len(line)
        row = {"y": y, "label": "", "values": {}}
        for w, col in leftovers:
            if abs(w.yc - y) <= 4.0 and col not in row["values"]:
                row["values"][col] = w.text
        rows.append(row)
    rows.sort(key=lambda r: r["y"])

    # 4. wrapped labels: a label line whose numbers sit on the next line, or a label continued in lower case
    merged: list[dict] = []
    for r in rows:
        prev = merged[-1] if merged else None
        if prev and prev["label"] and not prev["values"] and not r["label"] and r["values"]:
            prev["values"] = r["values"]
            continue
        if prev and prev["label"] and r["label"][:1].islower() and not (prev["values"] and r["values"]):
            prev["label"] = f"{prev['label']} {r['label']}"
            prev["values"] = prev["values"] or r["values"]
            continue
        merged.append(r)
    while merged and not merged[-1]["values"]:  # page footers below the table
        merged.pop()
    grid += [[r["label"]] + [r["values"].get(c, "") for c in value_cols] for r in merged]
    return grid


def extract(pdf_path: str, page_number: int) -> list[list[str]]:
    """The table on a page (numbered from 1, as in a PDF viewer)."""
    import pymupdf

    with pymupdf.open(pdf_path) as doc:
        return extract_page(doc[page_number - 1])
