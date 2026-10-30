# Right Number, Wrong Context: Relation-Aware Hallucination Detection for Financial Report QA with XBRL-Mined Supervision

M.L Ahamed, M.S.A Ahamed, Sharaf

> **Draft status (2026-10-30).** The test set is locked (394 questions, 788 answers; D-104) and labelled (D-105). Filled from the locked labels: the benchmark and label description (§5.1), the disclosure that every label, check and adjudication was made by separate Claude passes (§3, §5.1, Limitations), the limitations and the AI assistance statement. The results on the main answers (abstract, §6.2) are filled from the pre-registered analysis ([runs/main/report.md](../../runs/main/report.md); [preregistration](../preregistration.md); D-109 to D-112): D-H1 is untestable under its pre-registered rule (4 wrong-context test answers; §5.3), D-H2 is rejected (no difference) and D-H3 is untestable (no US threshold certifies). The two exploratory analyses in §6.2 were not run in this version. Still to do: the introduction, related work and method are drafts to revise against these results, and the whole paper needs final editing. Numbers marked *development* come from the controlled track or the pilot's development issuers and test no hypothesis. Citations marked `[verify]` or `[CITE: …]` must be checked against the source and entered in [related-work/detection.md](../related-work/detection.md) before submission.

## Abstract

Answers about financial reports can quote a real figure from the evidence under the wrong context: the Bank's profit given as the Group's, last year's revenue given for this year, thousands read as millions. Such "right number, wrong context" errors are hard for general hallucination detectors, because the number does appear in the evidence. We train a span detector to catch them using supervision mined automatically from US XBRL filings: each fact is paired with a sibling fact that differs in one part of its context, and an answer stating the sibling's value under the original context becomes a labelled negative. A second head names the failing relation (entity or scope, metric, period, scale or currency, sign, basis, missing operand). The learned channel is fused with an exact rule checker and calibrated, and its threshold is chosen with Learn-then-Test, which certifies one only if the calibration answers allow it. We evaluate on a new benchmark of 788 answers to 394 questions about 48 US and Sri Lankan annual reports, labelled by separate blind passes of Claude rather than by people. On Sri Lankan reports, which have no XBRL, the fused detector does not beat the rule checker alone on span F1 (0.205 against 0.181; paired difference 0.024, 95% CI [−0.059, 0.146]), so the rules suffice there. The cross-market test could not be run: no threshold on the fused risk certifies on the US calibration answers at α = 0.10, so there is no US threshold to carry to Sri Lankan reports, and recalibration on 100, 200 or all 250 Sri Lankan calibration labels restores none (0% of draws). Our pre-registered primary comparison, wrong-context recall with and without XBRL supervision, could not be tested either: the labels mark only 9 wrong-context spans across all 788 answers, and the test split holds 4 such answers, fewer than the 20 the pre-registered rule needs, so the comparison is reported as untestable. Descriptively, the fused detector ranks answers better than every other detector we compare (AUROC 0.849 [0.804, 0.895], against 0.803 for the rule checker and 0.609 to 0.688 for four released detectors), while the learned channel alone is weak on natural answers (AUROC 0.579, below the LettuceDetect v2 checkpoint it starts from, 0.688).

## 1. Introduction

Retrieval-augmented question answering over annual reports is now routine, and its errors are costly: an analyst who receives a wrong figure with a confident sentence around it has no reason to check it. Few of these errors are invented numbers. In the pilot of our benchmark, wrong answers mostly computed a percentage from the right figures and printed it wrongly, reversed a sign, or misstated a scale (§5.1). The errors this paper targets are subtler still: a real figure from the evidence under the wrong entity, year or line item. A detector that asks only "does this number appear in the evidence?" passes them, and annual reports invite them, printing Group and Company columns, two years side by side and the same line item under several headings.

Two families of tools address answer faithfulness. Rule-based checkers recompute every number and trace it to a table cell; on template answers they are close to perfect, but they say nothing about claims without a printed number, and they reject correct claims phrased in ways their rules do not cover. Learned span detectors such as LettuceDetect (Kovács and Recski, 2025 `[verify]`) mark unsupported answer tokens and generalise across phrasing, but they are trained on general retrieval-augmented data (RAGTruth; Niu et al., 2024) in which the subtle failures of financial answers are rare.

We built the detector around one way to close that gap: free, automatically mined supervision. US public companies file their financial statements in XBRL, where every fact carries its concept, period, unit and dimensional context. For any fact an answer might cite, the same filing usually holds siblings that differ in exactly one part of that context and carry a different value. Stating a sibling's value under the original fact's context produces a realistic wrong-context error, with an exact label for the part that differs. We use this as a *training* signal for a span detector, not as a lookup at inference.

We registered three hypotheses before the test set was opened (§5.3). The first, and the primary comparison, was that XBRL-mined negatives raise recall on wrong-context errors (D-H1). Our benchmark cannot test it. Its questions were written around wrong-context traps, but the labels mark only 9 entity, period or metric spans in all 788 answers, against 130 value spans, and the rule needs 20 such answers on test. D-H1 is reported as untestable, as the rule says. The other two hypotheses ask whether the learned channel adds to exact rules on Sri Lankan reports, which have no XBRL (D-H2), and whether a threshold certified on US filings holds there, and whether 100 local labels restore it (D-H3). D-H2 is rejected: on Sri Lankan test answers the fused detector does not beat the rule checker on span F1 (difference 0.024 [−0.059, 0.146]), so the rules suffice. D-H3 is untestable: no threshold on the fused risk certifies on the US calibration answers at α = 0.10, so there is no US threshold to carry over.

Our contributions:

1. **XBRL-mined wrong-context supervision** for a span detector: 14,512 labelled examples from the latest 10-Ks of 120 companies that never appear in the evaluation. Its pre-registered test (D-H1) proved untestable on our benchmark (§5.3).
2. **A relation-slot head** that names the failing part of a flagged span, alongside the span head, so a downstream repairer or reviewer knows what to fix.
3. **A two-channel detector**, the learned channel fused with an exact rule checker and calibrated, evaluated on natural answers (labelled by separate blind Claude passes, not by people; §5.1) with the false-alarm rate on clean answers (those not labelled incorrect) as a headline metric.
4. **A cross-market test**: a threshold certified on US filings, applied to Sri Lankan annual reports as it is and after recalibration with 100 and 200 local labels and with all available. On our benchmark no threshold certifies on the US calibration answers, so the test could not be run (D-H3 is untestable; §6.2).

We do not claim the first financial hallucination detector, nor the first typed or span-plus-evidence detector; related systems exist (§2).

## 2. Related work

**Hallucination detection for retrieval-augmented generation.** RAGTruth (Niu et al., 2024) provides span-level human labels of unsupported content in retrieval-augmented answers and is the standard training source for token-level detectors. LettuceDetect (Kovács and Recski, 2025 `[verify]`) frames detection as token classification over a long-context encoder (ModernBERT) and is our warm start. Its 2026 release adds a multilingual mmBERT encoder and a taxonomy head that types hallucinations (`[CITE: LettuceDetect v2 taxonomy head, model card — verify]`); that typed output is the closest prior work to our slot head; a comparison with it, planned as an exploratory analysis, was not run in this version (§6.2). Sentence- or answer-level judges include Vectara's HHEM-2.1-Open (`[CITE: HHEM model card — verify]`) and IBM's Granite Guardian (Padhi et al., 2024 `[verify]`; we use the 4.1 8B release), which scores groundedness among other risks. None of these is trained on financial context errors.

**Financial question answering.** FinQA (Chen et al., 2021) and TAT-QA (Zhu et al., 2021) pair questions about financial tables and text with gold answers and, for FinQA, executable programs; FinanceBench (Islam et al., 2023 `[verify]`) tests open-book QA over US filings. These datasets measure answer accuracy, not detection of unfaithful spans, and none covers Sri Lankan reports. We use FinQA and TAT-QA programs to inject controlled errors for training and development.

**Verification against filings.** The revised plan says VeriFin uses XBRL only at inference time. We have not yet opened it, so we make no claim about what it does until its row in [related-work/detection.md](../related-work/detection.md) is filled `[CITE: VeriFin — open and verify]`. We use XBRL only to build training data, so the detector needs no XBRL at inference and can run on Sri Lankan reports, which have none. `[Add any further financial verification systems found in the monthly literature refresh.]`

**Risk control.** We set the detector's threshold with Learn-then-Test (Angelopoulos et al., 2021 `[verify]`), using Hoeffding–Bentkus p-values (Bates et al., 2021), so the error rate among answers passed as safe is certified on a held-out calibration set.

## 3. Task

The input is a question, frozen evidence (report tables and, where present, text passages) and one answer. The detector returns (i) the answer spans that are not supported by the evidence, (ii) for each span, the relation slot that fails, and (iii) a calibrated risk that the answer contains at least one unsupported claim.

| Slot | The span is wrong because | Example (evidence: Group profit after tax 2025 = Rs. 14,212,560 thousand; Bank = Rs. 12,450,330 thousand) |
| --- | --- | --- |
| entity_scope | It belongs to another entity or scope | "Group profit was Rs. 12,450 million" (the Bank's) |
| metric | It belongs to another line item | Profit before tax quoted as profit after tax |
| period | It belongs to another year or quarter | The 2024 figure given for 2025 |
| unit | The kind of quantity is wrong | Shares for a currency amount |
| scale_currency | Right digits, wrong scale or currency | "Rs. 14,212,560 million" |
| sign | Direction or sign reversed | "fell 9.3%" when it rose |
| basis | Growth or share on the wrong base | Change divided by this year instead of last |
| missing_operand | The evidence lacks what the claim needs | A ratio whose inputs the extract never shows |
| value | Wrong, with no better description | Includes computed figures off in a printed digit |

The benchmark labels also mark unsupported non-numeric text (unsupported_text). The slot set is the one the annotation guide uses ([annotation-guide.md](../annotation-guide.md)). The labels are made by separate, blind passes of Claude (Anthropic), not by people (§5.1).

## 4. Method

### 4.1 Channel B: the rule checker

Channel B extracts every numeric claim from the answer (amounts with currency and scale, percentages, ratios and plain numbers, with any direction word such as "rose") and works out what each claim is about: its metric, entity and period, from the words around it and the question. It then traces the number to the evidence with exact Decimal arithmetic: to a table cell, or to a growth rate, difference, share or ratio computed from cells. A claim is *supported* if it traces under its intended context. It is *unsupported* if it traces only under a different context, and the parts that differ are named as slots, or if the intended cells contradict it. It is *unverifiable* if no rule covers the intended context or the evidence lacks it. For each claim the checker also records the cell expression that gives the correct value, which the repairer uses (companion paper).

Numbers are compared at the precision the answer prints them: a figure is supported if the true value rounds to it. Reports' printed conventions are handled explicitly: thousands written "Rs. '000", negatives in brackets, a fall written "(3)%", and per-share rows inside statements in thousands.

### 4.2 Channel A: the learned detector

Channel A is a LettuceDetect encoder with two heads. Inputs follow LettuceDetect's format: a prompt holding the question and the evidence passages, paired with the answer, with labels on answer tokens only. Each evidence table becomes one passage, with a cell id and column label on every number.

- **Span head**: per answer token, supported or not, warm-started from the released checkpoint.
- **Slot head**: a linear layer on the last hidden state that predicts, for each token inside a gold span, which relation fails. Its loss is added to the span loss with weight 0.5.

We start from the LettuceDetect v2 mmBERT encoder (`KRLabsOrg/lettucedect-v2-mmbert-base`), chosen over v1-large in a pilot on a T4 GPU because it trained 1.8 to 2.0 times faster in less memory at 1,024 and 2,048 tokens, with nothing in the pilot favouring the larger model. A claim is flagged when the highest token probability over its characters (or its direction word) reaches the decision threshold.

**Training data.** 34,229 examples from three sources:

- *Controlled track*: answers to FinQA and TAT-QA questions written from templates, with one planted error each (wrong period, metric or entity cell; wrong scale; reversed sign; wrong growth base; a figure whose correct cell was removed from the evidence) and the correct answers as clean negatives. Only questions from the training share of issuers are used.
- *RAGTruth*: 8,000 human-labelled answers, for general span detection.
- *XBRL-mined examples* (§4.3): 12,846 from the training share of companies.

Training runs one epoch at up to 2,048 tokens, learning rate 2e-5, effective batch 8, in fp16 on one free T4 GPU (4.3 hours).

**Large evidence.** An annual report's income statement and balance sheet run to 40–80 rows. Above 30 rows, Channel A reads only the rows holding a cell the rule checker traced a claim to, and the rows of the line items the claims are about or the question names, each row kept whole so the other entity's and year's figures stay beside it. Only the rule checker's output and the question are used, never gold. Controlled-track evidence never exceeds 25 rows, so training is unaffected.

### 4.3 Mining wrong-context negatives from XBRL

From one filing's facts, a cited fact is a (concept, period, dimensional context) triple with a value. A *sibling* differs from it in exactly one part and holds a different value:

| Sibling differs in | Slot |
| --- | --- |
| period | period |
| segment or other dimension member | entity_scope |
| concept | metric |
| none, but the value is rescaled (thousand vs million) | scale_currency |

A negative answer states the sibling's value under the cited fact's context (for a fictional filer, "Example Industries' revenue was $7,915.2 million in fiscal 2025", when that is the fiscal 2024 value), so the number exists in the filing but belongs elsewhere. The clean answer states the cited fact's own value. Answers name a fact's scope from its XBRL axis ("for its X segment", "from services"). The evidence is a table built from the filing's facts, so both the right and the wrong cell are visible. XBRL instance documents are parsed directly, without a taxonomy download.

Facts come from the latest 10-K of each of 120 FinQA companies, which are training-only; no benchmark issuer is mined. To stop a few very large filings dominating, 25 cited facts are sampled per filing (seeded by company), each with all its negatives. This gives 14,512 examples: 3,000 clean, 5,100 metric, 3,000 scale, 1,995 entity-scope and 1,417 period. One company in ten goes to development.

### 4.4 Fusion and calibration

For each numeric claim, features from both channels (Channel B's verdict, the number of failing slots and whether it has a correct value for the claim; Channel A's highest and mean token probability over the claim and whether any token passes 0.5; whether the claim is a percentage and whether it carries a direction word) feed a logistic regression that predicts whether the claim is wrong. Isotonic regression calibrates it on the calibration split. On the benchmark the fusion has no frozen weights: it is refitted on the calibration answers, the logistic regression on the issuers of one half of the calibration split and the isotonic step on the other half, with a claim counted wrong when it overlaps a labelled span. An answer's risk is the probability that at least one claim is wrong, treating claims as independent (0.5 when there is nothing to check). The send-or-flag threshold is chosen by Learn-then-Test at α = 0.10 and δ = 0.05 on the calibration split, so the share of unsupported answers among those passed is certified (companion policy paper). An answer is passed when its risk is below the threshold. The candidate thresholds are 0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.7 and 0.9, tested in that order, most cautious first, with Hoeffding–Bentkus p-values until the first one fails; the largest certified threshold is used. This grid serves both D-H3 and coverage at certified selective risk (§5.3).

## 5. Experimental setup

### 5.1 Data

**Benchmark.** 400 questions about the latest annual reports of 24 Sri Lankan and 24 US issuers (12 test and 12 calibration per country, issuer-disjoint from all training and development data), each with a gold answer written as an expression over cells of the benchmark's tables (read by the project's own table readers and kept only when every total adds up; no person has checked a table, D-114). A second-reader pass re-derived every gold answer from the report and the question's wording, without the author's answer, and checked the table rows each question uses against the source pages and filings. It found no wrong gold, but six questions whose wording admits a second reading: two "why" questions the tables only partly answer, two about a line item the report prints twice, one on net income with or without the noncontrolling share, and one on a company-defined ratio the filing rounds differently. They were excluded before filing, so the locked test set is 394 questions. Each is answered once by Qwen3.5-9B and Gemma 4 12B (4-bit, llama.cpp, thinking off), giving 788 answers: 496 about Sri Lankan reports and 292 about US reports, 392 on test issuers and 396 on calibration issuers. Full details are in the benchmark paper (`[cross-reference]`).

**Who labelled.** The project had no human labellers, second readers or adjudicator. Every one of those roles was taken by Claude (Anthropic), each as a separate pass (decision D-103): the second reader above, the labeller, the second labeller and the adjudicator. The labelling passes were blind to the generator, the system and any code label; the second reader did not see the author's answer. No person labelled, checked or adjudicated any benchmark answer. The agreement figures below are agreement between Claude's passes, not between people. There is no human agreement figure and no external adjudicator.

**How the labels were made.** Labels follow annotation guide v2: unsupported spans with slots, the answer's status (correct, incorrect, ambiguous, unhelpful) and usefulness. A pre-registered triage gave a code label (correct, useful, no spans) to 311 answers whose every number matched a gold value and whose words could not still make them wrong. The other 477 went to the labeller, with a hidden, stratified audit sample of 150 code labels; the code labels would stand only if at most 1 of the 150 was overruled. A first labelling pass was discarded before anything used it: its tasks left out each table's units note, which the generators saw, so scale and currency errors could not be judged. The tasks were rebuilt with the note and labelled again. The labeller labelled all 627 routed and audit tasks, and a second labeller the 80 pre-registered double-labelled tasks (60 routed, 20 audit), both blind. On the 80, Cohen's kappa per field:

| Field | Agreement | Kappa |
| --- | --- | --- |
| Status | 95% | 0.89 |
| Usefulness | 91% | 0.71 |
| Answer has a wrong span | 100% | 1.00 |

All but one of the 7 usefulness disagreements were on answers both passes called incorrect, and both marked the same 26 spans with the same slots. The 15 tasks whose labels differed in status, usefulness or span text went to the adjudicator pass, whose label decides. The audit overruled 4 of the 150 code labels (95% upper bound 6.0%): two answers that copy a table's thousands note onto a per-share figure, one with a wrong currency code, and one claiming its figure is printed on another line that shows a different one. With more than one overruled, the code labels fell, as pre-registered, and the labeller labelled the other 161 code-labelled answers. No code label decides any answer: 773 are decided by the labeller and 15 by the adjudicator. So the pre-registered re-analysis on answers not labelled by code is the main analysis itself.

**What the labels say.** Of the 788 answers, 592 are correct, 177 incorrect (22.5%; 170 of the 672 numeric answers, 25.3%), 16 unhelpful and 3 ambiguous.

| Country, generator | Answers | Correct | Incorrect | Unhelpful | Ambiguous |
| --- | --- | --- | --- | --- | --- |
| Sri Lanka, Gemma | 248 | 186 | 54 | 7 | 1 |
| Sri Lanka, Qwen | 248 | 188 | 53 | 7 | 0 |
| US, Gemma | 146 | 101 | 41 | 2 | 2 |
| US, Qwen | 146 | 117 | 29 | 0 | 0 |
| All | 788 | 592 | 177 | 16 | 3 |

Growth questions hold 88 of the 177 incorrect answers. The labelled spans by slot are value 130, unsupported_text 30, scale_currency 28, sign 17, entity_scope 5, period 3, basis 2 and metric 1; no span is labelled unit or missing_operand. So the wrong-context slots (entity_scope, metric, period) carry 9 spans across all 788 answers (see Limitations). Of the 392 test answers, 86 have spans. On the 672 numeric answers, test and calibration pooled, the rule checker flags 144 of the 170 labelled incorrect and 110 of the other 502; this describes the labels and tests no hypothesis.

**Pilot** *(development)*. 120 answers to 60 questions on 8 development issuers, labelled by Claude (D-103, D-105): 23 incorrect (19.2%), mostly a computed percentage off in a printed digit, a reversed sign or a wrong scale. Channel B flagged 19 of the 23 and 16 of the other 81 numeric answers. The pilot's tasks had the same missing units note as the discarded first pass, so these labels are development-only and guide design only.

**Controlled track** *(development)*. FinQA and TAT-QA items with planted errors, split by issuer into fit, tune, calibration and test shares. Development results use 2,000 tune-share items.

### 5.2 Systems

- Channel A, with and without XBRL-mined negatives (the primary comparison, D-H1), and without the slot head.
- Channel B alone; A alone; A + B fused.
- Released detectors: LettuceDetect v1-large and v2 mmBERT (risk = highest span confidence), HHEM-2.1-Open (risk = 1 − consistency) and Granite Guardian 4.1-8B at 4-bit, groundedness criterion, no thinking (risk = 1 if it judges the answer ungrounded). Every detector reads the same evidence text, focused as in §4.2 above 30 rows. On a T4, Granite Guardian reads a long prompt into its cache 1,024 tokens at a time and then answers greedily, which gives the same input and the same reply as one pass over the prompt, with nothing truncated; one pass over a prompt of about 9,000 tokens ran out of memory (D-108).

Apart from the hypothesis tests of §5.3, the comparisons among these systems (A alone, B alone and A + B; Channel A with and without its slot head; the four released detectors) are secondary analyses (pre-registration §7). They test no hypothesis and are reported with the same issuer-clustered 95% intervals.

### 5.3 Metrics and hypotheses

The pre-registered metrics are span F1 by slot, wrong-context recall (entity_scope, metric and period spans), the false-alarm rate on clean answers, AUROC, Brier score, ECE, and coverage at certified selective risk (α = 0.10). A *clean* answer is one not labelled incorrect (D-109). On the test answers, with answers labelled ambiguous left out (except in risk metrics) and reported separately, the analysis computes:

- **Span F1** on character overlap between predicted and gold spans, for B, A + B, Channel A alone and Channel A without its slot head. B's spans are the claims it flags, A + B's the claims the fused probability puts at 0.5 or more, and Channel A's the spans it marks.
- **By slot**, the share of each gold slot's characters that a detector's spans find; gold spans with no slot are reported as "none". For Channel A, **slot accuracy**: how often its span that overlaps a gold span names that span's slot.
- **For every detector**, AUROC of its answer risk, and, at the threshold set on the calibration answers to flag 10% of the clean ones, the false-alarm rate on clean test answers, recall on incorrect ones and wrong-context recall. Beside each, the share of clean calibration answers it actually flags: tied scores, such as Granite Guardian's 0 or 1, cannot flag exactly 10%.
- **AUROC differences** of A + B against each other detector, and of Channel A against its no-slot ablation.
- **Brier score and ECE** of the fused probabilities, per claim (a claim is wrong when it overlaps a labelled span) and per answer (the answer's risk against whether it is labelled incorrect).
- **Coverage at certified selective risk**: the fused-risk threshold certified on every calibration answer with D-H3's grid (§4.4), applied to the test answers, with the share passed and the risk among those passed.

In risk metrics (D-H3 and coverage at certified selective risk) an answer labelled ambiguous stays in, counts as unsafe and is reported separately. Intervals come from an issuer-clustered bootstrap: whole issuers resampled with replacement, 2,000 resamples, 95% percentile intervals, seed 0. Issuers, questions and answers are reported separately. The hypotheses and their decision rules were registered before the test set was opened ([preregistration](../preregistration.md) §2; D-102):

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| D-H1. XBRL negatives raise wrong-context recall | Higher recall at an equal clean false-alarm rate | False alarms rise or recall does not move |
| D-H2. A + B beats B alone on Sri Lankan reports | Higher span F1, intervals not overlapping | No gain; rules suffice, reported as such |
| D-H3. The US threshold fails on Sri Lanka; about 100 local labels restore it | Risk above α before, within α after | Holds without recalibration; also reported |

D-H1 is the paper's pre-registered primary comparison (pre-registration §3). "Higher" means that the 95% interval of the paired difference on the test split excludes zero in the stated direction; otherwise the hypothesis is rejected as "no difference". For D-H2 this paired interval, not a comparison of two separate intervals, decides. In detail:

- **D-H1.** Each model's threshold, with and without XBRL negatives, is set on the calibration split so that it flags 10% of the clean answers there. Wrong-context recall, over test answers with an entity_scope, metric or period span, is compared at those thresholds. If test has fewer than 20 such answers, D-H1 is reported as untestable. The labels mark 9 such spans across all 788 answers (§5.1), so test holds at most 9 such answers and D-H1 is untestable.
- **D-H2.** Span F1 of A + B minus span F1 of B, on the Sri Lankan test answers. B's spans are the claims it flags; A + B's are the claims the fused probability puts at 0.5 or more.
- **D-H3.** The threshold is certified on US calibration answers (§4.4) and applied unchanged to the Sri Lankan test answers. It fails if the lower end of its Sri Lankan test risk interval is above α. It is restored if, recalibrated on 100 Sri Lankan calibration labels, its Sri Lankan test risk is at most α: the threshold is certified again on each of 50 random draws of 100 labels (seed 0), and it is restored when at least half the draws certify a threshold whose Sri Lankan test risk is at most α (D-107). D-H3 has four outcomes. It is *untestable* if no threshold certifies on the US calibration answers (or if the fusion cannot be fitted). It is *rejected* if the US threshold holds on Sri Lanka without recalibration. It is *confirmed* if the threshold fails as it is and at least half of the 50 draws restore it. It is *not confirmed* if the threshold fails and is not restored. The label-efficiency curve gives the share of draws that restore it with 100 and with 200 Sri Lankan calibration labels (50 draws each), and whether recalibrating on all of them restores it. Sizes 25 and 50 were dropped before filing: at the send rates seen, they cannot certify α = 0.10 even with no error.

Every detection metric was to be reported again on answers not labelled by code; no code label decides any answer here (§5.1), so the main analysis is that analysis.

## 6. Results

### 6.1 Development results (controlled track; not a test of the hypotheses)

On 2,000 tune-share items with template answers:

| Detector | AUROC | Span F1 | Wrong-context recall | Clean false alarms at 0.5 |
| --- | --- | --- | --- | --- |
| Channel A (full) | 0.933 | 0.925 | 0.988 | 51.8% |
| without XBRL negatives | 0.932 | 0.922 | 0.992 | 48.2% |
| without slot head | 0.931 | 0.925 | 0.997 | 54.6% |
| LettuceDetect v1-large | 0.509 | | 0.728 | 69.7% |
| LettuceDetect v2 mmBERT | 0.555 | | 0.820 | 70.6% |
| HHEM-2.1-Open | 0.535 | | 0.680 | 66.7% |
| Granite Guardian 4.1-8B (1,000 items) | 0.806 | | 0.959 | 27.6% |

On template answers the rule checker alone reaches AUROC 0.997, and the calibrated A + B fusion 0.994–0.995 with 1.0% false alarms on 475 held-out items. XBRL negatives raised span recall on basis and sign errors (1.00 against 0.73; 0.97 against 0.83) but not wrong-context recall, which is near ceiling here. Every Channel A variant flags about half the clean answers at 0.5, so the threshold has to come from calibration. Template answers are where rules are strongest, so these figures rehearse the pipeline; the hypotheses are decided on natural answers.

### 6.2 Natural answers (test split)

- D-H2: rejected, no difference ("no gain; rules suffice", as pre-registered). On the Sri Lankan test answers (246 answers, 12 issuers), span F1 is 0.181 for B and 0.205 for A + B; the paired difference is 0.024 [−0.059, 0.146], and its interval includes zero.
- D-H3 (untestable: no US threshold certifies; §5.3), with the label-efficiency curve at 100 and 200 labels and all available: no threshold on the fused risk certifies on the US calibration answers at α = 0.10 (δ = 0.05), so there is no US threshold to apply to the Sri Lankan test answers and no Sri Lankan test risk to report for it. The label-efficiency curve is 0% of draws at 100 and at 200 Sri Lankan calibration labels, and recalibrating on all 250 does not restore it either.
- D-H1: untestable under its pre-registered rule. The test split holds fewer than 20 answers with an entity_scope, metric or period span (all 788 answers carry 9 such spans; test answers with one: 4). As description only, at each model's 10% calibration threshold Channel A finds 1 of the 4 with XBRL negatives (25.0%) and none without them (0.0%); the difference, 25.0 points [0.0, 100.0], rests on four answers and decides nothing.
- Secondary detection results, with intervals (§5.2, §5.3): each detector's AUROC, false alarms, recall and wrong-context recall, and the share of clean calibration answers it actually flags; AUROC differences of A + B against each other detector and of Channel A against its no-slot ablation: see Table 6.2a. A + B ranks answers best (AUROC 0.849 [0.804, 0.895]) and beats every other detector: by 0.047 [0.013, 0.079] over B, and by 0.161 [0.096, 0.231] (LettuceDetect v2) to 0.270 [0.207, 0.336] (Channel A) over the rest, every interval above zero. Channel A, near its ceiling on template answers (§6.1), is weak on natural ones (AUROC 0.579 [0.532, 0.624]); it ranks below all four released detectors (0.609 to 0.688), including LettuceDetect v2, its warm start (§4), and its value is through the fusion. Channel A minus its no-slot ablation is −0.035 [−0.081, 0.008]. At its 10% calibration threshold A + B flags 3.0% [1.2%, 4.9%] of clean test answers and finds 62.8% [51.1%, 75.3%] of incorrect ones; the other detectors that flag anything find 4.7% to 14.0% at 5.9% to 13.8% false alarms. Channel B and Granite Guardian flag nothing at that threshold, because their scores are tied: B takes three values, and 59 of the 304 clean calibration answers (19.4%) score its top value 1; Granite Guardian's output is 0 or 1, and 12.5% of clean calibration answers score 1. The threshold therefore lands on the top score, and their 0% false alarms and 0% recall are a property of tied scores under the filed rule, not of the detectors. Exploratory, not the filed threshold: flagging every answer at the top score gives Channel B 18.8% test false alarms and 70.9% recall, and Granite Guardian 10.5% and 32.6%. These tie counts and top-score rates were computed outside the filed analysis: runs/main/results.json holds the filed threshold's 0% rows but not these figures, no other file in the repository holds them, and they cannot be recomputed from it, since the labels and each answer's scores are not committed (D-115). Wrong-context recall, over only 4 test answers, is 25.0% [0.0%, 100.0%] for Channel A and its no-slot ablation and 0.0% for every other detector.
- Spans: span F1 of B, A + B, Channel A alone and Channel A without its slot head; the share of each gold slot's characters found; Channel A's slot accuracy: see Table 6.2b. Span F1 is 0.234 [0.150, 0.343] for B, 0.245 [0.141, 0.411] for A + B, 0.126 [0.082, 0.179] for Channel A and 0.145 [0.095, 0.210] for Channel A without its slot head. Value spans are found best (B 77.3%, A + B 69.9% of their characters). Channel A finds 87.5% of entity_scope characters, but its slot head names the gold slot of an overlapping span in only 3.4% [0.0%, 8.7%] of cases. No detector finds any period or sign characters. The 2 test answers labelled ambiguous (1 on calibration) are left out of these metrics; HHEM flags one of the test ones and no other detector flags either.
- Fused probabilities: Brier score and ECE per claim and per answer; coverage and risk among passed answers at certified selective risk: per claim, Brier 0.034 [0.023, 0.049] and ECE 0.022 [0.012, 0.038]; per answer, Brier 0.114 [0.091, 0.141] and ECE 0.100 [0.085, 0.137]. No fused-risk threshold certifies on all calibration answers at α = 0.10, so there is no coverage at certified selective risk to report.
- Exploratory, not in the pre-registration: the slot head's typed output against LettuceDetect v2's taxonomy head: not run in this version.
- Exploratory, not in the pre-registration: where the learned channel adds value (RQ2): Sri Lankan reports, claims with no printed number, correct claims the rules reject: not run in this version.

**Table 6.2a.** Detectors on the test split. Each threshold is set to flag 10% of the clean calibration answers; "Cal. flagged" is the share it does flag (tied scores can make it less). Issuer-clustered 95% intervals.

| Detector | AUROC | Cal. flagged | Test false alarms | Recall | Wrong-context recall (4 answers) |
| --- | --- | --- | --- | --- | --- |
| A + B fused | 0.849 [0.804, 0.895] | 2.3% | 3.0% [1.2%, 4.9%] | 62.8% [51.1%, 75.3%] | 0.0% |
| Channel B | 0.803 [0.764, 0.838] | 0.0% | 0.0% | 0.0% | 0.0% |
| Channel A | 0.579 [0.532, 0.624] | 9.9% | 11.8% [6.9%, 18.1%] | 8.1% [2.7%, 14.0%] | 25.0% [0.0%, 100.0%] |
| Channel A, no XBRL negatives | 0.592 [0.543, 0.645] | 9.9% | 6.6% [3.7%, 10.0%] | 4.7% [0.0%, 9.8%] | 0.0% |
| Channel A, no slot head | 0.614 [0.557, 0.672] | 9.9% | 13.8% [7.5%, 20.5%] | 12.8% [6.2%, 19.8%] | 25.0% [0.0%, 100.0%] |
| LettuceDetect v1-large | 0.641 [0.565, 0.713] | 9.9% | 5.9% [3.3%, 8.3%] | 4.7% [1.2%, 8.9%] | 0.0% |
| LettuceDetect v2 mmBERT | 0.688 [0.607, 0.762] | 9.9% | 6.9% [3.4%, 10.8%] | 14.0% [7.6%, 20.5%] | 0.0% |
| HHEM-2.1-Open | 0.609 [0.565, 0.662] | 9.9% | 5.9% [3.5%, 8.7%] | 5.8% [1.1%, 12.3%] | 0.0% |
| Granite Guardian 4.1-8B | 0.610 [0.556, 0.659] | 0.0% | 0.0% | 0.0% | 0.0% |

**Table 6.2b.** Spans on the test split (character overlap; ambiguous answers left out). Recall by slot is the share of that gold slot's characters found.

| Detector | Span F1 | Slot accuracy | value | scale_currency | sign | basis | entity_scope | metric | period | none |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Channel B | 0.234 [0.150, 0.343] | - | 77.3% | 65.6% | 0.0% | 50.0% | 0.0% | 0.0% | 0.0% | 0.1% |
| A + B fused | 0.245 [0.141, 0.411] | - | 69.9% | 0.0% | 0.0% | 14.3% | 0.0% | 0.0% | 0.0% | 0.0% |
| Channel A | 0.126 [0.082, 0.179] | 3.4% [0.0%, 8.7%] | 58.5% | 9.3% | 0.0% | 50.0% | 87.5% | 0.0% | 0.0% | 0.0% |
| Channel A, no slot head | 0.145 [0.095, 0.210] | - | 63.2% | 28.4% | 0.0% | 50.0% | 12.5% | 56.0% | 0.0% | 0.0% |

## Limitations

- **No human labels, checks or adjudication.** Claude (Anthropic) drafted the benchmark's questions and gold answers, and separate, blind Claude passes took every role the plan gave to people: the second reader of the questions and tables, the labeller, the second labeller and the adjudicator (D-103). No person labelled, checked or adjudicated any benchmark answer. The kappa values in §5.1 measure agreement between Claude's passes, not between people, and passes of one model can share blind spots that their agreement does not show. There is no human agreement figure and no external adjudicator. Every detection metric here is measured against Claude's labels. The safeguards that remain are code labels only where the gold cells decide, an independent audit of them (which overruled enough that no code label is used), and the pre-registered sensitivity analyses.
- **Triage rules.** The triage and gold-scorer rules stay as filed. The four audit overrules show what they miss: unit words copied onto per-share figures, currency codes and claims with no figure.
- **Few wrong-context errors.** The main questions were written around wrong-context traps (Group against Company, prior-year columns, repeated line items) to raise their rate, but the labels mark only 9 wrong-context spans in all 788 answers (5 entity_scope, 3 period, 1 metric), against 130 value spans. As in the pilot, natural errors fall mostly under other slots: value (the slot that includes computed figures off in a printed digit), scale or currency (28 spans) and sign (17). The test split therefore holds fewer than the 20 wrong-context answers the pre-registered rule needs, and D-H1, the paper's primary test of XBRL supervision, is reported as untestable under that rule.
- **Template supervision.** Controlled-track and XBRL-mined answers are written from templates. They teach the detector what wrong-context errors look like, but natural answers phrase things more freely, which is why every hypothesis is tested on natural answers.
- **US-only mining.** XBRL exists only for US filings. The Sri Lankan test measures how far US-mined supervision transfers; it cannot use Sri Lankan XBRL.
- **Fixed, arithmetic-checked evidence.** Every detector checks answers against the same stored tables, so table-reading differences cannot favour one detector over another. The tables are the project's readers' output, kept when every total adds up; a Claude pass checked only the rows the questions use, and no person has checked a table (D-104, D-114). A misread figure that breaks no total would be shared by the gold answers and the evidence. A secondary condition with automatically extracted tables (benchmark paper) was not run on the main answers in this version.
- **Scale.** 12 test issuers per country (392 test answers) give wide issuer-clustered intervals; we report them rather than per-answer intervals.
- **One training run per variant**, on free GPUs; seed variance is not measured.
- **The learned channel loses to its own starting point on natural answers.** Channel A's AUROC on the test split (0.579 [0.532, 0.624]) is below all four released detectors (0.609 to 0.688), including LettuceDetect v2 mmBERT (0.688), the checkpoint it was fine-tuned from (§4; [runs/main/report.md](../../runs/main/report.md)). Its contribution in this study is through the fusion with the rule checker.

## AI assistance statement

Claude (Anthropic's Claude Opus 5.5) wrote the project's code and drafted its documents, this paper included, at the authors' direction; every commit in the project's repository carries a "Co-Authored-By: Claude" line. Claude also drafted the benchmark's questions and gold answers and made the provisional pilot labels, which were used only for design decisions. Separate, blind Claude passes took every labelling and checking role the plan gave to people (D-103): the second reader of the 400 main questions and of the table rows they use, the labeller of every answer and of the audit sample, the second labeller of the 80 double-labelled tasks and the adjudicator of the 15 disagreements. The check of a sample of repaired answers (D-106) and the judgement of whether those repairs preserved the original's information (D-109) are blind Claude passes too. No person labelled, checked or adjudicated any benchmark item, and no person has checked a table (D-114). The kappa values are agreement between Claude's passes, not between people; there is no human agreement figure and no external adjudicator. The authors take responsibility for all content.

## References

`[Check every entry against the source and fill docs/related-work/detection.md.]`

- Angelopoulos, A. N., Bates, S., Candès, E. J., Jordan, M. I. and Lei, L. 2021. Learn then Test: Calibrating predictive algorithms to achieve risk control. arXiv. `[verify venue: the literature-review workbooks give The Annals of Applied Statistics 19(2), 2025, doi:10.1214/24-AOAS1998; not yet checked against the source]`
- Bates, S., Angelopoulos, A., Lei, L., Malik, J. and Jordan, M. 2021. Distribution-free, risk-controlling prediction sets. Journal of the ACM. `[verify]`
- Chen, Z. et al. 2021. FinQA: A dataset of numerical reasoning over financial data. EMNLP.
- Islam, P. et al. 2023. FinanceBench: A new benchmark for financial question answering. arXiv. `[verify]`
- Kovács, Á. and Recski, G. 2025. LettuceDetect: A hallucination detection framework for RAG applications. arXiv. `[verify]`
- Niu, C. et al. 2024. RAGTruth: A hallucination corpus for developing trustworthy retrieval-augmented language models. ACL.
- Padhi, I. et al. 2024. Granite Guardian. arXiv. `[verify; cite the 4.1 model card too]`
- Zhu, F. et al. 2021. TAT-QA: A question answering benchmark on a hybrid of tabular and textual content in finance. ACL.
- `[CITE: HHEM-2.1-Open model card, Vectara]`
- `[CITE: LettuceDetect v2 mmBERT and taxonomy head, model cards]`
- `[CITE: VeriFin]`
- `[CITE: XBRL specification and SEC EDGAR financial data]`
