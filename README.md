# FaithGuard

FaithGuard checks each AI answer about a financial report before it reaches the user, then sends it, fixes it, or refuses with a reason. It is a three-member research project: detection (M.L Ahamed), repair (M.S.A Ahamed) and decision policy (Sharaf).

- **Research plan:** [docs/FaithGuard-Revised-Plan.md](docs/FaithGuard-Revised-Plan.md), covering what is built and why
- **Phase plan:** [docs/FaithGuard-Phase-Plan.md](docs/FaithGuard-Phase-Plan.md), covering what to do in what order; each phase ends at an exit checklist
- **Decision log:** [docs/decision-log.md](docs/decision-log.md) · **Risk register:** [docs/risk-register.md](docs/risk-register.md)

## Repository layout

| Path | What it holds |
| --- | --- |
| `docs/` | Plans, decision log, risk register, authorship order, adjudicator request, related-work tables, original component designs (`docs/components/`) |
| `pilots/` | Phase-1 GPU pilot scripts, their Kaggle/Colab notebooks (`pilots/notebooks/`) and results (`pilots/results/`) |
| `logs/` | GPU-hour log and each account's GPU quota |
| `requirements/` | Pinned packages: `laptop.lock.txt` for laptops, `gpu.txt` for Kaggle and Colab |
| `setup/setup_cell.py` | The first cell of every Kaggle or Colab notebook |
| `src/faithguard/` | Project code (from phase 2) |
| `tests/` | Tests, run with `pytest` |
| `data/` | Local data only; never committed (see `data/README.md`) |

## Setting up a laptop

Use Python 3.11. From the repository folder:

```bash
python -m venv .venv
```

Then install the locked packages. On Windows:

```bash
.venv\Scripts\python -m pip install -r requirements/laptop.lock.txt
```

On macOS or Linux:

```bash
.venv/bin/python -m pip install -r requirements/laptop.lock.txt
```

Check it works:

```bash
.venv/Scripts/python -m pytest
```

**Adding a package:** add it to `requirements/laptop.txt` with an exact version, reinstall, regenerate the lock with `pip freeze --exclude pip > requirements/laptop.lock.txt`, and log it in the decision log.

## Kaggle and Colab

Every notebook starts with `setup/setup_cell.py`, which installs `requirements/gpu.txt` and uses the platform's own torch. The pilot notebooks already include it. After changing `requirements/gpu.txt` or any pilot script, rebuild the notebooks:

```bash
python pilots/build_notebooks.py
```

**Working rules** (from the revised plan): keep runs to a few hours and save a checkpoint at least every hour; save every output as soon as a step finishes; use your own account only; log every GPU session in `logs/gpu-hours.csv` with the session hours the platform shows.

## Where outputs live

| What | Where |
| --- | --- |
| Code, small results (JSON, CSV), logs and documents | This repository |
| Large outputs: generated answers, checkpoints, model files | Private Kaggle Datasets named `faithguard-<what>-v<N>` (for example `faithguard-answers-v1`), shared with the other two members |
| Copies for Colab work | A shared Google Drive folder `FaithGuard/`, with the same names |
| Gold answers and labels | A separate private Kaggle Dataset `faithguard-gold-v<N>`, read only by evaluation code |
| Sri Lankan report PDFs | Shared Drive only; the public release holds questions, labels and page pointers (risk R-07) |

## Phase 1 status

Phase 1 ends when everything below is done (see the phase plan for the exit checklist).

| Task | Owner | State | Next step |
| --- | --- | --- | --- |
| Authorship order | All | Done: [docs/authorship.md](docs/authorship.md) | None |
| Adjudicator | All | Draft: [docs/drafts/adjudicator-request.md](docs/drafts/adjudicator-request.md) | Send to an accounting lecturer or senior student |
| Code repository and environment | Sharaf | Local repository and laptop lock file done | Push to a private GitHub repository; teammates install and run `pytest` |
| Output locations | Sharaf | Done (above) | None |
| GPU quota per account | Each member | Template: [logs/gpu-quota.csv](logs/gpu-quota.csv) | Record what Kaggle and Colab show for your account |
| Decision log and risk register | Sharaf | Started: 13 decisions, 14 risks | Review at each weekly check |
| Repair GPU pilot | M.S.A Ahamed | Notebook ready: [pilots/notebooks/repair_pilot.ipynb](pilots/notebooks/repair_pilot.ipynb) | Run on Kaggle; log the verdict against D-003 |
| Detector GPU pilot | M.L Ahamed | Notebook ready: [pilots/notebooks/detector_pilot.ipynb](pilots/notebooks/detector_pilot.ipynb) | Run on Kaggle; choose the warm-start checkpoint |
| Generation GPU pilot | Sharaf | Notebook ready: [pilots/notebooks/generation_pilot.ipynb](pilots/notebooks/generation_pilot.ipynb) | Run on Kaggle; update the GPU-hour budget |
| Closest prior work per paper | Each member | Tables: [docs/related-work/](docs/related-work/) | Open each work and fill in its row; M.L Ahamed reads the LettuceDetect v2 taxonomy head first (risk R-11) |

Each pilot script also has a CPU smoke-test mode (`--tiny`, or `--dry-run` for generation). All three were smoke-tested on a laptop on 2026-10-08. Only T4 runs count towards the budget.
