# FaithGuard simple demo

One page for a non-technical audience: ask a question about a company's annual report, an AI answers, and FaithGuard says in plain words whether every number checks out, what it fixed, or why it held the answer back. Then plant a mistake and watch it get caught.

It runs on the same server as the full demo (see [README.md](README.md)) and changes nothing in it:

```
.venv\Scripts\python demo\app.py
```

then open **http://127.0.0.1:8765/simple.html**. The full demo stays at http://127.0.0.1:8765/ (the link at the top right of the simple page).

## What is on the page

1. **Pick a company report**: the fictional bank or one of the five real annual reports.
2. **Ask a question**: type one, or click a suggestion or a figure name. These were checked when the demo started (the template answer to each is sent unchanged), and the page says so; lines printed in brackets, breakdowns by owner and lines that share a name are left out. Typed questions and the AI's answers are not pre-checked.
3. **Get an answer**: *Ask the AI* (a small model live on the laptop, a few seconds), *Write a template answer from the table*, or *type your own answer* (right or wrong). A pasted answer from another AI works best when each figure has its own year and there are no page or note numbers; we have not measured larger models such as ChatGPT.

The result shows the answer with every number marked (green ✓ right, red ✗ wrong, amber ? not checkable or not what the question asks), a big verdict (sent, fixed, or held back), and three plain steps: what was checked against which figures in the report, what FaithGuard decided and why, and the answer the user gets. Every fix says that it was written by the rule repairer (v0), which runs on the laptop, while the evaluated system uses the trained repairer v1 (on the locked test both corrected 50.6% of the 83 wrong answers with the rule checker's flags; the rule repairer added a new error to 6.2% of the answers it sent, v1 to 0.4%; runs/main/report.md). **Try to trick it** plants one typical mistake (another part of the company, another year, the wrong line, the wrong size, up instead of down, a small maths slip); **Back to the original answer** undoes it. The mistakes are planted only where the checker can see them, so they are caught by design, and the page says so above the buttons, with how many were left out because their repair would not give the right figures back.

The header asks the server for its state every 10 s. If the server is restarted, the page says "The demo was restarted: reload the page." **Full demo with every detail →** opens the full demo on the question just asked.

## Two-minute script

Tokyo Cement → *By what percentage did the Group's profit for the year grow in 2026?* → **Ask the AI**: it says profit "grew by 49.9%"; the page crosses it out, says the report shows a fall of 25.4% (Rs. 3,459 million to Rs. 2,580 million), and sends "declined by 25.4%" (the rule repairer's fix; the note under it says the evaluated system uses v1). Then **Try to trick it → Use another part of the company**: the Company's figures are caught and the Group's put back.

## Honest limits (said on the page when they come up)

- A line printed in brackets (mostly a cost), given as a plain positive figure, is treated as a mistake. The page marks it amber as a *known limitation*, not as a fix, and offers no tricks on it.
- FaithGuard checks each number against what the answer says it is, not whether it answers the question asked. A company name with "Bank" or "Company" in it is read as that column, both ways: a right Group figure written after "Sampath Bank" is called wrong (amber, a known limitation), and the Bank's figure given for a Group question is accepted as the Bank's. An answer that gives another year's figure than the year asked is accepted the same way. The page marks both amber: "the number is in the report, but it is the Bank's (or the 2025) figure, and the question asks about the Group (or 2026)".
- A figure that adds up (or averages) several lines is compared with one line only, and a figure with no year of its own is read with its clause's year ("X (2025: Y)", "up from Y a year earlier"). The page marks these amber as not checkable, not as wrong. When FaithGuard changed such a figure, the page says the fix is not trustworthy.
- Open questions ("How did Sunshine Holdings perform in 2026?") name no line and no part of the company, so FaithGuard can check a figure against the wrong line and mix the Group's and the Company's figures; a right answer can be "fixed" into a wrong one. The page marks such an answer amber ("could not tell which line", or "the fix is not trustworthy" when a fix puts the Group's figure beside the Company's). Name the line and the Group or Company.
- *Write a template answer from the table* refuses rather than guess: a margin, ratio or return, a misspelt line name ("Did you mean “Net interest income”?"), a short name that is not clearly one line ("What dividend per share did the Company pay?" on Tokyo Cement), two line items it can read, a line printed in brackets, and a year the report does not cover (Ask the AI refuses that year too). It writes one line's figure: read its sentence before checking it.
- "By how much" questions, some answers on the large real reports, and some lookups with "up from" beside them are held back even when every number is right: FaithGuard plays safe there, and the page says why.
- Words like "up" or "down" are checked only when they describe a change; avoid extra numbers that are not report figures ("the 3rd record year").
