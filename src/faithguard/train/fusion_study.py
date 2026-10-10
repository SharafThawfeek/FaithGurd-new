"""The A + B fusion on the controlled track: does Channel A add to Channel B, and how well calibrated is the result?

    python -m faithguard.train.fusion_study --rows full=runs/detector/kaggle/eval-channel-a/fusion.jsonl --out runs/detector/fusion

The detector evaluation writes one row per numeric claim (fusion.jsonl). Items are split by a
stable hash of their id: half fit the logistic regression, a quarter calibrate it (isotonic), and a
quarter evaluate it. Three feature sets are compared: Channel B only, Channel A only, and both.
An answer is wrong if any of its claims is. Template answers favour Channel B (risk R-20), so this
checks the fusion pipeline end to end; it is not a test of H2, which needs natural answers.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from faithguard.detect.fusion import FEATURES, Fusion

FEATURE_SETS = {
    "B only": ("b_supported", "b_unsupported", "b_unverifiable", "b_slots", "b_has_expected", "kind_percent", "has_direction"),
    "A only": ("a_max", "a_mean", "a_any", "kind_percent", "has_direction"),
    "A + B": FEATURES,
}


def part(item_id: str) -> str:
    """fit (half), calibrate (a quarter) or evaluate (a quarter), by a stable hash of the item."""
    h = int(hashlib.sha256(item_id.encode("utf-8")).hexdigest(), 16) % 4
    return "fit" if h < 2 else "calibrate" if h == 2 else "evaluate"


def evaluate(rows: list[dict], features: tuple[str, ...]) -> dict:
    from faithguard.policy.outcome import auroc, brier, ece

    parts: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        parts[part(r["item_id"])].append(r)
    fusion = Fusion.fit(parts["fit"], features)
    fusion.calibrate(parts["calibrate"])
    test = parts["evaluate"]
    claim_p, claim_y = fusion.claim_probs(test), np.array([r["label"] for r in test])
    items: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(test):
        items[r["item_id"]].append(i)
    risk = np.array([1 - np.prod(1 - claim_p[idx]) for idx in items.values()])
    wrong = np.array([int(claim_y[idx].max()) for idx in items.values()])
    flagged = risk >= 0.5
    return {
        "claims": {"fit": len(parts["fit"]), "calibrate": len(parts["calibrate"]), "evaluate": len(test)},
        "items_evaluated": len(items),
        "claim_auroc": auroc(claim_y, claim_p),
        "item_auroc": auroc(wrong, risk),
        "item_brier": brier(wrong, risk),
        "item_ece": ece(wrong, risk),
        "false_alarm_clean": float(flagged[wrong == 0].mean()) if (wrong == 0).any() else None,
        "recall_wrong": float(flagged[wrong == 1].mean()) if (wrong == 1).any() else None,
    }


def report(results: dict[str, dict[str, dict]]) -> str:
    lines = ["# A + B fusion on the controlled track", "",
             "Per-claim logistic regression, isotonic calibration, item risk = P(any claim wrong); items split by hash: "
             "half fit, a quarter calibrate, a quarter evaluate. Template answers favour Channel B (risk R-20): a pipeline "
             "check, not a test of H2. See `faithguard.train.fusion_study`.", "",
             "| Channel A variant | Features | Claim AUROC | Item AUROC | Brier | ECE | False alarms (clean, risk >= 0.5) | Recall (wrong) |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]

    def f(x: float | None, pct: bool = False) -> str:
        return "-" if x is None else f"{100 * x:.1f}%" if pct else f"{x:.3f}"

    for variant, by_set in results.items():
        for name, r in by_set.items():
            lines.append(f"| {variant} | {name} | {f(r['claim_auroc'])} | {f(r['item_auroc'])} | {f(r['item_brier'])} | "
                         f"{f(r['item_ece'])} | {f(r['false_alarm_clean'], True)} | {f(r['recall_wrong'], True)} |")
    any_set = next(iter(next(iter(results.values())).values()))
    lines += ["", f"Evaluated on {any_set['items_evaluated']} items ({any_set['claims']['evaluate']} claims); "
              f"fitted on {any_set['claims']['fit']} claims and calibrated on {any_set['claims']['calibrate']}."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--rows", action="append", required=True, help="NAME=fusion.jsonl, one per Channel A variant")
    parser.add_argument("--out", default="runs/detector/fusion")
    args = parser.parse_args(argv)
    results = {}
    for spec in args.rows:
        name, path = spec.split("=", 1)
        rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines() if line.strip()]
        results[name] = {fs: evaluate(rows, features) for fs, features in FEATURE_SETS.items()}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (out / "report.md").write_text(report(results), encoding="utf-8")
    print(report(results))


if __name__ == "__main__":
    main()
