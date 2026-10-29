import random

import pytest

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
    assert {row["calibration_items"] for row in result["budget_curve"]["lightgbm"]} == {50, 200}
    assert "flip_matrix_test" in result["chosen_detail"]
    assert "# Policy study" in study.report(result)


def neural_predictions(rs, path, noise: float = 0.1, seed: int = 1):
    """What the GPU run writes: P(unsafe) and P(fix) for every tune, calibration and test record, by its key."""
    import json

    from faithguard.policy.neural import row_key

    rng = random.Random(seed)
    y_unsafe, y_fix = outcome.targets(rs)
    with open(path, "w", encoding="utf-8") as f:
        for r, u, x in zip(rs, y_unsafe, y_fix):
            if r.split != "fit":
                p = [min(1.0, max(0.0, float(y) + rng.uniform(-noise, noise))) for y in (u, x)]
                f.write(json.dumps({"key": row_key(r.item_id), "split": r.split, "p_unsafe": p[0], "p_fix": p[1]}) + "\n")
    return path


def test_neural_challenger_is_certified_on_the_same_grid_beside_lightgbm(tmp_path):
    # planted errors as in the controlled track: clean items "none", fixable "period", hopeless "missing_operand"
    error = {"supported_useful": "none", "unsupported": None}
    rs = [r.model_copy(update={"error": error[r.outcomes["send"]] or ("period" if r.outcomes["repair"] == "supported_useful" else "missing_operand")})
          for r in records()]
    path = neural_predictions(rs, tmp_path / "predictions.jsonl")
    result = study.run(rs, kinds=("lightgbm", "neural"), predictions={"neural": str(path)},
                       budget_sizes=(50, 200), budget_repeats=10, use_score=False)
    by = {f["family"]: f for f in result["families"]}
    ours, challenger = by["outcome_aware[lightgbm]"], by["outcome_aware[neural]"]
    assert challenger["settings"] == ours["settings"] == len(families.TAU_SEND) * len(families.TAU_FIX)
    assert challenger["chosen"] is not None and challenger["test"]["residual_risk"] <= 0.10
    assert result["models"]["neural"]["unsafe"]["auroc"] > 0.95
    assert set(result["budget_curve"]) == {"lightgbm", "neural"}
    assert result["deployable"].names == outcome.feature_names([r for r in rs if r.split == "fit"])  # LightGBM stays the deployed model
    neural = result["models"]["neural"]
    n_mo = sum(r.split == "test" and r.error == "missing_operand" for r in rs)
    assert neural["excluding_missing_operand"]["items"] == result["counts"]["test"]["items"] - n_mo
    assert set(neural["by_error"]) == {"none", "period", "missing_operand"} and neural["by_error"]["period"]["unsafe"]["auroc"] is None
    assert set(result["chosen_by_error"]) == {"lightgbm", "neural"}
    report = study.report(result)
    assert "outcome_aware[neural]" in report and "| neural | P(unsafe), all |" in report and "Certified (neural)" in report
    assert "| neural | P(fix), excl. missing_operand |" in report and "Brier score by planted error" in report
    assert "Wrong among sent (neural)" in report


def test_neural_challenger_needs_a_prediction_for_every_record(tmp_path):
    rs = records(400)
    path = neural_predictions(rs, tmp_path / "predictions.jsonl")
    lines = path.read_text(encoding="utf-8").splitlines()
    path.write_text("\n".join(lines[1:]) + "\n", encoding="utf-8")
    models = outcome.fit([r for r in rs if r.split == "fit"], "neural", predictions=path)
    with pytest.raises(ValueError, match="no prediction"):
        models.predict([r for r in rs if r.split != "fit"])
    skipped = study.run(rs, kinds=("lightgbm", "neural"), predictions={"neural": str(tmp_path / "missing.jsonl")},
                        budget_sizes=(50,), budget_repeats=2, use_score=False)
    assert "skipped" in skipped["models"]["neural"] and "outcome_aware[neural]" not in {f["family"] for f in skipped["families"]}


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


def test_transfer_study_scores_the_v0_policy_on_a_changed_repairer():
    from faithguard.policy import transfer

    v0 = records(2000)
    random.seed(3)
    v1 = []  # the new repairer breaks half of the repairs the old one got right
    for r in v0:
        broken = r.outcomes["send"] == "unsupported" and r.outcomes["repair"] == "supported_useful" and random.random() < 0.5
        v1.append(r.model_copy(update={"outcomes": r.outcomes | {"repair": "unsupported"}}) if broken else r)
    result = transfer.run(v0, v1, sizes=(50, 200), repeats=5)
    assert result["v0_on_v0_test"]["risk_within_alpha"]
    assert not result["as_is"]["risk_within_alpha"]  # repairing with the new repairer sends wrong answers
    assert result["refitted"] and result["refitted"]["risk_within_alpha"]  # refitting learns to abstain instead
    assert [r["labels"] for r in result["recalibrated"]][:2] == [50, 200]
    assert "# Transfer study" in transfer.report(result)


def test_issuer_check_can_pass_with_24_issuers_where_the_issuer_p_value_cannot():
    from faithguard.policy.certify import cluster_upper

    clean = [record(i, "clean", "calibration") for i in range(24 * 5)]  # 24 issuers, every answer safe and sent
    sends = ["send"] * len(clean)
    assert cluster_pvalue(clean, sends, 0.10) > 0.05  # the old check fails even here (D-102)
    assert cluster_upper(clean, sends) <= 0.10
    risky = [record(i, "fixable", "calibration") for i in range(24 * 5)]
    assert cluster_upper(risky, ["send"] * len(risky)) > 0.10


def test_threshold_transfer_counts_ambiguous_answers_unsafe_and_reports_the_label_curve():
    from faithguard.evaluate.analysis import _threshold_transfer
    from faithguard.gold import GoldLabel
    from fixtures import bank_item

    rng = random.Random(0)
    items, lab, risk = [], {}, {}
    for n in range(900):
        country, split = ("US", "LK")[n % 2], ("calibration", "test")[(n // 2) % 2]
        base = bank_item("Group profit after tax was Rs. 14,213 million.")
        item = base.model_copy(update={"id": f"a{n}", "question": base.question.model_copy(update={"country": country, "split": split, "issuer": f"i{n % 12}"})})
        r = rng.random()
        status = "ambiguous" if r > 0.97 else ("incorrect" if r > 0.9 else "correct")
        items.append(item)
        lab[item.id] = GoldLabel(item_id=item.id, status=status, annotator="claude-labeller@d103")
        risk[item.id] = 0.95 if status != "correct" else rng.random() * 0.01

    class Fusion:
        def item_risk(self, rows):
            return rows

    cal = [i for i in items if i.question.split == "calibration"]
    test = [i for i in items if i.question.split == "test"]
    out = _threshold_transfer(cal, test, lab, {}, Fusion(), lambda xs: risk[xs[0].id], 0)
    assert out["us_threshold"] is not None
    assert set(out["label_efficiency_curve"]) == {"100", "200", "all"}
    assert out["lk_calibration_labels"] == len([i for i in cal if i.question.country == "LK"])
    # an ambiguous answer sent below the threshold counts as unsafe: give one a low risk and the test risk rises
    worst = next(i for i in test if i.question.country == "LK" and lab[i.id].status == "ambiguous")
    risk[worst.id] = 0.0
    again = _threshold_transfer(cal, test, lab, {}, Fusion(), lambda xs: risk[xs[0].id], 0)
    assert again["lk_test_risk_as_is"]["estimate"] > out["lk_test_risk_as_is"]["estimate"]
