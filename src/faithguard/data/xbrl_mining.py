"""XBRL-mined wrong-context negatives for Channel A (the detection paper's main training signal).

From one filing's facts: for a fact the answer should cite (concept, period, segment),
find sibling facts that differ in exactly one part of the context and hold a different
value. A negative answer states the sibling's number under the cited fact's context,
so the number exists in the filing but belongs elsewhere ("right number, wrong
context"); it is labelled with the slot that differs:

    different period              -> period
    different segment (dimension) -> entity_scope
    different concept             -> metric
    the right number, scaled      -> scale_currency (thousand vs million)

The cited fact's own value gives the matching clean answer. Evidence is a table built
from the filing's facts, so both the right and the wrong cell are visible.
"""

from __future__ import annotations

import re
from collections import defaultdict
from decimal import Decimal
from typing import Iterator

from faithguard.calc.numbers import default_style, render
from faithguard.data.edgar import Fact
from faithguard.detect.channel_a import lettuce_prompt, evidence_passages
from faithguard.records import Evidence
from faithguard.tables import table_from_grid


def possessive(name: str) -> str:
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def concept_label(concept: str) -> str:
    """'us-gaap:NetIncomeLoss' -> 'net income loss'."""
    local = concept.split(":")[-1]
    words = re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", local).split()
    return " ".join(w.lower() for w in words)


def member_label(member: str) -> str:
    local = member.split(":")[-1]
    local = re.sub(r"Member$", "", local)
    return concept_label(local)


def fiscal_year(fact: Fact) -> str:
    return fact.period_end[:4]


def _key(f: Fact) -> tuple:
    return (f.concept, f.period_start, f.period_end, f.dimensions)


def _period_kind(f: Fact) -> str:
    return "instant" if f.period_start is None else "duration"


def siblings(facts: list[Fact], cited: Fact) -> list[tuple[Fact, str]]:
    """Facts differing from `cited` in exactly one context part, with a different value: (fact, slot)."""
    out = []
    for g in facts:
        if g is cited or g.unit != cited.unit or g.value == cited.value or _period_kind(g) != _period_kind(cited):
            continue
        same_concept = g.concept == cited.concept
        same_period = (g.period_start, g.period_end) == (cited.period_start, cited.period_end)
        same_dims = g.dimensions == cited.dimensions
        if same_concept and same_dims and not same_period:
            out.append((g, "period"))
        elif same_concept and same_period and not same_dims and len(g.dimensions) <= 1 and len(cited.dimensions) <= 1:
            out.append((g, "entity_scope"))
        elif not same_concept and same_period and same_dims and not g.dimensions:
            out.append((g, "metric"))
    return out


def evidence_for(facts: list[Fact], concepts: list[str], company: str) -> Evidence:
    """A table: one row per concept (and segment), one column per fiscal year, values in millions."""
    years = sorted({fiscal_year(f) for f in facts if f.concept in concepts}, reverse=True)
    rows: dict[tuple[str, tuple], dict[str, Fact]] = defaultdict(dict)
    for f in facts:
        if f.concept in concepts and len(f.dimensions) <= 1:
            rows[(f.concept, f.dimensions)].setdefault(fiscal_year(f), f)
    grid = [["(in millions)"] + [f"FY{y}" for y in years]]
    for (concept, dims), by_year in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        label = concept_label(concept)
        if dims:
            label = f"{label} - {member_label(dims[0][1])}"
        grid.append([label] + [f"{by_year[y].value / Decimal(10**6):,.1f}" if y in by_year else "" for y in years])
    return Evidence(tables=[table_from_grid("t1", grid, title=f"{company} (from XBRL)", currency="USD")])


def _answer(company: str, cited: Fact, value: Decimal, scale_shift: int = 0) -> tuple[str, tuple[int, int]]:
    label = concept_label(cited.concept)
    seg = f" for its {member_label(cited.dimensions[0][1])} segment" if cited.dimensions else ""
    style = default_style("amount", 6 + scale_shift, "USD", 1)
    number = render(value.scaleb(scale_shift) if scale_shift else value, style)
    if _period_kind(cited) == "instant":
        prefix = f"{possessive(company)} {label}{seg} stood at "
        text = f"{prefix}{number} at the end of fiscal {fiscal_year(cited)}."
    else:
        prefix = f"{possessive(company)} {label}{seg} was "
        text = f"{prefix}{number} in fiscal {fiscal_year(cited)}."
    return text, (len(prefix), len(prefix) + len(number))


def _question(company: str, cited: Fact) -> str:
    seg = f" for its {member_label(cited.dimensions[0][1])} segment" if cited.dimensions else ""
    when = "at the end of" if _period_kind(cited) == "instant" else "in"
    return f"What was {possessive(company)} {concept_label(cited.concept)}{seg} {when} fiscal {fiscal_year(cited)}?"


def mine(facts: list[Fact], company: str, max_per_fact: int = 3, scale_negatives: bool = True) -> Iterator[dict]:
    """Channel A training examples (same format as data.channel_a_examples): clean answers and wrong-context negatives."""
    usd = [f for f in facts if f.unit == "USD" and abs(f.value) >= 10**6 and len(f.dimensions) <= 1]
    for cited in usd:
        sibs = siblings(usd, cited)[:max_per_fact]
        if not sibs:
            continue
        concepts = sorted({cited.concept} | {g.concept for g, _ in sibs})
        evidence = evidence_for(usd, concepts, company)
        prompt = lettuce_prompt(_question(company, cited), evidence_passages(evidence))
        base_id = f"xbrl:{company}:{cited.concept}:{cited.period_end}:{len(cited.dimensions)}"
        text, _ = _answer(company, cited, cited.value)
        yield {"id": base_id + ":none", "source": "xbrl", "error": "none", "prompt": prompt, "answer": text, "spans": []}
        for g, slot in sibs:
            text, span = _answer(company, cited, g.value)
            yield {"id": f"{base_id}:{slot}:{g.context_id}", "source": "xbrl", "error": slot, "prompt": prompt, "answer": text, "spans": [(*span, slot)]}
        if scale_negatives:
            text, span = _answer(company, cited, cited.value, scale_shift=3)
            yield {"id": base_id + ":scale", "source": "xbrl", "error": "scale", "prompt": prompt, "answer": text, "spans": [(*span, "scale_currency")]}
