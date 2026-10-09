"""Build the phase-4 GPU notebooks (Kaggle or Colab). Each clones the repository, installs it,
downloads the data, runs one training or evaluation job, and leaves results in /kaggle/working/outputs.

    python notebooks/build.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPO = "https://github.com/SharafThawfeek/FaithGurd-new.git"

HOW_TO_RUN = """**On Kaggle:** Create → New Notebook → File → Import Notebook → this file. Settings: *Accelerator* **GPU T4 x2**, *Internet* **on**.
For long jobs use **Save Version → Save & Run All (Commit)**: it runs in the background for up to 12 hours and keeps everything in `/kaggle/working/outputs`.
To continue in a later notebook, add this notebook's output as input (*Add Input → Your Work*).

**Afterwards:** download `outputs/*/results.json` and `report.md` files into `runs/` in the repository, and log the session's GPU hours in `logs/gpu-hours.csv`. Checkpoints are saved regularly; re-running the same cell resumes from the latest one."""


SESSION_CHECK = """import shutil, socket
try:
    socket.gethostbyname("pypi.org")
except OSError:
    raise RuntimeError("No internet in this session. Kaggle: verify your phone number (Settings), then switch Internet on in the right-hand panel.")
if not shutil.which("nvidia-smi"):
    raise RuntimeError("No GPU in this session. Kaggle: verify your phone number (Settings), then set Accelerator to GPU T4 x2. Colab: Runtime > Change runtime type > T4 GPU.")
"""


def lines(text: str) -> list[str]:
    parts = text.split("\n")
    return [p + "\n" for p in parts[:-1]] + [parts[-1]]


def md(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": lines(text)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": lines(text)}


def setup_cell() -> str:
    requirements = [
        line.strip() for line in (ROOT / "requirements" / "gpu.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return (
        "# Setup: clone FaithGuard, install it with the pinned GPU packages, fetch the data.\n"
        + SESSION_CHECK
        + "import os, subprocess, sys\n"
        "WORK = '/kaggle/working' if os.path.exists('/kaggle') else '/content'\n"
        "os.chdir(WORK)\n"
        f"if not os.path.exists('faithguard'):\n    subprocess.check_call(['git', 'clone', '--depth', '1', '{REPO}', 'faithguard'])\n"
        "os.chdir('faithguard')\n"
        f"REQUIREMENTS = {requirements!r}\n"
        "subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', *REQUIREMENTS])\n"
        "subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', '-e', '.'])\n"
        "OUT = os.path.join(WORK, 'outputs'); os.makedirs(OUT, exist_ok=True)\n"
        "!faithguard data download all\n"
        "!nvidia-smi --query-gpu=name,memory.total --format=csv"
    )


GENERATE_START = """from pathlib import Path
from faithguard.generation import llama
SERVER = llama.prepare(os.path.join(WORK, 'llama_work'))   # pinned llama.cpp release; builds from source if needed
servers = {}
for i, name in enumerate(['qwen', 'gemma']):                # one model per T4
    servers[name] = llama.LlamaServer(SERVER, llama.model_path(name), port=8080 + i, gpu=str(i), log=f'{OUT}/server-{name}.log')
for name, s in servers.items():
    print(name, 'ready in', round(s.wait_ready()), 's')"""

GENERATE_RUN = """import threading
from faithguard.benchmark import BenchmarkQuestion
from faithguard.records import read_jsonl
from faithguard.generation.answers import generate_answers
from faithguard.generation.models import MODELS
questions = list(read_jsonl(QUESTIONS, BenchmarkQuestion))
print(len(questions), 'questions')
def run(name):
    n = generate_answers(questions, servers[name].url, name, MODELS[name]['sampling'], Path(OUT) / f'answers-{name}.jsonl')
    print(name, n, 'new answers')
threads = [threading.Thread(target=run, args=(n,)) for n in servers]
for t in threads: t.start()
for t in threads: t.join()"""

GENERATE_SUMMARY = """import json, statistics
for s in servers.values(): s.stop()
for name in servers:
    rows = [json.loads(l) for l in open(Path(OUT) / f'answers-{name}.jsonl', encoding='utf-8')]
    speed = [r['settings']['timings'].get('predicted_per_second', 0) for r in rows]
    print(name, len(rows), 'answers; thinking leaks:', sum(r['settings']['thinking_leak'] for r in rows),
          '; empty:', sum(not r['text'] for r in rows), '; median tokens/s:', round(statistics.median(speed), 1) if speed else '-')"""

NOTEBOOKS = {
    "generate_answers": {
        "title": "Generate benchmark answers with both generators",
        "about": "Answers every benchmark question once with Qwen3.5-9B and Gemma 4 12B (4-bit, llama.cpp, thinking off, fixed seed), "
                 "one model per T4, from the frozen evidence. Use the pilot questions first (60 questions, 120 answers), then the full set "
                 "after the pilot decisions. Re-running skips answers already written. Expect about 1 GPU hour for the pilot and 3-5 for the full set.",
        "cells": [
            ("Point to the built questions (a private Kaggle Dataset made from data/benchmark-build/, never the public repository)",
             "import glob\nQUESTIONS = sorted(glob.glob('/kaggle/input/**/questions.jsonl', recursive=True))[0]  # or set the path by hand\nprint(QUESTIONS)"),
            ("Start llama.cpp: one server per T4 (downloads 12.7 GB of model files the first time)", GENERATE_START),
            ("Generate with both models at once (resumable)", GENERATE_RUN),
            ("Stop the servers and summarise", GENERATE_SUMMARY),
        ],
    },
    "repair_sft": {
        "title": "Repair, stage A: fine-tune the edit-program repairer",
        "about": "Fine-tunes Qwen3.5-2B with LoRA to write edit programs (Stage A), then evaluates it on 500 development items "
                 "(correction rate, new errors, damage, valid programs). The `basis` error type is held out of training (RQ2). "
                 "Set MODE to 'qlora' if the phase-1 pilot said fp16 fails. Expect roughly 2-4 GPU hours.",
        "cells": [
            ("Training data from the controlled track (about 2 minutes on CPU)", "!faithguard sft --mode program"),
            ("Fine-tune (resumable)", "MODE = 'fp16'  # or 'qlora'\n!python -m faithguard.train.repair_sft --data runs/sft/repair-program-train.jsonl --out {OUT}/repair-sft --mode $MODE"),
            ("Evaluate the trained repairer", "!python -m faithguard.train.repair_eval --adapter {OUT}/repair-sft/adapter --load $MODE --out {OUT}/eval-repair-sft"),
        ],
    },
    "repair_baselines": {
        "title": "Repair baselines: free rewriting and zero-shot programs",
        "about": "The main comparison (RQ1): the same backbone fine-tuned to rewrite answers freely (FRED-style), then evaluated with the same "
                 "measures; plus zero-shot edit programs from the untrained backbone. Expect roughly 2-4 GPU hours.",
        "cells": [
            ("Training data for the rewrite baseline", "!faithguard sft --mode rewrite"),
            ("Fine-tune the rewrite baseline (resumable)", "MODE = 'fp16'\n!python -m faithguard.train.repair_sft --data runs/sft/repair-rewrite-train.jsonl --out {OUT}/rewrite-sft --mode $MODE"),
            ("Evaluate the rewrite baseline", "!python -m faithguard.train.repair_eval --mode rewrite --adapter {OUT}/rewrite-sft/adapter --load $MODE --out {OUT}/eval-rewrite-sft"),
            ("Zero-shot edit programs from the untrained backbone", "!python -m faithguard.train.repair_eval --load $MODE --out {OUT}/eval-zero-shot-2b"),
        ],
    },
    "repair_self_train": {
        "title": "Repair, stage B: executor-verified self-training",
        "about": "Starts from the Stage A adapter (add the repair_sft notebook's output as input and set ADAPTER), samples four programs per "
                 "item, keeps those the executor and gate accept, and fine-tunes again; two rounds, then evaluation. Expect roughly 6-10 GPU hours.",
        "cells": [
            ("Point to the Stage A adapter", "ADAPTER = '/kaggle/input/repair-sft/outputs/repair-sft/adapter'  # change to your input path\nMODE = 'fp16'\n!faithguard sft --mode program"),
            ("Self-training rounds (each round is saved; re-running skips finished rounds)", "!python -m faithguard.train.repair_self_train --adapter $ADAPTER --sft runs/sft/repair-program-train.jsonl --out {OUT}/self-train --mode $MODE --rounds 2"),
            ("Evaluate the final adapter", "import glob\nFINAL = sorted(glob.glob(OUT + '/self-train/round-*/adapter'))[-1]\n!python -m faithguard.train.repair_eval --adapter $FINAL --load $MODE --out {OUT}/eval-self-train"),
        ],
    },
    "detector_train": {
        "title": "Detection: train Channel A and its ablations",
        "about": "Trains the span head and relation-slot head on the LettuceDetect encoder chosen in the phase-1 pilot (set CHECKPOINT), "
                 "then the no-slot ablation, and evaluates both against Channel B on 2,000 development items. The repository ships the "
                 "XBRL-mined examples (runs/detector/xbrl.jsonl.gz, from `faithguard xbrl-mine`), so the no-XBRL ablation runs too. "
                 "Expect roughly 3-5 GPU hours.",
        "cells": [
            ("Training data (controlled track, RAGTruth and XBRL-mined examples)", "CHECKPOINT = 'KRLabsOrg/lettucedect-v2-mmbert-base'  # or KRLabsOrg/lettucedect-large-modernbert-en-v1\n!faithguard detector-data"),
            ("Channel A, full model", "!python -m faithguard.train.detector --data runs/detector/train.jsonl --checkpoint $CHECKPOINT --out {OUT}/channel-a"),
            ("Ablation: without the slot head", "!python -m faithguard.train.detector --data runs/detector/train.jsonl --checkpoint $CHECKPOINT --no-slot --out {OUT}/channel-a-noslot"),
            ("Ablation: without XBRL negatives (only if XBRL examples were mined)", "import os\nif os.path.exists('runs/detector/xbrl.jsonl') or os.path.exists('runs/detector/xbrl.jsonl.gz'):\n    !python -m faithguard.train.detector --data runs/detector/train.jsonl --checkpoint $CHECKPOINT --exclude xbrl --out {OUT}/channel-a-noxbrl"),
            ("Evaluate (also writes per-claim rows for the A+B fusion)", "!python -m faithguard.train.detector_eval --model-dir {OUT}/channel-a/model --out {OUT}/eval-channel-a\n!python -m faithguard.train.detector_eval --model-dir {OUT}/channel-a-noslot/model --out {OUT}/eval-channel-a-noslot"),
        ],
    },
    "detector_baselines": {
        "title": "Detection baselines: LettuceDetect, HHEM, Granite Guardian",
        "about": "Scores the released detectors on the same development items as Channel A: AUROC, false alarms on clean answers, "
                 "wrong-context recall. Granite Guardian (cut-list item 2) runs at 4-bit on 1,000 items. Expect roughly 2-4 GPU hours.",
        "cells": [
            ("LettuceDetect v1-large and v2 mmBERT", "!python -m faithguard.train.baseline_eval --detector lettuce-v1-large --out {OUT}/base-lettuce-v1\n!python -m faithguard.train.baseline_eval --detector lettuce-v2-mmbert --out {OUT}/base-lettuce-v2"),
            ("HHEM-2.1-Open", "!python -m faithguard.train.baseline_eval --detector hhem --out {OUT}/base-hhem"),
            ("Granite Guardian 4.1-8B (4-bit)", "!python -m faithguard.train.baseline_eval --detector granite --limit 1000 --out {OUT}/base-granite"),
        ],
    },
}


def build(name: str, spec: dict) -> Path:
    cells = [md(f"# {spec['title']}\n\n{spec['about']}\n\n{HOW_TO_RUN}"), code(setup_cell())]
    for title, command in spec["cells"]:
        cells.append(md(f"## {title}"))
        cells.append(code(command.replace("{OUT}", "{OUT}")))
    cells.append(md("## Results"))
    cells.append(code("import glob, json\nfor path in sorted(glob.glob(OUT + '/**/results.json', recursive=True)):\n    print(path)\n    print(json.dumps({k: v for k, v in json.load(open(path)).items() if k in ('summary', 'channel_a', 'channel_b', 'auroc', 'false_alarm_clean', 'wrong_context_recall')}, indent=1)[:1500])"))
    notebook = {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "accelerator": "GPU",
            "colab": {"gpuType": "T4", "provenance": []},
            "kaggle": {"accelerator": "nvidiaTeslaT4", "isGpuEnabled": True, "isInternetEnabled": True, "language": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    path = HERE / f"{name}.ipynb"
    path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    for name, spec in NOTEBOOKS.items():
        print("wrote", build(name, spec).relative_to(ROOT))
