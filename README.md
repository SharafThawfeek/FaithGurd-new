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
| `faithguard policy` | The policy study: outcome models, certified policies vs baselines, budget curve, SCoRE; report in `runs/policy/controlled/`. `--models lightgbm,neural` adds the neural challenger once its GPU predictions are fetched (D-096) |
| `faithguard outcome-data` | The neural outcome model's input rows from the controlled-track cache (targets for fit and tune only), into `runs/policy/neural/`, for the `outcome_model` notebook |
| `faithguard sft --mode program` (or `rewrite`) | Repairer training data from the controlled track, into `runs/sft/`; `--arithmetic` adds the repair-only arithmetic slips (D-088) |
| `faithguard transfer --v1 REPLAY` | The transfer study: the rule-repairer policy on a trained repairer's replays (written on a GPU by `python -m faithguard.train.replays`); report in `runs/policy/transfer/` |
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
| `faithguard labelling tasks --items F --mapping M` | Blinded Label Studio tasks with random keys; the key mapping M goes to the gold store |
| `faithguard labelling triage --items F --gold G [--filed REF]` | Code labels the answers it can decide; blinded tasks for a person for the rest plus a hidden audit of 150 code labels (D-100). Test and calibration answers need the filed pre-registration and a second reader for every question |
| `faithguard labelling audit --items F --gold G [--apply]` | The audit's verdict once every audited answer has a person's label; tasks for any answers that still need a person; `--apply` adds the code labels that stand, once every routed answer has a person's label |
| `faithguard labelling import --export F --mapping M --gold G` | Convert a Label Studio export into gold labels |
| `faithguard labelling spans --items F --gold G` | The deciding labels' span offsets for the test answers, for R-H1's gold-span setting (the faithguard-gold-spans Kaggle dataset) |
| `faithguard repair-check draw\|compare` | The pre-registered repair check: a blind labelled sample of changed repairs against code (D-106) |
| `faithguard analyse [--rehearse]` | Phase 7: the pre-registered hypotheses with issuer-clustered bootstrap intervals, on the locked test set; report in `runs/main/` |
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

### Phase 5: generate, freeze and pre-register (done)

| Exit item | State |
| --- | --- |
| All answers generated and stored | Done (D-073): 800 answers (400 questions, Qwen3.5-9B and Gemma-4-12B), no thinking leaks or empty answers, 0.95 GPU hours; files pinned in [manifests/main-answers.json](manifests/main-answers.json); blinded labelling tasks made (`labelling/main-tasks.json`, not in git), with no suggested labels; superseded by D-100, which builds the main tasks with `labelling triage` after filing |
| Evidence frozen and test set locked | Done (D-104): a second-reader pass by Claude (D-103) re-derived all 400 questions and checked the table rows they use; 6 questions with two readings excluded, so the locked test set is 394 questions and 788 answers ([manifests/locked-test.json](manifests/locked-test.json), [manifests/excluded-questions.json](manifests/excluded-questions.json)) |
| Detector, repairer v1 and all variants frozen | Done (D-101, D-104): hashes in [manifests/frozen-detector.json](manifests/frozen-detector.json) and [manifests/frozen-repair.json](manifests/frozen-repair.json); the free-rewrite baseline's adapter was added when its Kaggle run ended (D-110) |
| Pre-registration filed | Filed on 2026-10-29 as the git tag `prereg-v1` (D-104): [docs/preregistration.md](docs/preregistration.md); later changes are deviations in the decision log (D-105 to D-107) |

### Phase 6: label the benchmark (labels done; system runs next)

| Step | State |
| --- | --- |
| Run every frozen system on the items | `python -m faithguard.train.systems` (GPU) stores Channel A's spans and the trained repairer's outputs; large evidence is focused first (D-084). Dry run on the 120 pilot answers done (D-085) |
| Code checks on every repair | `faithguard systems` scores the stored outputs against gold, counts only: [runs/pilot/systems/report.md](runs/pilot/systems/report.md). On the pilot, after the gate and parser fixes (D-087, D-092, D-094), stage A corrects 34.8% of the wrong answers with the rule checker's spans and 39.1% with Channel A's, damaging none; the rules correct 43.5%. Without KEEP training the model corrects more with the rule checker's spans but loses more correct answers with Channel A's ([stage A](runs/pilot/systems-repair-sft/report.md), [no KEEP](runs/pilot/systems-repair-sft-nokeep/report.md)) |
| Label the 788 locked answers | Done (D-105). Every label, check and adjudication is a separate blind Claude pass, not a person (D-103). The triage gave 311 code labels and sent 477 answers to the labeller; the audit overruled 4 of its 150 code labels, so the code labels fell and the labeller labelled every answer. A second labeller on 80 tasks: status kappa 0.89, usefulness 0.71, wrong-span 1.00; 15 disagreements adjudicated. 177 of 788 answers incorrect (22.5%). Counts: [runs/main/labels/report.md](runs/main/labels/report.md). A first pass made without each table's units note was discarded unused |
| Check a sample of repairs | `faithguard repair-check draw` once the main systems' outputs are fetched: 50 changed repairs from each R-H1 arm and 50 across the other variants, labelled by a blind Claude pass and compared with code by `repair-check compare` (D-106) |

### Phase 4: components (built and trained; development-data runs done)

| Part | Built and tested on CPU | Waiting for |
| --- | --- | --- |
| Decision policy | Outcome models (LightGBM; the neural challenger, an mmBERT encoder fine-tuned on a GPU on the question, evidence, answer and features as text, D-096; trained in 1.01 GPU hours, D-099), Learn-then-Test certification over a pre-registered grid, five baselines and the oracle, certification-budget curve, issuer-level check, SCoRE comparator, deployable policy: [runs/policy/controlled/report.md](runs/policy/controlled/report.md); the v0-to-v1 transfer study (`faithguard.policy.transfer`, D-082), rehearsed with 4,000 trained-repairer replays: the v0 policy stays safe as it is, so the grid keeps no fallback (D-093, [report](runs/policy/transfer/report.md)) | Scoring the natural benchmark's answers with the saved neural model (a GPU step not yet written); the rehearsal repeated with repairer v1 (notebook `transfer_replays`, about 3.3 GPU hours); the natural benchmark (phases 5, 6) |
| Repair | Model repairer with retry, free-rewrite baseline, training data (10,587 examples; basis errors held out; 1,133 arithmetic slips with `--arithmetic`, D-088), fine-tuning, self-training and evaluation scripts | Stage A and the baselines trained (D-074, D-077), on 500 tune-track items: edit programs 62.3% corrected with 0.6% new errors, free rewriting 51.8% with 15.4%, zero-shot programs 8.0%; stage B self-training matches stage A on these template answers (D-079); with Channel A's spans stage A corrects 63.3% with no damage, and training without KEEP items changes nothing here (RQ3, D-090) ([reports](runs/repair/kaggle/)). The gate's share fix (D-087) adds about 3 points on re-gated programs. Repairer v1 (stage A with arithmetic slips, notebook `repair_v1`, about 8 GPU hours) waits for next week's quota |
| Detection | Channel A (span + slot heads), training data (34,229 examples, 12,846 of them XBRL-mined), training and evaluation scripts, A+B fusion with calibration, three baseline detectors, XBRL mining | Channel A and both ablations trained and evaluated on 2,000 tune-track items (D-075, D-076): AUROC 0.933 full, 0.932 without XBRL negatives, 0.931 without the slot head ([results](runs/detector/kaggle/)); A+B fusion fitted and calibrated: item AUROC 0.995, 1.0% false alarms on 475 held-out items (D-078, [report](runs/detector/fusion/report.md)); released baselines scored: AUROC 0.51 to 0.56 for LettuceDetect and HHEM, 0.81 for Granite Guardian (D-080) |

Policy study on the controlled track (rehearsal on template answers; certified at alpha = 0.10):

| Policy | Answers sent | Wrong among sent | Useful answers |
| --- | --- | --- | --- |
| Send everything | 100% | 79.0% (not certifiable) | 21.0% |
| Send only verified answers | 21.5% | 2.9% | 20.9% |
| Outcome-aware (LightGBM) | 73.8% | 1.6% | 72.7% |
| Outcome-aware (neural challenger, D-099) | 73.5% | 1.3% | 72.5% |
| Oracle with hindsight | 72.9% | 0% | 72.9% |

Certification needs about 200 calibration answers before it reliably passes (75% of random draws at 200 with LightGBM, 84% with the neural model; all at 400).

