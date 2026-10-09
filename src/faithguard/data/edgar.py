"""SEC EDGAR: company filings and their XBRL facts, for US evidence and XBRL-mined negatives.

The SEC requires every automated request to declare who is asking, in the
User-Agent header ("Name email@domain"), and blocks requests that do not. Set it
once in the environment before using this module:

    FG_SEC_USER_AGENT="FaithGuard research Your Name you@example.com"

Two sources of facts:
- companyfacts API: every non-dimensional fact a company has reported (fast, JSON)
- the XBRL instance of one filing (the *_htm.xml next to an inline 10-K): every fact
  with its context, including segment dimensions, which XBRL mining needs.

The instance is parsed directly with the standard library rather than Arelle:
mining needs concepts, values, periods, units, decimals and dimensions, all of
which are in the instance itself; Arelle would also download the full US-GAAP
taxonomy for each filing (decision D-014).
"""

from __future__ import annotations

import gzip
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

SEC_DATA = "https://data.sec.gov"
SEC_WWW = "https://www.sec.gov"
MIN_INTERVAL = 0.12  # the SEC allows 10 requests per second; stay under it
_last_request = 0.0

XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"


class SecAccessError(RuntimeError):
    pass


def user_agent() -> str:
    ua = os.environ.get("FG_SEC_USER_AGENT", "").strip()
    if "@" not in ua:
        raise SecAccessError(
            "Set FG_SEC_USER_AGENT to 'Name email@domain' before calling the SEC (it blocks undeclared tools)."
        )
    return ua


def fetch(url: str, cache: Path | None = None) -> bytes:
    """GET with the declared User-Agent, polite rate limiting and an optional file cache."""
    global _last_request
    if cache is not None and cache.exists():
        return cache.read_bytes()
    wait = MIN_INTERVAL - (time.monotonic() - _last_request)
    if wait > 0:
        time.sleep(wait)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent(), "Accept-Encoding": "gzip, deflate"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
            if response.headers.get("Content-Encoding") == "gzip":
                body = gzip.decompress(body)
    except urllib.error.HTTPError as err:
        raise SecAccessError(f"SEC returned {err.code} for {url}") from err
    finally:
        _last_request = time.monotonic()
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(body)
    return body


# www.sec.gov adds a bot-check script tag to every HTML page it serves, just before </body>
_INJECTED_SCRIPT = re.compile(rb'<script type="text/javascript"\s+src="/[^"]+"></script>(?=</body>\s*</html>\s*$)')


def fetch_document(url: str, cache: Path | None = None) -> bytes:
    """A filing document byte for byte as filed: the script tag the SEC's web server adds is removed."""
    return _INJECTED_SCRIPT.sub(b"", fetch(url, cache), count=1)


def cik10(cik: int | str) -> str:
    return str(int(cik)).zfill(10)


# ---------------------------------------------------------------------------
# Company facts (non-dimensional)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Fact:
    concept: str  # e.g. "us-gaap:NetIncomeLoss"
    value: Decimal
    unit: str  # e.g. "USD", "USD/shares", "pure"
    period_end: str  # ISO date
    period_start: str | None = None  # None for instant facts
    decimals: int | None = None  # None means INF
    entity: str = ""  # CIK
    dimensions: tuple[tuple[str, str], ...] = ()  # (axis, member) pairs; empty = whole entity
    form: str | None = None
    fiscal_year: int | None = None
    accession: str | None = None
    context_id: str | None = None


def company_facts(cik: int | str, cache_dir: Path | None = None) -> Iterator[Fact]:
    cache = cache_dir / f"companyfacts-{cik10(cik)}.json" if cache_dir else None
    data = json.loads(fetch(f"{SEC_DATA}/api/xbrl/companyfacts/CIK{cik10(cik)}.json", cache))
    for taxonomy, concepts in data.get("facts", {}).items():
        for concept, body in concepts.items():
            for unit, facts in body.get("units", {}).items():
                for f in facts:
                    try:
                        value = Decimal(str(f["val"]))
                    except (InvalidOperation, KeyError):
                        continue
                    yield Fact(
                        concept=f"{taxonomy}:{concept}", value=value, unit=unit, period_end=f["end"],
                        period_start=f.get("start"), entity=cik10(cik), form=f.get("form"),
                        fiscal_year=f.get("fy"), accession=f.get("accn"),
                    )


def annual_filings(cik: int | str, cache_dir: Path | None = None, forms=("10-K",)) -> list[dict]:
    """Recent annual filings: accession number, filing date, report date, primary document."""
    cache = cache_dir / f"submissions-{cik10(cik)}.json" if cache_dir else None
    data = json.loads(fetch(f"{SEC_DATA}/submissions/CIK{cik10(cik)}.json", cache))
    recent = data["filings"]["recent"]
    out = []
    for i, form in enumerate(recent["form"]):
        if form in forms:
            out.append({
                "accession": recent["accessionNumber"][i], "filed": recent["filingDate"][i],
                "report_date": recent["reportDate"][i], "document": recent["primaryDocument"][i],
                "inline_xbrl": bool(recent.get("isInlineXBRL", [0] * len(recent["form"]))[i]),
            })
    return out


def company_directory(cache_dir: Path | None = None) -> dict[str, dict]:
    """Ticker -> {cik_str, ticker, title} for every company that currently files with the SEC."""
    cache = cache_dir / "company_tickers.json" if cache_dir else None
    directory: dict[str, dict] = {}
    for row in json.loads(fetch(f"{SEC_WWW}/files/company_tickers.json", cache)).values():
        directory.setdefault(row["ticker"].upper(), row)
    return directory


def filing_folder(cik: int | str, accession: str) -> str:
    return f"{SEC_WWW}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}"


def filing_files(cik: int | str, accession: str, cache_dir: Path | None = None) -> list[dict]:
    """The files of one filing (name, size, type), from its EDGAR folder listing."""
    cache = cache_dir / f"index-{accession}.json" if cache_dir else None
    return json.loads(fetch(f"{filing_folder(cik, accession)}/index.json", cache))["directory"]["item"]


def instance_url(cik: int | str, accession: str, cache_dir: Path | None = None) -> str | None:
    """The extracted XBRL instance (*_htm.xml) of one filing, if EDGAR published one."""
    for item in filing_files(cik, accession, cache_dir):
        if item["name"].endswith("_htm.xml"):
            return f"{filing_folder(cik, accession)}/{item['name']}"
    return None


def latest_annual_report(cik: int | str, cache_dir: Path | None = None) -> dict | None:
    """The newest 10-K: accession, period end, filing date, and the main document's link and size.

    The filing list is always fetched fresh (a cached copy may predate the newest
    report); a filing's folder listing never changes, so that is cached.
    """
    filings = annual_filings(cik)
    if not filings:
        return None
    latest = max(filings, key=lambda f: f["filed"])
    files = {item["name"]: item for item in filing_files(cik, latest["accession"], cache_dir)}
    size = files.get(latest["document"], {}).get("size")
    return {
        **latest,
        "url": f"{filing_folder(cik, latest['accession'])}/{latest['document']}",
        "bytes": int(size) if size else None,
    }


# ---------------------------------------------------------------------------
# XBRL instance parsing (dimensional facts)
# ---------------------------------------------------------------------------


@dataclass
class _Context:
    start: str | None = None
    end: str | None = None
    dims: list[tuple[str, str]] = field(default_factory=list)


def _qname(tag: str, nsmap: dict[str, str]) -> str:
    """'{http://fasb.org/us-gaap/2024}NetIncomeLoss' -> 'us-gaap:NetIncomeLoss'."""
    if tag.startswith("{"):
        uri, local = tag[1:].split("}")
        return f"{nsmap.get(uri, uri)}:{local}"
    return tag


def parse_instance(xml: bytes, entity: str = "") -> list[Fact]:
    """Every numeric fact in an XBRL instance, with its period, unit, decimals and dimensions."""
    nsmap: dict[str, str] = {}
    for _, (prefix, uri) in ET.iterparse(__import__("io").BytesIO(xml), events=["start-ns"]):
        nsmap.setdefault(uri, prefix or "default")
    root = ET.fromstring(xml)
    contexts: dict[str, _Context] = {}
    for ctx in root.iter(f"{XBRLI}context"):
        c = _Context()
        period = ctx.find(f"{XBRLI}period")
        if period is not None:
            instant = period.find(f"{XBRLI}instant")
            if instant is not None:
                c.end = instant.text.strip()
            else:
                c.start = period.findtext(f"{XBRLI}startDate", "").strip() or None
                c.end = period.findtext(f"{XBRLI}endDate", "").strip() or None
        for member in ctx.iter(f"{XBRLDI}explicitMember"):
            c.dims.append((member.get("dimension", ""), (member.text or "").strip()))
        for member in ctx.iter(f"{XBRLDI}typedMember"):
            c.dims.append((member.get("dimension", ""), "".join(member.itertext()).strip()))
        contexts[ctx.get("id")] = c
    units: dict[str, str] = {}
    for unit in root.iter(f"{XBRLI}unit"):
        measures = [_qname_text(m.text) for m in unit.iter(f"{XBRLI}measure")]
        divide = unit.find(f"{XBRLI}divide")
        if divide is not None and len(measures) == 2:
            units[unit.get("id")] = f"{measures[0]}/{measures[1]}"
        else:
            units[unit.get("id")] = "*".join(measures)
    facts = []
    for el in root:
        ref, unit_ref = el.get("contextRef"), el.get("unitRef")
        if ref is None or unit_ref is None or el.text is None:
            continue
        try:
            value = Decimal(el.text.strip())
        except InvalidOperation:
            continue
        ctx = contexts.get(ref, _Context())
        decimals = el.get("decimals")
        facts.append(Fact(
            concept=_qname(el.tag, nsmap), value=value, unit=units.get(unit_ref, unit_ref),
            period_end=ctx.end or "", period_start=ctx.start,
            decimals=None if decimals in (None, "INF") else int(decimals), entity=entity,
            dimensions=tuple(sorted(ctx.dims)), context_id=ref,
        ))
    return facts


def _qname_text(text: str | None) -> str:
    """'iso4217:USD' -> 'USD'; 'xbrli:shares' -> 'shares'."""
    text = (text or "").strip()
    return text.split(":", 1)[1] if ":" in text else text
