"""Reading 10-K HTML tables into the benchmark CSV layout."""

from faithguard.data import html_tables
from faithguard.tables import table_from_grid

# Laid out as filing agents print statements: a grid-defining first row, a spanning
# year header, "$" and ")" in cells of their own, spacer cells, and an inline XBRL
# header hidden with display:none.
FILING = """<html><body>
<div style="display:none"><table><tr><td>hidden 999</td><td>1,000</td></tr></table></div>
<div>EXAMPLE CORP</div><div>CONSOLIDATED STATEMENTS OF OPERATIONS</div>
<div>(in thousands, except per share data)</div>
<table>
<tr><td></td><td></td><td></td><td></td><td></td><td></td><td></td><td></td></tr>
<tr><td></td><td colspan="7">Year Ended December 31,</td></tr>
<tr><td></td><td colspan="3">2025</td><td></td><td colspan="3">2024</td></tr>
<tr><td>Revenue</td><td>$</td><td>1,200</td><td></td><td></td><td>$</td><td>1,000</td><td></td></tr>
<tr><td>Operating expenses:</td><td colspan="3"></td><td></td><td colspan="3"></td></tr>
<tr><td>Cost of revenue</td><td colspan="2">700</td><td></td><td></td><td colspan="2">650</td><td></td></tr>
<tr><td>Other (expense) income</td><td colspan="2">(30</td><td>)</td><td></td><td colspan="2">&#8212;</td><td></td></tr>
<tr><td colspan="8"></td></tr>
<tr><td>Net income</td><td>$</td><td>470</td><td></td><td></td><td>$</td><td>350</td><td></td></tr>
<tr><td>Diluted EPS</td><td>$</td><td>1.25</td><td></td><td></td><td>$</td><td>0.93</td><td></td></tr>
</table>
<div>Notes follow.</div>
<table><tr><td>Words only</td><td>no numbers</td></tr></table>
</body></html>"""


def test_statement_reads_into_benchmark_layout():
    tables = html_tables.read_tables(FILING)
    assert len(tables) == 2 and tables[0].title == "(in thousands, except per share data)"
    grid = html_tables.to_grid(tables[0])
    assert grid == [
        ["(in thousands, except per share data)", "Year Ended December 31,", "Year Ended December 31,"],
        ["", "2025", "2024"],
        ["Revenue", "1,200", "1,000"],
        ["Operating expenses:", "", ""],
        ["Cost of revenue", "700", "650"],
        ["Other (expense) income", "(30)", "—"],
        ["Net income", "470", "350"],
        ["Diluted EPS", "1.25", "0.93"],
    ]


def test_grid_feeds_the_table_normaliser():
    grid = html_tables.to_grid(html_tables.read_tables(FILING)[0])
    table = table_from_grid("t1", grid, currency="USD")
    cells = {(c.row_label, c.period): c for c in table.cells if c.raw is not None}
    assert table.scale == 3
    assert cells[("Revenue", "2025")].raw == 1200 and cells[("Revenue", "2025")].scale == 3
    assert cells[("Other (expense) income", "2025")].raw == -30
    assert cells[("Diluted EPS", "2024")].scale == 0  # per-share figures are not in thousands


def test_listing_skips_tables_without_numbers():
    found = html_tables.list_tables(FILING, "statements of operations")
    assert [(index, rows, columns) for index, _, rows, columns in found] == [(0, 8, 2)]
    assert html_tables.list_tables(FILING, "balance sheet") == []


# Amounts end at grid positions 5, 8, 11 and per-share figures at 6, 9, 12: three columns, not one.
CHAINED = """<table>
<tr><td colspan="3"></td><td colspan="3">2025</td><td colspan="3">2024</td><td colspan="3">2023</td></tr>
<tr><td colspan="3">Revenue</td><td colspan="2">7,478</td><td></td><td colspan="2">7,948</td><td></td><td colspan="2">8,489</td><td></td></tr>
<tr><td colspan="3">Costs</td><td colspan="2">(1,000</td><td>)</td><td colspan="2">(900</td><td>)</td><td colspan="2">(800</td><td>)</td></tr>
<tr><td colspan="3">Diluted EPS</td><td colspan="3">3.03</td><td colspan="3">2.80</td><td colspan="3">3.13</td></tr>
</table>"""

# Years printed two positions left of their figures, and zero-width spaces in cells and labels.
OFFSET = """<table>
<tr><td colspan="3">(In millions)</td><td colspan="9">December 31,</td></tr>
<tr><td colspan="3">2025</td><td colspan="3">​</td><td colspan="3">2024</td><td colspan="3"></td></tr>
<tr><td colspan="3">Cash ​</td><td></td><td>683</td><td colspan="5"></td><td>651</td><td></td></tr>
<tr><td colspan="3">Total assets</td><td></td><td>60,922</td><td colspan="5"></td><td>59,365</td><td></td></tr>
</table>"""


def test_nearby_column_edges_do_not_chain_into_one_column():
    grid = html_tables.to_grid(html_tables.read_tables(CHAINED)[0])
    assert grid == [
        ["", "2025", "2024", "2023"],
        ["Revenue", "7,478", "7,948", "8,489"],
        ["Costs", "(1,000)", "(900)", "(800)"],
        ["Diluted EPS", "3.03", "2.80", "3.13"],
    ]


def test_years_left_of_their_column_and_zero_width_spaces():
    grid = html_tables.to_grid(html_tables.read_tables(OFFSET)[0])
    assert grid == [
        ["(In millions)", "December 31,", "December 31,"],
        ["", "2025", "2024"],
        ["Cash", "683", "651"],
        ["Total assets", "60,922", "59,365"],
    ]
