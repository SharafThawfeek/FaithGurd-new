// FaithGuard Stage: the screens around the 3D model. Pick a document, ask, watch the real result go through the machine.
import { Stage } from "./scene.js";
import * as L from "./logic.js";

const { h, state } = L;
const $ = (id) => document.getElementById(id);
const ui = { by: "ai", busy: false, playing: false, data: null, original: null, question: "", sourceNote: null, tricks: null, steps: {}, ms: 0, station: null, runId: null, seq: 0, trained: null, failed: null };
let stage = null;
try { if (location.search.includes("flat")) throw new Error("asked for the flat page"); stage = new Stage($("stage")); } catch (err) { console.warn("3D is off:", err); document.body.classList.add("flat"); }

const STEPS = [["ai", "Answer"], ["catch", "Catch"], ["control", "Control"], ["correct", "Correct"], ["out", "Result"]];
const VIEWS = [["all", "0", "All"], ["catch", "1", "Catch"], ["control", "2", "Control"], ["correct", "3", "Correct"]];
const TICK = { ok: "M1.5 8.3Q4.4 10.3 6.4 13.7Q9.3 6.7 15 1.5", bad: "M3 3l10 10M13 3 3 13", unsure: "M8 12v.5M5 5a3 3 0 1 1 3 3v1.5", go: "M2 8h11M9 4l4 4-4 4" };
const COLOR = { ok: "var(--green)", bad: "var(--red)", unsure: "var(--ochre)", go: "var(--ink)" };
const ACT = { send: "Send", repair: "Fix", abstain: "Withhold" };
const NOW = { catch: "Looking up each number in the report.", control: "Limits certified on template answers only. None on real answers.", correct: "Rule repairer here. The tested system uses repairer v1." };
const GATE = { provenance: "From the right cells", closure: "Rates redone", envelope: "Nothing else changed", recheck: "Checker agrees", relevance: "Still on the line asked" };
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
  if (a === "repair" && !d.output.changed) return { word: "Sent", cls: "send", over: "Unchanged", line: "Control asked for a fix, but every number traced, so nothing changed" };
  if (state.planted && a === "send") return { word: "Missed", cls: "missed", over: "Sent with your planted mistake", line: head };
  if (careful) return { word: a === "send" ? "Sent" : "Changed", cls: "careful", over: "With a warning", line: L.unknownLine(d) ? `${head} So it could not really check the answer.` : head };
  if (a === "send") {
    const n = claims.length;
    return { word: "Sent", cls: "send", over: "Unchanged", line: n ? `${n} of ${n} number${n > 1 ? "s" : ""} traced to the report. Words not checked.` : "No number to check" };
  }
  if (a === "repair") {
    const check = d.correct.rule && d.correct.rule.check, passed = check && check.checks ? check.checks.filter((c) => c.passed).length : 0;
    return { word: "Fixed", cls: "repair", over: "Changed and re-checked", line: check && check.checks ? `${head} ${passed} of ${check.checks.length} own checks passed.` : head };
  }
  const why = L.whyHeld(d), raw = (/^.*?[.](?:\s|$)/.exec(why) || [why])[0].trim(), first = raw.replace(" (step 1 says which)", "");
  return { word: "Withheld", cls: "abstain", over: "Not sent", line: raw.includes("(step 1 says which)") ? `${first} The checker missed this; the safety rule held it back for its own reasons.` : first };
}
const cellsOf = (c) => c.asked;
const named = (c, ids, labels = c.cell_labels) => ids.map((id) => L.cellText(id, labels[id])).join(" · ");

// the sent text, or the answer, with each number marked and clickable
function finalText(d) {
  const a = d.output.action, rule = d.correct.rule;
  if (a === "repair" && rule && rule.check && rule.check.text && d.output.changed) {
    const sure = called(d).cls === "repair", parts = [];
    let pos = 0;
    for (const c of rule.check.changes) {
      parts.push(rule.check.text.slice(pos, c.start), h("span", { class: sure ? "was" : "was doubt" }, c.old),
        h("span", { class: sure ? "now" : "now doubt", title: named(c, c.cells), onclick: () => look(c.cells) }, c.new));
      pos = c.end;
    }
    parts.push(rule.check.text.slice(pos));
    return parts;
  }
  const spans = [];
  for (const c of d.catch.claims) {
    const mark = L.classOf(d, c);
    if (mark === "bad" && L.signOnly(c)) { spans.push({ start: c.direction_span[0], end: c.direction_span[1], cls: "bad", c }); spans.push({ start: c.start, end: c.end, cls: "", c }); }
    else spans.push({ start: c.start, end: c.end, cls: mark, c });
  }
  spans.sort((x, y) => x.start - y.start);
  const parts = [];
  let pos = 0;
  for (const s of spans) {
    if (s.start < pos) continue;
    parts.push(d.answer.slice(pos, s.start), h("span", { class: `n ${s.cls}`, title: named(s.c, cellsOf(s.c)), onclick: () => look(cellsOf(s.c)) }, d.answer.slice(s.start, s.end)));
    pos = s.end;
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
  if (!ui.question && !ui.busy && !d && !ui.failed) {
    kids.push(h("div", { class: "intro" }, h("h1", {}, "Every number in an AI answer, checked against the report. Then sent, fixed or withheld."),
      r ? h("div", { class: "try" }, h("small", {}, "Try"), (r.suggestions || []).slice(0, 3).map((q) => h("button", { type: "button", onclick: () => { $("question").value = q; run(); } }, q)),
        h("p", { class: "quiet" }, "Development reports: the rules were tuned on the five real ones. Two statements only, no notes. Try questions are pre-checked; yours and the AI's answers are not.")) : null));
  } else {
    if (ui.question) kids.push(h("div", { class: "asked" }, ui.question));
    if (ui.playing || ui.busy || ui.failed) kids.push(renderSteps());
    if (ui.failed) kids.push(h("div", { class: "failnote" }, ui.failed.msg, ui.failed.cut ? h("p", {}, `Not checked: ${ui.failed.cut}`) : null));
    const place = !ui.playing && ui.station && ui.station !== "all" ? renderStation() : null;
    if (place) kids.push(place);
    else if (ui.playing) {
      const id = ["correct", "control", "catch"].find((k) => ui.steps[k]);
      if (id) kids.push(h("div", { class: "result" }, h("div", { class: "word now" }, STEPS.find(([k]) => k === id)[1]), h("div", { class: "line" }, NOW[id]), h("div", { class: "foot" }, "Already decided. Slowed here to watch.")));
    } else if (d) kids.push(renderResult(d));
  }
  box.replaceChildren(...kids);
}
function renderResult(d) {
  const c = called(d), a = d.output.action, rule = d.correct.rule, notes = L.notes(d).length;
  const text = a === "abstain" ? "“I can't give a reliable answer to this from the report.”" : a === "send" || a === "repair" ? finalText(d) : d.output.text;
  const from = a === "repair" && rule && rule.check ? [...new Set((rule.check.changes || []).flatMap((x) => x.cells.map((id) => L.cellText(id, x.cell_labels[id]))))] : [];
  const over = state.planted && c.word !== "Missed" ? `Planted: ${state.planted.title}` : c.over;
  const plantNote = state.planted && c.word !== "Missed" ? ` Planted where the checker can see it, so caught by design.${ui.tricks && ui.tricks.on === "repaired" ? " Planted in FaithGuard's fixed answer." : ""}` : "";
  const beside = [!state.planted && ui.sourceNote, d.caption].filter(Boolean).join(" ");
  return h("div", { class: "result" },
    h("div", { class: "over" }, over),
    h("div", { class: `word ${c.cls}` }, c.word),
    h("div", { class: "line" }, c.line),
    h("div", { class: "final" }, text),
    from.length ? h("div", { class: "src" }, `From the report: ${from.join(" · ")}`) : null,
    beside ? h("div", { class: "foot" }, beside) : null,
    h("div", { class: "acts" },
      h("button", { onclick: () => openSheet("why") }, notes ? `Why · ${notes} note${notes > 1 ? "s" : ""}` : "Why"),
      h("button", { onclick: () => openSheet("plant") }, "Plant a mistake"),
      state.planted ? h("button", { onclick: backToOriginal }, "Original") : null,
      h("button", { onclick: replay }, "Replay")),
    h("div", { class: "foot" }, footLine(d) + plantNote));
}
function footLine(d) {
  const a = d.catch.channel_a, m = a && /took (\d+) ms/.exec(a.note || ""), ms = ui.ms - (m ? +m[1] : 0);
  const time = ui.ms ? `Decided in ${ms < 1000 ? `${Math.max(1, Math.round(ms))} ms` : `${(ms / 1000).toFixed(1)} s`}.` : "";
  const slow = stage ? " Real result, slowed here to watch." : "";
  const fix = d.output.action === "repair" && d.output.changed ? " Fix by the rule repairer (simple rules); the tested system uses the trained repairer v1." : "";
  return time + slow + fix;
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
    return h("div", { class: "station" }, h("h2", {}, "1  Catch"), h("p", {}, "Looks for every number in a table cell. Rules, no AI."),
      d ? h("dl", {}, row("Numbers", d.catch.claims.length), row("Traced", counts.ok, "pass"), row("Wrong", counts.bad, counts.bad ? "fail" : null), row("Not sure", counts.unsure),
        a && a.source && a.source !== "pending" ? row("Channel A, studied only", `${(a.spans || []).length} flagged`) : null) : null);
  }
  if (name === "control") {
    const o = d && d.control.outcome, needFix = o && o.p_unsafe >= o.tau_send;
    return h("div", { class: "station" }, h("h2", {}, "2  Control"), h("p", {}, "Scores the risk, then sends, fixes or withholds."),
      d && o ? h("dl", {}, row("Risk score", o.p_unsafe.toFixed(2)), row("Send if below", o.tau_send), needFix ? row("Fix score", o.p_fix.toFixed(2)) : null, needFix ? row("Fix if above", o.tau_fix) : null, row("Decision", ACT[d.control.action] || d.control.action)) : null,
      h("p", { class: "quiet" }, "Limits certified on template answers only. None on real answers."),
      h("p", { class: "quiet" }, "A model score, not a measured chance: on the locked test it was off by 0.33 on average."));
  }
  const rule = d && d.correct.rule, check = rule && rule.check, released = rule && !rule.not_released && d.output.action === "repair";
  return h("div", { class: "station" }, h("h2", {}, "3  Correct"), h("p", {}, "A small program changes only the blocks the checker flagged. Code does the sum."),
    check && check.checks ? h("dl", {}, check.checks.map((c) => row(GATE[c.name] || c.name, c.passed ? "Pass" : "Fail", c.passed ? "pass" : "fail"))) : null,
    rule && rule.program.length ? h("div", { class: "prog" }, h("b", {}, "Rule repairer's program: "), rule.program.filter((p) => p.op !== "KEEP").map((p) => h("div", {}, p.text))) : null,
    rule && !released ? h("p", { class: "quiet" }, rule.not_released ? "Not released: Control withheld this answer." : "Not released: the fix failed a check, so the answer is withheld.") : null,
    released ? h("p", { class: "quiet" }, "FaithGuard's own checks. The sent fix is the rule repairer's, not v1's. Passing does not prove a fix right.") : null,
    ui.trained ? h("div", { class: "prog" }, h("b", {}, "Repairer v1: "), trainedText(ui.trained)) : null,
    d && d.correct.live_repairer && d.output.action !== "send" && !(ui.trained && ui.trained.running) ? h("button", { onclick: runTrained }, "Run trained repairer v1") : null);
}
function trainedText(t) {
  if (t.running) return t.label;
  if (t.error) return t.error;
  const edits = (t.program || []).filter((p) => p.op !== "KEEP").map((p) => p.text).join("  ");
  const res = { repaired: "Passed its checks", gate_failed: "Rejected by the checks" }[t.status] || "No fix written";
  return `${edits || "no change"}. ${t.label}. ${res}. Not sent: the sent text is the rule repairer's.`;
}
async function runTrained() {
  const d = ui.data, seq = ui.seq;
  ui.trained = { running: true, label: "Running on the GPU…", program: [] }; renderReadout();
  const out = await api("/api/trained", { id: d.id, answer: d.edited ? d.answer : undefined }, 60);
  if (seq !== ui.seq || ui.data !== d) return;
  ui.trained = out; renderReadout();
}

// ---------------------------------------------------------------- the detail sheet
function openSheet(kind) {
  const d = ui.data, box = $("sheet");
  if (!d) return;
  const close = h("button", { class: "close", "aria-label": "Close", onclick: () => (box.hidden = true) }, "×");
  if (kind === "why") {
    const a = d.output.action, n = L.notes(d), v = L.verdict(d), c = called(d);
    box.replaceChildren(...[close, h("h2", {}, v.querySelector(".head").textContent),
      h("p", {}, v.querySelector(".sub").textContent),
      h("h3", {}, "Every number"), L.checkList(d),
      h("h3", {}, "The decision"), h("p", {}, a === "send" || a === "repair" ? L.decision(d) : L.whyHeld(d)),
      c.cls === "send" && d.catch.claims.length ? h("p", {}, "On 672 labelled answers the checker passed 26 of the 170 wrong ones.") : null,
      d.caption ? h("p", {}, d.caption) : null,
      ui.sourceNote ? h("p", {}, ui.sourceNote) : null,
      n.length ? [h("h3", {}, "Good to know"), h("p", {}, n.join(" "))] : null,
      a === "repair" ? [h("h3", {}, "Who fixed it"), h("p", {}, "The rule repairer (v0), on this laptop. The system we evaluated uses the trained repairer v1. On the locked test, with the rule checker's flags, both corrected about half of the 83 wrong answers (rule repairer 50.6%; v1 49.4% to 50.6%). The rule repairer added a new error to 6.2% of the answers it sent, v1 to 0.4%, and it also damaged 6.3% of the right ones, v1 none.")] : null].flat().filter(Boolean));
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
  const left = !t.dropped ? null : `${t.dropped} planted mistake${t.dropped > 1 ? "s" : ""} left out: ` + (t.on_wrong
    ? "FaithGuard reads a number in this answer as wrong, and its repair changes that one too, so a planted mistake would not show on its own."
    : "FaithGuard's repair would not give the right figures back (a known limitation).");
  if (!t.edits.length) return stop(t.error ? `No mistakes could be prepared: ${t.error}` : left || "There is no correct number here to plant a mistake in.");
  return [h("p", {}, "These go only where the checker can see them, so catching them is by design. On 672 labelled real AI answers it flagged 144 of the 170 labelled wrong and 110 of the 502 labelled right."),
    h("div", { class: "tricks" }, t.edits.map((e) => { const n = L.trickName(e.label); return h("button", { onclick: () => plant(e, n) }, n.title, h("span", {}, n.detail), e.expect === "send" ? h("em", {}, "FaithGuard misses this one") : null); })),
    left ? h("p", {}, left) : null].filter(Boolean);
}
async function plant(e, name) {
  if (ui.busy) return;
  const seq = ui.seq;
  $("sheet").hidden = true; ui.busy = true; updateRun();
  const start = performance.now();
  const data = await api("/api/run", { id: ui.original.id, answer: e.answer, channel_a: false });
  if (seq !== ui.seq) return;
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
  if (ui.by === "mine" && !$("answer").value.trim()) { toast("Type an answer first."); return; }
  document.activeElement.blur(); $("menu").hidden = true;
  const seq = ++ui.seq;
  $("sheet").hidden = true; setView(null); ui.busy = true; ui.playing = false; updateRun();
  Object.assign(ui, { question, data: null, original: null, tricks: null, steps: {}, sourceNote: null, trained: null, ms: 0, failed: null });
  state.planted = null;
  if (stage) { stage.clearRun(); stage.fly("source", 0.9); }
  let answer, by = "Typed";
  if (ui.by === "mine") answer = $("answer").value.trim();
  else {
    const t0 = performance.now(), timer = setInterval(() => { if (seq !== ui.seq) { clearInterval(timer); return; } if (ui.by === "ai") step("ai", "now", `${((performance.now() - t0) / 1000).toFixed(1)} s`); }, 100);
    step("ai", "now", ui.by === "ai" ? "0.0 s" : "Template");
    if (stage && ui.by === "ai") stage.thinking(true);
    const out = await api(ui.by === "ai" ? "/api/ask/ai" : "/api/ask/draft", { report: r.id, question }, ui.by === "ai" ? 70 : 30);
    clearInterval(timer);
    if (seq !== ui.seq) return;
    if (stage) stage.thinking(false, !out.error);
    if (out.error) { ui.busy = false; ui.steps = {}; ui.failed = { msg: out.error, cut: out.cut_text }; updateRun(); renderReadout(); return; }
    answer = out.answer; ui.sourceNote = out.note || (out.source === "recorded" ? `The answer is ${out.by}.` : null);
    by = out.source === "recorded" ? "Recorded" : out.source === "ai" ? `${out.seconds} s live` : "Template";
    if (out.source === "recorded") refreshStatus();
  }
  step("ai", "on", by);
  const t1 = performance.now();
  const data = await api("/api/ask", { report: r.id, question, answer }, 60);
  ui.ms = performance.now() - t1;
  if (seq !== ui.seq) return;
  ui.busy = false;
  if (data.error) { ui.steps = {}; ui.failed = { msg: data.error }; updateRun(); renderReadout(); return; }
  ui.original = data;
  api("/api/plant", { id: data.id }, 60).then((t) => { if (seq === ui.seq) ui.tricks = t.error ? { edits: [], error: t.error } : t; });
  await show(data);
}

async function show(d) {
  $("sheet").hidden = true; setView(null);
  ui.data = d; ui.playing = !!stage; ui.trained = null;
  const keep = ui.steps.ai, count = d.catch.claims.length;
  ui.steps = keep ? { ai: keep } : {};
  updateRun(); renderReadout();
  const c = called(d), sure = c.cls === "repair";
  if (stage) {
    const marks = Object.fromEntries(d.catch.claims.map((x) => [x.id, L.classOf(d, x)]));
    const spots = Object.fromEntries(d.catch.claims.map((x) => [x.id, marks[x.id] === "bad" && L.signOnly(x) ? x.direction_span[0] : x.start]));
    const links = Object.fromEntries(d.catch.claims.map((x) => { const guess = x.loose_match || ["share", "ratio"].includes(x.relation); return [x.id, marks[x.id] === "bad" && x.came_from.length && !guess && !x.same_cell && !state.planted ? x.came_from : x.asked]; }));
    const seen = { ok: 0, bad: 0, unsure: 0 };
    await stage.play(d, { marks, spots, links, tone: c.cls, word: c.word, on: (ev, x) => {
      if (ev === "catch-start") step("catch", "now", `${count} number${count === 1 ? "" : "s"}`);
      if (ev === "claim") { seen[x.mark]++; step("catch", "now", [seen.ok && `${seen.ok} traced`, seen.bad && `${seen.bad} wrong`, seen.unsure && `${seen.unsure} unsure`].filter(Boolean).join(" · ")); }
      if (ev === "control-start") { step("catch", "on", null, !count ? undefined : seen.bad ? "bad" : seen.unsure ? "unsure" : "ok"); step("control", "now", ""); }
      if (ev === "control") { const o = d.control.outcome; step("control", "on", `${ACT[x.action] || x.action}${o ? ` · score ${o.p_unsafe.toFixed(2)}` : ""}`, "go"); }
      if (ev === "correct-start") step("correct", "now", "");
      if (ev === "changed") step("correct", "now", `${x.index} changed`);
      if (ev === "gate") step("correct", "now", `${x.index + 1} of 5 · ${x.check ? GATE[x.check.name] || x.check.name : ""}`);
      if (ev === "exit-start" && ui.steps.correct) { const ok = d.output.action === "repair"; step("correct", "on", !ok ? "Not released" : d.output.changed ? "Passed own checks" : "Nothing to change", !ok ? "bad" : sure ? "ok" : "unsure"); }
      if (ev === "exit-start" && !ui.steps.correct) step("correct", "", "Skipped");
      if (ev === "exit-start") step("out", "now", "");
    } });
    if (ui.data !== d) return;
  } else {
    step("catch", "on", `${count} number${count === 1 ? "" : "s"}`);
    step("control", "on", ACT[d.control.action] || d.control.action, "go");
    if (d.control.action === "repair") step("correct", "on", d.output.action === "repair" ? "Passed own checks" : "Not released");
  }
  step("out", "on", c.word, d.output.action === "abstain" || c.cls === "careful" || c.cls === "missed" ? "unsure" : "ok");
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
  Object.assign(ui, { question: "", data: null, original: null, tricks: null, steps: {}, failed: null });
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
    const [cls, text] = r.state === "ready" ? ["ready", "Qwen3.5-2B live on this laptop"] : r.state === "loading" ? ["wait", "AI loading"] : ["rec", "Recorded answers"];
    el.className = cls; el.replaceChildren(h("i"), h("span", { title: r.detail || null }, text));
  }
  clearTimeout(refreshStatus.t); refreshStatus.t = setTimeout(refreshStatus, s.repairer && s.repairer.state === "loading" ? 2000 : 10000);
}

$("views").replaceChildren(...VIEWS.map(([name, key, label]) => { const b = h("button", { onclick: () => { if (!ui.playing && !ui.busy) setView(name); } }, h("i", {}, key), label); b.dataset.view = name; return b; }));
$("by").replaceChildren(...[["ai", "AI writes it"], ["table", "Template from the table"], ["mine", "I type it"]].map(([mode, label]) => { const b = h("button", { type: "button", onclick: () => setBy(mode) }, label); b.dataset.mode = mode; return b; }));
setBy("ai");
$("ask").addEventListener("submit", (e) => { e.preventDefault(); run(); });
$("doc").addEventListener("click", () => { const m = $("menu"); m.hidden = !m.hidden; $("doc").setAttribute("aria-expanded", String(!m.hidden)); if (!m.hidden) renderMenu(); });
document.addEventListener("keydown", (e) => {
  if (/^(INPUT|TEXTAREA)$/.test(e.target.tagName)) { if (e.key === "Escape") e.target.blur(); return; }
  const view = VIEWS.find(([, key]) => key === e.key);
  if (view && !ui.playing && !ui.busy) setView(view[0]);
  if (e.key === "Escape") { $("sheet").hidden = true; $("menu").hidden = true; }
  if ((e.key === "r" || e.key === "R") && ui.data && !ui.playing && !ui.busy) replay();
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
