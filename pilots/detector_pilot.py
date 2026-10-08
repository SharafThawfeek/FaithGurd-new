"""Phase-1 detection pilot: which LettuceDetect encoder should Channel A start from?

Compares the two candidate checkpoints on a free T4:
    v1-large   KRLabsOrg/lettucedect-large-modernbert-en-v1   (ModernBERT-large)
    v2-mmbert  KRLabsOrg/lettucedect-v2-mmbert-base           (mmBERT-base, 0.3B)

For each checkpoint and sequence length (1,024 and 2,048 tokens) it fine-tunes in
fp16 mixed precision with gradient checkpointing, finds the largest batch that
fits, and records memory, speed and numeric stability. It then runs each released
checkpoint through the lettucedetect package on one financial example, to check
that the baseline and detector v0 work with the pinned package version.

Speed is only half of the choice: quality on a small development sample is
compared in phase 4. This pilot answers "does it fit, and how many GPU hours".

Examples:
    python detector_pilot.py
    python detector_pilot.py --models v2-mmbert --seq-lens 2048
    python detector_pilot.py --tiny        # CPU smoke test with tiny random encoders
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import random
import statistics
import time

import torch

from common import Stopwatch, environment, print_gpu_log_row, write_result

MODELS = {
    "v1-large": "KRLabsOrg/lettucedect-large-modernbert-en-v1",
    "v2-mmbert": "KRLabsOrg/lettucedect-v2-mmbert-base",
}

EXAMPLE_CONTEXT = (
    "Income statement extract (Rs. '000). Profit after tax: Group 14,212,560 in 2025 and 13,004,180 in 2024; "
    "Bank 12,450,330 in 2025 and 11,635,900 in 2024."
)
EXAMPLE_QUESTION = "What was the Group's profit after tax in FY2025?"
EXAMPLE_ANSWER = "Group profit after tax rose 7.0% to Rs. 12,450 million."


def synthetic_prompt(rng: random.Random, n_rows: int) -> str:
    rows = []
    for i in range(n_rows):
        metric = rng.choice(["Revenue", "Profit after tax", "Total assets", "Finance costs", "Net interest income"])
        entity = rng.choice(["Group", "Company", "Bank"])
        rows.append(f"{metric} ({entity}) 2025: {rng.randint(10**5, 10**8):,}; 2024: {rng.randint(10**5, 10**8):,}.")
    return "Report extract (Rs. '000). " + " ".join(rows) + "\nQuestion: What was the Group's revenue in FY2025?"


def synthetic_answer(rng: random.Random) -> str:
    return (
        f"Group revenue rose {rng.randint(1, 30)}.{rng.randint(0, 9)}% to Rs. {rng.randint(1000, 90000):,} million "
        "in FY2025, while profit after tax was broadly stable."
    )


def make_batch(tokenizer, rng: random.Random, batch: int, seq_len: int) -> dict:
    """Prompt and answer encoded as a pair, as LettuceDetect does; only answer tokens are labelled.

    The prompt is longer than seq_len and truncated, so every sequence is exactly seq_len
    real tokens (worst case for memory). Answer tokens containing a digit get label 1:
    a trivial task, used only to check that the loss falls and stays finite.
    """
    prompts = [synthetic_prompt(rng, n_rows=seq_len // 8) for _ in range(batch)]
    answers = [synthetic_answer(rng) for _ in range(batch)]
    enc = tokenizer(prompts, answers, truncation="only_first", max_length=seq_len, padding="max_length", return_tensors="pt")
    labels = torch.full_like(enc["input_ids"], -100)
    for row in range(batch):
        seq_ids = enc.sequence_ids(row)
        for pos, seq in enumerate(seq_ids):
            if seq == 1:
                token = tokenizer.convert_ids_to_tokens(int(enc["input_ids"][row, pos]))
                labels[row, pos] = int(any(ch.isdigit() for ch in token))
    return {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"], "labels": labels}


def tiny_model(model_id: str):
    from transformers import AutoConfig, AutoModelForTokenClassification

    config = AutoConfig.from_pretrained(model_id)
    config.hidden_size, config.intermediate_size = 64, 128
    config.num_hidden_layers, config.num_attention_heads = 2, 2
    return AutoModelForTokenClassification.from_config(config)


def train_steps(model, tokenizer, rng, device, batch, seq_len, steps, use_amp) -> dict:
    optimizer = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=2e-5)
    scaler = torch.amp.GradScaler(device, enabled=use_amp)
    if device == "cuda":
        torch.cuda.empty_cache()
        torch.cuda.reset_peak_memory_stats()
    losses, seconds, nonfinite, skipped = [], [], 0, 0
    for _ in range(steps):
        data = {k: v.to(device) for k, v in make_batch(tokenizer, rng, batch, seq_len).items()}
        start = time.perf_counter()
        optimizer.zero_grad(set_to_none=True)
        with torch.autocast(device, dtype=torch.float16, enabled=use_amp):
            loss = model(**data).loss
        if not torch.isfinite(loss):
            nonfinite += 1
        scaler.scale(loss).backward()
        scaler.unscale_(optimizer)
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        scale_before = scaler.get_scale() if use_amp else 1.0
        scaler.step(optimizer)
        scaler.update()
        if use_amp and scaler.get_scale() < scale_before:
            skipped += 1
        if device == "cuda":
            torch.cuda.synchronize()
        seconds.append(time.perf_counter() - start)
        losses.append(loss.item())
    del optimizer
    warm = seconds[2:] if len(seconds) > 4 else seconds
    out = {
        "batch": batch,
        "losses": [round(x, 4) for x in losses],
        "nonfinite_losses": nonfinite,
        "skipped_steps": skipped,
        "seconds_per_step": round(statistics.mean(warm), 3),
        "tokens_per_second": round(batch * seq_len / statistics.mean(warm), 1),
    }
    if device == "cuda":
        out["peak_memory_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
    return out


def free_memory() -> None:
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def run_config(name, model_id, seq_len, args, device, rng) -> dict:
    from transformers import AutoModelForTokenClassification, AutoTokenizer

    use_amp = device == "cuda"
    tokenizer = AutoTokenizer.from_pretrained(model_id)
    model = tiny_model(model_id) if args.tiny else AutoModelForTokenClassification.from_pretrained(model_id)
    model.to(device)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.train()
    record = {"model": name, "model_id": model_id, "seq_len": seq_len, "params_m": round(model.num_parameters() / 1e6, 1)}

    largest = None
    for batch in args.batches:
        try:
            train_steps(model, tokenizer, rng, device, batch, seq_len, steps=2, use_amp=use_amp)
            largest = batch
        except torch.OutOfMemoryError:
            free_memory()
            break
    record["largest_batch"] = largest
    if largest is None:
        record["verdict"] = "FAIL"
        record["reasons"] = ["batch of 1 does not fit"]
    else:
        run = train_steps(model, tokenizer, rng, device, largest, seq_len, steps=args.steps, use_amp=use_amp)
        record.update(run)
        record["gpu_hours_per_million_tokens"] = round(1e6 / run["tokens_per_second"] / 3600, 2)
        head, tail = statistics.mean(run["losses"][:3]), statistics.mean(run["losses"][-3:])
        reasons = []
        if any(not math.isfinite(x) for x in run["losses"][len(run["losses"]) // 2 :]):
            reasons.append("non-finite loss in the second half")
        if run["skipped_steps"] > max(3, args.steps // 5):
            reasons.append(f"GradScaler skipped {run['skipped_steps']} steps (fp16 overflow)")
        if not tail < head:
            reasons.append("loss did not fall")
        record["verdict"] = "PASS" if not reasons else "FAIL"
        record["reasons"] = reasons
        if args.tiny:
            record["verdict"], record["reasons"] = "SMOKE-OK", ["tiny random model; pass criteria not applied"]
    del model
    free_memory()
    print(json.dumps({k: v for k, v in record.items() if k != "losses"}))
    return record


def inference_check(model_id: str) -> dict:
    """Run the released checkpoint through the lettucedetect package on one financial example."""
    from lettucedetect.models.inference import HallucinationDetector

    try:
        with Stopwatch() as load:
            detector = HallucinationDetector(method="transformer", model_path=model_id, max_length=4096)
        with Stopwatch() as pred:
            spans = detector.predict(
                context=[EXAMPLE_CONTEXT], question=EXAMPLE_QUESTION, answer=EXAMPLE_ANSWER, output_format="spans"
            )
        return {"ok": True, "load_seconds": round(load.seconds, 1), "predict_seconds": round(pred.seconds, 2), "spans": spans}
    except Exception as err:  # report, never crash the pilot on the optional check
        return {"ok": False, "error": f"{type(err).__name__}: {str(err)[:300]}"}
    finally:
        free_memory()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default="v1-large,v2-mmbert")
    parser.add_argument("--seq-lens", default="1024,2048")
    parser.add_argument("--batches", default="1,2,4,8,16", help="batch sizes tried in order until one runs out of memory")
    parser.add_argument("--steps", type=int, default=20)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--skip-inference", action="store_true")
    parser.add_argument("--tiny", action="store_true", help="CPU smoke test with tiny random encoders")
    args = parser.parse_args()
    args.batches = [int(b) for b in args.batches.split(",")]
    seq_lens = [int(s) for s in args.seq_lens.split(",")]
    names = args.models.split(",")
    if args.tiny:
        seq_lens, args.batches, args.steps, args.skip_inference = [128], [1, 2], 4, True

    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    device = "cuda" if torch.cuda.is_available() and not args.tiny else "cpu"
    if device == "cpu" and not args.tiny:
        raise SystemExit("No GPU found. Turn on a GPU accelerator, or use --tiny for a CPU smoke test.")

    started = time.perf_counter()
    result: dict = {"pilot": "detector", "settings": vars(args), "environment": environment(), "runs": [], "inference": {}}
    for name in names:
        for seq_len in seq_lens:
            result["runs"].append(run_config(name, MODELS[name], seq_len, args, device, rng))
        if not args.skip_inference:
            result["inference"][name] = inference_check(MODELS[name])
            print(name, json.dumps(result["inference"][name], default=str)[:400])
    script_seconds = time.perf_counter() - started
    result["script_seconds"] = round(script_seconds, 1)

    print("\nSUMMARY")
    for run in result["runs"]:
        print(
            f"{run['model']:10s} seq {run['seq_len']:5d}  {run['verdict']:8s} largest batch {run['largest_batch']}  "
            f"tokens/s {run.get('tokens_per_second', '-')}  GPU-h/1M tokens {run.get('gpu_hours_per_million_tokens', '-')}  "
            f"peak {run.get('peak_memory_gb', '-')} GB"
        )
    outcome = "PASS" if all(r["verdict"] in ("PASS", "SMOKE-OK") for r in result["runs"]) else "PARTIAL"
    write_result("detector" + ("-tiny" if args.tiny else ""), result)
    print_gpu_log_row(
        "detector pilot", script_seconds / 3600, outcome, f"models {' '.join(names)}; seq {' '.join(map(str, seq_lens))}"
    )


if __name__ == "__main__":
    main()
