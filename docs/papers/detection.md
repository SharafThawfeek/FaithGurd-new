# Right Number, Wrong Context: Relation-Aware Hallucination Detection for Financial Report QA with XBRL-Mined Supervision

M.L Ahamed, M.S.A Ahamed, Sharaf

> **Draft status (2026-10-13).** Written before the benchmark is labelled. The introduction, related work, method, setup and limitations are drafts to revise. Results are placeholders, `[RESULT: …]`, filled in phase 7 from the pre-registered analysis ([preregistration](../preregistration.md)). Numbers marked *development* come from the controlled track or the pilot's development issuers and test no hypothesis. Citations marked `[verify]` or `[CITE: …]` must be checked against the source and entered in [related-work/detection.md](../related-work/detection.md) before submission.

## Abstract

Answers about financial reports can quote a real figure from the evidence under the wrong context: the Bank's profit given as the Group's, last year's revenue given for this year, thousands read as millions. Such "right number, wrong context" errors are hard for general hallucination detectors, because the number does appear in the evidence. We train a span detector to catch them using supervision mined automatically from US XBRL filings: each fact is paired with a sibling fact that differs in one part of its context, and an answer stating the sibling's value under the original context becomes a labelled negative. A second head names the failing relation (entity or scope, metric, period, scale or currency, sign, basis, missing operand). The learned channel is fused with an exact rule checker and calibrated, and its threshold is certified with Learn-then-Test. On a new benchmark of 800 human-labelled answers about 48 US and Sri Lankan annual reports, `[RESULT: wrong-context recall with vs without XBRL supervision at an equal clean false-alarm rate]`. `[RESULT: A + B against B alone on Sri Lankan reports]`. A threshold certified on US filings `[RESULT: holds / fails]` on Sri Lankan reports, and `[RESULT: n]` local labels restore it.

## 1. Introduction

Retrieval-augmented question answering over annual reports is now routine, and its errors are costly: an analyst who receives a wrong figure with a confident sentence around it has no reason to check it. Few of these errors are invented numbers. In the pilot of our benchmark, wrong answers mostly computed a percentage from the right figures and printed it wrongly, reversed a sign, or misstated a scale (§5.1). The errors this paper targets are subtler still: a real figure from the evidence under the wrong entity, year or line item. A detector that asks only "does this number appear in the evidence?" passes them, and annual reports invite them, printing Group and Company columns, two years side by side and the same line item under several headings.

Two families of tools address answer faithfulness. Rule-based checkers recompute every number and trace it to a table cell; on template answers they are close to perfect, but they say nothing about claims without a printed number, and they reject correct claims phrased in ways their rules do not cover. Learned span detectors such as LettuceDetect (Kovács and Recski, 2025 `[verify]`) mark unsupported answer tokens and generalise across phrasing, but they are trained on general retrieval-augmented data (RAGTruth; Niu et al., 2024) in which the subtle failures of financial answers are rare.

This paper asks whether free, automatically mined supervision closes that gap. US public companies file their financial statements in XBRL, where every fact carries its concept, period, unit and dimensional context. For any fact an answer might cite, the same filing usually holds siblings that differ in exactly one part of that context and carry a different value. Stating a sibling's value under the original fact's context produces a realistic wrong-context error, with an exact label for the part that differs. We use this as a *training* signal for a span detector, not as a lookup at inference.

Our contributions:

1. **XBRL-mined wrong-context supervision** for a span detector: 14,512 labelled examples from the latest 10-Ks of 120 companies that never appear in the evaluation.
2. **A relation-slot head** that names the failing part of a flagged span, alongside the span head, so a downstream repairer or reviewer knows what to fix.
3. **A two-channel detector**, the learned channel fused with an exact rule checker and calibrated, evaluated on human-labelled natural answers with the false-alarm rate on correct answers as a headline metric.
4. **A cross-market test**: a threshold certified on US filings, applied to Sri Lankan annual reports as it is and after recalibration with 25 to 200 local labels.

We do not claim the first financial hallucination detector, nor the first typed or span-plus-evidence detector; related systems exist (§2).

## 2. Related work

**Hallucination detection for retrieval-augmented generation.** RAGTruth (Niu et al., 2024) provides span-level human labels of unsupported content in retrieval-augmented answers and is the standard training source for token-level detectors. LettuceDetect (Kovács and Recski, 2025 `[verify]`) frames detection as token classification over a long-context encoder (ModernBERT) and is our warm start. Its 2026 release adds a multilingual mmBERT encoder and a taxonomy head that types hallucinations (`[CITE: LettuceDetect v2 taxonomy head, model card — verify]`); that typed output is the closest prior work to our slot head and is compared directly in §5. Sentence- or answer-level judges include Vectara's HHEM-2.1-Open (`[CITE: HHEM model card — verify]`) and IBM's Granite Guardian (Padhi et al., 2024 `[verify]`; we use the 4.1 8B release), which scores groundedness among other risks. None of these is trained on financial context errors.

**Financial question answering.** FinQA (Chen et al., 2021) and TAT-QA (Zhu et al., 2021) pair questions about financial tables and text with gold answers and, for FinQA, executable programs; FinanceBench (Islam et al., 2023 `[verify]`) tests open-book QA over US filings. These datasets measure answer accuracy, not detection of unfaithful spans, and none covers Sri Lankan reports. We use FinQA and TAT-QA programs to inject controlled errors for training and development.

**Verification against filings.** `[CITE: VeriFin — open and verify]` checks financial answers against XBRL facts at inference time. We use XBRL only to build training data, so the detector needs no XBRL at inference and can run on Sri Lankan reports, which have none. `[Add any further financial verification systems found in the monthly literature refresh.]`

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

Human labels also mark unsupported non-numeric text. The slot set is the one the annotation guide uses ([annotation-guide.md](../annotation-guide.md)).

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

For each numeric claim, features from both channels (Channel B's verdict, the number of failing slots and whether it has a correct value for the claim; Channel A's highest and mean token probability over the claim and whether any token passes 0.5; whether the claim is a percentage and whether it carries a direction word) feed a logistic regression that predicts whether the claim is wrong. Isotonic regression calibrates it on the calibration split. An answer's risk is the probability that at least one claim is wrong, treating claims as independent (0.5 when there is nothing to check). The send-or-flag threshold is chosen by Learn-then-Test at α = 0.10 on the calibration split, so the share of unsupported answers among those passed is certified (companion policy paper).

## 5. Experimental setup

### 5.1 Data

**Benchmark.** 400 question groups about the latest annual reports of 24 Sri Lankan and 24 US issuers (12 test and 12 calibration per country, issuer-disjoint from all training and development data), each with a gold answer written as an expression over cells of hand-corrected tables. Each question is answered once by Qwen3.5-9B and Gemma 4 12B (4-bit, llama.cpp, thinking off), giving 800 answers. Human annotators, blind to the generator, mark unsupported spans with slots, the answer's status (correct, incorrect, ambiguous, unhelpful) and usefulness; 20% are double-labelled, agreement is reported with Cohen's kappa, and disagreements go to an accounting adjudicator. Full details are in the benchmark paper (`[cross-reference]`).

**Pilot** *(development)*. 120 answers to 60 questions on 8 development issuers, labelled by an AI annotator and awaiting human review: 23 incorrect (19.2%), mostly a computed percentage off in a printed digit, a reversed sign or a wrong scale. Channel B flagged 19 of the 23 and 16 of the other 81 numeric answers. These figures guide design only.

**Controlled track** *(development)*. FinQA and TAT-QA items with planted errors, split by issuer into fit, tune, calibration and test shares. Development results use 2,000 tune-share items.

### 5.2 Systems

- Channel A, with and without XBRL-mined negatives (the primary ablation), and without the slot head.
- Channel B alone; A alone; A + B fused.
- Released detectors: LettuceDetect v1-large and v2 mmBERT (risk = highest span confidence), HHEM-2.1-Open (risk = 1 − consistency) and Granite Guardian 4.1-8B at 4-bit, groundedness criterion, no thinking (risk = 1 if it judges the answer ungrounded). Every detector reads the same evidence text, focused as in §4.2 above 30 rows.

### 5.3 Metrics and hypotheses

Span F1 by slot (character overlap between predicted and gold spans; answers labelled ambiguous are left out and reported separately), wrong-context recall (entity_scope, metric and period spans), the false-alarm rate on correct answers, AUROC, Brier score, ECE, and coverage at certified selective risk (α = 0.10). Intervals come from an issuer-clustered bootstrap (2,000 resamples). The hypotheses and their decision rules were registered before the test set was opened:

| Hypothesis | Confirmed if | Rejected if |
| --- | --- | --- |
| D-H1. XBRL negatives raise wrong-context recall | Higher recall at an equal clean false-alarm rate | False alarms rise or recall does not move |
| D-H2. A + B beats B alone on Sri Lankan reports | Higher span F1, intervals not overlapping | No gain; rules suffice, reported as such |
| D-H3. The US threshold fails on Sri Lanka; about 100 local labels restore it | Risk above α before, within α after | Holds without recalibration; also reported |

For D-H3, the threshold is certified on US calibration answers, applied unchanged to the Sri Lankan test answers, then recertified on random draws of 25, 50, 100 and 200 Sri Lankan calibration labels.

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

- D-H1: `[RESULT]`
- D-H2: `[RESULT]`
- D-H3, with the label-efficiency curve: `[RESULT]`
- Released detectors and the slot head's typed output against LettuceDetect v2's taxonomy head: `[RESULT]`
- Where the learned channel adds value (RQ2): Sri Lankan reports, claims with no printed number, correct claims the rules reject: `[RESULT]`

## Limitations

- **Authoring and labels.** The benchmark's questions and gold answers were drafted with an AI assistant and the pilot was labelled by one; the test set is locked only after every table and question has a human second reader, and all reported labels are human (see the AI assistance statement).
- **How often wrong-context errors occur.** The pilot's natural errors were mostly miscalculated percentages, signs and scales. The main questions were written around wrong-context traps (Group against Company, prior-year columns, repeated line items) to raise their rate, but if natural answers still contain few such errors, D-H1's test has little power; the number of wrong-context spans is reported with the result.
- **Template supervision.** Controlled-track and XBRL-mined answers are written from templates. They teach the detector what wrong-context errors look like, but natural answers phrase things more freely, which is why every hypothesis is tested on natural answers.
- **US-only mining.** XBRL exists only for US filings. The Sri Lankan test measures how far US-mined supervision transfers; it cannot use Sri Lankan XBRL.
- **Hand-corrected evidence.** The main test checks answers against hand-corrected tables, so table-reading errors cannot be mistaken for model errors. A secondary condition uses automatically extracted tables (§ benchmark paper).
- **Scale.** 12 test issuers per country give wide issuer-clustered intervals; we report them rather than per-answer intervals.
- **One training run per variant**, on free GPUs; seed variance is not measured.

## AI assistance statement

`[Finalise before submission.]` Claude (Anthropic) wrote most of the project's code, drafted the benchmark questions and gold answers, produced the pilot labels used only for design decisions, and drafted this paper. Every benchmark table and question is checked by a person before the test set is locked, the reported labels are human, and the authors take responsibility for all content.

## References

`[Check every entry against the source and fill docs/related-work/detection.md.]`

- Angelopoulos, A. N., Bates, S., Candès, E. J., Jordan, M. I. and Lei, L. 2021. Learn then Test: Calibrating predictive algorithms to achieve risk control. arXiv. `[verify venue]`
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
