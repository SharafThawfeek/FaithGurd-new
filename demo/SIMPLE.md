# FaithGuard simple demo

One page for a non-technical audience: ask a question about a company's annual report, an AI answers, and FaithGuard says in plain words whether every number checks out, what it fixed, or why it held the answer back. Then plant a mistake and watch it get caught.

It runs on the same server as the full demo (see [README.md](README.md)) and changes nothing in it:

```
.venv\Scripts\python demo\app.py
```

then open **http://127.0.0.1:8765/simple.html**. The full demo stays at http://127.0.0.1:8765/ (the link at the top right of the simple page).

## What is on the page

1. **Pick a company report**: the fictional bank or one of the five real annual reports.
2. **Ask a question**: type one, or click a suggestion or a figure name (all checked when the demo starts).
3. **Get an answer**: *Ask the AI* (a small model live on the laptop, a few seconds), *Take the right answer from the table*, or *type your own answer* (right or wrong).

The result shows the answer with every number marked (green ✓ right, red ✗ wrong, amber ? not checkable), a big verdict (sent, fixed, or held back), and three plain steps: what was checked against which figures in the report, what FaithGuard decided and why, and the answer the user gets. **Try to trick it** plants one typical mistake (another part of the company, another year, the wrong line, the wrong size, up instead of down, a small maths slip); **Back to the original answer** undoes it.

## Two-minute script

Tokyo Cement → *By what percentage did the Group's profit for the year grow in 2026?* → **Ask the AI**: it says profit "grew by 49.9%"; the page crosses it out, says the report shows a fall of 25.4% (Rs. 3,459 million to Rs. 2,580 million), and sends "declined by 25.4%". Then **Try to trick it → Use another part of the company**: the Company's figures are caught and the Group's put back.

## Honest limits (said on the page when they come up)

- A cost printed in brackets, given as a plain positive figure, is treated as a mistake; a company name with "Bank" or "Company" in it is read as that column. The page marks these amber as *known limitations*, not as fixes, and offers no tricks on them.
- "By how much" questions, and some answers on the large real reports, are held back even when every number is right: FaithGuard plays safe there, and the page says so.
- Words like "up" or "down" are checked only when they describe a change; avoid extra numbers that are not report figures ("the 3rd record year").
