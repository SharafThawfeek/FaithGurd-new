"""Phase-1 generation pilot: how many answers per GPU hour can a free T4 produce?

Runs both answer generators at 4-bit with llama.cpp on one GPU and times them on
realistic financial questions (a long report extract plus one question):
    qwen    unsloth/Qwen3.5-9B-GGUF            Qwen3.5-9B-Q4_K_M.gguf          (5.7 GB)
    gemma   google/gemma-4-12B-it-qat-q4_0-gguf gemma-4-12b-it-qat-q4_0.gguf     (7.0 GB)

Both run with thinking turned off (decision D-010) and with prompt caching off, so
each answer is timed as if its evidence were new. A second test runs four requests
at once, to see whether parallel slots raise throughput.

llama.cpp is pinned to release b11490. The pilot first tries the prebuilt Linux CUDA
binary with the system's CUDA libraries, then with llama.cpp's own CUDA runtime, and
if neither runs it builds from source (one time, roughly 10-30 minutes). Pass
--llama-server to reuse a binary from an earlier run.

Linux only (Kaggle or Colab). On a laptop, use --dry-run to check the prompts.

Examples:
    python generation_pilot.py
    python generation_pilot.py --models qwen --questions 4
    python generation_pilot.py --dry-run
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import os
import random
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from common import environment, nvidia_smi, print_gpu_log_row, write_result

LLAMA_TAG = "b11490"
RELEASE_URL = f"https://github.com/ggml-org/llama.cpp/releases/download/{LLAMA_TAG}"
PREBUILT = f"llama-{LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"  # 172 MB
CUDART = f"cudart-llama-{LLAMA_TAG}-bin-ubuntu-cuda-12.8-x64.tar.gz"  # 594 MB; only if the system lacks CUDA libraries

# Sampling: each vendor's recommended non-thinking settings, read from the model cards on 2026-10-08.
# The final generation settings are fixed and pre-registered in phase 5.
MODELS = {
    "qwen": {
        "repo": "unsloth/Qwen3.5-9B-GGUF",
        "file": "Qwen3.5-9B-Q4_K_M.gguf",
        "sampling": {"temperature": 1.0, "top_p": 1.0, "top_k": 20, "presence_penalty": 2.0},
    },
    "gemma": {
        "repo": "google/gemma-4-12B-it-qat-q4_0-gguf",
        "file": "gemma-4-12b-it-qat-q4_0.gguf",
        "sampling": {"temperature": 1.0, "top_p": 0.95, "top_k": 64},
    },
}

SYSTEM_PROMPT = (
    "You answer questions about company annual reports. Use only the report extract provided. "
    "State each figure with its currency, unit and period. Answer in at most three sentences."
)

METRICS = [
    "Gross income", "Interest income", "Interest expenses", "Net interest income", "Fee and commission income",
    "Net fee and commission income", "Net gains from trading", "Other operating income", "Total operating income",
    "Impairment charges", "Net operating income", "Personnel expenses", "Depreciation and amortisation",
    "Other operating expenses", "Operating profit before taxes on financial services", "Taxes on financial services",
    "Profit before income tax", "Income tax expense", "Profit after tax", "Total assets", "Loans and advances",
    "Deposits from customers", "Total equity", "Earnings per share (Rs.)",
]

QUESTIONS = [
    "What was the Group's profit after tax in FY2025?",
    "By how much did the Bank's net interest income change in FY2025, in percent?",
    "What was the Group's total operating income in FY2025 compared with FY2024?",
    "What were the Bank's impairment charges in FY2025?",
    "What share of the Group's gross income in FY2025 came from interest income?",
    "Did the Bank's personnel expenses rise or fall in FY2025, and by how much?",
    "What was the Group's earnings per share in FY2025?",
    "What was the difference between the Group's and the Bank's total assets at the end of FY2025?",
]


def report_extract(seed: int = 7) -> str:
    """A fixed synthetic income statement and balance sheet, about 1,800 Qwen tokens long."""
    rng = random.Random(seed)
    lines = [
        "Example Bank PLC (fictional) - Annual Report 2025 - Extract",
        "Statement of profit or loss and financial position. All figures in Rs. '000 unless stated.",
        "",
        "| Item | Group 2025 | Group 2024 | Bank 2025 | Bank 2024 |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for metric in METRICS:
        if metric.startswith("Earnings per share"):
            g25, g24 = round(rng.uniform(8, 30), 2), round(rng.uniform(8, 30), 2)
            b25, b24 = round(g25 * 0.9, 2), round(g24 * 0.9, 2)
            cells = [f"{v:.2f}" for v in (g25, g24, b25, b24)]
        else:
            g25 = rng.randint(2_000_000, 400_000_000)
            g24 = int(g25 * rng.uniform(0.82, 1.12))
            b25, b24 = int(g25 * rng.uniform(0.85, 0.95)), int(g24 * rng.uniform(0.85, 0.95))
            cells = [f"{v:,}" for v in (g25, g24, b25, b24)]
        lines.append(f"| {metric} | " + " | ".join(cells) + " |")
    lines += [
        "",
        "Notes: The Group comprises the Bank and its subsidiaries. Comparative figures for 2024 have not been restated.",
        "Earnings per share is stated in rupees. The financial year ends on 31 December.",
    ]
    narrative = (
        "Management commentary: Net interest income grew on the back of loan book expansion, while impairment "
        "charges moderated as asset quality improved. Operating expenses rose with wage revisions and investment "
        "in digital channels. The Group maintained capital ratios above regulatory minimums throughout the year. "
    )
    return "\n".join(lines) + "\n\n" + narrative * 6


# ---------------------------------------------------------------------------
# llama.cpp setup
# ---------------------------------------------------------------------------


def download(url: str, dest: Path) -> None:
    print(f"Downloading {url}")
    with urllib.request.urlopen(url) as response, open(dest, "wb") as out:
        shutil.copyfileobj(response, out)


def find_server(root: Path) -> Path | None:
    for path in root.rglob("llama-server"):
        if path.is_file():
            return path
    return None


def library_env(server: Path) -> dict:
    env = os.environ.copy()
    lib_dirs = {str(p.parent) for p in server.parent.parent.rglob("*.so*")} | {str(server.parent)}
    env["LD_LIBRARY_PATH"] = ":".join(sorted(lib_dirs) + [env.get("LD_LIBRARY_PATH", "")])
    return env


def server_sees_gpu(server: Path) -> tuple[bool, str]:
    proc = subprocess.run([str(server), "--list-devices"], capture_output=True, text=True, env=library_env(server))
    output = (proc.stdout + proc.stderr)[-1500:]
    return proc.returncode == 0 and "CUDA0" in output, output


def compute_capability() -> str:
    lines = nvidia_smi("compute_cap")
    return lines[0].replace(".", "") if lines else "75"


def unpack(name: str, into: Path) -> None:
    archive = into / name
    if not archive.exists():
        download(f"{RELEASE_URL}/{name}", archive)
    with tarfile.open(archive) as tar:
        tar.extractall(into)


def prepare_llama(workdir: Path) -> dict:
    """Return {'server': path, 'how': 'prebuilt'|'prebuilt+cudart'|'source', 'seconds': n, 'notes': ...}."""
    started = time.perf_counter()
    prebuilt_dir = workdir / f"llama-{LLAMA_TAG}-prebuilt"
    notes = []
    try:
        prebuilt_dir.mkdir(parents=True, exist_ok=True)
        unpack(PREBUILT, prebuilt_dir)
        server = find_server(prebuilt_dir)
        if server is None:
            raise OSError("prebuilt archive had no llama-server")
        server.chmod(0o755)
        for how in ("prebuilt", "prebuilt+cudart"):
            if how == "prebuilt+cudart":
                unpack(CUDART, prebuilt_dir)
            ok, output = server_sees_gpu(server)
            if ok:
                return {"server": server, "how": how, "seconds": round(time.perf_counter() - started, 1), "notes": notes}
            notes.append(f"{how} did not see the GPU: {output[-300:]}")
    except (urllib.error.URLError, tarfile.TarError, OSError) as err:
        notes.append(f"prebuilt failed: {err}")
    print("\n".join(notes))

    print("Building llama.cpp from source (one time; roughly 10-30 minutes)...")
    src = workdir / f"llama.cpp-{LLAMA_TAG}"
    if not src.exists():
        subprocess.check_call(
            ["git", "clone", "--depth", "1", "--branch", LLAMA_TAG, "https://github.com/ggml-org/llama.cpp", str(src)]
        )
    subprocess.check_call(
        [
            "cmake", "-S", str(src), "-B", str(src / "build"), "-DGGML_CUDA=ON", "-DLLAMA_CURL=OFF",
            f"-DCMAKE_CUDA_ARCHITECTURES={compute_capability()}", "-DCMAKE_BUILD_TYPE=Release",
        ]
    )
    subprocess.check_call(
        ["cmake", "--build", str(src / "build"), "--config", "Release", "-j", str(os.cpu_count() or 4), "--target", "llama-server"]
    )
    server = find_server(src / "build")
    if server is None:
        raise RuntimeError("source build finished but llama-server was not found")
    return {"server": server, "how": "source", "seconds": round(time.perf_counter() - started, 1), "notes": notes}


# ---------------------------------------------------------------------------
# Running the server and timing answers
# ---------------------------------------------------------------------------


class LlamaServer:
    def __init__(self, server: Path, model_path: str, port: int, ctx: int, slots: int, log_path: Path):
        args = [
            str(server), "-m", model_path, "--host", "127.0.0.1", "--port", str(port),
            "-ngl", "all", "-c", str(ctx * slots), "-np", str(slots), "--jinja", "--no-webui",
        ]
        env = library_env(server)
        env["CUDA_VISIBLE_DEVICES"] = "0"  # time one GPU, as the budget assumes
        self.log_path = log_path
        self.log = open(log_path, "w", encoding="utf-8")
        self.proc = subprocess.Popen(args, stdout=self.log, stderr=subprocess.STDOUT, env=env)
        self.url = f"http://127.0.0.1:{port}"

    def wait_ready(self, timeout: int = 900) -> float:
        started = time.perf_counter()
        while time.perf_counter() - started < timeout:
            if self.proc.poll() is not None:
                raise RuntimeError(f"llama-server exited: {self.log_tail()}")
            try:
                with urllib.request.urlopen(f"{self.url}/health", timeout=5) as r:
                    if r.status == 200:
                        return time.perf_counter() - started
            except (urllib.error.URLError, ConnectionError, TimeoutError):
                pass
            time.sleep(2)
        raise RuntimeError("llama-server did not become ready in time")

    def log_tail(self, chars: int = 1500) -> str:
        self.log.flush()
        return self.log_path.read_text(encoding="utf-8", errors="replace")[-chars:]

    def chat(self, question: str, extract: str, sampling: dict, seed: int, max_tokens: int) -> dict:
        body = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"{extract}\n\nQuestion: {question}"},
            ],
            "max_tokens": max_tokens,
            "seed": seed,
            "cache_prompt": False,
            "chat_template_kwargs": {"enable_thinking": False},
            **sampling,
        }
        request = urllib.request.Request(
            f"{self.url}/v1/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        started = time.perf_counter()
        with urllib.request.urlopen(request, timeout=600) as r:
            reply = json.loads(r.read())
        message = reply["choices"][0]["message"]
        content = message.get("content") or ""
        return {
            "seconds": time.perf_counter() - started,
            "timings": reply.get("timings", {}),
            "content": content,
            "thinking_leak": bool(message.get("reasoning_content"))
            or any(tag in content for tag in ("<think>", "<|channel>", "<|think|>")),
        }

    def stop(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


def time_model(name: str, server_bin: Path, model_path: str, args, extract: str, port: int, workdir: Path) -> dict:
    spec = MODELS[name]
    record: dict = {"model": name, "repo": spec["repo"], "file": spec["file"], "sampling": spec["sampling"]}
    questions = QUESTIONS[: args.questions]

    server = LlamaServer(server_bin, model_path, port, args.ctx, 1, workdir / f"server-{name}-1.log")
    try:
        record["load_seconds"] = round(server.wait_ready(), 1)
        server.chat(questions[0], extract, spec["sampling"], args.seed, 16)  # warm-up, not timed
        record["vram_after_load"] = nvidia_smi("memory.used")
        answers = [server.chat(q, extract, spec["sampling"], args.seed, args.max_tokens) for q in questions]
    except Exception as err:
        record["error"] = f"{err} | {server.log_tail(800)}"
        server.stop()
        return record
    server.stop()

    seconds = [a["seconds"] for a in answers]
    record["sequential"] = {
        "answers": len(answers),
        "mean_seconds_per_answer": round(statistics.mean(seconds), 2),
        "prompt_tokens_mean": round(statistics.mean(a["timings"].get("prompt_n", 0) for a in answers)),
        "output_tokens_mean": round(statistics.mean(a["timings"].get("predicted_n", 0) for a in answers)),
        "prompt_tokens_per_second": round(statistics.mean(a["timings"].get("prompt_per_second", 0) for a in answers), 1),
        "output_tokens_per_second": round(statistics.mean(a["timings"].get("predicted_per_second", 0) for a in answers), 1),
        "answers_per_gpu_hour": round(3600 / statistics.mean(seconds)),
        "thinking_leaks": sum(a["thinking_leak"] for a in answers),
        "sample_answers": [a["content"][:400] for a in answers[:3]],
    }

    if args.parallel > 1:
        server = LlamaServer(server_bin, model_path, port, args.ctx, args.parallel, workdir / f"server-{name}-{args.parallel}.log")
        try:
            server.wait_ready()
            jobs = [questions[i % len(questions)] for i in range(args.parallel * 2)]
            started = time.perf_counter()
            with cf.ThreadPoolExecutor(max_workers=args.parallel) as pool:
                done = list(
                    pool.map(lambda q: server.chat(q, extract, spec["sampling"], args.seed, args.max_tokens), jobs)
                )
            wall = time.perf_counter() - started
            record["parallel"] = {
                "slots": args.parallel,
                "answers": len(done),
                "wall_seconds": round(wall, 1),
                "answers_per_gpu_hour": round(3600 * len(done) / wall),
                "thinking_leaks": sum(a["thinking_leak"] for a in done),
            }
        except Exception as err:
            record["parallel"] = {"slots": args.parallel, "error": f"{err}"[:600]}
        finally:
            server.stop()

    best = max(
        record["sequential"]["answers_per_gpu_hour"],
        record.get("parallel", {}).get("answers_per_gpu_hour", 0),
    )
    record["best_answers_per_gpu_hour"] = best
    record["gpu_hours_for_460_answers"] = round(460 / best, 2)  # 920 answers in total, half per generator
    return record


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--models", default="qwen,gemma")
    parser.add_argument("--questions", type=int, default=len(QUESTIONS))
    parser.add_argument("--max-tokens", type=int, default=300)
    parser.add_argument("--ctx", type=int, default=6144, help="context tokens per slot")
    parser.add_argument("--parallel", type=int, default=4, help="slots for the concurrency test; 1 skips it")
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--workdir", default="llama_work")
    parser.add_argument("--llama-server", help="path to an existing llama-server binary; skips download and build")
    parser.add_argument("--dry-run", action="store_true", help="print the prompt and settings; download nothing")
    args = parser.parse_args()
    names = args.models.split(",")
    extract = report_extract()

    if args.dry_run:
        print(extract[:1200] + "\n...")
        print(f"\nExtract: {len(extract):,} characters (about 1,800 tokens with the Qwen tokenizer)")
        print(json.dumps({n: MODELS[n] for n in names}, indent=2))
        print(f"llama.cpp {LLAMA_TAG}; questions: {args.questions}; parallel slots: {args.parallel}")
        return
    if not sys.platform.startswith("linux"):
        raise SystemExit("This pilot runs on Linux (Kaggle or Colab). Use --dry-run elsewhere.")
    if not nvidia_smi():
        raise SystemExit("No GPU found. Turn on a GPU accelerator.")

    from huggingface_hub import hf_hub_download

    started = time.perf_counter()
    workdir = Path(args.workdir)
    workdir.mkdir(exist_ok=True)
    result: dict = {"pilot": "generation", "settings": vars(args), "environment": environment(), "llama_cpp_tag": LLAMA_TAG}
    if args.llama_server:
        llama = {"server": Path(args.llama_server), "how": "given", "seconds": 0}
    else:
        llama = prepare_llama(workdir)
    result["llama_cpp"] = {k: str(v) for k, v in llama.items()}
    print(f"llama.cpp ready ({llama['how']}, {llama['seconds']} s)")

    result["models"] = []
    for i, name in enumerate(names):
        spec = MODELS[name]
        dl_start = time.perf_counter()
        model_path = hf_hub_download(spec["repo"], spec["file"])
        record = time_model(name, Path(llama["server"]), model_path, args, extract, 8080 + i, workdir)
        record["download_seconds"] = round(time.perf_counter() - dl_start, 1)
        result["models"].append(record)
        print(json.dumps({k: v for k, v in record.items() if k != "sequential"}, default=str)[:800])

    script_seconds = time.perf_counter() - started
    result["script_seconds"] = round(script_seconds, 1)
    ok = [m for m in result["models"] if "best_answers_per_gpu_hour" in m]
    result["gpu_hours_for_all_920_answers"] = round(sum(m["gpu_hours_for_460_answers"] for m in ok), 2) if ok else None

    print("\nSUMMARY")
    for m in result["models"]:
        if "error" in m:
            print(f"{m['model']:6s} ERROR {m['error'][:300]}")
            continue
        seq = m["sequential"]
        print(
            f"{m['model']:6s} {seq['mean_seconds_per_answer']} s/answer  prompt {seq['prompt_tokens_per_second']} tok/s  "
            f"output {seq['output_tokens_per_second']} tok/s  best {m['best_answers_per_gpu_hour']} answers/GPU-hour  "
            f"thinking leaks {seq['thinking_leaks']}"
        )
    print(f"Projected GPU hours for all 920 answers: {result['gpu_hours_for_all_920_answers']}")
    outcome = "PASS" if len(ok) == len(names) else "PARTIAL"
    write_result("generation", result)
    print_gpu_log_row("generation pilot", script_seconds / 3600, outcome, f"llama.cpp {llama['how']}; models {' '.join(names)}")


if __name__ == "__main__":
    main()
