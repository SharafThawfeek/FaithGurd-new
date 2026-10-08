"""Phase-1 repair pilot: can a free T4 fine-tune the repairer with LoRA?

Runs a short LoRA fine-tune of Qwen3.5-2B on synthetic edit-program examples and
records memory, speed and numeric stability. The verdict decides where the team
starts on the fallback chain (decision D-003):

    fp16 LoRA -> QLoRA (fp32 maths) -> Qwen3 1.7B -> Qwen3 0.6B -> prompt-only repairer

Modes:
    fp16   base weights in fp16; LoRA weights in fp32; fp16 autocast with a GradScaler
    qlora  base weights in 4-bit NF4; LoRA weights and maths in fp32

Qwen3.5 mixes Gated DeltaNet (linear attention) layers with full attention. If the
`flash-linear-attention` package is installed, transformers uses its fast kernels;
otherwise it falls back to a much slower PyTorch version. The result records which
path ran, so the two can be compared.

Examples:
    python repair_lora_pilot.py --mode fp16
    python repair_lora_pilot.py --mode fp16 --seq-len 2048
    python repair_lora_pilot.py --mode qlora
    python repair_lora_pilot.py --tiny        # CPU smoke test with a tiny random model
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import random
import statistics
import time

import torch

from common import Stopwatch, environment, print_gpu_log_row, write_result

ENTITIES = ["Group", "Company", "Bank"]
METRICS = [
    "revenue",
    "profit after tax",
    "net interest income",
    "total assets",
    "operating expenses",
    "finance costs",
]


def fmt_thousands(value: int) -> str:
    return f"{value:,}"


def make_example(rng: random.Random) -> tuple[str, str, str]:
    """Return (prompt, program, target_cell) for one synthetic repair item.

    The answer quotes a figure from the wrong entity, the wrong period or the wrong
    scale, and the correct program copies the right cell. Synthetic data is only
    used here to measure speed and stability, never to report repair quality.
    """
    entities = rng.sample(ENTITIES, 2)
    metrics = rng.sample(METRICS, 3)
    cells = []
    for metric in metrics:
        for entity in entities:
            for period in ("FY2025", "FY2024"):
                cells.append(
                    {
                        "id": f"c{len(cells) + 1}",
                        "entity": entity,
                        "metric": metric,
                        "period": period,
                        "value": rng.randint(1_000_000, 90_000_000),
                    }
                )
    target = rng.choice([c for c in cells if c["period"] == "FY2025"])
    error = rng.choice(["entity", "period", "scale"])
    if error == "entity":
        wrong = next(
            c for c in cells if c["metric"] == target["metric"] and c["period"] == "FY2025" and c["entity"] != target["entity"]
        )
        quoted = f"Rs. {fmt_thousands(round(wrong['value'] / 1000))} million"
    elif error == "period":
        wrong = next(
            c for c in cells if c["metric"] == target["metric"] and c["entity"] == target["entity"] and c["period"] == "FY2024"
        )
        quoted = f"Rs. {fmt_thousands(round(wrong['value'] / 1000))} million"
    else:
        quoted = f"Rs. {fmt_thousands(target['value'])} million"

    rows = "\n".join(
        f"| {c['id']} | {c['entity']} | {c['metric']} | {c['period']} | {fmt_thousands(c['value'])} |" for c in cells
    )
    prompt = (
        "### Table (Rs. '000)\n"
        "| cell | entity | metric | period | value |\n"
        f"{rows}\n"
        "### Question\n"
        f"What was the {target['entity']}'s {target['metric']} in FY2025?\n"
        "### Answer\n"
        f"The {target['entity']}'s {target['metric']} was {quoted} in FY2025.\n"
        "### Flagged spans\n"
        f'[0] "{quoted}"\n'
        "### Program\n"
    )
    program = json.dumps({"edits": [{"op": "COPY", "span": 0, "cell": target["id"]}]})
    return prompt, program, target["id"]


def packed_blocks(tokenizer, rng: random.Random, n_blocks: int, seq_len: int) -> torch.Tensor:
    """Concatenate tokenised examples and cut them into equal blocks, so every step sees seq_len tokens."""
    eos = tokenizer.eos_token_id
    stream: list[int] = []
    while len(stream) < n_blocks * seq_len:
        prompt, program, _ = make_example(rng)
        stream.extend(tokenizer(prompt + program + "\n", add_special_tokens=False)["input_ids"])
        stream.append(eos)
    return torch.tensor(stream[: n_blocks * seq_len], dtype=torch.long).view(n_blocks, seq_len)


def kernel_path() -> dict:
    """Which implementation transformers will use for the linear-attention layers."""
    fla = importlib.util.find_spec("fla") is not None
    conv = importlib.util.find_spec("causal_conv1d") is not None
    return {
        "flash_linear_attention_installed": fla,
        "causal_conv1d_installed": conv,
        "gated_delta_rule": "fla kernels" if fla else "PyTorch fallback (slow)",
    }


def tiny_config(model_id: str):
    """Shrink the real Qwen3.5 config so the same model classes run on a laptop CPU."""
    from transformers import AutoConfig

    config = AutoConfig.from_pretrained(model_id)
    text = getattr(config, "text_config", config)
    text.hidden_size = 64
    text.intermediate_size = 128
    text.num_hidden_layers = 4
    if getattr(text, "layer_types", None):
        text.layer_types = text.layer_types[:4]
    text.num_attention_heads = 2
    text.num_key_value_heads = 1
    text.head_dim = 32
    for name, value in {
        "linear_num_key_heads": 2,
        "linear_num_value_heads": 2,
        "linear_key_head_dim": 16,
        "linear_value_head_dim": 16,
    }.items():
        if hasattr(text, name):
            setattr(text, name, value)
    return config


def load_model(args, device: str):
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    if args.tiny:
        model = AutoModelForCausalLM.from_config(tiny_config(args.model), dtype=torch.float32)
    elif args.mode == "fp16":
        model = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.float16, device_map={"": 0})
    else:
        quant = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float32,
        )
        model = AutoModelForCausalLM.from_pretrained(
            args.model, quantization_config=quant, dtype=torch.float32, device_map={"": 0}
        )
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    if args.tiny:
        model.to(device)
    model.config.use_cache = False
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})

    lora = LoraConfig(
        r=args.lora_r,
        lora_alpha=2 * args.lora_r,
        lora_dropout=0.0,
        target_modules="all-linear",
        task_type="CAUSAL_LM",
    )
    # peft keeps LoRA weights in fp32 even when the base model is fp16 (autocast_adapter_dtype).
    model = get_peft_model(model, lora)
    return tokenizer, model


def generation_check(model, tokenizer, rng: random.Random, device: str, use_amp: bool) -> dict:
    """After training, ask for one program and see whether it parses; shows fp16 inference is not broken."""
    prompt, _, target = make_example(rng)
    ids = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).input_ids.to(device)
    model.eval()
    model.config.use_cache = True
    with torch.no_grad(), torch.autocast(device, dtype=torch.float16, enabled=use_amp):
        out = model.generate(ids, max_new_tokens=48, do_sample=False, pad_token_id=tokenizer.eos_token_id)
    text = tokenizer.decode(out[0, ids.shape[1] :], skip_special_tokens=True)
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    try:
        program = json.loads(first_line)
        valid = True
        cell = program["edits"][0].get("cell")
    except (json.JSONDecodeError, KeyError, IndexError, TypeError, AttributeError):
        valid, cell = False, None
    return {"output": text[:200], "valid_json": valid, "copied_target_cell": cell == target}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", choices=["fp16", "qlora"], default="fp16")
    parser.add_argument("--model", default="Qwen/Qwen3.5-2B")
    parser.add_argument("--seq-len", type=int, default=1024)
    parser.add_argument("--micro-batch", type=int, default=1)
    parser.add_argument("--grad-accum", type=int, default=4)
    parser.add_argument("--steps", type=int, default=30)
    parser.add_argument("--lr", type=float, default=2e-4)
    parser.add_argument("--lora-r", type=int, default=16)
    parser.add_argument("--seed", type=int, default=13)
    parser.add_argument("--tag", default="", help="extra label for the result file, e.g. 'fla'")
    parser.add_argument("--tiny", action="store_true", help="CPU smoke test with a tiny random model")
    args = parser.parse_args()
    if args.tiny:
        args.seq_len, args.steps, args.grad_accum = 128, 6, 2

    torch.manual_seed(args.seed)
    rng = random.Random(args.seed)
    device = "cuda" if torch.cuda.is_available() and not args.tiny else "cpu"
    if device == "cpu" and not args.tiny:
        raise SystemExit("No GPU found. Turn on a GPU accelerator, or use --tiny for a CPU smoke test.")
    use_amp = device == "cuda" and args.mode == "fp16"

    result: dict = {
        "pilot": "repair_lora",
        "settings": vars(args),
        "environment": environment(),
        "kernels": kernel_path(),
    }
    print(json.dumps(result["kernels"]))

    started = time.perf_counter()
    try:
        with Stopwatch() as load_time:
            tokenizer, model = load_model(args, device)
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        result["load_seconds"] = round(load_time.seconds, 1)
        result["trainable_params_m"] = round(trainable / 1e6, 2)
        result["total_params_m"] = round(sum(p.numel() for p in model.parameters()) / 1e6, 1)

        n_blocks = args.steps * args.grad_accum * args.micro_batch
        data = packed_blocks(tokenizer, rng, n_blocks, args.seq_len)
        params = [p for p in model.parameters() if p.requires_grad]
        optimizer = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
        scaler = torch.amp.GradScaler(device, enabled=use_amp)
        if device == "cuda":
            torch.cuda.reset_peak_memory_stats()

        model.train()
        losses, step_seconds, grad_norms, scales = [], [], [], []
        nonfinite_losses, skipped_steps = 0, 0
        block = 0
        for step in range(args.steps):
            start = time.perf_counter()
            optimizer.zero_grad(set_to_none=True)
            step_loss = 0.0
            for _ in range(args.grad_accum):
                batch = data[block : block + args.micro_batch].to(device)
                block += args.micro_batch
                with torch.autocast(device, dtype=torch.float16, enabled=use_amp):
                    loss = model(input_ids=batch, labels=batch).loss / args.grad_accum
                if not torch.isfinite(loss):
                    nonfinite_losses += 1
                scaler.scale(loss).backward()
                step_loss += loss.item()
            scaler.unscale_(optimizer)
            grad_norm = torch.nn.utils.clip_grad_norm_(params, 1.0).item()
            scale_before = scaler.get_scale() if use_amp else 1.0
            scaler.step(optimizer)
            scaler.update()
            if use_amp and scaler.get_scale() < scale_before:
                skipped_steps += 1  # the scaler found inf/nan gradients and skipped this step
            if device == "cuda":
                torch.cuda.synchronize()
            step_seconds.append(time.perf_counter() - start)
            losses.append(step_loss)
            grad_norms.append(grad_norm)
            scales.append(scaler.get_scale() if use_amp else None)
            print(f"step {step + 1:3d}  loss {step_loss:8.4f}  grad-norm {grad_norm:9.3f}  {step_seconds[-1]:6.2f}s")

        warm = step_seconds[3:] if len(step_seconds) > 6 else step_seconds
        seconds_per_step = statistics.mean(warm)
        tokens_per_step = args.micro_batch * args.seq_len * args.grad_accum
        tokens_per_second = tokens_per_step / seconds_per_step
        head, tail = statistics.mean(losses[:5]), statistics.mean(losses[-5:])
        late_bad = sum(1 for x in losses[len(losses) // 2 :] if not math.isfinite(x))

        result["training"] = {
            "losses": [round(x, 4) for x in losses],
            "grad_norms": [round(x, 3) for x in grad_norms],
            "grad_scaler_scale": scales,
            "nonfinite_losses": nonfinite_losses,
            "skipped_steps": skipped_steps,
            "seconds_per_step": round(seconds_per_step, 2),
            "tokens_per_second": round(tokens_per_second, 1),
            "gpu_hours_per_million_tokens": round(1e6 / tokens_per_second / 3600, 2),
            "loss_first5": round(head, 4),
            "loss_last5": round(tail, 4),
        }
        if device == "cuda":
            result["peak_memory_gb"] = round(torch.cuda.max_memory_allocated() / 2**30, 2)
            result["peak_reserved_gb"] = round(torch.cuda.max_memory_reserved() / 2**30, 2)
        result["generation_check"] = generation_check(model, tokenizer, rng, device, use_amp)

        reasons = []
        if late_bad:
            reasons.append(f"{late_bad} non-finite losses in the second half")
        if use_amp and skipped_steps > max(3, args.steps // 5):
            reasons.append(f"GradScaler skipped {skipped_steps} of {args.steps} steps (fp16 overflow)")
        if not tail < head * 0.8:
            reasons.append("loss did not fall by at least 20%")
        result["verdict"] = "PASS" if not reasons else "FAIL"
        result["reasons"] = reasons
        if args.tiny:
            result["verdict"] = "SMOKE-OK"
            result["reasons"] = ["tiny random model: the code ran end to end; pass criteria not applied"]
    except torch.OutOfMemoryError as err:
        result["verdict"] = "FAIL"
        result["reasons"] = [f"out of GPU memory at seq_len {args.seq_len}: {str(err)[:200]}"]
    script_seconds = time.perf_counter() - started
    result["script_seconds"] = round(script_seconds, 1)

    print(f"\nVERDICT: {result['verdict']}  {'; '.join(result.get('reasons', []))}")
    if "training" in result:
        t = result["training"]
        print(
            f"tokens/s {t['tokens_per_second']}  GPU-hours per 1M tokens {t['gpu_hours_per_million_tokens']}"
            f"  peak memory {result.get('peak_memory_gb', 'n/a')} GB"
        )
    name = f"repair-{args.mode}-{args.seq_len}" + (f"-{args.tag}" if args.tag else "") + ("-tiny" if args.tiny else "")
    write_result(name, result)
    print_gpu_log_row(
        f"repair pilot {args.mode} {args.seq_len}{' ' + args.tag if args.tag else ''}",
        script_seconds / 3600,
        result["verdict"],
        f"{result['kernels']['gated_delta_rule']}",
    )


if __name__ == "__main__":
    main()
