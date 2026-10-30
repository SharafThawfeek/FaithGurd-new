"""Own questions in the demo (demo/ask.py) against the second mock panel's inputs, on made-up tables: no pilot data,
models or GPU needed. Each test is a finding: what was refused, written or said wrongly, and what is said now."""

import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parent.parent / "demo"
sys.path.insert(0, str(DEMO))

from ask import (Report, Unanswerable, _bad_wording, _loose, _own_year, _singular, _tidy, caveats, contradictions,  # noqa: E402
                 draft, make_item, missing_year, other_company, plant, read_question, typography)
from cases import Demo  # noqa: E402

from faithguard.claims import extract_claims  # noqa: E402
from faithguard.detect import detect  # noqa: E402
from faithguard.executor import apply  # noqa: E402
from faithguard.records import ClaimCheck, Context, DetectorOutput, Evidence  # noqa: E402
from faithguard.tables import table_from_grid  # noqa: E402

GRID = [["Statement", "Group", "Group", "Company", "Company"], ["Rs. '000", "2026", "2025", "2026", "2025"],
        ["Revenue", "65,925,260", "59,282,247", "4,000,000", "3,500,000"],
        ["Income", "29,875,514", "27,000,000", "1,500,000", "1,400,000"],
        ["Net interest income", "14,002,435", "12,519,938", "2,000,000", "1,800,000"],
        ["Profit for the year", "5,035,750", "5,164,800", "3,500,217", "2,243,000"],
        ["Net asset value per share", "45", "40", "30", "28"],
        ["Number of employees", "4,917", "4,428", "120", "110"],
        ["Total assets", "55,740,093", "48,200,000", "10,832,013", "9,900,000"]]


def made_up(name: str = "Test Holdings PLC") -> Report:
    return Report("demo:test", name, "LK", Evidence(tables=[table_from_grid("t1", GRID, currency="LKR")]), True)


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("demo")
    d = Demo(cache_path=tmp / "cache.json", config=tmp / "no-examples.json")
    d.reports["demo:test"] = made_up()
    return d


def notes(demo, question, answer, report="demo:test"):
    return " ".join(demo.ask(report, question, answer)["caveats"])


def test_another_company_is_refused_even_when_it_shares_a_word_with_this_one():
    sampath, tokyo = made_up("Sampath Bank PLC"), made_up("Tokyo Cement Company (Lanka) PLC")
    assert "Commercial Bank" in other_company(sampath, "What was Commercial Bank's profit for the year in 2025?")
    assert "John Keells Group" in other_company(made_up("Sunshine Holdings PLC"), "What was John Keells Group's revenue in 2026?")
    assert "Insee Cement" in other_company(tokyo, "What was Insee Cement's profit for the year in 2026?")
    assert "Insee Cement" in other_company(tokyo, "What was the profit of Insee Cement in 2026?")
    assert "Commercial Bank" in other_company(sampath, "How did Commercial Bank of Ceylon perform in 2025?")
    assert "John Keells" in other_company(made_up("Sunshine Holdings PLC"), "What revenue did John Keells report in 2026?")
    for fine in ("What was Sampath Bank's profit for the year in 2025?", "What's the Group's revenue in 2026?",
                 "What was the CEO's salary in 2026?", "What were the total assets as of December 31, 2025?",
                 "What was the Group's Revenue from Operations in 2026?", "What was the Group's Net Interest Income for 2026?",
                 "What were the Group's Amounts Due from Related Parties in 2026?", "What was Group Return on Equity in 2026?",
                 "What was the Group's revenue for FY2025/26?", "How did EBITDA change in 2026?",
                 "What dividend did the Board declare in 2026?", "How much did the Group make in 2026?",
                 "What did Sampath Bank report as net interest income in 2025?"):
        assert other_company(sampath if "Sampath" in fine else tokyo, fine) is None, fine


def test_a_fix_to_a_row_of_the_same_name_in_another_statement_is_said_not_trustworthy(demo):
    income = [["Statement of profit or loss", "Group", "Group"], ["Rs. '000", "2026", "2025"],
              ["Profit for the year", "5,035,750", "5,164,800"], ["Non-controlling interest", "1,966,330", "1,627,063"]]
    position = [["Statement of financial position", "Group", "Group"], ["Rs. '000", "2026", "2025"],
                ["Total equity", "40,000,000", "38,000,000"], ["Non-controlling interests", "7,450,423", "6,748,189"]]
    tables = [table_from_grid(i, g, currency="LKR").model_copy(update={"title": g[0][0]})
              for i, g in (("t1", income), ("t2", position))]
    demo.reports["demo:two"] = Report("demo:two", "Test Holdings PLC", "LK", Evidence(tables=tables), True)
    q = "What was the Group's non-controlling interest in 2026?"
    for answer in ("The Group's non-controlling interest was Rs. 7,450,423 thousand in 2026.",
                   "The Group's non-controlling interest for 2026 was 7,450,423 Rs. '000."):  # a bare number before a units note
        case = demo.ask("demo:two", q, answer)
        assert case["output"]["action"] == "repair"
        assert "is the report's figure for “Non-controlling interests” in the statement of financial position, but FaithGuard " \
               "read the row of the same name in the statement of profit or loss" in " ".join(case["caveats"])
    assert notes(demo, q, "The Group's non-controlling interest was Rs. 1,966,330 thousand in 2026.", "demo:two") == ""


def test_last_year_is_the_latest_year_and_a_change_from_last_year_has_its_base(demo):
    r = demo.reports["demo:test"]
    text, period, note = read_question(r, "What was the Group's revenue last year?")
    assert period == "2026" and "Read “last year” as 2026" in note
    assert read_question(r, "What was the Group's revenue in the previous year?")[1] == "2025"  # the year before the latest
    assert read_question(r, "How did the Group's revenue change compared with last year?")[1] == "2026"
    assert "from Rs. 59,282,247 thousand in 2025 to Rs. 65,925,260 thousand in 2026" in draft(
        r, "How did the Group's revenue change compared with last year?")
    assert "from Rs. 5,164,800 thousand in 2025" in draft(r, "What was the Group's profit for the year in 2026 compared with last year?")


def test_the_template_writes_a_count_as_a_count_and_refuses_what_it_would_answer_wrongly(demo):
    r = demo.reports["demo:test"]
    assert draft(r, "What was the Group's number of employees in 2026?") == "The Group's number of employees was 4,917 in 2026."
    refused = {
        "What was the Group's net profit margin in 2026?": "margin",  # not the profit itself
        "What was the Group's net interst income in 2026?": "Did you mean “Net interest income”?",  # not the line "Income"
        "What dividend per share did the Company pay in 2026?": "no line item",  # not net asset value per share
    }
    for question, said in refused.items():
        with pytest.raises(Unanswerable, match=said):
            draft(r, question)


def test_a_year_the_report_lacks_is_refused_the_same_way_for_the_template_and_the_ai(demo):
    r = demo.reports["demo:test"]
    assert missing_year(r, "What was the Group's revenue in 2024?") == "The report covers 2025 and 2026 only; it has no figures for 2024."
    assert "2023" in missing_year(r, "What was the Group's revenue in FY23?")
    assert missing_year(r, "What was the Group's revenue in 2026?") is None
    with pytest.raises(Unanswerable, match="no figures for 2024"):
        draft(r, "What was the Group's revenue in 2024?")


def test_an_answer_about_another_year_or_part_or_a_sum_is_said_not_passed(demo):
    q = "What was the Group's revenue in 2026?"
    assert "The question asks about 2026, but the answer gives the 2025 figure." in notes(
        demo, q, "The Group's revenue in 2025 was Rs. 59,282,247 thousand.")
    assert "asks about the Group, but the answer gives the Company's figure" in notes(
        demo, "what was the groups revenue in 2026", "The revenue in 2026 was Rs. 4,000,000 thousand.")  # "groups" read
    assert _singular("What were the Group's placements with banks?") == "What were the Group's placements with banks?"
    assert notes(demo, q, "The Group's revenue was Rs. 65,925,260 thousand in 2026.") == ""
    combined = demo.ask("demo:test", "What were the Group's revenue and income combined in 2026?",
                        "The Group's revenue and income combined were Rs. 95,800,774 thousand in 2026.")
    said = " ".join(combined["caveats"])  # withheld, or "fixed" to one of the two lines
    assert (said.startswith("Not checkable: “Rs. 95,800,774 thousand” adds up several lines") if combined["output"]["action"] != "repair"
            else said.startswith("Careful, this fix is not trustworthy: “Rs. 95,800,774 thousand” adds up several lines"))


def test_an_open_question_says_whose_figures_it_accepted(demo):
    said = notes(demo, "How did Test Holdings perform in 2026?", "Test Holdings made a profit for the year of Rs. 3,500,217 thousand in 2026.")
    assert "Unknown line item: the question names no line of the report" in said and "Profit for the year" in said
    assert "The question names no part of the company" in said  # the figure is the Company's


def test_a_figure_with_no_year_of_its_own_is_said_before_and_after_a_fix(demo):
    r = demo.reports["demo:test"]
    item = make_item(r, "t", "What was the Group's revenue in 2026?",
                     "Group revenue was Rs. 65,925,260 thousand (2025: Rs. 59,282,247 thousand).", "typed")
    held = " ".join(caveats(item, detect(item), "abstain"))
    assert "One year per clause: “Rs. 65,925,260 thousand” has no year of its own, so FaithGuard read it as 2025" in held
    # every such figure has its own note, its figure quoted first, so the pages mark each one "?" and none "wrong"
    both = make_item(r, "t", "What was the Group's revenue in 2026?",
                     "Group revenue was Rs. 65,925,260 thousand (2025: Rs. 59,282,247 thousand), an increase of 11.2%.", "typed")
    one_year = [c for c in caveats(both, detect(both), "abstain") if c.startswith("One year per clause:")]
    assert [c.split("”")[0] for c in one_year] == ["One year per clause: “Rs. 65,925,260 thousand", "One year per clause: “11.2%"]
    case = demo.ask("demo:test", item.question.text, item.answer.text)
    if case["output"]["action"] == "repair":
        assert any(c.startswith("Careful, this fix is not trustworthy: FaithGuard reads one year per clause") for c in case["caveats"])


def test_a_looked_up_figure_with_up_from_is_withheld_for_its_direction_word_not_the_report_size(demo):
    r = demo.reports["demo:test"]
    item = make_item(r, "t", "What was the Group's revenue in 2026?",
                     "The Group's revenue was Rs. 65,925,260 thousand in 2026, up from Rs. 59,282,247 thousand in 2025.", "typed")
    said = " ".join(caveats(item, detect(item), "abstain"))
    assert "a direction word (“up”, “down”) beside a looked-up figure" in said and "large real reports" not in said


def test_rounded_working_is_not_called_a_contradiction_but_a_wrong_direction_is():
    r = made_up()
    q = "By what percentage did the Group's revenue grow in 2026?"

    def flagged(text):
        item = make_item(r, "t", q, text, "typed")
        return contradictions(text, detect(item))

    assert not flagged("Revenue rose from Rs. 59.3 billion in 2025 to Rs. 65.9 billion in 2026, an increase of 11.2%.")
    assert not flagged("The Group's revenue grew 11.2% to Rs. 65.9 billion in 2026 from Rs. 59.3 billion in 2025.")
    assert flagged("The Group's revenue rose 14.2% from Rs. 59.3 billion in 2025 to Rs. 65.9 billion in 2026.")
    said = flagged("The Group's revenue fell by Rs. 6,643,013 thousand from Rs. 59,282,247 thousand in 2025 to "
                   "Rs. 65,925,260 thousand in 2026.")
    assert said and "it says “fell”" in said[0] and "is a rise" in said[0]


def test_a_coincidental_match_is_loose_and_a_swapped_direction_word_is_written_or_said():
    loose = ClaimCheck(claim_id="k1", verdict="unsupported", slots=["metric", "sign"], cells=["t1r9c1", "t1r4c1"],
                       intended=Context(metric="total revenues"), relation="share", fix="growth(t1r2c1, t1r2c2)")
    sign = loose.model_copy(update={"slots": ["sign"], "relation": "cell", "cells": ["t1r2c1"], "fix": "t1r2c1"})
    assert _loose(loose) and not _loose(sign)  # a real sign error on the asked line still warns
    text = "Profit recorded a decline of 25.4% in 2026."
    det = DetectorOutput(item_id="t", detector="test", claims=extract_claims(text), risk=0.0)
    rate = det.claims[0]
    swapped = [(*rate.direction_span, "grow"), (rate.start, rate.end, "5.5%")]  # what the frozen executor writes
    assert _bad_wording(text, det, swapped) == [("a grow of", "its noun")]
    assert apply(text, _tidy(text, det, swapped)) == "Profit recorded a growth of 5.5% in 2026."


# ---------------------------------------------------------------------------
# The third mock panel (30 Oct): each test a finding, on made-up tables
# ---------------------------------------------------------------------------

INCOME = [["Statement of profit or loss", "Group", "Group", "Company", "Company"], ["Rs. '000", "2026", "2025", "2026", "2025"],
          ["Revenue", "65,925,260", "59,282,247", "4,000,000", "3,500,000"],
          ["Gross profit", "18,429,630", "16,936,536", "1,200,000", "1,000,000"],
          ["Profit before tax", "6,935,000", "6,900,000", "3,700,000", "2,400,000"],
          ["Profit for the year", "5,035,750", "5,164,800", "3,500,217", "2,243,000"],
          ["Total assets", "55,740,093", "48,200,000", "10,832,013", "9,900,000"],
          ["Stated capital", "1,000,000", "1,000,000", "1,000,000", "1,000,000"]]


def report_of(grid, rid="demo:inc", name="Test Holdings PLC", currency="LKR") -> Report:
    return Report(rid, name, "LK", Evidence(tables=[table_from_grid("t1", grid, currency=currency)]), True)


@pytest.fixture(scope="module")
def inc(demo):
    demo.reports["demo:inc"] = report_of(INCOME)
    return demo


def held(report, question, answer):
    item = make_item(report, "t", question, answer, "typed")
    return " ".join(caveats(item, detect(item), "abstain"))


def test_a_right_figure_fixed_into_another_line_the_answer_names_is_said_not_trustworthy(inc):
    """F1, F2, W3-05: "gross profit for the year ended ..." read as profit for the year; a second line in the sentence."""
    q = "What was the Group's gross profit in 2026?"
    case = inc.ask("demo:inc", q, "The Group's gross profit for the year ended 31 March 2026 was Rs. 18.43 billion.")
    assert case["output"]["action"] == "repair"
    assert ("Careful, this fix is not trustworthy: “Rs. 18.43 billion” is the report's figure for “Gross profit”, the line the question "
            "asks about, but FaithGuard read “Profit for the year” in the answer's words") in " ".join(case["caveats"])
    said = notes(inc, "How did the Group's total assets change in 2026?", "The Group's total assets rose to Rs. 55.7 billion in 2026 from "
                 "Rs. 48.2 billion in 2025, while its profit for the year fell by Rs. 129.1 million.", "demo:inc")
    assert "“Rs. 48.2 billion” is the report's figure for “Total assets”, the line the question asks about" in said
    # a wrong gross profit fixed to the right one is a fix; the year written first is sent
    fixed = inc.ask("demo:inc", q, "The Group's gross profit was Rs. 19.43 billion in 2026.")
    assert fixed["output"]["action"] == "repair" and fixed["caveats"] == []
    assert notes(inc, q, "For the year ended 31 March 2026, the Group's gross profit was Rs. 18.43 billion.", "demo:inc") == ""


def test_another_line_given_openly_is_said_as_another_year_or_part_is(inc):
    """F8"""
    q = "What was the Group's profit for the year in 2026?"
    assert notes(inc, q, "The Group's profit before tax was Rs. 6,935,000 thousand in 2026.", "demo:inc").startswith(
        "The question asks about “Profit for the year”, but the answer gives the figure for “Profit before tax”.")
    assert notes(inc, q, "The Group's profit for the year was Rs. 5,035,750 thousand in 2026.", "demo:inc") == ""


def test_a_total_given_as_a_change_and_a_figure_with_no_unit_are_said(inc):
    """S1, S2: the checker supports both against a cell."""
    q, level = "How did the Company's profit for the year change in 2026?", "The Company's profit for the year increased by Rs. 3,500,217 thousand in 2026."
    assert notes(inc, q, level, "demo:inc").startswith(
        "A total given as a change: “Rs. 3,500,217 thousand” follows “increased by”, but it is the report's 2026 figure for the Company's "
        "profit for the year, not the change from 2025 (Rs. 1,257,217 thousand).")
    assert "Every number is supported" not in held(report_of(INCOME), q, level)
    assert notes(inc, q, "The Company's profit for the year increased by Rs. 1,257,217 thousand in 2026.", "demo:inc") == ""
    q = "What were the Group's total assets in 2026?"
    assert notes(inc, q, "The Group's total assets were 55,740,093 in 2026.", "demo:inc").startswith(
        "No unit: “55,740,093” has no unit, but the table is in thousands, so as written it is 1,000 times too small")
    for right in ("The Group's total assets were 55,740,093 Rs. '000 in 2026.", "The Group's total assets were Rs. 55,740,093 thousand in 2026."):
        assert notes(inc, q, right, "demo:inc") == ""


def test_a_short_name_is_read_as_a_line_only_when_the_line_s_main_words_are_in_it(demo):
    """W3-01, W3-06: "revenue" is not "Net other revenue"; it is still "Revenue from contracts with customers"."""
    other = report_of([["Statement", "Group", "Group"], ["Rs. '000", "2026", "2025"], ["Income", "29,875,514", "27,000,000"],
                       ["Net other revenue", "1,901,411", "1,700,000"], ["Profit for the year", "5,035,750", "5,164,800"]], "demo:other")
    demo.reports["demo:other"] = other
    assert read_question(other, "What was the Group's revenue in 2026?")[2] == ""
    with pytest.raises(Unanswerable, match="no line item"):
        draft(other, "What was the Group's revenue in 2026?")
    case = demo.ask("demo:other", "What was the Group's revenue in 2026?", "The Group's revenue was Rs. 29,875,514 thousand in 2026.")
    assert case["output"]["action"] != "repair" and " ".join(case["caveats"]).startswith("Unknown line item:")
    rcc = report_of([["Statement", "Group", "Group"], ["Rs. '000", "2026", "2025"],
                     ["Revenue from contracts with customers", "61,010,849", "50,100,000"]], "demo:rcc")
    assert read_question(rcc, "What was the Group's revenue in 2026?")[2].endswith(
        "FaithGuard reads “revenue” as the report's line “Revenue from contracts with customers”.")


def test_a_split_financial_year_is_read_as_its_second_year(demo):
    """W3-02: "FY25/26" is the 2026 column; the checker reads it in an answer as 2025, and the screen says so."""
    r = demo.reports["demo:test"]
    text, _, note = read_question(r, "What was the Group's revenue in FY25/26?")
    assert "FY2025/26" in text and note == "Read “FY25/26” as FY2025/26, the 2026 column."
    assert draft(r, "What was the Group's revenue in FY25/26?") == "The Group's revenue was Rs. 65,925,260 thousand in 2026."
    assert missing_year(r, "What was the Group's revenue in FY24/25?") is None
    case = demo.ask("demo:test", "What was the Group's revenue in FY25/26?", "The Group's revenue for FY25/26 was Rs. 65,925,260 thousand.")
    assert case["output"]["action"] == "repair"
    assert ("Careful, this fix is not trustworthy: “Rs. 65,925,260 thousand” is given for “FY25/26”, which the frozen checker reads as "
            "2025") in " ".join(case["caveats"])


def test_a_rate_is_checked_against_two_levels_of_its_own_line_only():
    """W3-03, F10: "increased by X, or Y%, to Z", another part's figure, another line's rate or direction word."""
    r = made_up()

    def flagged(question, text):
        return contradictions(text, detect(make_item(r, "t", question, text, "typed")))

    profit = "How did the Group's profit for the year change in 2026?"
    assert not flagged("How did the Group's net interest income change in 2026?", "The Group's net interest income increased by "
                       "Rs. 1,482,497 thousand, or 11.8%, to Rs. 14,002,435 thousand in 2026.")
    assert not flagged("By what percentage did the Group's revenue grow in 2026?", "The Group's revenue grew 11.2% to Rs. 65,925,260 "
                       "thousand in 2026, while the Company's revenue was Rs. 4,000,000 thousand in 2026.")
    assert not flagged(profit, "The Group's profit for the year fell from Rs. 5,164,800 thousand in 2025 to Rs. 5,035,750 thousand in "
                       "2026, while revenue rose 11.2%.")
    assert not flagged(profit, "The Group's profit for the year fell from Rs. 5,164,800 thousand in 2025 to Rs. 5,035,750 thousand in "
                       "2026, while total assets rose by Rs. 7,540,093 thousand.")
    assert flagged(profit, "The Group's profit for the year rose from Rs. 5,164,800 thousand in 2025 to Rs. 5,035,750 thousand in 2026.")


def test_a_fix_to_the_year_the_answer_gives_is_not_said_untrustworthy(inc):
    """W3-04, W3-09, W3-10: a yearless wrong-year figure, the report's own count, "higher than in 2025", an unchanged line."""
    for report, question, answer in [
            ("demo:test", "What was the Group's revenue in 2026?", "The Group's revenue was Rs. 59,282,247 thousand."),
            ("demo:test", "By what percentage did the Group's revenue grow in 2026?", "The Group's revenue grew 11.2% to Rs. 59.3 billion."),
            ("demo:test", "How many employees did the Group have in 2026?", "The Group had 4,428 employees in 2026."),
            ("demo:test", "What was the Group's revenue in 2026?", "In 2026 the Group's revenue of Rs. 65,952,260 thousand was 11.2% higher "
             "than in 2025."),
            ("demo:inc", "How did the Group's stated capital change in 2026?", "The Group's stated capital was Rs. 1,000,000 thousand in "
             "2026, unchanged from Rs. 1,100,000 thousand in 2025.")]:
        case = inc.ask(report, question, answer)
        assert case["output"]["action"] == "repair" and case["caveats"] == [], (answer, case["caveats"])
    text = "Kinsale reported $414.8 million of net income in 2025."
    assert _own_year(text, extract_claims(text), 0)


def test_a_year_in_brackets_after_a_figure_is_said_to_be_skipped(demo):
    """F4: "X (FY2026) vs Y (FY2025)"."""
    q = "What was the Group's profit for the year in 2026?"
    a = "Group profit for the year: Rs. 5,035,750 thousand (FY2026) vs Rs. 5,164,800 thousand (FY2025)."
    assert ("One year per clause: “Rs. 5,164,800 thousand” has its year in brackets after it (“(FY2025)”), which FaithGuard skips, so "
            "it read it as 2026") in held(made_up(), q, a)
    case = demo.ask("demo:test", q, a)
    assert case["output"]["action"] == "repair" and "but the answer gives it for 2025" in " ".join(case["caveats"])


def test_a_fix_that_gives_another_year_than_asked_is_said(demo):
    """F5: as the same text typed in is."""
    said = notes(demo, "What was the Group's revenue in 2026?", "The Group's revenue was Rs. 65.9 billion in 2025.")
    assert "The question asks about 2026, but the answer gives the 2025 figure." in said


def test_withheld_answers_get_the_reason_that_fits_them():
    """F6, P3-PROJ-09: a rate with only the new year's figure; the generic note does not blame table size alone."""
    r, q = made_up(), "By what percentage did the Group's revenue grow in 2026?"
    assert "a growth rate given with only the new year's figure" in held(r, q, "The Group's revenue grew 11.2% to Rs. 65,925,260 "
                                                                         "thousand in 2026.")
    said = held(r, q, "The Group's revenue grew 11.2% from Rs. 59,282,247 thousand in 2025 to Rs. 65,925,260 thousand in 2026.")
    assert "only the new year's figure" not in said and "on some wordings" in said


def test_a_page_number_and_a_fall_in_accounting_brackets_are_said():
    """F7, F3"""
    r = made_up()
    assert "“186” looks like a page or note number, not a report figure" in held(
        r, "What was the Group's net asset value per share in 2026?", "The Group's net asset value per share was Rs. 45 in 2026, compared "
        "with Rs. 40 in 2025 (page 186).")
    q = "How did the Group's profit for the year change in 2026?"
    assert ("Accounting brackets: “(2.5%)” is written in accounting brackets (a fall), but the frozen checker reads a bracketed rate as a "
            "rise (a known limitation); read as a fall, it matches the report.") in held(
        r, q, "The Group's profit for the year changed by (2.5%) in 2026.")
    assert "Accounting brackets" not in held(r, "What was the Group's revenue in 2026?", "The Group's revenue was Rs. 65,925,260 thousand "
                                             "in 2026, with income of Rs. 29,875,514 thousand (3%).")  # an aside, not a fall


def test_a_fix_in_the_answer_s_unit_prints_the_cell_with_its_unit_and_warns_when_far_off(inc):
    """F9"""
    said = notes(inc, "What were the Group's total assets in 2026?", "The Group's total assets were Rs. 55.7 trillion in 2026.", "demo:inc")
    assert "Rounded: the fix keeps the answer's unit, so the report's figure Rs. 55,740,093 thousand is written as" in said
    said = notes(inc, "What were the Company's total assets in 2026?", "The Company's total assets were Rs. 10.8 trillion in 2026.", "demo:inc")
    assert said.startswith("Careful, this fix is not trustworthy: the fix keeps the answer's unit, so it writes the report's figure "
                           "Rs. 10,832,013 thousand as Rs. 0.011 trillion, 2% off")


def test_a_wrong_direction_word_beside_a_printed_change_is_said(demo):
    """P3-PROJ-03: a rate read from a "Change %" column; a right word is not noted."""
    demo.reports["demo:chg"] = report_of([["Statement", "Group", "Group", "Group"], ["Rs. '000", "2025", "2024", "Change %"],
                                          ["Profit for the year", "32,571,337", "28,703,260", "13"]], "demo:chg")
    q = "By what percentage did the Group's profit for the year change in 2025?"
    for wrong, word in (("The Group's profit for the year fell by 13% in 2025.", "fell"),
                        ("In 2025 the Group's profit for the year was 13% lower than in 2024.", "lower")):
        assert notes(demo, q, wrong, "demo:chg") == (f"Direction not checked: “13%” is read from the report's printed change column, so "
                                                     f"FaithGuard did not check the word “{word}” beside it: the report prints 13 there, a "
                                                     "rise (a known limitation).")
    assert notes(demo, q, "The Group's profit for the year rose by 13% in 2025.", "demo:chg") == ""


def test_smaller_notes_say_what_happened(demo):
    """W3-13, W3-14, R2, F2: "combined" for one line; "an 11.2% grow"; a chance difference names no bracketed line; an
    explanation that names no line the checker read."""
    case = demo.ask("demo:test", "What was the Group's combined revenue in 2026?", "The Group's combined revenue was Rs. 59,282,247 "
                    "thousand in 2026.")
    assert case["output"]["action"] == "repair" and not any("adds up several lines" in c for c in case["caveats"])
    said = notes(demo, "By what percentage did the Group's revenue grow in 2026?", "The Group's revenue went from Rs. 59.3 billion in "
                 "2025 to Rs. 65.9 billion in 2026, an 11.2% decline.")
    assert "so the sentence reads “an 11.2% grow”" in said
    demo.reports["demo:ceo"] = report_of([["Statement", "Group", "Group", "Company", "Company"], ["Rs. '000", "2026", "2025", "2026", "2025"],
                                          ["Revenue", "65,925,260", "59,282,247", "4,000,000", "3,500,000"],
                                          ["Remeasurement of retirement benefit liability", "(15,310)", "(10,000)", "29,392", "20,000"]],
                                         "demo:ceo")
    said = notes(demo, "What was the CEO's salary in 2026?", "The CEO's salary was Rs. 45 million in 2026.", "demo:ceo")
    assert "printed in brackets" not in said and "or a growth rate, difference, share or ratio of two of them" in said
    said = held(report_of(INCOME), "What was the Group's revenue in 2026?", "The Group's revenue was Rs. 65,925,260 thousand in 2026, "
                "driven by higher gross profit.")
    assert said.endswith("FaithGuard checks the numbers, not the words around them: “driven by higher gross profit” was not checked.")
    assert "was read as" not in said  # the figure was read as revenue, the line its own clause names


def test_the_template_answers_fair_names_and_refuses_what_it_would_get_wrong():
    """W3-11, W3-12, W3-15"""
    r = made_up()
    assert draft(r, "What was the Group's net profit for the year in 2026?") == ("The Group's profit for the year was Rs. 5,035,750 "
                                                                               "thousand in 2026.")
    assert draft(r, "What was the Group's revenue figure for 2026?") == "The Group's revenue was Rs. 65,925,260 thousand in 2026."
    assert draft(r, "What was the Group's revenue the year before last?") == "The Group's revenue was Rs. 59,282,247 thousand in 2025."
    assert "Read “the year before last” as 2025" in read_question(r, "What was the Group's revenue the year before last?")[2]
    text, _, note = read_question(r, "What were the total assets of the Company and its subsidiaries in 2026?")
    assert "the Group" in text and note == "Read “the Company and its subsidiaries” as the Group."
    label = report_of([["Statement", "Group", "Group"], ["Rs. '000", "2026", "2025"],
                       ["Trade receivables, net of impairment of Rs. 27,328 in 2026", "124,593", "140,027"]])
    with pytest.raises(Unanswerable, match="with figures in it"):
        draft(label, "What were the Group's trade receivables in 2026?")
    one = Report("US:KNSL", "Kinsale Capital Group", "US", Evidence(tables=[table_from_grid(
        "t1", [["Balance sheet", "2025", "2024"], ["$ in thousands", "2025", "2024"], ["Total assets", "6,040,000", "4,890,000"]],
        currency="USD")]), True)
    assert read_question(one, "What were Kinsale Capital Group's total assets in 2025?")[2].endswith(
        "the report has no Group column, so that word of the company's name is left out.")


def test_the_other_company_guard_knows_the_company_s_own_names():
    """W3-07, W3-08: a misspelling, "Holding Company", "Co.", the ticker, a line's name are this company; "of HNB" is not."""
    sun = made_up("Sunshine Holdings PLC")
    knsl = Report("US:KNSL", "Kinsale Capital Group", "US", made_up().evidence, True)
    for report, fine in ((sun, "What was Sunshine Holding's revenue in 2026?"), (sun, "What was the Holding Company's profit for the year in 2026?"),
                         (made_up("Tokyo Cement Company (Lanka) PLC"), "What was Tokyo Cement Co.'s revenue in 2026?"),
                         (knsl, "What was KNSL's revenue in 2025?"), (sun, "What was Net Interest Income's growth in 2026?"),
                         (sun, "How did Revenue perform in 2026?"), (sun, "What was the amount of OCI in 2026?")):
        assert other_company(report, fine) is None, fine
    assert "asks about HNB." in other_company(made_up("Sampath Bank PLC"), "What was the net interest income of HNB in 2025?")
    assert "asks about Apple" in other_company(sun, "What was Apple's revenue in 2026?")


def test_a_straight_apostrophe_is_rewritten_only_inside_a_line_name():
    """F11: the rest of a pasted answer is shown and sent as pasted."""
    vocab = report_of([["Balance sheet", "Group", "Group"], ["Rs. '000", "2026", "2025"], ["Stockholders’ equity", "1,960,000", "1,483,561"],
                       ["Total liabilities", "2,307,395", "2,000,000"]]).vocab()
    assert typography("Kinsale's stockholders' equity was Rs. 1.96 billion.", vocab) == "Kinsale's stockholders’ equity was Rs. 1.96 billion."
    assert typography("Sunshine Holdings' total liabilities were Rs. 2.31 billion.", vocab) == (
        "Sunshine Holdings' total liabilities were Rs. 2.31 billion.")


def test_a_planted_wrong_year_never_writes_a_figure_the_answer_already_gives():
    """R6: a second row of the same name and figures ("rose 0.0% from X to X")."""
    r = report_of([["Statement of profit or loss", "Group", "Group"], ["Rs. '000", "2026", "2025"],
                   ["Profit for the year", "5,035,750", "5,164,800"], ["Other comprehensive income", "100,000", "90,000"],
                   ["Profit for the year", "5,035,750", "5,164,800"]])
    q = "By what percentage did the Group's profit for the year grow in 2026?"
    item = make_item(r, "t", q, draft(r, q), "template")
    assert not [text for label, text in plant(item, detect(item)) if label.startswith("Wrong year")]


# ---------------------------------------------------------------------------
# Integration of the third panel's fixes
# ---------------------------------------------------------------------------


def test_a_fall_s_rate_with_the_down_word_on_another_figure_is_said(inc):
    """W3-03 (related): "decreased by X, or Y%" is withheld with Y% read as a rise; the screen says the rate is right."""
    q = "How did the Group's profit for the year change in 2026?"
    right = notes(inc, q, "The Group's profit for the year decreased by Rs. 129.1 million, or 2.5%, to Rs. 5.04 billion in 2026.", "demo:inc")
    assert "Rate read as a rise: “2.5%” has no up/down word of its own (the sentence's “decreased” is on Rs. 129.1 million)" in right
    assert "read as a fall, as the sentence says, it matches the report" in right
    wrong = notes(inc, q, "The Group's profit for the year decreased by Rs. 129.1 million, or 3.5%, to Rs. 5.04 billion in 2026.", "demo:inc")
    assert "Rate read as a rise" not in wrong


def test_the_grew_to_reason_is_given_only_for_a_rate_and_a_figure_of_one_line():
    """F6: a rate of another line beside the figure gets the general reason, not "grew X% to Y"."""
    r = report_of(INCOME)
    one = held(r, "By what percentage did the Group's revenue grow in 2026?", "The Group's revenue grew 11.2% to Rs. 65.9 billion in 2026.")
    assert "only the new year's figure" in one
    two = held(r, "What was the Group's revenue in 2026?", "The Group's revenue was Rs. 65.9 billion in 2026, while gross profit grew 8.8%.")
    assert "only the new year's figure" not in two and "Every number is supported, yet the policy withholds the answer" in two


def test_no_mistake_is_planted_in_a_fix_the_screen_warns_about_or_one_that_answers_another_year(inc):
    """F1, F5: a right figure "fixed" into another line's, and a fix to the year the answer names, are no base for tricks."""
    moved = inc.ask("demo:inc", "What was the Group's gross profit in 2026?",
                    "The Group's gross profit for the year ended 31 March 2026 was Rs. 18.43 billion.")
    other_year = inc.ask("demo:inc", "What was the Group's revenue in 2026?", "The Group's revenue was Rs. 65.9 billion in 2025.")
    assert any(c.startswith("Careful, this fix is not trustworthy") for c in moved["caveats"])
    assert any(c.startswith("The question asks about 2026, but the answer gives the 2025 figure") for c in other_year["caveats"])
    for case in (moved, other_year):
        assert case["output"]["action"] == "repair"
        out = inc.plant_errors(case["id"])
        assert out["on"] == "original" and not out["edits"]
