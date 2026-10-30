// FaithGuard Stage: the screens around the 3D model. Pick a document, ask, watch the real result go through the machine.
import { Stage } from "./scene.js";
import * as L from "./logic.js";

const { h, state } = L;
const $ = (id) => document.getElementById(id);
const ui = { by: "ai", busy: false, data: null, original: null, sourceNote: null, tricks: null, steps: {}, ms: 0, ai: null, station: null, status: null, runId: null, seq: 0, played: false };
let stage = null;
try { if (location.search.includes("flat")) throw new Error("asked for the flat page"); stage = new Stage($("stage")); } catch (err) { console.warn("3D is off:", err); document.body.classList.add("flat"); }

const STEPS = [["ai", "Answer"], ["catch", "Catch"], ["control", "Control"], ["correct", "Correct"], ["out", "Result"]];
const VIEWS = [["all", "0", "All"], ["catch", "1", "Catch"], ["control", "2", "Control"], ["correct", "3", "Correct"]];
const TICK = { ok: "M2 8 6 13 14 2", bad: "M3 3l10 10M13 3 3 13", unsure: "M8 12v.5M5 5a3 3 0 1 1 3 3v1.5" };
const COLOR = { ok: "var(--green)", bad: "var(--red)", unsure: "var(--ochre)" };
function pencil(kind) {
  const ns = "http://www.w3.org/2000/svg", svg = document.createElementNS(ns, "svg"), p = document.createElementNS(ns, "path");
  svg.setAttribute("viewBox", "0 0 16 16");
  p.setAttribute("d", TICK[kind]); p.setAttribute("fill", "none"); p.setAttribute("stroke", COLOR[kind]); p.setAttribute("stroke-width", "2.2"); p.setAttribute("stroke-linecap", "round"); p.setAttribute("stroke-linejoin", "round");
  svg.append(p);
  return svg;
}
async function api(path, body, seconds = 30) {
  const stop = new AbortController(), timer = setTimeout(() => stop.abort(), seconds * 1000);
  try {
    const res = await fetch(path, { signal: stop.signal, ...(body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}) });
    return await res.json();
  } catch (err) {
    return { error: err.name === "AbortError" ? "That took too long, so it was stopped. Try again." : "The server did not answer. Is it still running?" };
  } finally { clearTimeout(timer); }
}
function toast(msg) { const t = $("toast"); t.textContent = msg; t.hidden = false; clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 7000); }
const report = () => state.reports.find((r) => r.id === state.report) || null;

// ---------------------------------------------------------------- what the result is called
function called(d) {
  const a = d.output.action, v = L.verdict(d), careful = v.classList.contains("abstain") && a !== "abstain";
  const head = v.querySelector(".head").textContent, claims = d.catch.claims;
  if (state.planted && a === "send") return { word: "Missed", cls: "missed", over: "Sent with your planted mistake", line: head };
  if (careful) return { word: "Careful", cls: "careful", over: a === "send" ? "Sent, with a warning" : "Changed, with a warning", line: head };
  if (a === "send") return { word: "Sent", cls: "send", over: "Unchanged", line: claims.length ? `${claims.length} of ${claims.length} number${claims.length > 1 ? "s" : ""} traced to the report` : "No number to check" };
  if (a === "repair") {
    const check = d.correct.rule && d.correct.rule.check, n = check && check.changes ? check.changes.length : 0, passed = check && check.checks ? check.checks.filter((c) => c.passed).length : 0;
    return { word: "Fixed", cls: "repair", over: "Changed and re-checked", line: check && check.checks ? `${n} ${n === 1 ? "change" : "changes"} · ${passed} of ${check.checks.length} checks passed` : head };
  }
  const why = L.whyHeld(d);
  return { word: "Withheld", cls: "abstain", over: "Not sent", line: (/^.*?[.](?:\s|$)/.exec(why) || [why])[0].trim() };
}
const cellsOf = (c) => (c.asked.length ? c.asked : c.cells);

// the sent text, or the answer, with each number marked and clickable
function finalText(d) {
  const a = d.output.action, rule = d.correct.rule;
  if (a === "repair" && rule && rule.check && rule.check.text) {
    const parts = []; let pos = 0;
    for (const c of rule.check.changes) {
      parts.push(rule.check.text.slice(pos, c.start), h("span", { class: "was" }, c.old),
        h("span", { class: "now", title: c.cells.map((id) => L.cellText(id, c.cell_labels[id])).join(" · "), onclick: () => look(c.cells) }, c.new));
      pos = c.end;
    }
    parts.push(rule.check.text.slice(pos));
    return parts;
  }
  const claims = [...d.catch.claims].sort((x, y) => x.start - y.start), parts = [];
  let pos = 0;
  for (const c of claims) {
    if (c.start < pos) continue;
    const mark = L.classOf(d, c);
    parts.push(d.answer.slice(pos, c.start), h("span", { class: `n ${mark}`, title: cellsOf(c).map((id) => L.cellText(id, c.cell_labels[id])).join(" · "), onclick: () => look(cellsOf(c)) }, d.answer.slice(c.start, c.end)));
    pos = c.end;
  }
  parts.push(d.answer.slice(pos));
  return parts;
}
function look(ids) {
  if (!stage || !ids.length || !stage.flyToCell(ids[0])) return;
  setView(null);
  if (ids.length > 1) stage.showOnly(ids);
}

// ---------------------------------------------------------------- the readout
function renderSteps() {
  return h("ol", { class: "steps" }, STEPS.map(([id, name]) => {
    const s = ui.steps[id] || {};
    return h("li", { class: s.state || "" }, s.mark ? pencil(s.mark) : h("span", {}), h("b", {}, name), h("span", { class: "num" }, s.text || ""));
  }));
}
function renderReadout() {
  const box = $("readout"), d = ui.data, kids = [], r = report();
  if (!ui.question && !ui.busy && !d) {
    kids.push(h("div", { class: "intro" }, h("h1", {}, "FaithGuard checks each number in an AI answer against the report’s tables."),
      r ? h("div", { class: "try" }, h("small", {}, "Try"), (r.suggestions || []).slice(0, 3).map((q) => h("button", { type: "button", onclick: () => { $("question").value = q; run(); } }, q))) : null));
  } else {
    if (ui.question) kids.push(h("div", { class: "asked" }, ui.question));
    kids.push(renderSteps());
    const place = !ui.playing && ui.station && ui.station !== "all" ? renderStation() : null;
    if (place) kids.push(place);
    else if (d && !ui.playing) {
      const c = called(d), a = d.output.action;
      const text = a === "abstain" ? "“I can't give a reliable answer to this from the report.”" : a === "send" || a === "repair" ? finalText(d) : d.output.text;
      kids.push(h("div", { class: "result" },
        h("div", { class: "over" }, c.over),
        h("div", { class: `word ${c.cls}` }, c.word),
        h("div", { class: "line" }, c.line),
        h("div", { class: "final" }, text),
        h("div", { class: "acts" },
          h("button", { onclick: () => openSheet("why") }, "Why"),
          h("button", { onclick: () => openSheet("plant") }, "Plant a mistake"),
          state.planted ? h("button", { onclick: backToOriginal }, "Original") : null,
          h("button", { onclick: replay }, "Replay")),
        h("div", { class: "foot" }, footLine(d))));
    }
  }
  box.replaceChildren(...kids);
}
function footLine(d) {
  const a = d.output.action;
  const live = ui.ms ? `Checked in ${ui.ms < 1000 ? `${Math.round(ui.ms)} ms` : `${(ui.ms / 1000).toFixed(1)} s`}. Real result, slowed here to watch.` : "";
  const fix = a === "repair" ? " Fix by the rule repairer; the tested system uses repairer v1." : "";
  return live + fix;
}
function step(id, st, text, mark) { ui.steps[id] = { ...(ui.steps[id] || {}), state: st, text: text ?? (ui.steps[id] || {}).text, mark: mark ?? (ui.steps[id] || {}).mark }; renderReadout(); }

// ---------------------------------------------------------------- the stations
function setView(name) {
  ui.station = name;
  for (const b of $("views").children) b.classList.toggle("on", b.dataset.view === name);
  if (name && stage) { stage.showOnly([]); stage.fly(name, 1.1); }
  renderReadout();
}
function renderStation() {
  const d = ui.data, name = ui.station, row = (k, v, cls) => [h("dt", {}, k), h("dd", { class: cls || null }, v)];
  if (name === "catch") {
    const counts = { ok: 0, bad: 0, unsure: 0 };
    if (d) d.catch.claims.forEach((c) => counts[L.classOf(d, c)]++);
    const a = d && d.catch.channel_a;
    return h("div", { class: "station" }, h("h2", {}, "1  Catch"), h("p", {}, "Traces every number to a table cell. Rules, no AI."),
      d ? h("dl", {}, row("Numbers", d.catch.claims.length), row("Traced", counts.ok, "pass"), row("Wrong", counts.bad, counts.bad ? "fail" : null), row("Not sure", counts.unsure),
        a && a.source ? row("Channel A, studied only", `${(a.spans || []).length} flagged`) : null) : null);
  }
  if (name === "control") {
    const o = d && d.control.outcome, word = { send: "Send", repair: "Fix", abstain: "Withhold" };
    return h("div", { class: "station" }, h("h2", {}, "2  Control"), h("p", {}, "Predicts the risk, then sends, fixes or withholds."),
      d && o ? h("dl", {}, row("P(unsafe)", o.p_unsafe.toFixed(2)), row("Send if below", o.tau_send), row("P(fix)", o.p_fix.toFixed(2)), row("Fix if above", o.tau_fix), row("Decision", word[d.control.action] || d.control.action)) : null,
      h("p", { class: "quiet" }, "Thresholds certified on practice data only. None certified on real answers."));
  }
  const rule = d && d.correct.rule, check = rule && rule.check, released = rule && !rule.not_released;
  return h("div", { class: "station" }, h("h2", {}, "3  Correct"), h("p", {}, "A small program changes only the wrong block. Code does the sum."),
    check && check.checks ? h("dl", {}, check.checks.map((c) => row(c.name[0].toUpperCase() + c.name.slice(1), c.passed ? "Pass" : "Fail", c.passed ? "pass" : "fail"))) : null,
    rule && rule.program.length ? h("div", { class: "prog" }, rule.program.filter((p) => p.op !== "KEEP").map((p) => h("div", {}, p.text))) : null,
    rule && !released ? h("p", { class: "quiet" }, "Not released: Control withheld this answer.") : null,
    ui.trained ? h("div", { class: "prog" }, h("b", {}, "Repairer v1: "), trainedText(ui.trained)) : null,
    d && d.correct.live_repairer && d.output.action !== "send" ? h("button", { onclick: runTrained }, "Run trained repairer v1") : null);
}
function trainedText(t) {
  if (t.error) return t.error;
  const edits = (t.program || []).filter((p) => p.op !== "KEEP").map((p) => p.text).join("  ");
  return `${edits || "no change"}. ${t.label}`;
}
async function runTrained() {
  const d = ui.data, seq = ui.seq;
  ui.trained = { label: "Running on the GPU…", program: [] }; renderReadout();
  const out = await api("/api/trained", { id: d.id, answer: d.edited ? d.answer : undefined }, 60);
  if (seq !== ui.seq) return;
  ui.trained = out; renderReadout();
}

// ---------------------------------------------------------------- the detail sheet
function openSheet(kind) {
  const d = ui.data, box = $("sheet");
  if (!d) return;
  const close = h("button", { class: "close", "aria-label": "Close", onclick: () => (box.hidden = true) }, "×");
  if (kind === "why") {
    const a = d.output.action, n = L.notes(d), v = L.verdict(d);
    box.replaceChildren(...[close, h("h2", {}, v.querySelector(".head").textContent),
      h("p", {}, v.querySelector(".sub").textContent),
      h("h3", {}, "Every number"), L.checkList(d),
      h("h3", {}, "The decision"), h("p", {}, a === "send" || a === "repair" ? L.decision(d) : L.whyHeld(d)),
      d.caption ? h("p", {}, d.caption) : null,
      ui.sourceNote ? h("p", {}, ui.sourceNote) : null,
      n.length ? [h("h3", {}, "Good to know"), h("p", {}, n.join(" "))] : null,
      a === "repair" ? [h("h3", {}, "Who fixed it"), h("p", {}, "The rule repairer (v0), on this laptop. The system we evaluated uses the trained repairer v1. On the locked test, with the rule checker's flags, the rule repairer added a new error to 6.2% of the answers it sent, v1 to 0.4%.")] : null].flat().filter(Boolean));
  } else {
    box.replaceChildren(close, h("h2", {}, "Plant a mistake"), ...plantBody());
  }
  box.hidden = false;
}
function plantBody() {
  const o = ui.original, t = ui.tricks, stop = (text) => [h("p", {}, text)];
  if (!o) return stop("Run a question first.");
  if (o.output.action === "abstain" && L.allChecked(o)) return stop("FaithGuard already held this answer back. Pick another question.");
  if (L.limited(o)) return stop("This answer runs into a known limitation, so a planted mistake would show nothing clear.");
  if (L.unknownLine(o) || (o.catch.claims.length && o.catch.claims.every((c) => c.verdict !== "supported" && (c.missing || c.verdict !== "unsupported" || L.cannotTrace(c))))) return stop("FaithGuard could not really check this answer, so a planted mistake would show nothing clear.");
  if (!t) return stop("Preparing mistakes…");
  if (L.has(o, L.NOTE.untrusted) && (t.on === "repaired" || (o.output.action === "repair" && !o.catch.claims.some((c) => c.verdict === "supported")))) return stop("FaithGuard's fix of this answer is not trustworthy, so a planted mistake would show nothing clear.");
  if (!t.edits.length) return stop(t.error ? `No mistakes could be prepared: ${t.error}` : "There is no correct number here to plant a mistake in.");
  return [h("p", {}, "These go only where the checker can see them, so catching them is by design. On 672 real AI answers it flagged 144 of the 170 wrong ones and 110 of the 502 right ones."),
    h("div", { class: "tricks" }, t.edits.map((e) => { const n = L.trickName(e.label); return h("button", { onclick: () => plant(e, n) }, n.title, h("span", {}, n.detail), e.expect === "send" ? h("em", {}, "FaithGuard misses this one") : null); }))];
}
async function plant(e, name) {
  if (ui.busy) return;
  $("sheet").hidden = true; ui.busy = true; updateRun();
  const start = performance.now();
  const data = await api("/api/run", { id: ui.original.id, answer: e.answer, channel_a: false });
  ui.ms = performance.now() - start; ui.busy = false;
  if (data.error) { toast(data.error); updateRun(); return; }
  state.planted = { title: name.title.toLowerCase(), kind: name.kind, answer: e.answer };
  await show(data);
}
function backToOriginal() { state.planted = null; ui.trained = null; show(ui.original); }
const replay = () => show(ui.data);

// ---------------------------------------------------------------- a run
function updateRun() { $("run").disabled = ui.busy || ui.playing; }
function readQuestion() { return $("question").value.trim(); }
async function run() {
  const r = report(), question = readQuestion();
  if (ui.busy || !r || !question) return;
  const seq = ++ui.seq;
  $("sheet").hidden = true; setView(null); ui.busy = true; ui.playing = false; updateRun();
  Object.assign(ui, { question, data: null, original: null, tricks: null, steps: {}, sourceNote: null, trained: null, ms: 0 });
  state.planted = null;
  if (stage) { stage.clearRun(); stage.fly("source", 0.9); }
  let answer, by = "Typed";
  if (ui.by === "mine") {
    answer = $("answer").value.trim();
    if (!answer) { ui.busy = false; updateRun(); toast("Type an answer first."); return; }
  } else {
    const t0 = performance.now(), timer = setInterval(() => { if (ui.by === "ai") step("ai", "now", `${((performance.now() - t0) / 1000).toFixed(1)} s`); }, 100);
    step("ai", "now", ui.by === "ai" ? "0.0 s" : "From the table");
    if (stage && ui.by === "ai") stage.thinking(true);
    const out = await api(ui.by === "ai" ? "/api/ask/ai" : "/api/ask/draft", { report: r.id, question }, ui.by === "ai" ? 90 : 30);
    clearInterval(timer);
    if (stage) stage.thinking(false);
    if (seq !== ui.seq) return;
    if (out.error) { ui.busy = false; ui.steps = {}; updateRun(); renderReadout(); toast(out.error); return; }
    answer = out.answer; ui.sourceNote = out.note || (out.source === "recorded" ? `The answer is ${out.by}.` : null);
    by = out.source === "recorded" ? "Recorded" : out.source === "ai" ? `${out.seconds} s live` : "Table";
    if (out.source === "recorded") refreshStatus();
  }
  step("ai", "on", by, "ok");
  const t1 = performance.now();
  const data = await api("/api/ask", { report: r.id, question, answer }, 60);
  ui.ms = performance.now() - t1;
  if (seq !== ui.seq) return;
  ui.busy = false;
  if (data.error) { ui.steps = {}; updateRun(); renderReadout(); toast(data.error); return; }
  ui.original = data;
  api("/api/plant", { id: data.id }, 60).then((t) => { if (seq === ui.seq) ui.tricks = t.error ? { edits: [], error: t.error } : t; });
  await show(data);
}

async function show(d) {
  ui.data = d; ui.playing = !!stage; ui.trained = null;
  const keep = ui.steps.ai;
  ui.steps = keep ? { ai: keep } : {};
  updateRun(); renderReadout();
  if (stage) {
    const marks = Object.fromEntries(d.catch.claims.map((c) => [c.id, L.classOf(d, c)]));
    const seen = { ok: 0, bad: 0, unsure: 0 }, word = { send: "Send", repair: "Fix", abstain: "Withhold" };
    await stage.play(d, { marks, on: (ev, x) => {
      if (ev === "catch-start") step("catch", "now", `${d.catch.claims.length} number${d.catch.claims.length === 1 ? "" : "s"}`);
      if (ev === "claim") { seen[x.mark]++; step("catch", "now", [seen.ok && `${seen.ok} traced`, seen.bad && `${seen.bad} wrong`, seen.unsure && `${seen.unsure} unsure`].filter(Boolean).join(" · ")); }
      if (ev === "control-start") { step("catch", "on", null, seen.bad ? "bad" : seen.unsure ? "unsure" : "ok"); step("control", "now", ""); }
      if (ev === "control") { const o = d.control.outcome; step("control", "on", `${word[x.action] || x.action}${o ? ` · risk ${o.p_unsafe.toFixed(2)}` : ""}`, x.action === "send" ? "ok" : x.action === "repair" ? "unsure" : "bad"); }
      if (ev === "correct-start") step("correct", "now", "");
      if (ev === "changed") step("correct", "now", `${x.index} changed`);
      if (ev === "gate") step("correct", "now", `Check ${x.index + 1} of 5`);
      if (ev === "exit-start" && ui.steps.correct) { const ok = d.output.action === "repair"; step("correct", "on", ok ? "Passed" : "Not released", ok ? "ok" : "bad"); }
      if (ev === "exit-start") step("out", "now", "");
    } });
    if (ui.data !== d) return;
  }
  const c = called(d);
  step("out", "on", c.word, d.output.action === "abstain" ? "bad" : c.cls === "careful" || c.cls === "missed" ? "unsure" : "ok");
  ui.playing = false; updateRun(); renderReadout();
}

// ---------------------------------------------------------------- the desk
function setBy(mode) {
  ui.by = mode;
  for (const b of $("by").children) b.classList.toggle("on", b.dataset.mode === mode);
  $("mine").hidden = mode !== "mine";
}
function setReport(id) {
  ui.seq++; ui.busy = false; ui.playing = false;
  state.report = id;
  const r = report();
  $("docname").textContent = r.name;
  $("menu").hidden = true; $("doc").setAttribute("aria-expanded", "false");
  if (stage) { stage.clearRun(); stage.setReport(r); stage.fly("all", 1); }
  Object.assign(ui, { question: "", data: null, original: null, tricks: null, steps: {} });
  state.planted = null; $("question").value = ""; $("sheet").hidden = true;
  setView(null); updateRun();
}
function renderMenu() {
  $("menu").replaceChildren(...state.reports.map((r) => h("button", { type: "button", role: "option", class: r.id === state.report ? "on" : null, onclick: () => setReport(r.id) }, r.name, r.real ? null : h("small", {}, "made up"))));
}
async function refreshStatus() {
  const s = await api("/api/status", null, 10), el = $("live");
  if (s.error) { el.className = "off"; el.replaceChildren(h("i"), "Server not answering"); }
  else {
    if (ui.runId === null) ui.runId = s.run_id || null;
    else if (s.run_id && s.run_id !== ui.runId) toast("The demo was restarted: reload the page.");
    const r = s.repairer || {};
    const [cls, text] = r.state === "ready" ? ["ready", "AI live on this laptop"] : r.state === "loading" ? ["wait", "AI loading"] : ["off", "AI off: recorded answers"];
    el.className = cls; el.replaceChildren(h("i"), h("span", { title: r.detail || null }, text));
  }
  clearTimeout(refreshStatus.t); refreshStatus.t = setTimeout(refreshStatus, s.repairer && s.repairer.state === "loading" ? 2000 : 10000);
}

$("views").replaceChildren(...VIEWS.map(([name, key, label]) => { const b = h("button", { onclick: () => { if (!ui.playing && !ui.busy) setView(name); } }, h("i", {}, key), label); b.dataset.view = name; return b; }));
$("by").replaceChildren(...[["ai", "AI writes it"], ["table", "From the table"], ["mine", "I type it"]].map(([mode, label]) => { const b = h("button", { type: "button", onclick: () => setBy(mode) }, label); b.dataset.mode = mode; return b; }));
setBy("ai");
$("ask").addEventListener("submit", (e) => { e.preventDefault(); run(); });
$("doc").addEventListener("click", () => { const m = $("menu"); m.hidden = !m.hidden; $("doc").setAttribute("aria-expanded", String(!m.hidden)); if (!m.hidden) renderMenu(); });
document.addEventListener("keydown", (e) => {
  if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) { if (e.key === "Escape") e.target.blur(); return; }
  const view = VIEWS.find(([, key]) => key === e.key);
  if (view && !ui.playing && !ui.busy) setView(view[0]);
  if (e.key === "Escape") { $("sheet").hidden = true; $("menu").hidden = true; }
  if ((e.key === "r" || e.key === "R") && ui.data && !ui.playing) replay();
  if (e.key === " " && ui.playing && stage) { e.preventDefault(); stage.pace = stage.pace > 2 ? 1.2 : 8; }
});
renderReadout(); refreshStatus();
const reports = await api("/api/reports", null, 120);
if (reports.error) toast(reports.error);
else {
  state.reports = reports;
  const first = reports.find((r) => r.id === "LK:TKYO") || reports.find((r) => r.real) || reports[0];
  setReport(first.id);
}
window.__stage = { ui, state, stage, run, show, L };  // for the browser checks
