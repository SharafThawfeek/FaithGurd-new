"""Annual report PDFs for the benchmark, listed in manifests/lk-reports.csv.

The manifest names each issuer's latest annual report on the Colombo Stock Exchange
(its period, filing date, CDN link and size, checked on 2026-10-08). Downloading
saves each PDF under data/raw/reports/<country>/<ISSUER>/<period end>.pdf (never in
git), checks its size against the manifest, and records its SHA-256 in the manifest
so every member can confirm they hold the same file.
"""

from __future__ import annotations

import csv
import hashlib
import shutil
import urllib.request
from pathlib import Path


def read_manifest(path: str | Path) -> list[dict]:
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def write_manifest(path: str | Path, rows: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(manifest: str | Path, splits: set[str], root: str | Path = "data/raw/reports", country: str = "LK",
             base_url: str | None = None) -> list[tuple[str, str]]:
    """Fetch every report in the chosen splits that is not already present; returns (issuer, outcome) pairs."""
    rows = read_manifest(manifest)
    results = []
    for row in rows:
        if row["split"] not in splits:
            continue
        dest = Path(root) / country / row["issuer"] / f"{row['period_end']}.pdf"
        url = row["url"] if base_url is None else base_url.rstrip("/") + "/" + row["url"].split("/", 3)[-1]
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            with urllib.request.urlopen(url, timeout=300) as response, open(tmp, "wb") as out:
                shutil.copyfileobj(response, out)
            tmp.replace(dest)
        size = dest.stat().st_size
        if str(size) != row["bytes"]:
            results.append((row["issuer"], f"size {size} differs from the manifest's {row['bytes']}: check the CSE page"))
            continue
        digest = sha256(dest)
        if row["sha256"] and row["sha256"] != digest:
            results.append((row["issuer"], "checksum differs from the recorded one"))
            continue
        row["sha256"] = digest
        results.append((row["issuer"], f"ok ({size / 2**20:.1f} MB)"))
    write_manifest(manifest, rows)
    return results
