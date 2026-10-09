# FaithGuard

FaithGuard checks each AI answer about a financial report before it reaches the user, then sends it, fixes it, or refuses with a reason. It is a three-part research project: detection (M.L Ahamed), repair (M.S.A Ahamed) and decision policy (Sharaf).

- **Research plan:** [docs/FaithGuard-Revised-Plan.md](docs/FaithGuard-Revised-Plan.md), covering what is built and why
- **Phase plan:** [docs/FaithGuard-Phase-Plan.md](docs/FaithGuard-Phase-Plan.md), covering what to do in what order; each phase ends at an exit checklist
- **Decision log:** [docs/decision-log.md](docs/decision-log.md) · **Risk register:** [docs/risk-register.md](docs/risk-register.md) · **Annotation guide (v2):** [docs/annotation-guide.md](docs/annotation-guide.md) · **Pre-registration (draft):** [docs/preregistration.md](docs/preregistration.md)

## How it works

```text
question + evidence + answer
  -> detect  (src/faithguard/detect)    every number traced to a cell, or the failing slot named
  -> decide  (src/faithguard/policy)    send, repair or abstain
  -> repair  (src/faithguard/repair)    COPY / CALCULATE edit program, run by the executor, checked by the hard gate
  -> output  (src/faithguard/pipeline.py)
```

Try the plan's worked example after running `faithguard slice` (see below):

```bash
faithguard trace --items runs/slice/items.jsonl --id "demo-lk-2:entity"
```

## Repository layout

| Path | What it holds |
| --- | --- |
| `src/faithguard/records.py` | Record format v1: items, evidence cells, detector output, decisions, edit programs, final outputs |
| `src/faithguard/gold.py` | The gold store (gold answers, labels, injections), kept apart from decision-time code |
| `src/faithguard/calc/` | Calculation API: numbers in text, Decimal arithmetic, the cell expression language |
| `src/faithguard/tables.py`, `claims.py` | Table normaliser; numeric claims and what each is about |
| `src/faithguard/detect/` | Channel B rule checker; Channel A (span and relation-slot heads); A+B fusion; baseline detectors |
| `src/faithguard/executor.py`, `repair/` | Deterministic executor; rule-only repairer v0; model repairer (edit programs, one retry); free-rewrite baseline; the hard gate |
| `src/faithguard/policy/` | Features; threshold policy v0; outcome models, certification, the policy study and the deployable outcome-aware policy |
| `src/faithguard/data/` | Loaders for FinQA, TAT-QA, RAGTruth and SEC XBRL; XBRL mining; training-data builders; dataset downloader |
| `src/faithguard/controlled.py` | The controlled track at scale: injected errors, issuer-disjoint track splits, cached parallel replays |
| `src/faithguard/benchmark.py`, `benchmark-example/` | The team benchmark format (report YAML + corrected-table CSVs), gold-answer checks, builder; a worked example |
| `src/faithguard/generation/` | Answer generation: generator settings, prompts, llama.cpp servers, resumable runs |
| `src/faithguard/train/` | GPU training and evaluation entry points (each with a `--tiny` CPU smoke test) |
| `notebooks/` | Phase-4 Kaggle/Colab notebooks that clone this repository and run the training jobs |
| `src/faithguard/inject.py`, `replay.py`, `evaluate/` | Error injector, replay harness, scoring and policy metrics |
| `src/faithguard/stats/` | Issuer-clustered bootstrap, Learn-then-Test certification, Cohen's kappa |
| `src/faithguard/splits.py`, `manifests/` | Split manifest (frozen with a hash), candidate issuers, dataset checksums |
| `src/faithguard/labelling.py`, `labelling/` | Blinded Label Studio tasks, the labelling interface, export conversion |
| `runs/` | Summaries and reports of runs (bulky item files are not committed) |
| `docs/` | Plans, logs, guides, related-work tables, original component designs |
| `pilots/` | Phase-1 GPU pilots and their Kaggle/Colab notebooks |
| `logs/`, `requirements/`, `setup/` | GPU logs, pinned packages, the notebook setup cell |
| `data/` | Local data only; never committed |

## Setting up a laptop

Use Python 3.11. From the repository folder:

```bash
python -m venv .venv
```

Install the locked packages and the project itself (on macOS or Linux use `.venv/bin/` instead of `.venv/Scripts/`):

```bash
.venv/Scripts/python -m pip install -r requirements/laptop.lock.txt
```

```bash
.venv/Scripts/python -m pip install -e .
```

Check it works:

```bash
.venv/Scripts/python -m pytest
```

Then fetch the datasets (about 160 MB; checksums are compared with `manifests/datasets.json`):

```bash
.venv/Scripts/faithguard data download all
```

**Adding a package:** add it to `requirements/laptop.txt` with an exact version, reinstall, regenerate the lock with `pip freeze --exclude pip --exclude faithguard > requirements/laptop.lock.txt` (the project itself is installed separately), and log it in the decision log.

**SEC access:** the SEC blocks requests that do not declare a contact. Set this once before any EDGAR command:

```bash
export FG_SEC_USER_AGENT="FaithGuard research Your Name you@example.com"
```

## Commands

| Command | What it does |
| --- | --- |
| `faithguard data download all` | Fetch FinQA, TAT-QA and RAGTruth into `data/raw/` and record checksums |
| `faithguard controlled --source tatqa --split dev` | Controlled track: inject known errors, replay every action, write `runs/controlled/<source>-<split>/summary.json` |
| `faithguard slice` | Thin end-to-end slice (32 items, rules only), report in `runs/slice/report.md` |
| `faithguard trace --items F --id ID` | One item step by step, for demonstrations |
| `faithguard policy` | The policy study: outcome models, certified policies vs baselines, budget curve, SCoRE; report in `runs/policy/controlled/` |
| `faithguard sft --mode program` (or `rewrite`) | Repairer training data from the controlled track, into `runs/sft/` |
| `faithguard detector-data` | Channel A training data (controlled track, RAGTruth, XBRL if mined), into `runs/detector/` |
| `faithguard xbrl-mine` | XBRL-mined wrong-context negatives from training-only US companies (needs `FG_SEC_USER_AGENT`) |
| `faithguard reports list` / `download --splits dev` | The annual reports in `manifests/lk-reports.csv` (default) or, with `--country US`, `manifests/us-reports.csv`; downloads record checksums |
| `faithguard reports locate --country US` | Each US issuer's latest 10-K on EDGAR, into `manifests/us-reports.csv` (needs `FG_SEC_USER_AGENT`) |
| `python -m faithguard.data.pdf_tables REPORT.pdf PAGES OUT.csv` | Draft a benchmark table from a Sri Lankan report PDF |
| `python -m faithguard.data.html_tables REPORT.htm list` / `extract N OUT.csv` | List a 10-K's tables, or draft one as a benchmark table |
| `faithguard benchmark cells FILE` | Every cell id of a report, for question writers |
| `faithguard benchmark check` | Recompute every gold answer from its cells and report mistakes ([benchmark guide](docs/benchmark-guide.md)) |
| `faithguard benchmark build [--pilot-only]` | Questions with frozen evidence, and their gold, into `data/benchmark-build/` |
| `faithguard generate --generator qwen` | Answers from one generator served by llama.cpp (resumable) |
| `faithguard items --questions F --answers A B` | Join questions and answers into items for labelling and the pipeline |
| `faithguard splits build` | Rebuild the split manifest from `manifests/issuers.csv` |
| `faithguard labelling tasks --items F` | Blinded Label Studio tasks; the key mapping goes to the gold store |
| `faithguard labelling import --export F` | Convert a Label Studio export into gold labels |
| `faithguard extraction compare\|all\|evidence` | The automatic-extraction run: PDF table tools against the hand-corrected tables, and the real-world condition's evidence |
| `faithguard hashes FILES --out F` | Pin files by SHA-256 (answers, evidence, the locked test set) |

## Kaggle and Colab

Every notebook starts with `setup/setup_cell.py`, which stops at once if the session has no internet or GPU, installs `requirements/gpu.txt` and uses the platform's own torch. After changing `requirements/gpu.txt` or any pilot script, rebuild the notebooks with `python pilots/build_notebooks.py`.

**From the command line:** `python pilots/kaggle_run.py push` runs the three pilots on Kaggle as private T4 notebooks, `status` shows their state and `fetch` copies their result files into `pilots/results/`. For the pilot answers, `dataset faithguard-benchmark data/benchmark-build/questions.jsonl` uploads the built questions as a private dataset (never the gold store), `push generate_answers --dataset faithguard-benchmark` runs the generation notebook on them, and `fetch generate_answers` copies the answers into `data/benchmark-build/`. It needs the Kaggle CLI with an API token in `~/.kaggle/` (never in this folder), and a phone-verified Kaggle account: without one, Kaggle runs notebooks with no GPU and no internet.

**Working rules:** keep runs to a few hours and save a checkpoint at least every hour; save every output as soon as a step finishes; use your own account only; log every GPU session in `logs/gpu-hours.csv` with the session hours the platform shows.

## Where outputs live

| What | Where |
| --- | --- |
| Code, small results (JSON, CSV), logs and documents | This repository |
| Large outputs: generated answers, checkpoints, model files | Private Kaggle Datasets named `faithguard-<what>-v<N>` |
| Copies for Colab work | A Google Drive folder `FaithGuard/`, with the same names |
| Gold answers and labels | `data/gold/` locally and a separate private Kaggle Dataset `faithguard-gold-v<N>`, read only by evaluation code |
| Sri Lankan report PDFs | Drive only; the public release holds questions, labels and page pointers (risk R-07) |

## Status

### Phase 1: set up

| Task | State | Next step |
| --- | --- | --- |
| Repository, environment, logs, decision log, risk register, authorship | Done | Review the logs at each weekly check |
| Adjudicator | Draft: [docs/drafts/adjudicator-request.md](docs/drafts/adjudicator-request.md) | Send to an accounting lecturer or senior student |
| GPU quota per account | Template: [logs/gpu-quota.csv](logs/gpu-quota.csv) | Record what Kaggle and Colab show |
| Repair, detector and generation GPU pilots | Done on Kaggle T4s (2026-10-09), results in [pilots/results/](pilots/results/): detector PASS (D-054), generation PASS (D-055), repair: fp16 LoRA at 1,024 and 2,048 tokens and QLoRA all train; repair training starts with fp16 LoRA (D-058) | None: phase-1 pilots complete |
| Closest prior work per paper | Tables in [docs/related-work/](docs/related-work/) | Open each work and fill in its row (LettuceDetect v2 taxonomy head first) |

### Phase 2: shared foundation

| Exit item | State |
| --- | --- |
| Record format v1 and gold store | Done (`records.py`, `gold.py`); a test enforces that decision-time code never imports gold |
| Calculation API and executor | Done, tested (`calc/`, `executor.py`) |
| FinQA, TAT-QA, RAGTruth loaded with licences and checksums | Done (`manifests/datasets.json`) |
| XBRL facts | Live: 14,512 XBRL-mined training examples from the latest 10-Ks of 120 FinQA companies, committed as `runs/detector/xbrl.jsonl.gz` (D-049) |
| Split manifest frozen | Built and hashed (`manifests/splits.json`); Sri Lankan tickers verified on the CSE (D-038); US tickers and CIKs verified on the SEC, two banks that stopped filing replaced (D-040) |
| Label Studio with guide v1 | Interface, converters and guide ready; install and start it as in the guide |
| Thin end-to-end slice on 20–40 items | Done: [runs/slice/report.md](runs/slice/report.md) (32 items, expected action on 29) |

Controlled track on development data, made from the project's own templates (pipeline checks, not results):

| Data | Items | Policy v0: sent | Wrong among sent | Useful sent | Send everything: wrong among sent | Expected action |
| --- | --- | --- | --- | --- | --- | --- |
| TAT-QA dev | 2,133 | 77.8% | 1.8% | 76.3% | 79.1% | 96.9% |
| FinQA dev | 791 | 61.4% | 0.8% | 60.9% | 77.2% | 83.6% |

### Phase 3: benchmark and pilot (questions drafted; cross-checks and labelling next)

| Exit item | State |
| --- | --- |
| Corrected tables and questions with gold answers | Format, checker and builder done ([benchmark guide](docs/benchmark-guide.md), [example](benchmark-example/)); all 28 benchmark reports per country downloaded, with checksums in [manifests/lk-reports.csv](manifests/lk-reports.csv) and [manifests/us-reports.csv](manifests/us-reports.csv); test and calibration tables drafted for all 48 reports (income statement and balance sheet: 48 Sri Lankan and 48 US tables, every total adds up; D-060, D-062); all 400 main questions drafted, 250 Sri Lankan (D-064) and 150 US (D-067), every gold answer recomputed from its cells by `faithguard benchmark check`; each awaits a second reader |
| Pilot: 60 questions, 120 answers, labelled | 60 pilot questions written and built: 33 Sri Lankan, 27 US (D-046, D-051), each awaiting a second reader; 120 answers generated on Kaggle (D-056); all 120 labelled by Claude at the user's request (D-066): 19.2% incorrect, so no harder question types are added, and the US count stays at 150 groups. Results in [runs/pilot/report.md](runs/pilot/report.md). The labels await a person's review in Label Studio: importing `data/benchmark-build/labels/tasks-with-labels.json` (not in git) shows them as pre-annotations to accept or correct; time the review to measure minutes per item |
| Annotation guide v2 | Drafted from the pilot's hard cases (D-068): [docs/annotation-guide.md](docs/annotation-guide.md); frozen once a person has reviewed the pilot labels. Labelling time goes in [logs/labelling-hours.csv](logs/labelling-hours.csv) |
| Automatic-extraction run on 20 tables | Done (D-070): PyMuPDF, pdfplumber and camelot on 20 Sri Lankan tables, [runs/extraction/report.md](runs/extraction/report.md); PyMuPDF (text) chosen, 94.2% of figures right on all 48 Sri Lankan main tables ([runs/extraction/all/report.md](runs/extraction/all/report.md)). Real-world evidence for the 400 main questions built in `data/benchmark-build/main-auto/` (not in git) |
| Future-period set held back | The next annual report of each test issuer, listed with expected dates in [manifests/future-period.csv](manifests/future-period.csv) (D-069); none downloaded |

### Phase 5: generate, freeze and pre-register (started)

| Exit item | State |
| --- | --- |
| All answers generated and stored | Done (D-073): 800 answers (400 questions, Qwen3.5-9B and Gemma-4-12B), no thinking leaks or empty answers, 0.95 GPU hours; files pinned in [manifests/main-answers.json](manifests/main-answers.json); blinded labelling tasks made (`labelling/main-tasks.json`, not in git), with no suggested labels |
| Evidence frozen and test set locked | After every table and question has a second reader |
| Detector, repairer v1 and all variants frozen | After phase 4's GPU runs |
| Pre-registration filed | Drafted (D-071): [docs/preregistration.md](docs/preregistration.md); filed at lock |

### Phase 4: components (built; GPU runs under way)

| Part | Built and tested on CPU | Waiting for |
| --- | --- | --- |
| Decision policy | Outcome models (LightGBM; TabICLv2 optional), Learn-then-Test certification over a pre-registered grid, five baselines and the oracle, certification-budget curve, issuer-level check, SCoRE comparator, deployable policy: [runs/policy/controlled/report.md](runs/policy/controlled/report.md) | The natural benchmark (phases 3, 5, 6) |
| Repair | Model repairer with retry, free-rewrite baseline, training data (10,587 examples; basis errors held out), fine-tuning, self-training and evaluation scripts | Stage A running on Kaggle since 2026-10-09 ([notebooks/repair_sft.ipynb](notebooks/repair_sft.ipynb)); then [repair_baselines.ipynb](notebooks/repair_baselines.ipynb) and [repair_self_train.ipynb](notebooks/repair_self_train.ipynb) |
| Detection | Channel A (span + slot heads), training data (34,229 examples, 12,846 of them XBRL-mined), training and evaluation scripts, A+B fusion with calibration, three baseline detectors, XBRL mining | Training running on Kaggle since 2026-10-09 ([notebooks/detector_train.ipynb](notebooks/detector_train.ipynb)); then [detector_baselines.ipynb](notebooks/detector_baselines.ipynb) |

Policy study on the controlled track (rehearsal on template answers; certified at alpha = 0.10):

| Policy | Answers sent | Wrong among sent | Useful answers |
| --- | --- | --- | --- |
| Send everything | 100% | 79.0% (not certifiable) | 21.0% |
| Send only verified answers | 21.5% | 2.9% | 20.9% |
| Outcome-aware (LightGBM) | 73.8% | 1.6% | 72.7% |
| Oracle with hindsight | 72.9% | 0% | 72.9% |

Certification needs about 200 calibration answers before it reliably passes (75% of random draws at 200, all at 400).

