"""Run the frozen GPU systems on benchmark items and store every output (phase 6, step 1).

    python -m faithguard.train.systems --items items.jsonl --out OUT [--channel-a MODEL] [--adapter ADAPTER --mode program|rewrite]
                                       [--gold-spans SPANS] [--neural MODEL]

For each item, whatever was asked for:

- with --channel-a: Channel A's spans and the per-claim fusion features (its token probabilities over each
  claim, beside the rule checker's verdict), in detector.jsonl;
- with --adapter: the trained repairer's output (an edit program, or a free rewrite with --mode rewrite)
  editing the claims the rule checker flags (repair-rule-spans.jsonl), the claims Channel A flags
  (repair-channel-a-spans.jsonl) and, with --gold-spans, the claims inside the labelled spans
  (repair-gold-spans.jsonl, R-H1's primary setting);
- with --neural: the neural outcome model's P(unsafe) and P(fix) (neural.jsonl, D-096).

Nothing here reads the gold store: --gold-spans is a file of span offsets cut from the labels, the
pre-registered oracle condition for repair. The outputs are scored afterwards, on a laptop. Runs resume:
items already in every output file are skipped. On test and calibration items this runs only after
the pre-registration is filed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Callable, Iterable, Iterator

from faithguard.records import ClaimCheck, DetectorOutput, Item, RepairOutput


def gold_flags(det: DetectorOutput, spans: list[tuple[int, int]]) -> DetectorOutput:
    """The rule checker's claims, flagged exactly where they (or their direction word) overlap a labelled span."""
    def overlaps(start: int, end: int) -> bool:
        return any(start < b and a < end for a, b in spans)

    checks = []
    for claim, check in zip(det.claims, det.checks):
        flagged = overlaps(claim.start, claim.end) or (claim.direction_span is not None and overlaps(*claim.direction_span))
        verdict = ("unsupported" if check.verdict == "supported" else check.verdict) if flagged else "supported"
        checks.append(ClaimCheck.model_validate(check.model_dump() | {"verdict": verdict}))
    return det.model_copy(update={"checks": checks, "detector": "gold-spans"})


def run_systems(items: Iterable[Item], channel_a=None, repairer: Callable[[Item, DetectorOutput], RepairOutput] | None = None,
                threshold: float = 0.5, gold_spans: dict[str, list[tuple[int, int]]] | None = None, neural=None) -> Iterator[dict]:
    """One row per item: whichever of the detector record, the repairs and the outcome probabilities were asked for."""
    from faithguard.detect import detect
    from faithguard.detect.channel_a import flag_claims
    from faithguard.detect.fusion import claim_features

    for item in items:
        det_b = detect(item)
        row: dict = {}
        det_a = None
        if channel_a is not None:
            tokens = channel_a.token_probs(item, det_b)
            det_a = flag_claims(det_b, tokens, threshold)
            row["detector"] = {"item_id": item.id, "risk_b": det_b.risk, "threshold": threshold,
                               "spans": [s.model_dump(mode="json") for s in channel_a.spans(item, tokens)],
                               "claims": claim_features(det_b, tokens)}
        if repairer is not None:
            row["repair_rule_spans"] = repairer(item, det_b).model_dump(mode="json")
            if det_a is not None:
                row["repair_channel_a_spans"] = repairer(item, det_a).model_dump(mode="json")
            if gold_spans is not None and item.id in gold_spans:
                row["repair_gold_spans"] = repairer(item, gold_flags(det_b, gold_spans[item.id])).model_dump(mode="json")
        if neural is not None:
            p_unsafe, p_fix = neural(item, det_b)
            row["neural"] = {"item_id": item.id, "p_unsafe": p_unsafe, "p_fix": p_fix}
        yield row


class NeuralScorer:
    """The trained neural outcome model (D-096), reading items as faithguard.data.outcome_examples writes them."""

    def __init__(self, model_dir: str, max_len: int = 1024):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        from faithguard.policy.neural import collate

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        self.model = AutoModelForSequenceClassification.from_pretrained(model_dir).eval()
        if torch.cuda.is_available():
            self.model.to("cuda")
        self.collate = collate(self.tokenizer.pad_token_id)
        self.max_len = max_len

    def __call__(self, item: Item, det: DetectorOutput) -> tuple[float, float]:
        from faithguard.focus import focus_rows
        from faithguard.policy.features import features
        from faithguard.policy.neural import encode, inputs

        pair = inputs(item, features(item, det), focus_rows(item.evidence, det, item.question.text))
        batch = self.collate([encode(self.tokenizer, pair, self.max_len)])
        with self.torch.no_grad():
            logits = self.model(**{k: v.to(self.model.device) for k, v in batch.items()}).logits
        p_unsafe, p_fix = self.torch.sigmoid(logits)[0].tolist()
        return p_unsafe, p_fix


FILES = {"detector": "detector", "repair_rule_spans": "repair-rule-spans", "repair_channel_a_spans": "repair-channel-a-spans",
         "repair_gold_spans": "repair-gold-spans", "neural": "neural"}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--items", required=True)
    parser.add_argument("--channel-a", help="Channel A model folder")
    parser.add_argument("--adapter", help="a trained repairer's LoRA adapter")
    parser.add_argument("--mode", choices=["program", "rewrite"], default="program", help="edit programs, or the free-rewrite baseline")
    parser.add_argument("--gold-spans", help="JSON Lines of {item_id, spans: [[start, end], ...]} cut from the labels (R-H1)")
    parser.add_argument("--neural", help="the neural outcome model's folder (D-096)")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--load", choices=["fp16", "qlora"], default="fp16")
    parser.add_argument("--threshold", type=float, default=0.5, help="Channel A probability that flags a claim")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)

    from faithguard.train.common import one_gpu

    one_gpu()
    from faithguard.records import read_jsonl

    items = list(read_jsonl(args.items, Item))[: args.limit]
    channel_a = repairer = neural = gold_spans = None
    if args.channel_a:
        from faithguard.detect.channel_a import ChannelA

        channel_a = ChannelA(args.channel_a, threshold=args.threshold)
    if args.adapter:
        from faithguard.repair.model import ModelRepairer
        from faithguard.repair.rewrite import REWRITE_SYSTEM, RewriteRepairer
        from faithguard.train.generation import Generator

        name = f"{args.model} + {args.adapter}"
        if args.mode == "rewrite":
            repairer = RewriteRepairer(Generator(args.model, args.load, adapter=args.adapter, system=REWRITE_SYSTEM, max_new_tokens=400), name=name)
        else:
            repairer = ModelRepairer(Generator(args.model, args.load, adapter=args.adapter), name=name)
    if args.gold_spans:
        rows = [json.loads(line) for line in open(args.gold_spans, encoding="utf-8") if line.strip()]
        gold_spans = {r["item_id"]: [tuple(s) for s in r["spans"]] for r in rows}
    if args.neural:
        neural = NeuralScorer(args.neural)
    wanted = [k for k, on in (("detector", channel_a), ("repair_rule_spans", repairer),
                              ("repair_channel_a_spans", repairer is not None and channel_a is not None),
                              ("repair_gold_spans", repairer is not None and gold_spans is not None), ("neural", neural)) if on]
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    have = {}
    for key in wanted:  # resume: what each output file already holds
        path = out / f"{FILES[key]}.jsonl"
        have[key] = {json.loads(line)["item_id"] for line in open(path, encoding="utf-8") if line.strip()} if path.exists() else set()

    def missing(item: Item) -> bool:
        return any(item.id not in have[k] for k in wanted if k != "repair_gold_spans" or item.id in gold_spans)

    todo = [item for item in items if missing(item)]
    print(f"{len(items) - len(todo)} items already done; {len(todo)} to run: {', '.join(wanted)}", flush=True)
    files = {key: open(out / f"{FILES[key]}.jsonl", "a", encoding="utf-8") for key in wanted}
    try:
        for n, row in enumerate(run_systems(todo, channel_a, repairer, args.threshold, gold_spans, neural), start=1):
            for key, f in files.items():
                item_id = row[key]["item_id"] if key in row else None
                if item_id is not None and item_id not in have[key]:
                    f.write(json.dumps(row[key]) + "\n")
                    f.flush()
            if n % 20 == 0:
                print(f"{n} of {len(todo)} items", flush=True)
    finally:
        for f in files.values():
            f.close()
    print(f"{len(items)} items -> {out}", flush=True)


if __name__ == "__main__":
    main()
