# FaithGuard Stage

The presentation demo: a live 3D model of the pipeline. Pick a document, ask a question, and watch the real result go through the machine. It uses the same server, API and checks as `demo/`, which stays as the backup.

```
.venv\Scripts\python stage\serve.py
```

It opens http://127.0.0.1:8770/. With `--no-models` it runs without the GPU and uses the answers recorded at rehearsal.

Close any other demo first: the 6 GB GPU can hold the models for one server only.

## Using it

1. **Document** (bottom left): the fictional bank or one of the five real reports.
2. **Who writes the answer**: the live AI, a template from the table, or your own typing.
3. **Question**, then **Run** or Enter.

| Key | Does |
| --- | --- |
| 0 1 2 3 | Camera: all, Catch, Control, Correct, with that part's numbers in the column |
| Space | Speed up the run in progress; again to return |
| R | Replay |
| Esc | Close the detail sheet |

Click a marked number in the answer and the camera flies to its cell in the report. **Why** opens the verdict, every number and the notes. **Plant a mistake** runs a planted mistake through the machine.

## What is real

Every number, verdict, cell, gauge and check on screen comes from the pipeline's result for that answer. The AI's writing time and repairer v1's run are live. The check and decision take under a second, so the machine plays their real result slowly, and the page says so.

## The design

White-card machine on a ledger sheet; a reading column ruled off by a double red margin; four pencils that always mean the same thing: green traced, red wrong, ochre unsure, blue the report. The answer is a tray of type blocks, so a fix lifts out only the wrong block: edits, not rewrites.

## The rules

`static/logic.js` is copied word for word from `demo/static/simple.js`, so this page marks numbers, warns and withholds exactly as the tested page does. `tests/test_stage.py` fails if the two drift apart. The short words on screen come from those rules, and the full words are one click away under **Why**.

## If 3D fails

The page falls back to the reading column alone when WebGL is missing, and `http://127.0.0.1:8770/?flat` asks for that on purpose. The renderer asks for the low-power GPU, so on this laptop the Intel chip draws and the NVIDIA chip stays free for the models. Three.js 0.180.0 (MIT) is kept in `static/vendor/`, so nothing loads from the network.

## Check

With the server up, in the page's console: `await import("/check.js"); await stageCheck();` runs real answers from every report through the whole page at high speed and returns any error.
