// FaithGuard demo UI: pick an example, walk Catch -> Control -> Correct -> Output, or edit the answer.
"use strict";

const STEPS = [
  { key: "catch", n: "Step 1", name: "Catch", who: "detection · M.L Ahamed" },
  { key: "control", n: "Step 2", name: "Control", who: "decision policy · Sharaf" },
  { key: "correct", n: "Step 3", name: "Correct", who: "repair · M.S.A Ahamed" },
  { key: "output", n: "Result", name: "Output", who: "what the user sees" },
];
const VERDICT_ICON = { supported: "✓", unsupported: "✗", unverifiable: "?" };
const ACTION_WORD = { send: "SEND", repair: "REPAIR", abstain: "ABSTAIN" };

const state = { examples: [], current: null, data: null, step: 0, claim: null, showAll: {}, view: "case",
                runSeq: 0, loadSeq: 0, timer: null, resultsTab: "main", results: null, trainedLive: {}, modelStates: {},
                reports: null, ask: { report: null, question: "", answer: "", busy: null, allItems: false, tables: false }, asked: [] };

// ---------------------------------------------------------------- helpers
function h(tag, attrs, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k === "html") el.innerHTML = v;
    else el.setAttribute(k, v === true ? "" : v);
  }
  put(el, ...kids);
  return el;
}
function put(el, ...kids) {  // append, skipping null/undefined/false (so nothing prints "null")
  for (const kid of kids.flat(Infinity)) {
    if (kid === null || kid === undefined || kid === false) continue;
    el.append(kid instanceof Node ? kid : document.createTextNode(String(kid)));
  }
  return el;
}
const pct = (x, d = 1) => (x === null || x === undefined ? "–" : (100 * x).toFixed(d) + "%");
const fmt = (x, d = 3) => (x === null || x === undefined ? "–" : Number(x).toFixed(d));
async function api(path, body) {
  try {
    const res = await fetch(path, body ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {});
    return await res.json();
  } catch {
    return { error: "The demo server did not answer. Is it still running?" };
  }
}
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(toast.t); toast.t = setTimeout(() => (t.hidden = true), 4000);
}
function badge(action, big) { return h("span", { class: `badge ${action}${big ? " big" : ""}` }, ACTION_WORD[action] || action); }
function srcTag(source, text) {
  const cls = source === "live" ? "live" : source ? "stored" : "";
  return h("span", { class: `src ${cls}` }, text);
}
function cellTag(id, label, kind) {
  const mark = kind === "asked" ? "✓ " : kind === "from" ? "✗ " : "";
  return h("span", { class: `celltag ${kind}`, title: id }, mark, label || id);
}

// ---------------------------------------------------------------- status bar
async function refreshStatus() {
  const s = await api("/api/status");
  if (s.error) return;
  const n = s.examples || 0;
  const pill = (name, st, stored) => {
    let text;
    if (st.state === "ready") text = (st.detail || "").replace(/ \(loaded.*$/, "");
    else if (st.state === "loading") text = "loading…";
    else text = `stored outputs for ${stored} of ${n}`;
    return h("span", { class: "pill", title: st.detail || "" }, h("span", { class: `dot ${st.state}` }), h("b", {}, name), text);
  };
  document.getElementById("status").replaceChildren(
    s.version ? h("span", { class: "pill", title: "the code this server runs" }, h("b", {}, "code"), s.version) : null,
    h("span", { class: "pill" }, h("span", { class: "dot ready" }), h("b", {}, "Channel B"), "rules, live"),
    pill("Channel A", s.channel_a, s.stored.channel_a),
    h("span", { class: "pill", title: s.policy.detail }, h("span", { class: `dot ${s.policy.state}` }), h("b", {}, "Policy"),
      s.policy.state === "ready" ? "LightGBM, live" : "trained policy missing: threshold v0"),
    pill("Trained repairer", s.repairer, s.stored.repairer),
  );
  const before = state.modelStates;
  state.status = s;
  state.modelStates = { a: s.channel_a.state, r: s.repairer.state };
  const becameReady = ["a", "r"].some((k) => before[k] === "loading" && state.modelStates[k] === "ready");
  if (state.view === "ask") updateAskButtons();
  if (becameReady && state.view === "case" && state.current) {
    if (state.data && !state.data.edited && document.activeElement.id !== "answerbox") loadCase(state.current, { keepStep: true });
    else toast("A trained model is now live: re-select the example to use it.");
  }
  if (s.channel_a.state === "loading" || s.repairer.state === "loading") setTimeout(refreshStatus, 2000);
}

// ---------------------------------------------------------------- sidebar
function renderSidebar() {
  const groups = [["fictional", "Fictional bank (made-up figures)"], ["pilot", "Real AI answers (pilot, development)"]];
  const side = document.getElementById("sidebar");
  side.replaceChildren();
  side.append(h("h3", {}, "Your own question"));
  side.append(h("button", { class: `ex cta${state.view === "ask" ? " active" : ""}`, onclick: showAsk },
    h("span", { class: "t" }, "Ask your own question ▶"),
    h("span", { class: "c" }, "any question on a real report: an AI (or you) answers, FaithGuard checks it")));
  for (const a of state.asked.slice(0, 8)) {
    const active = state.view === "case" && state.current === a.id;
    side.append(h("button", { class: `ex asked${active ? " active" : ""}`, onclick: () => selectExample(a.id), title: a.question },
      h("span", { class: "t" }, h("span", { class: "q" }, a.question), a.action ? badge(a.action) : null),
      h("span", { class: "c" }, `${a.report} · ${a.by}`)));
  }
  let n = 0;
  for (const [g, title] of groups) {
    const items = state.examples.filter((e) => e.group === g);
    if (!items.length) continue;
    side.append(h("h3", {}, title));
    for (const e of items) {
      n += 1;
      const active = state.view === "case" && state.current === e.id;
      side.append(h("button", { class: `ex${active ? " active" : ""}`, onclick: () => selectExample(e.id), title: e.id },
        h("span", { class: "t" }, h("span", {}, `${n}. ${e.title}`), e.expect ? badge(e.expect) : null),
        h("span", { class: "c" }, e.group === "pilot" ? `${e.country === "LK" ? "Sri Lankan" : "US"} report · ${e.id}` : e.caption)));
    }
  }
  if (!state.examples.some((e) => e.group === "pilot")) {
    side.append(h("p", { class: "note", style: "margin:8px" }, "Real pilot answers appear here when data/demo/examples.json and the pilot data are on this laptop (see demo/README.md)."));
  }
  side.append(h("h3", {}, "Evaluation"));
  side.append(h("button", { class: `ex${state.view === "results" ? " active" : ""}`, onclick: showResults },
    h("span", { class: "t" }, "Results"), h("span", { class: "c" }, "the locked test (D-113), then the development tables")));
}

function selectExample(id) {
  state.view = "case";
  state.claim = null;
  state.showAll = {};
  state.runSeq++;
  clearTimeout(state.timer);
  loadCase(id, {});
}

// Load an example: its original answer unless `answer` is given.
async function loadCase(id, { keepStep = false, answer = null } = {}) {
  const seq = ++state.loadSeq;
  state.current = id;
  if (!keepStep) state.step = 0;
  renderSidebar();
  const main = document.getElementById("main");
  main.classList.add("busy");
  const data = answer ? await api("/api/run", { id, answer }) : await api(`/api/case?id=${encodeURIComponent(id)}`);
  if (seq !== state.loadSeq) return;  // a newer selection won
  main.classList.remove("busy");
  if (data.error) { toast(data.error); return; }
  state.data = data;
  if (!keepStep || !data.catch.claims.some((c) => c.id === state.claim)) state.claim = firstClaim(data);
  render();
  if (data.group === "ask" && !data.planted) fetchPlanted(data.id);
}

function firstClaim(data) {
  const bad = data.catch.claims.find((c) => c.verdict !== "supported");
  return (bad || data.catch.claims[0] || {}).id || null;
}

// ---------------------------------------------------------------- try-it box
function scheduleRun(text) {
  clearTimeout(state.timer);
  const id = state.current;
  state.timer = setTimeout(() => runEdited(text, id), 450);
}

async function runEdited(text, id = state.current) {
  const seq = ++state.runSeq;
  const started = performance.now();
  const data = await api("/api/run", { id, answer: text, channel_a: false });
  if (seq !== state.runSeq || id !== state.current) return;  // stale: the presenter typed on or switched examples
  const errBox = document.getElementById("tryerr");
  if (data.error) {
    if (errBox) { errBox.textContent = data.error; errBox.hidden = false; }
    document.getElementById("panel")?.classList.add("stale");
    return;
  }
  data.ms = Math.round(performance.now() - started);
  state.data = data;
  const current = data.catch.claims.find((c) => c.id === state.claim);
  if (!current || current.verdict === "supported") state.claim = firstClaim(data);
  render({ keepTextarea: true });
  // Channel A follows when it is live, so the pipeline's answer never waits for it
  if (data.catch.channel_a && data.catch.channel_a.source === "pending") {
    const a = await api("/api/channel-a", { id, answer: text });
    if (seq !== state.runSeq || id !== state.current) return;
    state.data.catch.channel_a = a.error ? { source: null, note: a.error } : a;
    render({ keepTextarea: true });
  }
}

function useEdit(text) {
  const box = document.getElementById("answerbox");
  if (box) box.value = text;
  clearTimeout(state.timer);
  runEdited(text);
}

function resetAnswer() {
  state.runSeq++;
  clearTimeout(state.timer);
  loadCase(state.current, { keepStep: true });
}

// ---------------------------------------------------------------- main render
function render(opts = {}) {
  const main = document.getElementById("main");
  const d = state.data;
  if (!d) return;
  const box = document.getElementById("answerbox");
  const focused = document.activeElement === box && box;
  const caret = focused ? [box.selectionStart, box.selectionEnd] : null;

  let qa = document.getElementById("qa");
  if (!opts.keepTextarea || !qa) {
    qa = renderQA(d);
  } else {
    // keep the textarea (and the presenter's cursor) while the result below changes
    document.getElementById("tryrow").replaceChildren(...tryRowKids(d));
    document.getElementById("tryerr").hidden = true;
    document.getElementById("caveats").replaceChildren(...caveatList(d));
  }
  const panel = h("div", { id: "panel" }, [renderCatch, renderControl, renderCorrect, renderOutput][state.step](d));
  const nav = h("div", { class: "nav" },
    h("button", { class: "btn", onclick: () => go(state.step - 1), disabled: state.step === 0 }, "◀ Previous"),
    h("button", { class: "btn primary", onclick: () => go(state.step + 1), disabled: state.step === 3 }, "Next step ▶"));
  main.replaceChildren(qa, renderSteps(d), panel, nav);
  if (focused) {
    const again = document.getElementById("answerbox");
    again.focus();
    if (caret) again.setSelectionRange(caret[0], caret[1]);
  }
}

function go(step) {
  if (step < 0 || step > 3 || !state.data) return;
  state.step = step;
  render({ keepTextarea: true });
  const bar = document.querySelector(".steps");
  if (bar && bar.getBoundingClientRect().top < 0) bar.scrollIntoView({ block: "start" });
}

function renderQA(d) {
  const q = d.question;
  const box = h("textarea", { id: "answerbox", spellcheck: "false", "aria-label": "Answer to check",
    oninput: (ev) => scheduleRun(ev.target.value),
    onkeydown: (ev) => { if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); clearTimeout(state.timer); runEdited(ev.target.value); } } });
  box.value = d.answer;
  const asked = d.group === "ask";
  const where = asked && d.report ? `${d.report.name}${d.report.real ? " · real annual report" : ""}` : `${q.country === "LK" ? "Sri Lanka" : "US"} · ${q.issuer}`;
  return h("section", { class: `card qa${asked ? " asked" : ""}`, id: "qa" },
    h("div", { class: "meta" },
      h("span", {}, asked ? "Your question" : d.group === "pilot" ? "Real AI answer (pilot, development)" : "Fictional bank, made-up figures"),
      h("span", {}, where),
      d.generator ? h("span", {}, `answer by: ${d.generator}`) : null,
      asked ? h("button", { class: "btn small", onclick: showAsk }, "◀ Ask another question") : null),
    h("div", { class: "question" }, q.text),
    d.caption ? h("div", { class: "caption" }, d.caption) : null,
    h("div", { id: "caveats" }, caveatList(d)),
    h("div", { class: "tryit" },
      h("label", { for: "answerbox" }, "Answer · try it yourself: edit the text and the pipeline reruns"),
      box,
      asked ? plantedChips(d)
        : d.edits && d.edits.length ? h("div", { class: "chips" }, h("span", { class: "note" }, "Pre-checked edits: "),
          d.edits.map((e) => h("button", { class: "chip", title: e.answer, onclick: () => useEdit(e.answer) }, e.label, " → ", badge(e.expect)))) : null,
      h("div", { class: "row", id: "tryrow" }, ...tryRowKids(d)),
      h("div", { class: "err", id: "tryerr", hidden: true })));
}

function caveatList(d) {
  return (d.caveats || []).map((c) => h("div", { class: "caveat" }, h("b", {}, "Known limitation: "), c));
}

function plantedChips(d) {
  const label = h("span", { class: "note" }, d.planted_on === "repaired" ? "Plant an error in FaithGuard's repaired answer: " : "Plant an error in the original answer: ");
  if (!d.planted) return h("div", { class: "chips", id: "planted" }, label, h("span", { class: "spin" }), h("span", { class: "note" }, " finding errors to plant…"));
  if (d.plantError) return h("div", { class: "chips", id: "planted" }, label, h("span", { class: "note" }, d.plantError));
  if (!d.edits.length) return h("div", { class: "chips", id: "planted" }, label,
    h("span", { class: "note" }, "none: no number in the original answer is supported by a cell (it is already wrong, or has no number)."));
  return h("div", { class: "chips", id: "planted" }, label,
    d.edits.map((e) => h("button", { class: "chip plant", title: e.answer, onclick: () => useEdit(e.answer) }, e.label, " → ", badge(e.expect))),
    d.planted_dropped ? h("span", { class: "note" }, `(${d.planted_dropped} more left out: their repair does not give the right figures back, a known limitation)`) : null);
}

async function fetchPlanted(id) {
  const r = await api("/api/plant", { id });
  if (!state.data || state.data.id !== id) return;
  state.data.edits = r.error ? [] : r.edits;
  state.data.plantError = r.error || null;
  state.data.planted_on = r.on || "original";
  state.data.planted_dropped = r.dropped || 0;
  state.data.planted = true;
  const old = document.getElementById("planted");
  if (old) old.replaceWith(plantedChips(state.data));
}

function tryRowKids(d) {
  return [
    h("button", { class: "btn", onclick: resetAnswer, disabled: !d.edited }, "Reset to the original answer"),
    d.edited ? h("span", { class: "edited-tag" }, `Edited · live pipeline reran${d.ms ? ` in ${d.ms} ms` : ""}`)
      : h("span", {}, "Channel B, the policy, the rule repairer, executor and gate run live on every edit (Ctrl+Enter runs at once)."),
  ];
}

function correctSummary(d) {
  const rule = d.correct.rule;
  if (d.control.action === "send") return "not needed";
  if (d.control.action === "repair") return rule && rule.status === "repaired" ? "fixed, gate passed" : "gate rejected the fix";
  return rule && rule.status === "cannot_fix" ? "CANNOT_FIX (for comparison)" : "withheld";
}

function renderSteps(d) {
  const claims = d.catch.claims;
  const bad = claims.filter((x) => x.verdict !== "supported").length;
  const sums = [
    h("span", { class: "sum" }, claims.length ? `${claims.length - bad} of ${claims.length} numbers supported` : "no numbers found"),
    h("span", { class: "sum" }, badge(d.control.action), " ", d.control.outcome ? `P(unsafe) ${fmt(d.control.outcome.p_unsafe, 2)}` : ""),
    h("span", { class: "sum" }, correctSummary(d)),
    h("span", { class: "sum" }, badge(d.output.action),
      " ", d.output.action === "repair" ? "fixed answer" : d.output.action === "send" ? "original answer" : "evidence + reason"),
  ];
  return h("nav", { class: "steps", "aria-label": "Pipeline steps" }, STEPS.map((s, i) =>
    h("button", { class: `step${i === state.step ? " active" : ""}`, onclick: () => go(i) },
      h("div", { class: "n" }, `${s.n} `, h("span", { class: "who" }, `· ${s.who}`)),
      h("div", { class: "name" }, s.name, i < 3 ? " →" : ""), sums[i])));
}

// ---------------------------------------------------------------- step 1: Catch
function annotated(text, claims, onClick) {
  const parts = [];
  let pos = 0;
  for (const c of [...claims].sort((a, b) => a.start - b.start)) {
    parts.push(text.slice(pos, c.start));
    parts.push(h("span", { class: `claim ${c.verdict}${c.id === state.claim ? " sel" : ""}`, title: `${c.id}: ${c.verdict}`,
      onclick: () => onClick(c.id) }, text.slice(c.start, c.end), h("span", { class: "ic" }, VERDICT_ICON[c.verdict])));
    pos = c.end;
  }
  parts.push(text.slice(pos));
  return h("div", { class: "answer-text" }, parts);
}

function renderCatch(d) {
  const claims = d.catch.claims;
  const sel = claims.find((c) => c.id === state.claim);
  const pick = (id) => { state.claim = id; render({ keepTextarea: true }); };
  const left = h("section", { class: "card" },
    h("h2", {}, "Channel B · rule checker ", srcTag("live", "live")),
    claims.length ? annotated(d.answer, claims, pick) : h("p", { class: "note" }, "No number in this answer, so nothing can be traced."),
    h("div", { class: "legend" },
      h("span", {}, h("span", { class: "sw", style: "background:var(--good-soft)" }), "✓ supported"),
      h("span", {}, h("span", { class: "sw", style: "background:var(--bad-soft)" }), "✗ unsupported"),
      h("span", {}, h("span", { class: "sw", style: "background:var(--warn-soft)" }), "? unverifiable"),
      h("span", {}, `risk = ${fmt(d.catch.risk, 2)}`), claims.length ? h("span", {}, "click a number for its trace") : null),
    sel ? claimDetail(sel) : null);
  const right = h("section", { class: "card" }, channelA(d));
  return h("div", {}, h("div", { class: "grid2" }, left, right), evidence(d, sel), passages(d));
}

function claimDetail(c) {
  const ctx = c.intended || {};
  const about = [ctx.entity, ctx.metric, ctx.period && (ctx.base_period ? `${ctx.base_period} → ${ctx.period}` : ctx.period)].filter(Boolean).join(" · ") || "(not recognised)";
  const rows = [
    ["Verdict", h("span", { class: `verdict ${c.verdict}` }, `${VERDICT_ICON[c.verdict]} ${c.verdict}`)],
    ["Failing slot", c.slots.length ? c.slots.map((s) => h("span", { class: "slot bad" }, s)) : "none"],
    ["About", about],
  ];
  if (c.verdict === "supported") {
    rows.push(["Traced to", c.asked.length ? c.asked.map((id) => cellTag(id, c.cell_labels[id], "asked")) : "–"]);
  } else if (c.same_cell) {
    rows.push(["Number came from", c.came_from.map((id) => cellTag(id, c.cell_labels[id], "both")), h("div", { class: "note" }, c.misread || "the right cells, read wrongly")]);
  } else {
    rows.push(["Asked for", c.asked.length ? c.asked.map((id) => cellTag(id, c.cell_labels[id], "asked"))
      : c.missing ? "not in the evidence" : "not identified by the rule checker"]);
    rows.push([c.loose_match ? "Closest match found" : "Number came from",
      c.came_from.length ? c.came_from.map((id) => cellTag(id, c.cell_labels[id], "from")) : "no cell matches it",
      c.loose_match ? h("div", { class: "note" }, `the checker's best match (${c.relation} of these cells); it can be a coincidence`) : null]);
  }
  if (c.verdict !== "supported" && c.expected) rows.push(["Evidence supports", h("b", {}, c.expected), c.fix ? h("code", { style: "margin-left:8px" }, c.fix) : null]);
  return h("div", {}, h("h4", {}, `Claim ${c.id}: “${c.text}”`),
    h("dl", { class: "detail" }, rows.map(([k, ...v]) => [h("dt", {}, k), h("dd", {}, v)])));
}

function channelA(d) {
  const a = d.catch.channel_a || {};
  const label = { live: "live", laptop: "precomputed on this laptop", "kaggle-spans": "precomputed on Kaggle", pending: "computing…" }[a.source] || "not available";
  const head = h("h2", {}, "Channel A · trained detector ", srcTag(a.source === "live" ? "live" : a.source && a.source !== "pending" ? "stored" : "", label));
  const sub = h("div", { class: "note" }, "Fine-tuned LettuceDetect v2 mmBERT (307M) with a slot head: P(unsupported) for every answer token, and the relation it most likely breaks.");
  const caveat = h("p", { class: "note" }, "On its own Channel A raises many false alarms (52% of clean development answers; Results). It is shown beside the rules: the decision uses Channel B's checks.");
  if (!a.tokens) return [head, sub, h("p", { class: "note" }, a.note || ""), caveat];
  const text = d.answer;
  const parts = [];
  let pos = 0;
  for (const [s, e, p, slot] of a.tokens) {
    if (s < pos) continue;
    parts.push(text.slice(pos, s));
    const alpha = Math.min(0.9, 0.04 + 0.86 * p);
    parts.push(h("span", { class: `tok${p >= a.threshold ? " flag" : ""}`, style: `background: rgba(var(--heat), ${alpha.toFixed(3)})`,
      title: `P(unsupported) = ${p.toFixed(3)}${slot ? ` · slot: ${slot}` : ""}` }, text.slice(s, e)));
    pos = e;
  }
  parts.push(text.slice(pos));
  const spans = a.spans || [];
  const kaggle = a.source === "kaggle-spans";
  return [head, sub, h("div", { class: "heat", style: "margin-top:6px" }, parts),
    h("div", { class: "legend" }, kaggle ? h("span", {}, "flagged spans only (token probabilities were not stored)")
      : [h("span", {}, "P(unsupported) 0 ", h("span", { class: "scale" }), " 1"), h("span", {}, `flagged ≥ ${a.threshold} (underlined)`), h("span", {}, "hover a word for its probability")]),
    h("h4", {}, "Flagged spans and the slot head's guess"),
    spans.length ? h("ul", { class: "spans" }, spans.map((s) => h("li", {}, h("b", {}, `“${s.text.trim()}”`), ` ${fmt(s.score, 2)} `, h("span", { class: "slot" }, s.slot))))
      : h("p", { class: "note" }, "Nothing flagged: no token reaches the threshold."),
    h("p", { class: "note" }, a.note || ""), caveat];
}

function evidence(d, sel) {
  const marks = {};
  for (const c of d.catch.claims) for (const id of c.cells) marks[id] = marks[id] || "other";
  if (sel) {
    for (const id of sel.asked) marks[id] = "asked";
    for (const id of sel.came_from) marks[id] = marks[id] === "asked" ? "both" : "from";
  }
  const card = h("section", { class: "card evidence" }, h("h2", {}, "Evidence ",
    h("span", { class: "note" }, sel ? `· cells behind “${sel.text}”` : "")),
    h("div", { class: "legend", style: "margin:0 0 6px" },
      h("span", {}, h("span", { class: "sw", style: "background:var(--good-soft);border-color:var(--good)" }), "✓ asked-for cell (what the question needs)"),
      h("span", {}, h("span", { class: "sw", style: "background:var(--bad-soft);border-color:var(--bad)" }), "✗ the cell the number came from"),
      h("span", {}, h("span", { class: "sw", style: "background:var(--good-soft);border:2px dashed var(--bad)" }), "both: the right cell, read wrongly"),
      h("span", {}, h("span", { class: "sw", style: "background:var(--surface);box-shadow:inset 0 -2px 0 #b9b8b2" }), "traced by another number")));
  const hidden = [];
  for (const t of d.evidence.tables) {
    const el = table(t, marks);
    if (el) card.append(el); else hidden.push(t);
  }
  if (hidden.length) {
    card.append(h("p", { class: "note" }, "Also in the evidence: ", hidden.map((t, i) => [i ? " · " : "", `${t.id} ${t.title || "table"} (${t.rows.length} rows) `,
      h("button", { class: "btn small", onclick: () => { state.showAll[t.id] = true; render({ keepTextarea: true }); } }, "show")])));
  }
  return card;
}

function table(t, marks) {
  const all = state.showAll[t.id];
  const hit = new Set(t.rows.filter((r) => r.cells.some((c) => c && marks[c.id])).map((r) => r.row));
  const many = t.rows.length > 14;
  const shown = all || !many ? t.rows : t.rows.filter((r) => hit.has(r.row));
  if (!shown.length) return null;
  const unit = { 3: "thousands", 6: "millions", 9: "billions" }[t.scale];
  const title = h("div", { class: "tabletitle" }, `${t.id}: ${t.title || "table"}`,
    h("span", { class: "note" }, [unit ? ` · amounts in ${unit}` : "", t.currency ? ` · ${t.currency}` : "", t.page ? ` · page ${t.page}` : "",
      many ? ` · showing ${shown.length} of ${t.rows.length} rows ` : ""].join("")),
    many ? h("button", { class: "btn small", onclick: () => { state.showAll[t.id] = !all; render({ keepTextarea: true }); } },
      all ? "show the traced rows" : "show all rows") : null);
  const body = [];
  const gap = () => h("tr", { class: "gap" }, h("td", { colspan: t.columns.length + 1 }, "⋯"));
  let last = all || !many ? null : t.rows[0].row - 1;
  for (const r of shown) {
    if (last !== null && r.row > last + 1) body.push(gap());
    body.push(h("tr", {}, h("td", { class: "lab" }, r.label),
      r.cells.map((c) => c ? h("td", { class: `cell ${marks[c.id] || ""}`, title: c.id },
        marks[c.id] === "asked" ? "✓ " : marks[c.id] === "from" ? "✗ " : "", c.text, h("span", { class: "cid" }, c.id)) : h("td", {}))));
    last = r.row;
  }
  if (!all && many && last !== t.rows[t.rows.length - 1].row) body.push(gap());
  return h("div", {}, title, h("div", { class: "tablewrap" }, h("table", { class: "ev" },
    h("thead", {}, h("tr", {}, h("th", { class: "lab" }, ""), t.columns.map((c) => h("th", {}, c.label)))), h("tbody", {}, body))));
}

function passages(d) {
  if (!d.evidence.passages.length) return null;
  return h("section", { class: "card" }, h("h2", {}, "Text passages"),
    d.evidence.passages.map((p) => h("p", {}, h("b", {}, `${p.id}: `), p.text)));
}

// ---------------------------------------------------------------- step 2: Control
const YES_NO = new Set(["evidence_sufficient", "answers_question"]);

function renderControl(d) {
  const c = d.control;
  const o = c.outcome;
  const cert = c.certificate || {};
  const feats = h("section", { class: "card" }, h("h2", {}, "Pre-action features"),
    h("p", { class: "note" }, "Only what is known before acting: the detector's output and the evidence. No gold, nothing from a repair attempt."),
    h("table", { class: "feat" }, c.features.map((f) => h("tr", {}, h("td", {}, f.label),
      h("td", {}, YES_NO.has(f.name) ? (f.value ? "yes" : "no") : typeof f.value === "number" ? (Number.isInteger(f.value) ? f.value : f.value.toFixed(2)) : f.value)))));
  let decide;
  if (o) {
    const sendOk = o.p_unsafe < o.tau_send, fixOk = o.p_fix > o.tau_fix;
    decide = h("section", { class: "card" },
      h("h2", {}, "Outcome models · LightGBM ", srcTag("live", "live")),
      h("p", { class: "note" }, `Trained on ${(cert.fit_items || 13383).toLocaleString()} controlled-track answers (the fit split); thresholds certified on ${(cert.calibration_items || 0).toLocaleString()} others.`),
      probBar("P(unsafe): the original answer has a wrong number", o.p_unsafe, o.tau_send, `send if below ${o.tau_send}`),
      probBar("P(fix): the rule repairer would return a safe, useful answer", o.p_fix, o.tau_fix, `repair if above ${o.tau_fix}`),
      h("div", { class: "flow" },
        h("div", { class: "stepline" }, h("span", { class: `mark ${sendOk ? "yes" : "no"}` }, sendOk ? "✓" : "✗"),
          h("span", {}, `P(unsafe) ${fmt(o.p_unsafe)} ${sendOk ? "<" : "≥"} ${o.tau_send} → ${sendOk ? "send the original" : "do not send as is"}`)),
        !sendOk ? h("div", { class: "stepline" }, h("span", { class: `mark ${fixOk ? "yes" : "no"}` }, fixOk ? "✓" : "✗"),
          h("span", {}, `P(fix) ${fmt(o.p_fix)} ${fixOk ? ">" : "≤"} ${o.tau_fix} → ${fixOk ? "repair" : "abstain with the evidence"}`)) : null,
        h("div", { style: "margin-top:6px" }, "Action: ", badge(c.action, true))),
      h("p", { class: "note" }, "Threshold policy v0 (rules only, the baseline) would choose ", badge(c.baseline.action),
        c.baseline.action === c.action ? " too." : " here: the two policies disagree."));
  } else {
    decide = h("section", { class: "card" }, h("h2", {}, "Decision · threshold policy v0"),
      h("p", {}, "The trained policy's model file is missing on this laptop (runs/policy/controlled/policy.pkl; rebuild it with `faithguard policy`), so the rule-only threshold policy decides: ", badge(c.action, true)),
      h("p", { class: "note" }, c.reason));
  }
  const t = cert.test || {}, mix = cert.test_mix || {};
  const certCard = h("section", { class: "card cert" }, h("h2", {}, "The certified setting"),
    h("div", { style: "font-size:17px;margin-bottom:6px" }, h("code", {}, cert.setting || "send<0.5,fix>0.6"), `   ·   α = ${cert.alpha ?? 0.1}   ·   δ = ${cert.delta ?? 0.05}`),
    h("div", {}, h("span", { class: "k" }, "Guarantee: "),
      `with ${100 * (1 - (cert.delta ?? 0.05))}% confidence, at most ${100 * (cert.alpha ?? 0.1)}% of released answers (sent as is or repaired) contain an unsupported claim, as a share over many answers like the controlled-track calibration set (Learn-then-Test). It promises nothing about any single answer.`),
    h("div", {}, h("span", { class: "k" }, "Certified on: "),
      `${(cert.calibration_items || 0).toLocaleString()} calibration answers; ${cert.certified || "–"} settings pass; chosen setting's p = ${cert.p_value ? Number(cert.p_value).toExponential(1) : "–"} (answer-level)` +
      (cert.p_issuer ? `, ${fmt(cert.p_issuer, 3)} treating each issuer as one draw.` : ".")),
    t.items ? h("div", {}, h("span", { class: "k" }, "On the held-out controlled test: "),
      `${pct(t.emission_coverage)} of answers released (the policy sent ${pct(mix.send)} as is and chose repair for ${pct(mix.repair)}), ` +
      `${pct(t.residual_risk)} wrong among released, ${pct(t.useful_coverage)} useful.`) : null,
    h("h4", {}, "Certification budget: how many calibration answers are needed"),
    budgetChart(cert.budget_curve || []),
    d.group === "ask" || d.group === "pilot" ? h("div", { class: "verdictbox warn" },
      "Not certified for this answer: the guarantee is for answers like the controlled-track calibration set (template answers with planted errors). "
      + "Real reports and own questions are outside it; the certificate for natural answers is computed on the locked calibration answers in phase 7.") : null,
    h("p", { class: "note" }, "Controlled track (injected errors on FinQA and TAT-QA): development results. The locked test set is labelled by separate blind Claude passes, not by people (D-103, D-105); on it no policy setting certified (runs/main/report.md, D-113)."));
  return h("div", {}, h("div", { class: "grid2" }, decide, feats), h("div", { style: "height:14px" }), certCard);
}

function probBar(label, p, tau, tauLabel) {
  return h("div", { class: "prob" },
    h("div", { class: "lbl" }, h("span", {}, label), h("b", {}, fmt(p))),
    h("div", { class: "bar" }, h("div", { class: "fill", style: `width:${(100 * p).toFixed(1)}%` }),
      h("div", { class: "tau", style: `left:${100 * tau}%` }, h("span", {}, tauLabel))));
}

function budgetChart(curve) {
  if (!curve.length) return h("p", { class: "note" }, "No budget curve in runs/policy/controlled/results.json.");
  const W = 640, H = 230, L = 44, R = 150, T = 14, B = 34;
  const xs = curve.map((r) => r.calibration_items);
  const lx = (v) => L + ((Math.log2(v) - Math.log2(xs[0])) / (Math.log2(xs[xs.length - 1]) - Math.log2(xs[0]))) * (W - L - R);
  const ly = (v) => T + (1 - v) * (H - T - B);
  const ns = "http://www.w3.org/2000/svg";
  const s = (tag, attrs, text) => { const el = document.createElementNS(ns, tag); for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v); if (text !== undefined) el.textContent = text; return el; };
  const svg = s("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Certification budget curve" });
  const grid = s("g", { class: "grid" }), axis = s("g", { class: "axis" });
  for (const v of [0, 0.25, 0.5, 0.75, 1]) {
    grid.append(s("line", { x1: L, x2: W - R, y1: ly(v), y2: ly(v) }));
    axis.append(s("text", { x: L - 6, y: ly(v) + 4, "text-anchor": "end" }, `${v * 100}%`));
  }
  for (const v of xs) axis.append(s("text", { x: lx(v), y: H - B + 16, "text-anchor": "middle" }, v.toLocaleString()));
  axis.append(s("text", { x: (L + W - R) / 2, y: H - 2, "text-anchor": "middle" }, "calibration answers (random subsets)"));
  svg.append(grid, axis);
  const series = [
    { key: "certified_share", label: "a setting is certified", color: "var(--series-1)" },
    { key: "mean_test_useful_coverage_when_certified", label: "useful answers on test", color: "var(--series-2)" },
  ];
  for (const sr of series) {
    const pts = curve.filter((r) => r[sr.key] !== null && r[sr.key] !== undefined);
    svg.append(s("path", { d: pts.map((r, i) => `${i ? "L" : "M"}${lx(r.calibration_items).toFixed(1)},${ly(r[sr.key]).toFixed(1)}`).join(""),
      fill: "none", stroke: sr.color, "stroke-width": 2, "stroke-linejoin": "round" }));
    for (const r of pts) svg.append(s("circle", { cx: lx(r.calibration_items), cy: ly(r[sr.key]), r: 4, fill: sr.color, stroke: "var(--surface)", "stroke-width": 2 }));
    const lastPt = pts[pts.length - 1];
    svg.append(s("text", { x: W - R + 8, y: ly(lastPt[sr.key]) + (sr.key === "certified_share" ? -4 : 12), fill: "var(--text)", "font-size": 12 }, sr.label));
  }
  const wrap = h("div", { class: "chart" });
  const tip = h("div", { class: "tip", hidden: true });
  for (const r of curve) {
    const hit = s("rect", { x: lx(r.calibration_items) - 18, y: T, width: 36, height: H - T - B, fill: "transparent" });
    hit.addEventListener("mouseenter", () => {
      tip.hidden = false;
      tip.textContent = `${r.calibration_items.toLocaleString()} answers: certified in ${pct(r.certified_share, 0)} of draws; useful on test ${pct(r.mean_test_useful_coverage_when_certified)}`;
      const width = wrap.clientWidth, x = (lx(r.calibration_items) / W) * width;
      tip.style.top = `${wrap.querySelector("svg").clientHeight + 4}px`;
      tip.style.left = `${Math.max(0, Math.min(width - tip.offsetWidth, x - tip.offsetWidth / 2))}px`;
    });
    hit.addEventListener("mouseleave", () => (tip.hidden = true));
    svg.append(hit);
  }
  return put(wrap, svg, tip,
    h("div", { class: "legend" }, series.map((sr) => h("span", {}, h("span", { class: "sw", style: `background:${sr.color}` }), sr.label))));
}

// ---------------------------------------------------------------- step 3: Correct
function programBlock(view) {
  if (!view.program || !view.program.length) return h("p", { class: "note" }, "No edit program.");
  return h("div", { class: "prog" }, view.program.map((e) => {
    const [op, ...rest] = e.text.split(" ");
    return h("div", {}, h("span", { class: `op ${e.op}` }, op), " ", rest.join(" "));
  }));
}

function beforeAfter(original, check) {
  const before = [], after = [];
  let pos = 0;
  const changes = check.changes || [];
  let shift = 0;
  const orig = changes.map((c) => { const start = c.start - shift; const end = start + c.old.length; shift += c.new.length - c.old.length; return { ...c, ostart: start, oend: end }; });
  for (const c of orig) { before.push(original.slice(pos, c.ostart), h("span", { class: "old" }, c.old)); pos = c.oend; }
  before.push(original.slice(pos));
  pos = 0;
  for (const c of changes) {
    const tipText = c.cells.length ? Object.values(c.cell_labels).join("  |  ") : "";
    after.push(check.text.slice(pos, c.start), h("span", { class: "new", title: tipText }, c.new));
    pos = c.end;
  }
  after.push(check.text.slice(pos));
  return [h("div", { class: "balabel" }, "Before"), h("div", { class: "ba" }, before),
    h("div", { class: "balabel" }, check.passed ? "After" : "After (rejected by the gate: never shown to the user)"), h("div", { class: "ba" }, after),
    changes.some((c) => c.cells.length) ? h("ul", { class: "newcells" }, changes.filter((c) => c.cells.length).map((c) =>
      h("li", {}, h("b", {}, c.new), c.direction_word ? " ← the sign of the calculation on " : " ← ",
        c.cells.map((id) => cellTag(id, c.cell_labels[id], check.passed ? "asked" : "plain"))))) : null];
}

function gateList(check) {
  return h("ul", { class: "checks" }, check.checks.map((g) => h("li", {},
    h("span", { class: g.passed ? "ok" : "fail" }, g.passed ? "✓" : "✗"), h("b", {}, g.name), h("span", { class: "what" }, g.about),
    g.passed ? null : h("span", { class: "why" }, g.detail))));
}

function cannotFixBlock(cf) {
  return [h("div", { class: "verdictbox warn" }, `CANNOT_FIX · ${cf.reason.replace(/_/g, " ")}`),
    h("p", {}, cf.claim_text ? `“${cf.claim_text}”: ` : "", cf.explain, "."),
    cf.about ? h("p", { class: "note" }, `What the number is about: ${cf.about}`) : null,
    cf.note ? h("p", { class: "note" }, `Checker's note: ${cf.note}`) : null,
    cf.cells.length ? h("div", {}, h("span", { class: "note" }, "Evidence shown with it: "), cf.cells.map((id) => cellTag(id, cf.cell_labels[id], "plain"))) : null,
    cf.report_rows.length ? h("div", {}, h("span", { class: "note" }, "What the report does hold: "), cf.report_rows.map((r) => h("span", { class: "celltag plain" }, r))) : null];
}

// role: "released" (its output is what the pipeline sends), "withheld" (policy abstained) or "comparison"
function repairColumn(d, view, title, who, role) {
  const col = h("section", { class: "card repcol" }, h("h3", {}, title), h("div", { class: "who" }, who));
  if (!view) return col;
  put(col, h("div", { style: "margin-bottom:6px" }, srcTag(view.source, view.label)));
  if (view.status === "nothing_to_fix") return put(col, h("div", { class: "verdictbox info" }, "Nothing to fix: it kept every number."));
  put(col, h("h4", {}, "Edit program"), programBlock(view));
  if (view.cannot_fix) return put(col, cannotFixBlock(view.cannot_fix));
  if (view.status === "cannot_fix") return put(col, h("div", { class: "verdictbox warn" }, `CANNOT_FIX · ${view.reason}`));
  const check = view.check || {};
  if (check.executor_error) {
    put(col, h("div", { class: "verdictbox bad" }, `The executor rejected the program${view.attempts > 1 ? ` (after ${view.attempts} attempts)` : ""}: ${check.executor_error}. Nothing is sent from it.`));
    return col;
  }
  if (check.ran) {
    put(col, h("h4", {}, "Hard gate: five checks"), gateList(check));
    if (check.text) put(col, ...beforeAfter(d.answer, check));
  }
  if (view.status === "repaired") {
    const text = role === "released" ? "Passes every check: this repaired answer is what the user gets."
      : role === "withheld" ? "Passes the gate, but not released: the policy withheld the answer."
        : "Passes every check (for comparison: the deployed pipeline sends the rule repairer's output).";
    put(col, h("div", { class: `verdictbox ${role === "released" ? "good" : "info"}` }, text));
  } else if (view.status === "gate_failed") {
    put(col, h("div", { class: "verdictbox bad" }, `Rejected${view.attempts > 1 ? ` after ${view.attempts} attempts` : ""}: nothing wrong is sent from it.`));
  }
  return col;
}

function renderCorrect(d) {
  const c = d.correct, chose = d.control.action;
  const intro = h("section", { class: "card" });
  if (chose === "send") {
    return put(intro, h("h2", {}, "Nothing to correct"), h("p", {}, "The policy sent the original answer, so the repairer does not run."));
  }
  const rejected = chose === "repair" && c.action === "abstain";
  put(intro, h("h2", {}, `The policy chose ${ACTION_WORD[chose]}`),
    h("p", { class: "note" }, "A repairer writes an edit program (KEEP, COPY, CALCULATE or CANNOT_FIX); the Decimal executor applies it; the hard gate checks the result. ",
      chose === "abstain" ? "Here the policy withheld the answer, so both programs below are shown for comparison only." : "",
      rejected ? "The rule repairer's program did not pass, so the answer is withheld with the evidence." : ""));
  const ruleRole = chose === "abstain" ? "withheld" : "released";
  const rule = repairColumn(d, c.rule, "Rule repairer v0", "Copies the checker's fix: COPY a cell or CALCULATE from cells; CANNOT_FIX when no rule applies.", ruleRole);
  const key = `${d.id}|${d.answer}`;
  const live = state.trainedLive[key];
  const tview = live || c.trained;
  const trained = repairColumn(d, tview, "Trained repairer v1 (frozen, D-101)",
    "Qwen3.5-2B + LoRA, trained to write edit programs; the same executor and gate.", chose === "abstain" ? "withheld" : "comparison");
  if (!tview) put(trained, h("p", { class: "note" }, d.edited ? "No stored output for this edited answer." : "No stored output for this answer."));
  if (c.live_repairer) {
    const btn = h("button", { class: "btn primary", style: "margin-top:10px" }, live ? "Run it live again" : "Run the trained repairer live on this answer");
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      const t0 = performance.now();
      btn.replaceChildren(h("span", { class: "spin" }), " generating on the GPU… ", h("span", { id: "secs" }, "0 s"));
      const tick = setInterval(() => { const el = document.getElementById("secs"); if (el) el.textContent = `${Math.round((performance.now() - t0) / 1000)} s`; }, 500);
      try {
        const out = await api("/api/trained", { id: d.id, answer: d.edited ? d.answer : null });
        if (out.error) { toast(out.error); return; }
        state.trainedLive[key] = out;
        if (state.data && `${state.data.id}|${state.data.answer}` === key) render({ keepTextarea: true });
      } finally {
        clearInterval(tick);
        if (btn.isConnected) { btn.disabled = false; btn.textContent = "Try again"; }
      }
    });
    put(trained, btn);
  }
  return h("div", {}, intro, h("div", { class: "grid2" }, rule, trained));
}

// ---------------------------------------------------------------- Output
function renderOutput(d) {
  const o = d.output;
  const card = h("section", { class: "card" });
  if (o.action === "abstain") {
    put(card, h("h2", {}, "Withheld ", badge("abstain", true)),
      h("div", { class: "final abstain" }, "I can't give a reliable answer to this from the report."),
      h("div", { class: "reason" }, h("b", {}, "Reason: "), o.reason),
      o.evidence_cells.length ? h("div", { class: "reason" }, h("b", {}, "Evidence shown to the user (the cells the failing numbers matched): "),
        o.evidence_cells.map((id) => cellTag(id, o.cell_labels[id], "plain"))) : null,
      o.report_rows.length ? h("div", { class: "reason" }, h("b", {}, "What the report does hold: "), o.report_rows.map((r) => h("span", { class: "celltag plain" }, r))) : null);
  } else {
    put(card, h("h2", {}, o.action === "send" ? "Sent unchanged " : "Sent, repaired ", badge(o.action, true)),
      h("div", { class: "final" }, o.text),
      h("div", { class: "reason" }, h("b", {}, "Why: "), o.reason),
      o.evidence_cells.length ? h("div", { class: "reason" }, h("b", {}, "Cells behind the numbers: "),
        o.evidence_cells.map((id) => cellTag(id, o.cell_labels[id], "asked"))) : null);
  }
  if (d.reference) {
    put(card, h("p", { class: "note", style: "margin-top:12px" }, h("b", {}, "Reference answer "),
      "(development gold, never seen by the pipeline): ", d.reference));
  }
  return card;
}

// ---------------------------------------------------------------- Results
async function showResults() {
  state.view = "results";
  state.loadSeq++;
  renderSidebar();
  if (!state.results) {
    const r = await api("/api/results");
    if (r.error) { toast(r.error); return; }
    state.results = r;
  }
  renderResults();
}

function md(text) {
  // headings, tables, lists, paragraphs; `code` and **bold** inline (text is escaped first)
  const inline = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>").replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
  const out = [];
  const lines = (text || "").split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (/^#{1,4} /.test(l)) { const n = l.match(/^#+/)[0].length; out.push(`<h${n}>${inline(l.slice(n + 1))}</h${n}>`); continue; }
    if (l.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) { rows.push(lines[i]); i++; }
      i--;
      const cells = (r) => r.replace(/^\||\|$/g, "").split(/(?<!\\)\|/).map((c) => inline(c.trim().replace(/\\\|/g, "|")));
      const body = rows.filter((r) => !/^\|\s*-/.test(r));
      out.push("<table>" + body.map((r, k) => `<tr>${cells(r).map((c) => (k ? `<td>${c}</td>` : `<th>${c}</th>`)).join("")}</tr>`).join("") + "</table>");
      continue;
    }
    if (/^- /.test(l)) {
      const items = [];
      while (i < lines.length && /^- /.test(lines[i])) { items.push(`<li>${inline(lines[i].slice(2))}</li>`); i++; }
      i--;
      out.push(`<ul>${items.join("")}</ul>`);
      continue;
    }
    if (l.trim()) out.push(`<p>${inline(l)}</p>`);
  }
  return h("div", { class: "md", html: out.join("") });
}

function resTable(cols, rows) {
  return h("table", { class: "res" }, h("tr", {}, cols.map((c) => h("th", {}, c[0]))),
    rows.map((r) => h("tr", { class: r.ours ? "ours" : "" }, cols.map((c) => h("td", { class: c[2] ? "num" : "" }, c[1](r))))));
}

const REPAIR_COLS = [["Repairer", (x) => x.label], ["Corrected", (x) => pct(x.correction_rate), 1], ["Withheld when needed", (x) => pct(x.abstained_when_needed), 1],
  ["New errors", (x) => pct(x.new_error_rate), 1], ["Damage", (x) => pct(x.damage_rate), 1],
  ["Gate pass", (x) => (x.gate_pass_rate === null || x.gate_pass_rate === undefined ? "– (no gate)" : pct(x.gate_pass_rate)), 1]];

function renderResults() {
  const r = state.results;
  const main = document.getElementById("main");
  const tabs = [["main", "Locked test · D-113"], ["detection", "Catch · detection"], ["repair", "Correct · repair"], ["policy", "Control · policy"]];
  const body = h("div", {});
  const locked = state.resultsTab === "main";
  if (locked) {
    put(body, h("section", { class: "card" }, r.reports.main ? md(r.reports.main) : h("p", { class: "note" }, "runs/main/report.md is not on this laptop.")));
  } else if (state.resultsTab === "detection") {
    put(body, h("section", { class: "card" }, h("h2", {}, "Detectors on controlled-track development answers (Kaggle)"),
      resTable([["Detector", (x) => x.label], ["Answers", (x) => (x.items || 0).toLocaleString(), 1], ["AUROC", (x) => fmt(x.auroc), 1],
        ["False alarms on clean answers", (x) => pct(x.false_alarm_clean), 1], ["Recall on wrong-context errors", (x) => pct(x.wrong_context_recall), 1]], r.detectors),
      h("p", { class: "note" }, "From runs/detector/kaggle/*/results.json. Bold rows are FaithGuard's own detectors.")),
      h("section", { class: "card" }, md(r.reports.fusion)));
  } else if (state.resultsTab === "repair") {
    const name = state.repairReport || "eval-v1";
    const sel = h("select", { onchange: (ev) => { state.repairReport = ev.target.value; renderResults(); } },
      Object.keys(r.repair_reports).map((k) => h("option", { value: k, selected: k === name }, k)));
    put(body, h("section", { class: "card" }, h("h2", {}, "Repairers on the same 500 controlled-track development answers (411 wrong)"),
      resTable(REPAIR_COLS, r.repairers),
      h("p", { class: "note" }, "From runs/repair/rules and runs/repair/kaggle/*/results.json; stage A under the current gate (D-095). Bold: the rule repairer and the frozen repairer v1 (D-101). The free-rewriting row is the frozen R-H1 comparator (D-110).")),
      r.pilot_repair.length ? h("section", { class: "card" }, h("h2", {}, "Real AI answers (pilot, 104 answers, 23 wrong; development)"),
        resTable(REPAIR_COLS, r.pilot_repair),
        h("p", { class: "note" }, "Counts only, from runs/pilot/v1run-repair-v1. On natural answers the rules correct more than the trained repairer.")) : null,
      h("section", { class: "card" }, h("div", {}, "Full report: ", sel), md(r.repair_reports[name])));
  } else {
    put(body, h("section", { class: "card" }, md(r.reports.policy)));
  }
  main.replaceChildren(
    h("div", { class: "banner" }, locked
      ? "The locked test set, scored once after the pre-registration was filed (D-104, D-113): 394 questions and 788 answers on 48 Sri Lankan and US companies (392 test and 396 calibration answers). "
        + "The labels are made by separate blind Claude passes, not by people (D-103, D-105). One of the nine hypotheses is confirmed (R-H1); no policy setting is certified. Shown as generated, from runs/main/report.md."
      : "Development results, not the locked test set: these numbers come from the controlled track (injected errors) and Kaggle development runs. "
        + "The locked test set (788 answers) is labelled by separate blind Claude passes, not by people (D-103, D-105); on its 672 numeric answers the rule checker flags 144 of the 170 labelled incorrect and 110 of the 502 labelled right (runs/main/labels). Its pre-registered results are in the Locked test tab (D-113)."),
    h("div", { class: "tabs" }, tabs.map(([k, label]) => h("button", { class: `tab${state.resultsTab === k ? " active" : ""}`,
      onclick: () => { state.resultsTab = k; renderResults(); } }, label))),
    body);
}

// ---------------------------------------------------------------- ask your own question
async function showAsk() {
  state.view = "ask";
  state.loadSeq++;
  state.runSeq++;
  clearTimeout(state.timer);
  renderSidebar();
  if (!state.reports) {
    document.getElementById("main").replaceChildren(h("div", { class: "main-loading" }, "Loading the reports…"));
    const r = await api("/api/reports");
    if (r.error) { toast(r.error); return; }
    state.reports = r;
    const real = r.find((x) => x.real && x.country === "LK") || r[0];
    state.ask.report = state.ask.report || (real && real.id);
  }
  if (state.view === "ask") renderAsk();
}

function askReport() { return (state.reports || []).find((r) => r.id === state.ask.report) || null; }
function aiReady() { return state.status && state.status.repairer && state.status.repairer.state === "ready"; }
function aiNote() {
  const st = state.status && state.status.repairer;
  if (aiReady()) return "Qwen3.5-2B, live on this laptop's GPU (3-15 s): the trained repairer's base model with the repair training switched off, "
    + "asked for a one-sentence answer. The benchmark's answers came from larger models.";
  if (st && st.state === "loading") return "The AI is loading on the GPU (about 25 s)…";
  return "The AI is not loaded on this laptop (it needs the GPU and the model files): write the answer from the table, or type one.";
}

function setQuestion(text) {
  if (state.ask.busy) return;
  state.ask.question = text;
  state.ask.answer = "";
  const q = document.getElementById("askq");
  if (q) { q.value = text; q.focus(); }
  const a = document.getElementById("askanswer");
  if (a) a.value = "";
  updateAskButtons();
}

function askError(msg) {
  const el = document.getElementById("askerr");
  if (el) { el.textContent = msg || ""; el.hidden = !msg; }
}

const ASK_INPUTS = ["askreport", "askq", "askanswer", "asktables", "askall"];

function updateAskButtons() {
  const busy = state.ask.busy;
  const hasQ = state.ask.question.trim().length > 0;
  const set = (id, disabled) => { const el = document.getElementById(id); if (el && !(busy && busy.id === id)) el.disabled = disabled; };
  set("askai", !!busy || !hasQ || !aiReady());
  set("askdraft", !!busy || !hasQ);
  set("askgo", !!busy || !hasQ || !state.ask.answer.trim());
  for (const id of ASK_INPUTS) set(id, !!busy);
  document.querySelectorAll(".askcard .chip").forEach((c) => (c.disabled = !!busy));
  const note = document.getElementById("ainote");
  if (note) note.textContent = aiNote();
  if (busy) {  // a re-render while waiting keeps the spinner on the button that is waiting
    const btn = document.getElementById(busy.id);
    if (btn && !btn.querySelector(".spin")) { btn.disabled = true; btn.replaceChildren(h("span", { class: "spin" }), ` ${busy.text} `, h("span", { class: "secs" }, "")); }
  }
}

function busyButton(id, text) {
  const t0 = performance.now();
  state.ask.busy = { id, text };
  updateAskButtons();
  const tick = setInterval(() => { const s = document.querySelector(`#${id} .secs`); if (s) s.textContent = `${((performance.now() - t0) / 1000).toFixed(1)} s`; }, 100);
  return () => { clearInterval(tick); state.ask.busy = null; };
}

async function askFor(kind) {
  const r = askReport();
  const question = state.ask.question;
  if (state.ask.busy || !r || !question.trim() || (kind === "ai" && !aiReady())) return;
  askError("");
  const done = kind === "ai" ? busyButton("askai", "The AI is reading the report…") : busyButton("askdraft", "Writing from the table…");
  const out = await api(kind === "ai" ? "/api/ask/ai" : "/api/ask/draft", { report: r.id, question });
  done();
  if (state.view !== "ask" || state.ask.report !== r.id || state.ask.question !== question) { if (state.view === "ask") renderAsk(); return; }
  if (out.error) { renderAsk(); askError(out.error); return; }
  state.ask.answer = out.answer;
  state.ask.by = out.by;
  state.ask.seconds = out.seconds;
  renderAsk();
  checkAsk();
}

async function checkAsk() {
  const r = askReport();
  const question = state.ask.question, answer = state.ask.answer;
  if (state.ask.busy || !r || !question.trim() || !answer.trim()) return;
  askError("");
  const done = busyButton("askgo", "FaithGuard is checking…");
  const data = await api("/api/ask", { report: r.id, question, answer });
  done();
  if (state.view !== "ask" || state.ask.report !== r.id || state.ask.question !== question) { if (state.view === "ask") renderAsk(); return; }
  if (data.error) { renderAsk(); askError(data.error); return; }
  state.asked.unshift({ id: data.id, question: data.question.text, report: r.name, by: data.generator.split(",")[0], action: data.output.action });
  state.view = "case";
  state.current = data.id;
  state.data = data;
  state.step = 0;
  state.claim = firstClaim(data);
  state.showAll = {};
  renderSidebar();
  render();
  window.scrollTo(0, 0);
  fetchPlanted(data.id);
}

function previewTable(t) {
  const unit = { 3: "thousands", 6: "millions", 9: "billions" }[t.scale];
  return h("div", {}, h("div", { class: "tabletitle" }, `${t.title || "Table"}`,
    h("span", { class: "note" }, [unit ? ` · amounts in ${unit}` : "", t.currency ? ` · ${t.currency}` : "", ` · ${t.rows.length} rows`].join(""))),
    h("div", { class: "tablewrap preview" }, h("table", { class: "ev" },
      h("thead", {}, h("tr", {}, h("th", { class: "lab" }, ""), t.columns.map((c) => h("th", {}, c.label)))),
      h("tbody", {}, t.rows.map((row) => h("tr", {}, h("td", { class: "lab" }, row.label),
        row.cells.map((c) => h("td", { class: "cell" }, c ? c.text : ""))))))));
}

function renderAsk() {
  const r = askReport();
  const main = document.getElementById("main");
  if (!r) { main.replaceChildren(h("p", { class: "note" }, "No report is loaded.")); return; }
  const select = h("select", { id: "askreport", "aria-label": "Report", onchange: (ev) => {
    state.ask.report = ev.target.value; state.ask.question = ""; state.ask.answer = ""; state.ask.allItems = false; renderAsk(); } },
  state.reports.map((x) => h("option", { value: x.id, selected: x.id === r.id },
    `${x.name}${x.real ? ` · real annual report (${x.country === "LK" ? "Sri Lanka" : "US"})` : ""}`)));
  const input = h("input", { id: "askq", type: "text", class: "askq", maxlength: 300, autocomplete: "off", spellcheck: "false",
    placeholder: "Type any question about this report…", "aria-label": "Your question",
    oninput: (ev) => { state.ask.question = ev.target.value; updateAskButtons(); },
    onkeydown: (ev) => { if (ev.key === "Enter") { ev.preventDefault(); askFor(aiReady() ? "ai" : "draft"); } } });
  input.value = state.ask.question;
  const items = state.ask.allItems ? r.line_items : r.line_items.slice(0, 14);
  const busyNow = !!state.ask.busy;
  const answer = h("textarea", { id: "askanswer", spellcheck: "false", "aria-label": "Answer to check",
    placeholder: "…or type an answer here yourself, right or wrong",
    oninput: (ev) => { state.ask.answer = ev.target.value; state.ask.by = null; updateAskButtons(); },
    onkeydown: (ev) => { if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); checkAsk(); } } });
  answer.value = state.ask.answer;
  const card = h("section", { class: "card askcard" },
    h("h2", {}, "Ask your own question"),
    h("p", { class: "note lead" }, "Pick a report and ask anything its tables can answer. An AI answers, FaithGuard checks every number against the report, then sends, repairs or withholds the answer. Then plant an error and watch it get caught."),
    h("div", { class: "askrow" }, h("label", { for: "askreport" }, "1 · Report"), select),
    h("div", { class: "askrow" }, h("label", { for: "askq" }, "2 · Question"), input),
    r.suggestions.length ? h("div", { class: "chips indent" }, h("span", { class: "note" }, "Try: "),
      r.suggestions.map((s) => h("button", { class: "chip", onclick: () => setQuestion(s) }, s))) : null,
    r.line_items.length ? h("div", { class: "chips indent" }, h("span", { class: "note" }, "Line items in this report: "),
      items.map((x) => h("button", { class: "chip plain", title: x.question, onclick: () => setQuestion(x.question) }, x.label)),
      r.line_items.length > 14 ? h("button", { id: "askall", class: "btn small", disabled: busyNow,
        onclick: () => { state.ask.allItems = !state.ask.allItems; renderAsk(); } },
      state.ask.allItems ? "fewer" : `all ${r.line_items.length}`) : null) : null,
    h("div", { class: "askrow top" }, h("label", { for: "askanswer" }, "3 · Answer"),
      h("div", { class: "askanswer" },
        h("div", { class: "askbtns" },
          h("button", { id: "askai", class: "btn primary big", onclick: () => askFor("ai") }, "Ask the AI ▶"),
          h("button", { id: "askdraft", class: "btn big", onclick: () => askFor("draft") }, "Write the correct answer from the table")),
        h("div", { class: "note", id: "ainote" }, aiNote()),
        answer,
        state.ask.by && state.ask.answer ? h("div", { class: "note" }, `Answer by ${state.ask.by}${state.ask.seconds ? `, in ${state.ask.seconds} s` : ""}.`) : null,
        h("div", { class: "err", id: "askerr", hidden: true }),
        h("div", { class: "askbtns" }, h("button", { id: "askgo", class: "btn primary big", onclick: checkAsk }, "Check it with FaithGuard ▶"),
          h("span", { class: "note" }, "Enter in the question asks the AI; Ctrl+Enter in the answer checks it.")))));
  const tables = h("section", { class: "card" }, h("h2", {}, "What the AI and FaithGuard see ",
    h("button", { id: "asktables", class: "btn small", onclick: () => { state.ask.tables = !state.ask.tables; renderAsk(); } }, state.ask.tables ? "hide the tables" : "show the tables")),
  h("p", { class: "note" }, r.real ? "Tables taken from the company's published annual report (a development issuer of the benchmark)." : "Made-up figures on a fictional bank."),
  state.ask.tables ? r.evidence.tables.map(previewTable) : null);
  main.replaceChildren(card, tables);
  updateAskButtons();
}

// ---------------------------------------------------------------- start
document.addEventListener("keydown", (ev) => {
  if (state.view !== "case" || ["TEXTAREA", "INPUT", "SELECT"].includes(document.activeElement.tagName)) return;
  if (ev.key === "ArrowRight" || ev.key === "PageDown") { ev.preventDefault(); go(state.step + 1); }
  if (ev.key === "ArrowLeft" || ev.key === "PageUp") { ev.preventDefault(); go(state.step - 1); }
});

(async function start() {
  refreshStatus();
  const list = await api("/api/examples");
  if (list.error) { document.getElementById("main").textContent = list.error; return; }
  state.examples = list;
  renderSidebar();
  const first = list.find((e) => e.expect === "repair") || list[0];  // open on an error the system fixes
  if (first) loadCase(first.id, {});
})();
