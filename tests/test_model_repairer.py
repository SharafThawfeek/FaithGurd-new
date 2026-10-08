from faithguard.detect import detect
from faithguard.repair.backends import scripted
from faithguard.repair.model import ModelRepairer
from faithguard.repair.prompting import build_prompt, editable_claims, mark_claims, parse_program, program_json
from fixtures import GROUP_PAT_2024, GROUP_PAT_2025, bank_item

WORKED = "Group profit after tax rose 7.0% to Rs. 12,450 million."
GOOD = '{"edits":[{"op":"CALCULATE","claim":"k1","expr":"growth(t1r3c1, t1r3c2)"},{"op":"COPY","claim":"k2","cell":"t1r3c1"}]}'


def test_prompt_marks_claims_and_lists_editable_ones():
    item = bank_item(WORKED)
    det = detect(item)
    prompt = build_prompt(item, det.claims, editable_claims(det))
    assert "[k1: 7.0%]" in prompt and "[k2: Rs. 12,450 million]" in prompt
    assert f"{GROUP_PAT_2025} Group 2025: 14,212,560" in prompt
    assert "amounts in thousands" in prompt
    assert "FLAGGED CLAIMS: k1, k2" in prompt


def test_closure_adds_dependent_growth_claims():
    # only the amount is wrong (2024 figure), but the growth rate built on it must be editable too
    det = detect(bank_item("Group profit after tax rose 9.3% to Rs. 13,004 million."))
    assert editable_claims(det) == ["k1", "k2"]


def test_parser_handles_fences_chatter_and_bare_edits():
    assert parse_program("```json\n" + GOOD + "\n```").edits[1].cell == GROUP_PAT_2025
    assert parse_program("Sure! Here it is: " + GOOD + " Hope this helps.") is not None
    assert parse_program('{"op":"KEEP","claim":"k1"}').edits[0].op == "KEEP"
    assert parse_program("no json here") is None
    assert parse_program('{"edits":[{"op":"DELETE","claim":"k1"}]}') is None


def test_program_json_round_trips():
    program = parse_program(GOOD)
    assert parse_program(program_json(program)) == program


def test_model_repairer_fixes_the_worked_example():
    item = bank_item(WORKED)
    out = ModelRepairer(scripted([GOOD]))(item, detect(item))
    assert out.status == "repaired" and out.text == "Group profit after tax rose 9.3% to Rs. 14,213 million."


def test_retry_after_invalid_reply_and_after_gate_failure():
    item = bank_item(WORKED)
    gen = scripted(["oops", GOOD])
    out = ModelRepairer(gen)(item, detect(item))
    assert out.status == "repaired" and out.attempts == 2
    assert "not a valid edit program" in gen.prompts[1]

    wrong_cell = GOOD.replace('"cell":"t1r3c1"', f'"cell":"{GROUP_PAT_2024}"')
    gen = scripted([wrong_cell, wrong_cell])
    out = ModelRepairer(gen)(item, detect(item))
    assert out.status == "gate_failed" and "provenance" in out.reason
    assert "failed the checks" in gen.prompts[1]


def test_cannot_fix_and_nothing_to_fix():
    item = bank_item(WORKED)
    out = ModelRepairer(scripted(['{"edits":[{"op":"CANNOT_FIX","reason":"missing_operand"}]}']))(item, detect(item))
    assert out.status == "cannot_fix"
    clean = bank_item("Group profit after tax was Rs. 14,213 million in FY2025.")
    assert ModelRepairer(scripted([]))(clean, detect(clean)).status == "nothing_to_fix"


def test_marking_is_reversible():
    item = bank_item(WORKED)
    det = detect(item)
    marked = mark_claims(item.answer.text, det.claims)
    assert marked == "Group profit after tax rose [k1: 7.0%] to [k2: Rs. 12,450 million]."
