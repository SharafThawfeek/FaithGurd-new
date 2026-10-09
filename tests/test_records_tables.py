from decimal import Decimal

import pytest
from pydantic import ValidationError

from faithguard.records import (
    Answer,
    Calculate,
    Cell,
    Copy,
    EditProgram,
    Evidence,
    Item,
    Question,
    read_jsonl,
    write_jsonl,
)
from faithguard.tables import normalise_metric, normalise_period, table_from_grid

D = Decimal

BANK_GRID = [
    ["Income statement extract", "Group", "Group", "Bank", "Bank"],
    ["Rs. '000", "2025", "2024", "2025", "2024"],
    ["Profit after tax", "14,212,560", "13,004,180", "12,450,330", "11,635,900"],
    ["Impairment charges", "(2,104,330)", "(2,450,120)", "(1,980,410)", "(2,301,770)"],
    ["Net interest margin %", "4.2", "4.0", "4.1", "3.9"],
]


def bank_table():
    return table_from_grid("t1", BANK_GRID)


def test_table_reads_context_scale_and_negatives():
    t = bank_table()
    assert t.scale == 3
    pat = next(c for c in t.cells if c.metric == "profit after tax" and c.entity == "group" and c.period == "2025")
    assert pat.raw == D("14212560") and pat.value == D("14212560000")
    imp = next(c for c in t.cells if c.metric == "impairment charges" and c.entity == "bank" and c.period == "2024")
    assert imp.raw == D("-2301770")
    nim = next(c for c in t.cells if c.metric.startswith("net interest margin"))
    assert (nim.kind, nim.scale, nim.raw) == ("percent", 0, D("4.2"))  # "%" in the row label makes it a rate


def test_per_share_rows_ignore_the_table_scale_and_blank_labels_inherit_the_section():
    grid = [
        ["(in thousands)", "2019", "2018"],
        ["Revenue", "5,000", "4,000"],
        ["Basic earnings per share", "", ""],
        ["", "2.79", "2.69"],
    ]
    t = table_from_grid("t1", grid)
    revenue = next(c for c in t.cells if c.metric == "revenue" and c.period == "2019")
    eps = next(c for c in t.cells if c.row == 3 and c.period == "2019")
    assert revenue.value == D("5000000")
    assert (eps.metric, eps.scale, eps.value) == ("basic earnings per share", 0, D("2.79"))


def test_basic_and_diluted_rows_under_a_per_share_section_are_per_share():
    # As US income statements print them: "Basic" twice, once per share and once as shares (in thousands)
    grid = [
        ["(in thousands, except per share amounts)", "2025", "2024"],
        ["Net income", "451,123", "404,386"],
        ["Net income per share attributable to common shareholders:", "", ""],
        ["Basic", "15.64", "13.06"],
        ["Diluted", "15.28", "12.63"],
        ["Weighted average common shares outstanding:", "", ""],
        ["Basic", "28,846", "30,957"],
    ]
    cells = {(c.row, c.period): c for c in table_from_grid("t1", grid).cells}
    eps, shares = cells[(3, "2025")], cells[(6, "2025")]
    assert (eps.scale, eps.value) == (0, D("15.64"))
    assert (shares.scale, shares.value) == (3, D("28846000"))
    assert cells[(1, "2025")].scale == 3


def test_finqa_style_table():
    grid = [["", "amount ( in millions )"], ["2009 net revenue", "$ 536.7"], ["other", "-0.3 ( 0.3 )"]]
    t = table_from_grid("t1", grid)
    first, other = t.cells
    assert (first.metric, first.period, first.raw, first.scale) == ("net revenue", "2009", D("536.7"), 6)
    assert other.raw == D("-0.3")


def test_transposed_table():
    grid = [["Year", "Revenue", "Net income"], ["2025", "100", "10"], ["2024", "90", "8"]]
    t = table_from_grid("t1", grid)
    cell = next(c for c in t.cells if c.period == "2024" and c.metric == "net income")
    assert cell.raw == D("8")


@pytest.mark.parametrize(
    "text, period",
    [("FY2025", "2025"), ("2024/25", "2025"), ("Dec 31, 2019", "2019"), ("Year ended 31 March 2025", "2025"), ("FY25", "2025"), ("Group", None)],
)
def test_normalise_period(text, period):
    assert normalise_period(text) == period


def test_normalise_metric_drops_years_and_notes():
    assert normalise_metric("2009 Net revenue (Note 5)") == "net revenue"


def test_cell_ids_must_be_expression_names():
    with pytest.raises(ValidationError):
        Cell(id="t1:r1", table_id="t1", row=1, col=1, text="5")


def test_edit_program_round_trips_through_json():
    program = EditProgram(edits=[Copy(claim="k1", cell="t1r2c1"), Calculate(claim="k2", expr="growth(t1r2c1, t1r2c2)")])
    again = EditProgram.model_validate_json(program.model_dump_json())
    assert again == program
    assert [e.op for e in again.edits] == ["COPY", "CALCULATE"]


def test_items_round_trip_through_jsonl(tmp_path):
    item = Item(
        id="a1",
        question=Question(id="q1", issuer="demo", text="What was the Group's profit after tax in FY2025?"),
        evidence=Evidence(tables=[bank_table()]),
        answer=Answer(id="a1", question_id="q1", generator="template", text="Rs. 14,213 million"),
    )
    path = tmp_path / "items.jsonl"
    write_jsonl(path, [item])
    (back,) = read_jsonl(path, Item)
    assert back == item
    assert back.evidence.digest() == item.evidence.digest()
    assert back.evidence.cell("t1r2c1").raw == D("14212560")
    assert len(item.evidence.without(["t1r2c1"]).cells()) == len(item.evidence.cells()) - 1
