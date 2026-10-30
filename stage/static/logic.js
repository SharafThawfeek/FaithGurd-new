// FaithGuard Stage: what the page may say about an answer.
// Every rule below is copied word for word from demo/static/simple.js, so the new demo says what the tested page says.
// tests/test_stage.py fails if the two drift apart. Do not edit these rules here.
"use strict";

export const state = { reports: [], report: null, planted: null };

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

// Which mark a number gets: the rule inside marked() above, as one value for the 3D scene.
export function classOf(d, c) {
  const loose = unknownLine(d), off = offQuestion(d);
  const limited = limitationOf(d, c), noted = noteOn(d, c), flagged = flagOn(d, c);
  const unread = !flagged && loose && c.verdict === "supported";
  const other = !flagged && !unread && off && off.ids.includes(c.id);
  return flagged || unread || other ? "unsure" : c.verdict === "supported" ? "ok"
    : limited || noted || c.verdict !== "unsupported" || c.missing || cannotTrace(c) ? "unsure" : "bad";
}

export { NOTE, h, cellText, cells, marked, repaired, verdict, whyHeld, decision, checkList, notes, trickName, limited, has,
  contradicts, unknownLine, signOnly, allChecked, cannotTrace, flagOf, unchecked, shaky };
