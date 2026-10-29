# FaithGuard: panel defence

*Written 29 October 2026, in the evening. While this was being written, the phase 7 analysis of the locked test was committed at 19:54 (commit b6d441a, runs/main/report.md and runs/main/results.json), so the answers below use its results. The papers' result sections and the README status were then filled from this run (commit 31e14c3 at 20:03, D-113), and the demo was hardened against the mock panel (commit 8fb9764 at 20:07; its text was then brought in line with the locked-test results in the commit that adds this document). Check every number against runs/main/report.md before the talk. The panel's live repros were kept in a temporary folder of the session that wrote this; the cases quoted below are enough to reproduce them.*

---

## 1. Read this first

1. **The honest framing:** FaithGuard is a pre-registered study, and its locked test has now been scored. One of nine hypotheses is confirmed: typed edit programs make far fewer new errors than free rewriting (R-H1). The others failed, were not confirmed, or could not be tested, and no policy could be certified at a 10% error budget on 396 calibration answers. We report all of it under the filed decision rules. Every change made after filing is logged as a deviation (D-105 to D-112), and the results are in runs/main/report.md (D-113).
2. **If a demo answer is wrong, say:** "Yes, that is a known limit of the frozen checker. It was frozen before the locked test (D-104), and the test has now been scored with it (D-113). Patching it now would mean showing a system we did not test. Where this kind of error appears in the benchmark's answers, the labels count it as wrong: the rule checker misses 26 of 170 wrong numeric answers. Some demo cases, such as questions about another company, are not in the benchmark at all. It is on our limitations slide."
3. **If the labels are attacked, say:** "Every label is a separate blind Claude pass, not a person, and every paper says so (D-103)." Then, if the spot-check is done: "Here is the human spot-check we did, and what it found." If it is not done: "No person has checked the labels yet. That is the first thing we will do, under a rule we recorded before drawing the sample."
4. **If a result or number is attacked, say:** "Is that a controlled-track number or a locked-test number? Controlled-track numbers are rehearsals on errors we injected ourselves. The claims rest on the locked test, and where a hypothesis failed we report it as filed."
5. **Never say** "human-labelled", "certified" about anything on the benchmark, or "every number checks out" as if it meant "the answer is correct".

---

## 2. The 15 hardest questions

### 1. Who checked anything that is not Claude?

**Q:** "Claude wrote the 400 questions, the gold answers, the rule checker and the gold scorer. Claude also did the second reading, the labelling, the double labelling and the adjudication. What in your evaluation was checked by anyone who is not Claude? Your status kappa of 0.89 is between two runs of the same model with the same guide. What does that number measure?"

**Say:** "No person labelled, checked or adjudicated any benchmark item. D-103 records this, and every paper says it. Kappa 0.89 (agreement beyond chance) is one model agreeing with itself under one guide, so it shows consistency, not that the labels are right. Some parts do not rest on Claude alone. The answers come from Qwen and Gemma. Each numeric gold answer is a formula over named report cells, so code recomputes the arithmetic, although Claude chose the cells and the formula (D-064, D-067). The labeller was blind to the system, the generator and the code labels (D-103). The checks could fail, and they did fail. The labels disagree with our rule checker on 136 of 672 numeric answers. The audit overruled 4 of 150 code labels, so every code label was dropped. The repair check failed one group at 16%, so labels replaced the code scorer there. [If today's spot-check is done, add: 'People labelled 60 test answers blind and agreed with Claude on __ of 60, so the disagreement rate is at most __% with 95% confidence.' If it is not done, say that no person has checked the labels yet.]"

**Back it with:** D-103; D-105 (kappa 0.89; audit 4 of 150; code labels fall); D-112 (repair check, 8 of 50); D-100 (gold cell programs); D-064; D-067; runs/main/labels/report.md (labels by claude-labeller@d103 and claude-adjudicator@d103; checker against labels); docs/papers/benchmark.md §3 ("No person labels an answer").

### 2. What does the certificate promise, and why did nothing certify?

**Q:** "State exactly what the certificate promises. Your demo says 'with 95% confidence at most 10% of released answers contain a wrong number', next to real Sri Lankan reports where I just released wrong figures. Your 396 calibration answers are 198 questions answered twice, from 24 issuers. What guarantee survives?"

**Say:** "As filed, it promises this: with at least 95% probability over the draw of the calibration answers, at most 10% of all sent answers are unsupported, repairs included. That holds for new answers drawn the same way as the calibration answers, as judged by our labels for original answers and by our code gold scorer for repaired ones (preregistration §4; D-112). It promises nothing about one answer, one company, Sri Lanka alone, another generator or next year's reports. The figure in the demo is the controlled-track certificate, made on errors we injected into FinQA and TAT-QA, so it does not cover the real reports on screen. On the locked benchmark nothing certified, for two reasons. Settings that send a lot made too many errors: repairing every answer sent 266 calibration answers with 18 wrong, where our certificate allows at most 13 (D-113). Cautious settings sent too little: a setting must send at least 132 of the 396 with no error, and LightGBM's first setting sent only 6.4% of test answers, so the fixed sequence stopped there. The settings that were not certified kept errors among sent test answers near 6% (threshold policy 5.9%, repair-everything 5.7%), but that is an observation, not a guarantee. Finally, with 24 calibration companies no company-level certificate can pass even with zero errors, so the company-clustered bootstrap is only a sensitivity check."

**Back it with:** src/faithguard/stats/certify.py (docstring; `selective_risk_pvalue`); docs/preregistration.md §4 (α = 0.10, δ = 0.05; note on issuer-level testing; how original and repaired answers get their states); runs/main/report.md ("Policies on the test split": 0 of 56); runs/main/results.json (policy.study.families: repair_all p 0.343; uncertified references); runs/policy/controlled/report.md; D-102; D-112; D-113.

### 3. Why should the outcome-aware policy beat a threshold (P-H1)?

**Q:** "Your outcome models were fitted on small template tables. On Sunshine, a 'by how much' answer has every number supported and Channel B risk 0.0, yet it is withheld; the threshold baseline would send it. Across four Sri Lankan reports the deployed policy withholds 85 of 93 fully supported difference answers. On your controlled track 'repair everything' ties your learned policy. Why should we expect the outcome-aware policy to beat the threshold policy on natural answers?"

**Say:** "We had no development evidence that it would, and the test agrees: P-H1 is not confirmed. On the controlled track the main policies tied. LightGBM sent 73.8% with 1.6% wrong. 'Repair everything' and threshold policy v0 sent 74.0% with 1.6% wrong. Their useful coverage was 72.5% to 72.7%, against the hindsight oracle's 72.9% (the best choice for each answer, known only after the fact). Only the verified-only policy lagged: it sent 21.5%. On real reports the outcome models extrapolate on features such as table size that template tables never cover. That is why supported 'by how much' answers get a P(unsafe) of 0.66 and are withheld. On the locked test, LightGBM's P(unsafe) still ranks answers (AUROC 0.807) but is badly calibrated (ECE, the gap between predicted and observed rates, is 0.329). Its P(fix) is weak (AUROC 0.624), and the policy certified no setting. As filed, P-H1 is rejected: neither policy certified, so both send nothing and the difference is 0.0 [0.0, 0.0]. In the filed secondary comparison, the threshold policy at its most cautious uncertified setting is 51.5 points of useful coverage ahead [47.2, 55.7]. It carries no guarantee either, so we recommend neither as certified."

**Back it with:** runs/main/report.md (P-H1 and its secondary; outcome model table); runs/policy/controlled/report.md ("Certified policies on the test split"); docs/papers/policy.md §6.2; demo/README.md (Known limitations: "by how much", P(unsafe) 0.66); docs/preregistration.md §2 (P-H1 rule); D-102 (7); panel count of 85 of 93 (dbg3.py in the panel folder).

### 4. Released repairs that contradict themselves

**Q:** "On Sunshine, FaithGuard released 'Profit for the year declined by 2.5% in 2026, increasing from Rs. 2,243,695 thousand in 2025 to Rs. 3,500,217 thousand in 2026'. That is the Group's rate beside the Company's figures, with two opposite direction words, and all five gate checks passed. On Kinsale, a correct 'from $414.8 million to $503.6 million' became 'from $503.6 million to $503.6 million', and '$21.63 per diluted share' became '$503,614,000.00 per diluted share'. What does 'every released number is verified' mean if the sentence is false?"

**Say:** "It means less than it sounds, and we should stop saying it that way. The gate checks each number on its own: the cell it came from, recomputed growth rates, that nothing else changed, that the checker accepts it, and that the answer still answers the question. It does not check that the numbers in one sentence agree with each other, or that the number it replaced was a report figure at all. That is a real gap in the frozen gate (D-104), close to risk R-24. The fixes in the demo come from the rule repairer, which runs on the laptop's CPU. On the locked test, the rule repairer put a new wrong number into 6.2% of the answers it sent and turned 6.3% of correct answers wrong (both scored by code only). The trained repairer v1, which the evaluated system uses, did so in 0.4% of the answers it sent and turned none wrong."

**Back it with:** src/faithguard/repair/gate.py; src/faithguard/evaluate/repair.py (`summarise`: new errors counted over all sent answers); demo/views.py (`GATE_CHECKS`); demo/cases.py (the released repair is "rule repairer v0, live"); runs/main/report.md ("Repair on the test split", rule_spans rows); docs/risk-register.md R-24; panel repro R4 and novelty_knsl_year_first.json.

### 5. "ChatGPT with the PDF is accurate"

**Q:** "ChatGPT or GPT-5 given the PDF is already accurate. Your 22.5% error rate comes from two 9-12B models at 4 bits with thinking off, and the AI in your live demo is a 2B model. Why does FaithGuard need to exist?"

**Say:** "We agree on the facts. The benchmark's generators are Qwen3.5-9B and Gemma 4 12B at 4 bits with thinking off. The demo's AI is a 2B model chosen to show the pipeline on a laptop, and our papers say larger or proprietary models may err differently. We do not claim frontier models are wrong 22% of the time. FaithGuard does a different job from answering: it tries to trace each number to a report cell and to repair or withhold what does not match, whichever model wrote the answer. When it cannot tell which line a number is about, it currently lets the number through, and that is a known gap. With a very accurate model the real question is the cost, and we report it: the rule checker flags 110 of 502 correct numeric answers. [Add today's result: 'We asked ChatGPT ten questions on Sunshine's report, with the PDF, and it got __ right.' Give the real number, whatever it is.]"

**Back it with:** docs/preregistration.md §1 (Answers); docs/papers/benchmark.md Limitations ("Two generators"); demo/README.md ("Ask the AI": Qwen3.5-2B, adapter off; Known limitations: "when the question names no line item the report has, any figure from the tables passes"); runs/main/labels/report.md (checker against labels).

### 6. Channel A changes no decision

**Q:** "As far as I can see, Channel A never reaches a decision. natural_records runs the rule checker alone, the policy feature learned_span_max is always 0, and your fusion only rescores the rule checker's numeric claims. On template data Channel A flags 52% of clean answers, and A+B equals B alone. What does Channel A change in any send, repair or abstain decision?"

**Say:** "Nothing in the policy, and we should say that first. The deployed policy and its natural records use the rule checker (Channel B) alone. Channel A, the learned span detector, matters in the detection paper and in some repair variants. On the locked test, the pre-registered test of A+B against B on Sri Lankan span F1 (D-H2) found no difference: +0.024, interval −0.059 to 0.146. So, as filed, we report that rules suffice for finding spans. The fused score does rank answers a little better than the rules alone (AUROC 0.849 against 0.803, a secondary result). On natural answers Channel A alone is weak (AUROC 0.579), and on the test split it found none of the unsupported-text spans (0.0% of their characters). It beat the rules on test only for entity spans (87.5% of their characters against 0%), and the labels hold only 5 entity spans in all 788 answers. So far its value comes through the fusion's small ranking gain."

**Back it with:** src/faithguard/detect/__init__.py (`detect` = rules); src/faithguard/evaluate/analysis.py (natural_records); src/faithguard/evaluate/pilot.py (unsupported_text stored without a slot); runs/main/report.md (D-H2; AUROC differences; "Spans on the test split", 'none' column; Channel A AUROC); docs/papers/detection.md Table 6.2b; runs/detector/fusion/report.md; runs/detector/kaggle/eval-channel-a/results.json (0.518 against 0.009); runs/main/labels/report.md (30 unsupported_text spans; entity_scope 5).

### 7. D-H1 is untestable and the XBRL negatives target a rare error

**Q:** "Your detection paper's primary hypothesis is untestable. The XBRL negatives, your contribution 1, target an error the generators almost never make: 9 wrong-context spans in 788 answers against 130 value errors. The pilot had none, and on development data XBRL did not raise recall. Why was this not caught before the lock? And is the scarcity real, or does your labeller file everything under 'value'?"

**Say:** "We own it. Our pilot trigger (risk R-03) watched only the overall error rate, 19.2%, not the mix of error types, and the pilot labels had no wrong-context spans. We wrote the main questions around wrong-context traps, but the labels still mark only 9 such spans in 788 answers and only 4 test answers carry one. So D-H1 is untestable under the rule we filed before scoring. The development ablation had already shown no gain: AUROC 0.933 with the XBRL negatives (wrong examples mined from US XBRL tags) against 0.932 without. What remains is a finding: these generators mostly mis-compute rather than mis-attribute (130 value spans, 28 scale or currency, 17 sign). We cannot rule out that the labeller filed some context errors under 'value', and only a person re-slotting a sample can settle that."

**Back it with:** runs/main/results.json (detection.D-H1: 4 wrong-context test answers); runs/main/labels/report.md (spans by slot); runs/pilot/report.md; docs/papers/detection.md (development ablation table; Limitations, "Few wrong-context errors"); D-107 (3); docs/risk-register.md R-03, R-04.

### 8. Novelty against VeriFin, FinGround and FRED

**Q:** "VeriFin verifies answers against XBRL with a solver and abstains. FinGround rewrites unsupported claims with table-cell citations. FRED fine-tunes small models to detect and edit financial errors. The rows for these in your related-work tables are empty. In one sentence per paper: what is actually new?"

**Say:** "The building blocks are known: span detection, typed errors, verify-and-repair and risk-controlled abstention. Our plan lists these as claims to avoid. VeriFin works on US 10-K filings with XBRL. It plans with Claude Haiku 4.5, checks with a Z3 solver and outputs Verified, Violated or Abstain, with zero false accepts on its fixed candidate pools but 37-73 correct claims rejected, and it repairs by feedback-guided regeneration. Our claims are narrower:
- **Repair:** on the same 2B model and data, typed edit programs made 10.6 points fewer new errors than free rewriting and corrected 28.9 points more on natural errors (R-H1, confirmed).
- **Detection:** a detector trained from US XBRL that runs on Sri Lankan PDFs with no XBRL. On the locked test, fusing it with the rules gives only a small ranking gain (AUROC +0.047), it does not find Sri Lankan spans better (D-H2), and its XBRL test could not be run (D-H1).
- **Policy:** a certificate that counts the errors repair introduces, tested on a replay where every action is run on every answer. On our 396 natural calibration answers it certified nothing.
- **Benchmark:** the only Sri Lankan annual-report faithfulness set we found.

We have not run VeriFin or FinGround as baselines, and our comparison tables are still empty, so these claims stay provisional until we have read and compared them."

**Back it with:** docs/FaithGuard-Revised-Plan.md ("Defensible claim" and "Claims to avoid" for each paper); docs/related-work/detection.md, repair.md, policy.md (rows empty); docs/papers/*.md ("[CITE: … open and verify]"); runs/main/report.md (R-H1; D-H1; D-H2; AUROC differences; Policies on the test split); VeriFin arXiv 2608.10213 (open it today and confirm these facts).

### 9. Dropping human labelling, the "never cut" item

**Q:** "Your plan lists the human-labelled test set as never cut. On 28 October D-100 rejected Claude labelling all 800 answers and promised that a person would label the 61 pilot code labels before filing. One day later D-103 gave every role to Claude, saying 'the user works alone'. You are three members. Why could none of you label even 50 answers?"

**Say:** "D-103 replaced the plan's never-cut human labelling, and we say so plainly: our results rest on AI labels, not human ones. The change was recorded and written into the pre-registration before filing, so it is not hidden or decided after the fact. The person's blind review of the 61 pilot code labels that D-100 promised did not happen, and we are logging that as a deviation."

First, acknowledge the recorded reason: "D-103 records the reason as 'the user works alone'. That is not a good reason for a team of three, and we should have labelled a sample ourselves." Then give the team's agreed sentence, and say what human validation has actually been done today (fill this in only with real counts).

**Back it with:** docs/FaithGuard-Revised-Plan.md ("Never cut: the human-labelled natural test set"; "LLM judges ... never for test labels"); D-100; D-103; docs/preregistration.md §1 ("Who does it (D-103)"); docs/risk-register.md R-23; docs/authorship.md.

### 10. The gate turns right answers wrong (accounting)

**Q:** "On Sunshine I typed the correct Group profit attributable to owners of the company, Rs. 3,052,657 thousand. FaithGuard 'repaired' it to Rs. 5,035,750 thousand, which is the whole profit for the year including the non-controlling interests. Tokyo Cement's cost of sales rose; your AI said it fell 19.4%, and FaithGuard released 'decreased by 28.4%'. 'A loss of Rs. 16.7 million' was withheld, but '-Rs. 16.7 million' was sent. How can a gate that turns a right answer wrong be called a safety gate?"

**Say:** "These are real failures. The gate cannot catch them because it inherits the checker's reading: its provenance check only confirms that a copied cell matches what the checker thinks the claim is about. There are three causes in the frozen checker:
- it reads 'profit attributable to' as the total row;
- costs printed in brackets are stored as negative numbers, so a growing cost reads as a fall;
- its sign model ignores the words 'loss', 'expense' and 'deficit'.

Our demo README already lists the first two as known limitations. The system stays frozen as it was tested (D-104, scored in D-113), and the gate makes repairs consistent with the checker, not safe in general. We have not yet counted how many of the repairs the repairers sent on the locked test hit these patterns (no policy certified, so the benchmark policy itself released nothing; the labels mark 17 sign spans). That count goes into the error analysis."

**Back it with:** demo/README.md (Known limitations: bracketed expenses, "profit attributable to"); docs/papers/repair.md (provenance definition); D-104; D-113; runs/main/report.md (Policies on the test split: 0 certified; Repair on the test split); runs/main/labels/report.md (sign 17); panel log fin\ai_log.jsonl (ask-3336-359, ask-3336-365).

### 11. Nonsense passes when the checker cannot name the line item

**Q:** "I asked Tokyo Cement 'What was the Group's revenue in 2026?' and typed 'The Group's revenue was Rs. 71.60 in 2026.' That is the net asset value per share, and the page said 'Every number checks out.' Arbitrary ROE values were sent on every report, dividend income was sent as dividends paid, and 'It was 100%' was sent for profit. How is this a faithfulness checker?"

**Say:** "The frozen checker works out which line item a number is about from the words in the question and answer. Sometimes it cannot find the line. Tokyo Cement prints 'Revenue from contracts with customers', so plain 'revenue' does not match, and ROE, dividends paid and cash flow are not in the two statements at all. Then the checker has nothing to compare the number with, so any figure from that year passes, and so does any share or growth rate of two cells. The benchmark's questions are written in the reports' own line names, so the evaluation mostly avoids this case. A deployed system would not avoid it, and 'supported' should then read 'cannot be checked'. The checker also reads only numbers: it does not check that the answer answers the question, which company is named, or the words around the numbers."

**Back it with:** demo/README.md (Known limitations: "when the question names no line item the report has, any figure from the tables passes"); src/faithguard/detect/rules.py; D-064 (questions built from the cells' own labels); docs/preregistration.md §1 (evidence: income statement and balance sheet); panel sweep fin\sw2.txt.

### 12. Planted errors are caught by construction

**Q:** "I pressed 'Try to trick it', took 'Take a figure from the wrong line: use Gross profit', and the page said 'You planted a mistake' and then 'Every number checks out.' Your README says planted errors are only offered where the checker can see them. And every number on your Results screen comes from errors your own injector planted, of exactly the types your checker checks. Why show those numbers at all?"

**Say:** "That is fair. All 1,145 planted errors on the 260 one-click questions were caught because they are chosen where the checker can see them, so that 100% is by design. It shows the mechanism, not accuracy. The same holds for the controlled-track numbers (Channel B: 0.9% false alarms, 99.7% wrong-context recall), which come from our own error injector and which we treat as rehearsals (risks R-17 and R-20). On AI-written or typed answers the claim does not hold: when the checker cannot tell which line an answer is about, a wrong-line figure passes. Judge us by the natural numbers instead: on 672 labelled numeric answers the rule checker caught 144 of 170 wrong ones (84.7%) and flagged 110 of 502 right ones (21.9%)."

**Back it with:** demo/README.md (Stress tests: "planted errors are offered where the checker can usually see them"; re-check this wording after today's demo commit); runs/detector/kaggle/eval-channel-a/results.json; runs/main/labels/report.md; docs/risk-register.md R-17, R-20.

### 13. Why train a repair model if rules do as well?

**Q:** "On the only natural errors you have, the untrained rule repairer corrects 10 of 23 and your fine-tuned Qwen3.5-2B corrects 9. Self-training changed nothing. Why does the repair paper need a trained model?"

**Say:** "The 23 pilot errors could not separate them, but the locked test did, on safety rather than correction. With the rule checker's spans, both corrected about half of the 83 wrong answers: the rule repairer 50.6% scored by code, and v1 50.6% with labels for its changed repairs, or 49.4% scored by code like the rules. The rule repairer put a new wrong number into 6.2% of the answers it sent and turned 6.3% of correct answers wrong, against 0.4% and 0.0% for v1. That is a secondary comparison with no interval in the report, and the rules' numbers are scored by code only. Self-training also did not tie on test: stage B corrected 18.2 points more than stage A on Gemma's answers (interval 4.7 to 31.0). R-H2 is still not confirmed, because its held-out basis arm has only 2 test answers and we filed a rule that needs both arms."

**Back it with:** runs/main/report.md ("Repair on the test split"; "Scored by the gold scorer instead"; R-H2); runs/main/results.json (repair.R-H2); src/faithguard/evaluate/repair.py (`summarise`); runs/pilot/v1run-repair-v1/report.md (43.5% against 39.1%); docs/papers/repair.md §6.1; D-107 (4); D-112.

### 14. The scorer, checker and gate share blind spots

**Q:** "The rule checker flags errors, the gate rechecks repairs with that same checker, and the gold scorer that decides whether a repair is correct reads numbers with the same code. Originals are judged by Claude's labels, which mark unsupported text. Repaired answers are judged by your numbers-only scorer, so a repair that fixes the figure and keeps 'driven by record loan growth' counts as a fix. How do you know a 'corrected' repair is correct?"

**Say:** "Not fully, and we named this risk before filing (R-25). On original answers the scorer called 25 labelled-wrong answers right, and the rule checker missed 26. We have not yet counted how many of these are the same answers; that overlap is the shared blind spot. The guard is the repair check. A blind Claude pass labelled 143 changed repairs, and code and labels disagreed on 3 of 43 and 3 of 50 for the two R-H1 arms and on 8 of 50 for the other variants. So all 509 of the other variants' changed repairs were labelled, and their labels replaced the scorer's states in the repair summaries, R-H2 and R-H3. The new-error counts and the policy's records still use the scorer (D-112). Our one confirmed result, R-H1, still uses the scorer's states for its two arms. For v1 the check covered all 43 of its changed repairs, and labels and scorer differ on exactly 3: on two the scorer was stricter than the label, on one more lenient. For free rewriting it covered 50 of 63. 3 of 50 allows a true disagreement rate of up to about 15% (one-sided 95%), and those 3 also split two stricter and one more lenient. We will also report, beside R-H1, how many changed repairs keep unsupported wording, along with the labels' 'information preserved' rates (97.7% for v1, 90.0% for rewriting)."

**Back it with:** D-106; D-112; runs/main/report.md ("Repair check (D-106)"; "Information preserved"); runs/main/results.json (repair.repair_check, disagreements listed per arm); runs/main/labels/report.md (scorer right, labelled incorrect: 25; missed, labelled incorrect: 26); docs/preregistration.md §6 (R-25 note).

### 15. Sri Lankan coverage and sample sizes

**Q:** "How representative are your 24 Sri Lankan companies? The candidate list was 'written from memory', plantations and finance appear only in test, telecom only in calibration, and you use two statements per report. What can you say about Sri Lanka specifically, and where is the search record behind 'first Sri Lankan resource'?"

**Say:** "The frame was a hand-written list of 33 well-known Colombo Stock Exchange companies, checked against the exchange's own list (D-038) and split with seed 2026. It is not a random draw, so it leans towards large companies that report in English. Sri Lanka has 12 test and 12 calibration companies, 248 questions and 496 answers, of which 107 are labelled incorrect, and the evidence is the income statement and balance sheet only. Sectors differ between the splits (plantations and finance only in test, telecom only in calibration), so 'drawn the same way' holds only approximately, and we will report results by sector. On the test, A+B found Sri Lankan spans no better than the rules (D-H2), nothing was certified for Sri Lanka, and on 'first' our wording is 'we found no comparable public resource'. That search record still has to be written down."

**Back it with:** D-038; manifests/issuers.csv with manifests/splits.json; docs/papers/benchmark.md (abstract, §3); runs/main/labels/report.md; runs/main/report.md (D-H2, D-H3); docs/related-work/benchmark.md (search record empty).

---

## 3. By lens

### Methods

**Q:** "R-H1 compares edit programs, run by an executor and a five-check gate, with free rewriting that has no gate. Isn't 'programs make fewer new errors' just 'gated output makes fewer new errors'?"
**Say:** Partly, yes. R-H1 compares two whole systems, and the repair paper says so. We can add a gated-rewrite arm as exploratory work on the laptop CPU: pass the stored rewrite outputs through the frozen recheck, withhold the failures, and label the result as not pre-registered. Part of the gap can never be separated, because the provenance and envelope checks need a program.
**Back it with:** docs/papers/repair.md (baseline described as "no executor and no gate"); runs/main/report.md (R-H1); D-110.

**Q:** "Your pre-registration tag is from 08:19 on 29 October. Since then analysis.py has grown by hundreds of lines, with same-day deviations made after the label distribution was known. What did the pre-registration constrain?"
**Say:** The checker, gate, policy features, deployed policy, gold scorer and triage rules are unchanged since the tag. git shows no diff for detect/rules.py, repair/gate.py, policy/features.py, policy/deployed.py, evaluate/score.py or evaluate/triage.py. Other code did change, and every change is logged: analysis.py (+447/−72) and the policy study and transfer code, so that they compute what the filed text names (D-107, D-109), plus how labels are used for the repair-check group that failed (D-112); the units note in the labelling tasks (D-105); the repair check (D-106); Granite Guardian reading long prompts in chunks (D-108); and the rewrite baseline declining narrative answers with no numbers, which no analysis scores (D-111). Each change was committed before the analysis commit (b6d441a). Some changes were written after the label counts were known, and D-112 after the repair check's disagreement rates, so we will publish the diff from the tag.
**Back it with:** `git diff --numstat prereg-v1 HEAD -- src/faithguard`; docs/decision-log.md D-105 to D-112; git log (D-112 at 19:29, b6d441a at 19:54).

**Q:** "Where exactly is the wall between development and test? The checker, triage rules and guide were tuned on the pilot, and the demo runs on those same reports."
**Say:** Test and calibration companies never appear in the pilot, the training data or the demo. The demo's five real reports are development companies, and the XBRL training set's 120 companies are outside the evaluation. The demo is in-sample for the checker's rules (D-057), so it shows how the system works, not how well it works.
**Back it with:** manifests/splits.json (dev: CFIN, SAMP, SUN, TKYO, KNSL, DKS, MEDP, SLAB); D-057; D-104; docs/papers/detection.md (contribution 1).

**Q:** "Your detection baselines are general hallucination detectors. Have you beaten anything a reviewer would call a strong baseline?"
**Say:** We beat the released general detectors on the locked test: the fused score's AUROC (how well a score ranks wrong answers above right ones; 0.5 is chance) is 0.849 against LettuceDetect v2's 0.688, a difference of 0.161 [0.096, 0.231]. The strongest baseline in our design is our own rule checker (0.803), and fusion beats it only slightly (+0.047). We have not compared with VeriFin or FinGround.
**Back it with:** runs/main/report.md ("Detectors on the test split"; "AUROC difference"); docs/related-work/detection.md.

### Statistics

**Q:** "Your papers say certification needs 29 sent answers, or 32 under your certificate. With 396 calibration answers and your linearised loss, how many must a setting send? Can the first setting of your fixed sequence pass at all?"
**Say:** 29 is the count for an exact test on sent answers alone, which we do not use. Our certificate's 32 holds only when every calibration answer is sent, because the loss charges each withheld answer exactly at the boundary value. A setting must therefore send at least 132 of 396 with no error (67 of 100; 100 of 198). The first LightGBM setting (send if P(unsafe) < 0.02, repair if P(fix) > 0.99), ordered on template answers, has p = 0.99 on calibration (a setting certifies only if p is at most δ = 0.05), so the fixed sequence stopped at once. On test it sends only 25 of 392 answers (6.4%). At the rates seen, LightGBM's first setting could not certify at any number of labels, and the neural model's would need about 792. We will correct the wording in policy §4.4.
**Back it with:** src/faithguard/stats/certify.py (`zero_error_budget` = 29, `hb_zero_error_budget` = 32, the shifted loss; `selective_risk_pvalue`; minimums checked by running it); docs/papers/policy.md §4.4 and §6.2; runs/main/results.json (policy.study.families: outcome_aware[lightgbm] uncertified reference "send<0.02,fix>0.99", p 0.990, sent 25 of 392; labels_needed lightgbm null, neural 792); docs/preregistration.md §4 (δ = 0.05).

**Q:** "Recalibration with 100 labels (P-H3, and D-H3 with Sri Lankan labels): what does 'restored' actually test?"
**Say:** In the end both were untestable, because nothing certified to begin with. As designed, 100 labels is close to a zero-error test: at least 67 sent, none wrong. In the controlled transfer rehearsal, where about 1% of sent answers were wrong, 100 labels certified in 48% of draws and 200 in all of them. On natural answers, 200 labels certified in none of 50 draws for LightGBM and in 1 of 50 for the neural model, and all 396 did not certify. So on real answers no label count we tried was enough. 'Unsafe' is decided on the lower end of an interval. 'Restored' needs at least half of 50 draws of 100 labels to certify, with a test risk at most α as a point estimate. So the two use different standards of evidence, and we will state that.
**Back it with:** runs/main/report.md (D-H3, P-H3; Certification budget); runs/main/results.json (policy.study.budget_curve); runs/policy/transfer/report.md; docs/preregistration.md §2 (D-H3, P-H3); D-107 (2); D-109 (5).

**Q:** "Your Hoeffding-Bentkus test treats 396 answers as independent. Why trust a percentile bootstrap over 24 clusters?"
**Say:** We don't treat it as a guarantee. With few clusters a percentile bootstrap can under-cover, and it returns zero when no error is seen. It is a sensitivity check beside a certificate that works answer by answer. We report companies, questions and answers separately, because Qwen and Gemma answering the same question shrinks the effective sample.
**Back it with:** D-102 (4); docs/preregistration.md §4 (issuer-level check); docs/papers/policy.md §4.4 ("Issuer dependence").

**Q:** "Your certified quantity is 'unsupported', but according to whom? How large could label error be compared with alpha?"
**Say:** It is relative to our labels, and we cannot rule out label error near α. The policy's calibration repairs are scored by code only, because the repair check samples test repairs (D-112). Nothing certified, so label error cannot have produced a false guarantee here. It could only change whether a setting certifies. Before drawing anything, we are logging a human spot-check today: if the upper bound on disagreement between people and Claude is above 10%, every verdict is reported as provisional. It samples test answers, so it checks the labels in general, not the calibration labels the certificate used.
**Back it with:** D-106; D-112; docs/preregistration.md §4; runs/main/report.md (Policies: 0 certified in every family); docs/decision-log.md (latest entry D-113; the spot-check entry is still to be logged).

**Q:** "P-H1: if the threshold policy certifies nothing, you win against a policy that sends nothing. And is your 'calibrated detector threshold' the detection paper's calibrated fusion?"
**Say:** Neither side certified, so P-H1 compared two policies that send nothing, and we will not present it as a win for either. The pre-registered secondary comparison, at the threshold policy's most cautious uncertified setting, puts the threshold policy 51.5 points of useful coverage ahead [47.2, 55.7], because the uncertified outcome-aware policy sends nothing. And no, it is not the fusion: the comparator thresholds the rule checker's three-valued risk (0, 0.5 or 1).
**Back it with:** runs/main/report.md (P-H1 and its secondary); src/faithguard/detect/rules.py (`VERDICT_RISK`); D-109 (7).

**Q:** "How many certificates and tests do you run, and what is the family-wise error of the claims you will headline?"
**Say:** On the benchmark we ran seven policy families, 126 settings in all (1 + 1 + 3 + 3 + 6 + 56 + 56). Each family is tested in a fixed sequence that stops at the first failure, so within a family the chance of any false certificate is at most δ = 0.05. LightGBM was named in advance as the primary outcome model, with the others reported and never chosen among. There is no correction across families or across the nine hypotheses. To limit that, the pre-registration names one primary comparison per paper: D-H1 for detection, which was untestable; R-H1 for repair, which was confirmed; and P-H1 for policy, where nothing certified. The one claim we headline, R-H1, is a single pre-registered test, not a pick from many.
**Back it with:** docs/preregistration.md §3 (one primary comparison per paper) and §4 (Procedure; Outcome models: LightGBM primary); runs/main/report.md (Hypotheses; Policies table).

**Q:** "D-H3 certifies a fused-risk threshold on calibration answers that the fusion was itself fitted and calibrated on. Is that certificate valid?"
**Say:** Not strictly: the score saw those answers, so its p-values would be optimistic. In the result it is moot, because no US threshold certified and D-H3 is untestable. The design flaw is still real, and the paper will name a fusion fitted on development companies as the clean design.
**Back it with:** src/faithguard/evaluate/analysis.py (fusion fit; D-H3); docs/preregistration.md (Frozen inputs: "the fusion is refitted on calibration answers"); runs/main/report.md.

**Q:** "Which repairer does your P(fix) model predict, and whose repair outcomes does the benchmark policy act on?"
**Say:** The outcome models were fitted on the rule repairer's controlled-track replays, but the natural records carry v1's outcomes. That mismatch may be one reason P(fix) reaches only AUROC 0.624 on test. We have not tested it, and the small template tables are another candidate. Validity is unaffected, because calibration and test both carry v1's outcomes. The learned-span feature is zero in every controlled replay record.
**Back it with:** src/faithguard/evaluate/analysis.py (natural-records docstring; policy(): controlled = the rule repairer's replays, natural = repairer v1 on rule spans); D-102 (3); runs/main/report.md (outcome models); runs/controlled/*/replay.jsonl (learned_span_max zero in all records checked).

**Q:** "What can you say about the generator shift (certified on Qwen, reported on Gemma)?"
**Say:** Nothing is certified there either (0 of 56 settings). It was a stress test that breaks 'drawn the same way' on purpose.
**Back it with:** runs/main/report.md ("Generator shift"); D-109 (11).

### Data and labels

**Q:** "You call the evidence 'hand-corrected'. Who corrected the 96 tables, how many cells did they change, and what would catch a swapped year column or a Group column read as Company?"
**Say:** "Hand-corrected" overstates it. The Sri Lankan tables are our PDF reader's output, with manual header fixes for one company (People's Leasing), and every subtotal adds up. An arithmetic check cannot see a swapped column, though. The page check D-060 planned for a person was done by a Claude pass (D-103), and it checked the rows the questions use against the source pages, not every cell (D-104). The 48 US tables are read from the filings' HTML, and a fresh automatic reading gives the same tables (D-070). No person has checked any table yet. If today's check against page images is done, give its result; if not, say so.
**Back it with:** docs/preregistration.md §1; D-060; D-070; D-103; D-104; data/benchmark-tools/build_lk_main.py (`FIXES`: PLC headers only).

**Q:** "Who wrote the 400 questions and how? Your second reader found no wrong gold, but the second reader is the model that wrote them."
**Say:** Claude drafted all 400 with scripts: the Sri Lankan questions are built from the tables' own row labels (D-064), and Claude chose the US questions one at a time, each around a trap in its own tables (D-067; author Claude, `checked_by` empty until D-103's pass). The second reader was a separate Claude pass that found 6 questions with two readings, which we excluded, and no wrong gold (D-104). A correlated reader finding nothing is weak evidence, and `checked_by: claude-check` marks a pass, not a person.
**Back it with:** D-064; D-067; D-103; D-104.

**Q:** "Two of your four audit overrules are Gemma giving diluted EPS 'in thousands'. Did your evidence cause those errors?"
**Say:** Partly, yes. Our renderer prints one units line per table and drops the filings' "except per share" note, so our evidence made those errors easier. The answers are hashed and cannot be regenerated, so we will disclose this and report per-share scale errors separately.
**Back it with:** D-105 (ENSG-2025-02, POOL-2025-02); src/faithguard/generation/answers.py.

**Q:** "Your pilot decisions all rest on Claude's labels of 120 answers. What did the pilot actually validate?"
**Say:** It validated the pipeline: no thinking leaks, no empty answers, and an error rate above the 10% floor (19.2% by Claude's labels). It did not validate label quality, and those labels were made from tasks that left out each table's units note, so they are development-only (D-105). Minutes per item were never measured (R-01), and guide v2's freeze condition, a person's review, was never met. We are logging that as a deviation.
**Back it with:** D-066; D-068; D-105; runs/pilot/report.md; docs/risk-register.md R-01, R-03.

**Q:** "If a person now labels some of your test answers and disagrees with Claude, what changes? How many items, drawn how?"
**Say:** Before drawing, we record the rule in the decision log: 60 test answers, 15 per country and generator, each 15 made of 10 that Claude labelled correct and 5 it labelled otherwise, with the seed logged. Because the sample over-weights answers Claude called wrong, we report disagreement in each group and the rate reweighted to the test mix. The check changes no label. The 10% rule applies to the raw count of 60: if its upper bound is above α = 10% (2 or more disagreements of 60), every verdict is reported as provisional until people relabel the test set, and the reweighted rate is reported beside it.
**Back it with:** the "Do today" plan (steps 2 and 3); src/faithguard/stats/certify.py (`clopper_pearson_upper`: 0/60 4.9%, 1/60 7.7%, 2/60 10.1%); docs/decision-log.md (no spot-check entry after D-113 yet).

**Q:** "How many of your 177 'incorrect' answers are real hallucinations, and how many are a percentage off in its last printed digit?"
**Say:** We have not split them by size yet. The strict rule is deliberate: a figure must match the report at the precision the answer prints, so "about 10%" for 9.29% counts as wrong. Call the 22.5% a strict-precision error rate, and promise an exploratory split of last-digit slips against material errors.
**Back it with:** docs/annotation-guide.md (Rounding; the computed-figure row: "about 10%" for 9.29% is wrong); D-068; D-066 (pilot value spans mostly a computed percentage off in its last digit); runs/main/labels/report.md (value 130).

### Finance

**Q:** "I asked for the Company's (standalone) profit and the answer gave the Group's Rs. 2,580 million, labelled 'Group'. You sent it. Is consolidated against standalone handled at all?"
**Say:** Only partly. A figure from the wrong column is caught. But the checker takes the entity from the answer's own words first, so a true Group figure given for a Company question passes, and when no entity is named either column is accepted. Natural answers rarely make this error (5 entity spans in 788).
**Back it with:** runs/main/labels/report.md (entity_scope 5); docs/papers/detection.md (Limitations); panel repros.

**Q:** "Your one-click button 'What was the Group's non-controlling interest in 2026?' answers with the comprehensive income attributable to NCI, not the balance-sheet NCI, and Tokyo offers 'What was the Group's voting in 2026?'. Who checked these buttons?"
**Say:** The pre-check proves only that the template and the checker agree, not that an accountant would read the question that way. Breakdown rows lose their parent heading in parsing. Since this evening's commit 8fb9764, the one-click list leaves out attribution rows and continuation rows like '- Voting', so those buttons should no longer appear. If one still does, do not click it.
**Back it with:** demo/README.md (pre-check: "each is kept only if the template answers it and the live pipeline sends that answer"); demo/ask.py (lines 241-247; commit 8fb9764); panel repro ask-3336-366.

**Q:** "Sunshine's 2025 Group column is headed '(Restated*)'. How do you treat restatements?"
**Say:** We don't model them: the checker reads only the year, so 'as originally reported' goes unchecked. Growth on a restated base is the right like-for-like practice, but the answer should say so. This goes on the limitations list.
**Back it with:** panel repro (column label "Group 2025 (Restated*)").

**Q:** "Your refusals explain themselves with irrelevant figures, and a per-share 24.48 is printed as 'Rs. 24.5'. Is the explanation layer reliable?"
**Say:** No. The note lists the cells a wrong number happened to match, which is just noise when the match is a coincidence, and it rounds per-share figures. The text comes from the frozen pipeline.
**Back it with:** src/faithguard/pipeline.py (`evidence_note`).

**Q:** "Your README says the stress test of 68 AI questions had 'no bad repairs'. In 8 live questions I got two bad repairs and three wrong figures sent. Who judged the 68?"
**Say:** They were judged against the tables by a separate reviewer (demo/README.md). [Confirm today who that was, and say it plainly.] The 68 questions are not listed in the repository, so 'no bad repairs' holds only for that sample, and your eight questions show it missed cases like the ones you found.
**Back it with:** demo/README.md (Stress tests, "The AI"); commit dd6bbc3 (message: judged against the tables); panel log fin\ai_log.jsonl.

**Q:** "The Results screen says 'the human-labelled test comes next', but D-103 says Claude takes every human role. Which is true?"
**Say:** D-103 is true. The Results banner said 'human-labelled' until this evening's commit 8fb9764. It now says the locked test is labelled by separate blind Claude passes, not people. Its last words, 'System results on it come next', are also out of date now that the test results exist (runs/main/report.md). The "human-labelled" line that remains in the controlled-track report is printed by frozen code (src/faithguard/policy/study.py) and was written before D-103; the src/faithguard/splits.py docstring has the same old wording.
**Back it with:** D-103; demo/static/app.js (line 800); commit 8fb9764; runs/policy/controlled/report.md (line 12, under the split table); src/faithguard/policy/study.py (line 300); src/faithguard/splits.py (line 6); demo/README.md ("Output and Results").

### Demo

**Q:** "Your one-click questions are kept only if the pipeline sends the template's answer, and the live AI's prompt was changed so the checker reads it better. How representative is this demo?"
**Say:** Not representative, and we say so aloud. What we click has been checked in advance, and the 2B AI is asked for one sentence because its worked answers break the checker's one-period-per-clause limit. For representative numbers, use the benchmark. 22.5% of the 9-12B generators' 788 answers are labelled incorrect, and on 672 numeric answers the rule checker catches 144 of 170 wrong ones and flags 110 of 502 right ones. The demo's 2B AI was not measured on the benchmark.
**Back it with:** demo/README.md ("Ask your own question"; "Ask the AI": Qwen3.5-2B; Known limitations); runs/main/labels/report.md; docs/preregistration.md §1 (Answers).

**Q:** "I asked Kinsale's report about Apple's net income, and FaithGuard sent Kinsale's figure. Why?"
**Say:** The frozen checker checks numbers against the one report you chose and does not know company names, so 'Apple's' reads as no company at all. The demo was missing a guard for this. Since this evening's commit 8fb9764 it refuses a question that names another company and says which report it checks against. That guard is demo-side only: the evaluated system has none, and the benchmark has no cross-company questions.
**Back it with:** panel repro (US:KNSL, "What was Apple's net income in 2025?"); demo/ask.py (`other_company`); demo/README.md (On-screen warnings); commit 8fb9764.

**Q:** "Your README says the AI answers 'grew by 49.6%', but on screen it says 49.9%. Did you tune the questions until they worked?"
**Say:** The old README figure was from an earlier rehearsal. Decoding is greedy, but the AI's one-sentence prompt was tightened between rehearsals (demo/models.py `ANSWER_SYSTEM`), which changes its words. Today's answer is the one recorded in demo/rehearsal.json (49.9%), the outcome is the same ('declined by 25.4%'), and the README now says 49.9%. The one-click suggestions are pre-checked by design, and we say that.
**Back it with:** demo/README.md (suggested script) against demo/SIMPLE.md (49.9%); demo/rehearsal.json (LK:TKYO); git log -- demo/models.py (last change dd6bbc3).

**Q:** "What happens if the GPU or the AI fails during your talk?"
**Say:** The checker, policy, rule repairer, gate and planted errors all run on the CPU, and the full demo restarts with `--no-models` on stored outputs. With the AI off, 'Ask the AI' still gives its rehearsal answer to the scripted questions, labelled on screen as recorded (demo/rehearsal.json), so the script still runs. Only new typed questions lose the live AI. For those we take the answer from the table, type one in, or play the backup video.
**Back it with:** demo/README.md ("Before the talk"; "Recording a backup video"); demo/cases.py (`REHEARSAL`; `ask_ai`); demo/static/simple.js (line 209); demo/rehearsal.json.

**Q:** "Is the demo I am using running the code in your repository?"
**Say:** Answer "yes" only if you restarted after the last demo commit today, and give the commit hash. The panel found a server that started before uncommitted demo edits.
**Back it with:** `git status`; `git log -1`.

**Q:** "Can I break your demo from the keyboard?"
**Say:** Malformed input gets a polite message, and text is never inserted as HTML. The one weak spot the panel found, an answer with about 300 numbers that tied up the CPU for 43 seconds, is now closed: answers with more than 25 figures are refused (demo/app.py, commit 8fb9764). Check that the running server was started after that commit.
**Back it with:** panel probes (lens 5); demo/app.py (`MAX_FIGURES = 25`, lines 41 and 68-69); commit 8fb9764.

### Novelty

**Q:** "LettuceDetect v2 already types hallucinated spans, and FRED fine-tunes small models with a financial error taxonomy. What is new about your relation-slot head?"
**Say:** The overlap is real, and we logged it as risk R-11 on 8 October. We do not claim typed detection as new. On the locked test the slot head named the right slot for only 3.4% [0.0%, 8.7%] of overlapping spans, and Channel A with it was no better than without it (AUROC difference −0.035 [−0.081, 0.008]). The comparison with LettuceDetect v2's taxonomy head that R-11 called for was not run. So on natural answers the slot head is not a result, and the paper will say that beside contribution 2.
**Back it with:** docs/risk-register.md R-11; docs/FaithGuard-Revised-Plan.md ("Claims to avoid"); runs/main/report.md ("Spans": slot accuracy; "channel-a minus channel-a-noslot"); docs/papers/detection.md §1 (contribution 2), §2, §6.2.

**Q:** "Your policy paper cites CORA and Release Control as accept-repair-abstain policies. The only CORA I can find is a mobile GUI agent guard, and I cannot find 'Release Control' at all. What is novel?"
**Say:** We are checking both citations today, and we will drop any we cannot open. The panel also pointed to CGRiC (ICML 2026), which we must read. Our claim narrows to a paired replay that counts the errors repair introduces, and the label-budget curve. The repairer-swap study is only a controlled rehearsal: on natural answers P-H3 was untestable because the v0 policy did not certify. On our benchmark the certificate certified nothing.
**Back it with:** docs/papers/policy.md §2 ("[CITE: CORA — open and verify]"); docs/related-work/policy.md (rows empty); docs/FaithGuard-Revised-Plan.md ("Claims to avoid"); runs/main/report.md (P-H3); runs/policy/transfer/report.md.

**Q:** "Your systematic review excluded every preprint and took the 25 most-cited records per query. Did anyone actually open VeriFin?"
**Say:** Sorting by citation count and keeping the top 25 per query works against recent papers. Our exclusion rule E1 dropped preprints with no archival version, which on its own would drop an arXiv-only paper like VeriFin. Both are weaknesses of the review's design. Answer about who opened what truthfully, after today's reading, and claim only papers someone has actually opened.
**Back it with:** docs/literature-review/FaithGuard_LitReview_M1/M2/M3 .xlsx ("00 How to use": E1; "01 Search log": sorted by cited_by_count, 25 per page); docs/FaithGuard-Revised-Plan.md ("Only references you have opened").

**Q:** "In one sentence per paper: what is actually new, and what is incremental?"
**Say:**
- **Detection:** a detector trained from US XBRL that runs on Sri Lankan PDFs. Fused with the rules it ranks answers slightly better (+0.047 AUROC), but it finds spans no better (D-H2), and its XBRL test was untestable.
- **Repair:** on the same model and data, typed edit programs made 10.6 points fewer new errors and corrected 28.9 points more than free rewriting (R-H1, confirmed).
- **Policy:** a certificate that counts repair-introduced errors. It certified nothing on 396 natural calibration answers, and that is the budget finding.
- **Benchmark:** the only Sri Lankan annual-report faithfulness set we found, with executable gold and AI-made labels.

**Back it with:** runs/main/report.md; docs/FaithGuard-Revised-Plan.md ("Defensible claim" sections).

---

## 4. Limitations slide

- Every label, check and adjudication is a separate Claude pass; no person labelled the test set (D-103).
- Answers come from two open 9-12B models at 4 bits; larger or proprietary models may err differently (preregistration §1; docs/papers/benchmark.md, Limitations, "Two generators").
- Natural errors are mostly wrong values (130 of 216 labelled spans; 146 of the 177 incorrect answers are to computed questions such as growth and shares). Only 9 spans in 788 answers are wrong-context, on 4 test answers, so D-H1 could not be tested (runs/main/labels/report.md; D-107 (3); runs/main/results.json).
- The checker and gate check each number only against the cell the checker thinks it is about; when the checker cannot name the line item, any table figure passes. They do not check that the numbers in a sentence agree, the words around them, or which company is named. The gate's relevance check only asks that some supported number is about the question's line item (src/faithguard/repair/gate.py; src/faithguard/detect/rules.py; R-24; demo/README.md, Known limitations).
- On natural numeric answers the rule checker misses 26 of 170 wrong answers and flags 110 of 502 right ones (runs/main/labels/report.md).
- No policy certified a 10% error budget on 396 calibration answers; outcome models trained on template tables were miscalibrated on real reports (runs/main/report.md).
- Sri Lanka: 24 companies, two statements each, a hand-picked list; closest prior work (VeriFin, FinGround, FRED) not yet compared (D-038; docs/related-work/).

---

## 5. Do today

1. **Make one results slide from runs/main/report.md** (30 min; the policy lead drafts and the others check it). Show the nine verdicts in the report's own words with their intervals, and say the papers' result sections were filled from this run (D-113, commit 31e14c3); the analyses that were not run on the main answers (for example the flip matrix and regret, which need a certified policy) are marked 'not run'.

2. **Log the human spot-check before drawing anything** (15 min). Add a new decision entry (the next free number) that states:
   - 60 answers from the 392 test answers, 15 per country × generator, with 10 labelled correct by Claude and 5 labelled anything else in each cell;
   - the seed (pick an integer and write it down now; do not redraw if you dislike the sample);
   - that the check changes no label;
   - the consequence: if the one-sided 95% upper bound on status disagreement, on the raw count of 60, is above 10% (2 or more disagreements), every verdict is reported as provisional until people relabel the test set; the rate reweighted to the test mix is reported beside it.

3. **Human spot-check of the Claude labels** (about 2 hours per member; half a day in total).
   - One member draws the sample with the script below. It prints only counts, so nobody sees Claude's labels until all the human labels are in. Keep every file under `data/`, which git ignores; test answers must never reach the public repository.
     ```python
     import json, random
     SEED = 0  # replace with the seed in the decision entry
     items = [json.loads(l) for l in open("data/benchmark-build/main/items-locked.jsonl", encoding="utf-8")]
     deciding = {}
     for l in map(json.loads, open("data/benchmark-build/main/gold/labels.jsonl", encoding="utf-8")):
         if l["target"] != "original" or l["annotator"] == "claude-labeller-2@d103":
             continue
         if l["annotator"].startswith("claude-adjudicator") or l["item_id"] not in deciding:
             deciding[l["item_id"]] = l
     rng, sample = random.Random(SEED), []
     for country in ("LK", "US"):
         for gen in ("gemma", "qwen"):
             cell = sorted((r for r in items if r["question"]["split"] == "test"
                            and r["question"]["country"] == country and r["id"].endswith(":" + gen)),
                           key=lambda r: r["id"])
             ok = [r for r in cell if deciding[r["id"]]["status"] == "correct"]
             rest = [r for r in cell if deciding[r["id"]]["status"] != "correct"]
             sample += rng.sample(ok, 10) + rng.sample(rest, 5)
     rng.shuffle(sample)
     import os; os.makedirs("data/human-check", exist_ok=True)
     with open("data/human-check/items.jsonl", "x", encoding="utf-8") as f:
         for r in sample:
             f.write(json.dumps(r, ensure_ascii=False) + "\n")
     print(len(sample), "items written")
     ```
   - Build blinded tasks with random keys and order: `faithguard labelling tasks --items data/human-check/items.jsonl --out labelling/human-check-tasks.json --mapping data/human-check/mapping.json`. Load them into Label Studio with labelling/label_config.xml.
   - Each member labels 20 tasks under guide v2 (docs/annotation-guide.md), without seeing Claude's label or any system output. Five per cell (20 in all) also get a second member, which gives a kappa between people. That is 80 labellings at D-100's planning figure of 4 minutes each, about 5.3 hours across the team. Log every sitting in logs/labelling-hours.csv, which also gives the first real measure for R-01.
   - Compare each person's status, "has a wrong span" and slots with Claude's deciding label (the adjudicator's where it exists, otherwise claude-labeller@d103). Do not import the human labels into the main gold store.
   - Report it like this: "60 test answers, drawn [date], seed [S]. People agreed with Claude's status on A of 60; the disagreement rate is at most B% (one-sided 95% Clopper–Pearson). The kappa between people on 20 was K." Give the result per cell and reweighted to the test mix in both strata, country × generator and Claude's label (test: LK gemma 94 correct / 29 other, LK qwen 92/31, US gemma 53/20, US qwen 57/16), and list every disagreement by item ID. The rule fixed in the decision entry applies to the raw count of 60 (2 or more disagreements gives a bound above 10%, so every verdict is provisional). Report the weighted rate beside it. Bounds for 60: 0 disagree, 4.9%; 1, 7.7%; 2, 10.1%; 3, 12.4%; 4, 14.6%; 5, 16.7%. If time is short, use 40 answers (10 per cell): 0 disagree gives 7.2%, 1 gives 11.3%.
   - Optional, about 1.5 hours for one member: label 20 of the R-H1 arms' checked repairs (10 per arm, from `sample` in data/benchmark-build/main/gold/repair-check.json, same seed), because the one confirmed hypothesis is decided there.

4. **Check gold answers and tables against page images** (1.5 hours, one member). With the same seed, draw 20 of the 394 locked questions (12 Sri Lankan and 8 US, at most one per company). For each Sri Lankan question, open the statement page given in the evidence's `page` field and re-derive the gold answer from the page image, not the text layer. For each US question (`page` is empty), open the filing at the table's `source` URL (the SEC 10-K) and re-derive the answer from the statement there. Check the row, the year column, the Group/Company/Bank column and the unit. Also compare 10 random cells of People's Leasing's two statements with the page image (D-060). If 0 of 20 are wrong, the gold error rate is at most 13.9%.

5. **Ask ChatGPT 10 Sunshine questions and check them** (about 1 hour, one member). Upload data/raw/reports/LK/SUN/2026-03-31.pdf and ask these 10 questions:
   - What was the Group's revenue for the year ended 31 March 2026?
   - What was the Group's profit for the year in 2026?
   - What was the profit attributable to owners of the company (Group) in 2026?
   - What was the Company's standalone profit for the year in 2026?
   - By what percentage did the Group's profit for the year change in 2026?
   - By what percentage did the Group's revenue change in 2026?
   - How did the Group's cost of sales change in 2026?
   - What were the Group's total assets at 31 March 2026?
   - What was the non-controlling interest in the Group's statement of financial position at 31 March 2026?
   - What was the Group's basic earnings per share in 2026?

   Copy each answer word for word, with the model name and date. A person checks each figure against the printed statements at its printed precision (guide v2). Report the count, whatever it is. Do not paste these answers into the demo on stage unless you have rehearsed them, because multi-clause answers hit the checker's one-period-per-clause limit (demo/README.md).

6. **Open the closest prior work and fix the citations** (about 2 hours, split three ways). Open VeriFin (check every fact this document quotes), FRED, FinGround, CORA and Release Control (drop it if it cannot be found), and CGRiC. Fill in "What it actually does" and "Opened by" in docs/related-work/*.md.

7. **Remove the stale "human-labelled" claims** (15 min). The demo's Results banner and Control note (commit 8fb9764), docs/architecture.md and risk R-17 are already corrected; check the rest. Do not hand out the 10 October PDFs (Project Briefing, Questions and Answers, briefing/Decision Policy), or attach a one-page erratum that quotes D-103. In the risk register, set R-04 to triggered and correct the status of R-17, R-23 and R-25.

8. **Log the deviations nobody has logged yet** (20 min). Record that the person's review of the 61 pilot code labels promised in D-100 did not happen, that guide v2's freeze condition was never met, and that minutes per item were never measured (R-01). Agree one sentence on why no member labelled, and one line per member on who did what (docs/authorship.md), in 10 minutes.

9. **Restart and pre-check the demo** (20 min). Restart the server, run `precompute.py --check-only` and confirm it ends with "0 not as expected". Then ask each scripted question again and write down the AI's exact words today.

10. **Rehearse the demo script** (45 min, all three). Each member runs their three-minute script once. Add one drill where someone plays a panel member typing a bad question, and the presenter answers with the known-limit line.

11. **Record the backup video** (30-45 min). Record one take per member at the projector's resolution, with Xbox Game Bar (Win+Alt+R) or OBS, as demo/README.md describes.

---

## 6. On stage

Each member takes the questions on their own paper: detection M.L Ahamed, repair M.S.A Ahamed, policy Sharaf (docs/authorship.md).

**What to show**
- **Simple page, Tokyo Cement:** ask "By what percentage did the Group's profit for the year grow in 2026?" and press **Ask the AI**. The AI says profit "grew by 49.9%" (check today's wording). FaithGuard shows a fall of 25.4% (Rs. 3,459 million to Rs. 2,580 million) and sends "declined by 25.4%". Then use **Try to trick it → another part of the company** (demo/SIMPLE.md).
- **Full demo, fictional bank (examples 1-6)**, following each member's script in demo/README.md:
  - Catch: entity error and scale error. When you show the entity error, say it is rare in natural answers (5 of 216 labelled spans). When you show the Channel A card, add: 'On the locked test Channel A alone ranks answers barely above chance (AUROC 0.579), and the policy does not use it; fused with the rules it ranks slightly better than the rules alone (0.849 against 0.803).'
  - Control: P(unsafe) and P(fix). Say aloud: "This certificate is from the controlled track; on the benchmark nothing certified." README step 3 now says both halves: on injected errors 400 calibration answers always certify a setting; on the 396 natural calibration answers nothing certified. The neural model ran and certified 0 of 56, as the README now says.
  - Correct: the rule repairer on the left and trained v1 on the right. Say: "The demo releases the rule repairer's fix; the system we tested uses v1, which put a new wrong number into 0.4% of the answers it sent on the locked test, against the rule repairer's 6.2%."
- **Results:** use your results slide. The demo's Results banner now gives the natural checker numbers and points to runs/main/report.md; say them aloud anyway (on the 672 labelled numeric answers: 144 of 170 wrong ones caught, 84.7%; 110 of 502 right ones flagged, 21.9%).

**What not to type, and why**

| Do not type | Why |
| --- | --- |
| Costs or expenses printed in brackets (cost of sales, tax expense, finance expenses) and changes in them | They are stored as negative numbers, so a rising cost is "repaired" to "decreased" (demo/README.md, Known limitations) |
| "By how much…" questions | They are withheld on every real report even when right (P(unsafe) 0.66; the panel counted 85 of 93 supported answers withheld). Ask "By what percentage…" or "How did … change…" instead (demo/README.md) |
| Sampath Bank growth questions | They are withheld even when the AI is right (demo/README.md, stress tests) |
| Questions naming no line item in the two statements (ROE, dividends paid, cash flow, capex, capital adequacy) or a name the report does not print ("revenue" on Tokyo Cement or Kinsale) | Any figure from the tables passes the frozen checker and the answer can still be sent. The current page warns that it could not tell which line the question is about, but do not rely on the warning (demo/README.md, Known limitations; demo/static/simple.js; panel sweep). |
| Counts and non-report numbers ("1,850 people", "3 factories", "note 12", "the 3rd record year") | They are read as the asked line item and overwritten with a rupee figure, e.g. "employed 2,062,940,762 people" (panel repro; demo/SIMPLE.md, Honest limits; demo/README.md lists it as an on-screen warning) |
| Other companies ("Apple's net income") | The demo now refuses a question that names another company ('Apple's ...'), but that guard is in the demo only. The frozen pipeline checks only against the chosen report and never checks which company is named, so other wordings can still get through (demo/ask.py other_company; demo/README.md, stress tests). |
| Also avoid: profit attributable to owners, non-controlling interest, the "Voting" buttons, "from X to Y" without years, losses written in words, "as originally reported", answers like "It was 100%", and long answers with many numbers | These are frozen-checker limits (questions 10 and 11 above; demo/README.md) |

**If the demo misbehaves**
- Do not debug on stage. Say: "That's a known limit of the frozen checker: [name the class, e.g. bracketed costs]. The checker is frozen as filed (D-104), and our locked-test results are for this frozen version (D-113), so we do not patch it for the demo. It goes into the error analysis and the next version, and it is on our limitations slide." Write it down and move on.
- If the page says "Every number checks out" or "fixed" over a wrong answer, correct it aloud: "The page overclaims here. It means every number matches some cell in the report, not that the answer is right."
- If a panel member finds something new, thank them, name the nearest known class, and say it will go into the error analysis.
- If the GPU or AI fails: for the scripted questions **Ask the AI** shows the answer recorded at rehearsal, and the screen says so (say aloud that it is a recording). For other questions use **Take the right answer from the table** or type an answer. **Try to trick it** still runs on the CPU. Otherwise restart with `--no-models` (the full demo works from stored outputs) or play that member's backup clip.
- Before the talk, confirm the server was restarted after the last demo commit, and note which port you started it on (the README uses 8765).

---

## 7. Numbers to know

| What | Number | Source |
| --- | --- | --- |
| Locked test set | 394 questions, 788 answers (6 of 400 excluded) | D-104 |
| Split | 392 test and 396 calibration answers; 48 companies, 12 test + 12 calibration per country | items-locked.jsonl; preregistration §1 |
| Sri Lanka | 248 questions, 496 answers, 107 labelled incorrect | runs/main/labels/report.md |
| Generators | Qwen3.5-9B Q4_K_M and Gemma 4 12B QAT Q4_0, thinking off; demo AI Qwen3.5-2B | preregistration §1; demo/README.md |
| Error rate | 177 of 788 (22.5%); numeric 170 of 672 (25.3%) | runs/main/labels/report.md |
| Labelled spans | value 130, unsupported text 30, scale/currency 28, sign 17, entity 5, period 3, basis 2, metric 1 | runs/main/labels/report.md |
| Wrong-context | 9 spans in 788 answers; 4 test answers; D-H1 needs 20 | D-107 (3); runs/main/labels/report.md; runs/main/results.json; D-102 (1) |
| Pilot | 23 of 120 incorrect (19.2%); no wrong-context spans | runs/pilot/report.md |
| Who labelled | claude-labeller@d103 773, claude-adjudicator@d103 15 | runs/main/labels/report.md |
| Label agreement | status agreement 95%, kappa 0.89, on 80 double-labelled tasks, between two Claude passes | D-105 |
| Audit | 4 of 150 overruled (bound 6.0%) against a rule of at most 1 (3.1%), so the code labels fell | D-105 |
| Repair check | 3 of 43 (7.0%), 3 of 50 (6.0%), 8 of 50 (16.0%), so 459 more labelled | D-112; runs/main/report.md |
| Rule checker on natural numeric answers | caught 144 of 170 wrong (84.7%); flagged 110 of 502 right (21.9%) | runs/main/labels/report.md |
| Controlled track (rehearsal) | Channel B 0.9% false alarms, 99.7% wrong-context recall; Channel A alone 51.8% false alarms (2,000 controlled tune-track items) | runs/detector/kaggle/eval-channel-a/results.json |
| Test AUROC | fused A+B 0.849, rule checker 0.803, LettuceDetect v2 0.688, Channel A 0.579 | runs/main/report.md |
| D-H2 (Sri Lankan span F1, A+B − B) | +0.024 [−0.059, 0.146], no difference | runs/main/report.md |
| R-H1 (test, labelled spans) | new errors 0.3% against 10.9% (−10.6 [−13.7, −7.7]); corrected 49.4% against 20.5% (+28.9 [16.5, 43.7]); confirmed | runs/main/report.md |
| v1 against rules (test, rule spans) | corrected 50.6% (v1, by labels; 49.4% by the gold scorer) against 50.6% (rules, gold scorer only); new errors 0.4% against 6.2%; damage 0.0% against 6.3% (rules scored by code only; secondary comparison, no interval) | runs/main/report.md; D-112 |
| R-H2 / R-H3 | Gemma +18.2 [4.7, 31.0] but basis arm has 2 answers, so not confirmed / +0.4 [−0.9, 1.8], no difference | runs/main/results.json |
| Information preserved | v1 97.7%, rewriting 90.0% | runs/main/report.md |
| Policy, benchmark | 0 settings certified in any family at α = 0.10, δ = 0.05 | runs/main/report.md |
| Certificate minimum | at least 132 of 396 sent with 0 errors (67 of 100; 100 of 198); our certificate's 32 holds only if all are sent (29 is an exact test on sent answers alone, which we do not use) | src/faithguard/stats/certify.py; docs/papers/policy.md §4.4 |
| First LightGBM setting | send<0.02, fix>0.99: p = 0.99 on calibration, so the sequence stopped; sent 25 of 392 test answers (6.4%) | runs/main/results.json |
| Uncertified test risk | threshold 5.9% of sent; repair-all 5.7%; send-all 22.4% | runs/main/results.json |
| Outcome models on test | LightGBM P(unsafe) AUROC 0.807, ECE 0.329; P(fix) AUROC 0.624 | runs/main/report.md |
| Controlled policy (rehearsal) | LightGBM 73.8% sent, 1.6% wrong; repair-all and threshold v0 74.0%, 1.6%; verified-only 21.5% sent; oracle useful 72.9% | runs/policy/controlled/report.md |
| Repair, tune track (development) | v1 65.7% corrected, 0.5% new errors; rewrite 53.0%, 17.0%; rules 59.6%, 0.9%; damage 0% | D-110; runs/repair/rules/report.md |
| Demo | 260 one-click questions, 1,145 planted errors caught by construction; 68 AI questions, 3 sent wrong | demo/README.md |
| Timeline | prereg-v1 at 08:19 on 29 Oct; D-112 at 19:29; phase 7 analysis b6d441a at 19:54; papers filled 31e14c3 at 20:03; demo hardened 8fb9764 at 20:07. analysis.py +447/−72 since the tag. Unchanged: the rule checker, gate, policy features, deployed policy and gold scorer. Other logged changes: the rewrite baseline declines narrative answers (D-111), Granite prompt loading (D-108), labelling units note (D-105), repair-check code (D-106), policy study and transfer analyses (D-109) | git log; git diff --numstat prereg-v1 HEAD -- src/faithguard; docs/decision-log.md D-105, D-106, D-108, D-109, D-111 |
