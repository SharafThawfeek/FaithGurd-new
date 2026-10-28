"""The neural outcome model, the challenger to LightGBM (D-096): P(unsafe) and P(fix) from text.

An mmBERT encoder from Channel A's family (LettuceDetect v2, as a warm start) is fine-tuned with one
sigmoid per target on its mean-pooled output. It reads what LightGBM's features are computed from as
well as the features: the question and the evidence in Channel A's format (large evidence focused as
for Channel A, faithguard.focus), paired with the answer and the pre-action features written out in
words. Nothing comes from the gold store or from a repair attempt.

Training and scoring run on a GPU (faithguard.train.outcome_model); the policy study reads the
probabilities it wrote (faithguard.policy.outcome, kind "neural").
"""

from __future__ import annotations

from faithguard.detect.channel_a import evidence_passages, lettuce_prompt
from faithguard.policy.features import QUESTION_TYPES
from faithguard.records import SLOTS, Item

TARGETS = ("unsafe", "fix")


def signals_text(f: dict[str, float]) -> str:
    """The pre-action features (policy/features.py) in words."""

    def n(key: str) -> int:
        return int(f.get(key, 0))

    def yes(key: str) -> str:
        return "yes" if f.get(key, 0) > 0 else "no"

    slots = ", ".join(f"{s} {n(f'slot_{s}')}" for s in SLOTS if f.get(f"slot_{s}", 0) > 0) or "none"
    qtype = next((q for q in QUESTION_TYPES if f.get(f"qtype_{q}", 0) > 0), "other")
    return (
        f"Checker: risk {f.get('risk', 0):.2f}. Claims: {n('n_claims')}; supported {n('n_supported')}, "
        f"unsupported {n('n_unsupported')}, unverifiable {n('n_unverifiable')}; evidence links {n('n_links')}. "
        f"Failing slots: {slots}. Missing operands: {n('missing_operands')}. "
        f"Evidence holds a value for every failing claim: {yes('evidence_sufficient')}. "
        f"Answers the question: {yes('answers_question')}. Evidence: {n('n_cells')} cells, {n('n_passages')} passages. "
        f"Percentage claims: {n('n_percent_claims')}; directional claims: {n('n_directional_claims')}. "
        f"Learned span score: {f.get('learned_span_max', 0):.2f}. Question type: {qtype}."
    )


def inputs(item: Item, features: dict[str, float], focus: dict[str, set[int]] | None = None) -> list[str]:
    """[question and evidence, answer and signals]: the text pair the encoder reads (the first is cut first)."""
    prompt = lettuce_prompt(item.question.text, evidence_passages(item.evidence, focus=focus))
    return [prompt, f"{item.answer.text}\n{signals_text(features)}"]


def encode(tokenizer, pair: list[str], max_len: int) -> dict:
    enc = tokenizer(*pair, truncation="only_first", max_length=max_len)
    if len(enc["input_ids"]) > max_len:  # the answer and signals alone are too long: cut both
        enc = tokenizer(*pair, truncation="longest_first", max_length=max_len)
    return {"input_ids": enc["input_ids"], "attention_mask": enc["attention_mask"]}


def build_model(checkpoint: str, tiny: bool = False):
    """The encoder with a two-logit head (BCE loss per target). Imports transformers lazily."""
    from transformers import AutoConfig, AutoModelForSequenceClassification

    labels = {"id2label": dict(enumerate(TARGETS)), "label2id": {t: i for i, t in enumerate(TARGETS)},
              "problem_type": "multi_label_classification"}
    if tiny:
        config = AutoConfig.from_pretrained(checkpoint, **labels)
        config.hidden_size, config.intermediate_size, config.num_hidden_layers, config.num_attention_heads = 64, 128, 2, 2
        if getattr(config, "layer_types", None):
            config.layer_types = config.layer_types[:2]
        return AutoModelForSequenceClassification.from_config(config)
    model = AutoModelForSequenceClassification.from_pretrained(checkpoint, **labels)
    model.classifier.reset_parameters()  # LettuceDetect's token head has the same shape; this head starts fresh
    return model


def collate(pad_id: int):
    import torch

    def fn(batch: list[dict]) -> dict:
        width = max(len(b["input_ids"]) for b in batch)
        out = {
            "input_ids": torch.full((len(batch), width), pad_id, dtype=torch.long),
            "attention_mask": torch.zeros((len(batch), width), dtype=torch.long),
        }
        for i, b in enumerate(batch):
            n = len(b["input_ids"])
            out["input_ids"][i, :n] = torch.tensor(b["input_ids"])
            out["attention_mask"][i, :n] = torch.tensor(b["attention_mask"])
        if all("labels" in b for b in batch):
            out["labels"] = torch.tensor([b["labels"] for b in batch], dtype=torch.float)
        return out

    return fn
