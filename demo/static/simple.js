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
  asksAbout: "The question asks about",  // the entity, period and line notes: the answer gives another part's, year's or line's figure
  oneYear: "One year per clause:",
  sum: "Not checkable:",
  held: "Every number is supported, yet the policy withholds the answer:",
  name: "The answer says “",
  level: "A total given as a change:",  // a year's figure written as the change ("increased by Rs. 3,500,217")
  noUnit: "No unit:",  // the digits of a figure in thousands, with no unit
  direction: "Direction not checked:",  // a wrong up/down word beside a rate the checker read without it
  rateSign: "Rate read as a rise:",  // a fall's rate with no up/down word of its own ("decreased by X, or 25.4%")
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
// a fall written in accounting brackets ("changed by (22.5%)"): the checker reads it as a rise. With no up/down word and
// no other mistake, the figure is right
const bracketed = (d, c) => /\(\s*$/.test(d.answer.slice(0, c.start)) && /^\s*\)/.test(d.answer.slice(c.end));
const inBrackets = (d, c) => ["growth", "diff"].includes(c.relation) && !c.direction_span && c.slots.length && c.slots.every((s) => s === "sign")
  && bracketed(d, c);

function limitationOf(d, c) {
  // known limitations of FaithGuard that make it call a right figure wrong, with what to say instead
  const notes = d.caveats || [];
  if (c.slots.includes("sign") && c.relation === "cell" && notes.some((n) => /printed in brackets/.test(n))) {
    return "the report prints this line in brackets (as a minus figure), and FaithGuard treats a plain positive figure for it as a mistake";
  }
  if (inBrackets(d, c)) return "the answer writes the fall in accounting brackets, which FaithGuard reads as a rise";
  if (notes.some((n) => n.startsWith(`${NOTE.rateSign} “${c.text}”`))) {
    return "its up/down word is on another figure of the sentence (as in “decreased by X, or Y%”), and FaithGuard reads a rate with no up/down word of its own as a rise";
  }
  const name = notes.find((n) => n.startsWith(NOTE.name));
  if (c.slots.includes("entity_scope") && name) {
    const quoted = (/“([^”]+)”/.exec(name) || [])[1] || "the company's name";
    const word = /(Bank|Company)$/.exec(quoted);
    return `the answer names “${quoted}”, and FaithGuard reads the word “${word ? word[1] : "Bank"}” as that column of the report, not the Group`;
  }
  if (notes.some((n) => /^“000”/.test(n)) && /^0+$/.test(c.text.replace(/[^0-9]/g, ""))) return "the answer writes the unit as “000”, which FaithGuard reads as a number";
  if (notes.some((n) => n.startsWith(`“${c.text}” looks like a page or note number`))) return PAGE;
  return null;
}
const PAGE = "it looks like a page or note number, which FaithGuard reads as a report figure";

// the figure a server note is about: the one it quotes first (“66,423,749”), matched to the claim with that text, else to
// the claim that starts with it ("Rs. 3,500,217 (Rs. '000)"), the same digits or the same leading number
const digits = (s) => s.replace(/[^0-9.]/g, "").replace(/^\.+|\.+$/g, "");  // "Rs. 66,423,749 thousand" -> "66423749"
const leading = (s) => ((/\d[\d,]*(?:\.\d+)?/.exec(s) || [""])[0]).replace(/,/g, "");
const firstQuote = (n) => (/“([^”]+)”/.exec(n) || [])[1] || null;
function quotes(d, n, c) {
  const q = firstQuote(n), claims = d.catch.claims;
  if (!q) return false;
  const hit = claims.find((x) => x.text === q) || claims.find((x) => x.text.startsWith(q)) || claims.find((x) => digits(x.text) === digits(q))
    || claims.find((x) => leading(x.text) && leading(x.text) === leading(q));
  return !!hit && hit.id === c.id;
}

// a figure the server's notes say FaithGuard cannot check the way it did: a sum of several lines, a year read from the
// clause, or a right figure a fix moved to another line than the question asks; the note quotes the figure (“66,423,749”)
function noteOn(d, c) {
  if (c.verdict === "supported") return null;
  for (const n of d.caveats || []) {
    // a short split year ("FY25/26") read as its first year: the note says so, in the one-year form or a fix's
    const split = /” is given for “([^”]+)”, which the frozen checker reads as (\d{4})/.exec(n);
    const sum = n.startsWith(NOTE.sum), year = n.startsWith(NOTE.oneYear) || (n.startsWith(NOTE.untrusted) && (/one year per clause/i.test(n) || !!split));
    // "“Rs. 18.4 billion” is the report's figure for “Gross profit”, the line the question asks about (or the line the
    // answer names, or a row of that name), but FaithGuard read another line and changed it"
    const line = n.startsWith(NOTE.untrusted) && /^“[^”]+” is the report's figure for /.test(n.slice(NOTE.untrusted.length).trim());
    if (!(sum || year || line) || !quotes(d, n, c)) continue;
    if (line) {
      const asked = /the line the question asks about/.test(n);
      return { kind: "line", tip: `may be right: the report's figure for the line ${asked ? "the question asks about" : "the answer names"}`,
        text: ` may be right: it is the report's figure for the line ${asked ? "the question asks about" : "the answer names"}, but FaithGuard `
          + "read another line and changed it (a known limitation; the note below says which)." };
    }
    // both forms say where the year came from: the clause's, or the question's when the sentence has none
    const read = year ? (/\bas (\d{4})\b/.exec(n) || [])[1] : null, whose = /the question's year/.test(n) ? "the question's year"
      : /the clause's year/.test(n) ? "the clause's year" : "its clause's (or the question's) year";
    if (sum) return { kind: "sum", tip: "adds up several lines: not checkable",
      text: " can't be checked: it adds up (or averages) several lines of the report, and FaithGuard compares a figure with one line only (a known limitation)." };
    if (split) {
      const column = (/report's (?:FY[\d/]+ is its )?(\d{4}) column/.exec(n) || [])[1];
      return { kind: "year", why: "split", tip: `may be right: FaithGuard read “${split[1]}” as ${split[2]}`,
        text: ` may be right: the answer gives it for “${split[1]}”, which FaithGuard reads as ${split[2]}${column ? `, not as the report's ${column} column` : ""} (a known limitation).` };
    }
    // its year in brackets after it ("Rs 13.87bn (FY2025)"): the checker skips the aside, so the figure does have a year
    if (/has its year in brackets/.test(n) || /^\s*\(\s*(?:FY\s?)?(?:19|20)\d{2}(?:\s?[/-]\s?\d{2,4})?\s*\)/i.test(d.answer.slice(c.end))) {
      return { kind: "year", why: "bracket", tip: `may be right: FaithGuard skipped the year in brackets and read it with ${whose}`,
        text: ` may be right: its year is in brackets after it, which FaithGuard skips, so it read it as ${read ? `the ${read} figure, ${whose}` : whose} (a known limitation).` };
    }
    // a fix's note says the answer gives the figure a year ("a year earlier", "the previous year's"): not "no year of its own"
    const gives = (/the answer gives it for (\d{4})/.exec(n) || [])[1];
    if (gives || /(?:previous|prior|preceding|last)\s+year['’]s\s*$/i.test(d.answer.slice(Math.max(0, c.start - 30), c.start))) {
      return { kind: "year", why: "own", tip: `may be right: FaithGuard read it with ${whose}`,
        text: ` may be right: FaithGuard reads one year per clause, so it read it as ${read ? `the ${read} figure, ${whose}` : whose}${gives ? `, but the answer gives it for ${gives}` : ""} (a known limitation).` };
    }
    return { kind: "year", why: "none", tip: `may be right: FaithGuard read it with ${whose}`,
      text: ` may be right: it has no year of its own, so FaithGuard read it as ${read ? `the ${read} figure, ${whose}` : whose} (it reads one year per clause, a known limitation).` };
  }
  return null;
}

// a figure the checker accepted because a cell has it, while the answer gives it as something else: a year's total
// written as a change ("increased by Rs. 3,500,217"), or the bare digits of a figure in thousands. Step 1 goes on with the
// note's own words after the figure it quotes first, said plainly; own: false when it had to say it in its own words
const FLAGS = {
  level: { tip: "in the report as a year's total, not as a change",
    text: " is in the report, but as a year's total, not as the change the answer says it is. FaithGuard's checker accepts it because the figure is in the report (a known limitation)." },
  noUnit: { tip: "no unit: only its digits match the report",
    text: " has no unit, so as written it is not the report's figure; FaithGuard matched only its digits (a known limitation)." },
  direction: { tip: "the figure matches, but the up/down word beside it is wrong, and FaithGuard did not check it",
    text: " matches the report, but the up/down word beside it is wrong, and FaithGuard did not check that word (a known limitation)." },
};
function flagOn(d, c) {
  if (c.verdict !== "supported") return null;
  for (const n of d.caveats || []) {
    const kind = n.startsWith(NOTE.level) ? "level" : n.startsWith(NOTE.noUnit) ? "noUnit" : n.startsWith(NOTE.direction) ? "direction" : null;
    if (!kind || !quotes(d, n, c)) continue;
    const q = firstQuote(n), at = n.indexOf("“");
    const rest = n.slice(at + q.length + 2).trim();
    const own = /^[a-z]/.test(rest) && rest.length > 20;
    const text = own ? " " + rest.replace(/\b[Tt]he frozen checker\b/g, "FaithGuard's checker").replace(/\bmatches a cell\b/g, "matches a figure in the report")
      .replace(/\bto the cell\b/g, "to the report's figure") : FLAGS[kind].text;
    return { kind, note: n, own, text, tip: FLAGS[kind].tip };
  }
  return null;
}
const flagOf = (d) => has(d, NOTE.level) ? "level" : has(d, NOTE.noUnit) ? "noUnit" : has(d, NOTE.direction) ? "direction" : null;
// what a flagged answer gets wrong, for the verdict and step 2
const FLAG_WHAT = { level: "it gives a year's total as a change", noUnit: "a figure in it has no unit", direction: "an up/down word in it is wrong" };

// "The question asks about the Group, but the answer gives the Bank's figure." (or "about 2026, ... the 2025 figure", or
// "about “Revenue”, but the answer gives the figure for “Gross profit”"): the supported figures that are another part's,
// year's or line's than the question's. given and of(c) are said as "the Bank's figure", "the figure for “Gross profit”"
function offQuestion(d) {
  const n = (d.caveats || []).find((x) => x.startsWith(NOTE.asksAbout));
  if (!n) return null;
  const line = /^The question asks about “(.+?)”, but the answer gives the figure for “(.+?)”/.exec(n);
  const m = line || /^The question asks about (.+?), but the answer gives the (.+?) figure/.exec(n);
  if (!m) return null;
  const kind = line ? "line" : /^\d{4}/.test(m[1]) ? "year" : "entity", asked = m[1].replace(/^the /i, "").toLowerCase();
  const off = (c) => c.verdict === "supported" && c.intended && (kind === "line" ? true : kind === "year"
    ? c.intended.period && c.intended.period !== m[1] : c.intended.entity && c.intended.entity !== asked);
  let ids = d.catch.claims.filter(off).map((c) => c.id);
  if (!ids.length) ids = d.catch.claims.filter((c) => c.verdict === "supported").map((c) => c.id);
  const of = (c) => kind === "line" ? `the figure for “${m[2]}”` : kind === "year" ? `the ${(c.intended && c.intended.period) || m[2]} figure`
    : `the ${PART[c.intended && c.intended.entity] ? `${PART[c.intended.entity]}'s` : m[2]} figure`;
  return { note: n, kind, year: kind === "year", asked: kind === "line" ? `“${m[1]}”` : m[1],
    given: kind === "line" ? `the figure for “${m[2]}”` : `the ${m[2]} figure`, ids, of };
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
  if (c.slots.includes("sign") && bracketed(d, c)) {  // the brackets say down: the up/down slot is FaithGuard's misreading
    return `${mistakeOf(d, { ...c, slots: c.slots.filter((s) => s !== "sign") })}, and FaithGuard reads its accounting brackets as a rise (a known limitation)`;
  }
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
    // replaceChildren, unlike h(), writes a null as the text "null": pass only real nodes
    el.replaceChildren(...[h("span", { class: `dot ${r.state === "ready" ? "ready" : r.state === "loading" ? "loading" : ""}` }),
      h("span", { title: r.detail || null }, text),
      s.version ? h("span", { class: "ver", title: "the code this server runs" }, ` · code ${s.version}`) : null].filter(Boolean));
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
    // Enter does what "Ask the AI" does, as on the full page: with the AI off, the server answers with its rehearsal recording or says why not
    onkeydown: (ev) => { if (ev.key === "Enter" && !ev.repeat) { ev.preventDefault(); ask("ai"); } } });
  input.value = state.question;
  const more = (r.line_items || []).slice(0, 10);
  const typed = state.typing ? [
    h("div", { class: "label" }, "Paste an answer from another AI, or type your own, right or wrong"),
    h("div", { class: "hint" }, "FaithGuard reads one year per clause and every number as a report figure, so a pasted answer works best "
      + "when each figure has its own year and its unit, each sentence names one line of the report, a change gives both years' figures, "
      + "a fall says “fell” or uses a minus sign (not brackets), and there are no page or note numbers (known limitations)."),
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
    h("div", { class: "err", id: "askerr", hidden: true }),
    h("div", { class: "cut", id: "askcut", hidden: true })));
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
  if (hint) hint.textContent = aiReady() ? "The AI is Qwen3.5-2B, a small model running live on this laptop, with no FaithGuard training "
      + "(in our stress test an answer and its check took 2-25 s, 6.9 s on average). "
      + "The benchmark's answers came from 9-12B models, and 22.5% of them were labelled incorrect (D-105); we have not measured larger models such as ChatGPT."
    : repairer.state === "loading" ? "The AI is still loading (about a minute after the demo starts)."
      : `The live AI ${stoppedAnswering(repairer) ? "stopped answering" : repairer.state === "failed" ? "did not load" : "is not loaded on this laptop"}: `
        + "“Ask the AI” gives its answer recorded at rehearsal "
        + "for the suggested questions; otherwise write a template answer from the table, or type your own.";
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
// cut: the AI's text when it was cut off before a sentence ended; shown greyed beside the refusal, never checked
function askError(msg, cut = null) {
  const el = document.getElementById("askerr"), box = document.getElementById("askcut");
  if (!el) return;
  let plain = msg ? (TABLE_ERRORS.find(([re]) => re.test(msg)) || [null, msg])[1] || msg : "";
  // the server leaves "ask the AI" out of a refusal when the AI has no answer to give: so does the plain text
  if (msg && !/ask the AI/i.test(msg)) plain = plain.replace("Ask the AI or type your own answer.", "Type your own answer.");
  el.textContent = plain; el.hidden = !plain;
  if (box) {
    box.replaceChildren(...(plain && cut ? [h("div", { class: "k" }, "The AI's text as it was cut off, not checked:"), h("div", {}, cut)] : []));
    box.hidden = !(plain && cut);
  }
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
  if (out.error) { renderAsk(); askError(out.error, out.cut_text); return; }
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
    const limited = limitationOf(d, c), noted = noteOn(d, c), flagged = flagOn(d, c);
    const unread = !flagged && loose && c.verdict === "supported";  // in the report, but not checked against a line the question names
    const other = !flagged && !unread && off && off.ids.includes(c.id);  // another part's, year's or line's figure than the question's
    const cls = flagged || unread || other ? "unsure" : c.verdict === "supported" ? "ok"
      : limited || noted || c.verdict !== "unsupported" || c.missing || cannotTrace(c) ? "unsure" : "bad";
    if (cls === "bad" && signOnly(c)) {
      spans.push({ start: c.direction_span[0], end: c.direction_span[1], cls: "bad", tip: c.expected ? `the report says ${c.expected}` : "wrong direction" });
      spans.push({ start: c.start, end: c.end, cls: "plainnum", tip: "" });
    } else {
      const tip = cls === "ok" ? "matches the report" : flagged ? flagged.tip : unread ? "in the report, but not checked against the line the question asks about"
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
// a figure that matches nothing the checker can trace: a computed figure matched only by chance, with no expected value
const cannotTrace = (c) => c.verdict === "unsupported" && c.loose_match && !c.expected;
// an up/down mistake whose number is right: the direction word is what is wrong ("grew" for a fall). A loose match's
// direction word may be right (then the number is what is wrong), and so may a planted maths or size slip's
const signOnly = (c) => c.verdict === "unsupported" && c.slots.length > 0 && c.slots.every((s) => s === "sign") && !!c.direction_span
  && !c.loose_match && !(state.planted && /^(digit|scale)$/.test(state.planted.kind || ""));
// "a fall of 2.5%" as the report shows it, from the checker's expected value ("a fall of 2.5%" or "-2.5%")
const shownChange = (c) => !c.expected ? null : /^an? /.test(c.expected) ? c.expected
  : /^[-−]/.test(c.expected) ? `a fall of ${c.expected.slice(1)}` : `a rise of ${c.expected}`;

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
  const flag = flagOf(d);
  if ((a === "send" || a === "repair") && flag) {  // a figure the checker accepted because a cell has it, given as something else
    const what = FLAG_WHAT[flag];
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, a === "send" ? `Careful: FaithGuard sent this answer, but ${what}.` : `Careful: FaithGuard changed this answer, but ${what}.`),
        h("div", { class: "sub" }, (flag === "level"
          ? "The figure is in the report, so FaithGuard's checker accepted it, but it is not the change the answer says it is"
          : flag === "direction" ? "The figure matches the report, but FaithGuard did not check the up/down word beside it"
            : "Its digits match the report, but without its unit the figure is not the report's") + " (a known limitation). Step 1 says which.")));
  }
  if ((a === "send" || a === "repair") && unknownLine(d)) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "?"),
      h("div", {}, h("div", { class: "head" }, "FaithGuard matched the figure to the report, but could not tell which line the question is about."),
        h("div", { class: "sub" }, "So it could not really check the answer (a known limitation). Ask with the line's name as the report prints it.")));
  }
  if ((a === "send" || a === "repair") && off) {
    return h("div", { class: "verdict abstain" }, h("div", { class: "icon" }, "!"),
      h("div", {}, h("div", { class: "head" }, a === "send"
        ? `Careful: the number is in the report, but it is ${off.given}, and the question asks about ${off.asked}.`
        : `Careful: FaithGuard changed this answer, but it gives ${off.given}, and the question asks about ${off.asked}.`),
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
  // a figure the checker accepted because a cell has it: the policy held the answer back for its own reasons, rightly
  if (has(d, NOTE.level)) {
    return "One figure is a year's total given as a change (step 1 says which), so the change the answer gives is wrong. FaithGuard's checker accepted the figure "
      + "because it is in the report, so it did not see this mistake (a known limitation); its safety rule held the answer back for its own reasons, which is right here.";
  }
  if (has(d, NOTE.noUnit)) {
    return "A figure has no unit (step 1 says which), so as written it is not the report's figure. FaithGuard matched only its digits, so it did not see this mistake "
      + "(a known limitation); its safety rule held the answer back for its own reasons, which is right here.";
  }
  if (has(d, NOTE.direction)) {
    return "An up/down word is wrong (step 1 says which). FaithGuard's checker did not check that word, so it did not see this mistake "
      + "(a known limitation); its safety rule held the answer back for its own reasons, which is right here.";
  }
  const held = (d.caveats || []).find((n) => n.startsWith(NOTE.held)) || "";
  if (allChecked(d) && unknownLine(d)) {
    return "FaithGuard matched each figure to a figure in the report, or to one worked out from two of them, but could not tell which line the question is about, so this was no real check (a known limitation). "
      + "Its safety rule held the answer back.";
  }
  const off = offQuestion(d);
  if (allChecked(d) && off) {
    return `Every number is in the report, but the answer gives ${off.given}, and the question asks about ${off.asked}; FaithGuard does not check that (a known limitation). `
      + "Its safety rule held the answer back for its own reasons.";
  }
  if (allChecked(d) && /direction word/.test(held)) {
    return "Every number matches the report, but a word like “up” or “down” beside a looked-up figure makes FaithGuard's safety rule play safe: "
      + "it learned that from template answers with planted mistakes, not from real AI answers (a known limitation). Written with “compared with” instead, the same figures can be sent.";
  }
  // "grew 21.8% to Rs. 61.01 billion": a rate with only the new year's figure of the same line, as the server's note says
  const line = (c) => c.intended && c.intended.metric;
  if (allChecked(d) && /both years/.test(held) && claims.some((g) => ["growth", "diff"].includes(g.relation) && line(g)
      && claims.some((a) => a.relation === "cell" && line(a) === line(g)))) {
    return "Every number matches the report, but a growth rate given with only the new year's figure (“grew X% to Y”) makes FaithGuard's safety rule play safe: "
      + "such answers score just over its cut-off on these reports, a pattern it learned from template answers, not from real AI answers (a known limitation). "
      + "Written with both years' figures (“from X in 2025 to Y in 2026”), as the template answer does, the same figures were sent in our tests.";
  }
  if (allChecked(d)) {
    return "Every number matches the report, but FaithGuard's safety rule still judged the answer too risky to send, so it plays safe. The rule learned from template "
      + "answers with planted mistakes, not from real AI answers, so some other wordings score too high (a known limitation).";
  }
  // every figure it did not match is one it could not check, or one it misread: not a figure it found wrong
  const unmatched = claims.filter((c) => c.verdict !== "supported");
  const noted = unmatched.map((c) => noteOn(d, c));
  if (noted.length && noted.every((x) => x && x.kind !== "line")) {
    return noted.some((x) => x.kind === "sum")
      ? "A figure in the answer adds up (or averages) several lines of the report, and FaithGuard compares a figure with one line only, so it cannot check it (a known limitation). It holds back answers it cannot check."
      : noted.some((x) => x.why === "split")
        ? "FaithGuard reads a short split year such as “FY25/26” as its first year, not as the report's column for it, so it could not match a figure (a known limitation; the figure may be right). It holds back answers it cannot check."
        : noted.some((x) => x.why === "bracket")
          ? "FaithGuard skips a year written in brackets after a figure and reads the clause's (or the question's) year instead, so it could not match the figure (a known limitation; the figure may be right). It holds back answers it cannot check."
          : noted.some((x) => x.why === "own")
            ? "FaithGuard reads one year per clause, so it read a figure with the clause's (or the question's) year and could not match it (a known limitation; the figure may be right). It holds back answers it cannot check."
            : "FaithGuard reads one year per clause, so it gave a figure with no year of its own the clause's (or the question's) year and could not match it (a known limitation; the figure may be right). It holds back answers it cannot check.";
  }
  if (unmatched.every((c) => limitationOf(d, c) === PAGE)) {
    return "A page or note number in the answer is not a report figure, but FaithGuard reads every number as one and could not match it (a known limitation). It holds back answers it cannot check.";
  }
  if (unmatched.every((c) => limitationOf(d, c))) {
    return "FaithGuard misread a figure that may be right (step 1 says what; a known limitation), so it could not check it. It holds back answers it cannot check.";
  }
  if (unmatched.every((c) => c.verdict !== "unsupported" || cannotTrace(c))) {
    return "FaithGuard could not find where this figure comes from in the report, so it cannot check it, and it holds back answers it cannot check.";
  }
  if (unmatched.every((c) => limitationOf(d, c) || noteOn(d, c) || c.verdict !== "unsupported" || cannotTrace(c))) {
    return "FaithGuard could not check every figure in this answer (step 1 says why; known limitations), and it holds back answers it cannot check.";
  }
  return "A number is wrong, and FaithGuard could not fix it safely, so it stops the answer instead.";
}

// step 2 for an answer that was sent or changed
function decision(d) {
  const a = d.output.action, claims = d.catch.claims, off = offQuestion(d), flag = flagOf(d);
  if (a === "send") {
    if (!claims.length) return "There is no number in this answer, so there was nothing to check; FaithGuard sent it as it is.";
    if (flag === "level") return "The figure is in the report, so FaithGuard's checker accepted it and sent the answer; it does not check that a figure given as a change is one (a known limitation, see step 1).";
    if (flag === "direction") return "Each figure matches the report, so FaithGuard sent the answer; it did not check the up/down word beside one of them, and that word is wrong (a known limitation, see step 1).";
    if (flag) return "Each figure's digits match the report, so FaithGuard sent the answer; it does not check a unit the answer leaves out (a known limitation, see step 1).";
    if (unknownLine(d)) return "FaithGuard matched each figure to a figure in the report, or to a change or ratio worked out from two of them, but could not tell which line was asked about, so it sent the answer without a real check (a known limitation).";
    if (off) return `Every number matches the ${{ year: "year", entity: "part of the company", line: "line" }[off.kind]} the answer names, not the one the question asks about.`;
    if (contradicts(d)) return "Each number matches the report on its own, so FaithGuard sends it; it does not check that the sentence adds up.";
    if (claims.some((c) => c.verdict !== "supported")) return "Not every number could be checked (see step 1), but FaithGuard's safety rule judged the answer low-risk and sent it.";
    return "Every number matches the report, so FaithGuard sends it unchanged (it checks the numbers, not the words around them).";
  }
  if (has(d, NOTE.untrusted) || unchecked(d)) return "FaithGuard thought a number was wrong and changed it; the note below says why the change cannot be trusted.";
  if (limited(d)) return "FaithGuard thought a number was wrong (see step 1), and the report had a figure to put in its place.";
  if (flag) return `FaithGuard changed the number it found wrong, but ${{ level: "another figure is a year's total given as a change", noUnit: "a figure in the answer has no unit", direction: "an up/down word in the answer is wrong" }[flag]} (see step 1).`;
  if (off) return `FaithGuard changed the number it found wrong, but the answer still gives ${off.given}, and the question asks about ${off.asked}.`;
  if (has(d, NOTE.contradiction)) return "FaithGuard thought a number was wrong and changed it, but the changed answer does not add up (see the note below).";
  if (claims.filter((c) => c.verdict !== "supported").every(signOnly)) return "The report's two figures show which way it went, so FaithGuard can fix the up/down word.";
  return "The report has the right figure, so FaithGuard can fix the answer.";
}

function checkList(d) {
  const claims = d.catch.claims;
  if (!claims.length) return h("div", { class: "d" }, "There is no number in this answer to check.");
  const computed = (c) => ["growth", "diff", "share", "ratio"].includes(c.relation);
  const off = offQuestion(d);
  return h("ul", { class: "check" }, claims.map((c) => {
    const flagged = flagOn(d, c);
    if (flagged) {
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`), flagged.text,
        c.asked.length ? h("div", { class: "from" }, "Found in: ", cells(c, c.asked)) : null);
    }
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
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`), why === PAGE
        ? " looks like a page or note number, not a report figure, but FaithGuard reads every number as a report figure, so ignore what it says about it (a known limitation)."
        : ` is right, but ${why} (a known limitation).`,
        c.asked.length ? h("div", { class: "from" }, "FaithGuard compared it with: ", cells(c, c.asked)) : null);
    }
    const noted = noteOn(d, c);
    if (noted) {  // no "The report says" or "The answer used": the figure FaithGuard compared with is not the one the answer gives
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`), noted.text,
        c.asked.length ? h("div", { class: "from" }, noted.kind === "sum" ? "It compared it with one line only: " : "FaithGuard compared it with: ", cells(c, c.asked)) : null);
    }
    if (c.missing || c.verdict !== "unsupported" || cannotTrace(c)) {
      return h("li", { class: "unsure" }, h("b", {}, `? ${c.text}`),
        c.missing && !(c.intended && c.intended.metric) ? " can't be checked: FaithGuard could not tell which line of the report it is about."
          : c.missing ? " can't be checked: the two statements FaithGuard was given do not contain this figure."
            : " can't be checked: FaithGuard could not find where this figure comes from in the report.");
    }
    const guess = c.loose_match || ["share", "ratio"].includes(c.relation);
    const word = signOnly(c) && shownChange(c) ? d.answer.slice(...c.direction_span) : null;  // the number is right, its up/down word is not
    const rows = [];
    if (c.expected && c.expected !== c.text && !word) rows.push(h("div", { class: "k" }, "The report says"), h("div", {}, h("b", {}, c.expected)));
    if (c.asked.length) rows.push(h("div", { class: "k" }, "From"), h("div", {}, cells(c, c.asked)));
    if (c.came_from.length && !guess && !c.same_cell && !state.planted) rows.push(h("div", { class: "k" }, "The answer used"), h("div", {}, cells(c, c.came_from)));
    return h("li", { class: "bad" }, word ? [h("b", {}, `✗ “${word}”`), ` is wrong: the report shows ${shownChange(c)}.`]
      : [h("b", {}, `✗ ${c.text}`), ` is wrong: ${mistakeOf(d, c)}.`], rows.length ? h("div", { class: "pair" }, rows) : null);
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
  [/^(A total given as a change|No unit|Direction not checked):/, (m, d) => d.catch.claims.some((c) => { const f = flagOn(d, c); return f && f.own && f.note === m.input; }) ? null : m.input],  // in step 1, in its own words
  [/accounting brackets/, (m, d) => !m.input.startsWith(NOTE.untrusted)  // said in step 1, unless it is the note a not-trustworthy fix points to
    && d.catch.claims.some((c) => c.verdict !== "supported" && inBrackets(d, c)) ? null : m.input],
  [/^Rate read as a rise: “([^”]+)”/, (m, d) => d.catch.claims.some((c) => c.text === m[1] && limitationOf(d, c)) ? null : m.input],  // in step 1
  [/^“([^”]+)” looks like a page or note number/, (m, d) => d.catch.claims.some((c) => c.text === m[1] && limitationOf(d, c) === PAGE) ? null : m.input],  // in step 1
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
    out.push("Words like “up” or “down” are checked only when FaithGuard works out the change from two of the report's figures, not beside a single year's figure "
      + "or a change the report prints itself (a known limitation).");
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
    + "the system we evaluated uses the trained repairer v1. On the locked test, with the rule checker's flags, both corrected about half of the 83 wrong answers "
    + "(the rule repairer 50.6%, scored by code; v1 50.6% with labels for its changed repairs, or 49.4% scored by code like the rules, D-112), "
    + "but the rule repairer added a new error to 6.2% of the answers it sent and damaged 6.3% of the right ones, against 0.4% and none for v1 (runs/main/report.md).") : null;
  // a fix of the up/down word only changes no number: say what was re-checked
  const changes = (fixed && rule.check.changes) || [];
  const wordOnly = changes.length > 0 && changes.every((c) => c.direction_word), word = changes.some((c) => c.direction_word);
  const fix = fixed ? [
    h("div", { class: "final" }, repaired(rule.check)),
    rule.check.changes.some((c) => c.cells.length) ? h("div", { class: "from" }, "Worked out from: ",
      [...new Set(rule.check.changes.flatMap((c) => c.cells.map((id) => cellText(id, c.cell_labels[id]))))].join("  ·  ")) : null,
    limited(d) || shaky(d) || contradicts(d) || unchecked(d) || flagOf(d) ? null
      : h("div", { class: "note" }, wordOnly ? "Before sending, FaithGuard worked out the up/down word from the report's two figures and re-checked the answer against them. It does not check the other words."
        : word ? "Before sending, FaithGuard re-checked each new number against the report cells it came from, and worked out the up/down word from the report's two figures. It does not check the other words."
          : "Before sending, FaithGuard re-checked each new number against the report cell it came from. It does not check the words around them."),
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
        h("div", { class: "t" }, a === "repair" ? (wordOnly ? "Changed the up/down word and sent the answer" : "Changed the answer and sent it")
          : a === "send" ? "Sent it to the user" : "Told the user it can't answer reliably"), fix))),
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
  // no real check (no line named, or no figure FaithGuard can trace): a planted mistake would only repeat that
  if (unknownLine(o) || (o.catch.claims.length && o.catch.claims.every((c) => c.verdict !== "supported" && (c.missing || c.verdict !== "unsupported" || cannotTrace(c))))) {
    card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" },
      "FaithGuard could not really check this answer, so a planted mistake would not show anything clear. Pick one of the suggested questions to try."));
    return;
  }
  const t = state.tricks;
  if (!t) { card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" }, h("span", { class: "spin" }), "Preparing mistakes to plant…")); return; }
  // the mistakes would go into a fix FaithGuard itself says not to trust (the server plants none there)
  if (has(o, NOTE.untrusted) && (t.on === "repaired" || (o.output.action === "repair" && !o.catch.claims.some((c) => c.verdict === "supported")))) {
    card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" },
      "FaithGuard's fix of this answer is not trustworthy (see the note above), so a mistake planted in it would not show anything clear. Pick one of the suggested questions to try."));
    return;
  }
  // planted mistakes whose repair does not give the figures back are not offered; the page says how many
  // (on_wrong: they were judged against an answer that already has a wrong number, which every repair changes as well)
  const left = !t.dropped ? null : `${t.dropped} planted mistake${t.dropped > 1 ? "s" : ""} left out: ` + (t.on_wrong
    ? "FaithGuard reads a number in this answer as wrong, and its repair changes that one too, so a planted mistake would not show on its own."
    : "FaithGuard's repair would not give the right figures back (a known limitation).");
  if (!t.edits.length) {
    card.replaceChildren(h("h2", {}, "Try to trick it"), h("p", { class: "hint" }, t.error ? `No mistakes could be prepared: ${t.error}`
      : left || "There is no correct number in this answer to plant a mistake in."));
    return;
  }
  const whose = /^Qwen/.test(o.generator) ? "The AI's answer" : "This answer";
  const intro = h("p", { class: "d" }, t.on === "repaired"
    ? `${whose} had no correct number left to spoil, so these plant a mistake in FaithGuard's fixed answer. Pick one and see what FaithGuard does with it.`
    : "Plant one typical mistake and see what FaithGuard does with it.");
  // replaceChildren, unlike h(), writes a null as the text "null": pass only real nodes
  card.replaceChildren(...[h("h2", {}, "Try to trick it"), intro,
    h("p", { class: "hint" }, "These mistakes are planted only where FaithGuard's checker can see them, so catching them is by design: they show how FaithGuard "
      + "fixes a mistake, not how often it catches one. On the benchmark's 672 real AI answers with numbers, the checker flagged 144 of the 170 "
      + "that the labels call wrong, and also 110 of the 502 right ones (labels by separate blind Claude passes, D-103, D-105)."),
    h("div", { class: "tricks" }, t.edits.map((e) => {
      const n = trickName(e.label);
      return h("button", { class: `trick${state.planted && state.planted.answer === e.answer ? " on" : ""}`, title: e.answer, onclick: () => plant(e, n) },
        h("b", {}, n.title), h("span", {}, n.detail), e.expect === "send" ? h("span", { class: "miss" }, "FaithGuard misses this one") : null);
    })),
    left ? h("p", { class: "hint" }, left) : null].filter(Boolean));
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
