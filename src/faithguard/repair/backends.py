"""Text-generation backends for the model repairer.

    openai_chat   any OpenAI-compatible server, e.g. llama.cpp's llama-server (the deployed 4-bit runtime)
    hf_chat       a local transformers model, optionally with a LoRA adapter (Kaggle GPU)
    scripted      fixed replies, for tests

Each returns a function prompt -> reply text.
"""

from __future__ import annotations

import json
import urllib.request
from typing import Callable, Iterable

from faithguard.repair.prompting import SYSTEM, json_schema


def openai_chat(url: str, model: str = "local", temperature: float = 0.0, max_tokens: int = 400,
                constrained: bool = True, seed: int = 0, timeout: int = 300) -> Callable[[str], str]:
    """Chat completions against an OpenAI-compatible server. With `constrained`, ask for the edit-program JSON schema."""

    def generate(prompt: str) -> str:
        body = {
            "model": model,
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "seed": seed,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        if constrained:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "edit_program", "schema": json_schema()}}
        request = urllib.request.Request(
            url.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(request, timeout=timeout) as r:
            reply = json.loads(r.read())
        return reply["choices"][0]["message"].get("content") or ""

    return generate


def hf_chat(model_id: str, adapter: str | None = None, max_new_tokens: int = 400, temperature: float = 0.0,
            load_in_4bit: bool = False, device_map="auto") -> Callable[[str], str]:
    """A local transformers chat model (needs torch and transformers; used on Kaggle)."""
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_id)
    kwargs: dict = {"device_map": device_map}
    if load_in_4bit:
        from transformers import BitsAndBytesConfig

        kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
    else:
        kwargs["dtype"] = torch.float16 if torch.cuda.is_available() else torch.float32
    model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs)
    if adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(model, adapter)
    model.eval()

    def generate(prompt: str) -> str:
        messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
        text = tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        ids = tokenizer(text, return_tensors="pt").to(model.device)
        sampling = {"do_sample": True, "temperature": temperature} if temperature > 0 else {"do_sample": False}
        with torch.no_grad():
            out = model.generate(**ids, max_new_tokens=max_new_tokens, pad_token_id=tokenizer.eos_token_id, **sampling)
        return tokenizer.decode(out[0, ids["input_ids"].shape[1] :], skip_special_tokens=True)

    return generate


def scripted(replies: Iterable[str]) -> Callable[[str], str]:
    """Return the given replies in order (for tests); records the prompts it was sent."""
    queue = list(replies)
    prompts: list[str] = []

    def generate(prompt: str) -> str:
        prompts.append(prompt)
        return queue.pop(0) if queue else ""

    generate.prompts = prompts  # type: ignore[attr-defined]
    return generate
