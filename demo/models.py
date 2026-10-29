"""The trained models, live on this laptop when they can be: Channel A and the trained repairer.

Both load in a background thread, so the demo opens at once and works without them: then it shows
the outputs computed earlier (data/demo/cache.json, or the Kaggle pilot run). torch, transformers
and peft come from requirements/demo.txt; nothing here is imported until a model is loaded.

Memory on a 6 GB RTX 4050: the repairer (Qwen3.5-2B fp16 + LoRA) peaks at about 3.8 GB and Channel A
(fp32) takes 1.2 GB, which leaves almost nothing free. So when the repairer loads, Channel A runs on the
CPU (0.4-0.9 s an answer instead of 25 ms on the GPU); with --no-repairer it takes the GPU.
"""

from __future__ import annotations

import threading
import time
import traceback
from pathlib import Path

from faithguard.records import DetectorOutput, Evidence, Item, RepairOutput

BASE_MODEL = "Qwen/Qwen3.5-2B"
MAX_FAILURES = 3  # consecutive inference errors before a model is marked failed and stored outputs take over
ANSWER_TOKENS = 120
# The benchmark generators' prompt asks for up to three sentences; the 2B base model fills them with its working
# ("calculated as (14,212,560 - 13,004,180) / ..."), which the rule checker reads one year per clause. One sentence
# that names each figure's year is what the benchmark's larger AIs mostly wrote.
ANSWER_SYSTEM = (
    "You answer questions about company annual reports. Use only the report extract provided. "
    "Answer in one sentence. State each figure with its currency, unit and year. If a table's title has a units "
    "note, write that unit as a word (thousand, million or billion); if it has none, the figures are in single units. "
    "Do not show your working."
)


class Slot:
    """One model's state: off, loading, ready or failed, with a short detail for the status bar."""

    def __init__(self, name: str):
        self.name, self.state, self.detail, self.model = name, "off", "", None
        self.lock = threading.Lock()  # one inference at a time per model
        self.failures = 0

    def view(self) -> dict:
        return {"state": self.state, "detail": self.detail}

    def run(self, fn):
        with self.lock:
            try:
                out = fn()
            except Exception:
                self.failures += 1
                if self.failures >= MAX_FAILURES:
                    self.state, self.detail = "failed", f"{self.failures} errors in a row; showing stored outputs"
                _free_gpu()
                raise
            self.failures = 0
            return out


def _free_gpu() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    except ImportError:
        pass


class LiveModels:
    def __init__(self, channel_a_dir: Path | None, adapter_dir: Path | None, base_model: str = BASE_MODEL,
                 channel_a_device: str | None = None, warm_up: Item | None = None):
        self.channel_a_dir, self.adapter_dir, self.base_model = channel_a_dir, adapter_dir, base_model
        self.channel_a_device, self.warm_up_item = channel_a_device, warm_up
        self.channel_a, self.repairer = Slot("channel_a"), Slot("repairer")

    def status(self) -> dict:
        return {"channel_a": self.channel_a.view(), "repairer": self.repairer.view()}

    def start(self, channel_a: bool = True, repairer: bool = True) -> threading.Thread:
        if not repairer:
            self.repairer.detail = "not loaded (--no-repairer)"
        thread = threading.Thread(target=self._load, args=(channel_a, repairer), daemon=True)
        thread.start()
        return thread

    def _load(self, channel_a: bool, repairer: bool) -> None:
        if channel_a:
            self._load_one(self.channel_a, self.channel_a_dir, lambda folder: self._make_channel_a(folder, repairer))
        if repairer:
            self._load_one(self.repairer, self.adapter_dir, self._make_repairer)

    def _load_one(self, slot: Slot, folder: Path | None, make) -> None:
        if folder is None or not Path(folder).exists():
            slot.state, slot.detail = "off", f"no model files at {folder}: run demo/fetch_models.py"
            return
        slot.state, slot.detail = "loading", "loading…"
        started = time.perf_counter()
        try:
            slot.model, where = make(Path(folder))
            slot.state, slot.detail = "ready", f"live on the {where} (loaded in {time.perf_counter() - started:.0f} s)"
        except Exception as err:  # a missing package, no GPU, out of memory: fall back to stored outputs
            slot.state, slot.detail = "failed", f"{type(err).__name__}: {err}"[:300]
            traceback.print_exc()
            _free_gpu()

    def _make_channel_a(self, folder: Path, repairer_too: bool):
        import torch

        from faithguard.detect.channel_a import ChannelA

        device = self.channel_a_device or ("cuda" if torch.cuda.is_available() and not repairer_too else "cpu")
        return ChannelA(folder, device=device), ("GPU" if device == "cuda" else "CPU")

    def _make_repairer(self, folder: Path):
        import torch

        from faithguard.detect import detect
        from faithguard.repair.model import ModelRepairer
        from faithguard.train.generation import Generator

        if not torch.cuda.is_available():
            raise RuntimeError("the trained repairer needs a CUDA GPU to answer in a few seconds")
        repairer = ModelRepairer(Generator(self.base_model, "fp16", adapter=str(folder)), name=f"{self.base_model} + repair-v1 adapter (live)")
        if self.warm_up_item is not None:  # the first generation compiles kernels; do it now, not during the talk
            repairer(self.warm_up_item, detect(self.warm_up_item))
        return repairer, "GPU"

    # -- inference ---------------------------------------------------------

    def channel_a_tokens(self, item: Item, det: DetectorOutput) -> tuple[list | None, float]:
        if self.channel_a.state != "ready":
            return None, 0.0
        started = time.perf_counter()
        tokens = self.channel_a.run(lambda: self.channel_a.model.token_probs(item, det))
        return [list(t) for t in tokens], time.perf_counter() - started

    def repair(self, item: Item, det: DetectorOutput) -> tuple[RepairOutput | None, float]:
        if self.repairer.state != "ready":
            return None, 0.0
        started = time.perf_counter()
        out = self.repairer.run(lambda: self.repairer.model(item, det))
        return out, time.perf_counter() - started

    def answer(self, question: str, evidence: Evidence) -> tuple[str | None, float]:
        """The base model's own answer, the repair adapter switched off: the evidence and question rendered as
        for the benchmark's generators (faithguard.generation.answers), with a one-sentence instruction."""
        if self.repairer.state != "ready":
            return None, 0.0
        from faithguard.generation.answers import strip_thinking, user_prompt

        gen = self.repairer.model.generate  # the Generator inside the ModelRepairer

        def go() -> str:
            ids = gen._ids(user_prompt(question, evidence), ANSWER_SYSTEM)
            with gen.torch.no_grad(), gen.model.disable_adapter():
                out = gen.model.generate(**ids, max_new_tokens=ANSWER_TOKENS, do_sample=False, pad_token_id=gen.tokenizer.pad_token_id)
            return gen.tokenizer.decode(out[0][ids["input_ids"].shape[1]:], skip_special_tokens=True)

        started = time.perf_counter()
        with self.repairer.lock:  # the same GPU model, but its failures do not count against the trained repairer
            try:
                raw = go()
            except Exception:
                _free_gpu()
                raise
        text, _ = strip_thinking(raw)
        return " ".join(text.split()), time.perf_counter() - started
