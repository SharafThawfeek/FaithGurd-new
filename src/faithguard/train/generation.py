"""Generation from a backbone (+ optional LoRA adapter) loaded once, for evaluation and self-training."""

from __future__ import annotations

from faithguard.repair.prompting import SYSTEM


class Generator:
    def __init__(self, model_id: str, mode: str = "fp16", adapter: str | None = None, max_new_tokens: int = 256):
        import torch

        from faithguard.train.common import load_backbone

        self.torch = torch
        self.tokenizer, self.model = load_backbone(model_id, mode, adapter=adapter, trainable=False)
        if mode == "tiny":
            self.model.to("cpu")
        self.model.config.use_cache = True
        self.model.eval()
        self.max_new_tokens = max_new_tokens

    def _ids(self, prompt: str, system: str):
        messages = [{"role": "system", "content": system}, {"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        return self.tokenizer(text, return_tensors="pt", add_special_tokens=False).to(self.model.device)

    def sample(self, prompt: str, n: int = 1, temperature: float = 0.0, system: str = SYSTEM) -> list[str]:
        ids = self._ids(prompt, system)
        kwargs = {"do_sample": True, "temperature": temperature, "top_p": 0.95, "num_return_sequences": n} if temperature > 0 else {"do_sample": False}
        with self.torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=self.max_new_tokens, pad_token_id=self.tokenizer.pad_token_id, **kwargs)
        start = ids["input_ids"].shape[1]
        return [self.tokenizer.decode(seq[start:], skip_special_tokens=True) for seq in out]

    def __call__(self, prompt: str) -> str:
        return self.sample(prompt)[0]

    def close(self) -> None:
        del self.model
        if self.torch.cuda.is_available():
            self.torch.cuda.empty_cache()
