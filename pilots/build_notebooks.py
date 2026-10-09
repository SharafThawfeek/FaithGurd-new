"""Build one self-contained Kaggle/Colab notebook per pilot.

Each notebook installs the pinned GPU packages, writes the pilot scripts to disk
with %%writefile, runs them, and prints a summary. The .py files stay the single
source of truth: edit them, then run this script again.

    python pilots/build_notebooks.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "notebooks"

KAGGLE_STEPS = """**On Kaggle:** Create → New Notebook → File → Import Notebook → choose this file. In the right-hand panel set
*Accelerator* to **GPU T4 x2** and switch *Internet* **on** (needs a phone-verified account). Then *Run All*.

**On Colab:** File → Upload notebook. Runtime → Change runtime type → **T4 GPU**. Then Runtime → Run all.

**Afterwards:**
1. Download the `results` folder (Kaggle: *Output* panel; Colab: *Files* panel) and add the JSON files to `pilots/results/` in the repository.
2. Add a row to `logs/gpu-hours.csv`, using the **session hours the platform shows**, not just the script time.
3. Record the outcome in `docs/decision-log.md`."""

SUMMARY_CELL = '''import glob, json
for path in sorted(glob.glob("results/*.json")):
    r = json.load(open(path))
    print(f"\\n== {path}")
    if r["pilot"] == "repair_lora":
        t = r.get("training", {})
        print(r["verdict"], r.get("reasons"), "| kernels:", r["kernels"]["gated_delta_rule"])
        print("tokens/s", t.get("tokens_per_second"), "| GPU-h per 1M tokens", t.get("gpu_hours_per_million_tokens"),
              "| peak GB", r.get("peak_memory_gb"), "| skipped steps", t.get("skipped_steps"))
    elif r["pilot"] == "detector":
        for run in r["runs"]:
            print(run["model"], run["seq_len"], run["verdict"], "| batch", run["largest_batch"],
                  "| tokens/s", run.get("tokens_per_second"), "| GPU-h per 1M tokens", run.get("gpu_hours_per_million_tokens"),
                  "| peak GB", run.get("peak_memory_gb"))
        for name, check in r["inference"].items():
            print("inference", name, "ok" if check.get("ok") else check.get("error"))
    elif r["pilot"] == "generation":
        for m in r["models"]:
            print(m["model"], m.get("error") or f"{m['best_answers_per_gpu_hour']} answers per GPU hour")
        print("GPU hours for all 920 answers:", r.get("gpu_hours_for_all_920_answers"))'''

PILOTS = {
    "repair_pilot": {
        "title": "FaithGuard phase-1 repair pilot",
        "owner": "M.S.A Ahamed",
        "about": (
            "Can a free T4 fine-tune Qwen3.5-2B with LoRA? Four short runs: fp16 LoRA at 1,024 and 2,048 tokens, "
            "QLoRA with fp32 maths, and fp16 with the fast linear-attention kernels. Each prints PASS or FAIL with "
            "reasons, tokens per second, GPU hours per million training tokens and peak memory. "
            "The verdicts decide where to start on the fallback chain (decision D-003). Expect about 30-45 minutes."
        ),
        "scripts": ["common.py", "repair_lora_pilot.py"],
        "runs": [
            ("Run 1: fp16 LoRA, 1,024 tokens", "!python repair_lora_pilot.py --mode fp16 --seq-len 1024"),
            ("Run 2: fp16 LoRA, 2,048 tokens", "!python repair_lora_pilot.py --mode fp16 --seq-len 2048"),
            ("Run 3: QLoRA with fp32 maths, 1,024 tokens", "!python repair_lora_pilot.py --mode qlora --seq-len 1024"),
            (
                "Run 4: fp16 with the fast linear-attention kernels. These may not run on a T4; a failure here is a "
                "result to record, not a problem to fix.",
                "!pip install -q flash-linear-attention==0.5.2\n"
                "!python repair_lora_pilot.py --mode fp16 --seq-len 1024 --tag fla",
            ),
        ],
    },
    "detector_pilot": {
        "title": "FaithGuard phase-1 detector pilot",
        "owner": "M.L Ahamed",
        "about": (
            "Which LettuceDetect encoder should Channel A start from? Fine-tunes both candidates "
            "(v1 ModernBERT-large and v2 mmBERT-base) in fp16 with gradient checkpointing at 1,024 and 2,048 tokens, "
            "finds the largest batch that fits, and checks that both released checkpoints run through the pinned "
            "lettucedetect package. Expect about 20-30 minutes."
        ),
        "scripts": ["common.py", "detector_pilot.py"],
        "runs": [("Both encoders, both sequence lengths", "!python detector_pilot.py")],
    },
    "generation_pilot": {
        "title": "FaithGuard phase-1 generation pilot",
        "owner": "Sharaf",
        "about": (
            "How many answers per GPU hour can a free T4 produce? Downloads llama.cpp (release b11490) and both "
            "generators at 4-bit (12.7 GB in total), times eight realistic questions per model one at a time and "
            "four at once, and projects the GPU hours for all 920 answers. Expect about 45-75 minutes, more if "
            "llama.cpp has to be built from source."
        ),
        "scripts": ["common.py", "generation_pilot.py"],
        "runs": [("Both generators", "!python generation_pilot.py")],
    },
}


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


def markdown(text: str) -> dict:
    return {"cell_type": "markdown", "metadata": {}, "source": lines(text)}


def code(text: str) -> dict:
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": lines(text)}


def setup_cell() -> str:
    requirements = [
        line.strip()
        for line in (ROOT / "requirements" / "gpu.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    return (
        "# Setup: pinned GPU packages (requirements/gpu.txt) and a look at the GPU.\n"
        + SESSION_CHECK
        + "import subprocess, sys\n"
        f"REQUIREMENTS = {requirements!r}\n"
        'subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *REQUIREMENTS])\n'
        '!nvidia-smi --query-gpu=name,memory.total,driver_version,compute_cap --format=csv'
    )


def build(name: str, spec: dict) -> Path:
    cells = [
        markdown(f"# {spec['title']}\n\n**Run by:** {spec['owner']}\n\n{spec['about']}\n\n{KAGGLE_STEPS}"),
        code(setup_cell()),
    ]
    for script in spec["scripts"]:
        source = (HERE / script).read_text(encoding="utf-8")
        cells.append(code(f"%%writefile {script}\n{source}"))
    for title, command in spec["runs"]:
        cells.append(markdown(f"## {title}"))
        cells.append(code(command))
    cells.append(markdown("## Summary of every result in this session"))
    cells.append(code(SUMMARY_CELL))

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
    OUT.mkdir(exist_ok=True)
    path = OUT / f"{name}.ipynb"
    path.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_setup_cell() -> Path:
    """The same first cell, kept as a file so every future notebook starts identically."""
    path = ROOT / "setup" / "setup_cell.py"
    path.parent.mkdir(exist_ok=True)
    header = (
        "# Paste this as the first cell of every FaithGuard Kaggle or Colab notebook.\n"
        "# Generated from requirements/gpu.txt by pilots/build_notebooks.py; do not edit by hand.\n"
    )
    path.write_text(header + setup_cell() + "\n", encoding="utf-8")
    return path


if __name__ == "__main__":
    for name, spec in PILOTS.items():
        print("wrote", build(name, spec).relative_to(ROOT))
    print("wrote", write_setup_cell().relative_to(ROOT))
