# FaithGuard demo

A local, offline demo for the progress presentation. It opens in the browser and walks one answer through the pipeline: **1 Catch → 2 Control → 3 Correct → Output**, with a **Results** screen for the locked-test results (D-113) and the development tables. Each member drives their own step. Decision D-097.

```
.venv\Scripts\python demo\app.py
```

That one command opens `http://127.0.0.1:8765/`. On the first screen the status bar shows what is live:

| Pill | Live means | Otherwise |
| --- | --- | --- |
| Channel B | the rule checker (always live) | – |
| Channel A | the fine-tuned detector runs on every answer and every edit (CPU when the repairer is loaded, else GPU) | the token probabilities stored by `precompute.py` (original answers only) |
| Policy | the certified LightGBM outcome models | threshold v0, if `runs/policy/controlled/policy.pkl` is missing |
| Trained repairer | the repair-v1 adapter writes programs on the GPU when you press *Run the trained repairer live* (2-6 s) | stored outputs: this laptop's run for the fictional items, the Kaggle pilot run for the real answers |

The trained models load in the background (about a minute: Channel A first, then the repairer with one warm-up generation). The page works at once and switches to them when they are ready. Both pages ask the server for its status every 10 seconds, so a model that stops answering shows on its pill.

Flags: `--no-models` (live pipeline only, stored model outputs), `--no-repairer` (Channel A only, on the GPU), `--port 8766`, `--no-browser`. If the port is taken, an old demo is still running: close its window first.

## Setting up a laptop

1. **The base environment**: `python -m pip install -r requirements/laptop.lock.txt` (see the main README). If `runs/policy/controlled/policy.pkl` is missing, rebuild it with `faithguard policy` (about a minute; it is gitignored because pickles are never shared).
2. **The trained models** (optional, needs an NVIDIA GPU and the internet once):
   ```
   .venv\Scripts\python -m pip install -r requirements/demo.txt --extra-index-url https://download.pytorch.org/whl/cu128
   .venv\Scripts\python demo\fetch_models.py
   ```
   `fetch_models.py` takes Channel A from the private Kaggle dataset `faithguard-detector-models` and the repair-v1 adapter from the `repair_v1` notebook's output (both into `data/demo-models/`, with the Kaggle CLI token in `~/.kaggle`), and the Qwen3.5-2B base (4.3 GB) into the Hugging Face cache. `requirements/demo.txt` is a layer on top of the lock file: do not freeze it into `laptop.lock.txt`.
3. **The real answers** (optional): the pilot examples are listed in `data/demo/examples.json`, which is not in git (the pilot is development data and the repository is public). Its keys: `items` (the pilot items file), `gold` (the pilot gold store, read only by `precompute.py`), `kaggle_outputs` (the systems-pilot folder with `detector.jsonl` and `repair-rule-spans.jsonl`), `kaggle_label`, and `pilot`: a list of `{id, expect, title, caption, edits}`. Paths under `data/benchmark-build/main*` or `labelling/` are refused. Without the file the demo shows the six fictional items only.
4. **Pre-check and stored outputs**:
   ```
   .venv\Scripts\python demo\precompute.py
   ```
   It runs every example and every one-click edit through the live pipeline, checks each takes its intended action and that every sent or repaired answer is right by the development gold, stores Channel A's token probabilities and the trained repairer's outputs in `data/demo/cache.json`, and writes `data/demo/precheck.md`. It must end with **0 not as expected**. `--check-only` skips the models (seconds, CPU).

## Before the talk

- Run `precompute.py --check-only` and read the last line.
- Start the demo a few minutes early and wait for the green Channel A and Trained repairer pills. Close other programs using the GPU.
- Check the **code** pill (full demo) or the line next to "AI ready" (simple page): it shows the last commit, "+ local changes" when `demo/` or `src/` differ from it, and "edited since the server started: restart it" when the server runs older code than the files (checked on every status poll). If it says "+ local changes", commit or revert them first, then restart the server.
- After any restart of the server, reload both pages. They say so themselves: "The demo was restarted: reload the page." Own questions from before the restart are gone from the server.
- Use the projector at 1366×768 or more, browser zoom 100-125%. ← and → (or PageUp/PageDown) move between steps when the cursor is not in the answer box.
- If anything goes wrong with the models, restart with `--no-models`: every screen still works from stored outputs, and **Ask the AI** (on both pages) answers the four suggested questions per report with the AI's answers recorded at rehearsal (`demo/rehearsal.json`, labelled as recorded on screen). Other questions, the line-item buttons included, get "The AI is not loaded": use the template answer or type one.
- **Pasting an answer from another AI** (ChatGPT and the like): rehearse it before a panel member pastes. FaithGuard reads one year per clause and every number as a report figure. These forms were run through the pipeline on this build and sent with no warning (Kinsale's net income, Tokyo Cement's Group profit):
  - each figure with its own year: "Kinsale's net income was $503.6 million in 2025, compared with $414.8 million in 2024."
  - the current year in the clause, the comparative in brackets: "Kinsale's net income was $503.6 million in 2025 (2024: $414.8 million)."
  - a change with both years: "Kinsale's net income grew by 21.4% in 2025, from $414.8 million in 2024 to $503.6 million in 2025."
  - one figure and its year: "The Group's profit for the year was Rs. 2.58 billion in 2026."

  Forms that go wrong (see the limitations below): a figure with no year beside one that has a year ("Net income: $503.6 million (2024: $414.8 million)" is "fixed" to the 2024 figure, with a warning), "up from" beside a looked-up figure (withheld), page or note numbers ("page 152"), sums and averages, and open questions ("How did Sunshine perform?"). Ask the other AI to give each figure its own year and no references. Check these again after any change to the demo.

## Click-by-click scripts

Each script takes about three minutes. Examples are numbered as in the sidebar; 1-6 are the fictional bank, 7-11 the real pilot answers (talking points for 7-11 are in `data/demo/script.md`, kept out of git). Before the first real answer, say: "These are development answers, picked by hand to show each action, and the checker's rules were tuned on the pilot (D-057). They are in-sample for the checker: they show how it works, not how well." The sidebar says the same.

### Catch: detection (M.L Ahamed)

1. **2. Entity error**, step **1 Catch**. "The question asks for the Group; the answer's numbers are the Bank's." Click **Rs. 12,450 million**: verdict *unsupported*, failing slot `entity_scope`. In the evidence table the asked-for Group cell is green (✓) and the Bank cell the number came from is red (✗). Below: what the evidence supports, Rs. 14,213 million. Say the other half: "It catches the Bank's figure written as the Group's. An answer that openly gives the Bank's or 2024's figure is sent, because the checker matches each number to its own label, not to the question." The screen adds a note when it can tell.
2. Click **7.0%**: the checker matches it to the Bank's growth and recomputes the Group's, a rise of 9.3%.
3. Channel A card: the per-token heat map from the fine-tuned mmBERT, and the slot head's guess under *Flagged spans* (hover a word for its probability). "Channel A is trained to find wrong spans; Channel B traces them to cells." Its slot guess here is wrong (scale_currency and basis for an entity error): say so before anyone asks. On the locked test the slot head is right on 3.4% of spans (`runs/main/report.md`, "Spans on the test split"), and the policy does not use Channel A.
4. **3. Scale error**: the cell is outlined green with a red dashed border, "the right cell, read at the wrong scale".
5. **Try it**: open **1. Correct answer**, click the edit **Swap in the Bank's figure**. The amount turns red at once in Channel B. Say: "Channel A gave this amount 1.00 on the correct answer too: on these answers it cannot tell right from wrong, which is why the decision uses Channel B."
6. Real answer **8**: Channel A flags only the wrong growth rate.
- If asked about false alarms: on the correct answer (1) Channel A flags both numbers. On clean answers it alone raises false alarms half the time, which is why the decision uses Channel B's checks (Results → Catch: Channel B 0.9% false alarms; A+B fusion 1.0%). On the locked test Channel A ranks answers barely above chance (AUROC 0.579).
- If someone types in the box: the checker reads one year per clause. A base amount with no year ("rose 9.3% from Rs. 13,004 million to Rs. 14,213 million") is read as FY2025 and "repaired" to the same figure, and the screen warns (the sentence contradicts itself; one year per clause). Name both years ("from Rs. 13,004 million in FY2024 to Rs. 14,213 million in FY2025"); the hint under the box says so.

### Control: decision policy (Sharaf)

1. **2. Entity error**, step **2 Control**. The pre-action features on the right: only what is known before acting, no gold. Left: the LightGBM outcome models. P(unsafe) 1.000 is not below 0.5, so it is not sent as is; P(fix) 0.988 is above 0.6, so the action is **REPAIR**.
2. The certified setting: `send<0.5, fix>0.6`, α = 0.10, δ = 0.05. "With 95% confidence at most 10% of released answers contain a wrong number, for answers like the calibration set." Certified by Learn-then-Test on 5,423 calibration answers; held-out test: 73.8% released, 1.6% wrong among them.
3. The certification-budget curve: on the controlled track (injected errors), with 400 calibration answers or more a setting is always certified (LightGBM solid, the neural model dashed). Say the other half too, which the note under the chart gives: on the 396 natural calibration answers of the locked benchmark no setting certified (runs/main/report.md, D-113).
4. **6. Missing operand**: P(fix) 0.000, so the action is **ABSTAIN**. Say: "The policy withholds the original 15.2%. But a figure that equals a ratio of two cells is traced to those cells and sent: the trained repairer's 3.8% (net interest income over total assets), typed in, is sent. When the evidence does not name the line, the checker cannot tell what a ratio is about." **1. Correct answer**: P(unsafe) 0.031, so it is **SEND**.
5. **Try it** on **1. Correct answer**: click **Flip the direction**. The step bar's action changes from SEND to REPAIR live.
6. Under the bars: threshold policy v0, the rule-only baseline, and whether it agrees.
- If asked: on the 120 pilot answers LightGBM agrees with v0 on 111; on the other 9 it is more cautious (it withholds answers the labels call correct). The neural outcome model (D-096) was trained and run on the locked benchmark: like every family there, it certified 0 of 56 settings (runs/main/report.md).

### Correct: repair (M.S.A Ahamed)

1. **2. Entity error**, step **3 Correct**. Left, the rule repairer: `CALCULATE k1 = growth(t1r3c1, t1r3c2)` and `COPY k2 ← t1r3c1`. The five gate checks, all ✓. BEFORE/AFTER, with the cells behind each new number.
2. Right, the trained repairer v1, frozen in D-101 (Qwen3.5-2B + LoRA): the same program. Click **Run the trained repairer live on this answer** (3-6 s on the GPU).
3. **5. Sign error**: one CALCULATE, and the executor turns *fell* into *rose* from the sign of the calculation.
4. Real answer **9**: the rule repairer fixes the slip from the Company columns; the trained program uses a Group cell and the gate rejects it (provenance ✗, recheck ✗), so nothing wrong is sent.
5. **6. Missing operand**: the rule repairer's **CANNOT_FIX**, with its reason and what the report does hold. Then the trained column, and say: "The trained repairer computes 'return on equity' as net interest income over total assets, 3.8%, and all five gate checks pass, because return on equity is not in the evidence for provenance to check. The policy withholds the original 15.2%; the trained repairer's 3.8%, typed in, would be sent. It is a known gap in the gate." The warning box in the column says the same.
- Say plainly: "The demo releases the rule repairer's fix (it runs on the CPU); the system we tested uses v1, which put a new wrong number into 0.4% of the answers it sent on the locked test, against the rule repairer's 6.2%." On the locked test (83 wrong answers) both correct 50.6% with the rule checker's flags; the rule repairer also damaged 6.3% of the right answers, v1 none (runs/main/report.md). On the controlled track v1 corrects 65.7% against the rules' 59.6%; on the 23 wrong pilot answers the rules corrected more with the rule checker's flags (43.5% against 39.1%) and fewer with Channel A's (21.7% against 39.1%). The pilot is development data the rules were tuned on (Results → Correct).

### Ask your own question (any member, or a panel member at the keyboard)

The sidebar's first entry. Pick a report (the fictional bank, or one of the five real annual reports the pilot used: Sunshine Holdings, Kinsale, Central Finance, Sampath Bank, Tokyo Cement), type a question or click a suggestion or a line item, then:

- **Ask the AI ▶** (or Enter in the question): Qwen3.5-2B answers live on the GPU (4-13 s). It is the trained repairer's base model with the repair adapter switched off, so it has no FaithGuard training; it sees the tables rendered as the benchmark's generators saw them, and is asked for one sentence that names each figure's year (the generators' three-sentence prompt makes the 2B model show its working, which the rule checker reads badly). Its answer is cut at 120 tokens; when it runs past that, only its complete sentences are checked and the screen says so beside the answer. The answer goes straight into Catch. With the AI off, the button answers the four suggestions per report with their rehearsal recordings, labelled as recorded.
- **Write a template answer from the table**: a template sentence written from the cells of the line item the checker reads in the question (lookups, growth rates and changes), for when the GPU is not available. It refuses rather than guess: a line the tables do not have or a misspelt one ("Did you mean …?"), two rows of the same name, a line printed in brackets, two line items in one question, margins, ratios and returns, no earlier year for a change, a year the report lacks. It is still a template, not a checked answer: read its sentence before checking it, and FaithGuard checks it like any other answer.
- Or type any answer, right or wrong, and press **Check it with FaithGuard ▶**.

The *Try* suggestions and the line-item buttons are checked when the demo starts (in the background): each is kept only if the template answers it and the live pipeline sends that answer, so what is clicked on stage has been run. Rows printed in brackets (expenses), attribution rows and rows that share a name are left out of them (see the limitations below). Both pages say this under the buttons: the one-click questions are pre-checked, typed questions and the AI's answers are not.

On the answer, **Plant an error** writes one error of each kind into the original answer, each with the action the live pipeline takes: the other entity's figures (Group ↔ Company or Bank), the other year's figure, a neighbouring line item, thousand read as million, the direction word flipped, or a slip of 3 in the last digit (the commonest real error). The wrong figures are written by the executor from the wrong cells, in the answer's own style. Everything else works as for the examples: edit the answer, step through, run the trained repairer live. Own questions stay in the sidebar for the session.

Suggested script (2 minutes): Tokyo Cement → *By what percentage did the Group's profit for the year grow in 2026?* → **Ask the AI**: it says profit "grew by 49.9%" (the answer recorded at the latest rehearsal, demo/rehearsal.json); Catch marks it unsupported (profit fell from Rs. 3,459 million to Rs. 2,580 million), Control chooses REPAIR, Correct writes `CALCULATE` and the answer goes out as "declined by 25.4%". Then **Write a template answer from the table** on the same question (sent unchanged) and **Plant an error: Wrong entity**: the Company's cells turn red and the repair gives the Group's figures back. The AI is greedy (no sampling), so the same question gets the same answer at every rehearsal. Other questions where the AI slips and FaithGuard fixes it: Sunshine, *By what percentage did the Group's profit for the year grow in 2026?* (AI: grew 46.7%; FaithGuard: declined by 2.5%); Central Finance, the same question for 2026 (AI: 57.4%; FaithGuard: 3.7%). These are the answers recorded at the latest rehearsal; check them again after any change to the demo.

Stress tests before the talk (to be re-measured on the final build):
- **The AI** (laptop GPU, 68 questions over the six reports, each judged against the tables by a separate reviewer): 61 handled well (28 right and sent, 24 wrong and repaired to the right figures, 9 wrong and withheld), no bad repairs, 3 sent with a wrong figure (two on a question that names no entity, so the Company's figure was a fair reading), 3 right answers withheld (Sampath). Sampath Bank's growth questions are withheld even when the AI is right (the policy is cautious on that report), so do not use them on stage.
- **The one-click questions** (all 252 suggestions and line-item buttons over the six reports, re-run on this build): every template answer sent; their 1,105 planted errors all caught and repaired back to the right figures, none missed. This is by construction: planted errors are offered where the checker can usually see them (a direction flip only on a change, "a rise of 9.3%" and not "rose to X"; a wrong entity only when the question or answer names one; a slip moved further if it happens to equal another ratio in the tables; a variant whose repair would not give the figures back is left out, and the screen says how many). On AI or typed answers some planted errors are missed: the button says "FaithGuard misses this one", and the verdict says so. Say it: the natural numbers are the ones below.
- **Natural answers** (the benchmark's 672 labelled numeric answers, labels by separate blind Claude passes, D-103): the rule checker flags 144 of the 170 labelled incorrect and 110 of the 502 labelled right (`runs/main/labels/report.md`). Both pages say beside the planted errors that they are planted where the checker can see them, and give these natural numbers; so does the Results banner.
- **On-screen warnings for released answers** (demo-side, they change no decision): a sentence whose rate does not fit its own figures ("decreased 12.4% from Rs. 1.14 to Rs. 1.78"), the same figure written for two things, a count ("1,850 people") or a page or note reference ("page 152", "Note 45") overwritten with a money figure, a repaired figure next to the wrong year, a question whose line item the checker could not name, an answer about another part of the company than the question asks, "attributable to" questions, restated columns, words that were not checked ("driven by ..."). A question that names another company is refused ("Apple's", "Commercial Bank's" on Sampath Bank, "the profit of Insee Cement" on Tokyo Cement): a capitalised name holding a word that is not in the chosen company's name, or any capitalised name before a verb a company does ("What revenue did John Keells report" on Sunshine). The guard is demo-side and reads capitals, so a name typed in lower case ("insee cement") gets through, and an answer to it is checked against the chosen report; the frozen pipeline never checks which company is named. A question about a year the report lacks is refused before an answer is written, by the template and by **Ask the AI**; an answer typed for it is checked as usual, with a note that the report has no figures for that year. On the 1,357 one-click and planted cases of this build (the 252 template answers and their 1,105 planted errors, which print full-precision figures from the table), no warning fired on a template answer, the newer ones included: another year or part of the company than the question asks, a figure with no year of its own ("One year per clause"), a sum or average ("Not checkable"), a fix that changes the part of the company or puts the Group's figure beside the Company's, and the executor's "a grow of" ("Wording"). The only notes were the restated-column note where a figure comes from a Restated* column, and 15 "Rounded:" notes on planted thousand-to-million errors, each true (the repair writes the report's 22,150 thousand as "Rs. 22.2 million"). Answers pasted from other AIs are not part of that check. On the panel's 102 ChatGPT-style answers, the "does not add up" check, which allows for the rounding of each printed figure, fired once, on a repair that put one figure on both sides of "from … to".

### Output and Results (closing, any member)

- Step **Output** shows what the user gets: the original, the repaired answer with the cells behind its numbers, or a refusal with the evidence. Real answers also show the development reference answer, which the pipeline never sees.
- Real answer **11** (Tokyo Cement): the refusal's evidence is the checker's coincidental match for "21.7%", the Company's interest-bearing borrowings, on a question about Group revenue. Say so: "The frozen system shows the cells the wrong number matched, and here that match is a coincidence." The screen labels it.
- **Results** (sidebar): opens on **Locked test · D-113**, `runs/main/report.md` as generated (the nine hypotheses first, then detectors, spans and repair on the test split), under a banner with the split sizes, who labelled (separate blind Claude passes, not people; D-103, D-105) and the headline: one of nine hypotheses confirmed (R-H1), no policy setting certified. Reading notes above the report explain what reads oddly in it: the code-label line (the code labels fell, D-105), channel-b and granite at 0.0% (tied scores at the filed threshold), R-H1's "correction 28.9%" (a difference), and the labels report's "Pilot answers" heading. The other tabs are the development tables from `runs/`, under a banner that says so and what the rule checker does on the 672 labelled numeric answers.

## Recording a backup video

Start the demo, then record each script in turn with the Xbox Game Bar (Win+Alt+R starts and stops; files go to `Videos\Captures`) or OBS. Record at the projector's resolution, and keep one take per member so a failed live run can be swapped for its clip.

## Known limitations shown by the demo

- The rule checker reads one period per clause: a figure with no year of its own takes the year of its clause. It goes wrong in both directions. A base amount with no year is read as the current year: "rose 9.3% from Rs. 13,004 million to Rs. 14,213 million" is checked as FY2025 and "repaired" to the same figure, and so is "up from $4.89 billion a year earlier". A current figure with no year beside a comparative that has one is read as the comparative's year: "Net income: $503.6 million (2024: $414.8 million)" and "Rs. 65.9 billion, compared with Rs. 59.3 billion in 2025" are overwritten with the earlier figure, and a right figure can be marked wrong. A table with one column per year goes wrong the same way. The screen warns when a repair changed such a figure ("FaithGuard reads one year per clause"). Giving each figure its own year in its own clause avoids it ("$503.6 million in 2025, compared with $414.8 million in 2024"; the rehearsed forms are under Before the talk), and so do the one-click edits, which `precompute.py` checks.
- Channel A alone raises many false alarms; the policy reads Channel B's features.
- The gate cannot check a metric the evidence does not name (example 6, trained column): with no line to compare, provenance passes any cells of the right entity and year. The column's warning box says so.
- The checker compares a figure with one line only, so a figure that adds up or averages several lines ("revenue and other income combined", "the total of fee income and net investment income") cannot be checked: a correct sum is marked wrong next to one of its parts, and the answer is withheld. The screen says "Not checkable".
- Open questions ("How did Sunshine Holdings perform in 2026?", "Summarise the year") are not what FaithGuard checks: it needs a named line and Group or Company. On an open question the frozen checker can attach a figure to the wrong line and mix the Group's and the Company's figures, and a correct answer can be "fixed" into a wrong one (Sunshine: total comprehensive income "fixed" to total equity). The screen warns when a fix puts the Group's figure beside the Company's; do not rely on it.
- The checker reads the answer's own words for the part of the company: a correct Group figure written as "the Company's" is "fixed" to the Company's figure, on a question about the Group, and the change can turn round (Tokyo Cement: "declined by 25.4%" became "grew by 5.5%"). The screen warns ("Careful, this fix is not trustworthy").
- The frozen executor swaps a direction word but not its noun: "a decline of about 21.8%" can come out as "a grow of about 21.8%". The figure is what was checked; the screen notes the wording ("Wording").
- Every number is read as a report figure: a count, a page number or a note reference ("1,850 people", "page 152", "Note 45") can be overwritten with a table figure. Strip references from pasted answers.
- Own questions: expenses printed in brackets are stored as negative figures, so an answer giving an expense as a positive amount is "repaired" to a negative one, and a change in an expense takes the stored sign (cost of sales "decreased" when it rose). A loss written in words is read the same way: "other comprehensive income was a loss of Rs. 16.7 million" is withheld, and "-Rs. 16.7 million" is sent. The suggestions and line-item buttons leave those rows out, and the screen shows a *Known limitation* note when a question or answer touches one.
- Own questions: a units note written into the answer ("Rs 000") is read as a number, and the repair can write a figure over it; the AI is asked to write the unit as a word, and the screen notes it when it appears.
- Own questions: the 2B AI's long answers with working ("from X to Y") run into the one-period-per-clause limit above, which is why it is asked for one sentence.
- Own questions: "by how much" questions (typed as *difference*) are withheld on every real report even when every number is supported: the certified policy's P(unsafe) is 0.66 for them on tables this large (the controlled track's tables are small). Ask "By what percentage…" or "How did … change…" instead; the screen explains a withheld answer whose numbers are all supported. Sampath Bank's growth answers rounded to whole percents are withheld the same way, and so is a correct lookup that adds "up from X in <year>": "Net income was $503.6 million in 2025, up from $414.8 million in 2024" is withheld (P(unsafe) 0.709), while the same figures with "compared with" are sent (0.089). The policy counts direction words, a feature learned on the controlled track.
- Own questions: "profit attributable to owners/equity holders" can match a subtotal row, and rows that share a name (current and non-current, an impairment line and the loan book) are accepted either way by the checker. The template refuses both rather than guess; a typed answer to them is checked as the frozen checker reads it. A row whose name another statement also uses can be read as the other: Sunshine's correct balance-sheet non-controlling interest (Rs. 7,450,423 thousand) is "repaired" to the comprehensive income attributable to it (Rs. 1,966,330 thousand), and the screen warns that the fix is not trustworthy.
- Own questions: a company name with "Bank" or "Company" in it reads as that column. The question is shortened to the name before it ("Sampath Bank's" → "Sampath's", shown on screen); an answer that says "Sampath Bank's" gets a note instead, as answers are never rewritten.
- Own questions: when the question names no line item the report has, any figure from the tables passes (the checker has nothing to compare it with). Do not use that as a stunt.
- Short year forms ("FY25", "the previous year") are read into the question's period, the field the benchmark's writers set by hand; four-digit years are left to the checker. "Last year" is read as the report's latest year in a lookup, with a note on screen ("Read “last year” as 2026, the report's latest year; give the year to be sure"), and as the change into the latest year in "compared with last year". The rule checker, policy and repairers are the frozen research system (D-104); none of the above is patched for the demo.

## Files

| File | What it does |
| --- | --- |
| `app.py` | the local web server (Python standard library) and its API |
| `cases.py` | the examples and how one is run: the live pipeline plus the trained models' outputs |
| `ask.py` | your own question: the reports, suggestions, the template answer and the planted errors |
| `views.py` | what each step shows, as JSON |
| `models.py` | loading Channel A and the trained repairer, and running them |
| `results.py` | the Results screen's tables from `runs/` |
| `precompute.py` | the pre-check and the stored model outputs |
| `fetch_models.py` | downloads the model files |
| `static/` | the page: `index.html`, `app.js`, `style.css` |

The demo never reads the gold store or anything blinded; `precompute.py` reads the pilot gold store offline for the pre-check (`tests/test_demo.py` checks both).
