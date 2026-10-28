"""Fetch the trained models for the live demo into data/demo-models/ (gitignored). Needs the internet once.

    .venv\\Scripts\\python demo\\fetch_models.py            # Channel A, the repair-v1 adapter and the Qwen3.5-2B base
    .venv\\Scripts\\python demo\\fetch_models.py --only channel-a

Channel A comes from the private Kaggle dataset faithguard-detector-models, whose file names are the
model folder flattened with "__" (as notebooks/build.py rebuilds it on Kaggle); the adapter from the
repair_v1 notebook's output; the base model from Hugging Face. Uses the Kaggle CLI and token of
pilots/kaggle_run.py.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilots"))
MODELS = ROOT / "data" / "demo-models"
CHANNEL_A_FILES = ["channel_a.json", "slot_head.pt", "encoder__config.json", "encoder__tokenizer.json",
                   "encoder__tokenizer_config.json", "encoder__model.safetensors"]


def unflatten(download: Path, prefix: str, target: Path) -> None:
    """channel-a__model__encoder__config.json -> target/encoder/config.json"""
    for flat in download.glob(f"{prefix}__*"):
        if flat.name.endswith(".kaggle-partial"):
            continue
        dest = target.joinpath(*flat.name[len(prefix) + 2:].split("__"))
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(flat), dest)


def channel_a(user: str) -> None:
    from kaggle_run import kaggle

    download = MODELS / "channel-a-download"
    download.mkdir(parents=True, exist_ok=True)
    for name in CHANNEL_A_FILES:
        if not (download / f"channel-a__model__{name}").exists():
            kaggle("datasets", "download", f"{user}/faithguard-detector-models", "-f", f"channel-a__model__{name}", "-p", str(download))
    unflatten(download, "channel-a__model", MODELS / "channel-a" / "model")
    shutil.rmtree(download, ignore_errors=True)
    print("Channel A ->", MODELS / "channel-a" / "model")


def adapter(user: str) -> None:
    from kaggle_run import kaggle

    download = MODELS / "repair-v1-download"
    kaggle("kernels", "output", f"{user}/faithguard-repair-v1", "-p", str(download), "--file-pattern", r"repair-v1/adapter/[^/]+$")
    target = MODELS / "repair-v1" / "adapter"
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(download / "outputs" / "repair-v1" / "adapter"), target)
    shutil.rmtree(download, ignore_errors=True)
    print("repair-v1 adapter ->", target)


def base_model() -> None:
    from huggingface_hub import snapshot_download

    from models import BASE_MODEL

    print(BASE_MODEL, "->", snapshot_download(BASE_MODEL))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=["channel-a", "adapter", "base"])
    args = parser.parse_args(argv)
    from kaggle_run import username

    user = username() if args.only in (None, "channel-a", "adapter") else ""
    if args.only in (None, "channel-a"):
        channel_a(user)
    if args.only in (None, "adapter"):
        adapter(user)
    if args.only in (None, "base"):
        base_model()


if __name__ == "__main__":
    main()
