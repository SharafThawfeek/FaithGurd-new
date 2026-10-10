"""Stage B: executor-verified self-training of the repairer (rejection-sampling fine-tuning, not RL).

Each round:
  1. sample k edit programs per training item from the current adapter (temperature > 0);
  2. keep the first program that the executor runs and the hard gate accepts; no gold is used;
  3. fine-tune the adapter further on the kept programs, mixed with a share of the original
     supervised data (which also keeps CANNOT_FIX, since an abstention cannot be verified).

    python -m faithguard.train.repair_self_train --adapter /kaggle/working/repair-sft/adapter \
        --sft runs/sft/repair-program-train.jsonl --out /kaggle/working/self-train --rounds 2

Every round's samples and adapter are saved; finished rounds are skipped on restart.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path


def accepted_program(item, det, replies: list[str]):
    """The first sampled program the executor runs and the gate passes, or None."""
    from faithguard.detect.rules import EvidenceIndex
    from faithguard.executor import ExecError, execute
    from faithguard.records import CannotFix, Keep
    from faithguard.repair.gate import gate
    from faithguard.repair.prompting import editable_claims, parse_program

    editable = set(editable_claims(det))
    index = EvidenceIndex(item)
    for reply in replies:
        program = parse_program(reply)
        if program is None or any(isinstance(e, CannotFix) for e in program.edits):
            continue
        if any(not isinstance(e, Keep) and e.claim not in editable for e in program.edits):
            continue
        try:
            result = execute(item, det.claims, program)
        except ExecError:
            continue
        if gate(item, det, program, result, index).passed:
            return program
    return None


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--adapter", required=True, help="the Stage A adapter to start from")
    parser.add_argument("--sft", required=True, help="the Stage A training data, mixed back in each round")
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--mode", choices=["fp16", "qlora", "tiny"], default="fp16")
    parser.add_argument("--rounds", type=int, default=2)
    parser.add_argument("--items", type=int, default=1000, help="training items sampled per round")
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument("--temperature", type=float, default=0.8)
    parser.add_argument("--replay-share", type=float, default=0.5, help="original examples per kept example")
    parser.add_argument("--sources", default="tatqa,finqa")
    parser.add_argument("--hold-out", default="basis")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args(argv)
    if args.tiny:
        args.mode, args.items, args.samples, args.rounds = "tiny", 3, 2, 1

    from faithguard.train.common import one_gpu

    one_gpu()  # before the Generator starts CUDA, so the training rounds see one GPU too

    from faithguard.controlled import load_or_build
    from faithguard.detect import detect
    from faithguard.repair.prompting import SYSTEM, build_prompt, editable_claims, program_json
    from faithguard.train import repair_sft
    from faithguard.train.generation import Generator

    hold_out = {x for x in args.hold_out.split(",") if x}
    pool = []
    for source in args.sources.split(","):
        for split in ("train", "dev", "test"):
            items, gold, records = load_or_build(source, split)
            track = {r.item_id: r.split for r in records}
            pool += [it for it in items if track.get(it.id) == "fit" and gold.injections[it.id].error not in hold_out]
    sft_rows = [json.loads(line) for line in open(args.sft, encoding="utf-8") if line.strip()]
    rng = random.Random(args.seed)
    out = Path(args.out)
    adapter = args.adapter
    log = []
    for round_no in range(1, args.rounds + 1):
        round_dir = out / f"round-{round_no}"
        if (round_dir / "adapter").exists():
            adapter = str(round_dir / "adapter")
            continue
        round_dir.mkdir(parents=True, exist_ok=True)
        chosen = rng.sample(pool, min(args.items, len(pool)))
        started = time.time()
        gen = Generator(args.model, args.mode, adapter=adapter)
        kept = []
        attempted = 0
        for item in chosen:
            det = detect(item)
            editable = editable_claims(det)
            if not editable:
                continue
            attempted += 1
            prompt = build_prompt(item, det.claims, editable, det)
            program = accepted_program(item, det, gen.sample(prompt, n=args.samples, temperature=args.temperature))
            if program is not None:
                kept.append({"id": item.id, "error": "self-train", "messages": [
                    {"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}, {"role": "assistant", "content": program_json(program)},
                ]})
        gen.close()
        replay = rng.sample(sft_rows, min(len(sft_rows), max(1, int(len(kept) * args.replay_share)) if kept else min(len(sft_rows), 50)))
        data = round_dir / "data.jsonl"
        with open(data, "w", encoding="utf-8") as f:
            for row in kept + replay:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        stats = {"round": round_no, "items": attempted, "kept": len(kept), "acceptance": round(len(kept) / attempted, 4) if attempted else None,
                 "replayed": len(replay), "sampling_seconds": round(time.time() - started, 1)}
        print(json.dumps(stats), flush=True)
        train_args = ["--data", str(data), "--out", str(round_dir), "--model", args.model, "--mode", args.mode, "--adapter", adapter, "--epochs", "1"]
        if args.tiny:
            train_args += ["--tiny"]
        repair_sft.main(train_args)
        adapter = str(round_dir / "adapter")
        log.append(stats)
    (out / "self_train_log.json").write_text(json.dumps(log, indent=2), encoding="utf-8")
    print(f"final adapter: {adapter}")


if __name__ == "__main__":
    main()
