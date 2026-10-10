"""Channel A: the learned detector. A LettuceDetect encoder with two heads:

    span head   per answer token: supported (0) or not (1); warm-started from LettuceDetect
    slot head   per flagged token: which relation is wrong (entity_scope, metric, period, ...)

Inputs follow LettuceDetect's format (MIT licence), so the warm-start checkpoint sees
what it was trained on: a question-and-passages prompt paired with the answer, with
labels on answer tokens only. Evidence tables become one passage each, with a cell id
and column label on every number.
"""

from __future__ import annotations

import json
from pathlib import Path

from faithguard.records import SLOTS, DetectorOutput, Evidence, Item, Span

SLOT_NAMES: tuple[str, ...] = tuple(SLOTS)
SLOT_INDEX = {s: i for i, s in enumerate(SLOT_NAMES)}

# LettuceDetect's QA prompt (lettucedetect/prompts/qa_prompt_en.txt, MIT licence).
QA_TEMPLATE = (
    "Briefly answer the following question:\n{question}\n"
    "Bear in mind that your response should be strictly based on the following {n} passages:\n{context}\n"
    'In case the passages do not contain the necessary information to answer the question, please reply with: '
    '"Unable to answer based on given passages."\noutput:'
)
SCALE_WORDS = {3: "thousands", 6: "millions", 9: "billions"}


def evidence_passages(evidence: Evidence, max_passage_chars: int = 600) -> list[str]:
    out = []
    for t in evidence.tables:
        unit = f" (amounts in {SCALE_WORDS[t.scale]})" if t.scale in SCALE_WORDS else ""
        rows: dict[int, list] = {}
        for c in t.cells:
            rows.setdefault(c.row, []).append(c)
        lines = [f"Table {t.id}{': ' + t.title if t.title else ''}{unit}"]
        for r in sorted(rows):
            cells = rows[r]
            label = cells[0].row_label or cells[0].metric or ""
            lines.append(f"{label} | " + " | ".join(f"{c.column_label}: {c.text}" for c in cells))
        out.append("\n".join(lines))
    out += [p.text[:max_passage_chars] for p in evidence.passages]
    return out


def lettuce_prompt(question: str, passages: list[str]) -> str:
    context = "\n".join(f"passage {i + 1}: {p}" for i, p in enumerate(passages))
    return QA_TEMPLATE.format(question=question, n=len(passages), context=context)


def item_prompt(item: Item) -> str:
    return lettuce_prompt(item.question.text, evidence_passages(item.evidence))


def encode(tokenizer, prompt: str, answer: str, spans: list[tuple[int, int, str | None]], max_len: int = 2048) -> dict:
    """Token ids and labels. Span labels: -100 outside the answer, 1 inside a gold span, else 0.
    Slot labels: the slot index on span tokens whose slot is known, -100 elsewhere."""
    enc = tokenizer(prompt, answer, truncation="only_first", max_length=max_len, return_offsets_mapping=True)
    seq_ids = enc.sequence_ids()
    labels, slot_labels = [], []
    for (start, end), seq in zip(enc["offset_mapping"], seq_ids):
        if seq != 1 or start == end:
            labels.append(-100)
            slot_labels.append(-100)
            continue
        hit = next(((s, e, slot) for s, e, slot in spans if start < e and end > s), None)
        labels.append(1 if hit else 0)
        slot_labels.append(SLOT_INDEX[hit[2]] if hit and hit[2] in SLOT_INDEX else -100)
    return {
        "input_ids": enc["input_ids"],
        "attention_mask": enc["attention_mask"],
        "labels": labels,
        "slot_labels": slot_labels,
        "offsets": [list(o) for o in enc["offset_mapping"]],
        "sequence_ids": [s if s is not None else -1 for s in seq_ids],
    }


def build_model(checkpoint: str, use_slot: bool = True, slot_weight: float = 0.5, tiny: bool = False):
    """The two-headed model. Imports torch lazily so the rest of the package runs without it."""
    import torch
    from torch import nn
    from transformers import AutoConfig, AutoModelForTokenClassification

    class SpanSlotModel(nn.Module):
        def __init__(self):
            super().__init__()
            if tiny:
                config = AutoConfig.from_pretrained(checkpoint)
                config.hidden_size, config.intermediate_size, config.num_hidden_layers, config.num_attention_heads = 64, 128, 2, 2
                if getattr(config, "layer_types", None):
                    config.layer_types = config.layer_types[:2]
                self.encoder = AutoModelForTokenClassification.from_config(config)
            else:
                self.encoder = AutoModelForTokenClassification.from_pretrained(checkpoint)
            hidden = self.encoder.config.hidden_size
            self.use_slot = use_slot
            self.slot_weight = slot_weight
            self.slot_head = nn.Linear(hidden, len(SLOT_NAMES))

        def gradient_checkpointing_enable(self, **kwargs):
            self.encoder.gradient_checkpointing_enable(**kwargs)

        def forward(self, input_ids, attention_mask, labels=None, slot_labels=None, **_):
            out = self.encoder(input_ids=input_ids, attention_mask=attention_mask, output_hidden_states=True)
            span_logits = out.logits
            slot_logits = self.slot_head(out.hidden_states[-1])
            loss = None
            if labels is not None:
                ce = nn.CrossEntropyLoss(ignore_index=-100)
                loss = ce(span_logits.reshape(-1, span_logits.shape[-1]).float(), labels.reshape(-1))
                if self.use_slot and slot_labels is not None and (slot_labels != -100).any():
                    loss = loss + self.slot_weight * ce(slot_logits.reshape(-1, slot_logits.shape[-1]).float(), slot_labels.reshape(-1))
            return {"loss": loss, "span_logits": span_logits, "slot_logits": slot_logits}

        def save(self, path: str | Path) -> None:
            path = Path(path)
            self.encoder.save_pretrained(path / "encoder")
            torch.save(self.slot_head.state_dict(), path / "slot_head.pt")
            (path / "channel_a.json").write_text(json.dumps({"use_slot": self.use_slot, "slots": list(SLOT_NAMES)}), encoding="utf-8")

    return SpanSlotModel()


def collate(pad_id: int):
    import torch

    def fn(batch: list[dict]) -> dict:
        width = max(len(b["input_ids"]) for b in batch)
        out = {
            "input_ids": torch.full((len(batch), width), pad_id, dtype=torch.long),
            "attention_mask": torch.zeros((len(batch), width), dtype=torch.long),
            "labels": torch.full((len(batch), width), -100, dtype=torch.long),
            "slot_labels": torch.full((len(batch), width), -100, dtype=torch.long),
        }
        for i, b in enumerate(batch):
            n = len(b["input_ids"])
            for key in out:
                out[key][i, :n] = torch.tensor(b[key][:n])
        return out

    return fn


class ChannelA:
    """Inference: flagged answer spans with a probability and a slot."""

    def __init__(self, model_dir: str | Path, device: str | None = None, threshold: float = 0.5, max_len: int = 4096):
        import torch
        from transformers import AutoModelForTokenClassification, AutoTokenizer

        model_dir = Path(model_dir)
        self.torch = torch
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_dir / "encoder")
        self.encoder = AutoModelForTokenClassification.from_pretrained(model_dir / "encoder").to(self.device).eval()
        self.slot_head = torch.nn.Linear(self.encoder.config.hidden_size, len(SLOT_NAMES))
        head = model_dir / "slot_head.pt"
        if head.exists():
            self.slot_head.load_state_dict(torch.load(head, map_location="cpu"))
        self.slot_head.to(self.device).eval()
        self.threshold, self.max_len = threshold, max_len

    def token_probs(self, item: Item) -> list[tuple[int, int, float, int]]:
        """(answer char start, end, P(unsupported), slot index) for every answer token."""
        enc = encode(self.tokenizer, item_prompt(item), item.answer.text, [], self.max_len)
        ids = self.torch.tensor([enc["input_ids"]], device=self.device)
        mask = self.torch.tensor([enc["attention_mask"]], device=self.device)
        with self.torch.no_grad():
            out = self.encoder(input_ids=ids, attention_mask=mask, output_hidden_states=True)
            probs = out.logits.softmax(-1)[0, :, 1].tolist()
            slots = self.slot_head(out.hidden_states[-1])[0].argmax(-1).tolist()
        return [(s, e, p, k) for (s, e), seq, p, k in zip(enc["offsets"], enc["sequence_ids"], probs, slots) if seq == 1 and s != e]

    def spans(self, item: Item, tokens: list[tuple[int, int, float, int]] | None = None) -> list[Span]:
        tokens = self.token_probs(item) if tokens is None else tokens
        spans: list[Span] = []
        current: list[tuple[int, int, float, int]] = []
        for tok in tokens + [(10**9, 10**9, 0.0, 0)]:
            if tok[2] >= self.threshold and (not current or tok[0] - current[-1][1] <= 1):
                current.append(tok)
                continue
            if current:
                slot_votes = [k for *_, k in current]
                slot = max(set(slot_votes), key=slot_votes.count)
                spans.append(Span(start=current[0][0], end=current[-1][1], score=max(p for _, _, p, _ in current), slot=SLOT_NAMES[slot]))
            current = [tok] if tok[2] >= self.threshold else []
        return spans


def span_flags(channel_a: ChannelA, threshold: float | None = None):
    """A detector whose flagged claims are the ones Channel A marks: repair with predicted spans (repair RQ3).

    Claims and their checks come from the rule checker. A claim is flagged (verdict "unsupported") when
    Channel A's probability over its characters, or over its direction word, reaches the threshold, and
    passed as supported otherwise. So errors Channel A misses go unrepaired, and correct claims it flags
    reach the repairer as false positives, which KEEP training is meant to leave alone.
    """
    from faithguard.detect import detect

    cut = channel_a.threshold if threshold is None else threshold
    return lambda item: flag_claims(detect(item), channel_a.token_probs(item), cut)


def flag_claims(det: DetectorOutput, tokens: list[tuple[int, int, float, int]], threshold: float) -> DetectorOutput:
    """The rule checker's output, with each claim flagged or passed by Channel A's token probabilities (see span_flags)."""
    checks = []
    for claim in det.claims:
        check = det.check(claim.id)
        ranges = [(claim.start, claim.end)] + ([claim.direction_span] if claim.direction_span else [])
        p = max((prob for s, e, prob, _ in tokens for a, b in ranges if s < b and e > a), default=0.0)
        flagged = p >= threshold
        checks.append(check.model_copy(update={"verdict": "unsupported" if flagged else "supported",
                                               "slots": check.slots if flagged else []}))
    return det.model_copy(update={"checks": checks, "detector": f"channel-a-spans@{threshold}"})
