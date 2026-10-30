"""The AI stress test: the questions in questions.jsonl, asked through a running demo server the way a presenter
asks them (Ask the AI, then Check it with FaithGuard). It writes one JSON line per question: the AI's answer, the
action, the released text and the on-screen notes. Judging each line against the report's tables is a separate step.

    python demo/stress/run_ai.py http://127.0.0.1:8766 out.jsonl
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

QUESTIONS = Path(__file__).with_name("questions.jsonl")


def post(base: str, path: str, body: dict) -> dict:
    req = urllib.request.Request(base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def main(base: str, out: str) -> None:
    base = base.rstrip("/")
    status = json.loads(urllib.request.urlopen(base + "/api/status", timeout=30).read())
    print("version", status.get("version"), "| AI", status.get("repairer", {}).get("state"), flush=True)
    rows = [json.loads(line) for line in QUESTIONS.open(encoding="utf-8")]
    with open(out, "w", encoding="utf-8") as fh:
        for row in rows:
            rec = {"n": row["n"], "report": row["report"], "question": row["question"]}
            t0 = time.perf_counter()
            ai = post(base, "/api/ask/ai", {"report": row["report"], "question": row["question"]})
            rec["ai_answer"], rec["ai_error"] = ai.get("answer"), ai.get("error")
            if "answer" in ai:
                case = post(base, "/api/ask", {"report": row["report"], "question": row["question"], "answer": ai["answer"]})
                out_ = case.get("output", {})
                rec.update(action=out_.get("action"), released=out_.get("text"), on_screen_notes=case.get("caveats", []),
                           error=case.get("error"))
            rec["seconds"] = round(time.perf_counter() - t0, 1)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            print(rec["n"], rec["report"], rec.get("action") or rec["ai_error"], rec["seconds"], flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
