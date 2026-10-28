"""The presentation demo (demo/), on the fictional items only: no pilot data, models or GPU needed."""

import ast
import json
import sys
from pathlib import Path

import pytest

DEMO = Path(__file__).resolve().parent.parent / "demo"
sys.path.insert(0, str(DEMO))

from app import bad_answer, friendly  # noqa: E402
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


def test_the_demo_never_reads_gold_or_blinded_data():
    for name in ("app.py", "cases.py", "views.py", "models.py", "results.py"):
        tree = ast.parse((DEMO / name).read_text(encoding="utf-8"))
        imported = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
        imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        assert not {m for m in imported if m.startswith(("faithguard.gold", "faithguard.evaluate", "faithguard.labelling"))}, name
    for blinded in ("data/benchmark-build/main/items.jsonl", "data/benchmark-build/main-auto", "labelling/main-tasks.json"):
        with pytest.raises(ValueError):
            safe_path(blinded)
    safe_path("data/benchmark-build/items.jsonl")
