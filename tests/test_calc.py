from decimal import Decimal

import pytest

from faithguard.calc import (
    CalcError,
    ExprError,
    calculate,
    default_style,
    detect_scale,
    find_numbers,
    growth,
    matches,
    parse,
    parse_cell,
    refs,
    render,
    share,
)

D = Decimal


def one(text, **kw):
    found = find_numbers(text, **kw)
    assert len(found) == 1, found
    return found[0]


@pytest.mark.parametrize(
    "text, kind, value, scale, decimals",
    [
        ("Rs. 12,450 million", "amount", D("12450000000"), 6, 0),
        ("Rs.12,450mn", "amount", D("12450000000"), 6, 0),
        ("LKR 1.28 trillion", "amount", D("1280000000000"), 12, 2),
        ("$8.43 billion", "amount", D("8430000000"), 9, 2),
        ("US$ 5m", "amount", D("5000000"), 6, 0),
        ("7.0%", "percent", D("7.0"), 0, 1),
        ("12 per cent", "percent", D("12"), 0, 0),
        ("25 bps", "percent", D("0.25"), 0, 0),
        ("1.5x", "ratio", D("1.5"), 0, 1),
        ("5,829", "number", D("5829"), 0, 0),
        ("18,640 thousand", "amount", D("18640000"), 3, 0),
    ],
)
def test_find_numbers_parses_kinds_and_scales(text, kind, value, scale, decimals):
    m = one(text)
    assert (m.kind, m.value, m.scale, m.decimals) == (kind, value, scale, decimals)


def test_currency_codes():
    assert one("Rs. 5 million").currency == "LKR"
    assert one("$5 million").currency == "USD"
    assert one("5 million rupees").currency == "LKR"


def test_years_dates_and_ranges_are_not_claims():
    assert find_numbers("In FY2025 and 2024/25, on 31 December 2025") == []
    assert [m.kind for m in find_numbers("in 2025", include_years=True)] == ["year"]


def test_signs_and_brackets():
    assert one("fell to -3.2%").value == D("-3.2")
    assert one("a loss of $-5 million").value == D("-5000000")
    # brackets are an aside in prose, but a negative in table cells
    assert one("profit (Rs. 5 million) rose").value == D("5000000")
    assert parse_cell("(1,234)").raw == D("-1234")
    assert parse_cell("$ 5,829").raw == D("5829")
    assert parse_cell("—") is None


def test_ranges_do_not_create_negatives():
    values = [m.value for m in find_numbers("between 5–7% this year")]
    assert values == [D("7")] or values == [D("5"), D("7")]
    assert all(v > 0 for v in values)


def test_spans_point_at_the_text():
    text = "Group profit after tax rose 7.0% to Rs. 12,450 million."
    pct, amount = find_numbers(text)
    assert text[pct.start : pct.end] == "7.0%"
    assert text[amount.start : amount.end] == "Rs. 12,450 million"


def test_matches_uses_printed_precision():
    m = one("Rs. 12,450 million")
    assert matches(m, D("12450330000"))  # 12,450.33 million rounds to 12,450
    assert not matches(m, D("12451000000"))
    assert matches(one("9.3%"), D("9.2922"))
    assert not matches(one("9.3%"), D("9.36"))


def test_render_keeps_the_original_style():
    m = one("Rs. 12,450 million")
    assert render(D("14212560000"), m.style) == "Rs. 14,213 million"
    assert render(D("9.2922"), one("7.0%").style) == "9.3%"
    assert render(D("-1234"), parse_cell("(5)").style) == "(1,234)"
    assert render(D("0.25"), one("10 bps").style) == "25 bps"


def test_render_keeps_three_significant_digits_for_amounts():
    assert render(D("8432500000"), one("$8.4 billion").style) == "$8.43 billion"
    # at most two decimals more than the original style
    assert render(D("400000"), one("Rs. 2 million").style) == "Rs. 0.40 million"


def test_default_style():
    assert render(D("14212560000"), default_style("amount", 6, "LKR")) == "Rs. 14,213 million"
    assert render(D("9.29"), default_style("percent")) == "9.3%"


def test_detect_scale():
    assert detect_scale("Income statement (Rs. '000)") == 3
    assert detect_scale("(in millions)") == 6
    assert detect_scale("Year ended 31 December") == 0


def test_ops():
    assert growth(D("14212560"), D("13004180")).quantize(D("0.01")) == D("9.29")
    assert growth(D("90"), D("-100")) == D("190")
    assert share(D("1"), D("4")) == D("25")
    with pytest.raises(CalcError):
        growth(D("1"), D("0"))


def test_expressions():
    values = {"c1": D("14212560"), "c2": D("13004180"), "t1r3c2": D("5")}
    assert calculate("growth(c1, c2)", values).quantize(D("0.01")) == D("9.29")
    assert calculate("(c1 - c2) / c2 * 100", values) == calculate("growth(c1, c2)", values)
    assert calculate("-t1r3c2 + sum(1, 2, 3)", values) == D("1")
    assert refs(parse("share(c1, sum(c1, c2))")) == ["c1", "c2"]


@pytest.mark.parametrize(
    "bad",
    ["__import__('os')", "c1 ** 2", "open(c1)", "growth(c1)", "c1 +", "c1; c2", "x" * 600],
)
def test_expressions_reject_anything_else(bad):
    with pytest.raises(ExprError):
        parse(bad)


def test_unknown_cell_is_a_calc_error():
    with pytest.raises(CalcError):
        calculate("c9 + 1", {})
