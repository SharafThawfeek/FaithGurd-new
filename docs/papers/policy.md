# Should We Fix It? Certified Accept–Repair–Abstain Policies for Financial QA and Their Fragility When the Repairer Changes

Sharaf, M.L Ahamed, M.S.A Ahamed

> **Draft status (2026-10-29).** The test set is locked (394 questions, 788 answers) and labelled (D-103 to D-105). Filled now: the benchmark and its labels (§5), where the original answers' outcomes come from (§4.1), the limitations and the AI assistance statement. Still waiting for the main runs (detectors, repairers and policies on the locked answers): every result on natural answers, which stays a placeholder, `[RESULT: …]`, filled in phase 7 from the pre-registered analysis ([preregistration](../preregistration.md)). The introduction, related work and the rest of the method are drafts to revise; the method follows the filed pre-registration and D-100 to D-106. Numbers marked *development* come from the controlled track and test no hypothesis. Citations marked `[verify]` or `[CITE: …]` must be checked against the source and entered in [related-work/policy.md](../related-work/policy.md) before submission.

## Abstract

A system that checks AI answers about financial reports can send an answer as it is, repair it, or withhold it. Which action to take depends on what each would produce, and a repair can itself introduce errors. We build a paired replay dataset in which every action is played out on every answer and every outcome is scored, including answers that repair made worse. On it we fit two outcome models, the chance the original answer is unsafe and the chance repair returns a safe and useful answer, and choose among a pre-registered grid of decision rules with Learn-then-Test, certifying with high probability that at most α = 10% of sent answers are unsupported, repair-introduced errors included. On 788 answers about US and Sri Lankan annual reports, labelled by separate blind passes of Claude (Anthropic) rather than by people, the outcome-aware policy `[RESULT: useful coverage against a certified detector threshold]`. We also measure how many labels certification needs, and what happens to a certified policy when the repairer behind it is replaced: `[RESULT: as-is, recalibrated, refitted]`.

## 1. Introduction

Detectors and repairers for answer faithfulness are usually evaluated on their own. A deployed system needs a decision on top of them: for each answer, send it, try to repair it, or withhold it and show the user the evidence instead. That decision sets what the user experiences, how often they get an answer, and how often the answer they get is wrong.

The obvious rule is a threshold on the detector's risk: send answers below it, withhold the rest. It ignores repair. A better rule asks what each action would produce. If the original is likely wrong but the evidence holds the right values, repair may return a correct answer; if the evidence lacks them, repair will fail or, worse, produce a confident wrong answer. Predicting outcomes, not just risk, should let a system return more correct answers at the same error rate. But the error rate must count the errors repair introduces, and it must hold on new data, not just on average.

We make three contributions:

1. **A paired replay dataset.** Every action is run on every item, and each outcome is scored: unsupported, supported but unhelpful, or supported and useful. A flip matrix records each answer's state before and after repair, so answers repair made worse are counted rather than hidden in a net gain.
2. **A certified outcome-aware policy.** Two outcome models feed a pre-registered grid of decision rules; Learn-then-Test with Hoeffding–Bentkus p-values certifies the share of unsupported answers among those sent, with repair-introduced errors included, on an issuer-disjoint calibration set. We report how many labelled answers such a certificate needs, which matters to any team with a small labelling budget.
3. **A transfer study.** When the repairer changes, a certified policy's guarantee no longer covers the new outcomes. We test the old policy on the new repairer as it is, after recalibration with 100 or 200 new labels or all available, and after refitting.

We do not claim the first accept-repair-abstain policy, nor the first risk-controlled abstention (§2), and the replay study is not causal inference: it compares stored outcomes of actions that were all actually run.

## 2. Related work

**Selective prediction and abstention.** Selective classification lets a model abstain when unsure, trading coverage for risk (Geifman and El-Yaniv, 2017). Our policy extends the choice to a third action, repair, whose outcome must itself be predicted.

**Distribution-free risk control.** Risk-controlling prediction sets (Bates et al., 2021) and Learn-then-Test (Angelopoulos et al., 2021 `[verify]`) certify that a chosen parameter keeps a risk below α with probability at least 1 − δ, using p-values such as the Hoeffding–Bentkus bound and multiple-testing procedures such as fixed-sequence testing. We apply Learn-then-Test to a grid of accept-repair-abstain rules, with a linearised loss so that a ratio (errors among sent answers) can be certified. `[CITE: SCoRE / score-select — open and verify]` offers a selection procedure whose guarantee holds in expectation; we use it as a comparator for the send-or-abstain decision.

**Accept-repair-abstain policies.** `[CITE: CORA — open and verify]` and `[CITE: Release Control — open and verify]` already combine accepting, repairing and abstaining. We differ in certifying the whole pipeline's risk including repair-introduced errors, in reporting the label budget, and in studying transfer across a change of repairer. `[CITE: Conformal Policy Control — verify]` is a possible fourth transfer arm (stretch).

**Outcome models.** We use gradient-boosted trees (LightGBM; Ke et al., 2017) and, as one challenger, a fine-tuned encoder of the ModernBERT family `[CITE: ModernBERT — verify]`, `[CITE: mmBERT — verify]`: the one the companion detection paper's learned detector starts from `[CITE: LettuceDetect — verify]`.

## 3. Setting

Each item is a question, frozen evidence and an answer. A detector (companion detection paper) produces claim-level verdicts and a calibrated risk; a repairer (companion repair paper) can return a repaired answer or withhold. Each action's outcome is one of:

| State | Meaning |
| --- | --- |
| unsupported | At least one claim is not supported by the evidence (unsafe) |
| supported, unhelpful | Nothing is wrong, but the answer does not give what was asked |
| supported, useful | Correct and answers the question |
| abstained | Nothing sent; the user sees the evidence and a reason |

The policy's goal is to send as many supported, useful answers as possible while keeping the share of unsupported answers among those sent at most α.

## 4. Method

### 4.1 Replay

For every item the replay harness runs the detector, records the features known before any action, and then plays out all three actions: send the original, repair (scored as abstained when the repairer withholds), and abstain. Each sent text is scored against the gold store. The outcome of an original answer comes from its label on the benchmark (§5); an answer labelled ambiguous counts as unsafe. These labels are not made by people: the labeller, the second labeller and the adjudicator are separate, blind passes by Claude (Anthropic), as is the second reader who re-derived every gold answer before the test set was locked (D-103). Repaired answers are scored by code, the gold scorer reading each repair with its evidence against the gold answer written with each question, with a sample checked by a further blind Claude pass (D-106; repair paper). Gold labels live in a separate store that no component reads at decision time.

### 4.2 Features and outcome models

Features are pre-action only: the detector's risk; counts of claims, of supported, unsupported and unverifiable claims, and of evidence links; failing slots by type; missing operands; whether every failing claim has a correct value in the evidence (evidence sufficiency); whether the answer addresses the question; the size of the evidence; percentage and directional claims; the learned detector's highest span score; and the question type. Nothing comes from the gold store or from a repair attempt.

The benchmark has no fit or tune issuers, so the policy is fitted and tuned on the controlled track's fit and tune records (D-102). Two LightGBM models are trained on the controlled track's fit split:

- **P(unsafe)**: the chance the original answer is unsupported;
- **P(fix)**: the chance repair returns a supported, useful answer.

The one challenger is a neural outcome model trained for the policy. It is the multilingual ModernBERT encoder (mmBERT) that the detection paper's learned detector starts from, fine-tuned on a GPU with one sigmoid output per outcome on its mean-pooled representation, both trained together with binary cross-entropy. LightGBM sees only the detector's summary features. The encoder reads the question and the evidence (focused on the rows the claims need when the evidence is large), paired with the answer and the same pre-action features written as text, cut to 1,024 tokens from the end of the evidence. It is trained on the controlled track's fit split for at most two epochs, keeping the checkpoint with the lowest loss on its tune split, and never sees a calibration or test label. Both models are certified on the same grid with the same α and δ, and compared by AUROC, Brier score, ECE, certified useful coverage and the certification budget. The comparison asks whether reading the text adds anything to the detector's summary. LightGBM remains the primary model and the one deployed.

### 4.3 Policy families

| Family | Rule | Grid (pre-registered) |
| --- | --- | --- |
| Outcome-aware (the method) | Send if P(unsafe) < τ1; else repair if P(fix) > τ2; else abstain | τ1 ∈ {0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.5} × τ2 ∈ {0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99}: 56 settings |
| Calibrated detector threshold | Send if the detector's risk is below a threshold, else abstain | 0.25, 0.75, 1.01 |
| Threshold v0 | As above, but repair when the evidence holds every correct value | 0.25, 0.75, 1.01 |
| Static four-state classifier | Clean → send, fixable → repair, otherwise abstain, above a confidence | 0.5 to 0.95 |
| Always send; always repair | Fixed strategies | – |
| Stored-outcome oracle | The best action per item in hindsight | Upper bound only |

### 4.4 Certification

The certified quantity is the share of unsupported answers among sent answers. Written as a per-item loss,

$$
L = \mathbf{1}\{\text{unsafe sent}\} - \alpha \cdot \mathbf{1}\{\text{sent}\}, \qquad \mathbb{E}[L] \le 0 \iff P(\text{unsafe} \mid \text{sent}) \le \alpha ,
$$

so an answer repair made wrong counts exactly like an original that was wrong. For each family, Learn-then-Test (i) orders the grid on the tune split, most cautious first; (ii) on the calibration split computes each setting's Hoeffding–Bentkus p-value for H0: E[L] > 0 and certifies settings in that order until the first p-value above δ; and (iii) among the certified settings chooses the one with the highest useful coverage on calibration. Because the order comes from a separate split, every certified setting keeps the guarantee at once, so choosing among them is allowed. The chosen setting is then reported once on the test split. On the benchmark, the tune split is the controlled track's tune records, and the calibration and test splits are the benchmark's calibration and test answers (D-102). We use α = 0.10 and δ = 0.05.

If no setting certifies, the policy withholds every answer, which is safe, and this is reported. The grid has no "never repair" setting: adding such settings to the fixed sequence blocked certification on smaller calibration sets in a synthetic study, and the controlled-track rehearsal of the transfer study with real repairer replays did not need one (§6.1).

**Issuer dependence.** Answers about the same company are related. As a sensitivity check, we compute the chosen setting's one-sided 95% upper bound of residual risk on calibration from an issuer-clustered bootstrap (2,000 resamples); the check passes when the bound is at most α (D-102). An issuer-level Hoeffding–Bentkus p-value cannot pass with 24 calibration issuers even when no answer is wrong, so it is reported only for reference.

**Code labels.** The pre-registered sensitivity analysis that counts each unaudited code-labelled sent answer as unsafe at the audit's upper bound is moot: the code labels fell, and no code label decides any answer (§5, D-105).

**Label budget.** With zero errors among n independent sent answers, the exact 95% upper bound on the error rate is 1 − 0.05^(1/n), so 29 sent answers are needed to certify α = 0.10; the linearised Hoeffding–Bentkus certificate used here needs 32. We also draw random calibration subsets of increasing size and report how often a setting certifies and the useful coverage it then reaches.

### 4.5 Transfer when the repairer changes

Two replays of the same items differ only in their repairer: v0 is rule-only (copy and calculate from the rule checker's correct-value expressions), v1 the trained edit-program repairer. The v0 policy's outcome models are fitted on v0's replays of the fit records and its grid ordered on the tune records (on the benchmark, the controlled track's, D-102), and it is certified on v0's calibration records. Three arms are scored on v1's test records:

- **as-is**: v0's outcome models and certified setting, unchanged;
- **recalibrated**: v0's outcome models, with the setting recertified on 100 and 200 of v1's calibration labels (50 random draws each) and on all of them. Sizes 25 and 50 are dropped: at the send rates seen they cannot certify α = 0.10 even with no error (D-102);
- **refitted**: outcome models fitted on v1's replays of the fit records and certified on v1's calibration records.

A second shift, between generators, trains on Qwen answers and tests on Gemma answers.

## 5. Experimental setup

**Benchmark.** 400 question groups about 48 US and Sri Lankan annual reports, each answered by two generators, Qwen3.5-9B and Gemma 4 12B (800 answers; benchmark paper `[cross-reference]`). Before the test set was locked, a second-reader pass re-derived every gold answer from the report and checked the table rows it uses. It found no wrong gold, but 6 questions whose wording admits a second reading; these are excluded, so the locked set is 394 questions and 788 answers (D-104). Policies are certified on the calibration issuers' answers (396) and reported on the test issuers' answers (392); the splits are issuer-disjoint. The benchmark has no fit or tune issuers, so, as pre-registered, the outcome models are fitted on the controlled track's fit records and each grid is ordered on its tune records (D-102).

**Labels.** Each answer has a status (correct, incorrect, ambiguous or unhelpful), a usefulness label and spans with slot types, under annotation guide v2. The pre-registered protocol (D-100) let code label 311 answers correct, those whose every number matched the gold cells and whose wording could not still make them wrong, and routed the other 477 to the labeller, with a stratified random audit of 150 code labels hidden among them. The code labels were to stand only if at most 1 of the 150 was overruled. The audit overruled 4 (95% upper bound 6.0%), so the code labels fell as pre-registered: the labeller labelled the remaining code-labelled answers, and no code label decides any answer (D-105). A first labelling pass was discarded before anything used it, because the tasks' evidence left out each table's units note, which the generators had seen; the answers were labelled again with the note restored. Of the 788 answers, 773 are decided by the labeller and 15 by the adjudicator: 592 correct, 177 incorrect (22.5%; 25.3% of the 672 numeric answers), 16 unhelpful and 3 ambiguous. A second labeller labelled 80 pre-registered tasks blind. Status agreed on 95% of them (Cohen's kappa 0.89), usefulness on 91% (kappa 0.71) and whether an answer has a wrong span on all 80 (kappa 1.00); the 15 tasks whose labels differed went to the adjudicator, whose label decides. The rule checker flags 144 of the 170 incorrect numeric answers.

**Who labels.** The labeller, the second labeller, the adjudicator and the second reader are separate, blind passes by Claude (Anthropic), not people (D-103), and so is the check of repaired answers against the gold scorer (D-106). Kappa here measures agreement between Claude's passes, not between people. There is no human agreement figure and no external adjudicator.

**Controlled track** *(development rehearsal)*. FinQA and TAT-QA items with planted errors, where every outcome is scored automatically: 13,383 fit, 2,447 tune, 5,423 calibration and 6,450 test items from 984, 194, 401 and 391 issuers.

**Metrics.** Emission coverage (share of items sent), residual risk (share of sent answers unsupported, the certified quantity), useful coverage (share of items where a supported, useful answer is sent), the flip matrix, regret against the oracle, and Brier score and ECE per outcome model. Residual risk is also reported by group: numeric against narrative questions, US against Sri Lanka. An answer labelled ambiguous counts as unsafe. Intervals come from an issuer-clustered bootstrap (2,000 resamples).

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| P-H1. The outcome-aware policy beats the threshold policy | Higher useful coverage at equal certified α | No gain; the simpler policy is recommended |
| P-H2. α = 0.10 is certifiable at useful coverage | Certificate holds with coverage above the threshold policy | Not reachable; the budget curve says how many labels would be needed |
| P-H3. The v0 policy is unsafe on v1; recalibration restores safety | Risk above α as-is, within α after recalibration | Safe as-is, or refitting is needed; both are findings |

"Higher" means that the issuer-clustered bootstrap 95% interval of the paired difference on the test split excludes zero in that direction; otherwise the hypothesis is rejected as "no difference" (D-102). P-H1 compares the useful coverage of the outcome-aware policy and the calibrated detector threshold, both certified. If the threshold policy certifies no setting, it sends nothing (useful coverage 0); as a secondary analysis it is also compared at its most cautious uncertified setting. P-H2 holds if the outcome-aware policy certifies on calibration and its test useful coverage is above the threshold policy's. For P-H3, the v0 policy is unsafe as-is if the lower end of its test risk interval on v1's records is above α, and restored if, recalibrated on 100 v1 labels, it certifies and its test risk is at most α.

## 6. Results

### 6.1 Development rehearsal (controlled track; not a test of the hypotheses)

On template answers the rule checker almost determines the outcomes, so every outcome model is near-perfect (P(unsafe) AUROC 0.997 for LightGBM and the neural model; P(fix) 0.991 and 0.993) and policies that repair look alike. The rehearsal checks the machinery; the comparison that matters is on natural answers.

| Policy (certified at α = 0.10) | Sent | Wrong among sent | Useful |
| --- | --- | --- | --- |
| Always send (not certifiable) | 100.0% | 79.0% | 21.0% |
| Always repair | 74.0% | 1.6% | 72.7% |
| Calibrated detector threshold | 21.5% | 2.9% | 20.9% |
| Outcome-aware (LightGBM) | 73.8% | 1.6% | 72.7% |
| Outcome-aware (neural outcome model) | 73.5% | 1.3% | 72.5% |
| Oracle (hindsight) | 72.9% | 0.0% | 72.9% |

SCoRE, deciding only send or abstain with the same P(unsafe) scores, sent 22.7% with 5.5% wrong among sent. With LightGBM, certification succeeded in 1% of draws with 100 calibration answers, 75% with 200 and every draw from 400. Resampling whole issuers, the chosen setting's one-sided 95% upper bound of residual risk on calibration was 0.026, so the issuer-level check passes (the issuer-level p-value, for reference, was 0.002).

The neural outcome model's probabilities are slightly better than LightGBM's on test (Brier score 0.0069 against 0.0075 for P(unsafe), 0.0123 against 0.0127 for P(fix)). Its certified policy sends 1.3% wrong answers [0.7%, 1.9%] against 1.6% [1.0%, 2.2%], at the same useful coverage within the intervals, and it certifies on smaller calibration sets more often (6% of draws at 100 answers, 84% at 200). One feature of the controlled track favours a model that reads the evidence: the error injector creates a missing operand by deleting the needed cell, so that table row reads shorter than its neighbours, a cue natural answers lack and the checker's features mostly miss. Without those items the comparison is unchanged (P(fix) AUROC 0.973 against 0.967, Brier 0.0116 against 0.0123), and on those items the two models are level. The gain comes mostly from sign errors (P(unsafe) Brier 0.0096 against 0.0189), while the encoder is slightly worse on clean answers.

**Transfer rehearsal.** 4,000 items (1,000 per split) were replayed with the trained stage A repairer standing in for v1 and paired with the rule repairer's replays of the same items. The v0 policy sent 72.2% of v0's test answers with 1.9% wrong among them; unchanged on v1's test answers, it sent 71.6% with 1.0% wrong. Recalibrated on v1's labels it certified in 76% of draws with 100 labels and in every draw from 200; refitted, it sent 73.2% with 1.0% wrong. On template answers the trained repairer is at least as safe as the rules, so the old policy transfers as it is; the predicted failure of P-H3 does not occur in rehearsal. Replayed again with the frozen repairer v1 itself (3.11 GPU hours), the result is the same: unchanged on v1's test answers the v0 policy sent 71.6% with 1.0% wrong; recalibrated it certified in 48% of draws with 100 labels and in every draw from 200 (mean 1.0% wrong among sent, every certified draw within α); refitted, it sent 72.9% with 1.0% wrong.

### 6.2 Natural answers (test split)

- P-H1: `[RESULT]`
- P-H2, with the budget curve on natural answers: `[RESULT]`
- P-H3, with repairer v1: `[RESULT]`
- Flip matrix, regret, groups, the neural outcome model against LightGBM, the generator shift, the issuer-level check and SCoRE: `[RESULT]`

## Limitations

- **Exchangeability.** The certificate assumes calibration and test answers are exchangeable. Splits are issuer-disjoint and drawn from the same population of listed companies; the issuer-level check shows how much the per-answer guarantee relies on answers being independent.
- **Small calibration sets.** 396 calibration answers place the certificate near the edge of what the budget curve shows is needed; we report when it fails rather than loosening α.
- **Labels made by AI, not people.** Every label, check and adjudication on the benchmark is a separate, blind pass by Claude (Anthropic): the labeller, the second labeller, the adjudicator and the second reader of the gold answers (D-103), and the check of repaired answers (D-106). The kappa values in §5 measure agreement between Claude's passes, not between people; there is no human agreement figure and no external adjudicator. Passes by the same model may share mistakes that agreement between them cannot show, and those mistakes would pass into the outcome labels the policy is certified on.
- **Repair outcomes scored by code.** Repaired answers are judged against gold answers by code. A blind Claude pass labels a sample of changed repairs of numeric test answers with the annotation guide: 50 from each R-H1 arm and 50 pooled across the other repair variants, drawn with a fixed seed; if code and the check disagree on more than 10% of a group's checked repairs, every changed repair of that group is labelled (D-106). The check is not made by people.
- **No never-repair fallback.** If a new repairer made repair unsafe, the grid could only certify by withholding; refitting is the remedy we report.
- **Replay, not causal inference.** Every action was actually run on every item; we compare stored outcomes and make no causal claim beyond them.
- **Authoring**: see the AI assistance statement.

## AI assistance statement

`[Finalise before submission.]` Claude (Anthropic) wrote most of the project's code, drafted the benchmark questions and gold answers, produced the pilot labels used only for design decisions, and drafted this paper. Claude also checked and labelled the benchmark, in separate, blind passes (D-103): the second-reader pass that re-derived the 400 main questions and checked their tables before the test set was locked, the labelling of all 788 locked answers, the second labelling of 80 tasks for kappa, and the adjudication of the 15 tasks where the two labellings differed. The check of a sample of repaired answers against the gold scorer is also a blind Claude pass (D-106). No person labelled, checked or adjudicated the benchmark. The authors take responsibility for all content.

## References

`[Check every entry against the source and fill docs/related-work/policy.md.]`

- Angelopoulos, A. N., Bates, S., Candès, E. J., Jordan, M. I. and Lei, L. 2021. Learn then Test: Calibrating predictive algorithms to achieve risk control. arXiv. `[verify venue]`
- Bates, S., Angelopoulos, A., Lei, L., Malik, J. and Jordan, M. 2021. Distribution-free, risk-controlling prediction sets. Journal of the ACM. `[verify]`
- Geifman, Y. and El-Yaniv, R. 2017. Selective classification for deep neural networks. NeurIPS.
- Ke, G. et al. 2017. LightGBM: A highly efficient gradient boosting decision tree. NeurIPS.
- `[CITE: SCoRE / score-select]`
- `[CITE: CORA]`
- `[CITE: Release Control]`
- `[CITE: Conformal Policy Control]`
- `[CITE: ModernBERT]`
- `[CITE: mmBERT]`
- `[CITE: LettuceDetect]`
