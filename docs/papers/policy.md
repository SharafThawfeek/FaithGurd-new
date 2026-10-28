# Should We Fix It? Certified Accept–Repair–Abstain Policies for Financial QA and Their Fragility When the Repairer Changes

Sharaf, M.L Ahamed, M.S.A Ahamed

> **Draft status (2026-10-13).** Written before the benchmark is labelled. The introduction, related work, method, setup and limitations are drafts to revise. Results are placeholders, `[RESULT: …]`, filled in phase 7 from the pre-registered analysis ([preregistration](../preregistration.md)). Numbers marked *development* come from the controlled track and test no hypothesis. Citations marked `[verify]` or `[CITE: …]` must be checked against the source and entered in [related-work/policy.md](../related-work/policy.md) before submission.

## Abstract

A system that checks AI answers about financial reports can send an answer as it is, repair it, or withhold it. Which action to take depends on what each would produce, and a repair can itself introduce errors. We build a paired replay dataset in which every action is played out on every answer and every outcome is scored, including answers that repair made worse. On it we fit two outcome models, the chance the original answer is unsafe and the chance repair returns a safe and useful answer, and choose among a pre-registered grid of decision rules with Learn-then-Test, certifying with high probability that at most α = 10% of sent answers are unsupported, repair-introduced errors included. On 800 human-labelled answers about US and Sri Lankan annual reports, the outcome-aware policy `[RESULT: useful coverage against a certified detector threshold]`. We also measure how many labels certification needs, and what happens to a certified policy when the repairer behind it is replaced: `[RESULT: as-is, recalibrated, refitted]`.

## 1. Introduction

Detectors and repairers for answer faithfulness are usually evaluated on their own. A deployed system needs a decision on top of them: for each answer, send it, try to repair it, or withhold it and show the user the evidence instead. That decision sets what the user experiences, how often they get an answer, and how often the answer they get is wrong.

The obvious rule is a threshold on the detector's risk: send answers below it, withhold the rest. It ignores repair. A better rule asks what each action would produce. If the original is likely wrong but the evidence holds the right values, repair may return a correct answer; if the evidence lacks them, repair will fail or, worse, produce a confident wrong answer. Predicting outcomes, not just risk, should let a system return more correct answers at the same error rate. But the error rate must count the errors repair introduces, and it must hold on new data, not just on average.

We make three contributions:

1. **A paired replay dataset.** Every action is run on every item, and each outcome is scored: unsupported, supported but unhelpful, or supported and useful. A flip matrix records each answer's state before and after repair, so answers repair made worse are counted rather than hidden in a net gain.
2. **A certified outcome-aware policy.** Two outcome models feed a pre-registered grid of decision rules; Learn-then-Test with Hoeffding–Bentkus p-values certifies the share of unsupported answers among those sent, with repair-introduced errors included, on an issuer-disjoint calibration set. We report how many labelled answers such a certificate needs, which matters to any team with a small labelling budget.
3. **A transfer study.** When the repairer changes, a certified policy's guarantee no longer covers the new outcomes. We test the old policy on the new repairer as it is, after recalibration with 25 to 200 new labels, and after refitting.

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

For every item the replay harness runs the detector, records the features known before any action, and then plays out all three actions: send the original, repair (scored as abstained when the repairer withholds), and abstain. Each sent text is scored against the gold store. Outcomes of the original answer come from human labels on the benchmark; repaired answers are scored by code against the gold answer written with each question, with a human-checked sample (repair paper). Gold labels live in a separate store that no component reads at decision time.

### 4.2 Features and outcome models

Features are pre-action only: the detector's risk; counts of claims, of supported, unsupported and unverifiable claims, and of evidence links; failing slots by type; missing operands; whether every failing claim has a correct value in the evidence (evidence sufficiency); whether the answer addresses the question; the size of the evidence; percentage and directional claims; the learned detector's highest span score; and the question type. Nothing comes from the gold store or from a repair attempt.

Two LightGBM models are trained on the fit split:

- **P(unsafe)**: the chance the original answer is unsupported;
- **P(fix)**: the chance repair returns a supported, useful answer.

The one challenger is a neural outcome model trained for the policy. It is the multilingual ModernBERT encoder (mmBERT) that the detection paper's learned detector starts from, fine-tuned on a GPU with one sigmoid output per outcome on its mean-pooled representation, both trained together with binary cross-entropy. LightGBM sees only the detector's summary features. The encoder reads the question and the evidence (focused on the rows the claims need when the evidence is large), paired with the answer and the same pre-action features written as text, cut to 1,024 tokens from the end of the evidence. It is trained on the fit split for at most two epochs, keeping the checkpoint with the lowest loss on the tune split, and never sees a calibration or test label. Both models are certified on the same grid with the same α and δ, and compared by AUROC, Brier score, ECE, certified useful coverage and the certification budget. The comparison asks whether reading the text adds anything to the detector's summary. LightGBM remains the primary model and the one deployed.

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

so an answer repair made wrong counts exactly like an original that was wrong. For each family, Learn-then-Test (i) orders the grid on the tune split, most cautious first; (ii) on the calibration split computes each setting's Hoeffding–Bentkus p-value for H0: E[L] > 0 and certifies settings in that order until the first p-value above δ; and (iii) among the certified settings chooses the one with the highest useful coverage on calibration. Because the order comes from a separate split, every certified setting keeps the guarantee at once, so choosing among them is allowed. The chosen setting is then reported once on the test split. We use α = 0.10 and δ = 0.05.

If no setting certifies, the policy withholds every answer, which is safe, and this is reported. The grid has no "never repair" setting: adding such settings to the fixed sequence blocked certification on smaller calibration sets in a synthetic study, and the controlled-track rehearsal of the transfer study with real repairer replays did not need one (§6.1).

**Issuer dependence.** Answers about the same company are related. As a sensitivity check, the chosen setting is recertified treating each issuer as one draw.

**Label budget.** With zero errors among n independent sent answers, the exact 95% upper bound on the error rate is 1 − 0.05^(1/n), so 29 sent answers are needed to certify α = 0.10; the linearised Hoeffding–Bentkus certificate used here needs 32. We also draw random calibration subsets of increasing size and report how often a setting certifies and the useful coverage it then reaches.

### 4.5 Transfer when the repairer changes

Two replays of the same items differ only in their repairer: v0 is rule-only (copy and calculate from the rule checker's correct-value expressions), v1 the trained edit-program repairer. The v0 policy is fitted on v0's fit split and certified on v0's calibration split. Three arms are scored on v1's test records:

- **as-is**: v0's outcome models and certified setting, unchanged;
- **recalibrated**: v0's outcome models, with the setting recertified on 25, 50, 100 and 200 of v1's calibration labels (50 random draws each) and on all of them;
- **refitted**: outcome models fitted on v1's fit split and certified on v1's calibration split.

A second shift, between generators, trains on Qwen answers and tests on Gemma answers.

## 5. Experimental setup

**Benchmark.** 400 question groups about 48 US and Sri Lankan annual reports, each answered by two generators (800 answers), human-labelled (benchmark paper `[cross-reference]`). Policies are certified on the calibration issuers' answers and reported on the test issuers' answers; the splits are issuer-disjoint.

**Controlled track** *(development rehearsal)*. FinQA and TAT-QA items with planted errors, where every outcome is scored automatically: 13,383 fit, 2,447 tune, 5,423 calibration and 6,450 test items from 984, 194, 401 and 391 issuers.

**Metrics.** Emission coverage (share of items sent), residual risk (share of sent answers unsupported, the certified quantity), useful coverage (share of items where a supported, useful answer is sent), the flip matrix, regret against the oracle, and Brier score and ECE per outcome model. Residual risk is also reported by group: numeric against narrative questions, US against Sri Lanka. An answer labelled ambiguous counts as unsafe. Intervals come from an issuer-clustered bootstrap (2,000 resamples).

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| P-H1. The outcome-aware policy beats the threshold policy | Higher useful coverage at equal certified α | No gain; the simpler policy is recommended |
| P-H2. α = 0.10 is certifiable at useful coverage | Certificate holds with coverage above the threshold policy | Not reachable; the budget curve says how many labels would be needed |
| P-H3. The v0 policy is unsafe on v1; recalibration restores safety | Risk above α as-is, within α after recalibration | Safe as-is, or refitting is needed; both are findings |

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

SCoRE, deciding only send or abstain with the same P(unsafe) scores, sent 22.7% with 5.5% wrong among sent. With LightGBM, certification succeeded in 1% of draws with 100 calibration answers, 75% with 200 and every draw from 400. Treated issuer by issuer, the chosen setting's p-value was 0.002 (certified).

The neural outcome model's probabilities are slightly better than LightGBM's on test (Brier score 0.0069 against 0.0075 for P(unsafe), 0.0123 against 0.0127 for P(fix)). Its certified policy sends 1.3% wrong answers [0.7%, 1.9%] against 1.6% [1.0%, 2.2%], at the same useful coverage within the intervals, and it certifies on smaller calibration sets more often (6% of draws at 100 answers, 84% at 200). One feature of the controlled track favours a model that reads the evidence: the error injector creates a missing operand by deleting the needed cell, so that table row reads shorter than its neighbours, a cue natural answers lack and the checker's features mostly miss. Without those items the comparison is unchanged (P(fix) AUROC 0.973 against 0.967, Brier 0.0116 against 0.0123), and on those items the two models are level. The gain comes mostly from sign errors (P(unsafe) Brier 0.0096 against 0.0189), while the encoder is slightly worse on clean answers.

**Transfer rehearsal.** 4,000 items (1,000 per split) were replayed with the trained stage A repairer standing in for v1 and paired with the rule repairer's replays of the same items. The v0 policy sent 72.2% of v0's test answers with 1.9% wrong among them; unchanged on v1's test answers, it sent 71.6% with 1.0% wrong. Recalibrated on v1's labels it certified in 76% of draws with 100 labels and in every draw from 200; refitted, it sent 73.2% with 1.0% wrong. On template answers the trained repairer is at least as safe as the rules, so the old policy transfers as it is; the predicted failure of P-H3 does not occur in rehearsal.

### 6.2 Natural answers (test split)

- P-H1: `[RESULT]`
- P-H2, with the budget curve on natural answers: `[RESULT]`
- P-H3, with repairer v1: `[RESULT]`
- Flip matrix, regret, groups, the neural outcome model against LightGBM, the generator shift, the issuer-level check and SCoRE: `[RESULT]`

## Limitations

- **Exchangeability.** The certificate assumes calibration and test answers are exchangeable. Splits are issuer-disjoint and drawn from the same population of listed companies; the issuer-level check shows how much the per-answer guarantee relies on answers being independent.
- **Small calibration sets.** About 400 calibration answers per run place the certificate near the edge of what the budget curve shows is needed; we report when it fails rather than loosening α.
- **Repair outcomes scored by code.** Repaired answers are judged against gold answers by code, checked on a human sample; disagreements above about 10% trigger more human checking.
- **No never-repair fallback.** If a new repairer made repair unsafe, the grid could only certify by withholding; refitting is the remedy we report.
- **Replay, not causal inference.** Every action was actually run on every item; we compare stored outcomes and make no causal claim beyond them.
- **Authoring and labels**: see the AI assistance statement.

## AI assistance statement

`[Finalise before submission.]` Claude (Anthropic) wrote most of the project's code, drafted the benchmark questions and gold answers, produced the pilot labels used only for design decisions, and drafted this paper. Every benchmark table and question is checked by a person before the test set is locked, the reported labels are human, and the authors take responsibility for all content.

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
