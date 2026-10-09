"""Channel B: the rule checker.

For every numeric claim in an answer it works out what the claim is about
(metric, entity, period), then traces the number to the evidence: a table cell,
or a growth rate, difference or share computed from cells with exact Decimal
arithmetic. If the number only matches under a different context, the failing
relation slots are named:

    Group profit after tax rose 7.0% to Rs. 12,450 million.
    -> "Rs. 12,450 million" matches the Bank's 2025 cell, not the Group's: slot entity_scope
    -> "7.0%" matches the Bank's growth, not the Group's: slot entity_scope

Verdicts: supported (traced under the intended context), unsupported (traced only
under a wrong context, or contradicted by the intended cells), unverifiable (no
rule covers the intended context, or the evidence lacks it). For each claim the
check also records `fix`: the cell expression giving the correct value for the
intended context, which the repairer uses directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from faithguard.calc import ops
from faithguard.calc.numbers import NumberMention, find_numbers, matches
from faithguard.claims import (
    Vocabulary,
    claim_context,
    extract_claims,
    is_change_claim,
    prefers_difference,
    question_context,
    sentence_bounds,
)
from faithguard.records import Cell, Claim, ClaimCheck, Context, DetectorOutput, Item

NAME = "channel-b-v0"
SCALE_SHIFTS = (3, -3, 6, -6, 9, -9)
MAX_ROWS_FOR_SHARES = 40
RELATION_RANK = {"cell": 0, "passage": 1, "growth": 2, "diff": 3, "share": 4, "ratio": 5}
VERDICT_RISK = {"supported": 0.0, "unverifiable": 0.5, "unsupported": 1.0}

SeriesKey = tuple[str, int, "str | None"]  # (table, row, entity)


@dataclass
class Candidate:
    value: Decimal  # base units or percentage points
    cells: list[str]
    context: Context
    relation: str
    printed: Decimal | None = None  # the value in the table's printed units, for bare numbers
    currency: str | None = None
    slots: set[str] = field(default_factory=set)
    rows: tuple[tuple[str, int], ...] = ()
    other_metric: str | None = None  # a share's or ratio's denominator: "49.4% of total assets" names it


def _ctx(cell: Cell, period: str | None = None) -> Context:
    return Context(metric=cell.metric, entity=cell.entity, period=period or cell.period)


def context_slots(found: Context, intended: Context) -> set[str]:
    slots = set()
    if found.metric and intended.metric and found.metric != intended.metric:
        slots.add("metric")
    if found.entity and intended.entity and found.entity != intended.entity:
        slots.add("entity_scope")
    if found.period and intended.period and found.period != intended.period:
        slots.add("period")
    elif found.base_period and intended.base_period and found.base_period != intended.base_period:
        slots.add("period")
    return slots


class EvidenceIndex:
    """Every value the evidence supports, precomputed once per item.

    A series is one table row for one entity, across periods; each yields changes
    (differences and growth rates) between consecutive periods.
    """

    def __init__(self, item: Item):
        self.item = item
        all_cells = item.evidence.cells()
        self.vocab = Vocabulary(all_cells)
        self.cells = [c for c in all_cells if c.value is not None]
        self.series: dict[SeriesKey, dict[str, Cell]] = {}
        for c in self.cells:
            if c.kind in ("amount", "number", "percent") and c.metric and c.period:
                self.series.setdefault((c.table_id, c.row, c.entity), {}).setdefault(c.period, c)
        self.amounts: list[Candidate] = []
        self.percents: list[Candidate] = []
        self.ratios: list[Candidate] = []
        self._build()

    def _build(self) -> None:
        for c in self.cells:
            target = self.percents if c.kind == "percent" else self.ratios if c.kind == "ratio" else self.amounts
            target.append(Candidate(c.value, [c.id], _ctx(c), "cell", printed=c.raw, currency=c.currency, rows=((c.table_id, c.row),)))
        for (table, row, entity), by_period in self.series.items():
            periods = sorted(by_period)
            pairs = [(a, b) for i, a in enumerate(periods) for b in periods[i + 1 :]]  # every earlier/later pair
            for prev_p, cur_p in pairs:
                cur, prev = by_period[cur_p], by_period[prev_p]
                ctx = Context(metric=cur.metric, entity=entity, period=cur_p, base_period=prev_p)
                ids, rows = [cur.id, prev.id], ((table, row),)
                delta = ops.diff(cur.value, prev.value)
                if cur.kind == "percent":  # a change in a rate, in percentage points
                    self.percents.append(Candidate(delta, ids, ctx, "diff", rows=rows))
                else:
                    self.amounts.append(Candidate(delta, ids, ctx, "diff", ops.diff(cur.raw, prev.raw), rows=rows))
                if prev.value != 0:
                    self.percents.append(Candidate(ops.growth(cur.value, prev.value), ids, ctx, "growth", rows=rows))
                if cur.value != 0 and cur.kind != "percent":
                    wrong_base = ops.share(delta, abs(cur.value))
                    self.percents.append(Candidate(wrong_base, ids, ctx, "growth", slots={"basis"}, rows=rows))
        # the same line item for two entities in one period: "the Group's expenses were Rs. 3.6 bn higher than the Bank's"
        by_row: dict[tuple[str, int], dict[str, dict[str, Cell]]] = {}
        for (table, row, entity), by_period in self.series.items():
            if entity is not None:
                by_row.setdefault((table, row), {})[entity] = by_period
        for (table, row), by_entity in by_row.items():
            for a, a_cells in by_entity.items():
                for b, b_cells in by_entity.items():
                    for period, ca in a_cells.items() if a != b else ():
                        cb = b_cells.get(period)
                        if cb is not None and ca.kind != "percent" and cb.kind != "percent":
                            ctx = Context(metric=ca.metric, entity=a, period=period)
                            self.amounts.append(Candidate(
                                ops.diff(ca.value, cb.value), [ca.id, cb.id], ctx, "diff", ops.diff(ca.raw, cb.raw), rows=((table, row),),
                            ))
        by_column: dict[tuple[str, int], list[Cell]] = {}
        for c in self.cells:
            if c.kind == "amount":
                by_column.setdefault((c.table_id, c.col), []).append(c)
        for column in by_column.values():
            if len(column) > MAX_ROWS_FOR_SHARES:
                continue
            for a in column:
                for b in column:
                    if a.id != b.id and b.value != 0 and abs(a.value) <= abs(b.value):
                        ids, ctx = [a.id, b.id], _ctx(a)
                        self.percents.append(Candidate(ops.share(a.value, b.value), ids, ctx, "share", other_metric=b.metric))
                        self.ratios.append(Candidate(ops.ratio(a.value, b.value), ids, ctx, "ratio", other_metric=b.metric))
        for p in self.item.evidence.passages:
            for m in find_numbers(p.text):
                s, e = sentence_bounds(p.text, m.start)
                ctx = self.vocab.context_of(p.text[s:e])
                cand = Candidate(m.value, [p.id], ctx, "passage", printed=m.raw, currency=m.currency)
                (self.percents if m.kind == "percent" else self.ratios if m.kind == "ratio" else self.amounts).append(cand)

    # -- what the intended context supports --------------------------------

    def series_for(self, ctx: Context, prefer_rows: set[tuple[str, int]] = frozenset()) -> list[dict[str, Cell]]:
        """Series for the intended metric (and entity). If the answer already used one of
        several rows with this metric, only that row; otherwise all of them."""
        if ctx.metric is None:
            return []
        found = [(key, s) for key, s in self.series.items() if next(iter(s.values())).metric == ctx.metric]
        if ctx.entity is not None and any(key[2] == ctx.entity for key, _ in found):
            found = [(key, s) for key, s in found if key[2] == ctx.entity]
        elif ctx.entity is None and len({key[2] for key, _ in found}) > 1:
            group = [(key, s) for key, s in found if key[2] == "group"]
            found = group or found
        preferred = [(key, s) for key, s in found if (key[0], key[1]) in prefer_rows]
        return [s for _, s in (preferred or found)]

    def target_cell(self, ctx: Context, prefer_rows=frozenset(), kind: str | None = None) -> Cell | None:
        """The intended cell, or None if absent or ambiguous (several rows disagree)."""
        options = []
        for series in self.series_for(ctx, prefer_rows):
            cell = series.get(ctx.period) if ctx.period else series[max(series)]
            if cell is not None and (kind is None or (cell.kind == "percent") == (kind == "percent")):
                options.append(cell)
        if not options or len({c.value for c in options}) > 1:
            return None
        return options[0]

    def target_pair(self, ctx: Context, prefer_rows=frozenset()) -> tuple[Cell, Cell] | None:
        """The (current, previous) cells for a change in the intended context, or None if absent or ambiguous."""
        options = []
        for series in self.series_for(ctx, prefer_rows):
            period = ctx.period or max(series)
            earlier = [p for p in series if p < period]
            base = ctx.base_period if ctx.base_period in series else (max(earlier) if earlier else None)
            if period in series and base is not None and base < period:
                options.append((series[period], series[base]))
        if not options or len({(a.value, b.value) for a, b in options}) > 1:
            return None
        return options[0]


def _value_matches(claim: Claim, mention: NumberMention, cand: Candidate, directional: bool) -> tuple[bool, set[str]]:
    """Does the claim's number equal this candidate? Returns (match, extra slots)."""
    if claim.kind == "number" and cand.printed is not None:
        if matches(mention, cand.printed) or matches(mention, cand.value):
            return True, set()
    if directional and claim.value >= 0:
        if matches(mention, abs(cand.value)):
            sign_wrong = (claim.direction == "up" and cand.value < 0) or (claim.direction == "down" and cand.value > 0)
            return True, {"sign"} if sign_wrong else set()
        return False, set()
    if matches(mention, cand.value):
        return True, set()
    if matches(mention, -cand.value) and cand.value != 0:
        return True, {"sign"}
    if claim.kind == "amount":
        for shift in SCALE_SHIFTS:
            if matches(mention, cand.value.scaleb(shift)):
                return True, {"scale_currency"}
    return False, set()


def expected_value(
    claim: Claim, intended: Context, index: EvidenceIndex, is_change: bool, prefer_diff: bool, prefer_rows=frozenset()
) -> tuple[Decimal | None, str | None, list[str], str | None]:
    """(value, fix expression, cells, relation) the evidence supports for the intended context, if a rule covers it.

    A percentage is read as a change only when the sentence says so ("rose 7%", "a
    change of 7%"); "return on equity was 15%" is a level. For rates, "by 2.1%"
    means a change in percentage points, otherwise a relative growth rate.
    """
    if claim.kind == "percent":
        if is_change:
            pair = index.target_pair(intended, prefer_rows)
            if pair is not None:
                cur, prev = pair
                if cur.kind == "percent" and prefer_diff:
                    return ops.diff(cur.value, prev.value), f"diff({cur.id}, {prev.id})", [cur.id, prev.id], "diff"
                if prev.value != 0:
                    return ops.growth(cur.value, prev.value), f"growth({cur.id}, {prev.id})", [cur.id, prev.id], "growth"
            return None, None, [], None
        cell = index.target_cell(intended, prefer_rows, kind="percent")
        return (cell.value, cell.id, [cell.id], "cell") if cell is not None else (None, None, [], None)
    if claim.kind in ("amount", "number"):
        if is_change and prefer_diff:
            pair = index.target_pair(intended, prefer_rows)
            if pair is not None and pair[0].kind != "percent":
                cur, prev = pair
                value = ops.diff(cur.raw, prev.raw) if claim.kind == "number" else ops.diff(cur.value, prev.value)
                return value, f"diff({cur.id}, {prev.id})", [cur.id, prev.id], "diff"
        cell = index.target_cell(intended, prefer_rows, kind="amount")
        if cell is not None:
            return (cell.raw if claim.kind == "number" else cell.value), cell.id, [cell.id], "cell"
    return None, None, [], None


def check_claim(
    claim: Claim, mention: NumberMention, intended: Context, index: EvidenceIndex,
    is_change: bool = False, prefer_diff: bool = False, prefer_rows=frozenset(), named_metrics=frozenset(),
) -> tuple[ClaimCheck, tuple[tuple[str, int], ...]]:
    pool = index.percents if claim.kind == "percent" else index.ratios if claim.kind == "ratio" else index.amounts
    best: tuple[int, int, Candidate, set[str]] | None = None
    for cand in pool:
        directional = claim.direction is not None and cand.relation in ("growth", "diff")
        ok, extra = _value_matches(claim, mention, cand, directional)
        if not ok:
            continue
        slots = set(cand.slots) | extra | context_slots(cand.context, intended)
        if ("metric" in slots and cand.other_metric is not None and intended.metric == cand.other_metric
                and cand.context.metric in named_metrics):
            slots.discard("metric")  # "Leases were Rs. 83 bn. This is 49.4% of total assets": the clause names the denominator
        if claim.currency and cand.currency and claim.currency != cand.currency:
            slots.add("scale_currency")
        key = (len(slots), RELATION_RANK[cand.relation])
        if best is None or key < best[:2]:
            best = (*key, cand, slots)

    change = is_change
    # If the claim traced to a cell of the intended context but with the wrong scale or sign,
    # that cell's row is the one to fix from.
    if best is not None and not context_slots(best[2].context, intended):
        rows = best[2].rows or prefer_rows
    else:
        rows = prefer_rows
    expected, fix, target_cells, relation = expected_value(claim, intended, index, change, prefer_diff, rows)
    if best is not None and best[2].relation == "passage" and not best[3] and intended.metric and best[2].context.metric != intended.metric:
        # The number appears in the text, but in a sentence that does not name the intended metric: weak evidence.
        return ClaimCheck(
            claim_id=claim.id, verdict="unverifiable", slots=[], cells=best[2].cells, intended=intended,
            expected=expected, note="found only in text that does not name this metric",
        ), ()
    if best is not None:
        _, _, cand, slots = best
        supported = not slots
        return ClaimCheck(
            claim_id=claim.id,
            verdict="supported" if supported else "unsupported",
            slots=sorted(slots),
            cells=cand.cells,
            intended=intended,
            relation=cand.relation if cand.relation != "passage" else None,
            expected=expected,
            fix=None if supported else fix,
            note=f"traced to {cand.relation} {', '.join(cand.cells)}",
        ), (cand.rows if supported else ())
    if expected is not None:
        return ClaimCheck(
            claim_id=claim.id, verdict="unsupported", slots=["value"], cells=target_cells, intended=intended,
            relation=relation, expected=expected, fix=fix, note="the intended cells hold a different value",
        ), ()
    return ClaimCheck(
        claim_id=claim.id, verdict="unverifiable", slots=["missing_operand"], intended=intended,
        note="no rule covers this claim, or the evidence lacks its context",
    ), ()


def detect(item: Item) -> DetectorOutput:
    """Check every numeric claim in the item's answer against its evidence."""
    text = item.answer.text
    index = EvidenceIndex(item)
    claims = extract_claims(text)
    mentions = {(m.start, m.end): m for m in find_numbers(text)}
    default = question_context(item.question, index.vocab)
    intended = [claim_context(text, claims, i, index.vocab, default) for i in range(len(claims))]

    # First pass finds the table rows the answer's correct numbers come from; the
    # second pass prefers those rows when a metric appears in more than one row.
    used_rows: dict[str | None, set] = {}
    results = []
    for _ in range(2):
        results = []
        for i, claim in enumerate(claims):
            check, rows = check_claim(
                claim, mentions[(claim.start, claim.end)], intended[i], index,
                is_change=is_change_claim(text, claims, i), prefer_diff=prefers_difference(text, claim),
                prefer_rows=frozenset(used_rows.get(intended[i].metric, ())),
                named_metrics=frozenset(index.vocab.metrics_named(text[: claim.start])),
            )
            results.append(check)
            if rows:
                used_rows.setdefault(intended[i].metric, set()).update(rows)
    risk = max((VERDICT_RISK[c.verdict] for c in results), default=0.5)
    answers = any(
        c.verdict == "supported" and (default.metric is None or c.intended.metric == default.metric) for c in results
    )
    return DetectorOutput(item_id=item.id, detector=NAME, claims=claims, checks=results, risk=risk, answers_question=answers)
