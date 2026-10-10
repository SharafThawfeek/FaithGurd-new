"""A repairer driven by a language model that writes edit programs.

The model sees the evidence and the flagged claims and replies with an edit
program. The executor runs it, the hard gate checks it, and if either rejects it
the model gets one retry with the reason. If that also fails, the item is withheld.
Any text-generation backend can be plugged in (see repair.backends).
"""

from __future__ import annotations

from typing import Callable

from faithguard.detect.rules import EvidenceIndex
from faithguard.executor import ExecError, execute
from faithguard.records import CannotFix, DetectorOutput, EditProgram, Item, Keep, RepairOutput
from faithguard.repair.gate import gate
from faithguard.repair.prompting import build_prompt, editable_claims, parse_program

Generate = Callable[[str], str]


class ModelRepairer:
    def __init__(self, generate: Generate, name: str = "model", max_attempts: int = 2):
        self.generate = generate
        self.name = name
        self.max_attempts = max_attempts

    def __call__(self, item: Item, det: DetectorOutput) -> RepairOutput:
        if not det.claims:
            return RepairOutput(item_id=item.id, repairer=self.name, status="cannot_fix", reason="non_numeric: no numbers to repair")
        editable = editable_claims(det)
        if not editable:
            return RepairOutput(item_id=item.id, repairer=self.name, status="nothing_to_fix", text=item.answer.text)
        prompt = build_prompt(item, det.claims, editable, det)
        index = EvidenceIndex(item)
        feedback, reason, program = "", "", None
        for attempt in range(1, self.max_attempts + 1):
            reply = self.generate(prompt + feedback)
            program = parse_program(reply)
            if program is None:
                reason = "the reply was not a valid edit program"
                feedback = f"\n\nYour previous reply was rejected: {reason}. Reply with JSON only."
                continue
            stop = next((e for e in program.edits if isinstance(e, CannotFix)), None)
            if stop is not None:
                return RepairOutput(
                    item_id=item.id, repairer=self.name, status="cannot_fix", program=program, attempts=attempt,
                    reason=f"{stop.reason}: {stop.note}".rstrip(": "),
                )
            outside = [e.claim for e in program.edits if not isinstance(e, Keep) and e.claim not in editable]
            if outside:
                reason = f"edits claims that are not flagged: {', '.join(outside)}"
                feedback = f"\n\nYour previous reply was rejected: {reason}. Edit only the flagged claims."
                continue
            try:
                result = execute(item, det.claims, program)
            except ExecError as err:
                reason = f"the executor rejected it: {err}"
                feedback = f"\n\nYour previous reply was rejected: {reason}."
                continue
            verdict = gate(item, det, program, result, index)
            if verdict.passed:
                return RepairOutput(
                    item_id=item.id, repairer=self.name, status="repaired", program=program, text=result.text, gate=verdict, attempts=attempt
                )
            reason = "; ".join(verdict.failures)
            feedback = f"\n\nYour previous program failed the checks: {reason}. Try again."
        return RepairOutput(
            item_id=item.id, repairer=self.name, status="gate_failed", program=program, attempts=self.max_attempts, reason=reason
        )


def keep_all(det: DetectorOutput) -> EditProgram:
    return EditProgram(edits=[Keep(claim=c.id) for c in det.claims])
