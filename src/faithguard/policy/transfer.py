"""The transfer study (policy RQ3): does a policy fitted with repairer v0 stay safe when the repairer becomes v1?

Two replays of the same items, with the same splits and the same detector features, differ only in
their repair outcomes. The v0 policy is the outcome-aware policy fitted on v0's fit records and
certified on v0's calibration records. Three arms are then scored on v1's test records:

    as-is          v0's outcome models and certified setting, unchanged
    recalibrated   v0's outcome models, with the setting certified again on n of v1's calibration
                   records drawn at random (n = 25, 50, 100, 200, and all), so the label cost shows
    refitted       outcome models fitted on v1's fit records, certified on v1's calibration records

P-H3 (pre-registration §2, D-109): the v0 policy is unsafe as-is if the lower end of the issuer-clustered
95% interval of its risk on v1's test records is above alpha; it is restored if, recalibrated on 100 of v1's
calibration labels, it certifies and its test risk is at most alpha in at least half of the draws (the rule
D-107 fixes for D-H3). Confirmed if unsafe as-is and restored; a safe as-is arm, or one only refitting
rescues, are both findings.
"""

from __future__ import annotations

import random
from typing import Sequence

import numpy as np

from faithguard.evaluate import policy_metrics
from faithguard.policy import families, outcome
from faithguard.policy.certify import certify, states
from faithguard.stats import cluster_bootstrap

SPLITS = ("fit", "tune", "calibration", "test")


def _splits(records: Sequence) -> dict[str, list]:
    return {s: [r for r in records if r.split == s] for s in SPLITS}


def _candidates(models: outcome.OutcomeModels, records: Sequence) -> dict[str, list[str]]:
    return families.outcome_aware(*models.predict(records))


def _arm(test: Sequence, actions: Sequence[str], alpha: float) -> dict:
    m = policy_metrics(states(test, actions))
    return m | {"risk_within_alpha": m["residual_risk"] <= alpha}


def _risk_ci(test: Sequence, actions: Sequence[str], seed: int) -> list[float]:
    """[estimate, lower, upper] of the residual risk: issuer-clustered bootstrap, 2,000 resamples (pre-registration §6)."""
    pairs = list(zip(test, actions))
    est, lo, hi = cluster_bootstrap(pairs, lambda x: x[0].issuer, lambda xs: policy_metrics(states(*zip(*xs)) if xs else [])["residual_risk"],
                                    n_boot=2000, seed=seed)
    return [est, lo, hi]


def verdict(result: dict) -> str:
    """P-H3 from the arms: unsafe as-is by the interval, then restored by 100 labels, else whether refitting rescues it."""
    if "as_is" not in result:
        return "untestable (the v0 policy is not certifiable)"
    if not result["unsafe_as_is"]:
        return "rejected: safe as-is"
    first = result["recalibrated"][0] if result["recalibrated"] else {}
    if first.get("labels") == 100 and first.get("restored_share", 0.0) >= 0.5:
        return "confirmed"
    if result.get("refitted") and result["refitted"]["risk_within_alpha"]:
        return "rejected: refitting is needed"
    return "rejected: neither recalibration nor refitting restores it"


# 25 and 50 labels can never certify alpha = 0.10 at the send rates seen (D-102), so recalibration starts at 100
def run(v0: Sequence, v1: Sequence, alpha: float = 0.10, delta: float = 0.05, sizes: Sequence[int] = (100, 200),
        repeats: int = 50, seed: int = 0) -> dict:
    a, b = _splits(v0), _splits(v1)
    result: dict = {"alpha": alpha, "delta": delta, "counts": {s: [len(a[s]), len(b[s])] for s in SPLITS}}
    m0 = outcome.fit(a["fit"], "lightgbm", seed)
    cert0 = certify(a["tune"], a["calibration"], _candidates(m0, a["tune"]), _candidates(m0, a["calibration"]), alpha, delta)
    result["v0_setting"] = cert0.chosen
    if cert0.chosen is None:
        result["skipped"] = "the v0 policy is not certifiable on v0's calibration records"
        result["verdict"] = verdict(result)
        return result
    result["v0_on_v0_test"] = _arm(a["test"], _candidates(m0, a["test"])[cert0.chosen], alpha)
    test_candidates = _candidates(m0, b["test"])  # same features as v0's test records; v1's outcomes
    result["as_is"] = _arm(b["test"], test_candidates[cert0.chosen], alpha)
    result["as_is_risk_ci"] = _risk_ci(b["test"], test_candidates[cert0.chosen], seed)
    result["unsafe_as_is"] = result["as_is_risk_ci"][1] > alpha  # the lower end above alpha (a nan interval is never unsafe)

    tune_candidates, cal_candidates = _candidates(m0, b["tune"]), _candidates(m0, b["calibration"])
    rng = random.Random(seed)
    recalibrated = []
    for n in [*sizes, len(b["calibration"])]:
        n = min(n, len(b["calibration"]))
        draws = 1 if n == len(b["calibration"]) else repeats
        arms = []
        for _ in range(draws):
            idx = sorted(rng.sample(range(len(b["calibration"])), n))
            cert = certify(b["tune"], [b["calibration"][i] for i in idx], tune_candidates,
                           {k: [v[i] for i in idx] for k, v in cal_candidates.items()}, alpha, delta)
            arms.append(_arm(b["test"], test_candidates[cert.chosen], alpha) if cert.chosen else None)
        ok = [x for x in arms if x]
        recalibrated.append({
            "labels": n, "draws": draws, "certified_share": len(ok) / draws,
            "restored_share": sum(x["risk_within_alpha"] for x in ok) / draws,  # certified and within alpha on test
            "mean_risk": float(np.mean([x["residual_risk"] for x in ok])) if ok else None,
            "risk_within_alpha_share": float(np.mean([x["risk_within_alpha"] for x in ok])) if ok else None,
            "mean_useful_coverage": float(np.mean([x["useful_coverage"] for x in ok])) if ok else None,
        })
    result["recalibrated"] = recalibrated

    m1 = outcome.fit(b["fit"], "lightgbm", seed)
    cert1 = certify(b["tune"], b["calibration"], _candidates(m1, b["tune"]), _candidates(m1, b["calibration"]), alpha, delta)
    result["refitted_setting"] = cert1.chosen
    result["refitted"] = _arm(b["test"], _candidates(m1, b["test"])[cert1.chosen], alpha) if cert1.chosen else None
    result["verdict"] = verdict(result)
    return result


def report(result: dict) -> str:
    def pct(x) -> str:
        return "-" if x is None else f"{100 * x:.1f}%"

    lines = ["# Transfer study: the v0 policy when the repairer changes", "",
             f"Alpha {result['alpha']}, delta {result['delta']}. Items per split (v0, v1): {result['counts']}. "
             "See `faithguard.policy.transfer`.", ""]
    if "skipped" in result:
        return "\n".join(lines + [result["skipped"]]) + "\n"
    lines += ["| Arm | Setting | Sent | Wrong among sent | Useful | Within alpha |", "| --- | --- | --- | --- | --- | --- |"]
    for name, key, setting in (("v0 policy on v0 test", "v0_on_v0_test", result["v0_setting"]),
                               ("v0 policy on v1 test, as-is", "as_is", result["v0_setting"]),
                               ("refitted on v1", "refitted", result.get("refitted_setting"))):
        m = result.get(key)
        lines.append(f"| {name} | {setting or '-'} | " + (" | ".join([pct(m["emission_coverage"]), pct(m["residual_risk"]),
                     pct(m["useful_coverage"]), "yes" if m["risk_within_alpha"] else "no"]) if m else "not certifiable | - | - | -") + " |")
    if result.get("as_is_risk_ci"):
        est, lo, hi = result["as_is_risk_ci"]
        lines += ["", f"As-is risk on v1's test records: {pct(est)} [{pct(lo)}, {pct(hi)}] (issuer-clustered 95% interval); "
                  f"unsafe as-is: {'yes' if result['unsafe_as_is'] else 'no'}. P-H3: {result.get('verdict', '-')}."]
    lines += ["", "## Recalibrated on v1 labels (v0's outcome models kept)", "",
              "| v1 calibration labels | Draws | Certified | Restored (certified, within alpha) | Mean wrong among sent | Within alpha | Mean useful |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in result["recalibrated"]:
        lines.append(f"| {r['labels']} | {r['draws']} | {pct(r['certified_share'])} | {pct(r.get('restored_share'))} | {pct(r['mean_risk'])} | "
                     f"{pct(r['risk_within_alpha_share'])} | {pct(r['mean_useful_coverage'])} |")
    return "\n".join(lines) + "\n"
