"""Evaluate Channel A (and Channel B on the same items) on controlled-track items.

    python -m faithguard.train.detector_eval --model-dir /kaggle/working/channel-a/model --out /kaggle/working/eval-a

Measures (detection paper): item-level AUROC, false-alarm rate on clean answers (a
headline metric), recall of wrong-context errors (entity, period, metric), character-level
span F1 overall and by slot, and slot accuracy on correctly found spans. It also writes
per-claim features for training the A + B fusion (fusion.jsonl).
"""

from __future__ import annotations

import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

WRONG_CONTEXT = ("entity_scope", "period", "metric")


def char_set(spans) -> set[int]:
    out = set()
    for s, e, *_ in spans:
        out.update(range(s, e))
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model-dir", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--sources", default="tatqa,finqa")
    parser.add_argument("--track", default="tune")
    parser.add_argument("--limit", type=int, default=2000)
    parser.add_argument("--threshold", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=13)
    args = parser.parse_args(argv)

    from faithguard.controlled import load_or_build
    from faithguard.detect import detect
    from faithguard.detect.channel_a import ChannelA
    from faithguard.detect.fusion import claim_features
    from faithguard.data.channel_a_examples import controlled_spans
    from faithguard.policy.outcome import auroc

    import numpy as np

    pairs = []
    for source in args.sources.split(","):
        for split in ("train", "dev", "test"):
            items, gold, records = load_or_build(source, split)
            track = {r.item_id: r.split for r in records}
            pairs += [(it, gold) for it in items if track.get(it.id) == args.track]
    random.Random(args.seed).shuffle(pairs)
    pairs = pairs[: args.limit]

    channel_a = ChannelA(args.model_dir, threshold=args.threshold)
    y_item, a_score, b_score = [], [], []
    clean_alarm_a = clean_alarm_b = clean_n = 0
    ctx_found_a = ctx_found_b = ctx_n = 0
    tp = fp = fn = 0
    slot_stats: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0])  # tp, fp, fn per gold slot
    slot_hit = slot_total = 0
    fusion_rows = []
    for item, gold in pairs:
        gold_spans = controlled_spans(item, gold) or []
        tokens = channel_a.token_probs(item)
        det = detect(item)
        predicted = channel_a.spans(item)
        item_a = max((p for _, _, p, _ in tokens), default=0.0)
        error = gold.injections[item.id].error
        wrong = bool(gold_spans)
        y_item.append(int(wrong))
        a_score.append(item_a)
        b_score.append(det.risk)
        if not wrong:
            clean_n += 1
            clean_alarm_a += item_a >= args.threshold
            clean_alarm_b += det.risk >= 0.5
        if any(slot in WRONG_CONTEXT for *_, slot in gold_spans):
            ctx_n += 1
            ctx_found_a += item_a >= args.threshold
            ctx_found_b += det.risk >= 0.5
        g_chars, p_chars = char_set(gold_spans), char_set((s.start, s.end) for s in predicted)
        tp += len(g_chars & p_chars)
        fp += len(p_chars - g_chars)
        fn += len(g_chars - p_chars)
        for s, e, slot in gold_spans:
            chars = set(range(s, e))
            stats = slot_stats[slot or "none"]
            stats[0] += len(chars & p_chars)
            stats[2] += len(chars - p_chars)
            match = next((p for p in predicted if p.start < e and p.end > s), None)
            if match is not None and slot:
                slot_total += 1
                slot_hit += match.slot == slot
        for row in claim_features(det, tokens):
            claim = det.claim(row["claim_id"])
            row["label"] = int(any(claim.start < e and claim.end > s for s, e, _ in gold_spans))
            row["item_id"], row["error"] = item.id, error
            fusion_rows.append(row)

    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    y = np.array(y_item)
    result = {
        "items": len(pairs),
        "threshold": args.threshold,
        "channel_a": {
            "auroc": auroc(y, np.array(a_score)),
            "false_alarm_clean": clean_alarm_a / clean_n if clean_n else None,
            "wrong_context_recall": ctx_found_a / ctx_n if ctx_n else None,
            "span_precision": precision, "span_recall": recall,
            "span_f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "span_recall_by_slot": {k: v[0] / (v[0] + v[2]) if v[0] + v[2] else None for k, v in sorted(slot_stats.items())},
            "slot_accuracy": slot_hit / slot_total if slot_total else None,
        },
        "channel_b": {
            "auroc": auroc(y, np.array(b_score)),
            "false_alarm_clean": clean_alarm_b / clean_n if clean_n else None,
            "wrong_context_recall": ctx_found_b / ctx_n if ctx_n else None,
        },
        "settings": vars(args),
    }
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    with open(out / "fusion.jsonl", "w", encoding="utf-8") as f:
        for row in fusion_rows:
            f.write(json.dumps(row) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
