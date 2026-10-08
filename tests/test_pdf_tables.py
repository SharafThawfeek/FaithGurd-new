"""Reading a statement table from word positions, on a stand-in page (no PDF needed)."""

from decimal import Decimal
from types import SimpleNamespace

from faithguard.data.pdf_tables import extract_page
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
