"""Generating answers to benchmark questions, once, with fixed settings (phases 3 and 5).

Each generator answers every question from the same frozen evidence, rendered as
plain report tables (no cell ids: generators see what a reader would see). Answers
are appended to a JSON Lines file as they arrive, so an interrupted run resumes
where it stopped. Every answer records the settings that produced it.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.request
from pathlib import Path
from typing import Iterable

from faithguard.records import Answer, Evidence

SYSTEM = (
    "You answer questions about company annual reports. Use only the report extract provided. "
    "State each figure with its currency, unit and period. Answer in at most three sentences."
)
SCALE_NOTES = {3: "Rs. '000 / thousands", 6: "millions", 9: "billions"}
_THINK = re.compile(r"<think>.*?</think>|<\|channel>.*?<channel\|>", re.DOTALL)


def render_evidence(evidence: Evidence) -> str:
    """Report tables as a reader sees them: title, units, column headers, values as printed."""
    parts = []
    for t in evidence.tables:
        rows: dict[int, dict[int, str]] = {}
        labels: dict[int, str] = {}
        headers: dict[int, str] = {}
        for c in t.cells:
            rows.setdefault(c.row, {})[c.col] = c.text
            labels[c.row] = c.row_label
            headers[c.col] = c.column_label
        cols = sorted(headers)
        unit = f" (amounts in {SCALE_NOTES[t.scale]})" if t.scale in SCALE_NOTES else ""
        lines = [f"{t.title or 'Table'}{unit}", "| Item | " + " | ".join(headers[c] for c in cols) + " |", "|" + " --- |" * (len(cols) + 1)]
        for r in sorted(rows):
            lines.append(f"| {labels[r]} | " + " | ".join(rows[r].get(c, "") for c in cols) + " |")
        parts.append("\n".join(lines))
    parts += [p.text for p in evidence.passages]
    return "\n\n".join(parts)


def user_prompt(question: str, evidence: Evidence) -> str:
    return f"{render_evidence(evidence)}\n\nQuestion: {question}"


PROMPT_VERSION = hashlib.sha256((SYSTEM + user_prompt("{q}", Evidence())).encode()).hexdigest()[:12]


_OPEN_THINK = re.compile(r"<think>|<\|channel>|<\|think\|>")


def strip_thinking(raw: str) -> tuple[str, bool]:
    """(answer text, whether any reasoning leaked). A reply cut off inside an unclosed
    <think> block leaks too: everything from the opening tag on is dropped."""
    text = _THINK.sub("", raw)
    leaked = text != raw
    unclosed = _OPEN_THINK.search(text)
    if unclosed:
        text, leaked = text[: unclosed.start()], True
    return text.strip(), leaked


def chat(server: str, messages: list[dict], sampling: dict, seed: int, max_tokens: int, timeout: int = 600) -> dict:
    body = {
        "messages": messages, "max_tokens": max_tokens, "seed": seed, "cache_prompt": False,
        "chat_template_kwargs": {"enable_thinking": False}, **sampling,
    }
    request = urllib.request.Request(server.rstrip("/") + "/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as r:
        return json.loads(r.read())


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {json.loads(line)["id"] for line in open(path, encoding="utf-8") if line.strip()}


def generate_answers(questions: Iterable, server: str, generator: str, sampling: dict, out: Path,
                     seed: int = 2026, max_tokens: int = 300) -> int:
    """Answer each question not yet in `out`; returns how many new answers were written."""
    from faithguard.generation.models import LLAMA_TAG, MODELS

    out.parent.mkdir(parents=True, exist_ok=True)
    have = done_ids(out)
    written = 0
    with open(out, "a", encoding="utf-8", newline="\n") as f:
        for bq in questions:
            answer_id = f"{bq.question.id}:{generator}"
            if answer_id in have:
                continue
            messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user_prompt(bq.question.text, bq.evidence)}]
            reply = chat(server, messages, sampling, seed, max_tokens)
            message = reply["choices"][0]["message"]
            raw = message.get("content") or ""
            text, leaked = strip_thinking(raw)
            leaked = leaked or bool(message.get("reasoning_content"))
            answer = Answer(
                id=answer_id, question_id=bq.question.id, generator=generator, text=text,
                settings={
                    "model_file": MODELS[generator]["file"], "sampling": sampling, "seed": seed, "max_tokens": max_tokens,
                    "llama_cpp": LLAMA_TAG, "prompt_version": PROMPT_VERSION, "thinking_leak": leaked,
                    "timings": reply.get("timings", {}),
                },
            )
            f.write(answer.model_dump_json() + "\n")
            f.flush()
            written += 1
    return written
