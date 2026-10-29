"""Released detectors the detection paper compares against (GPU; inference only).

Each scores an item with a risk in [0, 1] (higher = more likely unsupported), on the
same evidence text Channel A sees, focused the same way when it is large (passages(), D-091):

    lettuce   LettuceDetect v1-large or v2 mmBERT (span detector): risk = highest span confidence
    hhem      Vectara HHEM-2.1-Open (premise/hypothesis consistency): risk = 1 - consistency
    granite   IBM Granite Guardian 4.1-8B, groundedness criterion, no-think mode: risk = 1 if it says "yes"
"""

from __future__ import annotations

import re

from faithguard.detect.channel_a import evidence_passages
from faithguard.records import Item


def passages(item: Item) -> list[str]:
    """The evidence passages every detector sees: above 30 rows, only the rows the rule checker traced the
    claims to and the line items they or the question name (faithguard.focus), as for Channel A."""
    from faithguard.detect import detect
    from faithguard.focus import focus_rows

    return evidence_passages(item.evidence, focus=focus_rows(item.evidence, detect(item), item.question.text))

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
            context=passages(item), question=item.question.text, answer=item.answer.text, output_format="spans"
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
        premise = "\n".join(passages(item)) + f"\nQuestion: {item.question.text}"
        score = self.model.predict([(premise, item.answer.text)])
        return float(1 - score[0])


class GraniteGuardianBaseline:
    name = "granite-guardian-4.1-8b"

    def __init__(self, model_id: str = "ibm-granite/granite-guardian-4.1-8b", load_in_4bit: bool = True):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tokenizer = AutoTokenizer.from_pretrained(model_id)
        kwargs: dict = {"device_map": "auto"}
        if load_in_4bit:
            from transformers import BitsAndBytesConfig

            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_compute_dtype=torch.float16)
        else:
            kwargs["dtype"] = torch.float16
        self.model = AutoModelForCausalLM.from_pretrained(model_id, **kwargs).eval()

    def risk(self, item: Item) -> float:
        documents = [{"doc_id": "0", "text": "\n".join(passages(item))}]
        messages = [
            {"role": "user", "content": item.question.text},
            {"role": "assistant", "content": item.answer.text},
            {"role": "user", "content": guardian_block()},
        ]
        text = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, documents=documents)
        ids = self.tokenizer(text, return_tensors="pt")["input_ids"].to(self.model.device)
        reply = self.tokenizer.decode(greedy_reply(self.model, ids, max_new_tokens=24), skip_special_tokens=True)
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.DOTALL)
        score = re.findall(r"<score>\s*(.*?)\s*</score>", reply, re.DOTALL)
        return 1.0 if score and score[0].strip().lower() == "yes" else 0.0


def greedy_reply(model, ids, max_new_tokens: int, chunk: int = 1024) -> list[int]:
    """Greedy decoding as model.generate(do_sample=False) does it, with the prompt read into the cache `chunk` tokens
    at a time: on a T4 the attention of a 9,000-token prompt in one pass does not fit in memory (no flash attention)."""
    import torch
    from transformers import DynamicCache

    eos = model.generation_config.eos_token_id
    eos = set(eos if isinstance(eos, list) else [] if eos is None else [eos])
    cache, out, reply = DynamicCache(), None, []
    with torch.no_grad():
        for start in range(0, ids.shape[1], chunk):
            out = model(input_ids=ids[:, start : start + chunk], past_key_values=cache, use_cache=True, logits_to_keep=1)
        for _ in range(max_new_tokens):
            token = int(out.logits[0, -1].argmax())
            if token in eos:
                break
            reply.append(token)
            out = model(input_ids=torch.tensor([[token]], device=ids.device), past_key_values=cache, use_cache=True, logits_to_keep=1)
    return reply


def make(name: str):
    if name in LETTUCE:
        return LettuceBaseline(name)
    if name == "hhem":
        return HHEMBaseline()
    if name == "granite":
        return GraniteGuardianBaseline()
    raise ValueError(f"unknown baseline {name}")
