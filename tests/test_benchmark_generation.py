"""The benchmark format, its gold-answer checks, and answer generation against a stand-in server."""

import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from faithguard import benchmark
from faithguard.generation.answers import generate_answers, render_evidence, strip_thinking

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "benchmark-example"


def copy_example(tmp_path: Path) -> Path:
    shutil.copytree(EXAMPLE, tmp_path / "bench")
    return tmp_path / "bench"


def test_example_checks_clean_and_builds_gold():
    findings, counts = benchmark.check(benchmark.report_paths(EXAMPLE))
    assert findings == [] and sum(counts.values()) == 5
    questions, gold = benchmark.build(benchmark.report_paths(EXAMPLE))
    g = gold.questions["DEMO-2025-02"]
    assert g.values[0].kind == "percent" and abs(float(g.values[0].value) - 9.29) < 0.01
    assert questions[0].question.issuer == "LK:DEMO" and questions[0].question.period == "2025"


@pytest.mark.parametrize(
    "old, new, message",
    [
        ("expect: Rs. 14,212,560 thousand", "expect: Rs. 13,004,180 thousand", "does not match"),  # misread figure
        ("answer: t1r3c1\n", "answer: t1r3c9\n", "fails"),  # unknown cell
        ("answer: growth(t1r3c1, t1r3c2)", "answer: growth(t1r3c1, t1r3c4)", "does not match"),  # wrong row/entity
    ],
)
def test_checker_catches_author_mistakes(tmp_path, old, new, message):
    root = copy_example(tmp_path)
    report = root / "LK" / "DEMO" / "2025.yaml"
    text = report.read_text(encoding="utf-8")
    assert old in text
    report.write_text(text.replace(old, new, 1), encoding="utf-8")
    findings, _ = benchmark.check(benchmark.report_paths(root))
    assert any(f.level == "error" and message in f.message for f in findings)


def test_checker_enforces_cross_checking_and_pilot_rules(tmp_path):
    root = copy_example(tmp_path)
    report = root / "LK" / "DEMO" / "2025.yaml"
    report.write_text(report.read_text(encoding="utf-8").replace("checked_by: M.L Ahamed", "checked_by: Sharaf", 1), encoding="utf-8")
    manifest = {"splits": {"LK:DEMO": "test"}}
    findings, _ = benchmark.check(benchmark.report_paths(root), manifest)
    messages = [f.message for f in findings]
    assert any("checked by its own author" in m for m in messages)
    assert any("pilot questions must come from dev issuers" in m for m in messages)


def test_generators_see_plain_tables_without_cell_ids():
    questions, _ = benchmark.build(benchmark.report_paths(EXAMPLE))
    text = render_evidence(questions[0].evidence)
    assert "| Profit after tax | 14,212,560 | 13,004,180 | 12,450,330 | 11,635,900 |" in text
    assert "t1r3c1" not in text and "thousands" in text


def test_thinking_is_stripped_and_flagged():
    assert strip_thinking("<think>hmm</think>Profit was Rs. 5 million.") == ("Profit was Rs. 5 million.", True)
    assert strip_thinking("<think> cut off mid-thought") == ("", True)
    assert strip_thinking("Profit was Rs. 5 million.") == ("Profit was Rs. 5 million.", False)


class _Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        question = body["messages"][-1]["content"].rsplit("Question: ", 1)[-1]
        reply = {"choices": [{"message": {"content": f"Answer to: {question}"}}], "timings": {"predicted_n": 5}}
        data = json.dumps(reply).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


def test_generation_writes_settings_and_resumes(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _Stub)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    questions, _ = benchmark.build(benchmark.report_paths(EXAMPLE))
    out = tmp_path / "answers.jsonl"
    try:
        assert generate_answers(questions[:1], url, "qwen", {"temperature": 1.0}, out) == 1
        assert generate_answers(questions, url, "qwen", {"temperature": 1.0}, out) == len(questions) - 1  # resumes
    finally:
        server.shutdown()
    rows = [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in rows] == [f"{q.question.id}:qwen" for q in questions]
    assert rows[0]["settings"]["seed"] == 2026 and rows[0]["settings"]["prompt_version"]
    assert rows[0]["text"].startswith("Answer to: What was the Group's profit after tax")
