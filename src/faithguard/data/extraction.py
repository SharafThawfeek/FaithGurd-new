"""The automatic-extraction run (phase 3): off-the-shelf PDF table tools against the hand-corrected tables.

The main test uses hand-corrected tables, so table-reading errors cannot be mistaken for model errors.
The real-world condition instead uses tables that a tool extracted with no correction. This module
runs three tools (PyMuPDF, pdfplumber, camelot) with each of their table-finding strategies, cleans
every tool's output the same way, and scores it against the corrected table:

- figures found: the share of the corrected table's figures that come out in the matching row. Rows
  are matched by their labels, in order down the page. A row's figures are compared column by column
  when the tool's row has as many figures, and otherwise in order (an extra or missing column), so a
  figure in the wrong row or the wrong column does not count;
- rows complete: rows whose figures all come out right;
- tables complete: tables with every figure right;
- wrong figures: figures in a matched row that are not the corrected table's (a misread or cut figure), which
  can mislead a checker, where a missing figure only leaves a claim unverifiable.

The pages come from the report files (a person found them), so finding the statement is not tested.
On each page the table with the most figures is kept, and a statement's pages are joined in order.
"""

from __future__ import annotations

import difflib
import re
import time
import warnings
from pathlib import Path

TOOLS: dict[str, tuple[str, ...]] = {  # tool -> its table-finding strategies
    "pymupdf": ("lines", "text"),
    "pdfplumber": ("lines", "text"),
    "camelot": ("lattice", "stream", "network", "hybrid"),
}
FIGURE = re.compile(r"^\(?-?\d[\d,]*(?:\.\d+)?\)?%?\*?$|^\(?-?\.\d+\)?%?$")
NIL = re.compile(r"^[-–—−]+$")
NOTE_REF = re.compile(r"^\(?\d{1,2}(?:\.\d{1,2}){0,2}(?:\s?\(?[a-z]{1,3}\)?)?\)?$")  # "7", "12.1", "13.1(a)"
TRAILING_REF = re.compile(r"(?:\s+\(?\d{1,2}(?:\.\d{1,2}){0,2}(?:\s?\(?[a-z]{1,3}\)?)?\)?)+$")  # "Gross income 7"
REF_WORDS = {"note", "notes", "note no", "page", "page no", "page no."}
YEAR = re.compile(r"^(?:FY)?(?:19|20)\d{2}(?:/\d{2})?\*?$")
LABEL_MATCH = 0.75  # least label similarity for two rows to be the same line item
WINDOW = 12  # how far ahead a row may be found (tools add header and wrapped-label rows)


# -- reading ---------------------------------------------------------------------------------------

def read_pages(pdf: str | Path, pages: list[int], tool: str, strategy: str) -> list[list[list[list[str]]]]:
    """Every candidate table on each page (pages numbered as a PDF viewer shows them), as grids of strings."""
    pdf = str(pdf)
    if tool == "pymupdf":
        import pymupdf

        with pymupdf.open(pdf) as doc:
            return [[t.extract() for t in doc[p - 1].find_tables(strategy=strategy).tables] for p in pages]
    if tool == "pdfplumber":
        import pdfplumber

        settings = {} if strategy == "lines" else {"vertical_strategy": strategy, "horizontal_strategy": strategy}
        with pdfplumber.open(pdf) as doc:
            return [doc.pages[p - 1].extract_tables(table_settings=settings) for p in pages]
    if tool == "camelot":
        import camelot

        out = []
        for p in pages:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # camelot warns on pages where it finds no table
                found = camelot.read_pdf(pdf, pages=str(p), flavor=strategy)
            out.append([t.df.values.tolist() for t in found])
        return out
    raise ValueError(f"unknown tool {tool!r}")


def clean(grid: list[list]) -> list[list[str]]:
    """Text cells with single spaces; empty rows and columns dropped."""
    rows = [[" ".join(str(c if c is not None else "").split()) for c in row] for row in grid]
    rows = [r for r in rows if any(r)]
    if not rows:
        return []
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    keep = [j for j in range(width) if any(r[j] for r in rows)]
    return [[r[j] for j in keep] for r in rows]


def statement(per_page: list[list[list[list[str]]]]) -> list[list[str]]:
    """One grid for a statement: on each page the table with the most figures, pages joined in order."""
    rows: list[list[str]] = []
    for tables in per_page:
        grids = [clean(t) for t in tables]
        grids = [g for g in grids if g]
        if grids:
            rows += max(grids, key=lambda g: sum(len(figs) for _, figs, _ in body_rows(g)))
    width = max((len(r) for r in rows), default=0)
    return [r + [""] * (width - len(r)) for r in rows]


def extract(pdf: str | Path, pages: list[int], tool: str, strategy: str) -> list[list[str]]:
    return statement(read_pages(pdf, pages, tool, strategy))


# -- rows: a label and its figures -----------------------------------------------------------------

def figure(token: str) -> str | None:
    """A printed figure in one form ('(1,234)' -> '-1234'), '-' for a nil, or None if the token is not a figure."""
    t = token.strip().rstrip("*")
    if NIL.match(t):
        return "-"
    if not FIGURE.match(t) or t in ("000", "'000"):
        return None
    negative = t.startswith("(") or t.startswith("-")
    digits = t.strip("()%").lstrip("-").replace(",", "")
    try:
        float(digits)
    except ValueError:
        return None
    return ("-" if negative else "") + digits


def first_value_column(grid: list[list[str]]) -> int:
    """The leftmost column holding a figure with a thousands separator: columns left of it are labels and references."""
    width = max((len(r) for r in grid), default=0)
    for j in range(width):
        if any(j < len(r) and any("," in tok and figure(tok) for tok in r[j].split()) for r in grid):
            return j
    return 1


def rows_of(grid: list[list[str]]) -> list[tuple[str, list[str]]]:
    """Each row as (label, figures). Note and page references are left out; text in a value cell before its figures joins the label."""
    first = first_value_column(grid)
    out = []
    for row in grid:
        label_parts = [c for c in row[:first] if c and not NOTE_REF.match(c) and c.lower().strip(".: ") not in REF_WORDS]
        figures: list[str] = []
        for cell in row[first:]:
            for tok in cell.split():
                f = figure(tok)
                if f is not None:
                    figures.append(f)
                elif not figures:  # text before the row's first figure belongs to the label (labels run into the next column)
                    label_parts.append(tok)
        label = TRAILING_REF.sub("", " ".join(label_parts)).strip()
        out.append((label, figures))
    return out


def is_header(figures: list[str]) -> bool:
    """Header rows hold years and units, not figures."""
    real = [f for f in figures if f != "-"]
    return not real or all(YEAR.match(f) for f in real)


def body_rows(grid: list[list[str]]) -> list[tuple[str, list[str], str]]:
    """Rows with figures, as (label, figures, the labels of the figure-less rows just above: a wrapped label or headings)."""
    out, above = [], ""
    for label, figures in rows_of(grid):
        if is_header(figures):
            above = f"{above}|{label}" if above and label else above or label  # a wrapped label arrives a line at a time
            continue
        out.append((label, figures, above))
        above = ""
    return out


# -- scoring ---------------------------------------------------------------------------------------

def _norm(label: str) -> str:
    return re.sub(r"[^a-z0-9]", "", label.lower())


def _similar(gold_label: str, row: tuple[str, list[str], str]) -> float:
    label, _, above = row
    g = _norm(gold_label)
    if not g:
        return 1.0 if not _norm(label) else 0.0
    lines = above.split("|") if above else []
    texts = [" ".join(lines[len(lines) - k:] + [label]) for k in range(len(lines) + 1)]  # the row, then with 1, 2, ... lines above
    return max(difflib.SequenceMatcher(None, g, _norm(text)).ratio() for text in texts)


def _matched(gold: list[str], got: list[str]) -> int:
    """Gold figures (not nils) matched: column by column when the row has as many figures, else in order."""
    if len(gold) == len(got):  # swapped figures both count as wrong
        return sum(1 for g, e in zip(gold, got) if g == e and g != "-")
    blocks = difflib.SequenceMatcher(None, gold, got, autojunk=False).get_matching_blocks()
    return sum(sum(1 for f in gold[b.a:b.a + b.size] if f != "-") for b in blocks)


def score(gold_grid: list[list[str]], grid: list[list[str]]) -> dict:
    """How much of the corrected table a tool's grid gets right (counts; see the module docstring)."""
    gold = body_rows(gold_grid)
    got = body_rows(grid)
    figures = found = rows = complete = wrong = 0
    used: set[int] = set()
    start = 0
    for label, gold_figs, _ in gold:
        n = sum(1 for f in gold_figs if f != "-")
        if not n:
            continue
        figures += n
        rows += 1
        best, best_key = None, (0.0, 0)
        for k in range(start, min(start + WINDOW, len(got))):
            sim = _similar(label, got[k])
            hits = _matched(gold_figs, got[k][1])
            if (sim >= LABEL_MATCH or not label and hits) and (sim, hits) > best_key:
                best, best_key = k, (sim, hits)
        if best is None:
            continue
        used.add(best)
        start = best + 1
        hits = best_key[1]
        found += hits
        complete += hits == n
        wrong += sum(1 for f in got[best][1] if f != "-") - hits
    spurious = sum(sum(1 for f in got[k][1] if f != "-") for k in range(len(got)) if k not in used)
    return {"figures": figures, "found": found, "rows": rows, "rows_complete": complete,
            "table_complete": figures > 0 and found == figures, "wrong": wrong, "unmatched_rows_figures": spurious}


def timed_extract(pdf: str | Path, pages: list[int], tool: str, strategy: str) -> tuple[list[list[str]], float, str]:
    """The tool's grid, the seconds it took, and the error if it failed (an empty grid then)."""
    t = time.perf_counter()
    try:
        grid = extract(pdf, pages, tool, strategy)
        error = ""
    except Exception as err:  # a tool that crashes on a page scores nothing there; the run goes on
        grid, error = [], f"{type(err).__name__}: {err}"[:200]
    return grid, time.perf_counter() - t, error


# -- the run ---------------------------------------------------------------------------------------

PAGES = re.compile(r"\bt(\d+) pages ([\d, ]+)")
REFERENCE = ("pdf_tables", "project")  # the project's own reader: built on these reports, so a reference, never a candidate


def statement_pages(report: Path) -> dict[str, list[int]]:
    """The PDF pages of each table, from the report file's comment ("t1 pages 334, 335; t2 pages 336")."""
    comment = " ".join(line for line in report.read_text(encoding="utf-8").splitlines() if line.startswith("#"))
    return {f"t{m.group(1)}": [int(p) for p in re.findall(r"\d+", m.group(2))] for m in PAGES.finditer(comment)}


def choose_reports(reports: list[Path], split_of, per_split: int = 5, seed: int = 2026) -> list[Path]:
    """A seeded draw of reports from each of the test and calibration splits."""
    import random

    rng = random.Random(seed)
    chosen: list[Path] = []
    for split in ("test", "calibration"):
        pool = sorted(p for p in reports if split_of(p) == split)
        chosen += sorted(rng.sample(pool, min(per_split, len(pool))))
    return chosen


def run(reports: list[Path], raw_root: Path, tools: dict[str, tuple[str, ...]] = TOOLS, reference: bool = True) -> list[dict]:
    """Score every tool and strategy on both statements of each report (one row per table, tool and strategy)."""
    import yaml

    from faithguard.benchmark import read_grid
    from faithguard.data import pdf_tables

    out = []
    for path in reports:
        spec = yaml.safe_load(path.read_text(encoding="utf-8"))
        pdf = raw_root / spec["country"] / spec["issuer"] / f"{spec['year_end']}.pdf"
        for table, pages in sorted(statement_pages(path).items()):
            gold = read_grid(path.with_suffix("") / f"{table}.csv")
            jobs = [(tool, strategy) for tool, strategies in tools.items() for strategy in strategies]
            for tool, strategy in jobs + ([REFERENCE] if reference else []):
                if (tool, strategy) == REFERENCE:  # page by page, joined, as for the tools
                    t = time.perf_counter()
                    try:
                        grid, error = [row for p in pages for row in pdf_tables.extract(str(pdf), [p])], ""
                    except Exception as err:
                        grid, error = [], f"{type(err).__name__}: {err}"[:200]
                    seconds = time.perf_counter() - t
                else:
                    grid, seconds, error = timed_extract(pdf, pages, tool, strategy)
                out.append({"issuer": spec["issuer"], "table": table, "pages": pages, "tool": tool, "strategy": strategy,
                            "seconds": round(seconds, 2), "error": error, **score(gold, grid)})
    return out


def summarise(rows: list[dict]) -> dict:
    """Totals per tool and strategy, each tool's best strategy, and the best eligible tool."""
    by: dict[tuple[str, str], dict] = {}
    for r in rows:
        s = by.setdefault((r["tool"], r["strategy"]), {"tool": r["tool"], "strategy": r["strategy"], "tables": 0, "figures": 0,
                                                       "found": 0, "wrong": 0, "rows": 0, "rows_complete": 0, "tables_complete": 0,
                                                       "seconds": 0.0, "errors": 0})
        s["tables"] += 1
        for k in ("figures", "found", "wrong", "rows", "rows_complete"):
            s[k] += r[k]
        s["tables_complete"] += r["table_complete"]
        s["seconds"] = round(s["seconds"] + r["seconds"], 2)
        s["errors"] += bool(r["error"])
    for s in by.values():
        s["found_share"] = round(s["found"] / s["figures"], 4) if s["figures"] else 0.0
        s["rows_complete_share"] = round(s["rows_complete"] / s["rows"], 4) if s["rows"] else 0.0

    def rank(s: dict) -> tuple:
        return (s["found_share"], s["tables_complete"], -s["seconds"])

    best_strategy = {}
    for (tool, _), s in by.items():
        if tool not in best_strategy or rank(s) > rank(by[(tool, best_strategy[tool])]):
            best_strategy[tool] = s["strategy"]
    eligible = [by[(tool, st)] for tool, st in best_strategy.items() if (tool, st) != REFERENCE and tool != REFERENCE[0]]
    best = max(eligible, key=rank)
    return {"by_strategy": sorted(by.values(), key=lambda s: (s["tool"], s["strategy"])), "best_strategy": best_strategy,
            "best": {"tool": best["tool"], "strategy": best["strategy"]}}


def report(summary: dict, rows: list[dict], title: str = "Automatic-extraction run: three tools on 20 tables") -> str:
    lines = [f"# {title}", "",
             "Scores against the hand-corrected tables (counts only; see `faithguard.data.extraction`). *Figures found*: share of "
             "the corrected table's figures that come out in the matching row, in order. The project's own reader "
             "(`pdf_tables`) was built on these reports, so it is shown as a reference and is never a candidate.", "",
             "| Tool | Strategy | Tables | Figures found | Wrong figures | Rows complete | Tables complete | Seconds | Errors |",
             "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for s in summary["by_strategy"]:
        mark = " (best)" if summary["best_strategy"].get(s["tool"]) == s["strategy"] else ""
        lines.append(f"| {s['tool']} | {s['strategy']}{mark} | {s['tables']} | {s['found']}/{s['figures']} ({100 * s['found_share']:.1f}%) | {s['wrong']} "
                     f"| {s['rows_complete']}/{s['rows']} ({100 * s['rows_complete_share']:.1f}%) | {s['tables_complete']} "
                     f"| {s['seconds']:.0f} | {s['errors']} |")
    best = summary["best"]
    lines += ["", f"**Best tool:** {best['tool']} ({best['strategy']}), the eligible tool with the most figures found "
              "(ties: more tables complete, then faster), a rule fixed before the run.", "",
              "## Figures found per table, each tool at its best strategy", ""]
    tools = list(summary["best_strategy"])
    lines += ["| Table | Pages | " + " | ".join(tools) + " |", "|" + " --- |" * (len(tools) + 2)]
    tables = sorted({(r["issuer"], r["table"]) for r in rows})
    for issuer, table in tables:
        cells = []
        for tool in tools:
            r = next(r for r in rows if (r["issuer"], r["table"], r["tool"], r["strategy"]) == (issuer, table, tool, summary["best_strategy"][tool]))
            cells.append(f"{r['found']}/{r['figures']}" + (" (error)" if r["error"] else ""))
        pages = next(r["pages"] for r in rows if (r["issuer"], r["table"]) == (issuer, table))
        lines.append(f"| {issuer} {table} | {', '.join(map(str, pages))} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


# -- the real-world condition's evidence -----------------------------------------------------------

CURRENCY = {"LK": "LKR", "US": "USD"}


def automatic_tables(report: Path, raw_root: Path, tool: str, strategy: str) -> tuple[list, list[dict]]:
    """A report's tables as the tool reads them, with no correction, and how each one's scale was found.

    The scale comes from the table's header or, failing that, from its first page's text; the currency
    from the country; entities from the column headers. Only the pages and titles come from the report
    file, which a person wrote.
    """
    import pymupdf

    from faithguard.benchmark import load_report
    from faithguard.calc.numbers import detect_scale
    from faithguard.tables import table_from_grid

    spec, corrected = load_report(report)
    pdf = raw_root / spec.country / spec.issuer / f"{spec.year_end}.pdf"
    pages = statement_pages(report)
    tables, notes = [], []
    for table_id, meta in spec.tables.items():
        grid = extract(pdf, pages[table_id], tool, strategy)
        first_body = next((i for i, (_, figures) in enumerate(rows_of(grid)) if not is_header(figures)), len(grid))
        scale, found_in = detect_scale(" ".join(" ".join(r) for r in grid[:first_body])), "header"
        if not scale:
            with pymupdf.open(str(pdf)) as doc:
                scale = detect_scale(doc[pages[table_id][0] - 1].get_text())
            found_in = "page" if scale else "none"
        tables.append(table_from_grid(table_id, grid, title=meta.title, scale=scale, currency=CURRENCY[spec.country],
                                      page=pages[table_id][0], source=spec.source))
        right = next(t.scale for t in corrected.tables if t.id == table_id)
        notes.append({"issuer": spec.issuer, "table": table_id, "scale": scale, "scale_from": found_in, "scale_right": scale == right,
                      "cells": len(tables[-1].cells), "corrected_cells": len(next(t for t in corrected.tables if t.id == table_id).cells)})
    return tables, notes
