"""Phase-4 pieces that run without a GPU: target programs, training data, fusion, XBRL mining, repair evaluation."""

from decimal import Decimal

import pytest

from faithguard.claims import extract_claims
from faithguard.data.channel_a_examples import controlled_spans
from faithguard.data.example import Example
from faithguard.detect.fusion import FEATURES, Fusion
from faithguard.evaluate import score_text
from faithguard.evaluate.repair import evaluate_repairer
from faithguard.executor import execute
from faithguard.gold import GoldQuestion, GoldStore, GoldValue
from faithguard.inject import inject
from faithguard.records import CannotFix, Copy, EditProgram, Keep, Question
from faithguard.repair import repair
from faithguard.data.repair_examples import target_for
from fixtures import bank_item

GROWTH = "((t1r3c1 - t1r3c2) / t1r3c2) * 100"  # Group profit after tax growth, FY2025


def growth_example() -> tuple[Example, GoldStore]:
    item = bank_item("x")
    gold_q = GoldQuestion(
        question_id="q-growth", answer_text="9.29", source="synthetic", cells=["t1r3c1", "t1r3c2"], program=GROWTH,
        values=[
            GoldValue(value=Decimal("9.292229"), kind="percent", role="answer"),
            GoldValue(value=Decimal("14212560000"), kind="amount", role="operand", cell="t1r3c1"),
            GoldValue(value=Decimal("13004180000"), kind="amount", role="operand", cell="t1r3c2"),
        ],
    )
    question = Question(id="q-growth", issuer="demo-bank", text="By what percentage did the Group's profit after tax grow in 2025?", source="synthetic")
    example = Example(question=question, evidence=item.evidence, gold=gold_q, grounded=True)
    gold = GoldStore("unused")
    gold.add_question(gold_q)
    return example, gold


def injected():
    example, gold = growth_example()
    pairs = inject(example)
    for _, injection in pairs:
        gold.add_injection(injection)
    return pairs, gold


def test_injector_covers_the_expected_errors():
    pairs, _ = injected()
    errors = {inj.error for _, inj in pairs}
    assert {"none", "metric", "entity", "sign", "basis", "missing_operand"} <= errors


def test_every_target_program_fixes_its_answer():
    pairs, gold = injected()
    g = gold.questions["q-growth"]
    for item, inj in pairs:
        if any(isinstance(e, CannotFix) for e in inj.target_program.edits):
            assert inj.error == "missing_operand" and inj.expected_action == "abstain"
            continue
        fixed = execute(item, extract_claims(item.answer.text), inj.target_program).text
        assert score_text(fixed, g) == "supported_useful", (inj.error, item.answer.text, fixed)
        if inj.error == "none":
            assert inj.target_program.edits == []


def test_channel_a_labels_name_the_slot():
    pairs, gold = injected()
    by_error = {inj.error: item for item, inj in pairs}
    assert controlled_spans(by_error["none"], gold) == []
    entity = controlled_spans(by_error["entity"], gold)
    assert entity and all(slot == "entity_scope" for *_, slot in entity)
    sign = controlled_spans(by_error["sign"], gold)
    texts = {by_error["sign"].answer.text[s:e] for s, e, _ in sign}
    assert any(t in ("rose", "fell", "up", "down") for t in texts)  # the direction word is labelled too
    missing = controlled_spans(by_error["missing_operand"], gold)
    assert missing and all(slot == "metric" for *_, slot in missing)


def test_sft_targets_keep_false_flags_and_skip_missed_claims():
    gold_program = EditProgram(edits=[Copy(claim="k2", cell="t1r3c1")])
    target = target_for(["k1", "k2"], gold_program)
    assert [e.op for e in target.edits] == ["KEEP", "COPY"]
    assert target_for(["k1"], gold_program) is None  # the wrong claim was not flagged
    stop = target_for(["k1"], EditProgram(edits=[CannotFix(reason="missing_operand", claim="k1")]))
    assert stop.edits[0].op == "CANNOT_FIX"


def test_repair_evaluation_counts_corrections_and_abstentions():
    pairs, gold = injected()
    result = evaluate_repairer([item for item, _ in pairs], gold, repair)
    s = result["summary"]
    assert s["correction_rate"] >= 0.8 and s["damage_rate"] == 0.0
    assert result["by_error"]["missing_operand"]["abstained_when_needed"] == 1.0


def test_fusion_learns_and_calibrates():
    import random

    random.seed(0)
    rows = []
    for _ in range(600):
        wrong = random.random() < 0.4
        a = min(1.0, max(0.0, (0.75 if wrong else 0.2) + random.uniform(-0.2, 0.2)))
        row = {f: 0.0 for f in FEATURES}
        row.update(b_unsupported=float(wrong and random.random() < 0.8), b_supported=float(not wrong), a_max=a, a_mean=a, a_any=float(a >= 0.5), label=int(wrong))
        rows.append(row)
    fusion = Fusion.fit(rows[:400])
    fusion.calibrate(rows[400:])
    p = fusion.claim_probs(rows[400:])
    labels = [r["label"] for r in rows[400:]]
    assert sum(pi for pi, y in zip(p, labels) if y) / sum(labels) > sum(pi for pi, y in zip(p, labels) if not y) / (len(labels) - sum(labels)) + 0.5
    assert fusion.item_risk([]) == 0.5
    assert 0 <= fusion.item_risk(rows[:3]) <= 1


def test_xbrl_mining_produces_labelled_wrong_context_negatives():
    from faithguard.data import edgar, xbrl_mining
    from test_edgar import INSTANCE

    rows = list(xbrl_mining.mine(edgar.parse_instance(INSTANCE, entity="1"), "Example Industries"))
    errors = [r["error"] for r in rows]
    assert errors.count("none") == 2 and errors.count("entity_scope") == 2 and errors.count("scale") == 2
    neg = next(r for r in rows if r["error"] == "entity_scope")
    (start, end, slot), = neg["spans"]
    assert slot == "entity_scope" and neg["answer"][start:end].startswith("$")
    assert "Example Industries' revenues" in neg["answer"]
    capped = list(xbrl_mining.mine(edgar.parse_instance(INSTANCE, entity="1"), "Example Industries", max_cited=1))
    assert [r["error"] for r in capped].count("none") == 1 and set(capped[0]) == set(rows[0])


def test_deployed_outcome_aware_policy_decides():
    from test_policy_study import records

    from faithguard.detect import detect
    from faithguard.policy import study

    result = study.run(records(1200), budget_sizes=(50,), budget_repeats=2, use_score=False)
    policy = result["deployable"]
    item = bank_item("Group profit after tax rose 7.0% to Rs. 12,450 million.")
    decision = policy.decide(item, detect(item))
    assert decision.action in ("send", "repair", "abstain") and "p_unsafe" in decision.scores
