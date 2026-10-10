"""Evaluate a model repairer on controlled-track items (GPU; or --tiny on CPU).

    # trained edit-program model
    python -m faithguard.train.repair_eval --adapter /kaggle/working/repair-sft/adapter --out /kaggle/working/eval-sft
    # zero-shot programs from the untrained backbone
    python -m faithguard.train.repair_eval --out /kaggle/working/eval-zero-shot
    # free-rewrite baseline
    python -m faithguard.train.repair_eval --mode rewrite --adapter /kaggle/working/rewrite-sft/adapter --out ...
    # the deployed 4-bit runtime (llama.cpp server already running)
    python -m faithguard.train.repair_eval --server http://127.0.0.1:8080 --out ...

Items come from the tune track by default (the repair paper's development data); the
calibration and test tracks are kept for the policy study and final runs.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", required=True)
    parser.add_argument("--mode", choices=["program", "rewrite", "rules"], default="program",
                        help="rules: the rule-only COPY and CALCULATE repairer (repairer v0; no model, runs on CPU)")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--adapter")
    parser.add_argument("--load", choices=["fp16", "qlora", "tiny"], default="fp16")
    parser.add_argument("--server", help="OpenAI-compatible URL (llama.cpp) instead of a local model")
    parser.add_argument("--sources", default="tatqa,finqa")
    parser.add_argument("--track", default="tune")
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--spans", default="rules",
                        help="which claims the repairer edits: 'rules' (the rule checker's flags) or a Channel A model folder "
                             "(its predicted spans, for repair RQ3)")
    parser.add_argument("--span-threshold", type=float, default=0.5, help="Channel A probability that flags a claim")
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args(argv)
    if args.tiny:
        args.load, args.limit = "tiny", 3

    from faithguard.controlled import load_or_build
    from faithguard.evaluate.repair import evaluate_repairer, report
    from faithguard.gold import GoldStore
    from faithguard.repair.model import ModelRepairer
    from faithguard.repair.rewrite import RewriteRepairer

    items, gold = [], GoldStore("unused")
    for source in args.sources.split(","):
        for split in ("train", "dev", "test"):
            its, g, records = load_or_build(source, split)
            track = {r.item_id: r.split for r in records}
            for it in its:
                if track.get(it.id) == args.track:
                    items.append(it)
                    gold.add_question(g.questions[it.question.id])
                    gold.add_injection(g.injections[it.id])
    random.Random(args.seed).shuffle(items)
    items = items[: args.limit]

    if args.mode == "rules":
        from faithguard.repair import rules

        repairer, name = rules.repair, "rules only (COPY and CALCULATE)"
    else:
        if args.server:
            from faithguard.repair.backends import openai_chat

            generate, name = openai_chat(args.server), f"server:{args.server}"
        else:
            from faithguard.train.generation import Generator

            generate, name = Generator(args.model, args.load, adapter=args.adapter), f"{args.model}{' + ' + args.adapter if args.adapter else ' (zero-shot)'}"
        repairer = ModelRepairer(generate, name=name) if args.mode == "program" else RewriteRepairer(generate, name=name)
    if args.spans == "rules":
        from faithguard.detect import detect as detector
    else:
        from faithguard.detect.channel_a import ChannelA, span_flags

        detector = span_flags(ChannelA(args.spans), threshold=args.span_threshold)
        name += f", Channel A spans at {args.span_threshold}"
    result = evaluate_repairer(items, gold, repairer, detector=detector)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    title = f"{args.mode} repairer, {name}, {args.track} track"
    (out / "report.md").write_text(report(title, result), encoding="utf-8")
    (out / "results.json").write_text(json.dumps({k: v for k, v in result.items() if k != "rows"} | {"settings": vars(args)}, indent=2), encoding="utf-8")
    with open(out / "rows.jsonl", "w", encoding="utf-8") as f:
        for row in result["rows"]:
            f.write(json.dumps(row) + "\n")
    print(report(title, result))


if __name__ == "__main__":
    main()
