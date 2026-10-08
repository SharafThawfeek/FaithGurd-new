"""Shared helpers for the phase-1 GPU pilots.

Each pilot records the machine it ran on, times itself, and writes one JSON
result file plus a ready-to-paste row for logs/gpu-hours.csv.
"""

from __future__ import annotations

import datetime as dt
import importlib.metadata as md
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

RESULTS_DIR = Path(os.environ.get("FG_RESULTS_DIR", "results"))

PACKAGES = (
    "torch",
    "transformers",
    "peft",
    "accelerate",
    "bitsandbytes",
    "huggingface_hub",
    "lettucedetect",
    "flash-linear-attention",
    "triton",
)


def detect_platform() -> str:
    if os.environ.get("KAGGLE_KERNEL_RUN_TYPE") or Path("/kaggle").exists():
        return "kaggle"
    if os.environ.get("COLAB_RELEASE_TAG") or "google.colab" in sys.modules:
        return "colab"
    return "local"


def package_version(name: str) -> str | None:
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


def nvidia_smi(query: str = "name,memory.total,memory.used,driver_version") -> list[str]:
    if not shutil.which("nvidia-smi"):
        return []
    out = subprocess.run(
        ["nvidia-smi", f"--query-gpu={query}", "--format=csv,noheader"],
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in out.stdout.splitlines() if line.strip()]


def environment() -> dict:
    """Describe the machine, so every result can be traced to its hardware and versions."""
    info: dict = {
        "platform": detect_platform(),
        "python": sys.version.split()[0],
        "os": platform.platform(),
        "started_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "nvidia_smi": nvidia_smi(),
        "packages": {name: package_version(name) for name in PACKAGES},
        "gpus": [],
    }
    try:
        import torch
    except ImportError:
        return info
    info["torch_cuda"] = torch.version.cuda
    if torch.cuda.is_available():
        for i in range(torch.cuda.device_count()):
            props = torch.cuda.get_device_properties(i)
            info["gpus"].append(
                {
                    "name": props.name,
                    "memory_gb": round(props.total_memory / 2**30, 2),
                    "compute_capability": f"{props.major}.{props.minor}",
                    # The T4 (7.5) and P100 (6.0) have no native bf16; that is why the pilots use fp16.
                    "native_bf16": props.major >= 8,
                }
            )
    return info


def gpu_name() -> str:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except ImportError:
        pass
    return "cpu"


class Stopwatch:
    def __enter__(self) -> "Stopwatch":
        self.start = time.perf_counter()
        self.seconds = 0.0
        return self

    def __exit__(self, *exc) -> None:
        self.seconds = time.perf_counter() - self.start


def write_result(name: str, result: dict) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = RESULTS_DIR / f"{name}-{stamp}.json"
    path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"\nResult written to {path}")
    return path


def print_gpu_log_row(task: str, script_hours: float, outcome: str, notes: str) -> None:
    """Print a row for logs/gpu-hours.csv.

    Kaggle and Colab charge for the whole session while a GPU is attached, so the
    member replaces script_hours with the session hours shown by the platform.
    """
    date = dt.date.today().isoformat()
    notes = notes.replace(",", ";")
    print("\nRow for logs/gpu-hours.csv (fill in member and account; use the session hours the platform shows):")
    print(f"{date},<member>,<account>,{detect_platform()},{gpu_name()},1,{task},{script_hours:.2f},{outcome},{notes}")


def pip_install(*requirements: str) -> None:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", *requirements])
