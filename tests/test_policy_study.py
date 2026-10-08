import random

from faithguard.policy import families, outcome, study
from faithguard.policy.certify import certify, cluster_pvalue
from faithguard.replay import ReplayRecord

SPLITS = ("fit", "tune", "calibration", "test")


def record(i: int, kind: str, split: str) -> ReplayRecord:
    """Three kinds of item: clean (send is safe), fixable (repair is useful), hopeless (nothing works)."""
    outcomes = {
        "clean": {"send": "supported_useful", "repair": "supported_useful", "abstain": "abstained"},
        "fixable": {"send": "unsupported", "repair": "supported_useful", "abstain": "abstained"},
        "hopeless": {"send": "unsupported", "repair": "abstained", "abstain": "abstained"},
    }[kind]
    risk = {"clean": 0.0, "fixable": 1.0, "hopeless": 0.5}[kind]
    features = {"risk": risk, "n_claims": 2.0, "evidence_sufficient": float(kind == "fixable"), "noise": random.random()}
    return ReplayRecord(
        item_id=f"i{i}", question_id=f"q{i}", issuer=f"co{i // 5}", split=split, features=features, risk=risk,
        decision="send", outcomes=outcomes, repair_status="repaired",
    )


def records(n: int = 2000, seed: int = 0) -> list[ReplayRecord]:
    random.seed(seed)
    kinds = ["clean"] * 4 + ["fixable"] * 4 + ["hopeless"] * 2
    return [record(i, random.choice(kinds), SPLITS[(i // 5) % 4]) for i in range(n)]


def test_outcome_aware_policy_is_certified_and_beats_send_or_abstain():
    result = study.run(records(), budget_sizes=(50, 200), budget_repeats=10, use_score=False)
    by = {f["family"]: f for f in result["families"]}
    ours = by["outcome_aware[lightgbm]"]
    assert ours["chosen"] is not None
    assert ours["test"]["residual_risk"] <= 0.10
    assert ours["test"]["useful_coverage"] > by["verified_only"]["test"]["useful_coverage"] + 0.2
    assert by["send_all"]["chosen"] is None  # 60% unsafe: never certifiable
    assert result["oracle_test"]["useful_coverage"] >= ours["test"]["useful_coverage"]
    assert {row["calibration_items"] for row in result["budget_curve"]} == {50, 200}
    assert "flip_matrix_test" in result["chosen_detail"]
    assert "# Policy study" in study.report(result)


def test_nothing_is_certified_when_every_setting_is_unsafe():
    rs = [r for r in records(800) if r.outcomes["send"] == "unsupported"]
    tune = [r for r in rs if r.split == "tune"]
    cal = [r for r in rs if r.split == "calibration"]
    cert = certify(tune, cal, families.fixed(tune, "send"), families.fixed(cal, "send"))
    assert cert.certified == [] and cert.chosen is None


def test_oracle_prefers_a_useful_answer():
    rs = records(30)
    acts = families.oracle(rs)
    for r, a in zip(rs, acts):
        assert r.outcomes[a] == "supported_useful" or a == "abstain"


def test_outcome_models_learn_the_targets():
    rs = records(1500)
    fit = [r for r in rs if r.split == "fit"]
    test = [r for r in rs if r.split == "test"]
    models = outcome.fit(fit)
    p_unsafe, p_fix = models.predict(test)
    y_unsafe, y_fix = outcome.targets(test)
    assert outcome.auroc(y_unsafe, p_unsafe) > 0.95 and outcome.auroc(y_fix, p_fix) > 0.95
    assert 0 <= outcome.ece(y_unsafe, p_unsafe) <= 1


def test_cluster_pvalue_is_a_probability():
    rs = [r for r in records(400) if r.split == "calibration"]
    p = cluster_pvalue(rs, ["send" if r.risk == 0 else "abstain" for r in rs], 0.10)
    assert 0 <= p <= 1
