"""Run the frozen GPU systems on benchmark items and store every output (phase 6, step 1).

    python -m faithguard.train.systems --items items.jsonl --channel-a CHANNEL_A_MODEL --adapter REPAIR_ADAPTER --out OUT

For each item: Channel A's spans and the per-claim fusion features (its token probabilities over each
claim, beside the rule checker's verdict), and the trained repairer's output twice, once editing the
claims the rule checker flags and once the claims Channel A flags. Three files are written:
detector.jsonl, repair-rule-spans.jsonl and repair-channel-a-spans.jsonl. Nothing here reads gold:
the outputs are scored afterwards, on a laptop, against the gold store. Before the pre-registration
is filed this runs only on development items (the pilot answers).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Iterable, Iterator

from faithguard.records import DetectorOutput, Item, RepairOutput


def run_systems(items: Iterable[Item], channel_a, repairer: Callable[[Item, DetectorOutput], RepairOutput],
                threshold: float = 0.5) -> Iterator[dict]:
    """One row per item: the detector record and both repairs (as plain dicts)."""
    from faithguard.detect import detect
    from faithguard.detect.channel_a import flag_claims
    from faithguard.detect.fusion import claim_features

    for item in items:
        det_b = detect(item)
        tokens = channel_a.token_probs(item)
        det_a = flag_claims(det_b, tokens, threshold)
        yield {
            "detector": {"item_id": item.id, "risk_b": det_b.risk, "threshold": threshold,
                         "spans": [s.model_dump(mode="json") for s in channel_a.spans(item, tokens)],
                         "claims": claim_features(det_b, tokens)},
            "repair_rule_spans": repairer(item, det_b).model_dump(mode="json"),
            "repair_channel_a_spans": repairer(item, det_a).model_dump(mode="json"),
        }


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", required=True)
    parser.add_argument("--channel-a", required=True, help="Channel A model folder")
    parser.add_argument("--adapter", required=True, help="the trained repairer's LoRA adapter")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--load", choices=["fp16", "qlora"], default="fp16")
    parser.add_argument("--threshold", type=float, default=0.5, help="Channel A probability that flags a claim")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    from faithguard.train.common import one_gpu

    one_gpu()
    from faithguard.detect.channel_a import ChannelA
    from faithguard.records import read_jsonl
    from faithguard.repair.model import ModelRepairer
    from faithguard.train.generation import Generator

    items = list(read_jsonl(args.items, Item))[: args.limit]
    channel_a = ChannelA(args.channel_a, threshold=args.threshold)
    repairer = ModelRepairer(Generator(args.model, args.load, adapter=args.adapter), name=f"{args.model} + {args.adapter}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    files = {key: open(out / f"{name}.jsonl", "w", encoding="utf-8") for key, name in
             (("detector", "detector"), ("repair_rule_spans", "repair-rule-spans"), ("repair_channel_a_spans", "repair-channel-a-spans"))}
    try:
        for n, row in enumerate(run_systems(items, channel_a, repairer, args.threshold), start=1):
            for key, f in files.items():
                f.write(json.dumps(row[key]) + "\n")
                f.flush()
            if n % 20 == 0:
                print(f"{n} of {len(items)} items", flush=True)
    finally:
        for f in files.values():
            f.close()
    print(f"{len(items)} items -> {out}", flush=True)


if __name__ == "__main__":
    main()
