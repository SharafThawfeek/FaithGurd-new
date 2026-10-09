"""Run the pilot notebooks on Kaggle from the command line and collect their results.

Needs the Kaggle CLI (kaggle 2.2.4) and an API token in ~/.kaggle/access_token
(kaggle.com, Settings, API Tokens). The account must be phone-verified: otherwise
Kaggle accepts the notebooks but runs them with no GPU and no internet.

    python pilots/kaggle_run.py push      # all three pilots, as private notebooks on a T4
    python pilots/kaggle_run.py status
    python pilots/kaggle_run.py fetch     # result JSON files -> pilots/results/

Kaggle charges GPU time for the whole session, so take the hours for
logs/gpu-hours.csv from the notebook's page, not from the scripts.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
PILOTS = {
    "repair_pilot": "FaithGuard repair pilot",
    "detector_pilot": "FaithGuard detector pilot",
    "generation_pilot": "FaithGuard generation pilot",
}
RESULT_FILE = re.compile(r"^(repair|detector|generation)-(?!.*-tiny-).*\.json$")


def kaggle(*args: str, capture: bool = False) -> str:
    exe = Path(sys.executable).parent / ("kaggle.exe" if os.name == "nt" else "kaggle")
    command = [str(exe) if exe.exists() else "kaggle", *args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    out = subprocess.run(command, check=True, text=True, capture_output=capture, env=env, encoding="utf-8")
    return out.stdout if capture else ""


def username() -> str:
    for line in kaggle("config", "view", capture=True).splitlines():
        if "username" in line:
            return line.split(":", 1)[1].strip()
    raise SystemExit("No Kaggle username found: check the API token in ~/.kaggle/")


def slug(user: str, name: str) -> str:
    return f"{user}/faithguard-{name.replace('_', '-')}"


def push(names: list[str]) -> None:
    user = username()
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            folder = Path(tmp) / name
            folder.mkdir()
            shutil.copy(HERE / "notebooks" / f"{name}.ipynb", folder / f"{name}.ipynb")
            metadata = {
                "id": slug(user, name),
                "title": PILOTS[name],
                "code_file": f"{name}.ipynb",
                "language": "python",
                "kernel_type": "notebook",
                "is_private": True,
                "enable_gpu": True,
                "enable_internet": True,
                "machine_shape": "NvidiaTeslaT4",
                "dataset_sources": [],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [],
            }
            (folder / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            kaggle("kernels", "push", "-p", str(folder))


def status(names: list[str]) -> None:
    user = username()
    for name in names:
        kaggle("kernels", "status", slug(user, name))


def fetch(names: list[str]) -> None:
    user = username()
    dest = HERE / "results"
    for name in names:
        with tempfile.TemporaryDirectory() as tmp:
            kaggle("kernels", "output", slug(user, name), "-p", tmp, "--file-pattern", r"\.json$", "-q")
            found = [p for p in Path(tmp).rglob("*.json") if RESULT_FILE.match(p.name)]
            for path in found:
                shutil.copy(path, dest / path.name)
                print(f"{name}: {path.name}")
            if not found:
                print(f"{name}: no result files (see the log on the notebook's Kaggle page)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["push", "status", "fetch"])
    parser.add_argument("pilots", nargs="*", help=f"any of {', '.join(PILOTS)} (default: all three)")
    args = parser.parse_args()
    names = args.pilots or list(PILOTS)
    unknown = set(names) - set(PILOTS)
    if unknown:
        parser.error(f"unknown pilot: {', '.join(sorted(unknown))}")
    {"push": push, "status": status, "fetch": fetch}[args.action](names)


if __name__ == "__main__":
    main()
