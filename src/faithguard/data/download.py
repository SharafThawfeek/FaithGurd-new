"""Download the public datasets and record exactly what was downloaded.

Each file's URL, size and SHA-256 go into manifests/datasets.json (committed), so
every member can check they hold identical data. The files themselves stay out
of git, under data/raw/.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

SOURCES = {
    "finqa": {
        "licence": "MIT",
        "homepage": "https://github.com/czyssrs/FinQA",
        "files": {f"{s}.json": f"https://raw.githubusercontent.com/czyssrs/FinQA/main/dataset/{s}.json" for s in ("train", "dev", "test")},
    },
    "tatqa": {
        "licence": "CC BY 4.0 (data); MIT (code)",
        "homepage": "https://github.com/NExTplusplus/TAT-QA",
        "files": {
            f"tatqa_dataset_{s}.json": f"https://raw.githubusercontent.com/NExTplusplus/TAT-QA/master/dataset_raw/tatqa_dataset_{s}.json"
            for s in ("train", "dev", "test_gold")
        },
    },
    "ragtruth": {
        "licence": "MIT",
        "homepage": "https://github.com/ParticleMedia/RAGTruth",
        "files": {f"{s}.jsonl": f"https://raw.githubusercontent.com/ParticleMedia/RAGTruth/main/dataset/{s}.jsonl" for s in ("response", "source_info")},
    },
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def download(name: str, root: str | Path = "data/raw", manifest: str | Path = "manifests/datasets.json") -> dict:
    spec = SOURCES[name]
    folder = Path(root) / name
    folder.mkdir(parents=True, exist_ok=True)
    entry = {"licence": spec["licence"], "homepage": spec["homepage"], "files": {}}
    for filename, url in spec["files"].items():
        path = folder / filename
        if not path.exists():
            with urllib.request.urlopen(url) as response, open(path, "wb") as out:
                shutil.copyfileobj(response, out)
        entry["files"][filename] = {"url": url, "bytes": path.stat().st_size, "sha256": sha256(path)}
    entry["recorded"] = dt.date.today().isoformat()
    manifest = Path(manifest)
    manifest.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(manifest.read_text(encoding="utf-8")) if manifest.exists() else {}
    previous = data.get(name, {}).get("files", {})
    for filename, info in entry["files"].items():
        if filename in previous and previous[filename]["sha256"] != info["sha256"]:
            raise RuntimeError(f"{name}/{filename} differs from the recorded copy; check before overwriting the manifest")
    data[name] = entry
    manifest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return entry
