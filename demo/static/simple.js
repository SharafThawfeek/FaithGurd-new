// FaithGuard, the simple view: ask a question, see the AI's answer, see what FaithGuard did, try to trick it.
// It uses the same live API as the full demo (app.js) and changes nothing in it.
"use strict";

const state = { reports: [], report: null, question: "", answer: "", typing: false, busy: null, status: null,
                data: null, original: null, planted: null, tricks: null, seq: 0 };

// ---------------------------------------------------------------- helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
async function api(path, body, seconds = 30) {
  const stop = new AbortController();
  const timer = setTimeout(() => stop.abort(), seconds * 1000);
  try {
    const res = await fetch(path, { signal: stop.signal, ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
    return await res.json();
  } catch (err) {
    return { error: err.name === "AbortError" ? "That took too long, so it was stopped. Try again, or take the answer from the table." : "The demo server did not answer. Is it still running?" };
  } finally {
    clearTimeout(timer);
  }
}
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 5000);
}
const aiReady = () => !!(state.status && state.status.repairer && state.status.repairer.state === "ready");
const report = () => state.reports.find((r) => r.id === state.report) || null;
const PART = { group: "Group", bank: "Bank", company: "Company" };
const DOWN_WORDS = /^(fell|fall|falls|fallen|falling|declined|decline|declines|declining|decreased|decrease|decreases|decreasing|dropped|drop|drops|down|lower|lost|shrank|contracted|deteriorated|retreated|smaller)$/i;

// ---------------------------------------------------------------- table cells in plain words
function tableOf(cellId) {
  const r = report();
  const id = (/^(t\d+)r/.exec(cellId || "") || [])[1];
  return r && r.evidence ? r.evidence.tables.find((t) => t.id === id) : null;
}

// "Profit for the year, GROUP 2026 Rs.: 2,579,997,694" -> "Profit for the year, Group 2026: Rs. 2,579,997,694"
function cellText(cellId, label) {
  const m = /^(.*):\s*([^:]*)$/.exec(label || "");
  if (!m) return label || "";
  let where = m[1], value = m[2].trim();
  const t = tableOf(cellId);
  const headerThousand = /'\s*000|\b000\b|thousand/i.test(where);
  const headerCurrency = /US\$|\$|USD/.test(where) ? "US$ " : /\bRs\b|Rs\.|LKR/.test(where) ? "Rs. " : "";
  where = where.replace(/\s*(Rs\.?\s*'?\s*000|Rs\.?|US\$\s*'?\s*000|US\$|\$\s*'?\s*000|LKR|USD|\(\s*'?000\s*\))\s*$/i, "")
    .replace(/^less\s*:\s*/i, "").replace(/(^|,\s*)-\s+/g, "$1").replace(/\s*\(restated\*?\)/ig, "")
    .replace(/\b(GROUP|BANK|COMPANY)\b/g, (w) => w[0] + w.slice(1).toLowerCase()).trim();
  const plainNumber = /^\(?-?[\d.,]+\)?$/.test(value);
  if (/change\s*%/i.test(where) && plainNumber) return `${where.replace(/\s*change\s*%/i, " change")}: ${value}%`;
  const noUnit = /per share|\(rs\.?\)|number of|employees|branches|%|ratio/i.test(where);
  where = where.replace(/\s*\(rs\.?\)/ig, "");
  if (!plainNumber || noUnit) return `${where}: ${value}`;
  const currency = headerCurrency || (t && t.currency === "USD" ? "US$ " : t && t.currency === "LKR" ? "Rs. " : "");
  const thousand = headerThousand || (!headerCurrency && t && t.scale === 3) ? " thousand" : t && !headerCurrency && t.scale === 6 ? " million" : "";
  return `${where}: ${currency}${value}${thousand}`;
}
const cells = (c, ids) => ids.map((id) => cellText(id, c.cell_labels[id])).join("  ·  ");
const partOf = (c, ids) => { for (const id of ids) { const m = /\b(Group|Bank|Company)\b/i.exec(c.cell_labels[id] || ""); if (m) return m[1][0].toUpperCase() + m[1].slice(1).toLowerCase(); } return null; };

// ---------------------------------------------------------------- what kind of problem a number has, in plain words
function limitationOf(d, c) {
  // known limitations of FaithGuard that make it call a right figure wrong, with what to say instead
  const notes = d.caveats || [];
  if (c.slots.includes("sign") && c.relation === "cell" && notes.some((n) => /printed in brackets/.test(n))) {
    return "the report prints this cost in brackets (as a minus figure), and FaithGuard treats a plain positive figure for it as a mistake";
  }
  const name = notes.find((n) => /^The answer says “/.test(n));
  if (c.slots.includes("entity_scope") && name) {
    const quoted = (/“([^”]+)”/.exec(name) || [])[1] || "the company's name";
    const word = /(Bank|Company)$/.exec(quoted);
    return `the answer names “${quoted}”, and FaithGuard reads the word “${word ? word[1] : "Bank"}” as that column of the report, not the Group`;
  }
  if (notes.some((n) => /^“000”/.test(n)) && /^0+$/.test(c.text.replace(/[^0-9]/g, ""))) return "the answer writes the unit as “000”, which FaithGuard reads as a number";
  return null;
}

function currencyWrong(d, c) {
  const textUsd = /US\$|\$|USD/.test(c.text), textRs = /Rs|LKR|rupee/i.test(c.text);
  const reportCurrency = ((d.evidence && d.evidence.tables) || []).map((t) => t.currency).find(Boolean);
  if (reportCurrency === "USD" && textRs) return "the currency is wrong (rupees instead of US dollars)";
  if (reportCurrency === "LKR" && textUsd) return "the currency is wrong (US dollars instead of rupees)";
  return null;
}

const PLANTED_MISTAKE = {
  entity: "it takes the figure from another part of the company",
  year: "it takes the figure from another year",
  line: "it takes a figure from the wrong line of the report",
  scale: "the size is wrong (for example thousands read as millions)",
  direction: "it says up where the report says down (or the other way round)",
  digit: "it does not match what the report's figures give",
};

function mistakeOf(d, c) {
  if (state.planted && PLANTED_MISTAKE[state.planted.kind]) return PLANTED_MISTAKE[state.planted.kind];
  const guess = c.loose_match || ["share", "ratio"].includes(c.relation);
  if (guess || !c.slots.length) return c.relation === "cell" ? "it does not match the report's figure" : "it does not match what the report's figures give";
  if (c.slots.includes("entity_scope")) {
    const want = partOf(c, c.asked), got = partOf(c, c.came_from);
    return want && got && want !== got ? `it took the ${got}'s figure instead of the ${want}'s` : "it took the figure from the wrong part of the company";
  }
  if (c.slots.includes("period")) return "it took the figure from the wrong year";
  if (c.slots.includes("scale_currency")) return currencyWrong(d, c) || "the size is wrong (for example thousands read as millions)";
  if (c.slots.includes("sign")) return "it says up where the report says down (or the other way round)";
  if (c.slots.includes("metric")) return "it took a figure from the wrong line of the report";
  if (c.slots.includes("basis")) return "the change is worked out from the wrong starting figure";
  if (c.slots.includes("unit")) return "the unit is wrong";
  return c.relation === "cell" ? "it does not match the report's figure" : "it does not match what the report's figures give";
}

// ---------------------------------------------------------------- status
async function refreshStatus() {
  const s = await api("/api/status");
  if (!s.error) state.status = s;
  const r = s.repairer || {};
  const el = document.getElementById("ai");
  const text = r.state === "ready" ? "AI ready (live on this laptop)" : r.state === "loading" ? "AI loading…" : "AI not loaded: recorded or table answers";
  el.replaceChildren(h("span", { class: `dot ${r.state === "ready" ? "ready" : r.state === "loading" ? "loading" : ""}` }), text,
    s.version ? h("span", { class: "ver", title: "the code this server runs" }, ` · code ${s.version}`) : null);
  updateButtons();
  if (r.state === "loading" || (s.channel_a && s.channel_a.state === "loading")) setTimeout(refreshStatus, 2000);
}

// ---------------------------------------------------------------- the question
function setQuestion(text) {
  if (state.busy) return;
  state.question = text;
  const input = document.getElementById("question");
  if (input && input.value !== text) input.value = text;
  if (state.data) { state.seq++; state.data = state.original = state.planted = state.tricks = null; renderResult(); }  // the old result answered another question
  updateButtons();
}

function renderAsk() {
  const r = report();
  const box = document.getElementById("ask");
  if (!r) { box.replaceChildren(h("div", { class: "card" }, "Loading the reports…")); return; }
  const select = h("select", { id: "report", "aria-label": "Company report",
    onchange: (ev) => { state.report = ev.target.value; state.question = ""; state.answer = ""; state.seq++; state.data = state.original = state.planted = state.tricks = null; renderAsk(); renderResult(); } },
  state.reports.map((x) => h("option", { value: x.id, selected: x.id === r.id },
    x.real ? `${x.name} (real annual report, ${x.country === "LK" ? "Sri Lanka" : "US"}, development set)` : x.name)));
  const input = h("input", { id: "question", class: "q", type: "text", maxlength: 300, autocomplete: "off", spellcheck: "false",
    placeholder: "Type a question, or pick one below", "aria-label": "Your question",
    oninput: (ev) => setQuestion(ev.target.value),
    onkeydown: (ev) => { if (ev.key === "Enter" && !ev.repeat) { ev.preventDefault(); ask(aiReady() ? "ai" : "table"); } } });
  input.value = state.question;
  const more = (r.line_items || []).slice(0, 10);
  const typed = state.typing ? [
    h("div", { class: "label" }, "Paste an answer from any AI (for example ChatGPT), or type your own, right or wrong"),
    (() => {
      const t = h("textarea", { id: "typed", "aria-label": "Your own answer", placeholder: "For example: The Group's profit for the year grew by 10% in 2026.",
        oninput: (ev) => { state.answer = ev.target.value; updateButtons(); } });
      t.value = state.answer;
      return t;
    })(),
    h("div", { class: "buttons" }, h("button", { id: "check", class: "btn primary", onclick: () => check(state.answer, "typed") }, "Check my answer ▶")),
  ] : null;
  box.replaceChildren(h("section", { class: "card" },
    h("div", { class: "label" }, "1. Pick a company report"), select,
    h("div", { class: "hint" }, r.real
      ? "FaithGuard sees this report's two main statements (income statement and balance sheet), not its notes. These five reports are development reports: the checker's rules were tuned on them; the 48 test and calibration reports stay locked and are not in the demo."
      : "Made-up figures, for showing each kind of mistake."),
    h("div", { class: "label" }, "2. Ask a question about it"), input,
    r.suggestions.length ? h("div", { class: "chips" }, r.suggestions.map((s) => h("button", { class: "chip", onclick: () => setQuestion(s) }, s))) : null,
    more.length ? h("div", { class: "chips more" }, h("span", { class: "hint" }, "Other figures you can ask about: "),
      more.map((x) => h("button", { class: "chip plain", title: x.question, onclick: () => setQuestion(x.question) }, x.label))) : null,
    h("div", { class: "label" }, "3. Get an answer"),
    h("div", { class: "buttons" },
      h("button", { id: "askai", class: "btn primary", onclick: () => ask("ai") }, "Ask the AI ▶"),
      h("button", { id: "asktable", class: "btn", onclick: () => ask("table") }, "Take the right answer from the table"),
      h("button", { id: "toggle", class: "link", onclick: () => { if (state.busy) return; state.typing = !state.typing; renderAsk(); } },
        state.typing ? "hide my own answer" : "or type your own answer")),
    h("div", { class: "hint", id: "aihint" }),
    typed,
    h("div", { class: "err", id: "askerr", hidden: true })));
  updateButtons();
}

function updateButtons() {
  const busy = state.busy, hasQ = state.question.trim().length > 0;
  const set = (id, off) => { const el = document.getElementById(id); if (el && !(busy && busy.id === id)) el.disabled = off; };
  set("askai", !!busy || !hasQ);
  set("asktable", !!busy || !hasQ);
  set("check", !!busy || !hasQ || !state.answer.trim());
  for (const id of ["report", "question", "typed", "toggle", "back"]) set(id, !!busy);
  document.querySelectorAll("#ask .chip, .trick").forEach((c) => (c.disabled = !!busy));
  if (busy && busy.id) {  // a re-render while waiting keeps the spinner on the button that is waiting
    const btn = document.getElementById(busy.id);
    if (btn && !btn.querySelector(".spin")) { btn.disabled = true; btn.replaceChildren(h("span", { class: "spin" }), busy.text, " ", h("span", { class: "secs" })); }
  }
  const hint = document.getElementById("aihint");
  if (hint) hint.textContent = aiReady() ? "The AI is Qwen3.5-2B, a small model running live on this laptop, with no FaithGuard training (a few seconds). The benchmark's answers came from 9-12B models; bigger models such as ChatGPT make fewer mistakes, and FaithGuard checks any of them: paste their answer under “type your own answer”."
    : state.status && state.status.repairer && state.status.repairer.state === "loading" ? "The AI is still loading (about a minute after the demo starts)."
      : "The live AI is not loaded on this laptop: “Ask the AI” gives its answer recorded at rehearsal for the scripted questions; otherwise take the answer from the table, or type your own.";
}

function startBusy(id, text) {
  const t0 = performance.now();
  state.busy = { id, text };
  updateButtons();
  const tick = setInterval(() => { const s = document.querySelector(`#${id} .secs`); if (s) s.textContent = `${((performance.now() - t0) / 1000).toFixed(1)} s`; }, 100);
  return () => { clearInterval(tick); state.busy = null; };
}

// the server's messages for questions the table answer cannot handle, in plain words
const TABLE_ERRORS = [
  [/no line item that this question names/, "FaithGuard could not match your question to a line of the two statements: check the spelling, use the line's name as the report prints it, or pick one below."],
  [/report covers .* only/, null],  // already plain: shown as it is
  [/is .*'s report, and the question asks about/, null],
  [/printed in brackets/, "That line is a cost the report prints in brackets, and the table answer skips those. Ask the AI or type your own answer."],
  [/more than one line item/, "The question names more than one line of the report. Ask about one at a time."],
  [/rows called/, "The report has more than one line with that name. Say which one you mean (for example current or non-current)."],
  [/no earlier year/, "The report has no earlier year to compare with."],
  [/lookups, growth rates and changes only/, "The table answer only covers single figures and changes over time. Ask the AI or type your own answer."],
  [/compares two entities/, "The table answer covers one part of the company at a time. Ask the AI or type your own answer."],
  [/^No figure for/, "The report has no figure for that year or that part of the company."],
];
function askError(msg) {
  const el = document.getElementById("askerr");
  if (!el) return;
  const plain = msg ? (TABLE_ERRORS.find(([re]) => re.test(msg)) || [null, msg])[1] || msg : "";
  el.textContent = plain; el.hidden = !plain;
  if (plain) el.scrollIntoView({ behavior: "smooth", block: "nearest" });
}

async function ask(kind) {
  const r = report(), question = state.question;
  if (state.busy || !r || !question.trim()) return;  // with the AI off, the server answers with its rehearsal recording, if any
  askError("");
  const done = kind === "ai" ? startBusy("askai", "The AI is reading the report…") : startBusy("asktable", "Looking it up…");
  const out = await api(kind === "ai" ? "/api/ask/ai" : "/api/ask/draft", { report: r.id, question }, kind === "ai" ? 90 : 30);
  done();
  if (state.report !== r.id || state.question !== question) { renderAsk(); return; }
  if (out.error) { renderAsk(); askError(out.error); return; }
  await check(out.answer, kind);
}

async function check(answer, kind) {
  const r = report(), question = state.question;
  if (state.busy || !r || !question.trim() || !answer || !answer.trim()) return;
  askError("");
  const id = kind === "ai" ? "askai" : kind === "table" ? "asktable" : "check";
  const done = startBusy(id, "FaithGuard is checking…");
  const data = await api("/api/ask", { report: r.id, question, answer }, 60);
  done();
  renderAsk();
  if (state.report !== r.id || state.question !== question) return;
  if (data.error) { askError(data.error); return; }
  const seq = ++state.seq;
  state.data = data; state.original = data; state.planted = null; state.tricks = null;
  renderResult();
  document.getElementById("result").scrollIntoView({ behavior: "smooth", block: "start" });
  const tricks = await api("/api/plant", { id: data.id }, 60);
  if (seq !== state.seq) return;
  state.tricks = tricks.error ? { edits: [], error: tricks.error } : tricks;
  renderTricks();
}

// ---------------------------------------------------------------- the result
function marked(d) {
  // the answer with every number marked right (green), wrong (red, crossed out) or not checkable (amber);
  // for an up/down mistake the direction word is what is crossed out, not the number
  const text = d.answer;
  const spans = [];
  const loose = unknownLine(d);
  for (const c of d.catch.claims) {
    const limited = limitationOf(d, c);
    const unread = loose && c.verdict === "supported" && !(c.intended && c.intended.metric);
    const cls = unread ? "unsure" : c.verdict === "supported" ? "ok" : limited || c.verdict !== "unsupported" || c.missing ? "unsure" : "bad";
    const signOnly = cls === "bad" && c.slots.includes("sign") && c.direction_span && !state.planted?.kind?.match(/^(digit|scale)$/);
    if (signOnly) {
      spans.push({ start: c.direction_span[0], end: c.direction_span[1], cls: "bad", tip: c.expected ? `the report says ${c.expected}` : "wrong direction" });
      spans.push({ start: c.start, end: c.end, cls: "plainnum", tip: "" });
    } else {
      spans.push({ start: c.start, end: c.end, cls, tip: cls === "ok" ? "matches the report" : c.expected ? `the report says ${c.expected}` : "could not be checked" });
    }
  }
  spans.sort((a, b) => a.start - b.start);
  const parts = [];
  let pos = 0;
  for (const s of spans) {
    if (s.start < pos) continue;
    parts.push(text.slice(pos, s.start));
    const mark = { ok: "✓", bad: "✗", unsure: "?" }[s.cls];
    parts.push(s.cls === "plainnum" ? h("span", { class: "num plain" }, text.slice(s.start, s.end))
      : h("span", { class: `num ${s.cls}`, title: s.tip }, text.slice(s.start, s.end), h("span", { class: "mk" }, mark)));
    pos = s.end;
  }
  parts.push(text.slice(pos));
  return parts;
}

function repaired(check) {
  // the fixed answer with the new numbers in green
  const parts = [];
  let pos = 0;
  for (const c of check.changes || []) {
    parts.push(check.text.slice(pos, c.start), h("span", { class: "num new" }, c.new));
    pos = c.end;
  }
  parts.push(check.text.slice(pos));
  return parts;
}

const limited = (d) => d.catch.claims.some((c) => c.verdict !== "supported" && limitationOf(d, c));

const has = (d, prefix) => (d.caveats || []).some((c) => c.startsWith(prefix));
const contradicts = (d) => has(d, "The sentence contradicts itself") || has(d, "Careful, this fix is not trustworthy");
const unknownLine = (d) => has(d, "Unknown line item");
const shaky = (d) => has(d, "“Attributable to”") || (d.output.action === "repair" && (d.caveats || []).some((c) => /printed in brackets/.test(c)));

function verdict(d) {
  const a = d.output.action;
  const claims = d.catch.claims;
  const wrong = claims.filter((c) => c.verdict !== "supported").length;
  if (state.planted && a === "send") {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, "FaithGuard missed your planted mistake."),
        h("div", { class: "sub" }, "It sent the answer with the mistake in it. This is one of the cases it cannot see yet; step 1 shows what it checked.")));
  }
  if ((a === "send" || a === "repair") && contradicts(d)) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, "Careful: the answer FaithGuard sent does not add up."),
        h("div", { class: "sub" }, "Each number matches the report on its own, but the answer as a whole is not right. FaithGuard does not yet check that (a known limitation); see below.")));
  }
  if ((a === "send" || a === "repair") && unknownLine(d)) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "?"),
      h("div", {}, h("div", { class: "head" }, "FaithGuard found the figure in the report, but could not tell which line the question is about."),
        h("div", { class: "sub" }, "So it could not really check the answer (a known limitation). Ask with the line's name as the report prints it.")));
  }
  if (a === "repair" && shaky(d)) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, "FaithGuard changed this answer, but this is a case it often gets wrong."),
        h("div", { class: "sub" }, "Check the changed figure against the report yourself (a known limitation; see below).")));
  }
  if (a === "send") {
    return h("div", { class: "verdict send" }, h("div", { class: "icon" }, "✓"),
      h("div", {}, h("div", { class: "head" }, claims.length ? "Every number checks out." : "No number to check."),
        h("div", { class: "sub" }, claims.length ? "FaithGuard sends the answer unchanged. It checks the numbers, not the words around them." : "FaithGuard sends the answer as it is.")));
  }
  if (a === "repair" && !limited(d) && claims.filter((c) => c.verdict !== "supported").every((c) => c.slots.length && c.slots.every((s) => s === "sign"))) {
    return h("div", { class: "verdict repair" }, h("div", { class: "icon" }, "✎"),
      h("div", {}, h("div", { class: "head" }, "The direction was wrong (up instead of down, or the other way). FaithGuard fixed it."),
        h("div", { class: "sub" }, "It worked out the direction from the report's figures, and checked the fix before sending it.")));
  }
  if (a === "repair" && limited(d)) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, "FaithGuard changed this answer, but because of a known limitation."),
        h("div", { class: "sub" }, "The figure in the answer was right; step 1 says what FaithGuard misread. It is a limitation we report, not a fix.")));
  }
  if (a === "repair") {
    return h("div", { class: "verdict repair" }, h("div", { class: "icon" }, "✎"),
      h("div", {}, h("div", { class: "head" }, wrong === 1 ? "A number was wrong. FaithGuard fixed it." : "Some numbers were wrong. FaithGuard fixed them."),
        h("div", { class: "sub" }, "It worked out the right figure from the report, and checked the fix before sending it.")));
  }
  return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
    h("div", {}, h("div", { class: "head" }, "FaithGuard holds the answer back."),
      h("div", { class: "sub" }, "It holds back answers it cannot check or fix. Step 2 below says why it stopped this one.")));
}

const allChecked = (d) => d.catch.claims.length > 0 && d.catch.claims.every((c) => c.verdict === "supported");

function whyHeld(d) {
  const claims = d.catch.claims;
  if (!claims.length) return "The answer has no number in it, so there is nothing to check against the report, and FaithGuard does not send unchecked answers.";
  if (claims.some((c) => c.missing && !(c.intended && c.intended.metric))) return "FaithGuard could not tell which line of the two statements this number is about, so it can neither check it nor fix it. It may be in a note, under another name, or not in the report at all.";
  if (claims.some((c) => c.missing)) return "The two statements FaithGuard was given do not contain the figure this answer needs, so it can neither check it nor fix it.";
  if (allChecked(d)) return "Every number matches the report, but FaithGuard's safety rule was tuned on smaller tables and is extra careful on big real reports, so it plays safe.";
  return "A number is wrong, and FaithGuard could not fix it safely, so it stops the answer instead.";
}

function checkList(d) {
  const claims = d.catch.claims;
  if (!claims.length) return h("div", { class: "d" }, "There is no number in this answer to check.");
  const computed = (c) => ["growth", "diff", "share", "ratio"].includes(c.relation);
  return h("ul", { class: "check" }, claims.map((c) => {
    if (c.verdict === "supported" && unknownLine(d) && !(c.intended && c.intended.metric)) {
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`), " appears in the report, but FaithGuard could not tell which line the question means, so this is no real check.",
        c.asked.length ? h("div", { class: "from" }, "It matched: ", cells(c, c.asked)) : null);
    }
    if (c.verdict === "supported") {
      return h("li", { class: "ok" }, h("b", {}, `✓ ${c.text}`), " matches the report",
        c.asked.length ? h("div", { class: "from" }, computed(c) ? "Worked out from: " : "Found in: ", cells(c, c.asked)) : null);
    }
    const why = limitationOf(d, c);
    if (why) {
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`), ` is right, but ${why} (a known limitation).`,
        c.asked.length ? h("div", { class: "from" }, "FaithGuard compared it with: ", cells(c, c.asked)) : null);
    }
    if (c.missing || c.verdict !== "unsupported" || (c.loose_match && !c.expected)) {
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`),
        c.missing && !(c.intended && c.intended.metric) ? " can't be checked: FaithGuard could not tell which line of the report it is about."
          : c.missing ? " can't be checked: the two statements FaithGuard was given do not contain this figure."
            : " can't be checked: FaithGuard could not find where this figure comes from in the report.");
    }
    const guess = c.loose_match || ["share", "ratio"].includes(c.relation);
    const rows = [];
    if (c.expected && c.expected !== c.text) rows.push(h("div", { class: "k" }, "The report says"), h("div", {}, h("b", {}, c.expected)));
    if (c.asked.length) rows.push(h("div", { class: "k" }, "From"), h("div", {}, cells(c, c.asked)));
    if (c.came_from.length && !guess && !c.same_cell && !state.planted) rows.push(h("div", { class: "k" }, "The answer used"), h("div", {}, cells(c, c.came_from)));
    return h("li", { class: "bad" }, h("b", {}, `✗ ${c.text}`), ` is wrong: ${mistakeOf(d, c)}.`, rows.length ? h("div", { class: "pair" }, rows) : null);
  }));
}

// the full demo's known-limitation notes, said plainly (the abstain one is already in step 2)
const PLAIN_NOTES = [
  [/printed in brackets/, "This line is a cost the report prints in brackets (as a minus figure). FaithGuard treats a plain positive figure for it as a mistake, a known limitation."],
  [/^“000”/, "The answer writes the unit as “000”, which FaithGuard misreads as a number (a known limitation)."],
  [/^The answer says “/, null],  // said in step 1
  [/^Every number is supported/, null],
  [/^The sentence contradicts itself/, null],  // kept as it is, below
];
function notes(d) {
  const out = (d.caveats || []).filter((c) => c.startsWith("The sentence contradicts itself"));
  for (const c of d.caveats || []) {
    const hit = PLAIN_NOTES.find(([re]) => re.test(c));
    if (!hit) out.push(c);
    else if (hit[1] && !out.includes(hit[1])) out.push(hit[1]);
  }
  if (d.catch.claims.some((c) => c.direction_span && c.relation === "cell")) {
    out.push("Words like “up” or “down” are checked only when they describe a change (a percentage or an amount of change).");
  }
  return out;
}

function renderResult() {
  const box = document.getElementById("result");
  const d = state.data;
  if (!d) { box.replaceChildren(); return; }
  const a = d.output.action;
  const by = /recorded at rehearsal/.test(d.generator) ? "The AI's answer to this question, recorded at rehearsal (the live AI is not loaded):"
    : /^Qwen/.test(d.generator) ? "The AI answered:" : /^a template/.test(d.generator) ? "The answer written from the table:" : "Your answer:";
  const planted = state.planted ? h("div", { class: "planted" }, h("b", {}, `You planted a mistake: ${state.planted.title}.`),
    h("button", { id: "back", class: "btn", onclick: backToOriginal }, "Back to the original answer")) : null;
  const decide = a === "send" ? "Every number matches, so it is safe to send."
    : a === "repair" && limited(d) ? "FaithGuard thought a number was wrong (see step 1), and the report had a figure to put in its place."
      : a === "repair" ? "The report has the right figure, so FaithGuard can fix the answer."
        : whyHeld(d);
  const rule = d.correct.rule;
  const fixed = a === "repair" && rule && rule.check && rule.check.text;
  const fix = fixed ? [
    h("div", { class: "final" }, repaired(rule.check)),
    rule.check.changes.some((c) => c.cells.length) ? h("div", { class: "from" }, "Worked out from: ",
      [...new Set(rule.check.changes.flatMap((c) => c.cells.map((id) => cellText(id, c.cell_labels[id]))))].join("  ·  ")) : null,
    limited(d) || shaky(d) || contradicts(d) ? null
      : h("div", { class: "note" }, "Before sending, FaithGuard re-checked each new number against the report cell it came from. It does not check the words around them."),
  ] : a === "send" ? [h("div", { class: "final" }, d.output.text)]
    : a === "repair" ? [h("div", { class: "final" }, d.output.text || "")]
      : [h("div", { class: "final" }, "“I can't give a reliable answer to this from the report.”"),
        h("div", { class: "note" }, "This is what the user sees instead of an answer FaithGuard cannot stand behind.")];
  const n = notes(d);
  box.replaceChildren(h("section", { class: "card", id: "resultcard" },
    planted,
    h("div", { class: "who" }, state.planted ? "The answer, with your planted mistake:" : by),
    h("div", { class: "answer" }, marked(d)),
    verdict(d),
    h("h2", {}, "What FaithGuard did"),
    h("div", { class: "steps" },
      h("div", { class: "step" }, h("div", { class: "n" }, "1"), h("div", {}, h("div", { class: "t" }, "Checked every number against the report"), checkList(d))),
      h("div", { class: "step" }, h("div", { class: "n" }, "2"), h("div", {}, h("div", { class: "t" }, "Decided what to do"), h("div", { class: "d" }, decide))),
      h("div", { class: "step" }, h("div", { class: "n" }, "3"), h("div", {},
        h("div", { class: "t" }, a === "repair" ? "Changed the numbers and sent the answer" : a === "send" ? "Sent it to the user" : "Told the user it can't answer reliably"), fix))),
    n.length ? h("div", { class: "note" }, h("b", {}, "Good to know: "), n.join(" ")) : null),
  h("section", { class: "card", id: "trickcard" }));
  renderTricks();
  updateButtons();
}

// ---------------------------------------------------------------- try to trick it
function trickName(label) {
  const [kind, ...rest] = label.split(": ");
  const detail = rest.join(": ");
  if (/^Wrong entity/.test(kind)) return { kind: "entity", title: "Use another part of the company", detail: detail.replace(/^the /, "use the ") };
  if (/^Wrong year/.test(kind)) return { kind: "year", title: "Use another year's figure", detail: detail.replace(/^the /, "use the ") };
  if (/^Wrong line item/.test(kind)) return { kind: "line", title: "Take a figure from the wrong line", detail: `use “${detail.replace(/^less\s*:\s*/i, "")}”` };
  if (/^Wrong scale/.test(kind)) return { kind: "scale", title: "Get the size wrong", detail };
  if (/^Flip the direction/.test(kind)) {
    const to = (/→ “([^”]+)”/.exec(detail) || [])[1] || "";
    return { kind: "direction", title: DOWN_WORDS.test(to) ? "Say down instead of up" : "Say up instead of down", detail };
  }
  if (/^Maths slip/.test(kind)) return { kind: "digit", title: /%/.test(detail) ? "Make a small maths mistake" : "Change a digit", detail };
  return { kind: "", title: label, detail: "" };
}

function renderTricks() {
  const card = document.getElementById("trickcard");
  if (!card || !state.original) return;
  const o = state.original;
  if (o.output.action === "abstain" && allChecked(o)) {
    card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" },
      "FaithGuard already held this answer back, so planting a mistake in it would show nothing new. Pick another question to try."));
    return;
  }
  if (limited(o)) {
    card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" },
      "This answer runs into a known limitation, so a planted mistake would not show anything clear. Pick one of the suggested questions to try."));
    return;
  }
  const t = state.tricks;
  if (!t) { card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" }, h("span", { class: "spin" }), "Preparing mistakes to plant…")); return; }
  if (!t.edits.length) {
    card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" }, t.dropped ? "FaithGuard could not prepare a clean mistake to plant in this answer."
      : "There is no correct number in this answer to plant a mistake in."));
    return;
  }
  const whose = /^Qwen/.test(o.generator) ? "The AI's answer" : "This answer";
  const intro = h("p", { class: "d" }, t.on === "repaired"
    ? `${whose} had no correct number left to spoil, so these plant a mistake in FaithGuard's fixed answer. Pick one and see if FaithGuard catches it.`
    : "Plant a typical mistake, the kind AIs really make, and see if FaithGuard catches it.");
  card.replaceChildren(h("h2", {}, "Try to trick it"), intro,
    h("div", { class: "tricks" }, t.edits.map((e) => {
      const n = trickName(e.label);
      return h("button", { class: `trick${state.planted && state.planted.answer === e.answer ? " on" : ""}`, title: e.answer, onclick: () => plant(e, n) },
        h("b", {}, n.title), h("span", {}, n.detail), e.expect === "send" ? h("span", { class: "miss" }, "FaithGuard misses this one") : null);
    })),
    h("p", { class: "hint" }, "These mistakes are planted where FaithGuard can usually see them, so most are caught. On the benchmark's 672 real AI answers with numbers, "
      + "the checker flagged 144 of the 170 that the labels call wrong, and also 110 of the 502 right ones (labels by separate blind Claude passes, D-103)."));
  updateButtons();
}

async function plant(e, name) {
  if (state.busy) return;
  const seq = ++state.seq;
  state.busy = { id: "" };
  updateButtons();
  const data = await api("/api/run", { id: state.original.id, answer: e.answer, channel_a: false });
  state.busy = null;
  if (seq !== state.seq) { updateButtons(); return; }
  if (data.error) {
    toast(data.error);
    if (/restarted/.test(data.error)) { state.data = state.original = state.planted = state.tricks = null; renderResult(); }
    updateButtons();
    return;
  }
  state.data = data;
  state.planted = { title: name.title.toLowerCase(), kind: name.kind, answer: e.answer };
  renderResult();
  document.getElementById("resultcard").scrollIntoView({ behavior: "smooth", block: "start" });
}

function backToOriginal() {
  if (state.busy) return;
  state.seq++;
  state.data = state.original;
  state.planted = null;
  renderResult();
}

// ---------------------------------------------------------------- start
(async function start() {
  renderAsk();
  refreshStatus();
  const reports = await api("/api/reports", null, 90);  // the first call can wait for the one-click questions to be checked
  if (reports.error) { toast(reports.error); return; }
  state.reports = reports;
  const first = reports.find((r) => r.id === "LK:TKYO") || reports.find((r) => r.real) || reports[0];
  state.report = first && first.id;
  renderAsk();
})();
