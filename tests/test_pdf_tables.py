"""Reading a statement table from word positions, on a stand-in page (no PDF needed)."""

from decimal import Decimal
from types import SimpleNamespace

import pytest

from faithguard import benchmark
from faithguard.data.pdf_tables import extract, extract_page
from faithguard.tables import table_from_grid


class Page:
    def __init__(self, words, height=842.0):
        self.words = words
        self.rect = SimpleNamespace(height=height)

    def get_text(self, kind):
        assert kind == "words"
        return self.words


def word(x1, y, text, x0=None):
    """A word ending at x1 (numbers are right-aligned), centred on line y."""
    x0 = x1 - 4.5 * len(text) if x0 is None else x0
    return (x0, y - 4, x1, y + 4, text, 0, 0, 0)


def label(y, text, x0=40.0):
    words, x = [], x0
    for part in text.split():
        words.append((x, y - 4, x + 4.5 * len(part), y + 4, part, 0, 0, 0))
        x += 4.5 * len(part) + 2.5
    return words


COLUMNS = (320, 390, 460, 530)  # right edges: Group 2026, Group 2025, Company 2026, Company 2025


def row(y, values, ys=None):
    ys = ys or [y] * len(values)
    return [word(x1, yy, v) for x1, yy, v in zip(COLUMNS, ys, values)]


def statement_page():
    words = label(60, "Income statement")
    words += [word(348, 88, "Group", x0=326), word(488, 88, "Company", x0=466)]
    words += label(100, "For the year ended 31 March") + [word(x1, 100, y) for x1, y in zip(COLUMNS, ("2026", "2025", "2026", "2025"))]
    words += [word(250, 112, "Note")]
    for x1 in COLUMNS:
        words += [word(x1 - 22, 112, "Rs."), word(x1, 112, "'000")]
    words += label(130, "Revenue") + [word(250, 130, "5")] + row(130, ["1,250,400", "1,100,200", "640,300", "590,100"])
    words += label(142, "Cost of sales") + [word(250, 142, "6")] + row(142, ["(800,100)", "(700,050)", "(400,200)", "(380,000)"])
    words += row(156, ["450,300", "400,150", "240,100", "210,100"])  # an unlabelled subtotal
    words += label(172, "Share of profit of equity accounted")  # a label that wraps; its numbers sit on the second line
    words += label(182, "investees, net of tax") + [word(250, 182, "7")] + row(185, ["52,000", "41,500", "-", "-"])
    words += label(198, "Profit before tax") + row(198, ["502,300", "441,650", "240,100", "210,100"], ys=[198, 198, 201, 201])
    words += [word(60, 820, "124")] + label(820, "Annual Report 2025/26", x0=80)  # page footer
    return Page(words)


def test_statement_table_is_read_by_position():
    grid = extract_page(statement_page())
    assert grid == [
        ["", "Group", "Group", "Company", "Company"],
        ["For the year ended 31 March", "2026", "2025", "2026", "2025"],
        ["", "Rs. '000", "Rs. '000", "Rs. '000", "Rs. '000"],
        ["Revenue", "1,250,400", "1,100,200", "640,300", "590,100"],
        ["Cost of sales", "(800,100)", "(700,050)", "(400,200)", "(380,000)"],
        ["", "450,300", "400,150", "240,100", "210,100"],
        ["Share of profit of equity accounted investees, net of tax", "52,000", "41,500", "-", "-"],
        ["Profit before tax", "502,300", "441,650", "240,100", "210,100"],
    ]
    table = table_from_grid("t1", grid)
    pbt = next(c for c in table.cells if c.metric == "profit before tax" and c.entity == "company" and c.period == "2025")
    assert pbt.value == Decimal("210100000")


def test_unit_rows_without_an_apostrophe_are_headers():
    grid = [
        ["", "BANK", "BANK", "BANK"],
        ["For the year ended 31st December", "2025", "2024", "Change"],
        ["", "Rs 000", "Rs 000", "%"],
        ["Gross income", "218,780,329", "195,321,016", "12"],
    ]
    table = table_from_grid("t1", grid)
    assert table.scale == 3 and {c.row for c in table.cells} == {3}
    gross = next(c for c in table.cells if c.period == "2025")
    assert gross.value == Decimal("218780329000") and gross.entity == "bank"
    assert next(c for c in table.cells if c.col == 3).kind == "percent"


BALANCE_SHEET = [
    ["", "Group", "Group", "Change"],
    ["As at 31 March", "2026", "2025", "%"],
    ["Rs. '000", "", "", ""],
    ["ASSETS", "", "", ""],
    ["Cash", "1,200", "1,100", "9"],
    ["Loans", "3,400", "2,900", "17"],
    ["Total assets", "4,600", "4,000", "15"],
    ["Interest income", "900", "800", "13"],
    ["Less: interest expense", "300", "250", "20"],
    ["Net interest income", "600", "550", "9"],
    ["Fees", "(100)", "-", "-"],
    ["", "500", "550", "(9)"],
    ["Non-controlling interest", "-", "-", "-"],
    ["Total", "500", "550", "(9)"],
]


def test_totals_add_up_and_misplaced_figures_are_caught():
    sums, failures = benchmark.total_rows(BALANCE_SHEET)
    assert sums == [6, 9, 11, 13] and failures == []
    broken = [list(r) for r in BALANCE_SHEET]
    broken[5][1] = "3,500"  # a misread figure
    broken[10][2] = "(100)"  # a figure read into the wrong column
    assert benchmark.total_rows(broken)[1] == [6, 11]


def test_check_warns_when_a_table_total_does_not_add_up(tmp_path):
    folder = tmp_path / "LK" / "TEST"
    (folder / "2026").mkdir(parents=True)
    (folder / "2026.yaml").write_text(
        'issuer: TEST\ncountry: LK\nname: Test PLC\nfiscal_year: "2026"\n'
        "tables:\n  t1:\n    title: Statement of financial position\n    page: 12\nquestions: []\n",
        encoding="utf-8",
    )
    rows = [list(r) for r in BALANCE_SHEET]
    rows[6][2] = "4,100"
    (folder / "2026" / "t1.csv").write_text("\n".join(",".join(f'"{c}"' for c in r) for r in rows), encoding="utf-8")
    findings, _ = benchmark.check(benchmark.report_paths(tmp_path))
    assert [(f.question, f.level) for f in findings] == [("t1r6", "warning")]
    assert "Total assets is not the sum of the rows above it" in findings[0].message and "page 12" in findings[0].message


def test_statement_continued_over_two_pdf_pages(tmp_path):
    pymupdf = pytest.importorskip("pymupdf")

    def put(page, y, text, right=None, x=40):
        if right is not None:
            x = right - pymupdf.get_text_length(text, fontname="helv", fontsize=8)
        page.insert_text((x, y), text, fontsize=8, fontname="helv")

    doc = pymupdf.open()
    for lines in (
        [("Cash", "1,200", "1,100"), ("Loans", "3,400", "2,900"), ("Total assets", "4,600", "4,000")],
        [("Deposits", "3,000", "2,700"), ("Equity", "1,600", "1,300"), ("Total equity and liabilities", "4,600", "4,000")],
    ):
        page = doc.new_page(width=595, height=842)
        put(page, 100, "As at 31 March")
        put(page, 100, "2026", right=400)
        put(page, 100, "2025", right=480)
        put(page, 112, "Rs. '000", right=400)
        put(page, 112, "Rs. '000", right=480)
        for k, (label, now, before) in enumerate(lines):
            put(page, 130 + 12 * k, label)
            put(page, 130 + 12 * k, now, right=400)
            put(page, 130 + 12 * k, before, right=480)
        put(page, 820, "Annual Report 2025/26")
    pdf = tmp_path / "report.pdf"
    doc.save(pdf)
    grid = extract(str(pdf), [1, 2])
    assert grid == [
        ["As at 31 March", "2026", "2025"],
        ["", "Rs. '000", "Rs. '000"],
        ["Cash", "1,200", "1,100"],
        ["Loans", "3,400", "2,900"],
        ["Total assets", "4,600", "4,000"],
        ["Deposits", "3,000", "2,700"],
        ["Equity", "1,600", "1,300"],
        ["Total equity and liabilities", "4,600", "4,000"],
    ]
    assert benchmark.total_rows(grid) == ([4, 7], [])


def test_headers_survive_page_numbers_footnote_years_and_a_wide_gap():
    words = [word(530, 40, "151")]  # a page number above the last column
    words += [word(348, 70, "Group", x0=326), word(488, 70, "Company", x0=466)]  # 18 points above the years
    words += label(88, "For the year ended 31 March") + [word(x1, 88, y) for x1, y in zip(COLUMNS, ("2026", "2025", "2026*", "2025"))]
    words += label(110, "Revenue") + row(110, ["1,250,400", "1,100,200", "640,300", "590,100"])
    words += label(122, "Cost of sales") + row(122, ["(800,100)", "(700,050)", "(400,200)", "(380,000)"])
    words += label(134, "Gross profit") + row(134, ["450,300", "400,150", "240,100", "210,100"])
    grid = extract_page(Page(words))
    assert grid[:2] == [["", "Group", "Group", "Company", "Company"], ["For the year ended 31 March", "2026", "2025", "2026*", "2025"]]
    assert [r[0] for r in grid[2:]] == ["Revenue", "Cost of sales", "Gross profit"]


def test_dates_and_as_at_lines_are_headers_not_figures():
    from faithguard.tables import is_header_row

    assert is_header_row(["(all amounts in Sri Lanka Rupees)", "As at 31", "December"])
    assert is_header_row(["", "31.03.2026", "31.03.2025"])
    assert not is_header_row(["Revenue", "Rs. 5,000", "4,000 mn"])
    table = table_from_grid("t1", [["", "As at", "As at"], ["", "31.03.2026", "31.03.2025"], ["Total assets", "5,000", "4,000"]])
    assert [c.period for c in table.cells] == ["2026", "2025"]


def test_glyph_coded_figures_are_decoded_and_whitespace_is_not():
    from faithguard.data.pdf_tables import _glyph_text

    assert _glyph_text("\x03\x15\x16\x0f\x13\x15\x15\x0f\x17\x1b\x16\x03").strip() == "23,022,483"
    assert _glyph_text("$V\x03DW\x03\x16\x14VW\x030DUFK\x0f").strip() == "As at 31st March,"
    assert _glyph_text("Figures\tin brackets") == "Figures\tin brackets"  # tabs are ordinary whitespace


def test_totals_allow_rounding_and_a_total_that_repeats_one_row():
    grid = [
        ["", "2026", "2025"],
        ["Non-current liabilities", "2,425,077", "2,491,939"],
        ["Current liabilities", "3,164,528", "2,473,971"],
        ["Total liabilities", "5,589,606", "4,965,910"],  # the report's own rounding: off by one
        ["Stated capital", "511,848", "511,848"],
        ["Retained earnings", "2,498,590", "3,235,391"],
        ["Total shareholders' equity", "3,010,438", "3,747,239"],
        ["Total equity", "3,010,438", "3,747,239"],  # repeats the row above
        ["Total equity and liabilities", "8,600,044", "8,713,149"],
    ]
    sums, failures = benchmark.total_rows(grid)
    assert failures == [] and sums == [3, 6, 7, 8]
    grid[3][1] = "5,589,706"  # off by 100 is a misread figure, not rounding
    assert 3 in benchmark.total_rows(grid)[1]


def test_net_of_rows_may_be_differences_and_lone_totals_are_not_flagged():
    grid = [
        ["", "2025", "2024"],
        ["ASSETS", "", ""],
        ["Cash", "683", "651"],
        ["Loans and leases", "60,917", "59,410"],
        ["Allowance for loan losses", "678", "696"],
        ["Loans held for investment, net of allowance", "60,239", "58,714"],
        ["Total assets", "60,922", "59,365"],
        ["Earnings per share:", "", ""],
        ["Total basic earnings", "10.08", "10.57"],  # printed without its parts
    ]
    sums, failures = benchmark.total_rows(grid)
    assert failures == [] and 5 in sums and 6 in sums
