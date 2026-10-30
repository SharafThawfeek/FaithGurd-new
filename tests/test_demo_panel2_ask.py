"""Own questions in the demo (demo/ask.py) against the second mock panel's inputs, on made-up tables: no pilot data,
models or GPU needed. Each test is a finding: what was refused, written or said wrongly, and what is said now."""

import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parent.parent / "demo"
sys.path.insert(0, str(DEMO))

from ask import (Report, Unanswerable, _bad_wording, _loose, _singular, _tidy, caveats, contradictions, draft,  # noqa: E402
                 make_item, missing_year, other_company, read_question)
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
