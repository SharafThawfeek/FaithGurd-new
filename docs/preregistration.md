# FaithGuard pre-registration

**Status: filed on 2026-10-29 as the git tag `prereg-v1` (D-104), before any system had been run on a test or calibration answer and before any of them was labelled or scored.** The evidence is frozen, the test set locked (788 items after excluding 6 ambiguous questions, D-104) and the components frozen (the hashes in [Frozen inputs](#frozen-inputs)). Every point the plan left open is settled (D-089, D-093, D-102). Anything changed after filing is recorded as a deviation in the decision log.

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
| Labels | Annotation guide v2 ([annotation-guide.md](annotation-guide.md), D-068): spans with slot types, status (correct, incorrect, ambiguous, unhelpful) and usefulness. **Who labels (D-100):** run only after filing and only on questions with a second reader, `faithguard labelling triage` gives an answer a code label (correct, useful, no spans) when the question asks for a number (not narrative or comparison questions, nor a difference between two entities), every number matches a gold value read with the evidence and one is the answer, every year, "this/last year", Group/Company/Bank word, metric name and unit word belongs to its figure's cells, "from" and "to" introduce the earlier and later figure of a change, every direction word says how the two cells moved, and the answer has no negation, hedge or guess, no explanation or judgement, no figure in words or fraction, no quarter or part-year, no percentage points (except for a difference of two percentages), no foreign currency, no currency after a bare figure printed in thousands or millions, no "loss" beside a figure that is not a loss and no thinking leak (the rules in `evaluate/triage.py` and `evaluate/score.py` at the filing commit). A person labels every other answer, plus a stratified random audit of 150 code labels (seed 2026; strata: country, generator, one figure or several) hidden among the other tasks. An audited answer counts as overruled if any person's label overrules it, unless the adjudicator's label says otherwise; the audit decides nothing until every audited answer has a person's label. The code labels stand only if at most 1 of the 150 is overruled; otherwise a person labels every code-labelled answer. An overruled audit answer, or any person's ambiguous label, sends the other code-labelled answers to the same question to a person. Code labels enter the gold store only once every answer routed to a person has a person's label. Each answer's deciding label is the adjudicated one, else a person's, else its code label. A second labeller labels 80 tasks (60 person-routed and 20 audit answers) for Cohen's kappa per field, and disagreements are adjudicated. **Who does it (D-103):** the second reader, the labeller of the routed and audited answers, the second labeller and the adjudicator are separate, blind passes by Claude, not people; every paper states this, and kappa is agreement between Claude's passes, not between people |
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

**How each is decided (D-102).** "Higher" and "lower" mean that the issuer-clustered bootstrap 95% interval (2,000 resamples, §6) of the paired difference on the test split excludes zero in the stated direction; otherwise the hypothesis is rejected as "no difference". In detail:

- **D-H1:** each model's threshold is set on the calibration split so that it flags 10% of the correct answers there; wrong-context recall (answers with an entity_scope, metric or period span) is compared on test at those thresholds. If test has fewer than 20 such answers, D-H1 is reported as untestable.
- **D-H2:** span F1 of A + B minus span F1 of B on the Sri Lankan test answers (B's spans are the claims it flags; A + B's are the claims the fused probability puts at 0.5 or more).
- **D-H3:** the threshold certified on US calibration answers fails if the lower end of its Sri Lankan test risk interval is above α, and is restored if, recalibrated on 100 Sri Lankan calibration labels, its Sri Lankan test risk is at most α.
- **R-H1 (replaces the frontier rule left Open):** each system at its own operating point; confirmed if the new-error rate of programs minus that of free rewriting is below zero and programs' correction rate is no more than 5 points below rewriting's (a non-inferiority margin). If programs correct more than 5 points less, R-H1 is reported as not decidable at a matched rate.
- **R-H2:** correction rate of the self-trained model (stage B) minus the supervised one (stage A) on held-out basis errors and on Gemma's answers; confirmed if above zero on both.
- **R-H3:** damage rate with Channel A's spans, KEEP-trained minus no-KEEP; confirmed if below zero.
- **P-H1:** useful coverage of the outcome-aware policy minus the calibrated detector threshold, both certified. If the threshold policy certifies no setting it sends nothing (useful coverage 0), which is reported as such; as a secondary analysis it is also compared at its most cautious uncertified setting.
- **P-H2:** the outcome-aware policy certifies on calibration and its test useful coverage is above the threshold policy's (as in P-H1).
- **P-H3:** unsafe as-is if the lower end of the v0 policy's test risk interval on v1's records is above α; restored if, recalibrated on 100 v1 labels, it certifies and its test risk is at most α.

## 3. Primary comparisons

One per paper; everything else is secondary.

| Paper | Primary comparison | Measured on |
| --- | --- | --- |
| Detection | Channel A trained with vs without XBRL-mined negatives: wrong-context recall at an equal clean false-alarm rate | Human-labelled natural answers, test split |
| Repair | Edit programs (repairer v1, D-101) vs free rewriting (same backbone, same data): new-error rate, with correction rate within a 5-point margin (§2) | Natural errors with gold spans, test split |
| Policy | Outcome-aware policy vs calibrated detector threshold: useful coverage, both certified at α = 0.10 | Test split, policies certified on the calibration split |

## 4. Policy certification

From `faithguard.policy` and `faithguard.stats` at the code version named at filing.

- **Risk target and confidence:** α = 0.10; δ = 0.05.
- **Certified quantity:** the share of sent answers that are unsupported, written as the per-item loss 1{unsafe sent} − α · 1{substantive sent} with expectation at most 0, so repair-introduced errors count.
- **Grid (outcome-aware policy):** send the original if P(unsafe) < τ1; otherwise repair if P(fix) > τ2; otherwise abstain. τ1 ∈ {0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5} and τ2 ∈ {0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99}: 56 settings (`TAU_SEND`, `TAU_FIX` in `policy/families.py`). The threshold policy's grid is its risk thresholds (0.25, 0.75, 1.01), and the static four-state classifier's its confidence levels (0.5 to 0.95).
- **Procedure:** Learn-then-Test. Order each family's grid on the tune split, most cautious first; on the calibration split compute each setting's Hoeffding–Bentkus p-value for H0: P(unsafe | sent) > α; certify in fixed sequence until the first p > δ; among certified settings choose the highest useful coverage on calibration; report that setting once on test.
- **Which records play which part on the benchmark (D-102):** the benchmark has only calibration and test issuers, so the outcome models are fitted on the controlled track's fit records and each grid is ordered on its tune records; certification uses the benchmark's calibration answers and the result is reported once on its test answers. The natural answers' replay records take an original's state from its label and a repair's from the gold scorer read with the evidence.
- **Issuer-level sensitivity check (risk R-14, D-102):** the chosen setting's one-sided 95% upper bound of residual risk on calibration from an issuer-clustered bootstrap (2,000 resamples); it passes when the bound is at most α. (An issuer-level Hoeffding–Bentkus p-value cannot pass with 24 calibration issuers even when every issuer sends everything without error, so it is reported only for reference.)
- **Comparator:** SCoRE (`score-select`), whose guarantee is on expected risk, not a high-probability bound.
- **When no setting certifies:** the grid has no setting that never repairs, and none is added (D-082, D-093). If no setting certifies, the policy withholds every answer and this is reported; in the transfer study, refitting is the remedy reported. The controlled-track rehearsal with real trained-repairer replays found the v0 policy safe as it is (D-093).
- **Outcome models:** LightGBM for P(unsafe) and P(fix), from pre-action features only, is the primary model and the one deployed. The one challenger is a neural outcome model (D-096): the v2 mmBERT encoder Channel A starts from, fine-tuned on a GPU with one output per target, reading the question, the evidence (focused as for Channel A), the answer and the same pre-action features written as text. It is trained on the fit split with early stopping on the tune split, never sees a calibration or test label, and is certified on the same grid with the same α and δ.

## 5. Metrics

| Paper | Metric | Definition |
| --- | --- | --- |
| Policy | Emission coverage | Share of items where an answer is sent (original or repaired) |
| Policy | Residual risk | Share of sent answers that are unsupported (the certified quantity) |
| Policy | Useful coverage | Share of items where a supported, useful answer is sent |
| Policy | Flip matrix, regret | Each answer's state before and after repair; useful coverage below the stored-outcome oracle |
| Detection | Span F1 by slot; wrong-context recall; clean false-alarm rate; AUROC; Brier score and ECE; coverage at certified selective risk | As in the revised plan. Span F1 is computed on character overlap between predicted and gold spans, as LettuceDetect reports span-level results and `train/detector_eval.py` computes it; answers labelled ambiguous are left out of span F1 and reported separately (D-089) |
| Repair | Correction rate; new-error rate; damage rate; information preserved (human-scored sample); abstention calibration; valid-program rate in the 4-bit runtime; latency | As in the revised plan. R-H1 compares each system at its own operating point with a 5-point non-inferiority margin on correction rate (§2, D-102), which settles the point left open here. "Information preserved" is scored by Claude on a sample, not by a person (D-103) |

**Ambiguous labels in risk metrics:** an answer labelled ambiguous counts as unsafe in residual risk (the conservative choice) and is reported separately (D-089).

**The gold scorer on natural answers (D-100):** a repair's state, and an original's code label, come from `score_text` read with the answer's evidence. A number matches a gold value at its printed precision; a change may be stated by its size and a direction word that says how the cells moved; a loss may be written as a positive figure right after "loss", or in accounting brackets; a ratio may be written as a percentage; the constants of a worked calculation are skipped. Template answers (the controlled track) are scored without the evidence.

## 6. Statistics

- **Intervals:** issuer-clustered bootstrap (`stats/bootstrap.py`): whole issuers resampled with replacement, 2,000 resamples, 95% percentile intervals, seed 0.
- **Counts:** issuers, questions and answers are always reported separately.
- **Recalibration label sizes (D-H3, P-H3):** 100 and 200 labels, and all available. 25 and 50 are dropped: at the send rates seen, they cannot certify α = 0.10 even with no error (D-102).
- **Repair labelling rule (D-100):** people check at least 50 changed repairs from each R-H1 arm (edit programs, free rewriting) and 50 across the other variants; if code and people disagree on more than 10% of an arm's checked repairs, people check every changed repair of that arm.
- **Code labels (D-100):** the audit's overruled share is reported with its 95% Clopper–Pearson upper bound. Every certificate is also computed with each unaudited code-labelled sent answer counted unsafe at that upper bound, and every detection metric again on person-labelled answers only; whether P-H1 to P-H3 or D-H1 to D-H3 change is reported. Code labels and the rule checker read numbers with the same code (`calc/numbers.py`, `claims.py`), so errors that code cannot see escape both (R-25).
- **Groups:** residual risk is also reported by group (numeric vs narrative, US vs Sri Lanka).

## 7. Secondary analyses

Not hypothesis tests; reported with the same intervals.

- Detection: A alone, B alone and A + B; with vs without the slot head; four released baselines (LettuceDetect v1-large and v2, HHEM-2.1-Open, Granite Guardian 4.1-8B). Every detector reads the same evidence text: above 30 rows, only the rows the rule checker traced the claims to and the line items the claims or the question name (`faithguard.focus`, D-084, D-091).
- Repair: rule-only COPY and CALCULATE; zero-shot programs (2B and 9B); supervised vs self-trained; gold vs predicted spans; with vs without KEEP training; dependency closure on vs off.
- Policy: always keep; always repair; static four-state classifier; stored-outcome oracle; LightGBM vs the neural outcome model (AUROC, Brier score, ECE, certified useful coverage and the certification-budget curve, D-096); v0 policy on v1 outputs as-is, recalibrated and refitted; train on Qwen answers, test on Gemma answers.
- The real-world condition (D-070): the full pipeline with automatically extracted Sri Lankan tables, reporting emission coverage, residual risk and useful coverage.

## Frozen inputs

Filled in at filing with `faithguard hashes`.

| Input | Hash |
| --- | --- |
| Split manifest | `db0433453c32632ecd44f6ecaab25b247ec509cdef2a6836673223ef3a03c771` |
| Main questions with frozen evidence (`questions.jsonl`) | `db45d0304502f251…` ([manifests/locked-test.json](../manifests/locked-test.json); every question checked by the second-reader pass, D-103) |
| The 800 answers | Qwen `b1360509876d3823…`, Gemma `133940729caba578…` (unchanged since D-073) |
| The locked test set: 788 items, 6 ambiguous questions excluded (D-104) | `items-locked.jsonl` `203c6a1706e5a2ef…`; [manifests/excluded-questions.json](../manifests/excluded-questions.json) |
| Detector, fusion and ablation variants | Channel A and the no-slot ablation in [manifests/frozen-detector.json](../manifests/frozen-detector.json); the no-XBRL ablation is added there when its download ends; the fusion is refitted on calibration answers as §2 states (no frozen weights); Channel A flags a claim for repair at 0.5 |
| Repairer v1 and repair variants | [manifests/frozen-repair.json](../manifests/frozen-repair.json): v1 (D-101), stage A, no-KEEP, stage B; the free-rewrite baseline retrained on v1's data is added when its run ends, before any of its outputs on main answers exist |
| Neural outcome model (D-096) | Its predictions file in frozen-detector.json; the model in Kaggle kernel faithguard-neural-outcome-model (run of 2026-10-28) |
| Code version used for the analysis, including the triage and scorer rules (D-100) and `evaluate/analysis.py` | The commit tagged `prereg-v1` |
