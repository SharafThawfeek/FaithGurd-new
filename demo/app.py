"""FaithGuard's local demo: one command opens it in the browser.

    .venv\\Scripts\\python demo\\app.py              # live pipeline; trained models live if installed
    .venv\\Scripts\\python demo\\app.py --no-models  # live pipeline only, stored model outputs

Offline: it reads the repository, the local data/ folder and the model files under data/demo-models/.
See demo/README.md.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(HERE), str(ROOT / "src")]

from decimal import InvalidOperation  # noqa: E402

from ask import bad_question  # noqa: E402
from cases import Demo, UnknownExample  # noqa: E402
from results import results  # noqa: E402

STATIC = HERE / "static"
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".svg": "image/svg+xml"}
CHANNEL_A_DIR = ROOT / "data" / "demo-models" / "channel-a" / "model"
ADAPTER_DIR = ROOT / "data" / "demo-models" / "repair-v1" / "adapter"
MAX_FIGURES = 25  # an answer with hundreds of figures would tie up the checker for everyone
# forms the frozen checker misreads, refused with how to write them: "31.03.2026" (read as figures and overwritten) and
# millions or billions before the number, "Rs. Mn 2,580" or "(Rs. Mn) was 2,580" (read as Rs. 2,580); "Rs. '000 1,280"
# and "Rs. thousand 1,280" are read right
NUMERIC_DATE = re.compile(r"\b\d{1,2}[./-]\d{1,2}[./-](?:\d{4}|\d{2})\b|\b\d{4}-\d{2}-\d{2}\b")
UNIT_FIRST = re.compile(r"((?:\bRs\b\.?|\bLKR\b|\bUSD\b|US\$|\$)\s*(?:mn|bn|million|billion)\b\.?)\)?"
                        r"\s*(?:(?:was|were|is|of)\s+|:\s*)?\d", re.I)


def friendly(err: Exception) -> str:
    """A message for the screen; the details go to the console."""
    if isinstance(err, UnknownExample):
        if str(err).startswith("ask-"):
            return "The demo was restarted (or this question is too old), so ask it again."
        return f"Unknown example {err}."
    if isinstance(err, InvalidOperation):
        return "A number in this text has too many digits for the demo. Try a shorter one."
    return ("The pipeline could not process this text, so nothing was decided. "
            f"Try another wording. ({type(err).__name__}: {str(err)[:160]})")


def bad_answer(answer) -> str | None:
    """Why an edited answer cannot be run, or None."""
    if answer is None:
        return None
    if not isinstance(answer, str):
        return "The answer must be text."
    if not answer.strip():
        return "The answer is empty: type an answer to check."
    if len(answer) > 4000:
        return "That answer is too long for the demo (4,000 characters at most)."
    if any(ord(ch) > 0xFFFF for ch in answer):
        return "Emoji and other symbols outside the basic character set are not supported in the demo."
    if len([n for n in re.findall(r"\d[\d,.]*", answer) if not re.fullmatch(r"(?:19|20)\d\d", n)]) > MAX_FIGURES:
        return f"That answer has too many figures for the demo ({MAX_FIGURES} at most, years not counted)."
    if (m := NUMERIC_DATE.search(answer)):
        return (f"Write dates in words (“31 March 2026”): FaithGuard reads every number in an answer as a report figure, so it "
                f"would read “{m.group(0)}” as figures and could overwrite them (a known limitation).")
    if (m := UNIT_FIRST.search(answer)):
        return (f"Write the unit after the number (“Rs. 2,580 million”): FaithGuard ignores “{m.group(1)}” written before "
                "the number, so it would read the figure without its unit (a known limitation).")
    return None


STARTED = time.time()
# What the server runs, for "+ local changes": its Python code, the pages, and the files in git it reads at start. The
# docs (demo/README.md, demo/SIMPLE.md) and the stress test's files (demo/stress/) do not count.
CODE = (":(glob)src/**/*.py", ":(glob)demo/*.py", "demo/static", "demo/rehearsal.json", "runs/policy/controlled/results.json",
        "manifests/issuers.csv")
# Read once at start (the pages' own files are served fresh): a change to one needs a restart. The policy and the
# examples list are not in git (*.pkl, data/), so only this check sees them.
READ_AT_START = (HERE / "rehearsal.json", ROOT / "runs" / "policy" / "controlled" / "policy.pkl",
                 ROOT / "runs" / "policy" / "controlled" / "results.json", ROOT / "data" / "demo" / "examples.json",
                 ROOT / "manifests" / "issuers.csv")


def edited_since(started: float) -> bool:
    """A Python file of demo/ or src/, or a file read at start, changed after the server started: it still runs the older
    code or data."""
    files = [*(ROOT / "src").rglob("*.py"), *HERE.glob("*.py"), *READ_AT_START]
    return any(p.exists() and p.stat().st_mtime > started for p in files)


def local_changes() -> list[str]:
    """The files of CODE that differ from the last commit, as git status lists them."""
    out = subprocess.run(["git", "status", "--porcelain", "--", *CODE], cwd=ROOT, capture_output=True, text=True, timeout=5)
    return out.stdout.splitlines()


def version(started: float | None = None) -> str:
    """The code: the commit, whether the code the server runs differs from it, and whether that code (or a file read at
    start) was edited after the server started. Read again on every status request, so the pill on screen never shows a
    state older than the working tree."""
    try:
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = local_changes()
    except (OSError, subprocess.SubprocessError):
        return ""
    stale = started is not None and edited_since(started)
    return f"{head}{' + local changes' if dirty else ''}{' (edited since the server started: restart it)' if stale else ''}"


class Server(ThreadingHTTPServer):
    """Refuses a port another demo is already using (Windows would otherwise let both bind it)."""

    allow_reuse_address = False
    daemon_threads = True
    request_queue_size = 32

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


class Handler(BaseHTTPRequestHandler):
    demo: Demo

    def log_message(self, fmt, *args):  # keep the console quiet
        pass

    def _send(self, body: bytes, kind: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, status: int = 200) -> None:
        self._send(json.dumps(data).encode("utf-8"), "application/json", status)

    def _guarded(self, fn) -> None:
        try:
            self._json(fn())
        except Exception as err:
            traceback.print_exc()
            self._json({"error": friendly(err)})

    def do_GET(self):
        url = urlparse(self.path)
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        if url.path == "/api/examples":
            return self._guarded(self.demo.listing)
        if url.path == "/api/status":
            return self._guarded(lambda: {**self.demo.status(), "version": version(STARTED)})
        if url.path == "/api/case":
            return self._guarded(lambda: self.demo.case(query.get("id", "")))
        if url.path == "/api/results":
            return self._guarded(lambda: results(ROOT))
        if url.path == "/api/reports":
            return self._guarded(self.demo.report_listing)
        name = "index.html" if url.path in ("/", "") else url.path.lstrip("/")
        path = (STATIC / name).resolve()
        if STATIC in path.parents and path.is_file():
            return self._send(path.read_bytes(), TYPES.get(path.suffix, "application/octet-stream"))
        self._send(b"not found", "text/plain", 404)

    def do_POST(self):
        url = urlparse(self.path)
        try:
            length = int(self.headers.get("Content-Length", 0) or 0)
            if length > 64_000:
                return self._json({"error": "That request is too large for the demo."})
            body = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, UnicodeDecodeError):
            return self._json({"error": "The request was not valid JSON."})
        if not isinstance(body, dict):
            return self._json({"error": "The request was not valid JSON."})
        example, answer = str(body.get("id", "")), body.get("answer")
        problem = bad_answer(answer)
        if problem:
            return self._json({"error": problem})
        if url.path in ("/api/ask", "/api/ask/ai", "/api/ask/draft"):
            report, question = str(body.get("report", "")), body.get("question")
            problem = bad_question(question)
            if problem:
                return self._json({"error": problem})
            if url.path == "/api/ask/ai":
                return self._guarded(lambda: self.demo.ask_ai(report, question))
            if url.path == "/api/ask/draft":
                return self._guarded(lambda: self.demo.ask_draft(report, question))
            if answer is None:
                return self._json({"error": "Type an answer, ask the AI, or write a template answer from the table first."})
            return self._guarded(lambda: self.demo.ask(report, question, answer))
        if url.path == "/api/plant":
            return self._guarded(lambda: self.demo.plant_errors(example))
        if url.path == "/api/run":
            return self._guarded(lambda: self.demo.case(example, answer, channel_a=body.get("channel_a", True) is True))
        if url.path == "/api/channel-a":
            return self._guarded(lambda: self.demo.channel_a_only(example, answer))
        if url.path == "/api/trained":
            return self._guarded(lambda: self.demo.trained_live(example, answer))
        self._json({"error": "unknown request"}, 404)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--no-models", action="store_true", help="do not load Channel A or the trained repairer")
    parser.add_argument("--no-repairer", action="store_true", help="load Channel A only")
    parser.add_argument("--channel-a-device", choices=["cuda", "cpu"],
                        help="default: the CPU when the repairer also loads (6 GB is not enough for both), else the GPU")
    args = parser.parse_args(argv)
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # never reach for the network during a talk
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

    try:
        server = Server(("127.0.0.1", args.port), Handler)
    except OSError:
        sys.exit(f"Port {args.port} is in use: is the demo already running? Close it, or start this one with --port {args.port + 1}.")
    Handler.demo = Demo()
    Handler.demo.prepare()
    if not args.no_models:
        from models import LiveModels

        first = next(iter(Handler.demo.examples.values()))
        warm = next((e.item for e in Handler.demo.examples.values() if e.expect == "repair"), first.item)
        Handler.demo.models = LiveModels(CHANNEL_A_DIR, ADAPTER_DIR, channel_a_device=args.channel_a_device, warm_up=warm)
        Handler.demo.models.start(channel_a=True, repairer=not args.no_repairer)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"FaithGuard demo at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("stopped")


if __name__ == "__main__":
    main()
