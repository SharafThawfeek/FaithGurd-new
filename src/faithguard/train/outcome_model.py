"""Train the neural outcome model, the policy's challenger to LightGBM (D-096); GPU, --tiny on CPU.

    faithguard outcome-data      # laptop: runs/policy/neural/outcome-data.jsonl from the controlled-track cache
    python -m faithguard.train.outcome_model --data outcome-data.jsonl --out /kaggle/working/outputs/outcome-model

Fine-tunes an mmBERT encoder (Channel A's warm start) with two sigmoid heads, P(unsafe) and P(fix),
on the fit rows; the tune rows are evaluated twice an epoch, the checkpoint with the lowest tune loss is
kept, and training stops after --patience evaluations without improvement. Then P(unsafe) and P(fix)
are written for every tune, calibration and test row (the last two carry no labels) to
<out>/predictions.jsonl, which `faithguard policy --models lightgbm,neural` certifies on the same grid.

Resumable: a checkpoint at every evaluation, the latest picked up on restart; a saved model is not
trained again. The model goes to <out>/model, and the checkpoints are deleted once it is saved (D-075).
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import time
from pathlib import Path

DEFAULT_CHECKPOINT = "KRLabsOrg/lettucedect-v2-mmbert-base"


def predict(model, encoded: list[dict], batch: int, collate_fn) -> list[list[float]]:
    """Sigmoid outputs for each row, batched by length on one device."""
    import torch

    device = "cuda" if torch.cuda.is_available() and next(model.parameters()).is_cuda else "cpu"
    model.eval()
    order = sorted(range(len(encoded)), key=lambda i: len(encoded[i]["input_ids"]))
    out: list[list[float]] = [[]] * len(encoded)
    with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.float16, enabled=device == "cuda"):
        for k in range(0, len(order), batch):
            idx = order[k : k + batch]
            b = collate_fn([{key: encoded[i][key] for key in ("input_ids", "attention_mask")} for i in idx])
            logits = model(input_ids=b["input_ids"].to(device), attention_mask=b["attention_mask"].to(device)).logits
            for i, p in zip(idx, torch.sigmoid(logits.float()).tolist()):
                out[i] = p
    return out


def quality(rows: list[dict], probs: list[list[float]]) -> dict:
    """AUROC, Brier and ECE per target on the labelled rows (tune)."""
    import numpy as np

    from faithguard.policy import outcome
    from faithguard.policy.neural import TARGETS

    idx = [i for i, r in enumerate(rows) if "labels" in r]
    y = np.array([rows[i]["labels"] for i in idx], dtype=float).reshape(-1, len(TARGETS))
    p = np.array([probs[i] for i in idx], dtype=float).reshape(-1, len(TARGETS))
    out: dict = {"rows": len(idx)}
    for j, t in enumerate(TARGETS):
        out[t] = {"auroc": outcome.auroc(y[:, j], p[:, j]), "brier": outcome.brier(y[:, j], p[:, j]), "ece": outcome.ece(y[:, j], p[:, j])}
    return out


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--data", required=True, help="rows from `faithguard outcome-data`")
    parser.add_argument("--out", required=True)
    parser.add_argument("--checkpoint", default=DEFAULT_CHECKPOINT, help="Channel A's warm-start encoder (D-075)")
    parser.add_argument("--max-len", type=int, default=1024)
    parser.add_argument("--epochs", type=float, default=2.0)
    parser.add_argument("--max-steps", type=int, default=-1)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--grad-accum", type=int, default=2)
    parser.add_argument("--lr", type=float, default=3e-5)
    parser.add_argument("--evals-per-epoch", type=int, default=2)
    parser.add_argument("--patience", type=int, default=2, help="evaluations on tune without a lower loss before stopping")
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--tiny", action="store_true")
    args = parser.parse_args(argv)
    if args.tiny:
        args.max_steps, args.batch, args.grad_accum, args.max_len = 4, 2, 1, 256

    import torch
    from transformers import AutoModelForSequenceClassification, AutoTokenizer, EarlyStoppingCallback, Trainer, TrainingArguments

    from faithguard.policy.neural import build_model, collate, encode
    from faithguard.train.common import latest_checkpoint

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    rows = [json.loads(line) for line in open(args.data, encoding="utf-8") if line.strip()]
    if args.tiny:  # a few rows of each split
        rows = [r for s in ("fit", "tune", "calibration", "test") for r in [r for r in rows if r["split"] == s][: 16 if s == "fit" else 4]]
    counts = {s: sum(r["split"] == s for r in rows) for s in sorted({r["split"] for r in rows})}
    print(f"{len(rows)} rows {counts}", flush=True)
    out = Path(args.out)
    model_dir = out / "model"
    tokenizer = AutoTokenizer.from_pretrained(model_dir if (model_dir / "config.json").exists() else args.checkpoint)
    encoded = [encode(tokenizer, r["text"], args.max_len) | ({"labels": [float(y) for y in r["labels"]]} if "labels" in r else {}) for r in rows]
    lengths = sorted(len(e["input_ids"]) for e in encoded)
    print(f"tokens per row: median {lengths[len(lengths) // 2]}, max {lengths[-1]}; cut to {args.max_len}: "
          f"{sum(n >= args.max_len for n in lengths)}", flush=True)
    collate_fn = collate(tokenizer.pad_token_id)

    if (model_dir / "config.json").exists():
        print(f"model already trained: {model_dir}", flush=True)
        model = AutoModelForSequenceClassification.from_pretrained(model_dir)
        log = json.loads((out / "train_log.json").read_text(encoding="utf-8"))
    else:
        train = [e for e, r in zip(encoded, rows) if r["split"] == "fit"]
        tune = [e for e, r in zip(encoded, rows) if r["split"] == "tune"]
        model = build_model(args.checkpoint, tiny=args.tiny)
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
        every = max(1, args.max_steps // 2) if args.max_steps > 0 else 1 / (args.epochs * args.evals_per_epoch)  # a ratio of all steps
        targs = TrainingArguments(
            output_dir=str(out), per_device_train_batch_size=args.batch, per_device_eval_batch_size=4 * args.batch,
            gradient_accumulation_steps=args.grad_accum, learning_rate=args.lr, weight_decay=0.01,
            num_train_epochs=args.epochs, max_steps=args.max_steps, lr_scheduler_type="linear", warmup_steps=0.05,
            eval_strategy="steps", eval_steps=every, save_strategy="steps", save_steps=every, save_total_limit=1,
            load_best_model_at_end=True, metric_for_best_model="eval_loss", greater_is_better=False,
            train_sampling_strategy="group_by_length", logging_steps=25, fp16=torch.cuda.is_available() and not args.tiny,
            report_to="none", remove_unused_columns=False, dataloader_num_workers=0, seed=args.seed, use_cpu=args.tiny,
        )
        trainer = Trainer(model=model, args=targs, train_dataset=train, eval_dataset=tune, data_collator=collate_fn,
                          callbacks=[EarlyStoppingCallback(early_stopping_patience=args.patience)])
        started = time.time()
        trainer.train(resume_from_checkpoint=latest_checkpoint(out))
        trainer.save_model(str(model_dir))  # the best checkpoint's weights (load_best_model_at_end)
        tokenizer.save_pretrained(model_dir)
        log = {"examples": {"fit": len(train), "tune": len(tune)}, "seconds": round(time.time() - started, 1),
               "best_checkpoint": trainer.state.best_model_checkpoint, "best_tune_loss": trainer.state.best_metric,
               "settings": vars(args), "history": trainer.state.log_history}
        (out / "train_log.json").write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
        for checkpoint in out.glob("checkpoint-*"):  # only for resuming; each holds the optimizer too (D-075)
            shutil.rmtree(checkpoint)
        print(f"model saved to {model_dir}", flush=True)

    if torch.cuda.is_available() and not args.tiny:
        model.to("cuda")
    started = time.time()
    scored = [i for i, r in enumerate(rows) if r["split"] != "fit"]  # the policy study orders, certifies and reports on these
    probs = predict(model, [encoded[i] for i in scored], 4 * args.batch, collate_fn)
    with open(out / "predictions.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for i, (p_unsafe, p_fix) in zip(scored, probs):
            f.write(json.dumps({"item_id": rows[i]["item_id"], "split": rows[i]["split"], "p_unsafe": p_unsafe, "p_fix": p_fix}) + "\n")
    summary = {"rows": counts, "tune": quality([rows[i] for i in scored], probs), "best_tune_loss": log.get("best_tune_loss"),
               "train_seconds": log.get("seconds"), "predict_seconds": round(time.time() - started, 1)}
    (out / "results.json").write_text(json.dumps({"summary": summary, "settings": vars(args)}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=1), flush=True)
    print(f"{len(scored)} predictions -> {out / 'predictions.jsonl'}", flush=True)


if __name__ == "__main__":
    main()
