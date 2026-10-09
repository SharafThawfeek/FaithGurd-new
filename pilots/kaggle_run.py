"""Run the GPU notebooks on Kaggle from the command line and collect their results.

Needs the Kaggle CLI (kaggle 2.2.4) and an API token in ~/.kaggle/access_token
(kaggle.com, Settings, API Tokens). The account must be phone-verified: otherwise
Kaggle accepts the notebooks but runs them with no GPU and no internet.

    python pilots/kaggle_run.py push      # the three phase-1 pilots, as private notebooks on a T4
    python pilots/kaggle_run.py status
    python pilots/kaggle_run.py fetch     # result JSON files -> pilots/results/

The pilot answers: upload the built questions as a private dataset (never the gold
store), run the generation notebook with it attached, then collect the answers:

    python pilots/kaggle_run.py dataset faithguard-benchmark data/benchmark-build/questions.jsonl
    python pilots/kaggle_run.py push generate_answers --dataset faithguard-benchmark
    python pilots/kaggle_run.py fetch generate_answers   # answers-*.jsonl -> data/benchmark-build/

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
ROOT = HERE.parent
# name -> (folder holding the notebook, Kaggle title, output file names to collect, where they go)
NOTEBOOKS = {
    "repair_pilot": (HERE / "notebooks", "FaithGuard repair pilot", r"repair-(?!.*-tiny-).*[.]json", HERE / "results"),
    "detector_pilot": (HERE / "notebooks", "FaithGuard detector pilot", r"detector-(?!tiny-).*[.]json", HERE / "results"),
    "generation_pilot": (HERE / "notebooks", "FaithGuard generation pilot", r"generation-.*[.]json", HERE / "results"),
    "generate_answers": (ROOT / "notebooks", "FaithGuard answer generation", r"answers-.*[.]jsonl", ROOT / "data" / "benchmark-build"),
}
PILOTS = ["repair_pilot", "detector_pilot", "generation_pilot"]


def kaggle(*args: str, capture: bool = False, check: bool = True) -> str:
    exe = Path(sys.executable).parent / ("kaggle.exe" if os.name == "nt" else "kaggle")
    command = [str(exe) if exe.exists() else "kaggle", *args]
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}  # the CLI writes notebook logs in the default encoding
    out = subprocess.run(command, check=check, text=True, capture_output=capture, env=env, encoding="utf-8")
    return (out.stdout or "") + (out.stderr or "") if capture else ""


def username() -> str:
    for line in kaggle("config", "view", capture=True).splitlines():
        if "username" in line:
            return line.split(":", 1)[1].strip()
    raise SystemExit("No Kaggle username found: check the API token in ~/.kaggle/")


def slug(user: str, name: str) -> str:
    """The notebook's address, which Kaggle derives from its title ("FaithGuard answer generation" -> faithguard-answer-generation)."""
    return f"{user}/" + re.sub(r"[^a-z0-9]+", "-", NOTEBOOKS[name][1].lower()).strip("-")


def push(names: list[str], datasets: list[str]) -> None:
    user = username()
    with tempfile.TemporaryDirectory() as tmp:
        for name in names:
            folder = Path(tmp) / name
            folder.mkdir()
            source, title = NOTEBOOKS[name][:2]
            shutil.copy(source / f"{name}.ipynb", folder / f"{name}.ipynb")
            metadata = {
                "id": slug(user, name),
                "title": title,
                "code_file": f"{name}.ipynb",
                "language": "python",
                "kernel_type": "notebook",
                "is_private": True,
                "enable_gpu": True,
                "enable_internet": True,
                "machine_shape": "NvidiaTeslaT4",
                "dataset_sources": [d if "/" in d else f"{user}/{d}" for d in datasets],
                "competition_sources": [],
                "kernel_sources": [],
                "model_sources": [],
            }
            (folder / "kernel-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            kaggle("kernels", "push", "-p", str(folder))


def status(names: list[str]) -> None:
    user = username()
    for name in names:
        out = kaggle("kernels", "status", slug(user, name), capture=True, check=False).strip()
        print(out.splitlines()[-1] if out else f"{name}: no answer from Kaggle")


def fetch(names: list[str]) -> None:
    user = username()
    for name in names:
        pattern, dest = NOTEBOOKS[name][2:]
        dest.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            kaggle("kernels", "output", slug(user, name), "-p", tmp, "--file-pattern", f"(^|/){pattern}$", "--page-size", "200", "-q")
            found = [p for p in Path(tmp).rglob("*") if p.is_file() and re.fullmatch(pattern, p.name)]
            for path in found:
                shutil.copy(path, dest / path.name)
                print(f"{name}: {path.name} -> {dest}")
            if not found:
                print(f"{name}: no result files (see the log on the notebook's Kaggle page)")


def dataset(name: str, files: list[str]) -> None:
    """Upload files as a private Kaggle Dataset, or as a new version if it exists."""
    user = username()
    if any("gold" in Path(f).parts for f in files):
        raise SystemExit("The gold store never goes to the generators' datasets")
    with tempfile.TemporaryDirectory() as tmp:
        for f in files:
            shutil.copy(f, Path(tmp) / Path(f).name)
        meta = {"title": name.replace("-", " ").title(), "id": f"{user}/{name}", "licenses": [{"name": "other"}]}
        (Path(tmp) / "dataset-metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        exists = "ready" in kaggle("datasets", "status", f"{user}/{name}", capture=True, check=False).lower()
        if exists:
            kaggle("datasets", "version", "-p", tmp, "-m", "updated by pilots/kaggle_run.py")
        else:
            kaggle("datasets", "create", "-p", tmp)  # private unless --public is given


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("action", choices=["push", "status", "fetch", "dataset"])
    parser.add_argument("names", nargs="*", help=f"notebooks ({', '.join(NOTEBOOKS)}; default: the three pilots), "
                                                 "or for `dataset`: the dataset name, then its files")
    parser.add_argument("--dataset", action="append", default=[], help="push: attach this dataset (repeatable)")
    args = parser.parse_args()
    if args.action == "dataset":
        if len(args.names) < 2:
            parser.error("dataset needs a name and at least one file")
        dataset(args.names[0], args.names[1:])
        return
    names = args.names or PILOTS
    unknown = set(names) - set(NOTEBOOKS)
    if unknown:
        parser.error(f"unknown notebook: {', '.join(sorted(unknown))}")
    if args.action == "push":
        push(names, args.dataset)
    else:
        {"status": status, "fetch": fetch}[args.action](names)


if __name__ == "__main__":
    main()
