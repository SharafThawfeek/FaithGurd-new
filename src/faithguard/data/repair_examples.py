"""Training data for the repairer: chat examples whose reply is an edit program (or a rewrite).

For each controlled-track item the detector decides which claims are editable, as it
would in deployment, and the target is built from the gold edit program:

    flagged claim the gold program edits       -> that COPY or CALCULATE
    flagged claim the gold program leaves alone -> KEEP (teaches the model to reject false flags)
    evidence removed on purpose                 -> CANNOT_FIX missing_operand

Items whose wrong claims the detector did not flag are skipped (the edit envelope
would forbid the fix). Some error types can be held out entirely, so the paper can
test repair on error types never seen in training (RQ2). The free-rewrite baseline
uses the same items with the corrected answer text as the target.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Iterable, Iterator

from faithguard.detect import detect
from faithguard.gold import GoldStore
from faithguard.records import CannotFix, EditProgram, Item, Keep
from faithguard.repair.prompting import SYSTEM, build_prompt, editable_claims, program_json

REWRITE_SYSTEM = (
    "You correct wrong numbers in answers about financial reports. Use only the evidence. "
    "Reply with the corrected answer and nothing else, or with CANNOT_FIX if the evidence cannot support it."
)


def target_for(editable: list[str], gold_program: EditProgram) -> EditProgram | None:
    """The gold program restricted to editable claims, with KEEP for the rest. None if a needed edit is not editable."""
    stop = next((e for e in gold_program.edits if isinstance(e, CannotFix)), None)
    if stop is not None:
        return EditProgram(edits=[CannotFix(reason=stop.reason, claim=stop.claim if stop.claim in editable else None)])
    by_claim = {e.claim: e for e in gold_program.edits}
    if any(c not in editable for c in by_claim):
        return None  # the detector missed a wrong claim: the envelope would forbid fixing it
    return EditProgram(edits=[by_claim.get(c, Keep(claim=c)) for c in editable])


def _false_flag(item_id: str, claims: list[str], rate: float) -> str | None:
    """Deterministically pick one claim to flag by mistake, for a share `rate` of items."""
    h = int(hashlib.sha256(item_id.encode()).hexdigest()[:8], 16)
    if not claims or (h % 1000) / 1000 >= rate:
        return None
    return claims[h % len(claims)]


def examples(
    items: Iterable[Item], gold: GoldStore, mode: str = "program", hold_out: tuple[str, ...] = (), false_flag_rate: float = 0.3
) -> Iterator[dict]:
    """Chat-format training examples. mode: 'program' (edit programs) or 'rewrite' (free-text baseline).

    A share of items also get one correct claim flagged by mistake, as a learned
    detector will sometimes do; its target is KEEP (RQ3: training on false flags).
    """
    for item in items:
        injection = gold.injections.get(item.id)
        if injection is None or injection.target_program is None or injection.error in hold_out:
            continue
        det = detect(item)
        editable = editable_claims(det)
        unflagged = [c.id for c in det.claims if c.id not in editable]
        extra = _false_flag(item.id, unflagged, false_flag_rate)
        if extra is not None:
            editable = [c.id for c in det.claims if c.id in set(editable) | {extra}]
        if not editable:
            continue
        target = target_for(editable, injection.target_program)
        if target is None:
            continue
        prompt = build_prompt(item, det.claims, editable)
        if mode == "program":
            system, reply = SYSTEM, program_json(target)
        else:
            from faithguard.repair.rewrite import REWRITE_INSTRUCTIONS

            prompt = prompt.rsplit("Write a JSON edit program", 1)[0] + REWRITE_INSTRUCTIONS
            stop = any(isinstance(e, CannotFix) for e in target.edits)
            system, reply = REWRITE_SYSTEM, ("CANNOT_FIX" if stop or injection.correct_text is None else injection.correct_text)
        yield {
            "id": item.id,
            "error": injection.error,
            "issuer": item.question.issuer,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
                {"role": "assistant", "content": reply},
            ],
        }


def write(path: str | Path, rows: Iterable[dict]) -> Counter:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    counts: Counter = Counter()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
            counts[row["error"]] += 1
    return counts
