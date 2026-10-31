# Intro video

`FaithGuard-Intro.mp4` is the last cut of the AI-voiced intro video (30 October 2026, 2 min 18 s, 1920×1080). Do not play it at Progress Presentation 1: the module's PP1 template asks for a 1 to 2 minute video, and its handwritten note reads as recorded by a person, with AI tools for images only. The team records its own video from the script in the demo and viva run-sheet. The cuts in `old/` are superseded: they are kept as a record of what was corrected, and they overclaim in the ways listed below.

The narration is a synthetic voice (Microsoft Edge text-to-speech, en-US-AndrewNeural), not a team member. Like the rest of the repository, the script and the render code were written by Claude at the team's direction (README, "AI assistance").

| File | What it is |
| --- | --- |
| `FaithGuard-Intro.mp4` | The current cut |
| `intro-video/script.json` | The narration, one entry per sentence, grouped by scene. The captions show the same text. |
| `intro-video/tts.py` | Voices each sentence to its own MP3 with edge-tts (run it in its own environment) |
| `intro-video/render.py` | Draws the scenes, lays the captions on the narration and writes the MP4. Needs Pillow, NumPy, ffmpeg and the Windows Segoe UI fonts. `--sheet` and `--frames` write still frames to check the layout first. |
| `old/FaithGuard-Intro-2026-10-24.mp4` | Superseded cut of 24 October (2 min 6 s). Do not play. |
| `old/FaithGuard-Intro-2026-10-30-0213.mp4` | Superseded cut of 30 October, 02:13 (2 min 8 s). Do not play. |
| `old/FaithGuard-Intro-2026-10-30-0435.mp4` | Superseded cut of 30 October, 04:35, committed in 6c44784 (2 min 13 s). Do not play. |

To rebuild: `python tts.py script.json AUDIO_DIR`, then `python render.py script.json AUDIO_DIR OUT.mp4` (both in `intro-video/`).

## What the current cut says, and what backs it

- **The problem.** "Our benchmark labels: 216 marked spans. 130 are a wrong number; 9 are wrong context." From runs/main/labels/report.md ("Labelled spans by slot": entity_scope 5, period 3 and metric 1 make the 9). Wrong-context errors are called rare.
- **Sri Lanka.** "We found no comparable public dataset". The search was not systematic (docs/papers/benchmark.md, abstract).
- **Detect.** "Mismatches are flagged, with the reason. Some errors are missed." The rule checker misses 26 of 170 wrong numeric answers (runs/main/labels/report.md). When it cannot name the line item, any table figure passes (docs/panel-defence.md, section 2, question 11).
- **The green box.** "Answer sent, with its sources" means the answer went out with its numbers checked and traced. It does not mean the answer is right: no policy setting was certified on the benchmark's answers (runs/main/report.md, D-113).
- **Repair.** "Flagged numbers are replaced with the report's own figures." A flagged number is not always wrong, and a fix can be wrong: the hard gate makes a repair agree with the checker, not safe in general (docs/panel-defence.md, section 2, question 10).
- **The example.** The report is the demo's fictional bank, with made-up figures, and the screen says so. On the demo, POST /api/ask {"report":"demo:fictional-bank","question":"What was the Group's profit after tax in 2025?","answer":"Group profit after tax rose 7.0% to Rs. 12,450 million."} is repaired to "Group profit after tax rose 9.3% to Rs. 14,213 million." (checked on commit 6c44784 with the models off).
- **What makes it different.** "Trains on context mistakes built from US filings; not shown to help": the XBRL negatives showed no gain in development (AUROC 0.933 with them, 0.932 without; docs/papers/detection.md §6.1), and D-H1 was untestable on the locked test (4 wrong-context test answers, fewer than the 20 it needs; runs/main/report.md, runs/main/results.json). "Fixes numbers precisely" rests on R-H1, the one confirmed hypothesis: typed edit programs make fewer new errors than free rewriting. "Tests a limit on wrong answers, and says when it is not met": nothing was certified at the 10% budget (D-113). The benchmark in the last row is not yet released (docs/papers/benchmark.md, section 6).

## What the old cuts got wrong

All three old cuts say the following. The current cut corrects each one.

| Old cut says | Why it is wrong | Current cut |
| --- | --- | --- |
| "Every number in the answer is checked against the report's own tables, and anything that does not fit is flagged" | The checker misses 26 of 170 wrong numeric answers | "Numbers that do not match are flagged, with the reason, but some errors are missed." |
| Green box: "Trusted answer, with its sources" | Nothing was certified on the benchmark (D-113); checked numbers do not mean a right answer | "Answer sent, with its sources" |
| "Wrong numbers are replaced with the report's own figures, so every corrected number can be traced to its source" | Repair changes flagged numbers, which are not always wrong, and a change can be wrong | "Flagged numbers are replaced …, so every changed number can be traced to its source." |
| "And if an answer cannot be made safe, the reader gets the evidence …" | It implies that every answer sent was made safe | "And if an answer is held back, the reader gets the evidence …" |
| "It learns these context mistakes from real company filings." | The mistakes are built from US XBRL filings, not found in them, and their benefit was not shown (development: no gain; D-H1 untestable) | "It trains a detector on context mistakes built from US company filings, though our tests have not shown that this helps." |
| The example's table is headed "Annual report extract" | The bank is fictional and its figures are made up | "Annual report extract (fictional bank, made-up figures)" |

The 24 October and 30 October 02:13 cuts also say:

- "Often the figure is real, but it belongs somewhere else: the Bank's profit given as the Group's, last year's figure given for this year, or thousands read as millions", over the cards "Wrong entity", "Wrong year" and "Wrong scale". This frames wrong-context errors as the usual case, but the labels mark 9 of 216 spans as wrong context and 130 as a wrong number. The 04:35 cut corrected it.
- "No Sri Lankan dataset: no public benchmark exists to test this for Sri Lankan companies", and "there is no public dataset to test this at all". This is stated as fact, but the search was not systematic. The 04:35 cut says "we found no comparable public dataset".
- "These mistakes are hard to catch, because the number really is in the report", which repeats the wrong-context framing.

The 24 October cut also says "It sets a tested limit on how many wrong answers can get through". Nothing was certified on the benchmark (D-113). The 02:13 cut changed it to "It tests a limit on how many wrong answers get through, and says so when the limit cannot be met".
