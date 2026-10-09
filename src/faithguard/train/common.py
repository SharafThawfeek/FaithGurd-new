"""Shared pieces for GPU training: loading the backbone with LoRA, and chat tokenisation.

Modes follow decision D-003 and the phase-1 pilot:
    fp16   base weights fp16, LoRA weights fp32, fp16 autocast (fastest on a T4 if stable)
    qlora  base weights 4-bit NF4, LoRA weights and maths fp32 (fallback if fp16 overflows)
    tiny   a shrunken copy of the real architecture on CPU, for smoke tests only
"""

from __future__ import annotations

import glob
import os
from pathlib import Path


def one_gpu() -> None:
    """Train on the first GPU only. Call before torch starts CUDA.

    On Kaggle's T4 x2 the Trainer would otherwise wrap the model in DataParallel across both GPUs,
    and Qwen3.5's fallback linear-attention kernels fail on the second copy ("lazy wrapper should be
    called at most once"). The phase-1 pilot trained on one GPU, so its speeds still apply.
    """
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")


def load_backbone(model_id: str, mode: str, lora_r: int = 16, adapter: str | None = None, trainable: bool = True):
    import torch
    from peft import LoraConfig, PeftModel, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    if mode == "tiny":
        config = AutoConfig.from_pretrained(model_id)
        text = getattr(config, "text_config", config)
        for name, value in dict(hidden_size=64, intermediate_size=128, num_hidden_layers=4, num_attention_heads=2,
                                num_key_value_heads=1, head_dim=32, linear_num_key_heads=2, linear_num_value_heads=2,
                                linear_key_head_dim=16, linear_value_head_dim=16).items():
            if hasattr(text, name):
                setattr(text, name, value)
        if getattr(text, "layer_types", None):
            text.layer_types = text.layer_types[:4]
        model = AutoModelForCausalLM.from_config(config, dtype=torch.float32)
    elif mode == "fp16":
        model = AutoModelForCausalLM.from_pretrained(model_id, dtype=torch.float16, device_map={"": 0})
    elif mode == "qlora":
        quant = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True, bnb_4bit_compute_dtype=torch.float32)
        model = AutoModelForCausalLM.from_pretrained(model_id, quantization_config=quant, dtype=torch.float32, device_map={"": 0})
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    else:
        raise ValueError(mode)
    model.config.use_cache = False
    if trainable:
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    if adapter:
        model = PeftModel.from_pretrained(model, adapter, is_trainable=trainable)
    elif trainable:
        model = get_peft_model(model, LoraConfig(r=lora_r, lora_alpha=2 * lora_r, lora_dropout=0.0, target_modules="all-linear", task_type="CAUSAL_LM"))
    return tokenizer, model


def encode_chat(tokenizer, messages: list[dict], max_len: int) -> dict | None:
    """Token ids for a chat example, with the loss only on the assistant's reply.

    The prompt is rendered exactly as at inference (generation prompt, thinking off),
    and the reply plus end-of-turn is appended, so training and use see the same format.
    """
    prompt = tokenizer.apply_chat_template(messages[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    reply = messages[-1]["content"] + (tokenizer.eos_token or "")
    p_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    r_ids = tokenizer(reply, add_special_tokens=False)["input_ids"]
    if len(p_ids) + len(r_ids) > max_len:
        return None
    return {"input_ids": p_ids + r_ids, "labels": [-100] * len(p_ids) + r_ids}


def collate(pad_id: int):
    import torch

    def fn(batch: list[dict]) -> dict:
        width = max(len(b["input_ids"]) for b in batch)
        ids = torch.full((len(batch), width), pad_id, dtype=torch.long)
        labels = torch.full((len(batch), width), -100, dtype=torch.long)
        mask = torch.zeros((len(batch), width), dtype=torch.long)
        for i, b in enumerate(batch):
            n = len(b["input_ids"])
            ids[i, :n] = torch.tensor(b["input_ids"])
            labels[i, :n] = torch.tensor(b["labels"])
            mask[i, :n] = 1
        return {"input_ids": ids, "labels": labels, "attention_mask": mask}

    return fn


def latest_checkpoint(out: str | Path) -> str | None:
    found = sorted(glob.glob(os.path.join(str(out), "checkpoint-*")), key=lambda p: int(p.rsplit("-", 1)[-1]))
    return found[-1] if found else None
