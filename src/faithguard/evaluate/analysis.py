"""The pre-registered analyses on the labelled main benchmark (phase 7; pre-registration §2 to §7, D-102).

Inputs, all produced after filing: the 800 main items, their gold store with labels (code labels and
Claude's labelling passes, D-100, D-103), every frozen system's stored GPU outputs
(`faithguard.train.systems`, one folder per system) and the released detectors' scores. Each hypothesis
is decided by the issuer-clustered bootstrap 95% interval (2,000 resamples) of its paired difference on
the test split, as the pre-registration states. Offline code: it reads the gold store.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Callable, Sequence

import numpy as np

from faithguard.gold import GoldLabel, GoldStore
from faithguard.records import Item


WRONG_CONTEXT = {"entity_scope", "metric", "period"}
N_BOOT = 2000


def read_rows(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    return {r["item_id"]: r for r in (json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip())}


def load_outputs(folder: str | Path) -> dict[str, dict[str, dict]]:
    """{system: {"detector": rows, "repair_rule_spans": rows, ..., "scores": rows}} from the fetched GPU outputs."""
    out: dict[str, dict[str, dict]] = {}
    for sub in sorted(Path(folder).iterdir()) if Path(folder).exists() else []:
        if sub.is_dir():
            name = sub.name.removeprefix("systems-main-").removeprefix("systems-pilot-").removeprefix("main-base-")
            out[name] = {kind: read_rows(sub / f"{file}.jsonl") for kind, file in (
                ("detector", "detector"), ("repair_rule_spans", "repair-rule-spans"), ("repair_channel_a_spans", "repair-channel-a-spans"),
                ("repair_gold_spans", "repair-gold-spans"), ("neural", "neural"), ("scores", "scores"))}
    return out


def paired(items: Sequence[Item], value: Callable[[list[Item]], float | None], seed: int = 0) -> dict:
    """A statistic on the test items with its issuer-clustered bootstrap 95% interval (resamples where it is undefined are dropped)."""
    groups: dict[str, list[Item]] = {}
    for i in items:
        groups.setdefault(i.question.issuer, []).append(i)
    keys = sorted(groups)
    est = value(list(items))
    rng = random.Random(seed)
    stats = []
    for _ in range(N_BOOT if len(keys) > 1 else 0):
        v = value([i for k in rng.choices(keys, k=len(keys)) for i in groups[k]])
        if v is not None and v == v:
            stats.append(v)
    stats.sort()
    lo = stats[int(0.025 * len(stats))] if stats else float("nan")
    hi = stats[min(len(stats) - 1, int(0.975 * len(stats)))] if stats else float("nan")
    return {"estimate": float("nan") if est is None else est, "ci95": [lo, hi], "items": len(items),
            "issuers": len(keys), "resamples_used": len(stats)}


def decide(d: dict, direction: str) -> str:
    """'confirmed' when the interval excludes zero in the stated direction, else 'no difference'."""
    lo, hi = d["ci95"]
    if any(x != x for x in (lo, hi)):
        return "untestable"
    return "confirmed" if (lo > 0 if direction == "above" else hi < 0) else "no difference"


# ---------------------------------------------------------------- labels

def labels(items: Sequence[Item], gold: GoldStore) -> dict[str, GoldLabel]:
    from faithguard.evaluate.pilot import label_of

    return {i.id: label for i in items if (label := label_of(gold, i.id))}


def wrong(label: GoldLabel) -> bool:
    return label.status == "incorrect"


def wrong_context(label: GoldLabel) -> bool:
    return any(s.slot in WRONG_CONTEXT for s in label.spans)


# ---------------------------------------------------------------- detection (D-H1 to D-H3)

def item_score(det_row: dict | None) -> float:
    """Channel A's item score: its highest probability over any claim or flagged span (0 when nothing)."""
    if not det_row:
        return 0.0
    return max([c["a_max"] for c in det_row["claims"]] + [s["score"] for s in det_row.get("spans", [])] + [0.0])


def detection(items: Sequence[Item], gold: GoldStore, outputs: dict, seed: int = 0) -> dict:
    from faithguard.detect import detect
    from faithguard.detect.fusion import Fusion

    lab = labels(items, gold)
    usable = [i for i in items if i.id in lab and lab[i.id].status != "ambiguous"]
    cal = [i for i in usable if i.question.split == "calibration"]
    test = [i for i in usable if i.question.split == "test"]
    out: dict = {"items": {"calibration": len(cal), "test": len(test)}}

    # D-H1: Channel A with vs without XBRL negatives, recall on wrong-context answers at a 10% clean false-alarm rate
    def threshold(scores: dict[str, float]) -> float:
        clean = sorted(scores[i.id] for i in cal if not wrong(lab[i.id]))
        return clean[int(0.9 * len(clean))] if clean else 1.0

    full = {i.id: item_score(outputs.get("repair-v1", {}).get("detector", {}).get(i.id)) for i in usable}
    noxbrl = {i.id: item_score(outputs.get("channel-a-noxbrl", {}).get("detector", {}).get(i.id)) for i in usable}
    t_full, t_nox = threshold(full), threshold(noxbrl)
    targets = [i for i in test if wrong(lab[i.id]) and wrong_context(lab[i.id])]

    def recall_gap(s: list[Item]) -> float | None:
        s = [i for i in s if wrong(lab[i.id]) and wrong_context(lab[i.id])]
        if not s:
            return None
        return float(np.mean([full[i.id] > t_full for i in s]) - np.mean([noxbrl[i.id] > t_nox for i in s]))

    d_h1 = paired(test, recall_gap, seed)
    out["D-H1"] = {"wrong_context_test_answers": len(targets), "thresholds": {"full": t_full, "no_xbrl": t_nox},
                   "recall_full": float(np.mean([full[i.id] > t_full for i in targets])) if targets else None,
                   "recall_no_xbrl": float(np.mean([noxbrl[i.id] > t_nox for i in targets])) if targets else None,
                   "difference": d_h1,
                   "verdict": "untestable (fewer than 20 wrong-context test answers)" if len(targets) < 20 else decide(d_h1, "above")}

    # the fusion of A and B, fitted on half the calibration issuers and calibrated on the other half
    def claim_rows(subset: list[Item]) -> list[dict]:
        rows = []
        for i in subset:
            det_row = outputs.get("repair-v1", {}).get("detector", {}).get(i.id)
            if not det_row:
                continue
            claims = {c.id: c for c in detect(i).claims}
            spans = [(s.start, s.end) for s in lab[i.id].spans]
            for c in det_row["claims"]:
                claim = claims.get(c["claim_id"])
                if claim is None:
                    continue
                hit = any(claim.start < b and a < claim.end for a, b in spans)
                rows.append(c | {"label": int(hit), "item_id": i.id, "start": claim.start, "end": claim.end})
        return rows

    halves = [[i for i in cal if hash_half(i.question.issuer) == h] for h in (0, 1)]
    fit_rows, cal_rows = claim_rows(halves[0]), claim_rows(halves[1])
    fusion = None
    if fit_rows and cal_rows and len({r["label"] for r in fit_rows}) == 2:
        fusion = Fusion.fit(fit_rows)
        fusion.calibrate(cal_rows)

    # D-H2: span F1 of A + B against B alone, on the Sri Lankan test answers
    lk_test = [i for i in test if i.question.country == "LK"]
    pred_b, pred_ab = {}, {}
    for i in lk_test:
        det = detect(i)
        pred_b[i.id] = [(c.start, c.end) for c, ch in zip(det.claims, det.checks) if ch.verdict != "supported"]
        rows = claim_rows([i])
        probs = fusion.claim_probs(rows) if fusion and rows else []
        pred_ab[i.id] = [(r["start"], r["end"]) for r, p in zip(rows, probs) if p >= 0.5]

    def f1(subset: list[Item], pred: dict) -> float | None:
        tp = fp = fn = 0
        for i in subset:
            g = set().union(*[set(range(s.start, s.end)) for s in lab[i.id].spans]) if lab[i.id].spans else set()
            p = set().union(*[set(range(a, b)) for a, b in pred[i.id]]) if pred[i.id] else set()
            tp, fp, fn = tp + len(g & p), fp + len(p - g), fn + len(g - p)
        return 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None

    d_h2 = paired(lk_test, lambda s: (f1(s, pred_ab) or 0.0) - (f1(s, pred_b) or 0.0), seed)
    out["D-H2"] = {"span_f1_b": f1(lk_test, pred_b), "span_f1_a_plus_b": f1(lk_test, pred_ab), "difference": d_h2,
                   "verdict": decide(d_h2, "above") if fusion else "untestable (fusion could not be fitted)"}

    # D-H3: a fused-risk threshold certified on US calibration answers, then on Sri Lanka as-is and recalibrated
    out["D-H3"] = _threshold_transfer(cal, test, lab, outputs, fusion, claim_rows, seed) if fusion else {"verdict": "untestable"}

    # every detector on the test split: AUROC, clean false alarms at its calibration threshold
    scores = {"channel-a": full, "channel-a-noxbrl": noxbrl,
              "channel-a-noslot": {i.id: item_score(outputs.get("channel-a-noslot", {}).get("detector", {}).get(i.id)) for i in usable},
              "channel-b": {i.id: detect(i).risk for i in usable}}
    if fusion:
        scores["fused-a+b"] = {i.id: fusion.item_risk(claim_rows([i])) for i in usable}
    for name in ("lettuce-v1", "lettuce-v2", "hhem", "granite"):
        rows = outputs.get(name, {}).get("scores", {})
        if rows:
            scores[name] = {i.id: float(rows.get(i.id, {}).get("risk", 0.0)) for i in usable}
    out["detectors"] = {name: _detector_metrics(s, cal, test, lab) for name, s in scores.items()}
    return out


def hash_half(text: str) -> int:
    import hashlib

    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % 2


def _detector_metrics(scores: dict[str, float], cal: list[Item], test: list[Item], lab: dict) -> dict:
    from sklearn.metrics import roc_auc_score

    clean_cal = sorted(scores[i.id] for i in cal if not wrong(lab[i.id]))
    t = clean_cal[int(0.9 * len(clean_cal))] if clean_cal else 1.0
    y = [int(wrong(lab[i.id])) for i in test]
    s = [scores[i.id] for i in test]
    return {"auroc": float(roc_auc_score(y, s)) if len(set(y)) == 2 else None,
            "threshold_at_10pct_calibration_false_alarms": t,
            "test_false_alarms": float(np.mean([v > t for v, w in zip(s, y) if not w])) if y.count(0) else None,
            "test_recall": float(np.mean([v > t for v, w in zip(s, y) if w])) if sum(y) else None,
            "test_wrong_context_recall": float(np.mean([scores[i.id] > t for i in test if wrong(lab[i.id]) and wrong_context(lab[i.id])]))
            if any(wrong(lab[i.id]) and wrong_context(lab[i.id]) for i in test) else None}


def _threshold_transfer(cal, test, lab, outputs, fusion, claim_rows, seed, alpha: float = 0.10, delta: float = 0.05) -> dict:
    """Send an answer when its fused risk is below t; certify t by Learn-then-Test (Hoeffding-Bentkus, fixed sequence)."""
    from faithguard.stats import fixed_sequence, selective_risk_pvalue

    grid = (0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)
    risk = {i.id: fusion.item_risk(claim_rows([i])) for i in cal + test}

    def certify(subset: list[Item]) -> float | None:
        ps = []
        for t in grid:  # most cautious first
            sent = [risk[i.id] < t for i in subset]
            unsafe = [s and lab[i.id].status in ("incorrect", "ambiguous") for s, i in zip(sent, subset)]
            ps.append(selective_risk_pvalue(unsafe, sent, alpha))
        ok = fixed_sequence(ps, delta)
        return grid[ok[-1]] if ok else None

    def test_risk(subset: list[Item], t: float | None) -> float | None:
        if t is None:
            return None
        sent = [i for i in subset if risk[i.id] < t]
        return float(np.mean([lab[i.id].status in ("incorrect", "ambiguous") for i in sent])) if sent else 0.0

    us_cal = [i for i in cal if i.question.country == "US"]
    lk_cal = [i for i in cal if i.question.country == "LK"]
    lk_test = [i for i in test if i.question.country == "LK"]
    t_us = certify(us_cal)
    as_is = paired(lk_test, lambda s: test_risk(s, t_us), seed) if t_us is not None else None
    rng = random.Random(seed)
    restored = []
    for _ in range(50):
        draw = rng.sample(lk_cal, min(100, len(lk_cal)))
        t = certify(draw)
        restored.append(t is not None and (test_risk(lk_test, t) or 0.0) <= alpha)
    fails = as_is is not None and as_is["ci95"][0] > alpha
    return {"us_threshold": t_us, "lk_test_risk_as_is": as_is, "restored_share_with_100_lk_labels": float(np.mean(restored)),
            "verdict": "confirmed" if fails and np.mean(restored) >= 0.5 else
                       ("holds without recalibration" if as_is is not None and not fails else "untestable (no US threshold certified)")}


# ---------------------------------------------------------------- repair (R-H1 to R-H3)

def repair(items: Sequence[Item], gold: GoldStore, outputs: dict, gold_spans: dict[str, list] | None, seed: int = 0) -> dict:
    from faithguard.evaluate.repair import summarise
    from faithguard.evaluate.systems import LABEL_STATE, score_rows

    lab = labels(items, gold)
    state = {i: LABEL_STATE[x.status] for i, x in lab.items() if x.status in LABEL_STATE}
    test = [i for i in items if i.question.split == "test"]
    by_id = {i.id: i for i in items}
    rows_by = {}
    for system in ("repair-v1", "repair-sft", "repair-sft-nokeep", "stage-b", "rewrite-v1"):
        o = outputs.get(system)
        if not o or not o["detector"]:
            continue
        repairs = {"rule_spans": o["repair_rule_spans"], "channel_a_spans": o["repair_channel_a_spans"], "gold_spans": o["repair_gold_spans"]}
        rows = score_rows(test, gold, o["detector"], repairs, state, gold_spans)
        for name, rs in rows.items():
            key = name.replace("trained repairer", system) if name.startswith("trained") else name
            rows_by.setdefault(key, rs)
    out: dict = {"summaries": {k: summarise(v) for k, v in sorted(rows_by.items())}}

    def rate(rs: list[dict], keep: Callable[[dict], bool], hit: Callable[[dict], bool]) -> float | None:
        kept = [r for r in rs if keep(r)]
        return float(np.mean([hit(r) for r in kept])) if kept else None

    def diff(a: str, b: str, keep, hit, direction: str, subset: Callable[[Item], bool] = lambda i: True) -> dict:
        ra = {r["item_id"]: r for r in rows_by.get(a, [])}
        rb = {r["item_id"]: r for r in rows_by.get(b, [])}
        common = [by_id[i] for i in ra if i in rb and subset(by_id[i])]

        def value(s: list[Item]) -> float | None:
            x, y = rate([ra[i.id] for i in s], keep, hit), rate([rb[i.id] for i in s], keep, hit)
            return None if x is None or y is None else x - y

        d = paired(common, value, seed)
        return d | {"verdict": decide(d, direction), "a": a, "b": b}

    sent = lambda r: r["after"] != "abstained"
    needs = lambda r: r["before"] == "unsupported"
    clean = lambda r: r["before"] != "unsupported"
    new_error = lambda r: bool(r["new_errors"])
    corrected = lambda r: r["after"] == "supported_useful"
    damaged = lambda r: r["after"] == "unsupported"

    # R-H1: programs (v1) vs free rewriting, with the labelled spans: new errors lower, correction within 5 points
    new_err = diff("repair-v1, gold_spans", "rewrite-v1, gold_spans", sent, new_error, "below")
    corr = diff("repair-v1, gold_spans", "rewrite-v1, gold_spans", needs, corrected, "above")
    margin_ok = corr["estimate"] == corr["estimate"] and corr["estimate"] >= -0.05
    out["R-H1"] = {"new_error_difference": new_err, "correction_difference": corr,
                   "verdict": ("confirmed" if new_err["verdict"] == "confirmed" and margin_ok else
                               "not decidable at a matched rate" if not margin_ok else "no difference")}
    # R-H2: self-training (stage B) vs supervised (stage A): held-out basis errors and Gemma's answers
    basis = lambda i: i.id in lab and any(s.slot == "basis" for s in lab[i.id].spans)
    gemma = lambda i: i.answer.generator.startswith("gemma")
    r2 = {"basis": diff("stage-b, rule_spans", "repair-sft, rule_spans", needs, corrected, "above", basis),
          "gemma": diff("stage-b, rule_spans", "repair-sft, rule_spans", needs, corrected, "above", gemma)}
    out["R-H2"] = r2 | {"verdict": "confirmed" if all(x["verdict"] == "confirmed" for x in r2.values()) else "not confirmed"}
    # R-H3: KEEP training (stage A) vs no-KEEP, damage with Channel A's spans
    r3 = diff("repair-sft, channel_a_spans", "repair-sft-nokeep, channel_a_spans", clean, damaged, "below")
    out["R-H3"] = r3
    return out


# ---------------------------------------------------------------- policy (P-H1 to P-H3)

def natural_records(items: Sequence[Item], gold: GoldStore, repairs: dict[str, dict], rule_repairer: bool = False) -> list:
    """Replay records for the benchmark answers: an original's state from its label, a repair's from the gold scorer."""
    from faithguard.detect import detect
    from faithguard.evaluate.score import score_text
    from faithguard.evaluate.systems import LABEL_STATE
    from faithguard.policy.features import features
    from faithguard.records import RepairOutput
    from faithguard.repair import rules
    from faithguard.replay import ReplayRecord

    lab = labels(items, gold)
    records = []
    for i in items:
        if i.id not in lab or lab[i.id].status not in LABEL_STATE:
            continue
        det = detect(i)
        before = LABEL_STATE[lab[i.id].status]
        if rule_repairer:
            out = rules.repair(i, det)
        elif i.id in repairs:
            out = RepairOutput.model_validate(repairs[i.id])
        else:
            continue
        text = out.text if out.status in ("repaired", "nothing_to_fix") else None
        after = "abstained" if text is None else before if text == i.answer.text else score_text(text, gold.questions[i.question.id], i.evidence)
        records.append(ReplayRecord(item_id=i.id, question_id=i.question.id, issuer=i.question.issuer, split=i.question.split,
                                    error=None, expected_action=None, features=features(i, det), risk=det.risk, decision="send",
                                    outcomes={"send": before, "repair": after, "abstain": "abstained"}, repair_status=out.status))
    return records


def policy(items: Sequence[Item], gold: GoldStore, outputs: dict, controlled: list, controlled_v1: list | None = None, seed: int = 0) -> dict:
    """controlled: the rule repairer's controlled-track replays; controlled_v1: repairer v1's (the transfer_replays run)."""
    from faithguard.evaluate import policy_metrics
    from faithguard.policy import study, transfer

    v1 = outputs.get("repair-v1", {}).get("repair_rule_spans", {})
    natural = natural_records(items, gold, v1)
    fit_tune = [r for r in controlled if r.split in ("fit", "tune")]
    result = study.run(fit_tune + natural, seed=seed, use_score=False, budget_sizes=(100, 200, 400), budget_repeats=50)
    test = [r for r in natural if r.split == "test"]
    by = {f["family"]: f for f in result["families"]}
    ours, theirs = by.get("outcome_aware[lightgbm]", {}), by.get("verified_only", {})
    a, b = ours.get("_test_actions"), theirs.get("_test_actions")
    out: dict = {"study": {k: v for k, v in result.items() if not k.startswith("_models_") and k != "deployable"}}
    out["study"]["families"] = [{k: v for k, v in f.items() if not k.startswith("_")} for f in result["families"]]
    if a and b:
        idx = {r.item_id: n for n, r in enumerate(test)}
        items_test = [i for i in items if i.id in idx]

        def gap(s: list[Item]) -> float:
            sel = [idx[i.id] for i in s]
            ua = policy_metrics([test[n].outcomes[a[n]] for n in sel])["useful_coverage"]
            ub = policy_metrics([test[n].outcomes[b[n]] for n in sel])["useful_coverage"]
            return ua - ub

        d = paired(items_test, gap, seed)
        out["P-H1"] = d | {"comparator_certified": theirs.get("chosen") is not None,
                           "verdict": decide(d, "above") if ours.get("chosen") else "outcome-aware policy not certified"}
        out["P-H2"] = {"certified": ours.get("chosen") is not None, "useful_coverage_test": (ours.get("test") or {}).get("useful_coverage"),
                       "verdict": "confirmed" if ours.get("chosen") and out["P-H1"]["estimate"] > 0 else "not confirmed"}
    # P-H3: the policy fitted with the rule repairer (v0) on its natural records, as-is and recalibrated on v1's
    v0_natural = natural_records(items, gold, {}, rule_repairer=True)
    v0_all = fit_tune + v0_natural
    v1_fit_tune = [r for r in (controlled_v1 or []) if r.split in ("fit", "tune")] or fit_tune
    v1_all = v1_fit_tune + natural
    try:
        t = transfer.run(v0_all, v1_all, seed=seed)
        out["P-H3"] = t
    except Exception as err:  # noqa: BLE001 - reported, not hidden
        out["P-H3"] = {"error": str(err)}
    return out


def report(result: dict) -> str:
    def f(x, pct=True):
        if x is None or x != x:
            return "-"
        return f"{100 * x:.1f}%" if pct else f"{x:.3f}"

    def ci(d, pct=True):
        return f"{f(d['estimate'], pct)} [{f(d['ci95'][0], pct)}, {f(d['ci95'][1], pct)}]"

    det, rep, pol = result.get("detection", {}), result.get("repair", {}), result.get("policy", {})
    lines = ["# Phase 7: the pre-registered analyses on the main benchmark", "",
             "Test split; intervals are issuer-clustered bootstrap 95% (2,000 resamples). Labels: code labels with an audit (D-100) "
             "and Claude's labelling passes (D-103). See `faithguard.evaluate.analysis`.", "", "## Hypotheses", "",
             "| Hypothesis | Estimate [95% interval] | Verdict |", "| --- | --- | --- |"]
    if "D-H1" in det:
        lines.append(f"| D-H1 XBRL negatives raise wrong-context recall (difference) | {ci(det['D-H1']['difference'])} | {det['D-H1']['verdict']} |")
    if "D-H2" in det:
        lines.append(f"| D-H2 A + B beats B on Sri Lanka (span F1 difference) | {ci(det['D-H2']['difference'], False)} | {det['D-H2']['verdict']} |")
    if "D-H3" in det:
        d = det["D-H3"]
        shown = ci(d["lk_test_risk_as_is"]) if d.get("lk_test_risk_as_is") else "-"
        lines.append(f"| D-H3 US threshold on Sri Lanka (risk as-is; restored with 100 labels {f(d.get('restored_share_with_100_lk_labels'))}) | {shown} | {d['verdict']} |")
    if "R-H1" in rep:
        lines.append(f"| R-H1 programs make fewer new errors (difference; correction {ci(rep['R-H1']['correction_difference'])}) | "
                     f"{ci(rep['R-H1']['new_error_difference'])} | {rep['R-H1']['verdict']} |")
    if "R-H2" in rep:
        lines.append(f"| R-H2 self-training helps out of distribution (basis {ci(rep['R-H2']['basis'])}) | Gemma {ci(rep['R-H2']['gemma'])} | {rep['R-H2']['verdict']} |")
    if "R-H3" in rep:
        lines.append(f"| R-H3 KEEP training cuts damage (difference) | {ci(rep['R-H3'])} | {rep['R-H3']['verdict']} |")
    if "P-H1" in pol:
        lines.append(f"| P-H1 outcome-aware beats the detector threshold (useful coverage difference) | {ci(pol['P-H1'])} | {pol['P-H1']['verdict']} |")
    if "P-H2" in pol:
        lines.append(f"| P-H2 alpha = 0.10 certifiable at useful coverage | {f(pol['P-H2']['useful_coverage_test'])} | {pol['P-H2']['verdict']} |")
    if "P-H3" in pol and "as_is" in pol["P-H3"]:
        a = pol["P-H3"]["as_is"]
        lines.append(f"| P-H3 v0 policy on v1 (risk as-is) | {f(a.get('residual_risk'))} | {'unsafe' if not a.get('risk_within_alpha') else 'safe as-is'} |")
    if det.get("detectors"):
        lines += ["", "## Detectors on the test split", "", "| Detector | AUROC | False alarms | Recall | Wrong-context recall |", "| --- | --- | --- | --- | --- |"]
        for name, m in det["detectors"].items():
            lines.append(f"| {name} | {f(m['auroc'], False)} | {f(m['test_false_alarms'])} | {f(m['test_recall'])} | {f(m['test_wrong_context_recall'])} |")
    if rep.get("summaries"):
        lines += ["", "## Repair on the test split", "", "| Repairer, spans | Wrong originals | Corrected | Withheld when needed | New errors | Damage |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for name, s in rep["summaries"].items():
            lines.append(f"| {name} | {s['needing_repair']} | {f(s['correction_rate'])} | {f(s['abstained_when_needed'])} | {f(s['new_error_rate'])} | {f(s['damage_rate'])} |")
    if pol.get("study"):
        lines += ["", "## Policies on the test split (certified on calibration, alpha = 0.10)", "",
                  "| Policy | Certified | Sent | Wrong among sent | Useful |", "| --- | --- | --- | --- | --- |"]
        for fam in pol["study"]["families"]:
            t = fam.get("test") or {}
            lines.append(f"| {fam['family']} | {fam['certified']} of {fam['settings']} | {f(t.get('emission_coverage'))} | {f(t.get('residual_risk'))} | {f(t.get('useful_coverage'))} |")
    return "\n".join(lines) + "\n"
