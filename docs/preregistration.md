# FaithGuard pre-registration (draft)

**Status: draft, not filed.** Phase 5 files this document before any test result is seen, either on OSF Registries or as a tagged commit pushed to GitHub. It is filed only after the evidence is frozen, the test set is locked and every component is frozen (the hashes in [Frozen inputs](#frozen-inputs)). Points the plan leaves open are marked **Open** with a proposed default; each must be settled by its owner, or the default accepted, before filing. Nothing here comes from looking at test answers: at the time of drafting, no system had been run on a test or calibration answer.

Sources: [the revised plan](FaithGuard-Revised-Plan.md) (hypotheses, research questions, experiments), [the phase plan](FaithGuard-Phase-Plan.md) (phase 5: what the pre-registration states) and the code named in each section.

## 1. Data

| Item | Pre-registered |
| --- | --- |
| Issuers | 12 test and 12 calibration issuers per country (US, Sri Lanka), issuer-disjoint from training and development ([manifests/splits.json](../manifests/splits.json), D-007) |
| Split manifest hash | `db0433453c32632ecd44f6ecaab25b247ec509cdef2a6836673223ef3a03c771` (the `sha256` field of the manifest) |
| Calibration versus test | Option B: about 12 extra issuers per country for calibration, the same 400 questions (D-007) |
| Questions | 400 question groups: 250 Sri Lankan, 150 US (D-064, D-067), each with gold answer, gold cells and question type |
| Answers | Each question answered once by Qwen3.5-9B (Q4_K_M) and Gemma 4 12B (QAT Q4_0) with llama.cpp b11490, thinking off, fixed seed and settings, prompt version `1f13b3d92d8a`: 800 answers |
| Evidence | Hand-corrected income statement and balance sheet per report (D-060, D-062), frozen by hash at lock |
| Real-world condition | The same answers checked against tables read by PyMuPDF (text) with no correction (D-070); a secondary analysis, not a hypothesis test |
| Labels | Annotation guide v2 ([annotation-guide.md](annotation-guide.md), D-068): spans with slot types, status (correct, incorrect, ambiguous, unhelpful) and usefulness; 240 items double-labelled; Cohen's kappa per field; disagreements adjudicated by an accounting lecturer or senior accounting student |
| Future-period set | The next annual report of each test issuer, held back unopened ([manifests/future-period.csv](../manifests/future-period.csv), D-069) |

## 2. Hypotheses

Nine hypotheses, three per paper, as in the revised plan. Each is confirmed or rejected only by its stated condition.

### Detection (M.L Ahamed)

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| D-H1. XBRL negatives raise wrong-context recall | Higher recall at an equal clean false-alarm rate | False alarms rise or recall does not move |
| D-H2. A + B beats B alone on Sri Lankan reports | Higher span F1, intervals not overlapping | No gain; rules suffice, reported as such |
| D-H3. The US threshold fails on Sri Lanka; about 100 local labels restore it | Risk above α before, within α after | Holds without recalibration; also reported |

### Repair (M.S.A Ahamed)

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| R-H1. Programs create fewer new errors than free rewriting | Lower new-error rate at a matched correction rate | No difference; reported as a negative result |
| R-H2. Self-training improves out-of-distribution repair | Gains on held-out error types and generator | Gains only on seen error types |
| R-H3. KEEP training cuts harm from detector false positives | Lower damage rate with predicted spans | No change |

### Decision policy (Sharaf)

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| P-H1. The outcome-aware policy beats the threshold policy | Higher useful coverage at equal certified α | No gain; the simpler policy is recommended |
| P-H2. α = 0.10 is certifiable at useful coverage | Certificate holds with coverage above the threshold policy | Not reachable; the budget curve says how many labels would be needed |
| P-H3. The v0 policy is unsafe on v1; recalibration restores safety | Risk above α as-is, within α after recalibration | Safe as-is, or refitting is needed; both are findings |

## 3. Primary comparisons

One per paper; everything else is secondary.

| Paper | Primary comparison | Measured on |
| --- | --- | --- |
| Detection | Channel A trained with vs without XBRL-mined negatives: wrong-context recall at an equal clean false-alarm rate | Human-labelled natural answers, test split |
| Repair | Edit programs vs free rewriting (same backbone, same data): new-error rate at a matched correction rate | Natural errors with gold spans, test split |
| Policy | Outcome-aware policy vs calibrated detector threshold: useful coverage, both certified at α = 0.10 | Test split, policies certified on the calibration split |

## 4. Policy certification

From `faithguard.policy` and `faithguard.stats` at the code version named at filing.

- **Risk target and confidence:** α = 0.10; δ = 0.05.
- **Certified quantity:** the share of sent answers that are unsupported, written as the per-item loss 1{unsafe sent} − α · 1{substantive sent} with expectation at most 0, so repair-introduced errors count.
- **Grid (outcome-aware policy):** send the original if P(unsafe) < τ1; otherwise repair if P(fix) > τ2; otherwise abstain. τ1 ∈ {0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5} and τ2 ∈ {0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99}: 56 settings (`TAU_SEND`, `TAU_FIX` in `policy/families.py`). The threshold policy's grid is its risk thresholds (0.25, 0.75, 1.01), and the static four-state classifier's its confidence levels (0.5 to 0.95).
- **Procedure:** Learn-then-Test. Order each family's grid on the tune split, most cautious first; on the calibration split compute each setting's Hoeffding–Bentkus p-value for H0: P(unsafe | sent) > α; certify in fixed sequence until the first p > δ; among certified settings choose the highest useful coverage on calibration; report that setting once on test.
- **Issuer-level sensitivity check (risk R-14):** the same certification with each issuer as one draw; reported next to the main certificate.
- **Comparator:** SCoRE (`score-select`), whose guarantee is on expected risk, not a high-probability bound.
- **Fallback when repair becomes unsafe. Open (Sharaf):** the grid has no setting that never repairs, so in the transfer study recalibration with v0's models cannot fall back to send-or-abstain; adding never-repair settings to the fixed-sequence chain blocks certification on smaller calibration sets (D-082). Proposed: keep the grid, and add a separate send-or-abstain fallback family certified with half of δ, used only when no outcome-aware setting certifies.
- **Outcome models:** LightGBM for P(unsafe) and P(fix), from pre-action features only; TabICLv2 as the one challenger.

## 5. Metrics

| Paper | Metric | Definition |
| --- | --- | --- |
| Policy | Emission coverage | Share of items where an answer is sent (original or repaired) |
| Policy | Residual risk | Share of sent answers that are unsupported (the certified quantity) |
| Policy | Useful coverage | Share of items where a supported, useful answer is sent |
| Policy | Flip matrix, regret | Each answer's state before and after repair; useful coverage below the stored-outcome oracle |
| Detection | Span F1 by slot; wrong-context recall; clean false-alarm rate; AUROC; Brier score and ECE; coverage at certified selective risk | As in the revised plan. **Open (M.L Ahamed):** the span-matching rule for F1 (proposed: token-level overlap) and how ambiguous labels count (proposed: left out of span F1, reported separately) |
| Repair | Correction rate; new-error rate; damage rate; information preserved (human-scored sample); abstention calibration; valid-program rate in the 4-bit runtime; latency | As in the revised plan. **Open (M.S.A Ahamed):** how the correction rate is matched for R-H1 (proposed: compare new-error rates along each system's correction-versus-new-error frontier, at the free-rewrite baseline's correction rate) |

**Ambiguous labels in risk metrics. Open (all):** proposed default: an answer labelled ambiguous counts as unsafe in residual risk (the conservative choice) and is reported separately.

## 6. Statistics

- **Intervals:** issuer-clustered bootstrap (`stats/bootstrap.py`): whole issuers resampled with replacement, 2,000 resamples, 95% percentile intervals, seed 0.
- **Counts:** issuers, questions and answers are always reported separately.
- **Recalibration label sizes (D-H3, P-H3):** 25, 50, 100 and 200 labels.
- **Repair labelling rule:** if code and humans disagree on more than about 10% of the 400 sampled repairs, human checking of repairs is expanded.
- **Groups:** residual risk is also reported by group (numeric vs narrative, US vs Sri Lanka).

## 7. Secondary analyses

Not hypothesis tests; reported with the same intervals.

- Detection: A alone, B alone and A + B; with vs without the slot head; four released baselines (LettuceDetect v1-large and v2, HHEM-2.1-Open, Granite Guardian 4.1-8B).
- Repair: rule-only COPY and CALCULATE; zero-shot programs (2B and 9B); supervised vs self-trained; gold vs predicted spans; with vs without KEEP training; dependency closure on vs off.
- Policy: always keep; always repair; static four-state classifier; stored-outcome oracle; LightGBM vs TabICLv2; v0 policy on v1 outputs as-is, recalibrated and refitted; train on Qwen answers, test on Gemma answers.
- The real-world condition (D-070): the full pipeline with automatically extracted Sri Lankan tables, reporting emission coverage, residual risk and useful coverage.

## Frozen inputs

Filled in at filing with `faithguard hashes`.

| Input | Hash |
| --- | --- |
| Split manifest | `db0433453c32632ecd44f6ecaab25b247ec509cdef2a6836673223ef3a03c771` |
| Main questions with frozen evidence (`questions.jsonl`) | To fill at lock (after every table and question is cross-checked) |
| The 800 answers | To fill at lock |
| Detector, fusion and ablation variants | To fill (M.L Ahamed) |
| Repairer v1 and repair variants | To fill (M.S.A Ahamed) |
| Code version used for the analysis | Commit hash at filing |
