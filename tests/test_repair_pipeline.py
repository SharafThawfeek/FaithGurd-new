import pytest

from faithguard.detect import detect
from faithguard.executor import ExecError, execute
from faithguard.pipeline import run
from faithguard.records import Calculate, Copy, EditProgram, Keep
from faithguard.repair import repair
from fixtures import BANK_PAT_2025, GROUP_PAT_2024, GROUP_PAT_2025, bank_item, us_item


def test_worked_example_end_to_end():
    item = bank_item("Group profit after tax rose 7.0% to Rs. 12,450 million.")
    out = run(item)
    assert out.action == "repair"
    assert out.text == "Group profit after tax rose 9.3% to Rs. 14,213 million."
    ops = [e.op for e in out.repair.program.edits]
    assert ops == ["CALCULATE", "COPY"]
    assert out.repair.gate.passed


def test_correct_answer_is_sent_unchanged():
    item = bank_item("Group profit after tax rose 9.3% to Rs. 14,213 million in FY2025.")
    out = run(item)
    assert (out.action, out.text) == ("send", item.answer.text)


def test_missing_cell_leads_to_abstention_with_evidence():
    item = bank_item("Group profit after tax was Rs. 12,450 million.", drop=[GROUP_PAT_2025])
    out = run(item)
    assert out.action == "abstain" and out.text is None
    assert out.reason


def test_sign_error_flips_the_direction_word():
    item = us_item("Net income rose 6.5% to $612.4 million.", question="How did Example Industries' net income change in FY2025?")
    out = run(item)
    assert out.action == "repair"
    assert out.text == "Net income fell 6.5% to $612.4 million."


def test_closure_recomputes_dependent_growth():
    # The amount is the 2024 figure; the growth rate is the correct one, so closure leaves it unchanged.
    item = bank_item("Group profit after tax rose 9.3% to Rs. 13,004 million.")
    out = run(item)
    assert out.text == "Group profit after tax rose 9.3% to Rs. 14,213 million."


def test_period_and_scale_errors_are_repaired_in_the_answer_style():
    out = run(bank_item("Group profit after tax was Rs. 14,212,560 million in FY2025."))
    assert out.text == "Group profit after tax was Rs. 14,213 million in FY2025."
    out = run(us_item("Revenue was $8,432.5 billion in fiscal 2025."))
    assert out.text == "Revenue was $8.43 billion in fiscal 2025."


def test_gate_rejects_a_program_that_copies_the_wrong_cell():
    item = bank_item("Group profit after tax was Rs. 12,450 million in FY2025.")
    det = detect(item)
    from faithguard.detect.rules import EvidenceIndex
    from faithguard.repair.gate import gate

    program = EditProgram(edits=[Copy(claim="k1", cell=GROUP_PAT_2024)])
    result = execute(item, det.claims, program)
    verdict = gate(item, det, program, result, EvidenceIndex(item))
    assert not verdict.passed
    assert any(f.startswith("provenance") for f in verdict.failures)


def test_executor_rejects_unknown_cells_and_type_mismatches():
    item = bank_item("Group profit after tax rose 7.0% to Rs. 12,450 million.")
    claims = detect(item).claims
    with pytest.raises(ExecError):
        execute(item, claims, EditProgram(edits=[Copy(claim="k2", cell="t9r9c9")]))
    with pytest.raises(ExecError):
        execute(item, claims, EditProgram(edits=[Copy(claim="k1", cell=GROUP_PAT_2025)]))  # amount into a percent
    with pytest.raises(ExecError):
        execute(item, claims, EditProgram(edits=[Calculate(claim="k1", expr="__import__('os')")]))
    with pytest.raises(ExecError):
        execute(item, claims, EditProgram(edits=[Keep(claim="k1"), Keep(claim="k1")]))


def test_repair_reports_nothing_to_fix():
    item = bank_item("Group profit after tax was Rs. 14,213 million in FY2025.")
    assert repair(item, detect(item)).status == "nothing_to_fix"


def test_bank_cell_constant_is_the_bank():
    item = bank_item("x")
    assert item.evidence.cell(BANK_PAT_2025).entity == "bank"
