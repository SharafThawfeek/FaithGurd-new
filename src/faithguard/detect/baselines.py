"""Released detectors the detection paper compares against (GPU; inference only).

Each scores an item with a risk in [0, 1] (higher = more likely unsupported), on the
same evidence text Channel A sees:

    lettuce   LettuceDetect v1-large or v2 mmBERT (span detector): risk = highest span confidence
    hhem      Vectara HHEM-2.1-Open (premise/hypothesis consistency): risk = 1 - consistency
    granite   IBM Granite Guardian 4.1-8B, groundedness criterion, no-think mode: risk = 1 if it says "yes"
"""

from __future__ import annotations

import re

from faithguard.detect.channel_a import evidence_passages
from faithguard.records import Item

LETTUCE = {
    "lettuce-v1-large": "KRLabsOrg/lettucedect-large-modernbert-en-v1",
    "lettuce-v2-mmbert": "KRLabsOrg/lettucedect-v2-mmbert-base",
}

# From the Granite Guardian 4.1 8B model card (IBM Research, Apache-2.0), reproduced exactly.
GUARDIAN_JUDGE_NOTHINK = (
    "<no-think>As a judge agent, assess whether the provided text meets the given "
    "judging criteria using all available information, including conversations, "
    "documents, and tools. Provide your score immediately without explanation. "
    "Output empty <think>\\n</think> tags followed by your score in <score></score> tags."
)
PROMPT_RESPONSE_SCHEMA = "If the last assistant's text meets the criteria, return 'yes'; otherwise, return 'no'."
GROUNDEDNESS_CRITERIA = (
    "A text is considered ungrounded or unfaithful if it includes information "
    "lacking support from, or directly contradicting, the provided document(s). "
    "This risk arises when the text fabricates details, misinterprets the content, "
    "or makes unsupported extrapolations beyond what is explicitly stated in the "
    "document(s)."
)


def guardian_block(criteria: str = GROUNDEDNESS_CRITERIA) -> str:
    return f"{GUARDIAN_JUDGE_NOTHINK}\n\n### Criteria: {criteria}\n\n### Scoring Schema: {PROMPT_RESPONSE_SCHEMA}"


class LettuceBaseline:
    def __init__(self, name: str = "lettuce-v2-mmbert", max_length: int = 4096):
        from lettucedetect.models.inference import HallucinationDetector

        self.name = name
        self.detector = HallucinationDetector(method="transformer", model_path=LETTUCE[name], max_length=max_length)

    def risk(self, item: Item) -> float:
        spans = self.detector.predict(
            context=evidence_passages(item.evidence), question=item.question.text, answer=item.answer.text, output_format="spans"
        )
        return max((float(s.get("confidence", 0.0)) for s in spans), default=0.0)


class HHEMBaseline:
    name = "hhem-2.1-open"

    def __init__(self):
        from transformers import AutoModelForSequenceClassification

        self.model = AutoModelForSequenceClassification.from_pretrained("vectara/hallucination_evaluation_model", trust_remote_code=True)
        try:
            import torch

            if torch.cuda.is_available():
                self.model = self.model.to("cuda")
        except ImportError:
            pass
        self.model.eval()

    def risk(self, item: Item) -> float:
        premise = "\n".join(evidence_passages(item.evidence)) + f"\nQuestion: {item.question.text}"
        score = self.model.predict([(premise, item.answer.text)])
        return float(1 - score[0])


class GraniteGuardianBaseline:
    name = "granite-guardian-4.1-8b"

    def __init__(self, model_id: str = "ibm-granite/granite-guardian-4.1-8b", load_in_4bit: bool = True):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        kwargs: dict = {"device_map": "auto"}
        if load_in_4bit:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
        else:
            kwargs["dtype"] = torch.float16
        self.model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs).eval()

    def risk(self, item: Item) -> float:
        documents = [{"doc_id": "0", "text": "\n".join(evidence_passages(item.evidence))}]
        messages = [
            {"role": "user", "content": item.question.text},
            {"role": "assistant", "content": item.answer.text},
            {"role": "user", "content": guardian_block()},
        ]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, documents=documents)
        ids = self.tokenizer(text, return_tensors="pt").to(self.model.device)
        with self.torch.no_grad():
            out = self.model.generate(**ids, max_new_tokens=24, do_sample=False)
        reply = self.tokenizer.decode(out[0, ids["input_ids"].shape[1] :], skip_special_tokens=True)
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
        score = re.findall(r"<score>\s*(.*?)\s*</score>", reply, re.DOTALL)
        return 1.0 if score and score[0].strip().lower() == "yes" else 0.0


def make(name: str):
    if name in LETTUCE:
        return LettuceBaseline(name)
    if name == "hhem":
        return HHEMBaseline()
    if name == "granite":
        return GraniteGuardianBaseline()
    raise ValueError(f"unknown baseline {name}")
