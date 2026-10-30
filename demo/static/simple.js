// FaithGuard, the simple view: ask a question, see the AI's answer, see what FaithGuard did, try to trick it.
// It uses the same live API as the full demo (app.js) and changes nothing in it.
"use strict";

const state = { reports: [], report: null, question: "", answer: "", typing: false, busy: null, status: null, runId: null,
                data: null, original: null, planted: null, tricks: null, sourceNote: null, seq: 0 };

// the starts of the server's notes (demo/ask.py, demo/cases.py) that change what this page says
const NOTE = {
  unknownLine: "Unknown line item:",
  untrusted: "Careful, this fix is not trustworthy:",
  contradiction: "The sentence contradicts itself:",
  asksAbout: "The question asks about",  // the entity and the period notes: the answer gives another part's or year's figure
  oneYear: "One year per clause:",
  sum: "Not checkable:",
  held: "Every number is supported, yet the policy withholds the answer:",
  name: "The answer says “",
};

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
    return { error: err.name === "AbortError" ? "That took too long, so it was stopped. Try again, or write a template answer from the table." : "The demo server did not answer. Is it still running?" };
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
// the AI loaded and then failed several times in a row (demo/models.py), not one that failed to load
const stoppedAnswering = (r) => !!r && r.state === "failed" && /stopped answering|errors in a row/.test(r.detail || "");
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
    return "the report prints this line in brackets (as a minus figure), and FaithGuard treats a plain positive figure for it as a mistake";
  }
  const name = notes.find((n) => n.startsWith(NOTE.name));
  if (c.slots.includes("entity_scope") && name) {
    const quoted = (/“([^”]+)”/.exec(name) || [])[1] || "the company's name";
    const word = /(Bank|Company)$/.exec(quoted);
    return `the answer names “${quoted}”, and FaithGuard reads the word “${word ? word[1] : "Bank"}” as that column of the report, not the Group`;
  }
  if (notes.some((n) => /^“000”/.test(n)) && /^0+$/.test(c.text.replace(/[^0-9]/g, ""))) return "the answer writes the unit as “000”, which FaithGuard reads as a number";
  return null;
}

// a figure the server's notes say FaithGuard cannot check the way it did: a sum of several lines, or a year read from
// the clause; the note quotes the figure (“66,423,749”)
function noteOn(d, c) {
  if (c.verdict === "supported") return null;
  const digits = (s) => s.replace(/[^0-9.]/g, "").replace(/^\.+|\.+$/g, "");  // "Rs. 66,423,749 thousand" -> "66423749"
  for (const n of d.caveats || []) {
    const sum = n.startsWith(NOTE.sum), year = n.startsWith(NOTE.oneYear) || (n.startsWith(NOTE.untrusted) && /one year per clause/i.test(n));
    const quote = (/“([^”]+)”/.exec(n) || [])[1];
    if (!(sum || year) || !quote || (quote !== c.text && digits(quote) !== digits(c.text))) continue;
    // both forms say where the year came from: the clause's, or the question's when the sentence has none
    const read = year ? (/\bas (\d{4})\b/.exec(n) || [])[1] : null, whose = /the question's year/.test(n) ? "the question's year"
      : /the clause's year/.test(n) ? "the clause's year" : "its clause's (or the question's) year";
    return sum ? { kind: "sum", tip: "adds up several lines: not checkable",
      text: " can't be checked: it adds up (or averages) several lines of the report, and FaithGuard compares a figure with one line only (a known limitation)." }
      : { kind: "year", tip: `may be right: FaithGuard read it with ${whose}`,
        text: ` may be right: it has no year of its own, so FaithGuard read it as ${read ? `the ${read} figure, ${whose}` : whose} (it reads one year per clause, a known limitation).` };
  }
  return null;
}

// "The question asks about the Group, but the answer gives the Bank's figure." (or "about 2026, ... the 2025 figure"):
// the supported figures that are another part's or year's than the question's
function offQuestion(d) {
  const n = (d.caveats || []).find((x) => x.startsWith(NOTE.asksAbout));
  const m = n && /^The question asks about (.+?), but the answer gives the (.+?) figure/.exec(n);
  if (!m) return null;
  const year = /^\d{4}/.test(m[1]), asked = m[1].replace(/^the /i, "").toLowerCase();
  const off = (c) => c.verdict === "supported" && c.intended && (year ? c.intended.period && c.intended.period !== m[1]
    : c.intended.entity && c.intended.entity !== asked);
  let ids = d.catch.claims.filter(off).map((c) => c.id);
  if (!ids.length) ids = d.catch.claims.filter((c) => c.verdict === "supported").map((c) => c.id);
  return { note: n, year, asked: m[1], given: m[2], ids,
    of: (c) => year ? `the ${(c.intended && c.intended.period) || m[2]} figure` : `the ${PART[c.intended && c.intended.entity] ? `${PART[c.intended.entity]}'s` : m[2]} figure` };
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
};
// the checker's slot that says it found the planted kind of mistake; otherwise the reason is what the checker found
const PLANTED_SLOT = { entity: "entity_scope", year: "period", line: "metric", scale: "scale_currency", direction: "sign" };

function mistakeOf(d, c) {
  const kind = state.planted && state.planted.kind;
  if (kind && PLANTED_MISTAKE[kind] && c.slots.includes(PLANTED_SLOT[kind])) return PLANTED_MISTAKE[kind];
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
// asked every 10 s (every 2 s while a model loads), and after the AI fails or gives a recorded answer
async function refreshStatus() {
  const s = await api("/api/status", null, 10);
  const el = document.getElementById("ai");
  if (s.error) {
    el.replaceChildren(h("span", { class: "dot" }), "The demo server is not answering");
  } else {
    if (state.runId === null) state.runId = s.run_id || null;
    else if (s.run_id && s.run_id !== state.runId) {  // a new server: this page's questions and results are gone from it
      const banner = document.getElementById("restart");
      if (banner) { banner.textContent = "The demo was restarted: reload the page."; banner.hidden = false; }
    }
    state.status = s;
    const r = s.repairer || {};
    const text = r.state === "ready" ? "AI ready (live on this laptop)" : r.state === "loading" ? "AI loading…"
      : stoppedAnswering(r) ? "AI not answering: recorded or table answers" : r.state === "failed" ? "AI did not load: recorded or table answers"
        : "AI not loaded: recorded or table answers";
    el.replaceChildren(h("span", { class: `dot ${r.state === "ready" ? "ready" : r.state === "loading" ? "loading" : ""}` }),
      h("span", { title: r.detail || null }, text),
      s.version ? h("span", { class: "ver", title: "the code this server runs" }, ` · code ${s.version}`) : null);
  }
  updateButtons();
  const loading = !s.error && ((s.repairer && s.repairer.state === "loading") || (s.channel_a && s.channel_a.state === "loading"));
  clearTimeout(refreshStatus.timer);  // one timer, however many calls overlap
  refreshStatus.timer = setTimeout(refreshStatus, loading ? 2000 : 10000);
}

// ---------------------------------------------------------------- the question
function setQuestion(text) {
  if (state.busy) return;
  state.question = text;
  const input = document.getElementById("question");
  if (input && input.value !== text) input.value = text;
  if (state.data) { state.seq++; state.data = state.original = state.planted = state.tricks = state.sourceNote = null; renderResult(); }  // the old result answered another question
  updateButtons();
}

function renderAsk() {
  const r = report();
  const box = document.getElementById("ask");
  if (!r) { box.replaceChildren(h("div", { class: "card" }, "Loading the reports…")); return; }
  const select = h("select", { id: "report", "aria-label": "Company report",
    onchange: (ev) => { state.report = ev.target.value; state.question = ""; state.answer = ""; state.seq++; state.data = state.original = state.planted = state.tricks = state.sourceNote = null; renderAsk(); renderResult(); } },
  state.reports.map((x) => h("option", { value: x.id, selected: x.id === r.id },
    x.real ? `${x.name} · ${x.country === "LK" ? "Sri Lanka" : "US"} · real report (development)` : x.name)));
  const input = h("input", { id: "question", class: "q", type: "text", maxlength: 300, autocomplete: "off", spellcheck: "false",
    placeholder: "Type a question, or pick one below", "aria-label": "Your question",
    oninput: (ev) => setQuestion(ev.target.value),
    onkeydown: (ev) => { if (ev.key === "Enter" && !ev.repeat) { ev.preventDefault(); ask(aiReady() ? "ai" : "table"); } } });
  input.value = state.question;
  const more = (r.line_items || []).slice(0, 10);
  const typed = state.typing ? [
    h("div", { class: "label" }, "Paste an answer from another AI, or type your own, right or wrong"),
    h("div", { class: "hint" }, "FaithGuard reads one year per clause and every number as a report figure, so a pasted answer works best "
      + "when each figure has its own year and there are no page or note numbers (known limitations)."),
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
    r.suggestions.length || more.length ? h("div", { class: "hint pre" }, "These suggestions and figure names were checked when the demo started: "
      + "for each, the template answer written from the table is sent unchanged. Some lines are left out: those printed in brackets "
      + "(mostly costs, which FaithGuard stores as negative figures, a known limitation), breakdowns by owner, and lines that share a name. "
      + "Questions you type, and the AI's answers, are not pre-checked.") : null,
    h("div", { class: "label" }, "3. Get an answer"),
    h("div", { class: "buttons" },
      h("button", { id: "askai", class: "btn primary", onclick: () => ask("ai") }, "Ask the AI ▶"),
      h("button", { id: "asktable", class: "btn", onclick: () => ask("table") }, "Write a template answer from the table"),
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
  const repairer = (state.status && state.status.repairer) || {};
  if (hint) hint.textContent = aiReady() ? "The AI is Qwen3.5-2B, a small model running live on this laptop, with no FaithGuard training (a few seconds). "
      + "The benchmark's answers came from 9-12B models, and 22.5% of them were labelled incorrect (D-105); we have not measured larger models such as ChatGPT."
    : repairer.state === "loading" ? "The AI is still loading (about a minute after the demo starts)."
      : `The live AI ${stoppedAnswering(repairer) ? "stopped answering" : repairer.state === "failed" ? "did not load" : "is not loaded on this laptop"}: `
        + "“Ask the AI” gives its answer recorded at rehearsal "
        + "for the scripted questions; otherwise write a template answer from the table, or type your own.";
}

function startBusy(id, text) {
  const t0 = performance.now();
  state.busy = { id, text };
  updateButtons();
  const tick = setInterval(() => { const s = document.querySelector(`#${id} .secs`); if (s) s.textContent = `${((performance.now() - t0) / 1000).toFixed(1)} s`; }, 100);
  return () => { clearInterval(tick); state.busy = null; };
}

// the server's messages for questions the template answer cannot handle, in plain words
const TABLE_ERRORS = [
  [/no line item that this question names/, "FaithGuard could not match your question to a line of the two statements: check the spelling, use the line's name as the report prints it, or pick one below."],
  [/report covers .* only/, null],  // already plain: shown as it is
  [/is .*'s report, and the question asks about/, null],
  [/printed in brackets/, "The report prints that line in brackets (a minus figure, mostly a cost), and the template answer skips those. Ask the AI or type your own answer."],
  [/more than one line item/, "The question names more than one line of the report. Ask about one at a time."],
  [/rows called/, "The report has more than one line with that name. Say which one you mean (for example current or non-current)."],
  [/no earlier year/, "The report has no earlier year to compare with."],
  [/lookups, growth rates and changes only/, "The template answer only covers single figures and changes over time. Ask the AI or type your own answer."],
  [/compares two entities/, "The template answer covers one part of the company at a time. Ask the AI or type your own answer."],
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
  if (kind === "ai" && (out.error || out.source === "recorded")) refreshStatus();  // the AI may have stopped: say so in the header
  if (state.report !== r.id || state.question !== question) { renderAsk(); return; }
  if (out.error) { renderAsk(); askError(out.error); return; }
  await check(out.answer, kind, out.note);
}

async function check(answer, kind, note = null) {
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
  state.data = data; state.original = data; state.planted = null; state.tricks = null; state.sourceNote = note || null;
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
  const loose = unknownLine(d), off = offQuestion(d);
  for (const c of d.catch.claims) {
    const limited = limitationOf(d, c), noted = noteOn(d, c);
    const unread = loose && c.verdict === "supported";  // in the report, but not checked against a line the question names
    const other = !unread && off && off.ids.includes(c.id);  // another part's or year's figure than the question's
    const cls = unread || other ? "unsure" : c.verdict === "supported" ? "ok"
      : limited || noted || c.verdict !== "unsupported" || c.missing ? "unsure" : "bad";
    // a loose match's direction word may be right: then the number is what is wrong
    const signOnly = cls === "bad" && c.slots.includes("sign") && c.direction_span && !c.loose_match && !state.planted?.kind?.match(/^(digit|scale)$/);
    if (signOnly) {
      spans.push({ start: c.direction_span[0], end: c.direction_span[1], cls: "bad", tip: c.expected ? `the report says ${c.expected}` : "wrong direction" });
      spans.push({ start: c.start, end: c.end, cls: "plainnum", tip: "" });
    } else {
      const tip = cls === "ok" ? "matches the report" : unread ? "in the report, but not checked against the line the question asks about"
        : other ? `${off.of(c)}, but the question asks about ${off.asked}` : noted ? noted.tip
          : c.expected && !limited ? `the report says ${c.expected}` : limited ? "a known limitation" : "could not be checked";
      spans.push({ start: c.start, end: c.end, cls, tip });
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
const contradicts = (d) => has(d, NOTE.contradiction) || has(d, NOTE.untrusted);
const unknownLine = (d) => has(d, NOTE.unknownLine);
const shaky = (d) => has(d, "“Attributable to”") || (d.output.action === "repair" && (d.caveats || []).some((c) => /printed in brackets/.test(c)));
const unchecked = (d) => d.catch.claims.some((c) => noteOn(d, c));  // a sum, or a figure read with the clause's year

function verdict(d) {
  const a = d.output.action;
  const claims = d.catch.claims;
  const wrong = claims.filter((c) => c.verdict !== "supported").length;
  const off = offQuestion(d);
  if (state.planted && a === "send") {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, "FaithGuard missed your planted mistake."),
        h("div", { class: "sub" }, "It sent the answer with the mistake in it. This is one of the cases it cannot see yet; step 1 shows what it checked.")));
  }
  if (a === "repair" && has(d, NOTE.untrusted)) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, "Careful: FaithGuard's fix is not trustworthy."),
        h("div", { class: "sub" }, "The repair passed FaithGuard's own checks, but it changed a figure it should have kept or wrote one where it does not belong. The note below says which (a known limitation).")));
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
  if ((a === "send" || a === "repair") && off) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, a === "send"
        ? `Careful: the number is in the report, but it is the ${off.given} figure, and the question asks about ${off.asked}.`
        : `Careful: FaithGuard changed this answer, but it gives the ${off.given} figure, and the question asks about ${off.asked}.`),
        h("div", { class: "sub" }, "FaithGuard checks each number against what the answer says it is, not whether it answers the question asked (a known limitation)."
          + (a === "send" ? " It sent the answer as it is." : ""))));
  }
  if ((a === "send" || a === "repair") && unchecked(d)) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "?"),
      h("div", {}, h("div", { class: "head" }, a === "send" ? "Careful: FaithGuard sent this answer, but it could not check every number."
        : "Careful: FaithGuard changed this answer, but it could not check every number."),
        h("div", { class: "sub" }, "Step 1 says which number and why (a known limitation). Check it against the report yourself.")));
  }
  if (a === "repair" && shaky(d)) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, "FaithGuard changed this answer, but this is a kind of answer it is known to get wrong."),
        h("div", { class: "sub" }, "Check the changed figure against the report yourself (a known limitation; see below).")));
  }
  if (a === "send" && wrong) {  // the policy can send an answer whose numbers the checker did not all match
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "?"),
      h("div", {}, h("div", { class: "head" }, "Careful: FaithGuard sent this answer, but not every number checks out."),
        h("div", { class: "sub" }, "Step 1 shows which. FaithGuard's safety rule judged the answer low-risk and sent it anyway.")));
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
  if (allChecked(d) && (d.caveats || []).some((n) => n.startsWith(NOTE.held) && /direction word/.test(n))) {
    return "Every number matches the report, but a word like “up” or “down” beside a looked-up figure makes FaithGuard's safety rule play safe: "
      + "it learned that from template answers with planted mistakes, not from real AI answers (a known limitation). Written with “compared with” instead, the same figures can be sent.";
  }
  if (allChecked(d)) return "Every number matches the report, but FaithGuard's safety rule was tuned on smaller tables and is extra careful on big real reports, so it plays safe.";
  const noted = claims.filter((c) => c.verdict !== "supported").map((c) => noteOn(d, c));
  if (noted.length && noted.every(Boolean)) {
    return noted.some((x) => x.kind === "sum")
      ? "A figure in the answer adds up (or averages) several lines of the report, and FaithGuard compares a figure with one line only, so it cannot check it (a known limitation). It holds back answers it cannot check."
      : "FaithGuard reads one year per clause, so it gave a figure with no year of its own the clause's (or the question's) year and could not match it (a known limitation; the figure may be right). It holds back answers it cannot check.";
  }
  return "A number is wrong, and FaithGuard could not fix it safely, so it stops the answer instead.";
}

// step 2 for an answer that was sent or changed
function decision(d) {
  const a = d.output.action, claims = d.catch.claims, off = offQuestion(d);
  if (a === "send") {
    if (!claims.length) return "There is no number in this answer, so there was nothing to check; FaithGuard sent it as it is.";
    if (unknownLine(d)) return "FaithGuard found each figure somewhere in the report but could not tell which line was asked about, so it sent the answer without a real check (a known limitation).";
    if (off) return off.year ? "Every number matches the year the answer names, not the one the question asks about."
      : "Every number matches the part of the company the answer names, not the one the question asks about.";
    if (contradicts(d)) return "Each number matches the report on its own, so FaithGuard sends it; it does not check that the sentence adds up.";
    if (claims.some((c) => c.verdict !== "supported")) return "Not every number could be checked (see step 1), but FaithGuard's safety rule judged the answer low-risk and sent it.";
    return "Every number matches the report, so FaithGuard sends it unchanged (it checks the numbers, not the words around them).";
  }
  if (has(d, NOTE.untrusted) || unchecked(d)) return "FaithGuard thought a number was wrong and changed it; the note below says why the change cannot be trusted.";
  if (limited(d)) return "FaithGuard thought a number was wrong (see step 1), and the report had a figure to put in its place.";
  if (off) return `FaithGuard changed the number it found wrong, but the answer still gives the ${off.given} figure, and the question asks about ${off.asked}.`;
  if (has(d, NOTE.contradiction)) return "FaithGuard thought a number was wrong and changed it, but the changed answer does not add up (see the note below).";
  return "The report has the right figure, so FaithGuard can fix the answer.";
}

function checkList(d) {
  const claims = d.catch.claims;
  if (!claims.length) return h("div", { class: "d" }, "There is no number in this answer to check.");
  const computed = (c) => ["growth", "diff", "share", "ratio"].includes(c.relation);
  const off = offQuestion(d);
  return h("ul", { class: "check" }, claims.map((c) => {
    if (c.verdict === "supported" && unknownLine(d)) {
      const found = ["share", "ratio"].includes(c.relation) ? " matches a ratio of two figures in the report (shown below), which may be a coincidence"
        : computed(c) ? " matches the change between two figures in the report (shown below), which may be a coincidence"
          : c.intended && c.intended.metric ? " matches the report's figure for the line the answer names" : " appears in the report";
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`), `${found}, but FaithGuard could not tell which line the question means, so this is no real check.`,
        c.asked.length ? h("div", { class: "from" }, "It matched: ", cells(c, c.asked)) : null);
    }
    if (c.verdict === "supported" && off && off.ids.includes(c.id)) {
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`), ` is in the report as ${off.of(c)}, but the question asks about ${off.asked}. `
        + "FaithGuard checks each number against what the answer says it is, not whether it answers the question asked (a known limitation).",
        c.asked.length ? h("div", { class: "from" }, "Found in: ", cells(c, c.asked)) : null);
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
    const noted = noteOn(d, c);
    if (noted) {  // no "The report says" or "The answer used": the figure FaithGuard compared with is not the one the answer gives
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`), noted.text,
        c.asked.length ? h("div", { class: "from" }, noted.kind === "sum" ? "It compared it with one line only: " : "FaithGuard compared it with: ", cells(c, c.asked)) : null);
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

// the full demo's known-limitation notes, said plainly: a text, a function of the match and the case (null: already said
// on the page), or null (said in step 2, or kept as it is below)
const PLAIN_NOTES = [
  [/^(.+?) is printed in brackets/, (m) => `${m[1]} is printed in brackets in the report (as a minus figure). FaithGuard treats a plain positive figure for it as a mistake, a known limitation.`],
  [/^“000”/, "The answer writes the unit as “000”, which FaithGuard misreads as a number (a known limitation)."],
  [/^The answer says “([^”]+)”/, (m, d) => {
    const word = (/“(\w+)” in the company's name/.exec(m.input) || [])[1] || "Bank";
    if (d.catch.claims.some((c) => c.verdict !== "supported" && c.slots.includes("entity_scope"))) return null;  // said in step 1
    if (!d.catch.claims.some((c) => c.intended && c.intended.entity === word.toLowerCase())) return null;  // the checker did not read that column
    return `The answer says “${m[1]}”: FaithGuard reads the word “${word}” in the company's name as that column of the report, not the Group's (a known limitation).`;
  }],
  [/^The question asks about/, (m, d) => (offQuestion(d) || {}).note === m.input ? null : m.input],  // said in the verdict and step 1
  [/^(Not checkable|One year per clause):/, (m, d) => d.output.action !== "repair" && d.catch.claims.some((c) => noteOn(d, c)) ? null : m.input],  // said in step 1
  [/^Wording:/, (m) => m.input.replace(/the frozen executor/g, "FaithGuard's repair")],
  [/^Every number is supported/, null],
  [/^The sentence contradicts itself/, null],  // kept as it is, below
];
function notes(d) {
  const out = (d.caveats || []).filter((c) => c.startsWith(NOTE.contradiction));
  for (const c of d.caveats || []) {
    const hit = PLAIN_NOTES.find(([re]) => re.test(c));
    const text = !hit ? c : typeof hit[1] === "function" ? hit[1](hit[0].exec(c), d) : hit[1];
    if (text && !out.includes(text)) out.push(text);
  }
  if (d.catch.claims.some((c) => c.direction_span && c.relation === "cell")) {
    out.push("Words like “up” or “down” are checked only when they describe a change (a percentage or an amount of change).");
  }
  return out;
}

function renderResult() {
  const box = document.getElementById("result");
  const d = state.data;
  const link = document.getElementById("full");  // the full demo opens on this question (app.js reads ?case=)
  if (link) link.href = d && state.original ? `/?case=${encodeURIComponent(state.original.id)}` : "/";
  if (!d) { box.replaceChildren(); return; }
  const a = d.output.action;
  // a recording says why it was used, as the server labels it: "(the live AI is not loaded)" or "(the live AI did not answer)"
  const by = /recorded at rehearsal/.test(d.generator) ? `The AI's answer to this question, recorded at rehearsal${(/\s*\([^)]*\)/.exec(d.generator) || [""])[0]}:`
    : /^Qwen/.test(d.generator) ? "The AI answered:" : /^a template/.test(d.generator) ? "The template answer written from the table:" : "Your answer:";
  const planted = state.planted ? h("div", { class: "planted" }, h("b", {}, `You planted a mistake: ${state.planted.title}.`),
    h("button", { id: "back", class: "btn", onclick: backToOriginal }, "Back to the original answer")) : null;
  const decide = a === "send" || a === "repair" ? decision(d) : whyHeld(d);
  const rule = d.correct.rule;
  const fixed = a === "repair" && rule && rule.check && rule.check.text;
  // the released fix is the rule repairer's (it runs on the CPU); the evaluated system repairs with v1
  const which = a === "repair" ? h("div", { class: "note" }, "This fix was written by the rule repairer (v0), which runs on this laptop; "
    + "the system we evaluated uses the trained repairer v1. On the locked test, with the rule checker's flags, both corrected 50.6% of the 83 wrong answers, "
    + "but the rule repairer added a new error to 6.2% of the answers it sent and damaged 6.3% of the right ones, against 0.4% and none for v1 (runs/main/report.md).") : null;
  const fix = fixed ? [
    h("div", { class: "final" }, repaired(rule.check)),
    rule.check.changes.some((c) => c.cells.length) ? h("div", { class: "from" }, "Worked out from: ",
      [...new Set(rule.check.changes.flatMap((c) => c.cells.map((id) => cellText(id, c.cell_labels[id]))))].join("  ·  ")) : null,
    limited(d) || shaky(d) || contradicts(d) || unchecked(d) ? null
      : h("div", { class: "note" }, "Before sending, FaithGuard re-checked each new number against the report cell it came from. It does not check the words around them."),
    which,
  ] : a === "send" ? [h("div", { class: "final" }, d.output.text)]
    : a === "repair" ? [h("div", { class: "final" }, d.output.text || ""), which]
      : [h("div", { class: "final" }, "“I can't give a reliable answer to this from the report.”"),
        h("div", { class: "note" }, "This is what the user sees instead of an answer FaithGuard cannot stand behind.")];
  const n = notes(d);
  box.replaceChildren(h("section", { class: "card", id: "resultcard" },
    planted,
    h("div", { class: "who" }, state.planted ? "The answer, with your planted mistake:" : by),
    h("div", { class: "answer" }, marked(d)),
    !state.planted && state.sourceNote ? h("div", { class: "note" }, state.sourceNote) : null,
    d.caption && d.group === "ask" ? h("div", { class: "note" }, d.caption) : null,  // how FaithGuard read the question ("Read “last year” as 2026 ...")
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
  // planted mistakes whose repair does not give the figures back are not offered; the page says how many
  const left = t.dropped ? `${t.dropped} planted mistake${t.dropped > 1 ? "s" : ""} left out: FaithGuard's repair would not give the right figures back (a known limitation).` : null;
  if (!t.edits.length) {
    card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" }, t.error ? `No mistakes could be prepared: ${t.error}`
      : left || "There is no correct number in this answer to plant a mistake in."));
    return;
  }
  const whose = /^Qwen/.test(o.generator) ? "The AI's answer" : "This answer";
  const intro = h("p", { class: "d" }, t.on === "repaired"
    ? `${whose} had no correct number left to spoil, so these plant a mistake in FaithGuard's fixed answer. Pick one and see what FaithGuard does with it.`
    : "Plant one typical mistake and see what FaithGuard does with it.");
  card.replaceChildren(h("h2", {}, "Try to trick it"), intro,
    h("p", { class: "hint" }, "These mistakes are planted only where FaithGuard's checker can see them, so catching them is by design: they show how FaithGuard "
      + "fixes a mistake, not how often it catches one. On the benchmark's 672 real AI answers with numbers, the checker flagged 144 of the 170 "
      + "that the labels call wrong, and also 110 of the 502 right ones (labels by separate blind Claude passes, D-103, D-105)."),
    h("div", { class: "tricks" }, t.edits.map((e) => {
      const n = trickName(e.label);
      return h("button", { class: `trick${state.planted && state.planted.answer === e.answer ? " on" : ""}`, title: e.answer, onclick: () => plant(e, n) },
        h("b", {}, n.title), h("span", {}, n.detail), e.expect === "send" ? h("span", { class: "miss" }, "FaithGuard misses this one") : null);
    })),
    left ? h("p", { class: "hint" }, left) : null);
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
