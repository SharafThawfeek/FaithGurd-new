"""Score released detectors on controlled-track items (GPU).

    python -m faithguard.train.baseline_eval --detector lettuce-v2-mmbert --out /kaggle/working/base-lettuce-v2
    python -m faithguard.train.baseline_eval --detector hhem --out ...
    python -m faithguard.train.baseline_eval --detector granite --limit 500 --out ...

Writes results.json (AUROC, false alarms on clean answers, wrong-context recall at
risk >= 0.5) and scores.jsonl (one risk per item, for later fusion or policy features).
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--detector", required=True, help="lettuce-v1-large, lettuce-v2-mmbert, hhem or granite")
    parser.add_argument("--out", required=True)
    parser.add_argument("--sources", default="tatqa,finqa")
    parser.add_argument("--track", default="tune")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args(argv)

    import numpy as np

    from faithguard.controlled import load_or_build
    from faithguard.detect import baselines
    from faithguard.data.channel_a_examples import controlled_spans
    from faithguard.policy.outcome import auroc

    pairs = []
    for source in args.sources.split(","):
        for split in ("train", "dev", "test"):
            items, gold, records = load_or_build(source, split)
            track = {r.item_id: r.split for r in records}
            pairs += [(it, gold) for it in items if track.get(it.id) == args.track]
    random.Random(args.seed).shuffle(pairs)
    pairs = pairs[: args.limit]

    detector = baselines.make(args.detector)
    started = time.time()
    rows = []
    for item, gold in pairs:
        spans = controlled_spans(item, gold) or []
        rows.append({
            "item_id": item.id, "error": gold.injections[item.id].error, "wrong": int(bool(spans)),
            "wrong_context": int(any(s[2] in ("entity_scope", "period", "metric") for s in spans)),
            "risk": detector.risk(item),
        })
    y = np.array([r["wrong"] for r in rows])
    risk = np.array([r["risk"] for r in rows])
    clean = [r for r in rows if not r["wrong"]]
    context = [r for r in rows if r["wrong_context"]]
    result = {
        "detector": args.detector,
        "items": len(rows),
        "auroc": auroc(y, risk),
        "false_alarm_clean": sum(r["risk"] >= 0.5 for r in clean) / len(clean) if clean else None,
        "wrong_context_recall": sum(r["risk"] >= 0.5 for r in context) / len(context) if context else None,
        "seconds_per_item": round((time.time() - started) / max(1, len(rows)), 3),
        "settings": vars(args),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with open(out / "scores.jsonl", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
