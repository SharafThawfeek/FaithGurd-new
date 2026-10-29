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


def test_abstention_names_a_text_passage_the_claim_was_traced_to():
    # The number is found only in a passage about another metric: unverifiable, traced to p1, not a table cell
    item = us_item("Revenue was $9,100.0 million in FY2025.", passages=["Backlog reached $9,100.0 million at year end."])
    out = run(item)
    assert out.action == "abstain" and out.evidence_cells == ["p1"]
    assert "text passage p1: Backlog reached $9,100.0 million at year end." in out.reason


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


def test_gate_accepts_a_share_of_two_line_items_the_question_names():
    # The claim's own context names one line item; the share's whole is the other one the question names (D-087)
    from faithguard.detect.rules import EvidenceIndex
    from faithguard.repair.gate import gate

    item = us_item("Operating income of $1,104.7 million was 14.2% of revenue of $8,432.5 million in FY2025.",
                   question="What share of Example Industries' revenue in FY2025 was operating income?")
    det = detect(item)

    def verdict(expression):
        program = EditProgram(edits=[Calculate(claim="k2", expr=expression)])
        result = execute(item, det.claims, program)
        return gate(item, det, program, result, EvidenceIndex(item)), result.text

    passed, text = verdict("share(t1r2c1, t1r1c1)")  # operating income over revenue
    assert passed.passed and "13.1% of revenue" in text
    failed, _ = verdict("share(t1r3c1, t1r1c1)")  # net income, which the question does not name
    assert any(f.startswith("provenance: k2 uses t1r3c1") for f in failed.failures)
    last_year, _ = verdict("share(t1r2c2, t1r1c2)")  # the right line items, but FY2024's
    assert any(f.startswith("provenance: k2 uses t1r2c2 (period)") for f in last_year.failures)


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
    # seen on the pilot's natural answers (D-092): a difference of amounts written into a percentage claim,
    # and a calculation on typed-in numbers, which no provenance check can trace
    with pytest.raises(ExecError, match="gives an amount for a percent claim"):
        execute(item, claims, EditProgram(edits=[Calculate(claim="k1", expr="diff(t1r3c1, t1r3c2)")]))
    with pytest.raises(ExecError, match="gives a percentage for a amount claim"):
        execute(item, claims, EditProgram(edits=[Calculate(claim="k2", expr="growth(t1r3c1, t1r3c2)")]))
    with pytest.raises(ExecError, match="at least one evidence cell"):
        execute(item, claims, EditProgram(edits=[Calculate(claim="k2", expr="14212.56 / 1000")]))
    fixed = execute(item, claims, EditProgram(edits=[Calculate(claim="k1", expr="growth(t1r3c1, t1r3c2)"),
                                                     Calculate(claim="k2", expr="t1r3c1 / 1")]))
    assert fixed.text == "Group profit after tax rose 9.3% to Rs. 14,213 million."  # scaling is not judged


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

        def token_probs(self, _item, det=None):
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
        def token_probs(self, _item, det=None):
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


def test_systems_runner_repairs_inside_gold_spans_and_runs_parts_alone():
    from faithguard.records import RepairOutput
    from faithguard.train.systems import gold_flags, run_systems

    text = "Group profit after tax rose 7.0% to Rs. 14,213 million."  # 7.0% is the Bank's growth; the amount is right
    item = bank_item(text)
    seen = []

    def repairer(it, det):
        seen.append([det.check(c.id).verdict for c in det.claims])
        return RepairOutput(item_id=it.id, repairer="fake", status="nothing_to_fix", text=it.answer.text)

    start = text.index("Rs.")
    (row,) = run_systems([item], None, repairer, gold_spans={item.id: [(start, len(text) - 1)]})
    assert seen[-1] == ["supported", "unsupported"]  # only the labelled span is flagged, whatever the checker says
    assert set(row) == {"repair_rule_spans", "repair_gold_spans"}  # no Channel A asked for, so no detector record
    assert all(c.verdict == "supported" for c in gold_flags(detect(item), []).checks)  # no labelled span, nothing flagged
    (row,) = run_systems([item], neural=lambda it, d: (0.2, 0.9))
    assert row == {"neural": {"item_id": item.id, "p_unsafe": 0.2, "p_fix": 0.9}}


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


def test_large_evidence_is_focused_on_the_rows_the_claims_need():
    from faithguard.focus import FOCUS_ABOVE_ROWS, focus_rows
    from faithguard.records import Evidence
    from faithguard.repair.prompting import build_prompt, editable_claims
    from faithguard.tables import table_from_grid
    from fixtures import BANK_GRID

    small = bank_item("Group profit after tax was Rs. 12,450 million.")
    assert focus_rows(small.evidence, detect(small), small.question.text) is None  # small evidence is shown whole
    filler = [[f"Other line item {i}", f"{1000 + i:,}", "900", "800", "700"] for i in range(FOCUS_ABOVE_ROWS)]
    big = small.model_copy(update={"evidence": Evidence(tables=[table_from_grid("t1", BANK_GRID + filler, currency="LKR")])})
    det = detect(big)
    focus = focus_rows(big.evidence, det, big.question.text)
    assert focus == {"t1": {3}}  # the profit after tax row: the claim's cell and the question's line item
    prompt = build_prompt(big, det.claims, editable_claims(det), det)
    assert "t1r3c1" in prompt and "Other line item" not in prompt and "rows of these statements are not shown" in prompt


def test_released_detectors_see_the_same_focused_evidence(tmp_path, monkeypatch):
    import json

    from faithguard.detect import baselines
    from faithguard.detect.channel_a import evidence_passages
    from faithguard.focus import FOCUS_ABOVE_ROWS
    from faithguard.records import Evidence, write_jsonl
    from faithguard.tables import table_from_grid
    from faithguard.train import baseline_eval
    from fixtures import BANK_GRID

    small = bank_item("Group profit after tax was Rs. 12,450 million.")
    assert baselines.passages(small) == evidence_passages(small.evidence)  # controlled-track sizes: unchanged
    filler = [[f"Other line item {i}", f"{1000 + i:,}", "900", "800", "700"] for i in range(FOCUS_ABOVE_ROWS)]
    big = small.model_copy(update={"evidence": Evidence(tables=[table_from_grid("t1", BANK_GRID + filler, currency="LKR")])})
    text = "\n".join(baselines.passages(big))
    assert "14,212,560" in text and "Other line item" not in text  # D-091: the rows Channel A sees, nothing else

    class Fake:  # stands in for a released detector, so no model is downloaded
        def risk(self, item):
            return 0.25

    monkeypatch.setattr(baselines, "make", lambda name: Fake())
    write_jsonl(tmp_path / "items.jsonl", [small, big.model_copy(update={"id": "demo-bank-big"})])
    baseline_eval.main(["--detector", "hhem", "--items", str(tmp_path / "items.jsonl"), "--out", str(tmp_path / "out")])
    rows = [json.loads(line) for line in (tmp_path / "out" / "scores.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows == [{"item_id": "demo-bank", "detector": "hhem", "risk": 0.25}, {"item_id": "demo-bank-big", "detector": "hhem", "risk": 0.25}]
    assert not (tmp_path / "out" / "results.json").exists()  # benchmark items: no gold, so no metrics


def test_repair_check_samples_changed_test_repairs_and_compares_code_with_labels():
    from decimal import Decimal

    from faithguard.evaluate import repair_check
    from faithguard.gold import GoldLabel, GoldQuestion, GoldStore, GoldValue

    item = bank_item("Group profit after tax was Rs. 12,450 million.")
    item.question.split = "test"
    other = item.model_copy(update={"id": "demo-bank-2", "question": item.question.model_copy(update={"split": "calibration"})})
    fixed = {"item_id": item.id, "repairer": "trained", "status": "repaired", "text": "Group profit after tax was Rs. 14,213 million."}
    same = fixed | {"text": item.answer.text}
    outputs = {"repair-v1": {"repair_gold_spans": {item.id: fixed, other.id: fixed | {"item_id": other.id}}, "repair_rule_spans": {item.id: same}},
               "stage-b": {"repair_rule_spans": {item.id: fixed | {"status": "cannot_fix"}}, "repair_channel_a_spans": {item.id: fixed}}}
    changes = repair_check.changed([item, other], outputs)
    # only test answers sent changed: not calibration, not unchanged text, not a withheld repair
    assert changes == {"repair-v1, gold_spans": {item.id: fixed["text"]}, "stage-b, channel_a_spans": {item.id: fixed["text"]}}
    sample = repair_check.draw(changes)
    assert sample == {"other variants": [f"{item.id}@stage-b, channel_a_spans"], "repair-v1, gold_spans": [f"{item.id}@repair-v1, gold_spans"]}
    (task,) = repair_check.repair_items([item], changes, sample["repair-v1, gold_spans"])
    assert task.id == f"{item.id}@repair-v1, gold_spans" and task.answer.text == fixed["text"]

    gold = GoldStore("unused")
    gold.add_question(GoldQuestion(question_id="q-bank", answer_text="Rs. 14,213 million", cells=["t1r3c1"],
                                   values=[GoldValue(value=Decimal("14212560000"), kind="amount")], source="test"))
    assert repair_check.compare([item], gold, changes, sample)["repair-v1, gold_spans"]["labelled"] == 0
    gold.add_label(GoldLabel(item_id=task.id, target="repair", status="correct", useful=True, annotator="claude-labeller@d106"))
    gold.add_label(GoldLabel(item_id=f"{item.id}@stage-b, channel_a_spans", target="repair", status="incorrect", annotator="claude-labeller@d106"))
    result = repair_check.compare([item], gold, changes, sample)
    assert result["repair-v1, gold_spans"] == {"planned": 1, "labelled": 1, "disagree": 0, "rate": 0.0,
                                               "label_every_changed_repair": False, "disagreements": []}
    assert result["other variants"]["disagree"] == 1 and result["other variants"]["label_every_changed_repair"]
    # the information-preserved pass (D-109): its own keys, the original beside the repaired text, a share per group
    tasks, mapping = repair_check.info_tasks([item], changes, [task.id])
    (info,) = tasks
    assert set(info["data"]) == {"task_key", "question", "evidence_html", "original", "repaired"}
    assert info["data"]["original"] == item.answer.text and info["data"]["repaired"] == fixed["text"]
    assert mapping == {info["data"]["task_key"]: task.id}
    summary = repair_check.info_summary([item], [{"task_key": info["data"]["task_key"], "preserved": True}], mapping, sample)
    assert summary["repair-v1, gold_spans"]["checked"] == 1 and summary["repair-v1, gold_spans"]["preserved"]["estimate"] == 1.0
    assert summary["other variants"]["checked"] == 0


def test_labels_replace_the_scorer_for_a_group_the_repair_check_failed(tmp_path):
    import json
    from decimal import Decimal

    from faithguard.evaluate import analysis
    from faithguard.gold import GoldLabel, GoldQuestion, GoldStore, GoldValue

    item = bank_item("Group profit after tax was Rs. 12,450 million.")
    item.question.split = "test"
    det = detect(item)
    fixed = {"item_id": item.id, "repairer": "trained", "status": "repaired", "text": "Group profit after tax was Rs. 14,213 million."}
    record = {"item_id": item.id, "threshold": 0.5, "claims": [{"claim_id": c.id, "a_max": 0.9} for c in det.claims]}
    system = {"detector": {item.id: record}, "repair_rule_spans": {item.id: fixed}, "repair_channel_a_spans": {item.id: fixed}, "repair_gold_spans": {}}
    outputs = {"repair-sft": system, "repair-sft-nokeep": system}
    gold = GoldStore(tmp_path)
    gold.add_question(GoldQuestion(question_id="q-bank", answer_text="Rs. 14,213 million", cells=["t1r3c1"],
                                   values=[GoldValue(value=Decimal("14212560000"), kind="amount")], source="test"))
    gold.add_label(GoldLabel(item_id=item.id, target="original", status="incorrect", annotator="claude-labeller@d103"))
    gold.add_label(GoldLabel(item_id=f"{item.id}@repair-sft, rule_spans", target="repair", status="incorrect", annotator="claude-labeller@d106"))

    plain = analysis.repair([item], gold, outputs, None)
    assert "labelled_arms" not in plain and plain["summaries"]["repair-sft, rule_spans"]["correction_rate"] == 1.0  # the scorer's state

    (tmp_path / "repair-check-result.json").write_text(json.dumps({"other variants": {"label_every_changed_repair": True}}), encoding="utf-8")
    out = analysis.repair([item], gold, outputs, None)
    # D-112: the label's state replaces the scorer's for the failed group's changed repairs; the scorer's results stay beside
    assert out["summaries"]["repair-sft, rule_spans"]["correction_rate"] == 0.0
    assert out["code_scored"]["summaries"]["repair-sft, rule_spans"]["correction_rate"] == 1.0
    assert out["labelled_arms"]["repair-sft, rule_spans"] == {"changed": 1, "unlabelled": 0, "label_differs_from_code": 1}
    assert out["labelled_arms"]["repair-sft, channel_a_spans"]["unlabelled"] == 1  # a changed repair with no label keeps the scorer's
    assert out["summaries"]["repair-sft, channel_a_spans"]["correction_rate"] == 1.0
    assert out["summaries"]["rule repairer, rule_spans"] == out["code_scored"]["summaries"]["rule repairer, rule_spans"]  # not a trained arm
    assert set(out["code_scored"]) == {"summaries", "R-H2", "R-H3"}
    assert "replaces the gold scorer's (D-112)" in analysis.report({"repair": out})
