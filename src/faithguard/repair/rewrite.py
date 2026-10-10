"""The free-rewrite baseline (FRED-style): the model rewrites the whole answer.

Same backbone, same data and same prompt as the edit-program repairer, but the reply
is the corrected answer text (or CANNOT_FIX). There is no executor and no gate: that
is the comparison the repair paper's main question (RQ1) makes.
"""

from __future__ import annotations

from typing import Callable

from faithguard.records import DetectorOutput, Item, RepairOutput
from faithguard.repair.prompting import build_prompt, editable_claims

REWRITE_INSTRUCTIONS = (
    "Rewrite the answer so that every number is supported by the evidence, changing as little as possible. "
    "Reply with the corrected answer only, or with CANNOT_FIX if the evidence lacks what is needed."
)


class RewriteRepairer:
    def __init__(self, generate: Callable[[str], str], name: str = "rewrite"):
        self.generate = generate
        self.name = name

    def __call__(self, item: Item, det: DetectorOutput) -> RepairOutput:
        editable = editable_claims(det)
        if det.claims and not editable:
            return RepairOutput(item_id=item.id, repairer=self.name, status="nothing_to_fix", text=item.answer.text)
        prompt = build_prompt(item, det.claims, editable, det).rsplit("Write a JSON edit program", 1)[0] + REWRITE_INSTRUCTIONS
        reply = self.generate(prompt).strip()
        if not reply or reply.upper().startswith("CANNOT_FIX"):
            return RepairOutput(item_id=item.id, repairer=self.name, status="cannot_fix", reason="the model declined", attempts=1)
        return RepairOutput(item_id=item.id, repairer=self.name, status="repaired", text=reply, attempts=1)
