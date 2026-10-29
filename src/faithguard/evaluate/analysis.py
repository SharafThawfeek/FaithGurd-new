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
GRID = (0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)  # fused-risk thresholds for sending an answer, most cautious first
UNSAFE = ("incorrect", "ambiguous")  # in risk metrics an ambiguous answer counts as unsafe (pre-registration §5, D-089)


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
        return _span_f1(subset, pred, lab)

    d_h2 = (paired(lk_test, lambda s: (f1(s, pred_ab) or 0.0) - (f1(s, pred_b) or 0.0), seed) if fusion
            else {"estimate": float("nan"), "ci95": [float("nan"), float("nan")], "items": len(lk_test)})
    out["D-H2"] = {"span_f1_b": f1(lk_test, pred_b), "span_f1_a_plus_b": f1(lk_test, pred_ab), "difference": d_h2,
                   "verdict": decide(d_h2, "above") if fusion else "untestable (fusion could not be fitted)"}

    # span metrics on every test answer (pre-registration §5, §7): B, A + B, Channel A alone and without its slot head
    spans: dict[str, dict] = {"channel-b": {}, "fused-a+b": {}}
    for i in test:
        det = detect(i)
        spans["channel-b"][i.id] = [(c.start, c.end, None) for c, ch in zip(det.claims, det.checks) if ch.verdict != "supported"]
        rows = claim_rows([i])
        probs = fusion.claim_probs(rows) if fusion and rows else []
        spans["fused-a+b"][i.id] = [(r["start"], r["end"], None) for r, p in zip(rows, probs) if p >= 0.5]
    if not fusion:
        del spans["fused-a+b"]
    for name, system in (("channel-a", "repair-v1"), ("channel-a-noslot", "channel-a-noslot")):
        rows = outputs.get(system, {}).get("detector", {})
        if rows:
            spans[name] = {i.id: [(x["start"], x["end"], x.get("slot")) for x in (rows.get(i.id) or {}).get("spans", [])] for i in test}
    out["spans"] = {name: _span_metrics(test, pred, lab, seed, slotted=name == "channel-a") for name, pred in spans.items()}

    # D-H3: a fused-risk threshold certified on US calibration answers, then on Sri Lanka as-is and recalibrated;
    # a risk metric, so ambiguous answers stay in and count as unsafe (pre-registration §5, D-089)
    labelled = [i for i in items if i.id in lab]
    cal_all = [i for i in labelled if i.question.split == "calibration"]
    test_all = [i for i in labelled if i.question.split == "test"]
    out["D-H3"] = _threshold_transfer(cal_all, test_all, lab, outputs, fusion, claim_rows, seed) if fusion else {"verdict": "untestable"}

    if fusion:
        # the fused probabilities' calibration on test (Brier score, ECE), per claim and per answer
        test_claims = {i.id: claim_rows([i]) for i in test}
        claim_p = {k: list(fusion.claim_probs(rows)) if rows else [] for k, rows in test_claims.items()}
        fused_item = {i.id: fusion.item_risk(test_claims[i.id]) for i in test}

        def calibration(metric, per_claim: bool):
            from faithguard.policy import outcome

            def value(sub: list[Item]) -> float | None:
                if per_claim:
                    y = [r["label"] for i in sub for r in test_claims[i.id]]
                    pr = [q for i in sub for q in claim_p[i.id]]
                else:
                    y, pr = [int(wrong(lab[i.id])) for i in sub], [fused_item[i.id] for i in sub]
                return float(getattr(outcome, metric)(np.array(y, dtype=float), np.array(pr, dtype=float))) if y else None
            return paired(test, value, seed)

        out["fused_calibration"] = {level: {m: calibration(m, level == "claim") for m in ("brier", "ece")} for level in ("claim", "answer")}
        # coverage at certified selective risk: the fused-risk threshold certified on every calibration answer, applied to test
        risk = {i.id: fusion.item_risk(claim_rows([i])) for i in cal_all + test_all}
        t = _certify_threshold(cal_all, risk, lab)
        out["selective"] = {"threshold": t, "certified": t is not None,
                            "test_coverage": paired(test_all, lambda sub: float(np.mean([risk[i.id] < t for i in sub])) if sub else None, seed)
                            if t is not None else None,
                            "test_risk": paired(test_all, lambda sub: _sent_risk(sub, risk, lab, t), seed) if t is not None else None}

    # every detector on the test split: AUROC, clean false alarms at its calibration threshold, with intervals (§7)
    scores = {"channel-a": full} if outputs.get("repair-v1", {}).get("detector") else {}
    for name in ("channel-a-noxbrl", "channel-a-noslot"):
        if outputs.get(name, {}).get("detector"):
            scores[name] = noxbrl if name == "channel-a-noxbrl" else {i.id: item_score(outputs[name]["detector"].get(i.id)) for i in usable}
    scores["channel-b"] = {i.id: detect(i).risk for i in usable}
    if fusion:
        scores["fused-a+b"] = {i.id: fusion.item_risk(claim_rows([i])) for i in usable}
    for name in ("lettuce-v1", "lettuce-v2", "hhem", "granite"):
        rows = outputs.get(name, {}).get("scores", {})
        if rows:
            scores[name] = {i.id: float(rows.get(i.id, {}).get("risk", 0.0)) for i in usable}
    out["detectors"] = {name: _detector_metrics(sc, cal, test, lab, seed) for name, sc in scores.items()}
    # AUROC differences: the fused detector against each other one, and Channel A with against without its slot head
    pairs = [("fused-a+b", n) for n in scores if n != "fused-a+b" and "fused-a+b" in scores]
    pairs += [("channel-a", "channel-a-noslot")] if {"channel-a", "channel-a-noslot"} <= set(scores) else []

    def auroc_gap(x: str, y: str):
        def value(sub: list[Item]) -> float | None:
            a, b = _auroc(scores[x], sub, lab), _auroc(scores[y], sub, lab)
            return None if a is None or b is None else a - b
        return value

    out["auroc_differences"] = {f"{x} minus {y}": paired(test, auroc_gap(x, y), seed) for x, y in pairs}
    return out


def hash_half(text: str) -> int:
    import hashlib

    return int(hashlib.sha256(text.encode()).hexdigest(), 16) % 2


def _auroc(scores: dict[str, float], subset: list[Item], lab: dict) -> float | None:
    from sklearn.metrics import roc_auc_score

    y = [int(wrong(lab[i.id])) for i in subset]
    return float(roc_auc_score(y, [scores[i.id] for i in subset])) if len(set(y)) == 2 else None


def _detector_metrics(scores: dict[str, float], cal: list[Item], test: list[Item], lab: dict, seed: int = 0) -> dict:
    """AUROC, and at the threshold flagging 10% of the clean calibration answers the false alarms and recall on test, each
    with its issuer-clustered interval (secondary analyses carry the same intervals, pre-registration §7)."""
    clean_cal = sorted(scores[i.id] for i in cal if not wrong(lab[i.id]))
    t = clean_cal[int(0.9 * len(clean_cal))] if clean_cal else 1.0

    def flagged(keep: Callable[[Item], bool]):
        def value(sub: list[Item]) -> float | None:
            kept = [i for i in sub if keep(i)]
            return float(np.mean([scores[i.id] > t for i in kept])) if kept else None
        return value

    return {"auroc": paired(test, lambda sub: _auroc(scores, sub, lab), seed),
            "threshold_at_10pct_calibration_false_alarms": t,
            # tied scores (Granite's are 0 or 1) cannot flag exactly 10%: the share of clean calibration answers flagged
            "calibration_false_alarms": float(np.mean([v > t for v in clean_cal])) if clean_cal else None,
            "test_false_alarms": paired(test, flagged(lambda i: not wrong(lab[i.id])), seed),
            "test_recall": paired(test, flagged(lambda i: wrong(lab[i.id])), seed),
            "test_wrong_context_recall": paired(test, flagged(lambda i: wrong(lab[i.id]) and wrong_context(lab[i.id])), seed)}


def _span_chars(spans) -> set[int]:
    return {c for a, b, *_ in spans for c in range(a, b)}


def _span_f1(subset: list[Item], pred: dict, lab: dict) -> float | None:
    """Character-overlap span F1 against the labelled spans (D-089)."""
    tp = fp = fn = 0
    for i in subset:
        g = _span_chars((x.start, x.end) for x in lab[i.id].spans)
        q = _span_chars(pred.get(i.id, []))
        tp, fp, fn = tp + len(g & q), fp + len(q - g), fn + len(g - q)
    return 2 * tp / (2 * tp + fp + fn) if (2 * tp + fp + fn) else None


def _span_metrics(test: list[Item], pred: dict, lab: dict, seed: int, slotted: bool = False) -> dict:
    """Span F1, the share of each gold slot's characters found, and (for a detector that names slots) how often the predicted
    span overlapping a gold span names its slot, as train/detector_eval.py computes them; ambiguous answers are left out."""
    def slot_recall(slot: str):
        def value(sub: list[Item]) -> float | None:
            tp = fn = 0
            for i in sub:
                q = _span_chars(pred.get(i.id, []))
                for x in lab[i.id].spans:
                    if (x.slot or "none") == slot:
                        g = set(range(x.start, x.end))
                        tp, fn = tp + len(g & q), fn + len(g - q)
            return tp / (tp + fn) if tp + fn else None
        return value

    def slot_accuracy(sub: list[Item]) -> float | None:
        hits = []
        for i in sub:
            for x in lab[i.id].spans:
                match = next((q for q in pred.get(i.id, []) if q[0] < x.end and q[1] > x.start), None)
                if match is not None and x.slot:
                    hits.append(match[2] == x.slot)
        return float(np.mean(hits)) if hits else None

    slots = sorted({x.slot or "none" for i in test for x in lab[i.id].spans})  # spans with no slot as "none", like detector_eval
    out = {"span_f1": paired(test, lambda sub: _span_f1(sub, pred, lab), seed),
           "recall_by_slot": {slot: paired(test, slot_recall(slot), seed) for slot in slots}}
    if slotted:
        out["slot_accuracy"] = paired(test, slot_accuracy, seed)
    return out


def _certify_threshold(subset: list[Item], risk: dict[str, float], lab: dict, alpha: float = 0.10, delta: float = 0.05) -> float | None:
    """Send an answer when its fused risk is below t; certify t by Learn-then-Test (Hoeffding-Bentkus, fixed sequence)."""
    from faithguard.stats import fixed_sequence, selective_risk_pvalue

    ps = []
    for t in GRID:  # most cautious first
        sent = [risk[i.id] < t for i in subset]
        unsafe = [x and lab[i.id].status in UNSAFE for x, i in zip(sent, subset)]
        ps.append(selective_risk_pvalue(unsafe, sent, alpha))
    ok = fixed_sequence(ps, delta)
    return GRID[ok[-1]] if ok else None


def _sent_risk(subset: list[Item], risk: dict[str, float], lab: dict, t: float | None) -> float | None:
    if t is None:
        return None
    sent = [i for i in subset if risk[i.id] < t]
    return float(np.mean([lab[i.id].status in UNSAFE for i in sent])) if sent else 0.0


def _threshold_transfer(cal, test, lab, outputs, fusion, claim_rows, seed, alpha: float = 0.10, delta: float = 0.05) -> dict:
    """D-H3: the fused-risk threshold certified on US calibration answers, on Sri Lanka as-is and recalibrated."""
    risk = {i.id: fusion.item_risk(claim_rows([i])) for i in cal + test}

    def certify(subset: list[Item]) -> float | None:
        return _certify_threshold(subset, risk, lab, alpha, delta)

    def test_risk(subset: list[Item], t: float | None) -> float | None:
        return _sent_risk(subset, risk, lab, t)

    us_cal = [i for i in cal if i.question.country == "US"]
    lk_cal = [i for i in cal if i.question.country == "LK"]
    lk_test = [i for i in test if i.question.country == "LK"]
    t_us = certify(us_cal)
    as_is = paired(lk_test, lambda s: test_risk(s, t_us), seed) if t_us is not None else None
    rng = random.Random(seed)

    def restored_share(size: int | None) -> float:
        """Share of 50 random draws of `size` Sri Lankan calibration labels (all of them: one draw) whose threshold holds on test."""
        draws = [lk_cal] if size is None or size >= len(lk_cal) else [rng.sample(lk_cal, size) for _ in range(50)]
        held = []
        for draw in draws:
            t = certify(draw)
            held.append(t is not None and (test_risk(lk_test, t) or 0.0) <= alpha)
        return float(np.mean(held))

    restored = restored_share(100)  # the hypothesis: restored when at least half the 100-label draws hold
    curve = {"100": restored, "200": restored_share(200), "all": restored_share(None)}  # pre-registration §6, reported
    fails = as_is is not None and as_is["ci95"][0] > alpha
    if t_us is None:
        verdict = "untestable (no US threshold certified)"
    elif not fails:
        verdict = "rejected: holds without recalibration"
    elif restored >= 0.5:
        verdict = "confirmed"
    else:
        verdict = "not confirmed: fails as-is, not restored with 100 labels"
    return {"us_threshold": t_us, "lk_test_risk_as_is": as_is, "restored_share_with_100_lk_labels": restored,
            "label_efficiency_curve": curve, "lk_calibration_labels": len(lk_cal), "verdict": verdict}


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


def neural_predictions(outputs: dict, controlled_predictions: str | Path, path: str | Path) -> Path | None:
    """One file of the neural outcome model's probabilities (D-096) for every record the benchmark run scores: the controlled
    track's (its tune records order the grid) and the main answers' from systems_main, keyed as outcome.Scores reads them."""
    from faithguard.policy.neural import row_key

    rows = outputs.get("repair-v1", {}).get("neural", {})
    if not rows or not Path(controlled_predictions).exists():
        return None
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(Path(controlled_predictions).read_text(encoding="utf-8").rstrip("\n") + "\n")
        for item_id, r in sorted(rows.items()):
            f.write(json.dumps({"key": row_key(item_id), "split": "natural", "p_unsafe": r["p_unsafe"], "p_fix": r["p_fix"]}) + "\n")
    return path


def _useful_gap(records: list, items: Sequence[Item], a: Sequence[str], b: Sequence[str], seed: int) -> dict:
    """Useful coverage of actions a minus actions b on the same records, with its issuer-clustered interval."""
    from faithguard.evaluate import policy_metrics

    idx = {r.item_id: n for n, r in enumerate(records)}
    sub_items = [i for i in items if i.id in idx]

    def gap(s: list[Item]) -> float:
        sel = [idx[i.id] for i in s]
        return (policy_metrics([records[n].outcomes[a[n]] for n in sel])["useful_coverage"]
                - policy_metrics([records[n].outcomes[b[n]] for n in sel])["useful_coverage"])

    return paired(sub_items, gap, seed)


def _group_risk(records: list, items: Sequence[Item], actions: Sequence[str], seed: int) -> dict:
    """Residual risk of the chosen policy on test by group (pre-registration §6: numeric vs narrative, US vs Sri Lanka)."""
    from faithguard.evaluate import policy_metrics

    idx = {r.item_id: n for n, r in enumerate(records)}
    by_item = {i.id: i for i in items}
    groups = {"numeric": lambda i: i.question.question_type != "narrative", "narrative": lambda i: i.question.question_type == "narrative",
              "US": lambda i: i.question.country == "US", "LK": lambda i: i.question.country == "LK"}
    def metrics(s: list[Item]) -> dict:
        return policy_metrics([records[idx[i.id]].outcomes[actions[idx[i.id]]] for i in s])

    def risk(s: list[Item]) -> float | None:  # undefined, not 0, when nothing in the sample is sent
        m = metrics(s)
        return m["residual_risk"] if m["emitted"] else None

    out = {}
    for name, keep in groups.items():
        sub = [by_item[k] for k in idx if keep(by_item[k])]
        if sub:
            out[name] = paired(sub, risk, seed) | {"sent": metrics(sub)["emitted"]}
    return out


def policy(items: Sequence[Item], gold: GoldStore, outputs: dict, controlled: list, controlled_v1: list | None = None, seed: int = 0,
           neural_file: str | Path | None = None) -> dict:
    """controlled: the rule repairer's controlled-track replays; controlled_v1: repairer v1's (the transfer_replays run);
    neural_file: the neural outcome model's probabilities for the controlled and the main records (neural_predictions)."""
    from faithguard.policy import study, transfer

    v1 = outputs.get("repair-v1", {}).get("repair_rule_spans", {})
    natural = natural_records(items, gold, v1)
    fit_tune = [r for r in controlled if r.split in ("fit", "tune")]
    kinds = ("lightgbm", "neural") if neural_file else ("lightgbm",)
    result = study.run(fit_tune + natural, seed=seed, kinds=kinds, use_score=True, budget_sizes=(100, 200, None), budget_repeats=50,
                       predictions={"neural": str(neural_file)} if neural_file else None)
    test = [r for r in natural if r.split == "test"]
    by = {f["family"]: f for f in result["families"]}
    ours, theirs = by.get("outcome_aware[lightgbm]", {}), by.get("verified_only", {})
    a, b = ours.get("_test_actions"), theirs.get("_test_actions")
    out: dict = {"study": {k: v for k, v in result.items() if not k.startswith("_models_") and k != "deployable"}}
    out["study"]["families"] = [{k: v for k, v in f.items() if not k.startswith("_")} for f in result["families"]]
    if a and b:
        d = _useful_gap(test, items, a, b, seed)
        out["P-H1"] = d | {"comparator_certified": theirs.get("chosen") is not None,
                           "verdict": decide(d, "above") if ours.get("chosen") else "outcome-aware policy not certified"}
        if theirs.get("chosen") is None and theirs.get("_reference_actions"):
            # D-102 (7): the threshold policy at its most cautious uncertified setting, a secondary analysis
            ref = _useful_gap(test, items, a, theirs["_reference_actions"], seed)
            out["P-H1"]["secondary_vs_uncertified_threshold"] = ref | {"setting": theirs["uncertified_reference"]["setting"],
                                                                       "verdict": decide(ref, "above") if ours.get("chosen") else "-"}
        out["P-H2"] = {"certified": ours.get("chosen") is not None, "useful_coverage_test": (ours.get("test") or {}).get("useful_coverage"),
                       "budget_curve": result.get("budget_curve", {}).get("lightgbm"),
                       "labels_needed": result.get("labels_needed", {}).get("lightgbm"),
                       "verdict": "confirmed" if ours.get("chosen") and decide(out["P-H1"], "above") == "confirmed" else "not confirmed"}
    if a and ours.get("chosen"):
        out["groups"] = _group_risk(test, items, a, seed)
    neural = by.get("outcome_aware[neural]", {})
    if a and neural.get("_test_actions") and ours.get("chosen") and neural.get("chosen"):
        out["neural_vs_lightgbm"] = {"useful_coverage_difference": _useful_gap(test, items, neural["_test_actions"], a, seed)}
    # generator shift (§7): with no natural fit split the outcome models stay the controlled track's (D-102), so the policy is
    # certified on the Qwen calibration answers and reported on the Gemma test answers
    shift = [r for r in natural if (r.split == "calibration" and r.item_id.endswith(":qwen")) or (r.split == "test" and r.item_id.endswith(":gemma"))]
    g = study.run(fit_tune + shift, seed=seed, use_score=False, budget_sizes=())
    out["generator_shift"] = {"counts": g["counts"], "families": [{k: v for k, v in f.items() if not k.startswith("_")} for f in g["families"]
                                                                  if f["family"] in ("outcome_aware[lightgbm]", "verified_only")]}
    # P-H3: the policy fitted with the rule repairer (v0) on its natural records, as-is and recalibrated on v1's
    v0_natural = natural_records(items, gold, {}, rule_repairer=True)
    v0_all = fit_tune + v0_natural
    v1_fit_tune = [r for r in (controlled_v1 or []) if r.split in ("fit", "tune")] or fit_tune
    v1_all = v1_fit_tune + natural
    try:
        out["P-H3"] = transfer.run(v0_all, v1_all, seed=seed)
    except Exception as err:  # noqa: BLE001 - reported, not hidden
        out["P-H3"] = {"error": str(err), "verdict": "untestable (error)"}
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
    if "D-H3" in det and "us_threshold" not in det["D-H3"]:
        lines.append(f"| D-H3 US threshold on Sri Lanka | - | {det['D-H3']['verdict']} |")
    elif "D-H3" in det:
        d = det["D-H3"]
        shown = ci(d["lk_test_risk_as_is"]) if d.get("lk_test_risk_as_is") else "-"
        curve = ", ".join(f"{k}: {f(v)}" for k, v in d.get("label_efficiency_curve", {}).items())
        lines.append(f"| D-H3 US threshold on Sri Lanka (risk as-is; restored with 100 labels {f(d.get('restored_share_with_100_lk_labels'))}"
                     f"{'; curve ' + curve if curve else ''}) | {shown} | {d['verdict']} |")
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
    if "P-H3" in pol:
        t = pol["P-H3"]
        if t.get("as_is_risk_ci"):
            est, lo, hi = t["as_is_risk_ci"]
            first = (t.get("recalibrated") or [{}])[0]
            lines.append(f"| P-H3 v0 policy on v1 (risk as-is; restored with {first.get('labels', 100)} labels in {f(first.get('restored_share'))} of draws) | "
                         f"{f(est)} [{f(lo)}, {f(hi)}] | {t['verdict']} |")
        else:
            lines.append(f"| P-H3 v0 policy on v1 | - | {t.get('verdict', t.get('skipped', t.get('error', '-')))} |")
    sec = pol.get("P-H1", {}).get("secondary_vs_uncertified_threshold")
    if sec:
        lines += ["", f"P-H1 secondary (D-102): against the threshold policy at its most cautious uncertified setting ({sec['setting']}), "
                  f"useful coverage difference {ci(sec)}."]
    if pol.get("P-H2") and not pol["P-H2"]["certified"]:
        n = pol["P-H2"].get("labels_needed")
        lines += ["", "P-H2: not certified with every calibration answer; at the rates seen the first setting of the fixed sequence "
                  + (f"would need about {n:,} calibration answers." if n else "cannot certify at any label count tried.")]
    if det.get("detectors"):
        lines += ["", "## Detectors on the test split", "",
                  "Threshold set to flag 10% of the clean calibration answers (the share it does flag is shown: tied scores can make it less).", "",
                  "| Detector | AUROC | Calibration false alarms | Test false alarms | Recall | Wrong-context recall |", "| --- | --- | --- | --- | --- | --- |"]
        for name, m in det["detectors"].items():
            lines.append(f"| {name} | {ci(m['auroc'], False)} | {f(m['calibration_false_alarms'])} | {ci(m['test_false_alarms'])} | "
                         f"{ci(m['test_recall'])} | {ci(m['test_wrong_context_recall'])} |")
    if det.get("auroc_differences"):
        lines += ["", "| AUROC difference | Estimate [95% interval] |", "| --- | --- |"]
        lines += [f"| {k} | {ci(v, False)} |" for k, v in det["auroc_differences"].items()]
    if det.get("spans"):
        slots = sorted({k for m in det["spans"].values() for k in m["recall_by_slot"]})
        lines += ["", "## Spans on the test split (character overlap; ambiguous answers left out)", "",
                  "| Detector | Span F1 | Slot accuracy | " + " | ".join(f"Recall: {k}" for k in slots) + " |",
                  "| --- | --- | --- |" + " --- |" * len(slots)]
        for name, m in det["spans"].items():
            cells = [ci(m["recall_by_slot"][k]) if k in m["recall_by_slot"] else "-" for k in slots]
            lines.append(f"| {name} | {ci(m['span_f1'], False)} | {ci(m['slot_accuracy']) if 'slot_accuracy' in m else '-'} | " + " | ".join(cells) + " |")
    if det.get("fused_calibration"):
        c = det["fused_calibration"]
        lines += ["", f"Fused probabilities on test: per claim Brier {ci(c['claim']['brier'], False)}, ECE {ci(c['claim']['ece'], False)}; "
                  f"per answer Brier {ci(c['answer']['brier'], False)}, ECE {ci(c['answer']['ece'], False)}."]
    if det.get("selective"):
        sel = det["selective"]
        lines += ["", "Coverage at certified selective risk (fused risk, threshold certified on every calibration answer at alpha = 0.10): "
                  + (f"send below {sel['threshold']}; test coverage {ci(sel['test_coverage'])}, risk among sent {ci(sel['test_risk'])}."
                     if sel["certified"] else "no threshold certified.")]
    if rep.get("summaries"):
        lines += ["", "## Repair on the test split", "", "| Repairer, spans | Wrong originals | Corrected | Withheld when needed | New errors | Damage |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for name, s in rep["summaries"].items():
            lines.append(f"| {name} | {s['needing_repair']} | {f(s['correction_rate'])} | {f(s['abstained_when_needed'])} | {f(s['new_error_rate'])} | {f(s['damage_rate'])} |")
    if rep.get("repair_check"):
        lines += ["", "## Repair check (D-106)", "", "| Group | Checked | Code and label disagree | Every changed repair labelled |", "| --- | --- | --- | --- |"]
        for g, r in rep["repair_check"].items():
            lines.append(f"| {g} | {r['labelled']} of {r['planned']} | {r['disagree']} ({f(r['rate'])}) | {'yes' if r['label_every_changed_repair'] else 'no'} |")
    if rep.get("information_preserved"):
        lines += ["", "## Information preserved (D-109)", "", "| Group | Checked | Preserved |", "| --- | --- | --- |"]
        for g, r in rep["information_preserved"].items():
            lines.append(f"| {g} | {r['checked']} | {ci(r['preserved'])} |")
    def family_rows(families: list[dict]) -> list[str]:
        out = []
        for fam in families:
            t, c = fam.get("test") or {}, fam.get("test_ci") or {}

            def cell(key):
                return f"{f(t.get(key))} [{f(c[key][1])}, {f(c[key][2])}]" if key in c else f(t.get(key))
            out.append(f"| {fam['family']} | {fam['certified']} of {fam['settings']} | {cell('emission_coverage')} | {cell('residual_risk')} | {cell('useful_coverage')} |")
        return out

    if pol.get("study"):
        lines += ["", "## Policies on the test split (certified on calibration, alpha = 0.10)", "",
                  "| Policy | Certified | Sent | Wrong among sent | Useful |", "| --- | --- | --- | --- | --- |"]
        lines += family_rows(pol["study"]["families"])
        models = pol["study"].get("models", {})
        if models:
            lines += ["", "| Outcome model | Target | AUROC | Brier | ECE |", "| --- | --- | --- | --- | --- |"]
            for kind, m in models.items():
                for target in ("unsafe", "fix"):
                    if target in m:
                        lines.append(f"| {kind} | P({target}) | {f(m[target]['auroc'], False)} | {f(m[target]['brier'], False)} | {f(m[target]['ece'], False)} |")
        score = pol["study"].get("score_comparator")
        if score and "skipped" not in score:
            lines += ["", f"SCoRE (send or abstain, expected-risk guarantee): sent {f(score['emission_coverage'])}, wrong among sent "
                      f"{f(score['residual_risk'])}, useful {f(score['useful_coverage'])}."]
        for kind, rows in (pol["study"].get("budget_curve") or {}).items():
            lines += ["", f"Certification budget ({kind}): " + "; ".join(
                f"{r['calibration_items']} answers certify in {f(r['certified_share'])} of {r['draws']} draws" for r in rows) + "."]
    if pol.get("neural_vs_lightgbm"):
        lines += ["", f"Neural outcome model minus LightGBM, useful coverage on test: {ci(pol['neural_vs_lightgbm']['useful_coverage_difference'])}."]
    if pol.get("groups"):
        lines += ["", "Residual risk of the chosen policy on test by group: "
                  + "; ".join(f"{k} {ci(v)} ({v['sent']} of {v['items']} sent)" for k, v in pol["groups"].items()) + "."]
    if pol.get("generator_shift"):
        g = pol["generator_shift"]
        lines += ["", "## Generator shift: certified on Qwen calibration answers, reported on Gemma test answers", "",
                  "| Policy | Certified | Sent | Wrong among sent | Useful |", "| --- | --- | --- | --- | --- |"]
        lines += family_rows(g["families"])
    return "\n".join(lines) + "\n"
