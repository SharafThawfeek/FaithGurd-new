"""The pilot notebooks must match the scripts and pinned packages they were built from.

If this fails, run `python pilots/build_notebooks.py` and commit the result.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NOTEBOOKS = sorted((ROOT / "pilots" / "notebooks").glob("*.ipynb"))


def cells(notebook: Path) -> list[str]:
    data = json.loads(notebook.read_text(encoding="utf-8"))
    return ["".join(cell["source"]) for cell in data["cells"] if cell["cell_type"] == "code"]


def test_notebooks_exist():
    assert {p.stem for p in NOTEBOOKS} == {"repair_pilot", "detector_pilot", "generation_pilot"}


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda p: p.stem)
def test_embedded_scripts_match_sources(notebook):
    for source in cells(notebook):
        match = re.match(r"%%writefile (\S+)\n", source)
        if match:
            script = ROOT / "pilots" / match.group(1)
            assert source[match.end() :] == script.read_text(encoding="utf-8"), f"{script.name} changed; rebuild"


@pytest.mark.parametrize("notebook", NOTEBOOKS, ids=lambda p: p.stem)
def test_setup_cell_pins_gpu_requirements(notebook):
    pinned = [
        line.strip()
        for line in (ROOT / "requirements" / "gpu.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    setup = cells(notebook)[0]
    assert f"REQUIREMENTS = {pinned!r}" in setup
