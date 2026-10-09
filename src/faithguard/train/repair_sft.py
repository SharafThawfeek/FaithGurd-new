"""Supervised fine-tuning of the repairer (Stage A), or of the free-rewrite baseline.

    python -m faithguard.train.repair_sft --data runs/sft/repair-program-train.jsonl --out /kaggle/working/repair-sft
    python -m faithguard.train.repair_sft --data runs/sft/repair-rewrite-train.jsonl --out /kaggle/working/rewrite-sft
    python -m faithguard.train.repair_sft --data ... --tiny     # CPU smoke test with a tiny random model

Runs are resumable: checkpoints are saved every --save-steps and the latest one is
picked up automatically, so a 12-hour Kaggle session limit costs at most one interval.
The final LoRA adapter is written to <out>/adapter.
"""

from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="chat JSONL from faithguard sft")
    parser.add_argument("--out", required=True)
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--mode", choices=["fp16", "qlora", "tiny"], default="fp16")
    parser.add_argument("--adapter", help="continue from an existing LoRA adapter (self-training rounds)")
    parser.add_argument("--max-len", type=int, default=2048)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--batch", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=8)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--save-steps", type=int, default=100)
    parser.add_argument("--limit", type=int, help="use only the first N examples")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args(argv)
    if args.tiny:
        args.mode, args.max_steps, args.save_steps, args.limit, args.grad_accum, args.max_len = "tiny", 4, 2, 8, 1, 4096

    from faithguard.train.common import collate, encode_chat, latest_checkpoint, load_backbone, one_gpu

    one_gpu()

    import torch
    from transformers import Trainer, TrainingArguments

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    rows = [json.loads(line) for line in open(args.data, encoding="utf-8") if line.strip()]
    if args.limit:
        rows = rows[: args.limit]
    tokenizer, model = load_backbone(args.model, args.mode, args.lora_r, adapter=args.adapter, trainable=True)
    encoded = [e for e in (encode_chat(tokenizer, r["messages"], args.max_len) for r in rows) if e is not None]
    print(f"{len(encoded)} of {len(rows)} examples fit in {args.max_len} tokens", flush=True)

    out = Path(args.out)
    steps = args.max_steps if args.max_steps > 0 else int(len(encoded) * args.epochs / (args.batch * args.grad_accum)) + 1
    targs = TrainingArguments(
        output_dir=str(out),
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum,
        learning_rate=args.lr,
        num_train_epochs=args.epochs,
        max_steps=args.max_steps,
        lr_scheduler_type="cosine",
        warmup_steps=max(1, int(0.03 * steps)),  # transformers 5 dropped warmup_ratio
        logging_steps=5,
        save_steps=args.save_steps,
        save_total_limit=2,
        fp16=args.mode == "fp16",
        report_to="none",
        remove_unused_columns=False,
        dataloader_num_workers=0,
        seed=args.seed,
        use_cpu=args.mode == "tiny",
    )
    trainer = Trainer(model=model, args=targs, train_dataset=encoded, data_collator=collate(tokenizer.pad_token_id))
    started = time.time()
    trainer.train(resume_from_checkpoint=latest_checkpoint(out))
    model.save_pretrained(out / "adapter")
    tokenizer.save_pretrained(out / "adapter")
    log = {
        "examples": len(encoded),
        "seconds": round(time.time() - started, 1),
        "settings": vars(args),
        "history": trainer.state.log_history,
    }
    (out / "train_log.json").write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print(f"adapter saved to {out / 'adapter'}", flush=True)


if __name__ == "__main__":
    main()
