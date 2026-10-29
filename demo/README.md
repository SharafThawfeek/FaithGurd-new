# FaithGuard demo

A local, offline demo for the progress presentation. It opens in the browser and walks one answer through the pipeline: **1 Catch → 2 Control → 3 Correct → Output**, with a **Results** screen for the development tables. Each member drives their own step. Decision D-097.

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

The trained models load in the background (about 25 s, including one warm-up generation). The page works at once and switches to them when they are ready.

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
- Start the demo a minute early and wait for the green Channel A and Trained repairer pills. Close other programs using the GPU.
- Use the projector at 1366×768 or more, browser zoom 100-125%. ← and → (or PageUp/PageDown) move between steps when the cursor is not in the answer box.
- If anything goes wrong with the models, restart with `--no-models`: every screen still works from stored outputs.

## Click-by-click scripts

Each script takes about three minutes. Examples are numbered as in the sidebar; 1-6 are the fictional bank, 7-11 the real pilot answers (talking points for 7-11 are in `data/demo/script.md`, kept out of git).

### Catch: detection (M.L Ahamed)

1. **2. Entity error**, step **1 Catch**. "The question asks for the Group; the answer's numbers are the Bank's." Click **Rs. 12,450 million**: verdict *unsupported*, failing slot `entity_scope`. In the evidence table the asked-for Group cell is green (✓) and the Bank cell the number came from is red (✗). Below: what the evidence supports, Rs. 14,213 million.
2. Click **7.0%**: the checker matches it to the Bank's growth and recomputes the Group's, a rise of 9.3%.
3. Channel A card: the per-token heat map from the fine-tuned mmBERT, and the slot head's guess under *Flagged spans* (hover a word for its probability). "Channel A is trained to find wrong spans; Channel B traces them to cells."
4. **3. Scale error**: the cell is outlined green with a red dashed border, "the right cell, read at the wrong scale".
5. **Try it**: open **1. Correct answer**, click the edit **Swap in the Bank's figure**. The amount turns red at once, and Channel A follows half a second later.
6. Real answer **8**: Channel A flags only the wrong growth rate.
- If asked about false alarms: on the correct answer (1) Channel A flags the amount too. On clean answers it alone raises false alarms half the time, which is why the decision uses Channel B's checks (Results → Catch: Channel B 0.9% false alarms; A+B fusion 1.0%).

### Control: decision policy (Sharaf)

1. **2. Entity error**, step **2 Control**. The pre-action features on the right: only what is known before acting, no gold. Left: the LightGBM outcome models. P(unsafe) 1.000 is not below 0.5, so it is not sent as is; P(fix) 0.988 is above 0.6, so the action is **REPAIR**.
2. The certified setting: `send<0.5, fix>0.6`, α = 0.10, δ = 0.05. "With 95% confidence at most 10% of released answers contain a wrong number, for answers like the calibration set." Certified by Learn-then-Test on 5,423 calibration answers; held-out test: 73.8% released, 1.6% wrong among them.
3. The certification-budget curve: with 400 calibration answers or more a setting is always certified.
4. **6. Missing operand**: P(fix) 0.000, so the action is **ABSTAIN**. **1. Correct answer**: P(unsafe) 0.031, so it is **SEND**.
5. **Try it** on **1. Correct answer**: click **Flip the direction**. The step bar's action changes from SEND to REPAIR live.
6. Under the bars: threshold policy v0, the rule-only baseline, and whether it agrees.
- If asked: on the 120 pilot answers LightGBM agrees with v0 on 111; on the other 9 it is more cautious (it withholds answers the labels call correct). The neural outcome model (D-096) is the trained challenger, still to be trained.

### Correct: repair (M.S.A Ahamed)

1. **2. Entity error**, step **3 Correct**. Left, the rule repairer: `CALCULATE k1 = growth(t1r3c1, t1r3c2)` and `COPY k2 ← t1r3c1`. The five gate checks, all ✓. BEFORE/AFTER, with the cells behind each new number.
2. Right, the trained repairer v1 candidate (Qwen3.5-2B + LoRA): the same program. Click **Run the trained repairer live on this answer** (3-6 s on the GPU).
3. **5. Sign error**: one CALCULATE, and the executor turns *fell* into *rose* from the sign of the calculation.
4. Real answer **9**: the rule repairer fixes the slip from the Company columns; the trained program uses a Group cell and the gate rejects it (provenance ✗, recheck ✗), so nothing wrong is sent.
5. **6. Missing operand**: the rule repairer's **CANNOT_FIX**, with its reason and what the report does hold.
- Say plainly: on the controlled track the trained v1 corrects 65.7% against the rules' 59.6%, but on the 23 wrong pilot answers the rules correct more (43.5% against 39.1%; Results → Correct).
- If asked about example 6's trained column: the trained repairer computes "return on equity" as net interest income over total assets, and the gate passes it, because return on equity is not in the evidence for provenance to check. The policy withholds that answer anyway; it is a known gap in the gate.

### Ask your own question (any member, or a panel member at the keyboard)

The sidebar's first entry. Pick a report (the fictional bank, or one of the five real annual reports the pilot used: Sunshine Holdings, Kinsale, Central Finance, Sampath Bank, Tokyo Cement), type a question or click a suggestion or a line item, then:

- **Ask the AI ▶** (or Enter in the question): Qwen3.5-2B answers live on the GPU (4-13 s). It is the trained repairer's base model with the repair adapter switched off, so it has no FaithGuard training; it sees the tables rendered as the benchmark's generators saw them, and is asked for one sentence that names each figure's year (the generators' three-sentence prompt makes the 2B model show its working, which the rule checker reads badly). The answer goes straight into Catch.
- **Write the correct answer from the table**: a template written from the cells the question names (lookups, growth rates and changes), for when the GPU is not available. It refuses rather than guess (two rows of the same name, a line printed in brackets, two line items in one question, no earlier year for a change).
- Or type any answer, right or wrong, and press **Check it with FaithGuard ▶**.

The *Try* suggestions and the line-item buttons are checked when the demo starts (about 25 s, in the background): each is kept only if the template answers it and the live pipeline sends that answer, so what is clicked on stage has been run. Rows printed in brackets (expenses) are left out of them (see the limitations below).

On the answer, **Plant an error** writes one error of each kind into the original answer, each with the action the live pipeline takes: the other entity's figures (Group ↔ Company or Bank), the other year's figure, a neighbouring line item, thousand read as million, the direction word flipped, or a slip of 3 in the last digit (the commonest real error). The wrong figures are written by the executor from the wrong cells, in the answer's own style. Everything else works as for the examples: edit the answer, step through, run the trained repairer live. Own questions stay in the sidebar for the session.

Suggested script (2 minutes): Tokyo Cement → *By what percentage did the Group's profit for the year grow in 2026?* → **Ask the AI**: it says profit "grew by 49.6%"; Catch marks it unsupported (profit fell from Rs. 3,459 million to Rs. 2,580 million), Control chooses REPAIR, Correct writes `CALCULATE` and the answer goes out as "declined by 25.4%". Then **Write the correct answer from the table** on the same question (sent unchanged) and **Plant an error: Wrong entity**: the Company's cells turn red and the repair gives the Group's figures back. The AI is greedy (no sampling), so the same question gets the same answer at every rehearsal. Other questions where the AI slips and FaithGuard fixes it: Sunshine, *By what percentage did the Group's profit for the year grow in 2026?* (AI: grew 15.0%; FaithGuard: declined by 2.5%); Central Finance, the same question for 2026 (AI: 57.6%; FaithGuard: 3.7%).

Stress tests before the talk:
- **The AI** (laptop GPU, 68 questions over the six reports, each judged against the tables by a separate reviewer): 61 handled well (28 right and sent, 24 wrong and repaired to the right figures, 9 wrong and withheld), no bad repairs, 3 sent with a wrong figure (two on a question that names no entity, so the Company's figure was a fair reading), 3 right answers withheld (Sampath). Sampath Bank's growth questions are withheld even when the AI is right (the policy is cautious on that report), so do not use them on stage.
- **The one-click questions** (all 260 suggestions and line-item buttons over the six reports): every template answer sent; their 1,145 planted errors all caught and repaired back to the right figures, none missed.
- Planted errors are offered only where the checker can see them: a direction flip only on a change ("a rise of 9.3%", not "rose to X"), a wrong entity only when the question or answer names one, a slip moved further if it happens to equal another ratio in the tables, and a variant whose repair would not give the figures back is left out (the screen says how many).

### Output and Results (closing, any member)

- Step **Output** shows what the user gets: the original, the repaired answer with the cells behind its numbers, or a refusal with the evidence. Real answers also show the development reference answer, which the pipeline never sees.
- **Results** (sidebar): detection, repair and policy tables from `runs/`, under the banner "development results; the human-labelled test comes next".

## Recording a backup video

Start the demo, then record each script in turn with the Xbox Game Bar (Win+Alt+R starts and stops; files go to `Videos\Captures`) or OBS. Record at the projector's resolution, and keep one take per member so a failed live run can be swapped for its clip.

## Known limitations shown by the demo

- The rule checker reads one period per clause: a base amount with no year ("rose 9.3% from Rs. 13,004 million to Rs. 14,213 million") is checked as FY2025 and "repaired" to the same figure. Typing the years avoids it, and so do the one-click edits, which `precompute.py` checks.
- Channel A alone raises many false alarms; the policy reads Channel B's features.
- The gate cannot check a metric the evidence does not name (example 6, trained column).
- Own questions: expenses printed in brackets are stored as negative figures, so an answer giving an expense as a positive amount is "repaired" to a negative one, and a change in an expense takes the stored sign (cost of sales "decreased" when it rose). The suggestions and line-item buttons leave those rows out, and the screen shows a *Known limitation* note when a question or answer touches one.
- Own questions: a units note written into the answer ("Rs 000") is read as a number, and the repair can write a figure over it; the AI is asked to write the unit as a word, and the screen notes it when it appears.
- Own questions: the 2B AI's long answers with working ("from X to Y") run into the one-period-per-clause limit above, which is why it is asked for one sentence.
- Own questions: "by how much" questions (typed as *difference*) are withheld on every real report even when every number is supported: the certified policy's P(unsafe) is 0.66 for them on tables this large (the controlled track's tables are small). Ask "By what percentage…" or "How did … change…" instead; the screen explains a withheld answer whose numbers are all supported. Sampath Bank's growth answers rounded to whole percents are withheld the same way.
- Own questions: "profit attributable to owners/equity holders" can match a subtotal row, and rows that share a name (current and non-current, an impairment line and the loan book) are accepted either way by the checker. The template refuses both rather than guess; a typed answer to them is checked as the frozen checker reads it.
- Own questions: a company name with "Bank" or "Company" in it reads as that column. The question is shortened to the name before it ("Sampath Bank's" → "Sampath's", shown on screen); an answer that says "Sampath Bank's" gets a note instead, as answers are never rewritten.
- Own questions: when the question names no line item the report has, any figure from the tables passes (the checker has nothing to compare it with). Do not use that as a stunt.
- Short year forms ("FY25", "the previous year") are read into the question's period, the field the benchmark's writers set by hand; four-digit years are left to the checker. The rule checker, policy and repairers are the frozen research system (D-104); none of the above is patched for the demo.

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
