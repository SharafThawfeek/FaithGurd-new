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


def test_channel_a_spans_decide_which_claims_reach_the_repairer():
    from faithguard.detect.channel_a import span_flags

    text = "Group profit after tax was Rs. 14,213 million, against Rs. 12,450 million for the Bank."
    item = bank_item(text)

    class FakeChannelA:  # flags only the first figure, which is correct
        threshold = 0.5

        def token_probs(self, _item):
            start = text.index("14,213")
            return [(start, start + 6, 0.9, 0), (text.index("12,450"), text.index("12,450") + 6, 0.1, 0)]

    det = span_flags(FakeChannelA())(item)
    verdicts = {c.text: det.check(c.id).verdict for c in det.claims}
    assert verdicts["Rs. 14,213 million"] == "unsupported"  # a false positive reaches the repairer
    assert verdicts["Rs. 12,450 million"] == "supported"  # unflagged claims pass through
    assert det.detector == "channel-a-spans@0.5"
    # the rule repairer withholds rather than rewrite a correct figure: the false positive costs coverage, not correctness
    assert repair(item, det).status == "cannot_fix"


def test_systems_runner_stores_both_repairs_and_the_detector_record():
    from faithguard.records import RepairOutput
    from faithguard.train.systems import run_systems

    text = "Group profit after tax was Rs. 12,450 million."  # the Bank's figure: the rule checker flags it
    item = bank_item(text)

    class FakeChannelA:  # flags nothing
        def token_probs(self, _item):
            return [(0, 5, 0.1, 0)]

        def spans(self, _item, tokens=None):
            return []

    seen = []

    def repairer(it, det):
        seen.append([det.check(c.id).verdict for c in det.claims])
        return RepairOutput(item_id=it.id, repairer="fake", status="nothing_to_fix", text=it.answer.text)

    (row,) = run_systems([item], FakeChannelA(), repairer)
    assert seen == [["unsupported"], ["supported"]]  # rule spans first, then Channel A's (which flag nothing)
    assert row["detector"]["item_id"] == item.id and row["detector"]["claims"][0]["b_unsupported"] == 1.0
    assert row["repair_rule_spans"]["status"] == row["repair_channel_a_spans"]["status"] == "nothing_to_fix"


def test_stored_system_outputs_are_scored_against_gold():
    from decimal import Decimal

    from faithguard.evaluate import systems
    from faithguard.gold import GoldQuestion, GoldStore, GoldValue

    item = bank_item("Group profit after tax was Rs. 12,450 million.")  # the Bank's figure
    gold = GoldStore("unused")
    gold.add_question(GoldQuestion(question_id="q-bank", answer_text="Rs. 14,213 million", cells=["t1r3c1"],
                                   values=[GoldValue(value=Decimal("14212560000"), kind="amount")], source="test"))
    det = detect(item)
    claim = det.claims[0]
    detector_rows = {item.id: {"item_id": item.id, "threshold": 0.5, "claims": [{"claim_id": claim.id, "a_max": 0.9}]}}
    fixed = {"item_id": item.id, "repairer": "trained", "status": "repaired", "text": "Group profit after tax was Rs. 14,213 million."}
    summary = systems.score([item], gold, detector_rows, {"rule_spans": {item.id: fixed}, "channel_a_spans": {item.id: fixed}},
                            {item.id: "unsupported"})
    assert summary["trained repairer, rule_spans"]["correction_rate"] == 1.0
    assert summary["rule repairer, channel_a_spans"]["needing_repair"] == 1  # Channel A flagged the wrong figure too
    assert "| trained repairer, rule_spans |" in systems.report(summary)
