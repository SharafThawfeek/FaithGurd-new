"""The policy study: fit, certify and compare every policy family on replay records.

Splits come from the records (fit, tune, calibration, test; issuer-disjoint). For
each family: order its grid on tune, certify on calibration with Learn-then-Test at
alpha, then report the chosen setting on test with issuer-clustered intervals.
Also: outcome-model quality, regret against the oracle, the flip matrix, results by
group, the certification-budget curve, the issuer-level sensitivity check, and
SCoRE as a comparator for the send-or-abstain decision.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Sequence

import numpy as np

from faithguard.evaluate import flip_matrix, policy_metrics
from faithguard.policy import families, outcome
from faithguard.policy.certify import certify, cluster_pvalue, indicators, states
from faithguard.stats import cluster_bootstrap, fixed_sequence, selective_risk_pvalue

QTYPES = ("lookup", "difference", "growth", "share", "ratio", "sum", "average", "other")


def _source(r) -> str:
    return r.issuer.split(":")[0]


def _qtype(r) -> str:
    return next((q for q in QTYPES if r.features.get(f"qtype_{q}", 0) > 0), "other")


def _ci(records: Sequence, actions: Sequence[str], key: str, seed: int) -> list[float]:
    pairs = list(zip(records, actions))

    def stat(sample):
        return policy_metrics([r.outcomes[a] for r, a in sample])[key]

    est, lo, hi = cluster_bootstrap(pairs, lambda p: p[0].issuer, stat, n_boot=500, seed=seed)
    return [round(est, 4), round(lo, 4), round(hi, 4)]


def _evaluate(name: str, tune, cal, test, cands: tuple[dict, dict, dict], alpha, delta, oracle_useful, seed) -> dict:
    cert = certify(tune, cal, cands[0], cands[1], alpha, delta)
    out = {
        "family": name,
        "settings": len(cands[1]),
        "certified": len(cert.certified),
        "chosen": cert.chosen,
        "calibration": cert.calibration,
        "p_chosen": cert.pvalues.get(cert.chosen) if cert.chosen else None,
    }
    if cert.chosen is None:
        # report the most cautious setting for reference, clearly marked as uncertified
        ref = cert.order[0]
        out["uncertified_reference"] = {"setting": ref, "p": cert.pvalues[ref], "test": policy_metrics(states(test, cands[2][ref]))}
        return out
    acts = cands[2][cert.chosen]
    m = policy_metrics(states(test, acts))
    m["regret"] = oracle_useful - m["useful_coverage"]
    out["test"] = m
    out["test_ci"] = {k: _ci(test, acts, k, seed) for k in ("residual_risk", "useful_coverage", "emission_coverage")}
    out["cluster_p_calibration"] = cluster_pvalue(cal, cands[1][cert.chosen], alpha)
    return out


def budget_curve(cal, test, cal_cands, test_cands, order, alpha, delta, sizes, repeats, seed) -> list[dict]:
    """How many calibration answers are needed to certify, and how much useful coverage that buys on test."""
    rng = np.random.default_rng(seed)
    cal = list(cal)
    rows = []
    for n in sizes:
        if n > len(cal):
            continue
        ok, coverage = 0, []
        for _ in range(repeats):
            idx = rng.choice(len(cal), n, replace=False)
            sub = [cal[i] for i in idx]
            pvals = []
            for name in order:
                acts = [cal_cands[name][i] for i in idx]
                unsafe, sent = indicators(sub, acts)
                pvals.append(selective_risk_pvalue(unsafe, sent, alpha))
            certified = [order[i] for i in fixed_sequence(pvals, delta)]
            if certified:
                ok += 1
                best = max(certified, key=lambda nm: policy_metrics(states(sub, [cal_cands[nm][i] for i in idx]))["useful_coverage"])
                coverage.append(policy_metrics(states(test, test_cands[best]))["useful_coverage"])
        rows.append({
            "calibration_items": n,
            "certified_share": ok / repeats,
            "mean_test_useful_coverage_when_certified": round(float(np.mean(coverage)), 4) if coverage else None,
        })
    return rows


def score_comparator(cal, test, p_cal, p_test, alpha, seed, n_test=500, repeats=3) -> dict:
    """SCoRE (selective deployment risk) for send-or-abstain.

    SCoRE is an e-value method whose power grows with the ratio of calibration to test
    items, and its cost grows with test size times (calibration + test) size; so all
    calibration items are used against random test subsamples, with the package's
    recommended 'homo' boosting (randomised, seeded).
    """
    from SCoRE import SCoRE_SDR

    rng = np.random.default_rng(seed)
    runs = []
    losses = np.array([r.outcomes["send"] == "unsupported" for r in cal], dtype=float)
    # Tree models give many tied scores; conformal methods assume ties are broken at random.
    jitter_cal = np.asarray(p_cal) + rng.uniform(0, 1e-9, len(p_cal))
    jitter_test = np.asarray(p_test) + rng.uniform(0, 1e-9, len(p_test))
    for k in range(repeats):
        ti = rng.choice(len(test), min(n_test, len(test)), replace=False)
        chosen = SCoRE_SDR((losses, jitter_cal), jitter_test[ti], alpha=alpha, gamma=alpha, prune="homo", random_state=seed + k)
        selected = set(int(j) for j in chosen)
        acts = ["send" if k in selected else "abstain" for k in range(len(ti))]
        runs.append(policy_metrics(states([test[i] for i in ti], acts)))
    keys = ("emission_coverage", "residual_risk", "useful_coverage")
    return {
        "guarantee": "expected risk among sent answers <= alpha (not a high-probability bound)",
        "subsample": {"calibration": len(cal), "test": n_test, "repeats": repeats, "prune": "homo"},
        **{k: round(float(np.mean([r[k] for r in runs])), 4) for k in keys},
    }


def run(records: Sequence, alpha: float = 0.10, delta: float = 0.05, kinds=("lightgbm",), seed: int = 0,
        budget_sizes=(50, 100, 200, 400, 800, 1600, 3200), budget_repeats: int = 100, use_score: bool = True) -> dict:
    t0 = time.time()
    split = {s: [r for r in records if r.split == s] for s in ("fit", "tune", "calibration", "test")}
    fit, tune, cal, test = split["fit"], split["tune"], split["calibration"], split["test"]
    oracle_test = families.oracle(test)
    oracle_m = policy_metrics(states(test, oracle_test))
    result: dict = {
        "alpha": alpha,
        "delta": delta,
        "counts": {s: {"items": len(v), "issuers": len({r.issuer for r in v})} for s, v in split.items()},
        "oracle_test": oracle_m,
        "families": [],
        "models": {},
    }

    def add(name, cands):
        result["families"].append(_evaluate(name, tune, cal, test, cands, alpha, delta, oracle_m["useful_coverage"], seed))

    add("send_all", tuple(families.fixed(x, "send") for x in (tune, cal, test)))
    add("repair_all", tuple(families.fixed(x, "repair") for x in (tune, cal, test)))
    add("verified_only", tuple(families.verified_only(x) for x in (tune, cal, test)))
    add("threshold_v0", tuple(families.threshold_v0(x) for x in (tune, cal, test)))

    # static four-state classifier
    from lightgbm import LGBMClassifier

    names = outcome.feature_names(fit)
    clf = LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=15, random_state=seed, deterministic=True, force_row_wise=True, verbose=-1)
    clf.fit(outcome.matrix(fit, names), families.four_state_labels(fit))
    add("four_state", tuple(families.four_state(clf.predict_proba(outcome.matrix(x, names))) for x in (tune, cal, test)))

    preds = {}
    for kind in kinds:
        try:
            models = outcome.fit(fit, kind, seed)
        except ImportError as err:
            result["models"][kind] = {"skipped": str(err)}
            continue
        p = {s: models.predict(x) for s, x in (("tune", tune), ("cal", cal), ("test", test))}
        preds[kind] = p
        result[f"_models_{kind}"] = models
        y_unsafe, y_fix = outcome.targets(test)
        result["models"][kind] = {
            "rows": models.info["rows"],
            "unsafe": {"auroc": outcome.auroc(y_unsafe, p["test"][0]), "brier": outcome.brier(y_unsafe, p["test"][0]), "ece": outcome.ece(y_unsafe, p["test"][0])},
            "fix": {"auroc": outcome.auroc(y_fix, p["test"][1]), "brier": outcome.brier(y_fix, p["test"][1]), "ece": outcome.ece(y_fix, p["test"][1])},
        }
        add(f"outcome_aware[{kind}]", tuple(families.outcome_aware(*p[s]) for s in ("tune", "cal", "test")))

    # the chosen outcome-aware policy, in more detail
    main = next((f for f in result["families"] if f["family"] == "outcome_aware[lightgbm]"), None)
    if main and main.get("chosen") and "lightgbm" in preds:
        p = preds["lightgbm"]
        cands = {s: families.outcome_aware(*p[s]) for s in ("tune", "cal", "test")}
        acts = cands["test"][main["chosen"]]
        result["chosen_detail"] = {
            "flip_matrix_test": flip_matrix((r.outcomes["send"], r.outcomes["repair"]) for r in test),
            "action_mix_test": {a: acts.count(a) for a in ("send", "repair", "abstain")},
            "by_source": {g: policy_metrics([r.outcomes[a] for r, a in zip(test, acts) if _source(r) == g]) for g in sorted({_source(r) for r in test})},
            "by_question_type": {g: policy_metrics([r.outcomes[a] for r, a in zip(test, acts) if _qtype(r) == g]) for g in sorted({_qtype(r) for r in test})},
            "by_error": {g: policy_metrics([r.outcomes[a] for r, a in zip(test, acts) if r.error == g]) for g in sorted({r.error for r in test if r.error})},
        }
        from faithguard.policy.certify import order_settings
        from faithguard.policy.deployed import OutcomeAwarePolicy, parse_setting

        tau_send, tau_fix = parse_setting(main["chosen"])
        lgbm = result.pop("_models_lightgbm")
        result["deployable"] = OutcomeAwarePolicy(
            names=lgbm.names, unsafe_model=lgbm.unsafe, fix_model=lgbm.fix, tau_send=tau_send, tau_fix=tau_fix,
            certificate={"alpha": alpha, "delta": delta, "p_value": main["p_chosen"], "setting": main["chosen"]},
        )
        order = order_settings(tune, cands["tune"])
        result["budget_curve"] = budget_curve(cal, test, cands["cal"], cands["test"], order, alpha, delta, budget_sizes, budget_repeats, seed)
        if use_score:
            try:
                result["score_comparator"] = score_comparator(cal, test, p["cal"][0], p["test"][0], alpha, seed)
            except ImportError as err:
                result["score_comparator"] = {"skipped": str(err)}
    result["seconds"] = round(time.time() - t0, 1)
    return result


def _pct(x) -> str:
    return "–" if x is None else f"{100 * x:.1f}%"


def report(result: dict) -> str:
    a = result["alpha"]
    lines = [
        "# Policy study (controlled track)",
        "",
        f"Risk target alpha = {a}, confidence 1 - delta = {1 - result['delta']}. Splits are issuer-disjoint:",
        "",
        "| Split | Items | Issuers |",
        "| --- | --- | --- |",
    ]
    for s, c in result["counts"].items():
        lines.append(f"| {s} | {c['items']:,} | {c['issuers']:,} |")
    lines += [
        "",
        "These answers were made by the project's error injector from FinQA and TAT-QA gold programs, so they rehearse the method; the paper's claims rest on the human-labelled natural test.",
        "",
        "## Certified policies on the test split",
        "",
        "Each family's grid is ordered on the tune split and certified on the calibration split (Learn-then-Test, Hoeffding-Bentkus, fixed sequence). The chosen setting is then applied to test; brackets are 95% intervals from an issuer-clustered bootstrap.",
        "",
        "| Policy | Certified settings | Chosen | Answers sent | Wrong among sent | Useful answers | Regret vs oracle |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for f in result["families"]:
        if f.get("chosen") is None:
            ref = f.get("uncertified_reference", {})
            t = ref.get("test", {})
            lines.append(f"| {f['family']} | 0 of {f['settings']} | none (p = {ref.get('p', 1):.3g}) | {_pct(t.get('emission_coverage'))} | {_pct(t.get('residual_risk'))} | {_pct(t.get('useful_coverage'))} | – |")
            continue
        t, ci = f["test"], f["test_ci"]
        lines.append(
            f"| {f['family']} | {f['certified']} of {f['settings']} | `{f['chosen']}` | {_pct(t['emission_coverage'])} "
            f"| {_pct(t['residual_risk'])} [{_pct(ci['residual_risk'][1])}, {_pct(ci['residual_risk'][2])}] "
            f"| {_pct(t['useful_coverage'])} [{_pct(ci['useful_coverage'][1])}, {_pct(ci['useful_coverage'][2])}] | {_pct(t['regret'])} |"
        )
    o = result["oracle_test"]
    lines += [f"| oracle (hindsight) | – | – | {_pct(o['emission_coverage'])} | {_pct(o['residual_risk'])} | {_pct(o['useful_coverage'])} | 0 |", ""]

    lines += ["## Outcome models on test", "", "| Model | Target | AUROC | Brier | ECE |", "| --- | --- | --- | --- | --- |"]
    for kind, m in result["models"].items():
        if "skipped" in m:
            lines.append(f"| {kind} | skipped: {m['skipped']} | | | |")
            continue
        for target in ("unsafe", "fix"):
            q = m[target]
            lines.append(f"| {kind} | P({target}) | {q['auroc']:.3f} | {q['brier']:.3f} | {q['ece']:.3f} |")
    lines.append("")

    if "chosen_detail" in result:
        d = result["chosen_detail"]
        lines += ["## The chosen outcome-aware policy", "", f"Actions on test: {d['action_mix_test']}.", ""]
        lines += ["Flip matrix on test (state of the original answer → state after repair):", "", "| Original | Unsupported | Supported, unhelpful | Supported, useful | Abstained |", "| --- | --- | --- | --- | --- |"]
        for row, cols in d["flip_matrix_test"].items():
            lines.append(f"| {row} | {cols['unsupported']} | {cols['supported_unhelpful']} | {cols['supported_useful']} | {cols['abstained']} |")
        for title, key in (("By source", "by_source"), ("By question type", "by_question_type"), ("By planted error", "by_error")):
            lines += ["", f"{title}:", "", "| Group | Items | Sent | Wrong among sent | Useful |", "| --- | --- | --- | --- | --- |"]
            for g, m in d[key].items():
                lines.append(f"| {g} | {m['items']} | {_pct(m['emission_coverage'])} | {_pct(m['residual_risk'])} | {_pct(m['useful_coverage'])} |")
        lines.append("")
    if "budget_curve" in result:
        lines += ["## Certification budget", "", "Random calibration subsets of each size; share of draws in which at least one setting is certified, and the useful coverage on test of the setting then chosen.", "", "| Calibration answers | Certified | Useful coverage on test |", "| --- | --- | --- |"]
        for row in result["budget_curve"]:
            lines.append(f"| {row['calibration_items']} | {_pct(row['certified_share'])} | {_pct(row['mean_test_useful_coverage_when_certified'])} |")
        lines.append("")
    main = next((f for f in result["families"] if f["family"] == "outcome_aware[lightgbm]"), None)
    if main and main.get("chosen"):
        lines += ["## Issuer-level sensitivity check", "", f"Treating each issuer as one draw, the chosen setting's p-value on calibration is {main['cluster_p_calibration']:.3g} (item-level: {main['p_chosen']:.3g}); certified at delta = {result['delta']}: {main['cluster_p_calibration'] <= result['delta']}.", ""]
    if "score_comparator" in result:
        s = result["score_comparator"]
        if "skipped" in s:
            lines += ["## SCoRE comparator", "", f"Skipped: {s['skipped']}", ""]
        else:
            lines += [
                "## SCoRE comparator (send or abstain only)", "",
                f"SCoRE-SDR (score-select 0.1.1) with the same P(unsafe) scores, alpha = gamma = {a}, 'homo' boosting; guarantee: {s['guarantee']}. "
                f"All {s['subsample']['calibration']:,} calibration answers against {s['subsample']['repeats']} random test subsamples of {s['subsample']['test']}.", "",
                f"Answers sent {_pct(s['emission_coverage'])}; wrong among sent {_pct(s['residual_risk'])}; useful {_pct(s['useful_coverage'])}. "
                "It decides only send or abstain, so compare it with verified_only; repair is what lifts the other policies' useful coverage.", "",
            ]
    lines.append(f"Run time: {result['seconds']} s.")
    return "\n".join(lines) + "\n"


def save(result: dict, out: str | Path) -> Path:
    """results.json and report.md; the deployable policy goes to policy.pkl (not committed: rebuilt by the command)."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    deployable = result.get("deployable")
    if deployable is not None:
        deployable.save(out / "policy.pkl")
    clean = {k: v for k, v in result.items() if k != "deployable" and not k.startswith("_models_")}
    (out / "results.json").write_text(json.dumps(clean, indent=2, default=str) + "\n", encoding="utf-8")
    (out / "report.md").write_text(report(clean), encoding="utf-8")
    return out
