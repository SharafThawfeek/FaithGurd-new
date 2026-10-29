"""The presentation demo (demo/), on the fictional items only: no pilot data, models or GPU needed."""

import ast
import json
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parent.parent / "demo"
sys.path.insert(0, str(DEMO))

from app import bad_answer, friendly  # noqa: E402
from ask import bad_question, draft, question_type  # noqa: E402
from cases import Demo, UnknownExample, safe_path  # noqa: E402
from views import channel_a_view  # noqa: E402

from faithguard.demo import bank_items  # noqa: E402


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("demo")
    return Demo(cache_path=tmp / "cache.json", config=tmp / "no-examples.json")


def test_fictional_examples_take_their_action_and_their_edits_too(demo):
    assert len(demo.examples) == len(bank_items())
    for e in demo.examples.values():
        case = demo.case(e.item.id)
        json.dumps(case)
        assert case["output"]["action"] == e.expect
        for label, answer, expect in e.edits:
            assert demo.case(e.item.id, answer)["output"]["action"] == expect, label


def test_repaired_output_cites_the_cells_of_the_new_numbers(demo):
    # not the Bank cells the wrong numbers came from
    assert demo.case("demo-lk-2:entity")["output"]["evidence_cells"] == ["t1r3c1", "t1r3c2"]
    assert demo.case("demo-lk-4:period")["output"]["evidence_cells"] == ["t1r3c1"]


def test_scale_and_sign_errors_point_at_the_right_cells_read_wrongly(demo):
    scale = demo.case("demo-lk-3:scale")["catch"]["claims"][0]
    assert scale["same_cell"] and scale["came_from"] == scale["asked"] == ["t1r3c1"] and "scale" in scale["misread"]
    sign = demo.case("demo-lk-5:sign")["catch"]["claims"][0]
    assert sign["same_cell"] and "direction" in sign["misread"] and sign["expected"] == "a rise of 9.3%"
    entity = demo.case("demo-lk-2:entity")["catch"]["claims"][1]
    assert entity["asked"] == ["t1r3c1"] and entity["came_from"] == ["t1r3c3"] and not entity["loose_match"]


def test_new_numbers_sit_where_the_changes_say(demo):
    for example in ("demo-lk-2:entity", "demo-lk-3:scale", "demo-lk-4:period", "demo-lk-5:sign"):
        check = demo.case(example)["correct"]["rule"]["check"]
        assert check["passed"] and [g["passed"] for g in check["checks"]] == [True] * 5
        for change in check["changes"]:
            assert check["text"][change["start"]:change["end"]] == change["new"]
            assert change["cells"]  # a corrected direction word shows its calculation's cells too


def test_cannot_fix_shows_the_reason_and_what_the_report_holds(demo):
    case = demo.case("demo-lk-6:missing_operand")
    stop = case["correct"]["rule"]["cannot_fix"]
    assert stop["reason"] == "missing_operand" and stop["explain"]
    assert "Profit after tax" in stop["report_rows"] and case["output"]["report_rows"]


def test_edited_answers_never_raise(demo):
    odd = ["hello world", "12", "Rs. 1e9999 million rose 99999999999999999999999% (5) 3/4 $,,, 12.3.4",
           "Group profit after tax rose 7.0% to Rs. 12,450 million in FY2025 and 9.3% and 14,213 and fell 3% from 2023.",
           "Group profit after tax fell (1,234) to Rs. 0 million", "۱۲٣ rupees — 14,213 million"]
    for text in odd:
        case = demo.case("demo-lk-1:none", text)
        assert case["edited"] and case["output"]["action"] in ("send", "repair", "abstain")
        assert case["catch"]["channel_a"]["source"] is None  # never "computing…" when Channel A is not live


def test_bad_requests_get_a_friendly_message():
    assert bad_answer("   ") and bad_answer("x" * 5000) and bad_answer("profit 😀 rose") and bad_answer(12)
    assert bad_answer("Group profit after tax rose 9.3%.") is None
    assert friendly(UnknownExample("nope")).startswith("Unknown example")
    assert "could not process" in friendly(KeyError("t9r9c9"))


def test_channel_a_spans_widen_to_the_whole_number(demo):
    item = demo.examples["demo-lk-2:entity"].item
    det = demo.case("demo-lk-2:entity")  # claims: "7.0%" at 28-32, "Rs. 12,450 million" at 36-54
    tokens = [[28, 29, 0.9, 1], [29, 32, 0.2, 1], [40, 42, 0.8, 0], [42, 45, 0.7, 0]]
    from faithguard.detect import detect

    view = channel_a_view(item, tokens, "live", det=detect(item))
    assert [s["text"] for s in view["spans"]] == ["7.0%", "Rs. 12,450 million"]
    assert det["catch"]["claims"][0]["text"] == "7.0%"


def test_own_questions_get_a_type_from_their_wording():
    assert question_type("What was the Group's profit after tax in 2025?") == "lookup"
    assert question_type("By what percentage did the Bank's deposits grow in 2025?") == "growth"
    assert question_type("How did the Group's revenue change in 2026 compared with 2025?") == "growth"
    assert question_type("By how much did net interest income increase?") == "difference"
    assert question_type("What share of total assets were loans?") == "share"
    assert bad_question("  ") and bad_question("x" * 400) and bad_question(None)
    assert bad_question("What was the Group's revenue?") is None


def test_a_line_item_named_in_the_question_does_not_set_its_type():
    from faithguard.claims import Vocabulary
    from faithguard.tables import table_from_grid

    grid = [["t", "Group", "Group"], ["Rs. '000", "2025", "2024"], ["Change in fair value of investments", "1,200", "900"],
            ["Share of profit of associates", "300", "250"]]
    vocab = Vocabulary(table_from_grid("t1", grid, currency="LKR").cells)
    assert question_type("What was the Group's change in fair value of investments in 2025?", vocab) == "lookup"
    assert question_type("What was the Group's share of profit of associates in 2025?", vocab) == "lookup"
    assert question_type("By what percentage did the Group's share of profit of associates grow in 2025?", vocab) == "growth"


def test_the_template_takes_the_base_year_the_question_names_and_refuses_a_change_without_one(demo):
    report = demo.reports["demo:fictional-bank"]
    assert "from Rs. 13,004,180 thousand in 2024" in draft(report, "By what percentage did the Group's profit after tax grow from 2024 to 2025?")
    with pytest.raises(ValueError):
        draft(report, "By what percentage did the Group's profit after tax grow in 2024?")  # no 2023 in the table


def test_questions_are_read_as_their_writers_meant(demo):
    from ask import read_question

    bank = demo.reports["demo:fictional-bank"]
    assert read_question(bank, "What was the Group's net interest income in FY24?")[1] == "2024"
    assert read_question(bank, "What was the Group's net interest income in the previous year?")[1] == "2024"
    assert read_question(bank, "What was the Group's net interest income in 2025?")[1] is None  # the checker reads 4-digit years itself
    assert "44,102,870" in draft(bank, "What was the Group's net interest income in FY24?")
    real = next((r for r in demo.reports.values() if r.real and " Bank" in r.name), None)
    if real is not None:  # the pilot data is on this laptop
        text, _, note = read_question(real, f"What was {real.name.split()[0]} Bank's profit for the year in 2025?")
        assert " Bank" not in text and note


def test_the_template_refuses_what_it_cannot_write_right():
    from ask import Report
    from faithguard.records import Evidence
    from faithguard.tables import table_from_grid

    grid = [["Statement", "Group", "Group"], ["Rs. '000", "2025", "2024"], ["Loans and advances", "1,000", "900"],
            ["Cost of sales", "(700)", "(650)"], ["Loans and advances", "50", "40"]]
    report = Report("demo:test", "Test PLC", "LK", Evidence(tables=[table_from_grid("t1", grid, currency="LKR")]), True)
    for question in ("What were the Group's loans and advances in 2025?",  # two rows of that name, different figures
                     "What was the Group's cost of sales in 2025?",  # printed in brackets
                     "By what percentage did the Group's cost of sales grow in 2025?"):
        with pytest.raises(ValueError):
            draft(report, question)


def test_own_question_on_the_fictional_bank_template_answer_sent_and_planted_errors_repaired_back(demo):
    report = demo.reports["demo:fictional-bank"]
    chips = demo.chips(report.id)
    questions = chips["suggestions"]
    assert len(questions) >= 3 and chips["line_items"]
    for question in questions:
        answer = demo.ask_draft(report.id, question)["answer"]
        case = demo.ask(report.id, question, answer)
        assert case["group"] == "ask" and case["output"]["action"] == "send" and not case["caveats"], question
        assert case["generator"].startswith("a template")
        planted = demo.plant_errors(case["id"])["edits"]
        kinds = {e["label"].split(":")[0] for e in planted}
        assert {"Wrong entity", "Wrong scale", "Maths slip"} <= kinds, question
        assert "Wrong year" in kinds or "grow" in question or "change" in question, question
        for e in planted:
            rerun = demo.case(case["id"], e["answer"])
            assert rerun["output"]["action"] == e["expect"] == "repair", e["label"]
            assert same_figures(rerun["output"]["text"], answer), e["label"]  # the repair gives the right figures back


def same_figures(text: str, reference: str) -> bool:
    """Each number equals the reference's to the coarser of the two printed precisions, with the same direction."""
    from decimal import Decimal

    from faithguard.claims import extract_claims

    got, want = extract_claims(text), extract_claims(reference)
    if len(got) != len(want):
        return False
    for a, b in zip(got, want):
        unit = max(Decimal(1).scaleb(-c.decimals) * (Decimal(10) ** c.scale if c.kind == "amount" else 1) for c in (a, b))
        if a.direction != b.direction or abs(a.value - b.value) > unit / 2:
            return False
    return True


def test_typed_answers_are_labelled_typed_and_unknown_reports_refused(demo):
    case = demo.ask("demo:fictional-bank", "What was the Group's profit after tax in 2025?", "It was Rs. 9 million.")
    assert case["generator"] == "typed in the demo" and case["output"]["action"] != "send"
    assert demo.example(case["id"]).group == "ask" and case["id"] not in {e["id"] for e in demo.listing()}
    with pytest.raises(UnknownExample):
        demo.ask("LK:NOPE", "What was revenue?", "Rs. 1 million.")
    assert "error" in demo.ask_ai("demo:fictional-bank", "What was revenue?")  # no models in the tests
    assert "error" in demo.ask_draft("demo:fictional-bank", "What was the Group's return on equity in 2025?")
    listing = demo.report_listing()
    assert listing and all(r["suggestions"] and r["evidence"]["tables"] for r in listing)
    assert all(item["question"].endswith("?") for r in listing for item in r["line_items"])


def test_the_demo_never_reads_gold_or_blinded_data():
    for name in ("app.py", "cases.py", "views.py", "models.py", "results.py", "ask.py"):
        tree = ast.parse((DEMO / name).read_text(encoding="utf-8"))
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not {m for m in imported if m.startswith(("faithguard.gold", "faithguard.evaluate", "faithguard.labelling"))}, name
    for blinded in ("data/benchmark-build/main/items.jsonl", "data/benchmark-build/main-auto", "labelling/main-tasks.json"):
        with pytest.raises(ValueError):
            safe_path(blinded)
    safe_path("data/benchmark-build/items.jsonl")
