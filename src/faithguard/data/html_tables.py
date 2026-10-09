"""Reading financial statement tables from 10-K HTML documents (SEC EDGAR).

A 10-K's tables are real HTML tables, but laid out for print: a dollar sign, a
number and a closing bracket often sit in cells of their own, spacer cells separate
the year columns, and headers such as "Year Ended December 31," span several
columns. This reader:

1. lays every row out on the table's own column grid (colspans expanded);
2. finds the number columns from where numbers end, as a printed table aligns them
   on the right; a separate "$" is dropped and a separate ")" or "%" is joined to
   its number;
3. gives each number column the header text above it (spanning headers included)
   and puts the unit line, such as "(in thousands, except per share data)", in the
   first column;
4. drops blank rows and keeps section rows such as "Operating expenses:".

The result is a grid in the benchmark CSV layout. Like the PDF reader, it is a
first draft: check every table against the filing before writing questions on it.

    python -m faithguard.data.html_tables REPORT.htm list [PATTERN]
    python -m faithguard.data.html_tables REPORT.htm extract INDEX OUT.csv
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from html.parser import HTMLParser

NUMBER = re.compile(r"^\(?\$?\s?-?[\d,]*\d(\.\d+)?\)?%?$|^[-–—]+$")
YEAR = re.compile(r"^(19|20)\d{2}$")
UNIT_LINE = re.compile(r"(?i)\b(in (thousands|millions|billions)|amounts in|dollars in|except (per[- ]share|share))")


@dataclass
class HtmlTable:
    index: int
    caption: list[str]  # the last few text blocks before the table, nearest last
    rows: list[list[tuple[int, int, str]]] = field(default_factory=list)  # (start, end, text) per cell

    @property
    def title(self) -> str:
        return self.caption[-1] if self.caption else ""


class _Reader(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tables: list[HtmlTable] = []
        self.blocks: list[str] = []
        self.text: list[str] = []
        self.depth = 0
        self.row: list[tuple[int, int, str]] | None = None
        self.cell: list[str] | None = None
        self.colspan = 1
        self.position = 0
        self.hidden: list[str] = []  # open tags of a display:none element (the inline XBRL header)

    def handle_starttag(self, tag, attrs):
        style = (dict(attrs).get("style") or "").replace(" ", "").lower()
        if self.hidden or "display:none" in style:
            self.hidden.append(tag)
            return
        if tag == "table":
            self.depth += 1
            if self.depth == 1:
                self._flush()
                self.tables.append(HtmlTable(len(self.tables), self.blocks[-4:]))
        elif self.depth == 1 and tag == "tr":
            self.row, self.position = [], 0
        elif self.depth == 1 and tag in ("td", "th") and self.row is not None:
            self.cell = []
            try:
                self.colspan = max(1, int(dict(attrs).get("colspan") or 1))
            except ValueError:
                self.colspan = 1
        elif tag == "br":
            (self.cell if self.cell is not None else self.text).append(" ")
        elif self.depth == 0 and tag in ("p", "div"):
            self._flush()

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == "table" and self.depth:
            self.depth -= 1
        elif self.depth == 1 and tag in ("td", "th") and self.cell is not None and self.row is not None:
            text = re.sub(r"\s+", " ", "".join(self.cell)).strip()
            self.row.append((self.position, self.position + self.colspan, text))
            self.position += self.colspan
            self.cell = None
        elif self.depth == 1 and tag == "tr" and self.row is not None:
            self.tables[-1].rows.append(self.row)
            self.row = None
        elif self.depth == 0 and tag in ("p", "div"):
            self._flush()

    def handle_data(self, data):
        if self.hidden:
            return
        if self.cell is not None:
            self.cell.append(data)
        elif self.depth == 0:
            self.text.append(data)

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.text)).strip()
        if text:
            self.blocks.append(text)
        self.text = []


def read_tables(html: str) -> list[HtmlTable]:
    reader = _Reader()
    reader.feed(html)
    reader.close()
    return reader.tables


def _is_number(text: str) -> bool:
    return bool(NUMBER.match(text)) and not YEAR.match(text)


def _join_pieces(row: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Drop lone '$' cells and empty cells; join a lone ')' or '%' to the number before it."""
    out: list[tuple[int, int, str]] = []
    for start, end, text in row:
        if not text or text == "$":
            continue
        if text in (")", "%", ")%") and out and re.search(r"\d$", out[-1][2]):
            prev_start, prev_end, prev = out[-1]
            out[-1] = (prev_start, prev_end, prev + text)  # the number keeps its own right edge
            continue
        out.append((start, end, text.replace("$ ", "").replace("$", "") if _is_number(text) else text))
    return out


def to_grid(table: HtmlTable) -> list[list[str]]:
    """The table in the benchmark CSV layout: header rows, then one row per line item."""
    rows = [_join_pieces(r) for r in table.rows]
    rows = [r for r in rows if r]
    numeric_rows = [i for i, r in enumerate(rows) if any(_is_number(t) and s > 0 for s, _, t in r)]
    if not numeric_rows:
        return []
    first_body = numeric_rows[0]
    edges = sorted({e for r in rows[first_body:] for s, e, t in r if s > 0 and _is_number(t)})
    # nearby edges belong to one column when no row has numbers at both
    columns: list[int] = []
    for e in edges:
        if columns and all(not ({columns[-1], e} <= {x for s, x, t in r if s > 0 and _is_number(t)}) for r in rows):
            if e - columns[-1] <= 2:
                columns[-1] = e
                continue
        columns.append(e)

    def column_of(end: int) -> int | None:
        best = min(range(len(columns)), key=lambda k: abs(columns[k] - end))
        return best if abs(columns[best] - end) <= 2 else None

    grid: list[list[str]] = []
    unit = ""
    for i, row in enumerate(rows):
        line = [""] * (len(columns) + 1)
        if i < first_body:  # header rows: spanning text goes to every number column it covers
            for start, end, text in row:
                if UNIT_LINE.search(text) and not unit:
                    unit = text
                    continue
                covered = [k for k, c in enumerate(columns) if start < c <= end]
                if start == 0 and not covered:
                    line[0] = text
                for k in covered:
                    line[k + 1] = text
            if any(line):
                grid.append(line)
            continue
        label = []
        for start, end, text in row:
            if start > 0 and _is_number(text) and (k := column_of(end)) is not None:
                line[k + 1] = text
            elif start > 0 and (covered := [k for k, c in enumerate(columns) if start < c <= end]):
                for k in covered:  # words in number columns ("n/m", a repeated year header)
                    line[k + 1] = text
            else:
                label.append(text)
        line[0] = " ".join(label)
        grid.append(line)
    if not unit:  # often printed just above the table, under its title
        unit = next((b for b in reversed(table.caption[-2:]) if UNIT_LINE.search(b) and len(b) < 80), "")
    if unit:
        if grid and not grid[0][0]:
            grid[0][0] = unit
        else:
            grid.insert(0, [unit] + [""] * len(columns))
    return grid


def list_tables(html: str, pattern: str = "") -> list[tuple[int, str, int, int]]:
    """(index, title, rows, number columns) of every table with numbers, optionally filtered by title."""
    found = []
    for table in read_tables(html):
        grid = to_grid(table)
        title = " | ".join(table.caption[-2:])
        if grid and re.search(pattern, title, re.IGNORECASE):
            found.append((table.index, title, len(grid), len(grid[0]) - 1))
    return found


def extract(path: str, index: int) -> list[list[str]]:
    with open(path, encoding="utf-8", errors="replace") as f:
        tables = read_tables(f.read())
    return to_grid(tables[index])


def main(argv: list[str] | None = None) -> None:
    import argparse
    import csv
    from pathlib import Path

    parser = argparse.ArgumentParser(description="List or read the tables of a 10-K HTML document into draft benchmark CSVs.")
    parser.add_argument("report")
    sub = parser.add_subparsers(dest="action", required=True)
    p = sub.add_parser("list")
    p.add_argument("pattern", nargs="?", default="", help="regular expression on the text before each table")
    p = sub.add_parser("extract")
    p.add_argument("index", type=int, help="table number from `list`")
    p.add_argument("csv", help="where to write the table, e.g. data/benchmark/US/MEDP/2025/t1.csv")
    args = parser.parse_args(argv)
    if args.action == "list":
        html = Path(args.report).read_text(encoding="utf-8", errors="replace")
        for index, title, n_rows, n_cols in list_tables(html, args.pattern):
            print(f"{index:4}  {n_rows:3} rows x {n_cols} columns  {title[:110]}")
        return
    grid = extract(args.report, args.index)
    if not grid:
        raise SystemExit(f"table {args.index} has no numbers")
    out = Path(args.csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="") as f:
        csv.writer(f, lineterminator="\n").writerows(grid)
    print(f"{out}: {len(grid)} rows x {len(grid[0]) - 1} columns. A draft: compare every row with the filing.")


if __name__ == "__main__":
    main()
