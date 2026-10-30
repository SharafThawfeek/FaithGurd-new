"""The demo server's side of the second mock panel's fixes, on the fictional items only: no pilot data, models or GPU."""

import contextlib
import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEMO = ROOT / "demo"
sys.path.insert(0, str(DEMO))

import models  # noqa: E402
from app import READ_AT_START, bad_answer, local_changes, version  # noqa: E402
from ask import CONTRADICTION, UNKNOWN_LINE, bad_question, figures_match  # noqa: E402
from cases import KAGGLE_LABELS, Demo, load_examples  # noqa: E402
from models import ANSWER_TOKENS, MAX_FAILURES, LiveModels  # noqa: E402

from faithguard.demo import bank_items  # noqa: E402

BANK = "demo:fictional-bank"


@pytest.fixture()
def demo(tmp_path):
    return Demo(cache_path=tmp_path / "cache.json", config=tmp_path / "no-examples.json")


def test_the_budget_curve_is_a_list_of_points_and_the_precheck_guards_it(demo):
    from precompute import precheck

    curve = demo.certificate["budget_curve"]
    assert isinstance(curve, list) and curve and all("certified_share" in p for p in curve)
    assert isinstance(demo.certificate.get("budget_curve_neural", []), list)
    gold = {item.id: g for item, g, _ in bank_items()}
    lines, _ = precheck(demo, gold)
    assert lines[-1].startswith("Certification budget curve (LightGBM)") and lines[-1].endswith("OK.")
    demo.certificate = {**demo.certificate, "budget_curve": {"lightgbm": curve}}  # the shape that broke the chart
    broken, _ = precheck(demo, gold)
    assert broken[-1].endswith("NO: the chart would not draw.")


def test_sidebar_examples_and_their_edits_carry_the_on_screen_notes(demo):
    # a correct answer whose base year is not written is "repaired" into a rate from a figure to itself
    case = demo.case("demo-lk-1:none", "Group profit after tax rose 9.3% from Rs. 13,004 million to Rs. 14,213 million in FY2025.")
    assert case["output"]["action"] == "repair" and any(x.startswith(CONTRADICTION) for x in case["caveats"])
    case = demo.case("demo-lk-2:entity", "Bank profit after tax rose 7.0% to Rs. 12,450 million.")
    assert case["output"]["action"] == "send" and any("asks about the Group" in x for x in case["caveats"])
    assert case["report"]["name"] == "Fictional bank (made-up figures)"  # the meta line names the report, not an id


def test_the_screen_says_what_answers_the_question_and_relevance_compute(demo):
    # the frozen feature and gate check: a supported number on the question's line item, or any supported number when the
    # question names no line the checker reads; entity and year are not compared
    case = demo.case("demo-lk-2:entity", "Bank profit after tax rose 7.0% to Rs. 12,450 million.")
    label = next(f["label"] for f in case["control"]["features"] if f["name"] == "answers_question")
    assert label == ("a supported number is on the question's line item, or the question names no line the checker reads "
                     "(entity and year not compared)")
    assert case["control"]["question_line_named"] is True
    gate = next(g for g in demo.case("demo-lk-2:entity")["correct"]["rule"]["check"]["checks"] if g["name"] == "relevance")
    assert "answers the question" not in gate["about"] and "entity and year not compared" in gate["about"]
    assert "when the question names no line the checker reads" in gate["about"]
    # return on equity is no line of the tables: the "yes" comes from any supported number, and the case says so
    case = demo.case("demo-lk-6:missing_operand", "The Group's return on equity was 3.8% in FY2025.")
    feature = next(f for f in case["control"]["features"] if f["name"] == "answers_question")
    assert feature["value"] and case["control"]["question_line_named"] is False
    assert any(x.startswith(UNKNOWN_LINE) for x in case["caveats"])


def test_the_missing_operand_caption_says_what_is_sent(demo):
    caption = demo.example("demo-lk-6:missing_operand").caption
    assert "3.8%" in caption and "29.5%" in caption and "sent" in caption
    for figure in ("3.8%", "29.5%"):  # each equals a ratio of two cells of another line, and is sent with a warning
        case = demo.case("demo-lk-6:missing_operand", f"The Group's return on equity was {figure} in FY2025.")
        assert case["output"]["action"] == "send" and any(x.startswith(UNKNOWN_LINE) for x in case["caveats"])
    assert demo.case("demo-lk-6:missing_operand")["output"]["action"] == "abstain"


def test_a_rise_of_only_for_a_change_and_a_cannot_fix_says_when_the_line_is_unknown(demo):
    q = "What was the Group's profit after tax in 2025?"
    claim = demo.ask(BANK, q, "Group profit after tax fell to Rs. 12,000 million in 2025.")["catch"]["claims"][0]
    assert claim["direction"] and claim["relation"] == "cell" and claim["expected"] == "Rs. 14,213 million"
    claim = demo.ask(BANK, "By what percentage did the Group's profit after tax grow in 2025?",
                     "Group profit after tax fell 9.3% in 2025.")["catch"]["claims"][0]
    assert claim["expected"] == "a rise of 9.3%"
    stop = demo.ask(BANK, "What did the Group earn in 2025?", "The Group earned Rs. 14,212,560 million in 2025.")["correct"]["rule"]
    assert stop["cannot_fix"]["reason"] == "ambiguous_evidence"
    assert stop["cannot_fix"]["explain"].startswith("the checker could not name the line item the question asks about")


def test_the_stored_kaggle_repairs_are_labelled_as_the_frozen_v1(tmp_path):
    item = bank_items()[1][0]
    item = item.model_copy(update={"id": "PILOT-1", "question": item.question.model_copy(update={"split": "dev"})})
    (tmp_path / "items.jsonl").write_text(item.model_dump_json() + "\n", encoding="utf-8")
    runs = next(iter(KAGGLE_LABELS))
    config = {"items": str(tmp_path / "items.jsonl"), "kaggle_outputs": runs, "kaggle_label": "trained repairer v1 candidate",
              "pilot": [{"id": "PILOT-1", "title": "t", "caption": "c"}]}
    (tmp_path / "examples.json").write_text(json.dumps(config), encoding="utf-8")
    pilot = [e for e in load_examples(tmp_path / "examples.json") if e.group == "pilot"]
    assert pilot and pilot[0].kaggle["run"] == KAGGLE_LABELS[runs]
    assert "candidate" not in KAGGLE_LABELS[runs] and "frozen, D-101" in KAGGLE_LABELS[runs]


class FakeGenerator:
    """Stands in for the Generator inside the ModelRepairer: returns a fixed reply, no torch, no GPU."""

    torch = SimpleNamespace(no_grad=contextlib.nullcontext)

    def __init__(self, text: str, tokens: list[int], end_id: int = 2):
        self.text, self.tokens = text, tokens
        self.model = SimpleNamespace(generation_config=SimpleNamespace(eos_token_id=[end_id]), disable_adapter=contextlib.nullcontext,
                                     generate=lambda **kw: [[9, 9, 9] + self.tokens])
        self.tokenizer = SimpleNamespace(eos_token_id=end_id, pad_token_id=0, decode=lambda ids, skip_special_tokens: self.text)

    def _ids(self, prompt, system):
        return {"input_ids": SimpleNamespace(shape=(1, 3))}


def live(demo, generator) -> LiveModels:
    lm = LiveModels(None, None)
    lm.repairer.state, lm.repairer.model = "ready", SimpleNamespace(generate=generator)
    demo.models = lm
    return lm


def test_a_cut_off_ai_answer_is_checked_only_up_to_its_last_whole_sentence(demo):
    q = "What was the Group's profit after tax in 2025?"
    full = [5] * (ANSWER_TOKENS - 1) + [2]  # all tokens used, but the last one ends the reply: not cut
    live(demo, FakeGenerator("Group profit after tax was Rs. 14,213 million in 2025.", full))
    out = demo.ask_ai(BANK, q)
    assert out["answer"] == "Group profit after tax was Rs. 14,213 million in 2025." and "note" not in out
    live(demo, FakeGenerator("Group profit after tax was Rs. 14,213 million in 2025. It rose 9.3% from Rs. 13,0", [5] * ANSWER_TOKENS))
    out = demo.ask_ai(BANK, q)
    assert out["answer"] == "Group profit after tax was Rs. 14,213 million in 2025." and "cut off" in out["note"]
    assert demo.ask(BANK, q, out["answer"])["generator"].startswith("Qwen")  # still labelled the AI's answer
    live(demo, FakeGenerator("Group profit after tax was Rs. 14,21", [5] * ANSWER_TOKENS))
    out = demo.ask_ai(BANK, q)  # one cut sentence (the prompt asks for one): refused, its text returned to show unchecked
    assert "answer" not in out and "cut off" in out["error"] and out["cut_text"] == "Group profit after tax was Rs. 14,21"


def test_a_year_the_report_lacks_is_refused_before_the_ai_is_asked(demo):
    def never(**kw):
        raise AssertionError("the AI was asked")

    live(demo, SimpleNamespace(_ids=never))
    out = demo.ask_ai(BANK, "What was the Group's profit after tax in 2027?")
    assert "answer" not in out and "2027" in out["error"]


def test_the_ai_failing_again_and_again_turns_it_off_in_the_status(demo, monkeypatch):
    def broken(prompt, system):
        raise RuntimeError("CUDA error")

    monkeypatch.setattr(models, "_free_gpu", lambda: None)
    live(demo, SimpleNamespace(_ids=broken))
    assert demo.status()["repairer"]["state"] == "ready" and demo.status()["run_id"] == demo.run_id
    line_item = "What were the Group's total assets in 2025?"  # not recorded at rehearsal
    for _ in range(MAX_FAILURES):
        assert "could not answer (RuntimeError)" in demo.ask_ai(BANK, line_item)["error"]
    repairer = demo.status()["repairer"]
    assert repairer["state"] == "failed" and repairer["detail"].startswith("the AI stopped answering")
    assert demo.ask_ai(BANK, line_item)["error"].startswith("The AI is off")
    recorded = demo.ask_ai(BANK, "What was the Group's profit after tax in 2025?")
    assert recorded["source"] == "recorded" and "did not answer" in recorded["by"] and "not loaded" not in recorded["by"]


def test_ask_the_ai_says_why_the_ai_is_off_and_the_template_does_not_send_the_user_there(demo, monkeypatch):
    open_q, recorded_q = "What were the Group's total assets in 2025?", "What was the Group's profit after tax in 2025?"
    no_line = "What was the Group's goodwill in 2025?"  # the template refuses it
    error = demo.ask_ai(BANK, open_q)["error"]  # demo.models is None: started with --no-models
    assert "--no-models" in error and "GPU" not in error
    assert "ask the AI" not in demo.ask_draft(BANK, no_line)["error"]
    monkeypatch.setattr(LiveModels, "_load", lambda self, channel_a, repairer: None)
    lm = LiveModels(None, None)
    lm.start(channel_a=True, repairer=False)
    demo.models = lm
    assert "--no-repairer" in demo.ask_ai(BANK, open_q)["error"]
    lm = LiveModels(None, DEMO)  # an adapter folder that exists: the repairer waits for Channel A, and says it is loading
    lm.start(channel_a=True, repairer=True)
    demo.models = lm
    assert lm.repairer.state == "loading"
    assert demo.ask_ai(BANK, open_q)["error"].startswith("The AI is still loading")
    recorded = demo.ask_ai(BANK, recorded_q)
    assert recorded["source"] == "recorded" and "(the live AI is still loading)" in recorded["by"]
    assert "ask the AI" in demo.ask_draft(BANK, no_line)["error"]  # it answers in a moment


def test_planted_mistakes_on_a_half_right_answer_are_judged_against_its_repair(demo, monkeypatch):
    q = "By what percentage did the Group's profit after tax grow in 2025?"
    case = demo.ask(BANK, q, "Group profit after tax rose 7.0% to Rs. 14,213 million in 2025.")
    fixed = case["output"]["text"]
    assert case["output"]["action"] == "repair" and fixed == "Group profit after tax rose 9.3% to Rs. 14,213 million in 2025."
    out = demo.plant_errors(case["id"])
    assert out["on"] == "original" and out["dropped"] == 0 and not out["on_wrong"] and len(out["edits"]) >= 3
    for e in out["edits"]:  # each repair fixes the planted mistake and the answer's own wrong rate
        assert e["expect"] == "repair" and figures_match(demo.case(case["id"], e["answer"])["output"]["text"], fixed)
    # a fix the screen warns about is no target: judged against the original, every repair differs, and the reason is given
    monkeypatch.setattr(Demo, "doubtful", lambda self, item, final, notes=None: True)
    case = demo.ask(BANK, q, "Group profit after tax rose 7.0% to Rs. 14,213 million in 2025.")
    out = demo.plant_errors(case["id"])
    assert not out["edits"] and out["dropped"] >= 3 and out["on_wrong"]
    assert demo.case(case["id"])["planted_on_wrong"] is True


def test_the_version_is_read_again_and_says_when_the_server_runs_older_code():
    now = version(time.time() + 3600)
    if not now:
        pytest.skip("no git here")
    assert "restart" not in now
    assert version(0.0).endswith("(edited since the server started: restart it)")


def test_the_version_counts_only_the_code_the_server_runs():
    try:
        listed = [line[3:].strip('"') for line in local_changes()]
    except OSError:
        pytest.skip("no git here")
    assert not [p for p in listed if p in ("demo/README.md", "demo/SIMPLE.md") or p.startswith(("demo/stress", "docs/"))]
    assert ROOT / "data" / "demo" / "examples.json" in READ_AT_START  # read once at start: a change needs a restart


def test_the_ai_is_asked_a_short_split_year_in_full(demo):
    """W3-02: "FY24/25" reaches the AI as "FY2024/25", which the frozen checker reads as the 2025 column."""
    asked = []

    def answer(question, evidence):
        asked.append(question)
        return "The Group's profit after tax was Rs. 14,212,560 thousand in FY2024/25.", 1.0, False
    demo.models = SimpleNamespace(repairer=SimpleNamespace(state="ready", detail=""), channel_a=SimpleNamespace(state="off", detail=""),
                                  ai_stopped=False, answer=answer)
    out = demo.ask_ai(BANK, "What was the Group's profit after tax in FY24/25?")
    assert out["source"] == "ai" and asked == ["What was the Group's profit after tax in FY2024/25?"]


def test_a_sidebar_example_s_unknown_line_note_gives_no_advice_it_cannot_take(demo):
    """EX-3: the question of example 6 cannot be edited, so the note does not say to name the line."""
    case = demo.case("demo-lk-6:missing_operand", "The Group's return on equity was 3.8% in FY2025.")
    note = next(c for c in case["caveats"] if c.startswith(UNKNOWN_LINE))
    assert "name it as the report does" not in note and note.endswith("A match does not show that a figure is the one the question asks for.")


def test_inputs_the_checker_would_misread_are_refused_with_how_to_write_them():
    assert "Write dates in words" in bad_answer("The Group's revenue for the year ended 31.03.2026 was Rs. 65,925,260 thousand.")
    assert "Write the unit after the number" in bad_answer("The Group's profit for the year was Rs. Mn 2,580 in 2026.")
    assert "“Rs. Mn”" in bad_answer("The Group's revenue (Rs. Mn) was 65,925 in 2026.")
    for fine in ("The Group's revenue for the year ended 31 March 2026 was Rs. 65,925,260 thousand.",
                 "The Group's revenue was Rs. 65,925 Mn in 2026.", "The Group's revenue was 5,035,750 Rs. '000 in 2026.",
                 "It rose from Rs. '000 1,280 in 2025 to Rs. '000 48,614 in 2026."):  # "'000" before the number is read right
        assert bad_answer(fine) is None, fine
    years = " ".join(f"In {y} it was {n}." for y, n in zip(range(2001, 2026), range(1, 26)))  # 25 figures and 25 years
    assert bad_answer(years) is None
    assert "years not counted" in bad_answer(years + " Then 26.")
    assert "English only" in bad_question("2026 දී සමූහයේ ලාභය කීයද?")
    assert bad_question("What was Nestlé's revenue in 2026?") is None
