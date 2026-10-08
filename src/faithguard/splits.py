"""The split manifest: which issuer belongs to which split, frozen with a hash.

Splits are issuer-disjoint: a company never appears in two splits. Benchmark
issuers are assigned per country, spread across sectors, with a fixed seed:

    test         12 per country  (the locked, human-labelled natural test)
    calibration  12 per country  (decision D-007, option B)
    dev           4 per country  (pilot questions come from here, decision D-004)
    train        the rest, plus every FinQA, TAT-QA and RAGTruth source

No FinQA company may be a test or calibration issuer; build() refuses if one is.
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
from collections import defaultdict
from pathlib import Path

COUNTS = {"test": 12, "calibration": 12, "dev": 4}
ORDER = ("test", "calibration", "dev")


def read_issuers(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def assign(issuers: list[dict], seed: int = 2026, counts: dict[str, int] = COUNTS) -> dict[str, str]:
    """issuer id -> split, stratified by sector within each country."""
    out: dict[str, str] = {}
    by_country: dict[str, list[dict]] = defaultdict(list)
    for row in issuers:
        by_country[row["country"]].append(row)
    for country, rows in sorted(by_country.items()):
        rng = random.Random(f"{seed}:{country}")
        by_sector: dict[str, list[dict]] = defaultdict(list)
        for row in sorted(rows, key=lambda r: r["issuer"]):
            by_sector[row["sector"]].append(row)
        for members in by_sector.values():
            rng.shuffle(members)
        # interleave sectors so each split gets a spread of industries
        queue, i = [], 0
        sectors = sorted(by_sector)
        while any(by_sector[s] for s in sectors):
            s = sectors[i % len(sectors)]
            if by_sector[s]:
                queue.append(by_sector[s].pop())
            i += 1
        slots = [split for split in ORDER for _ in range(counts[split])]
        # deal round-robin across the three benchmark splits, then the rest to train
        dealt: dict[str, int] = defaultdict(int)
        k = 0
        for row in queue:
            for _ in range(len(ORDER)):
                split = ORDER[k % len(ORDER)]
                k += 1
                if dealt[split] < counts[split]:
                    dealt[split] += 1
                    out[f"{country}:{row['issuer']}"] = split
                    break
            else:
                out[f"{country}:{row['issuer']}"] = "train"
        assert sum(dealt.values()) <= len(slots)
    return out


def build(issuers_csv: str | Path, finqa_tickers: set[str], seed: int = 2026) -> dict:
    issuers = read_issuers(issuers_csv)
    splits = assign(issuers, seed)
    clash = [k for k, s in splits.items() if k.startswith("US:") and s in ("test", "calibration") and k[3:] in finqa_tickers]
    if clash:
        raise ValueError(f"FinQA companies in test or calibration: {clash}")
    manifest = {
        "seed": seed,
        "counts": COUNTS,
        "rules": [
            "Splits are issuer-disjoint.",
            "FinQA, TAT-QA and RAGTruth sources are training or development data only.",
            "No FinQA company is a test or calibration issuer.",
            "Pilot questions come only from dev issuers.",
            "Future-period set: the next fiscal year's reports of the test issuers, held back unopened.",
        ],
        "splits": dict(sorted(splits.items())),
    }
    manifest["sha256"] = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    return manifest


def split_of(manifest: dict, country: str, issuer: str) -> str:
    """The split an issuer belongs to; any issuer not in the manifest is training data."""
    return manifest["splits"].get(f"{country}:{issuer}", "train")


def verify(manifest: dict) -> bool:
    body = {k: v for k, v in manifest.items() if k != "sha256"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() == manifest.get("sha256")
