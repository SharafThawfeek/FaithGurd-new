"""US annual reports from SEC EDGAR: the 10-K manifest, its lookup, and byte-exact downloads."""

import csv
import hashlib
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from faithguard.data import edgar, reports

ROOT = Path(__file__).resolve().parents[1]
FILED = b"<html><body><div>Consolidated Balance Sheets</div></body></html>\n"
SERVED = FILED.replace(b"</body>", b'<script type="text/javascript"  src="/AbC-d/eF1/gh"></script></body>')


def test_injected_script_is_removed(monkeypatch):
    monkeypatch.setattr(edgar, "fetch", lambda url, cache=None: SERVED)
    assert edgar.fetch_document("https://www.sec.gov/x.htm") == FILED
    monkeypatch.setattr(edgar, "fetch", lambda url, cache=None: FILED)
    assert edgar.fetch_document("https://www.sec.gov/x.htm") == FILED


def test_sec_download_declares_contact_and_keeps_filed_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("FG_SEC_USER_AGENT", "FaithGuard test tester@example.org")
    agents = []

    class Files(BaseHTTPRequestHandler):
        def do_GET(self):
            agents.append(self.headers.get("User-Agent"))
            self.send_response(200)
            self.send_header("Content-Length", str(len(SERVED)))
            self.end_headers()
            self.wfile.write(SERVED)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Files)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    manifest = tmp_path / "us-reports.csv"
    row = {"issuer": "DEMO", "split": "dev", "report": "Form 10-K", "period_end": "2025-12-31", "filed": "2026-02-20",
           "url": "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/demo-20251231.htm",
           "bytes": str(len(FILED)), "sha256": "", "cik": "1", "accession": "0000000001-26-000001"}
    with open(manifest, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)
    try:
        results = reports.download(manifest, {"dev"}, tmp_path / "raw", "US", base_url=f"http://127.0.0.1:{server.server_address[1]}")
    finally:
        server.shutdown()
    assert results == [("DEMO", "ok (0.0 MB)")]
    assert agents == ["FaithGuard test tester@example.org"]
    assert (tmp_path / "raw" / "US" / "DEMO" / "2025-12-31.htm").read_bytes() == FILED
    assert reports.read_manifest(manifest)[0]["sha256"] == hashlib.sha256(FILED).hexdigest()


def test_locate_us_lists_latest_10k_and_reports_missing_issuers(monkeypatch):
    monkeypatch.setattr(edgar, "company_directory", lambda cache_dir=None: {"AAA": {"cik_str": 7, "title": "AAA INC"}})
    monkeypatch.setattr(edgar, "latest_annual_report", lambda cik, cache_dir=None: {
        "accession": "0000000007-26-000003", "filed": "2026-02-27", "report_date": "2026-01-31",
        "document": "aaa-20260131.htm", "inline_xbrl": True, "bytes": 2_000_000,
        "url": "https://www.sec.gov/Archives/edgar/data/7/000000000726000003/aaa-20260131.htm",
    })
    issuers = [{"country": "US", "issuer": "AAA"}, {"country": "US", "issuer": "GONE"}, {"country": "LK", "issuer": "COMB"}]
    rows, problems = reports.locate_us(issuers, {"US:AAA": "dev"})
    assert [(r["issuer"], r["split"], r["period_end"], r["bytes"], r["cik"]) for r in rows] == [
        ("AAA", "dev", "2026-01-31", "2000000", "7")
    ]
    assert rows[0]["report"] == "Form 10-K for the fiscal year ended 31 January 2026"
    assert problems == ["GONE: not in the SEC's list of companies that currently file"]


def test_us_manifest_covers_every_benchmark_issuer():
    rows = reports.read_manifest(ROOT / "manifests" / "us-reports.csv")
    manifest = json.loads((ROOT / "manifests" / "splits.json").read_text(encoding="utf-8"))
    benchmark = {k[3:] for k, v in manifest["splits"].items() if k.startswith("US:") and v != "train"}
    assert benchmark <= {r["issuer"] for r in rows}
    assert all(r["split"] == manifest["splits"].get(f"US:{r['issuer']}", "train") for r in rows)
    assert all(r["url"].startswith("https://www.sec.gov/Archives/edgar/data/") and int(r["bytes"]) > 500_000 for r in rows)
