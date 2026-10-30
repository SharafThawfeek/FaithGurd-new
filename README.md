# FaithGuard

FaithGuard checks each AI answer about a financial report before it reaches the user, then sends it, fixes it, or refuses with a reason. It is a three-part research project: detection (M.L Ahamed), repair (M.S.A Ahamed) and decision policy (Sharaf).

**AI assistance.** Claude (Anthropic) wrote the project's code and drafted its documents at the team's direction. Claude also took every labelling and checking role the plan gave to people (D-103), each as a separate, blind pass: the second reader of the 400 main questions and the table rows they use (D-104), the labeller of every benchmark answer, the second labeller of 80 tasks, the adjudicator of the 15 disagreements, and the checker of the repair sample (D-106, D-109). No person labelled, checked or adjudicated the benchmark, so its kappa is agreement between Claude's passes. Every commit was made from one GitHub account (SharafThawfeek) with Claude as co-author, and every Kaggle session in [logs/gpu-hours.csv](logs/gpu-hours.csv) ran on one Kaggle account (sharafthawfeek), the detection and repair training included. Where the decision log says "the user" (D-066, D-070, D-103), it means the person directing Claude. The decision log's Owner column names who owns each decision. The team takes responsibility for all content.

- **Research plan:** [docs/FaithGuard-Revised-Plan.md](docs/FaithGuard-Revised-Plan.md), covering what is built and why
- **Phase plan:** [docs/FaithGuard-Phase-Plan.md](docs/FaithGuard-Phase-Plan.md), covering what to do in what order; each phase ends at an exit checklist
- **Decision log:** [docs/decision-log.md](docs/decision-log.md) · **Risk register:** [docs/risk-register.md](docs/risk-register.md) · **Annotation guide (v2):** [docs/annotation-guide.md](docs/annotation-guide.md) · **Pre-registration (filed, tag `prereg-v1`):** [docs/preregistration.md](docs/preregistration.md), with the erratum below
- **History:** this repository starts on 8 October 2026 (commit d032e98) with the revised plan of that day, which replaces a plan set out in documents of 7 October 2026 (see the plan's section "Changes from the previous plan"); the three original component designs are in [docs/components/](docs/components/)
- **Licence:** none chosen yet: the code and the benchmark data have no licence or release terms, so default copyright applies. Release terms for the Sri Lankan reports are risk R-07

**Erratum to the filed pre-registration.** The filed text stays as filed (`git diff prereg-v1 HEAD -- docs/preregistration.md` is empty), but three of its phrases are wrong: §1 calls the evidence "Hand-corrected", §3 measures the detection comparison on "Human-labelled natural answers", and §5 scores information preserved on a "human-scored sample". No person corrected or checked a table: the tables were drafted by the project's PDF and HTML readers, with fixes made in code, and kept only when every subtotal and total adds up (D-060, D-062), and a Claude pass checked the rows the questions use against the pages (D-104). No person labelled or scored an answer either: every label and check, and the judgement of information preserved, is a separate blind Claude pass (D-103, D-106, D-109). Where §1 and §6 say "a person", read the labeller's role, as §1's last sentence says. The filing is an unsigned annotated git tag in the team's own repository, pushed to GitHub; no outside registry (such as OSF or AsPredicted) holds a copy or a timestamp. D-114 records this erratum.

## Papers and demo

The four papers are working drafts. Their result sections are filled from the pre-registered analysis in [runs/main/](runs/main/report.md) as it was generated (D-113); open citations and checks are still marked in square brackets.

| What | Where |
| --- | --- |
| Detection: *Right Number, Wrong Context* (lead author M.L Ahamed) | [docs/papers/detection.md](docs/papers/detection.md) |
| Repair: *Edit Programs, Not Rewrites* (lead author M.S.A Ahamed) | [docs/papers/repair.md](docs/papers/repair.md) |
| Decision policy: *Should We Fix It?* (lead author Sharaf) | [docs/papers/policy.md](docs/papers/policy.md) |
| The joint benchmark paper (working title) | [docs/papers/benchmark.md](docs/papers/benchmark.md) |
| How the system fits together | [docs/architecture.md](docs/architecture.md) |
| The local demo: `.venv\Scripts\python demo\app.py`, then http://127.0.0.1:8765/ (full demo) or http://127.0.0.1:8765/simple.html (one page for a general audience) | [demo/README.md](demo/README.md), [demo/SIMPLE.md](demo/SIMPLE.md) |
| Known limitations | Each paper's Limitations section; "Known limitations shown by the demo" in [demo/README.md](demo/README.md); the [risk register](docs/risk-register.md) |

## Plan versus what happened

The revised plan of 8 October 2026 set the dates below. D-114 records the change of dates and of who labels.

| Step | Planned (revised plan, timeline) | What happened |
| --- | --- | --- |
| Test set locked, pre-registration filed | 31 January 2027 | 29 October 2026, as the git tag `prereg-v1` (D-104) |
| Labelling the locked answers | 1 February to 31 March 2027, by the three members (about 105 hours, with the pilot and double review) | 29 October 2026; every label, check and adjudication is a separate blind Claude pass, and no person labelled (D-103, D-105) |
| Analysis | Final runs, papers and report, 1 April to 30 June 2027 | 29 October 2026 (D-113); the papers are working drafts |

Of the plan's "never cut" items, the human-labelled natural test set was cut (D-103); the certified risk study ran, but no policy certifies on natural answers (D-113); and the detection paper's main ablation (D-H1, XBRL negatives) is untestable, with 4 wrong-context answers in the test split where its rule needs 20 (D-113).

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
| `src/faithguard/benchmark.py`, `benchmark-example/` | The team benchmark format (report YAML + table CSVs), gold-answer checks, builder; a worked example |
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
| `faithguard extraction compare\|all\|evidence` | The automatic-extraction run: PDF table tools against the benchmark tables (drafted by the project's reader and kept only when every total adds up, D-060; no person checked them), and the real-world condition's evidence |
| `faithguard hashes FILES --out F` | Pin files by SHA-256 (answers, evidence, the locked test set) |

## Kaggle and Colab

Every notebook starts with `setup/setup_cell.py`, which stops at once if the session has no internet or GPU, installs `requirements/gpu.txt` and uses the platform's own torch. After changing `requirements/gpu.txt` or any pilot script, rebuild the notebooks with `python pilots/build_notebooks.py`.

**From the command line:** `python pilots/kaggle_run.py push` runs the three pilots on Kaggle as private T4 notebooks, `status` shows their state and `fetch` copies their result files into `pilots/results/`. For the pilot answers, `dataset faithguard-benchmark data/benchmark-build/questions.jsonl` uploads the built questions as a private dataset (never the gold store), `push generate_answers --dataset faithguard-benchmark` runs the generation notebook on them, and `fetch generate_answers` copies the answers into `data/benchmark-build/`. It needs the Kaggle CLI with an API token in `~/.kaggle/` (never in this folder), and a phone-verified Kaggle account: without one, Kaggle runs notebooks with no GPU and no internet.

**Working rules:** keep runs to a few hours and save a checkpoint at least every hour; save every output as soon as a step finishes; use your own account only (in practice every logged session ran on one account, sharafthawfeek; see AI assistance above); log every GPU session in `logs/gpu-hours.csv` with the session hours the platform shows.

## Where outputs live

| What | Where |
| --- | --- |
| Code, small results (JSON, CSV), logs and documents | This repository |
| Large outputs: generated answers, checkpoints, model files | Private Kaggle Datasets named `faithguard-<what>-v<N>` |
| Copies for Colab work | A Google Drive folder `FaithGuard/`, with the same names |
| Gold answers and labels | The `gold/` folder of each build under `data/benchmark-build/` (local only, not in git; the `data/gold/` this table named before does not exist, D-100), read only by evaluation code. On Kaggle only the test answers' span offsets, in the dataset `faithguard-gold-spans` (D-105) |
| Sri Lankan report PDFs | Drive only; a public release would hold questions, labels and page pointers only (risk R-07; no release terms chosen yet) |

## Status

### Phase 1: set up

| Task | State | Next step |
| --- | --- | --- |
| Repository, environment, logs, decision log, risk register, authorship | Done | Review the logs at each weekly check |
| Adjudicator | Not used: no adjudicator took part. A blind Claude pass adjudicated the 15 disagreements (D-103, D-105); the draft request, [docs/drafts/adjudicator-request.md](docs/drafts/adjudicator-request.md), is kept as written | None |
| GPU quota per account | Not recorded: [logs/gpu-quota.csv](logs/gpu-quota.csv) has one blank row per member and platform | None: the sessions themselves are in [logs/gpu-hours.csv](logs/gpu-hours.csv), 33 Kaggle sessions and 70.5 hours, all on the sharafthawfeek account |
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
| Label Studio with guide v1 | Interface, converters and guide ready; no person used them for the benchmark, whose labels are blind Claude passes on the blinded tasks (D-103, D-105) |
| Thin end-to-end slice on 20–40 items | Done: [runs/slice/report.md](runs/slice/report.md) (32 items, expected action on 29) |

Controlled track on development data, made from the project's own templates (pipeline checks, not results):

| Data | Items | Policy v0: sent | Wrong among sent | Useful sent | Send everything: wrong among sent | Expected action |
| --- | --- | --- | --- | --- | --- | --- |
| TAT-QA dev | 2,133 | 77.8% | 1.8% | 76.3% | 79.1% | 96.9% |
| FinQA dev | 791 | 61.4% | 0.8% | 60.9% | 77.2% | 83.6% |

### Phase 3: benchmark and pilot (done)

| Exit item | State |
| --- | --- |
| Tables and questions with gold answers | Format, checker and builder done ([benchmark guide](docs/benchmark-guide.md), [example](benchmark-example/)); all 28 benchmark reports per country downloaded, with checksums in [manifests/lk-reports.csv](manifests/lk-reports.csv) and [manifests/us-reports.csv](manifests/us-reports.csv); test and calibration tables drafted by the project's PDF and HTML readers for all 48 reports (income statement and balance sheet: 48 Sri Lankan and 48 US tables, every total adds up; D-060, D-062); all 400 main questions drafted, 250 Sri Lankan (D-064) and 150 US (D-067), every gold answer recomputed from its cells by `faithguard benchmark check`. The second reader is a blind Claude pass, which re-derived all 400 and checked the table rows they use against the pages (D-103, D-104); no person checked a table or question |
| Pilot: 60 questions, 120 answers, labelled | 60 pilot questions written and built: 33 Sri Lankan, 27 US (D-046, D-051), with no second reader (the pilot is development data and reports no result, D-105); 120 answers generated on Kaggle (D-056); all 120 labelled by Claude at the user's request (D-066): 19.2% incorrect, so no harder question types are added, and the US count stays at 150 groups. Results in [runs/pilot/report.md](runs/pilot/report.md). No person reviewed these labels, and the blind review of the pilot's 61 code labels that D-100 set before filing did not happen, so minutes per item were never measured (R-01) |
| Annotation guide v2 | Drafted from the pilot's hard cases (D-068): [docs/annotation-guide.md](docs/annotation-guide.md); the main labels follow it (pre-registration §1). It was to be frozen once a person had reviewed the pilot labels, and no person did. No person labelled, so [logs/labelling-hours.csv](logs/labelling-hours.csv) is empty by design (header only; D-103) |
| Automatic-extraction run on 20 tables | Done (D-070): PyMuPDF, pdfplumber and camelot on 20 Sri Lankan tables, [runs/extraction/report.md](runs/extraction/report.md); PyMuPDF (text) chosen, 94.2% of figures right on all 48 Sri Lankan main tables ([runs/extraction/all/report.md](runs/extraction/all/report.md)). Real-world evidence for the 400 main questions built in `data/benchmark-build/main-auto/` (not in git) |
| Future-period set held back | The next annual report of each test issuer, listed with expected dates in [manifests/future-period.csv](manifests/future-period.csv) (D-069); none downloaded |

### Phase 4: components (done)

| Part | Built and tested on CPU | Trained and run |
| --- | --- | --- |
| Decision policy | Outcome models (LightGBM; the neural challenger, an mmBERT encoder fine-tuned on a GPU on the question, evidence, answer and features as text, D-096; trained in 1.01 GPU hours, D-099), Learn-then-Test certification over a pre-registered grid, five baselines and the oracle, certification-budget curve, issuer-level check, SCoRE comparator, deployable policy: [runs/policy/controlled/report.md](runs/policy/controlled/report.md); the v0-to-v1 transfer study (`faithguard.policy.transfer`, D-082), rehearsed with 4,000 trained-repairer replays: the v0 policy stays safe as it is, so the grid keeps no fallback (D-093) | systems_main ran the neural outcome model with repairer v1 on all 788 locked answers (D-111). The transfer rehearsal was repeated with the frozen repairer v1 (`transfer_replays`, 3.11 GPU hours, 2026-10-29): the v0 policy stays within alpha as it is (1.0% wrong among sent), and recalibrated on 100 v1 labels it certifies in 48% of draws, from 200 in all ([report](runs/policy/transfer/report.md)). On the natural benchmark: phases 5 to 7 |
| Repair | Model repairer with retry, free-rewrite baseline, training data (10,587 examples; basis errors held out; 1,133 arithmetic slips with `--arithmetic`, D-088), fine-tuning, self-training and evaluation scripts | Stage A and the baselines trained (D-074, D-077), on 500 tune-track items: edit programs 62.3% corrected with 0.6% new errors, free rewriting 51.8% with 15.4%, zero-shot programs 8.0%; stage B self-training matches stage A on these template answers (D-079); with Channel A's spans stage A corrects 63.3% with no damage, and training without KEEP items changes nothing here (RQ3, D-090) ([reports](runs/repair/kaggle/)). The gate's share fix (D-087) adds about 3 points on re-gated programs. Repairer v1 (stage A with the arithmetic slips; `repair_v1`, 7.63 GPU hours) corrects 65.7% with 0.5% new errors on the tune track (D-095) and is frozen (D-101); the free-rewrite baseline was retrained on v1's data and frozen (D-110) |
| Detection | Channel A (span + slot heads), training data (34,229 examples, 12,846 of them XBRL-mined), training and evaluation scripts, A+B fusion with calibration, three baseline detectors, XBRL mining | Channel A and both ablations trained and evaluated on 2,000 tune-track items (D-075, D-076): AUROC 0.933 full, 0.932 without XBRL negatives, 0.931 without the slot head ([results](runs/detector/kaggle/)); A+B fusion fitted and calibrated: item AUROC 0.995, 1.0% false alarms on 475 held-out items (D-078, [report](runs/detector/fusion/report.md)); released baselines scored: AUROC 0.51 to 0.56 for LettuceDetect and HHEM, 0.81 for Granite Guardian (D-080) |

Policy study on the controlled track (rehearsal on template answers; certified at alpha = 0.10):

| Policy | Answers sent | Wrong among sent | Useful answers |
| --- | --- | --- | --- |
| Send everything | 100% | 79.0% (not certifiable) | 21.0% |
| Send only verified answers | 21.5% | 2.9% | 20.9% |
| Outcome-aware (LightGBM) | 73.8% | 1.6% | 72.7% |
| Outcome-aware (neural challenger, D-099) | 73.5% | 1.3% | 72.5% |
| Oracle with hindsight | 72.9% | 0% | 72.9% |

On the controlled track, certification needs about 200 calibration answers before it reliably passes (75% of random draws at 200 with LightGBM, 84% with the neural model; all at 400). On the 396 natural calibration answers nothing certifies (D-113; Phase 7 below).

### Phase 5: generate, freeze and pre-register (done)

| Exit item | State |
| --- | --- |
| All answers generated and stored | Done (D-073): 800 answers (400 questions, Qwen3.5-9B and Gemma-4-12B), no thinking leaks or empty answers, 0.95 GPU hours; files pinned in [manifests/main-answers.json](manifests/main-answers.json); blinded labelling tasks made (`labelling/main-tasks.json`, not in git), with no suggested labels; superseded by D-100, which builds the main tasks with `labelling triage` after filing |
| Evidence frozen and test set locked | Done (D-104): a second-reader pass by Claude (D-103) re-derived all 400 questions and checked the table rows they use; 6 questions with two readings excluded, so the locked test set is 394 questions and 788 answers ([manifests/locked-test.json](manifests/locked-test.json), [manifests/excluded-questions.json](manifests/excluded-questions.json)) |
| Detector, repairer v1 and all variants frozen | Done (D-101, D-104): hashes in [manifests/frozen-detector.json](manifests/frozen-detector.json) and [manifests/frozen-repair.json](manifests/frozen-repair.json); the free-rewrite baseline's adapter was added when its Kaggle run ended (D-110), and the no-XBRL ablation's hashes 3 minutes after filing (commit d3faf92), as the filing said they would be |
| Pre-registration filed | Filed on 2026-10-29 as the git tag `prereg-v1` (D-104): [docs/preregistration.md](docs/preregistration.md); later changes are deviations in the decision log (D-105 to D-112, and the no-XBRL ablation's hash added three minutes after the tag, D-114 (5); D-113 records the analysis). The erratum at the top of this page corrects three of its phrases, and D-114 lists the other corrections and reversals |

### Phase 6: label the benchmark (done)

| Step | State |
| --- | --- |
| Run every frozen system on the items | Done: `python -m faithguard.train.systems` (GPU) ran systems_main on all 788 locked answers, storing Channel A's spans and every repairer's outputs, and every frozen file matched its hash; large evidence is focused first (D-084). The rewrite baseline was rerun after D-111, which has it decline narrative answers with no numbers. Dry run on the 120 pilot answers (D-085) |
| Code checks on every repair | `faithguard systems` scores the stored outputs against gold, counts only: [runs/pilot/systems/report.md](runs/pilot/systems/report.md). On the pilot, after the gate and parser fixes (D-087, D-092, D-094), stage A corrects 34.8% of the wrong answers with the rule checker's spans and 39.1% with Channel A's, damaging none; the rules correct 43.5%. Without KEEP training the model corrects more with the rule checker's spans but loses more correct answers with Channel A's ([stage A](runs/pilot/systems-repair-sft/report.md), [no KEEP](runs/pilot/systems-repair-sft-nokeep/report.md)) |
| Label the 788 locked answers | Done (D-105). Every label, check and adjudication is a separate blind Claude pass, not a person (D-103). The triage gave 311 code labels and sent 477 answers to the labeller; the audit overruled 4 of its 150 code labels, so the code labels fell and the labeller labelled every answer. A second labeller on 80 tasks: status kappa 0.89, usefulness 0.71, wrong-span 1.00; 15 disagreements adjudicated. 177 of 788 answers incorrect (22.5%). Counts: [runs/main/labels/report.md](runs/main/labels/report.md). A first pass made without each table's units note was discarded unused |
| Check a sample of repairs | Done (D-106): a blind Claude pass labelled every changed repair of v1 with gold spans and 50 each from rewriting with gold spans and from the other variants. Code and labels disagree on 3 of 43 (7.0%), 3 of 50 (6.0%) and 8 of 50 (16.0%), so all 509 changed repairs of the other variants were labelled, and their labels replace the scorer's states in the repair summaries, R-H2 and R-H3 (D-112). Information preserved on the same sample (D-109): 97.7% for v1 with gold spans, 90.0% for rewriting with gold spans, 66.0% for the other variants |

**Note on generated reports.** Reports under `runs/` are kept as the code wrote them, and that code is frozen at `prereg-v1` (D-104), so some of their wording predates D-103. [runs/main/labels/report.md](runs/main/labels/report.md) is titled "Pilot answers", the title the frozen `evaluate.pilot` writes, but it counts the 788 locked answers. In [runs/main/triage/report.md](runs/main/triage/report.md), "a person's labels", "A person labels" and "also a person" name the labeller's role, and in [runs/policy/controlled/report.md](runs/policy/controlled/report.md) "the human-labelled natural test" is the locked test. Under D-103 every one of those labels is a blind Claude pass. The labelling commands above use "a person" in the same sense.

### Phase 7: analyse (done)

`faithguard analyse` on the locked test set, with issuer-clustered bootstrap 95% intervals: [runs/main/report.md](runs/main/report.md).

| Hypothesis | Estimate [95% interval] | Verdict |
| --- | --- | --- |
| D-H1: XBRL negatives raise wrong-context recall | 4 wrong-context test answers; the rule needs 20 | Untestable, as pre-registered |
| D-H2: A + B beats B on Sri Lankan spans | Span F1 0.205 against 0.181 (246 answers, 12 issuers): 0.024 [−0.059, 0.146] | Rejected: no difference |
| D-H3: the US threshold carries over to Sri Lanka | No US threshold certifies at alpha = 0.10; label-efficiency curve 0% at 100, 200 and all 250 labels | Untestable |
| R-H1: edit programs make fewer new errors than rewriting (gold spans) | New errors 0.3% against 10.9%: −10.6 points [−13.7, −7.7]; correction 49.4% against 20.5%: +28.9 points [16.5, 43.7] | Confirmed |
| R-H2: self-training helps out of distribution | Gemma's answers +18.2 points [4.7, 31.0]; held-out basis errors 0.0 [0.0, 0.0] on only 2 answers | Not confirmed: the rule needs a gain on both |
| R-H3: KEEP training cuts damage | +0.4 points [−0.9, 1.8] (0.8% against 0.4%) | Rejected: no change |
| P-H1: the outcome-aware policy beats the detector threshold | Neither certifies, so both send nothing: 0.0 [0.0, 0.0] | Rejected: no difference |
| P-H2: alpha = 0.10 certifiable at useful coverage | LightGBM certifies in 0% of draws at 100, 200 and all 396 calibration answers; neural in 2% at 200 | Rejected: not reachable |
| P-H3: the v0 policy carries over to v1 | The v0 policy is not certifiable on v0's natural calibration records | Untestable |

No policy certifies because, with only 396 calibration answers, the bound on wrong-among-sent needs a low error rate at high coverage: repairing everything sends 266 of them (67.2%) with 18 wrong, where certifying allows at most 13, and the outcome models, trained on template answers, are miscalibrated on natural ones (the oracle with hindsight reaches 86.0% useful coverage with nothing wrong sent, so the gap is in prediction and label budget).
