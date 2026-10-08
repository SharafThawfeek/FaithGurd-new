"""Train Channel A: span head plus relation-slot head on a LettuceDetect encoder (GPU; --tiny on CPU).

    python -m faithguard.train.detector --data runs/detector/train.jsonl --out /kaggle/working/channel-a
    python -m faithguard.train.detector ... --exclude xbrl      # ablation: without XBRL negatives (RQ1)
    python -m faithguard.train.detector ... --no-slot           # ablation: without the slot head

Resumable like the repair script: checkpoints every --save-steps, latest picked up on restart.
The trained model goes to <out>/model (encoder/, slot_head.pt, channel_a.json).
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

DEFAULT_CHECKPOINT = "KRLabsOrg/lettucedect-v2-mmbert-base"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT, help="the warm-start encoder chosen in the phase-1 pilot")
    parser.add_argument("--exclude", default="", help="comma-separated sources to leave out, e.g. xbrl")
    parser.add_argument("--no-slot", action="store_true")
    parser.add_argument("--slot-weight", type=float, default=0.5)
    parser.add_argument("--max-len", type=int, default=2048)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--batch", type=int, default=4)
    parser.add_argument("--grad-accum", type=int, default=2)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--save-steps", type=int, default=200)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args(argv)
    if args.tiny:
        args.max_steps, args.save_steps, args.limit, args.batch, args.grad_accum = 4, 2, 16, 2, 1

    import torch
    from transformers import AutoTokenizer, Trainer, TrainingArguments

    from faithguard.detect.channel_a import build_model, collate, encode
    from faithguard.train.common import latest_checkpoint

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    exclude = {x for x in args.exclude.split(",") if x}
    rows = [json.loads(line) for line in open(args.data, encoding="utf-8") if line.strip()]
    rows = [r for r in rows if r["source"] not in exclude]
    random.shuffle(rows)
    if args.limit:
        rows = rows[: args.limit]
    tokenizer = AutoTokenizer.from_pretrained(args.checkpoint)
    encoded = []
    for r in rows:
        e = encode(tokenizer, r["prompt"], r["answer"], [tuple(s) for s in r["spans"]], args.max_len)
        if any(label != -100 for label in e["labels"]):  # the answer survived truncation
            encoded.append({k: e[k] for k in ("input_ids", "attention_mask", "labels", "slot_labels")})
    sources: dict[str, int] = {}
    for r in rows:
        sources[r["source"]] = sources.get(r["source"], 0) + 1
    print(f"{len(encoded)} examples {sources}", flush=True)

    model = build_model(args.checkpoint, use_slot=not args.no_slot, slot_weight=args.slot_weight, tiny=args.tiny)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    out = Path(args.out)
    steps = args.max_steps if args.max_steps > 0 else int(len(encoded) * args.epochs / (args.batch * args.grad_accum)) + 1
    targs = TrainingArguments(
        output_dir=str(out), per_device_train_batch_size=args.batch, gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr, num_train_epochs=args.epochs, max_steps=args.max_steps, lr_scheduler_type="linear",
        warmup_steps=max(1, int(0.05 * steps)), logging_steps=10, save_steps=args.save_steps, save_total_limit=2,
        fp16=torch.cuda.is_available() and not args.tiny, report_to="none", remove_unused_columns=False,
        dataloader_num_workers=0, seed=args.seed, use_cpu=args.tiny,
    )
    trainer = Trainer(model=model, args=targs, train_dataset=encoded, data_collator=collate(tokenizer.pad_token_id))
    started = time.time()
    trainer.train(resume_from_checkpoint=latest_checkpoint(out))
    model.save(out / "model")
    tokenizer.save_pretrained(out / "model" / "encoder")
    log = {"examples": len(encoded), "sources": sources, "seconds": round(time.time() - started, 1), "settings": vars(args), "history": trainer.state.log_history}
    (out / "train_log.json").write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print(f"model saved to {out / 'model'}", flush=True)


if __name__ == "__main__":
    main()
