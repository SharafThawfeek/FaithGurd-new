"""Annual reports for the benchmark, listed in manifests/lk-reports.csv and manifests/us-reports.csv.

Each manifest names every issuer's latest annual report: for Sri Lanka the PDF on the
Colombo Stock Exchange (checked on 2026-10-08), for the US the 10-K's main document
on SEC EDGAR (`locate_us`). Each row gives the period, filing date, link and size.
Downloading saves each report under data/raw/reports/<country>/<ISSUER>/<period end>
with the link's extension (.pdf or .htm; never in git), checks its size against the
manifest, and records its SHA-256 in the manifest so every member can confirm they
hold the same file. SEC links go through the SEC client, which declares the
FG_SEC_USER_AGENT contact and keeps to the SEC's request rate.
"""

from __future__ import annotations

import csv
import datetime as dt
import hashlib
import shutil
import urllib.parse
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
        suffix = Path(urllib.parse.urlparse(row["url"]).path).suffix or ".pdf"
        dest = Path(root) / country / row["issuer"] / f"{row['period_end']}{suffix}"
        url = row["url"] if base_url is None else base_url.rstrip("/") + "/" + row["url"].split("/", 3)[-1]
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(".part")
            if urllib.parse.urlparse(row["url"]).hostname.endswith("sec.gov"):
                from faithguard.data import edgar

                tmp.write_bytes(edgar.fetch_document(url))
            else:
                with urllib.request.urlopen(url, timeout=300) as response, open(tmp, "wb") as out:
                    shutil.copyfileobj(response, out)
            tmp.replace(dest)
        size = dest.stat().st_size
        if str(size) != row["bytes"]:
            results.append((row["issuer"], f"size {size} differs from the manifest's {row['bytes']}: check the source"))
            continue
        digest = sha256(dest)
        if row["sha256"] and row["sha256"] != digest:
            results.append((row["issuer"], "checksum differs from the recorded one"))
            continue
        row["sha256"] = digest
        results.append((row["issuer"], f"ok ({size / 2**20:.1f} MB)"))
    write_manifest(manifest, rows)
    return results


def locate_us(issuers: list[dict], splits: dict[str, str], cache_dir: Path | None = None) -> tuple[list[dict], list[str]]:
    """Each US issuer's latest 10-K on EDGAR as a manifest row, plus the issuers that have none.

    The SEC's company list is fetched fresh: a company that stops filing drops out of it.
    """
    from faithguard.data import edgar

    directory = edgar.company_directory()
    rows, problems = [], []
    for issuer in (i for i in issuers if i["country"] == "US"):
        entry = directory.get(issuer["issuer"])
        if entry is None:
            problems.append(f"{issuer['issuer']}: not in the SEC's list of companies that currently file")
            continue
        report = edgar.latest_annual_report(entry["cik_str"], cache_dir)
        if report is None or not report["inline_xbrl"] or not report["bytes"]:
            problems.append(f"{issuer['issuer']}: no 10-K with inline XBRL on EDGAR")
            continue
        period = dt.date.fromisoformat(report["report_date"])
        rows.append({
            "issuer": issuer["issuer"],
            "split": splits.get(f"US:{issuer['issuer']}", "train"),
            "report": f"Form 10-K for the fiscal year ended {period.day} {period:%B %Y}",
            "period_end": report["report_date"],
            "filed": report["filed"],
            "url": report["url"],
            "bytes": str(report["bytes"]),
            "sha256": "",
            "cik": str(entry["cik_str"]),
            "accession": report["accession"],
        })
    return rows, problems
