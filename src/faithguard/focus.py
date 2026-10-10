"""Focusing large evidence on the rows a decision needs (D-084).

An annual report's income statement and balance sheet run to 40-80 rows. Shown whole, they made the
repairer's prompts about four times longer than the 2,048 tokens it was trained on, and most of
Channel A's inputs longer than its training length too. The controlled track's evidence never exceeds
25 rows, so evidence up to FOCUS_ABOVE_ROWS rows is shown whole and nothing trained or measured there
changes.

Above that, the rows kept are those holding a cell any claim was traced to, and those of the line
items the claims are about or the question names. Rows are kept whole, so the other entity's and
year's figures stay beside each traced one. Only the rule checker's output and the question are
used, never gold.
"""

from __future__ import annotations

from faithguard.records import DetectorOutput, Evidence

FOCUS_ABOVE_ROWS = 30


def focus_rows(evidence: Evidence, det: DetectorOutput | None, question: str = "") -> dict[str, set[int]] | None:
    """{table id: rows to show} when the evidence is large, or None to show all of it."""
    from faithguard.claims import Vocabulary

    cells = evidence.cells()
    if det is None or len({(c.table_id, c.row) for c in cells}) <= FOCUS_ABOVE_ROWS:
        return None
    by_id = {c.id: c for c in cells}
    metrics = {det.check(cl.id).intended.metric for cl in det.claims} - {None}
    metrics |= Vocabulary(cells).metrics_named(question)
    keep: dict[str, set[int]] = {}
    for check in det.checks:
        for cid in check.cells:
            if cid in by_id:
                keep.setdefault(by_id[cid].table_id, set()).add(by_id[cid].row)
    for c in cells:
        if c.metric in metrics:
            keep.setdefault(c.table_id, set()).add(c.row)
    return keep or None
