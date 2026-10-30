// Browser check. In the page console: await import("/check.js"); await stageCheck();
// Runs real answers from every report through the whole page at high speed, and returns what each one did.
// Fails loudly on an exception, on a run that never finishes, or on a mark that differs from the tested page's rule.
async function stageCheck({ perReport = 3, plantEach = true } = {}) {
  const { ui, state, stage, show, L } = window.__stage;
  const post = (path, body) => fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }).then((r) => r.json());
  const out = { runs: 0, actions: {}, words: {}, errors: [] };
  if (stage) stage.instant = true;
  async function one(data, label) {
    if (data.error) { out.errors.push(`${label}: ${data.error}`); return; }
    try {
      for (const c of data.catch.claims) {
        const mine = L.classOf(data, c);
        const holder = document.createElement("div");
        holder.append(...L.marked(data));
        const seen = [...holder.querySelectorAll(".num")].map((e) => [e.textContent.replace(/[✓✗?]$/, ""), e.className.replace("num ", "")]);
        const hit = seen.find(([text]) => text === data.answer.slice(c.start, c.end));
        if (hit && hit[1] !== "plain" && hit[1] !== mine) out.errors.push(`${label}: mark ${mine} != page ${hit[1]} on ${hit[0]}`);
      }
      await show(data);
      out.runs++;
      out.actions[data.output.action] = (out.actions[data.output.action] || 0) + 1;
      const word = document.querySelector("#readout .word");
      if (!word) out.errors.push(`${label}: no verdict on screen`);
      else out.words[word.textContent] = (out.words[word.textContent] || 0) + 1;
      if (ui.playing) out.errors.push(`${label}: still playing`);
      const text = document.getElementById("readout").textContent;
      if (/Every number checks out/.test(text)) out.errors.push(`${label}: said every number checks out`);
    } catch (err) { out.errors.push(`${label}: ${err.message}`); }
  }
  for (const r of state.reports) {
    state.report = r.id;
    if (stage) stage.setReport(r);
    for (const q of (r.suggestions || []).slice(0, perReport)) {
      const draft = await post("/api/ask/draft", { report: r.id, question: q });
      if (draft.error) { out.errors.push(`${r.id} draft: ${draft.error}`); continue; }
      const data = await post("/api/ask", { report: r.id, question: q, answer: draft.answer });
      state.planted = null; ui.original = data;
      await one(data, `${r.id} ${q}`);
      if (!plantEach || data.error) continue;
      const tricks = await post("/api/plant", { id: data.id });
      for (const e of (tricks.edits || []).slice(0, 3)) {
        const planted = await post("/api/run", { id: data.id, answer: e.answer, channel_a: false });
        const n = L.trickName(e.label);
        state.planted = { title: n.title.toLowerCase(), kind: n.kind, answer: e.answer };
        await one(planted, `${r.id} planted ${e.label}`);
      }
      state.planted = null;
    }
    for (const [q, a] of [["What was the return on equity in 2026?", "Return on equity was 12.5% in 2026."],
                          ["How much did profit change?", "It changed by Rs. 100 million."],
                          ["What was the Group's revenue in 2026?", "The Group's revenue was Rs. 71.60 in 2026."],
                          ["Summarise the year.", "It was a good year."]]) {
      const data = await post("/api/ask", { report: r.id, question: q, answer: a });
      state.planted = null;
      await one(data, `${r.id} typed ${q}`);
    }
  }
  if (stage) stage.instant = false;
  return out;
}

window.stageCheck = stageCheck;
