// FaithGuard Stage: the 3D model. A white-card machine stands on a ledger sheet; an answer is a tray of type blocks.
// Everything it shows comes from the pipeline's result for the real answer: this file only moves things.
import * as THREE from "three";
import { RoundedBoxGeometry } from "./vendor/RoundedBoxGeometry.js";

const HEX = { paper: 0xe9e4d8, bone: 0xf6f2e8, card: 0xe4dfd2, ink: 0x17191b, steel: 0x2b2e31, graphite: 0x5c5f60,
              red: 0xc2301c, green: 0x1e6b4e, ochre: 0xb4760f, blue: 0x2a4bc7 };
const CSS = { paper: "#e9e4d8", bone: "#f6f2e8", card: "#e4dfd2", ink: "#17191b", graphite: "#5c5f60", rule: "#b9ccc8",
              margin: "#c98476", red: "#c2301c", green: "#1e6b4e", ochre: "#b4760f", blue: "#2a4bc7" };
const SANS = 'Bahnschrift, "Segoe UI", Arial, sans-serif';
const SERIF = '"Sitka Text", Sitka, Cambria, Georgia, serif';
const MARK = { ok: CSS.green, bad: CSS.red, unsure: CSS.ochre };

const ease = {
  linear: (t) => t,
  inOut: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  out: (t) => 1 - Math.pow(1 - t, 3),
  back: (t) => { const c = 1.5; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); },
};
const STOP = Symbol("stopped");
const V = (x, y, z) => new THREE.Vector3(x, y, z);
const STATION = { start: -18.5, catch: -13, control: -2.5, press: 7.5, gates: [11.6, 13, 14.4, 15.8, 17.2], dock: 26 };
const LANE = { send: -7.2, hold: 7.2 };
const BLOCK_DEPTH = 0.62, ROW = 0.74, MAX_ROW = 8.4, MAX_ROWS = 7, PX = 170, FONT_PX = 62;

const VIEWS = {
  all: { pos: V(0.5, 76, 88), tgt: V(0.5, 0, -2.2) },
  source: { pos: V(-19, 30, 31), tgt: V(-19, 0.6, -0.5) },
  catch: { pos: V(-9, 38, 44), tgt: V(-9, 2, -5) },
  control: { pos: V(-1, 34, 38), tgt: V(-1, 1, -3) },
  correct: { pos: V(8, 32, 30), tgt: V(8, 0.8, -0.8) },
  gates: { pos: V(15.5, 27, 29), tgt: V(15, 0.6, 0) },
  sent: { pos: V(24, 31, 25), tgt: V(24, 0.5, -7.2) },
  held: { pos: V(24, 31, 40), tgt: V(24, 0.5, 7.2) },
};

// ---------------------------------------------------------------- small makers
function canvas(w, h) {
  const c = document.createElement("canvas");
  c.width = w; c.height = h;
  return [c, c.getContext("2d")];
}
function texture(c) {
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}
function printed(c, w, h, { flat = false, opacity = 1 } = {}) {
  const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h),
    new THREE.MeshBasicMaterial({ map: texture(c), transparent: true, opacity, depthWrite: false, toneMapped: false }));
  if (flat) m.rotation.x = -Math.PI / 2;
  return m;
}
function word(text, { size = 64, font = SANS, weight = 600, color = CSS.ink, track = 0, pad = 8 } = {}) {
  const [c, x] = canvas(8, 8);
  x.font = `${weight} ${size}px ${font}`;
  if (track) x.letterSpacing = `${track}px`;
  const w = Math.ceil(x.measureText(text).width) + pad * 2, h = Math.ceil(size * 1.3);
  c.width = w; c.height = h;
  x.font = `${weight} ${size}px ${font}`;
  if (track) x.letterSpacing = `${track}px`;
  x.fillStyle = color; x.textBaseline = "middle";
  x.fillText(text, pad, h / 2);
  return c;
}
// a label printed on the ledger sheet, or on any flat face
function ink(text, height, opts = {}) {
  const c = word(text, opts);
  const m = printed(c, height * c.width / c.height, height, opts);
  return m;
}
// an auditor's mark, drawn as a pencil stroke
function tick(x, cx, cy, s, kind, color) {
  x.save(); x.strokeStyle = color; x.lineWidth = s * 0.17; x.lineCap = "round"; x.lineJoin = "round";
  x.beginPath();
  if (kind === "ok") { x.moveTo(cx - s * 0.5, cy + s * 0.02); x.quadraticCurveTo(cx - s * 0.28, cy + s * 0.18, cx - s * 0.12, cy + s * 0.44); x.quadraticCurveTo(cx + s * 0.1, cy - s * 0.1, cx + s * 0.54, cy - s * 0.5); }
  else if (kind === "bad") { x.moveTo(cx - s * 0.42, cy - s * 0.42); x.lineTo(cx + s * 0.42, cy + s * 0.42); x.moveTo(cx + s * 0.42, cy - s * 0.42); x.lineTo(cx - s * 0.42, cy + s * 0.42); }
  else { x.arc(cx, cy - s * 0.16, s * 0.3, Math.PI * 1.05, Math.PI * 2.25); x.lineTo(cx, cy + s * 0.2); x.moveTo(cx, cy + s * 0.46); x.lineTo(cx, cy + s * 0.47); }
  x.stroke(); x.restore();
}

export class Stage {
  constructor(el) {
    this.el = el;
    this.renderer = new THREE.WebGLRenderer({ canvas: el, antialias: true, powerPreference: "low-power" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.renderer.shadowMap.enabled = true;
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer.toneMapping = THREE.NoToneMapping;
    this.scene = new THREE.Scene();
    this.scene.background = new THREE.Color(HEX.paper);
    this.scene.fog = new THREE.Fog(HEX.paper, 150, 300);
    this.camera = new THREE.PerspectiveCamera(22, 1, 1, 500);
    this.view = { pos: VIEWS.all.pos.clone(), tgt: VIEWS.all.tgt.clone() };
    this.pace = 1.2; this.run = 0; this.tweens = []; this.time = 0;
    this.cellIndex = new Map(); this.temp = []; this.tray = null; this.geoms = new Map();
    this.mats = {
      bone: new THREE.MeshStandardMaterial({ color: HEX.bone, roughness: 0.92 }),
      card: new THREE.MeshStandardMaterial({ color: HEX.card, roughness: 0.95 }),
      ink: new THREE.MeshStandardMaterial({ color: HEX.ink, roughness: 0.62, metalness: 0.15 }),
      steel: new THREE.MeshStandardMaterial({ color: HEX.steel, roughness: 0.5, metalness: 0.3 }),
      line: new THREE.LineBasicMaterial({ color: HEX.ink, transparent: true, opacity: 0.55 }),
    };
    this.lights(); this.ground(); this.lanes(); this.source(); this.gantryCatch(); this.studied(); this.control(); this.press(); this.gateRow(); this.docks(); this.book();
    this.resize();
    window.addEventListener("resize", () => this.resize());
    this.clock = new THREE.Clock();
    this.renderer.setAnimationLoop(() => this.frame());
  }

  // ---------------------------------------------------------------- the room
  lights() {
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0xcfc8b6, 1.95));
    const sun = new THREE.DirectionalLight(0xfff4e2, 1.35);
    sun.position.set(-30, 60, 40);
    sun.castShadow = true;
    sun.shadow.mapSize.set(3072, 3072);
    Object.assign(sun.shadow.camera, { left: -52, right: 52, top: 40, bottom: -40, near: 10, far: 170 });
    sun.shadow.radius = 5; sun.shadow.bias = -0.0004; sun.shadow.normalBias = 0.03;
    this.scene.add(sun);
  }

  ground() {
    const [c, x] = canvas(1024, 1024);
    x.fillStyle = CSS.paper; x.fillRect(0, 0, 1024, 1024);
    for (let i = 0; i < 9000; i++) {  // paper fibre
      x.fillStyle = `rgba(${Math.random() < 0.5 ? "120,110,90" : "255,255,255"},${Math.random() * 0.05})`;
      x.fillRect(Math.random() * 1024, Math.random() * 1024, 1 + Math.random() * 3, 1);
    }
    x.strokeStyle = CSS.rule; x.lineWidth = 2;
    for (let i = 0; i < 4; i++) { const y = i * 256 + 128; x.beginPath(); x.moveTo(0, y); x.lineTo(1024, y); x.stroke(); }
    const t = texture(c);
    t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(26, 26);
    const g = new THREE.Mesh(new THREE.PlaneGeometry(320, 320), new THREE.MeshStandardMaterial({ map: t, roughness: 1 }));
    g.rotation.x = -Math.PI / 2; g.receiveShadow = true;
    this.scene.add(g);
    for (const dx of [0, 0.34]) {  // the ledger's double red margin
      const m = new THREE.Mesh(new THREE.PlaneGeometry(0.08, 320), new THREE.MeshBasicMaterial({ color: CSS.margin }));
      m.rotation.x = -Math.PI / 2; m.position.set(-37 + dx, 0.012, 0);
      this.scene.add(m);
    }
  }

  // a flat printed track along a curve
  ribbon(curve, width, color, y = 0.016) {
    const n = Math.ceil(curve.getLength() * 3), pos = [], idx = [];
    for (let i = 0; i <= n; i++) {
      const p = curve.getPointAt(i / n), t = curve.getTangentAt(i / n), s = V(-t.z, 0, t.x).multiplyScalar(width / 2);
      pos.push(p.x + s.x, y, p.z + s.z, p.x - s.x, y, p.z - s.z);
      if (i < n) { const a = i * 2; idx.push(a, a + 1, a + 2, a + 1, a + 3, a + 2); }
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3)); g.setIndex(idx);
    const m = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, toneMapped: false }));
    this.scene.add(m);
    return m;
  }

  lanes() {
    const c = (...p) => new THREE.CatmullRomCurve3(p.map(([x, z]) => V(x, 0, z)), false, "centripetal");
    const [cx, s, h, g, d] = [STATION.control, LANE.send, LANE.hold, STATION.gates[4] + 1.6, STATION.dock];
    this.paths = {
      toCatch: c([STATION.start, 0], [STATION.catch, 0]),
      toControl: c([STATION.catch, 0], [cx, 0]),
      send: c([cx, 0], [1.6, s * 0.46], [6, s * 0.92], [10, s], [18, s], [d, s]),
      hold: c([cx, 0], [1.6, h * 0.46], [6, h * 0.92], [10, h], [18, h], [d, h]),
      fix: c([cx, 0], [STATION.press, 0]),
      gates: c([STATION.press, 0], [g, 0]),
      pass: c([g, 0], [g + 2, s * 0.42], [g + 3.8, s * 0.94], [g + 5, s], [d, s]),
      fail: c([g, 0], [g + 2, h * 0.42], [g + 3.8, h * 0.94], [g + 5, h], [d, h]),
    };
    for (const p of Object.values(this.paths)) { this.ribbon(p, 2.6, 0xdfd9cb, 0.012); this.ribbon(p, 0.08, CSS.ink, 0.02); }
    const t = (text, x, z) => { const m = ink(text, 0.7, { flat: true, color: CSS.graphite, track: 6, size: 54 }); m.position.set(x, 0.03, z); this.scene.add(m); };
    t("LOOKS SAFE", 12.4, LANE.send + 1.9); t("FIXABLE", 3.2, 1.15); t("NEITHER", 12.2, LANE.hold - 1.9);
    // the three parts, called out on the sheet like a drawing
    const y = 12.3, call = (n, name, sub, x, z) => {
      const big = ink(`${n}  ${name}`, 1.9, { flat: true, size: 110, weight: 700, track: 4, pad: 2 });
      big.position.set(x + big.geometry.parameters.width / 2 - 0.3, 0.03, y); this.scene.add(big);
      const small = ink(sub, 0.8, { flat: true, size: 56, weight: 400, color: CSS.graphite, pad: 2 });
      small.position.set(x + small.geometry.parameters.width / 2 - 0.2, 0.03, y + 1.45); this.scene.add(small);
      const lead = new THREE.Mesh(new THREE.PlaneGeometry(0.05, y - 1 - z), new THREE.MeshBasicMaterial({ color: CSS.ink }));
      lead.rotation.x = -Math.PI / 2; lead.position.set(x, 0.025, (y - 1 + z) / 2); this.scene.add(lead);
    };
    call(1, "CATCH", "Traces each number to the report", STATION.catch, 2.2);
    call(2, "CONTROL", "Send, fix or withhold", STATION.control, 5.7);
    call(3, "CORRECT", "Changes only the wrong block", STATION.press + 1, 2.2);
  }

  block(w, h, d, mat = "bone", r = 0.05) {
    const key = `${w.toFixed(2)}|${h.toFixed(2)}|${d.toFixed(2)}|${r}`;
    if (!this.geoms.has(key)) this.geoms.set(key, [new RoundedBoxGeometry(w, h, d, 2, r), new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d))]);
    const [geo, edges] = this.geoms.get(key);
    const m = new THREE.Mesh(geo, this.mats[mat]);
    m.castShadow = true; m.receiveShadow = true;
    if (mat === "bone" || mat === "card") m.add(new THREE.LineSegments(edges, this.mats.line));
    return m;
  }

  at(mesh, x, y, z) { mesh.position.set(x, y, z); this.scene.add(mesh); return mesh; }

  source() {
    const x = -26.4;
    this.aiBody = this.at(this.block(5.2, 3.6, 7.6), x, 1.8, 0);
    const lab = ink("AI MODEL", 1.05, { flat: true, size: 90, weight: 700, track: 3 });
    lab.position.set(x, 3.62, 0.6); this.scene.add(lab);
    this.aiLamp = this.lamp(x + 1.5, 3.8, -2.6);
  }

  lamp(x, y, z) {
    const m = new THREE.Mesh(new THREE.SphereGeometry(0.2, 20, 14), new THREE.MeshStandardMaterial({ color: 0xb5b0a3, roughness: 0.5 }));
    return this.at(m, x, y, z);
  }

  arch(x, span, height, mat = "bone", thick = 1.05, deep = 1.5) {
    const post = (z) => this.at(this.block(deep, height, thick, mat, 0.05), x, height / 2, z);
    const a = post(-span / 2 - thick / 2), b = post(span / 2 + thick / 2);
    const c = this.at(this.block(deep, thick, span + 2 * thick, mat, 0.05), x, height + thick / 2, 0);
    return [a, b, c];
  }

  // a one-sided frame: the column stands behind the lane, so nothing hides the tray
  frameC(x, height, reach = 3.8) {
    const z0 = -4.6;
    this.at(this.block(1.7, height, 1.3), x, height / 2, z0);
    this.at(this.block(1.7, 2, 2.4), x, 1, z0 - 0.1);
    const len = reach - z0 + 0.65;
    this.at(this.block(1.7, 1, len), x, height + 0.5, z0 + len / 2 - 0.65);
  }

  gantryCatch() {
    const x = STATION.catch;
    this.frameC(x, 3.4);
    const beam = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.05, 7), new THREE.MeshBasicMaterial({ color: CSS.blue, toneMapped: false, transparent: true, opacity: 0 }));
    this.scan = this.at(beam, x, 3.3, 0);
  }

  studied() {
    // Channel A and the fusion, drawn as outlines: studied beside the checker, not part of the decision
    const x = STATION.catch - 8.6, z = 6.6;
    const hollow = (w, h, d, px, pz) => {
      const e = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.BoxGeometry(w, h, d)), new THREE.LineDashedMaterial({ color: HEX.graphite, dashSize: 0.22, gapSize: 0.16 }));
      e.computeLineDistances(); e.position.set(px, h / 2, pz); this.scene.add(e);
    };
    hollow(3.4, 1.1, 2.2, x, z); hollow(3.4, 1.1, 2.2, x + 4.6, z);
    const lab = (text, px) => { const m = ink(text, 0.56, { flat: true, color: CSS.graphite, size: 50, weight: 600 }); m.position.set(px, 0.03, z + 1.75); this.scene.add(m); };
    lab("Channel A", x); lab("A + B fusion", x + 4.6);
    const n = ink("Studied. Not in the decision", 0.64, { flat: true, color: CSS.graphite, size: 50, weight: 400 });
    n.position.set(x + 2.3, 0.03, z + 2.6); this.scene.add(n);
  }

  control() {
    const x = STATION.control, r = 5.6;
    const [c, g] = canvas(1024, 1024);
    g.fillStyle = "#1c1e20"; g.fillRect(0, 0, 1024, 1024);
    g.translate(512, 512); g.strokeStyle = "#8d8c84"; g.lineWidth = 3;
    for (let i = 0; i < 72; i++) { g.rotate(Math.PI / 36); g.beginPath(); g.moveTo(0, 470 + (i % 6 ? 16 : 0)); g.lineTo(0, 500); g.stroke(); }
    const top = new THREE.MeshStandardMaterial({ map: texture(c), roughness: 0.6 });
    this.disk = this.at(new THREE.Mesh(new THREE.CylinderGeometry(r, r, 0.18, 96), [this.mats.steel, top, this.mats.steel]), x, 0.09, 0);
    this.disk.castShadow = true; this.disk.receiveShadow = true;
    this.gaugeA = this.gauge("P(unsafe)", x - 3.8, -7.4); this.gaugeB = this.gauge("P(fix)", x - 0.6, -7.4);
    const note = ink("Thresholds certified on practice data only", 0.46, { flat: true, color: CSS.graphite, size: 46, weight: 400 });
    note.position.set(x + 8.3, 0.03, -9.55); this.scene.add(note);
  }

  gauge(name, x, z) {
    const H = 4.8, body = this.at(this.block(2.8, H, 0.3), x, H / 2, z);
    body.rotation.x = -0.14;
    const [c, g] = canvas(480, 834);
    const draw = (value, tau, hot) => {
      g.clearRect(0, 0, 480, 834);
      g.fillStyle = CSS.ink; g.font = `600 48px ${SANS}`; g.textBaseline = "alphabetic"; g.fillText(name, 22, 60);
      g.font = `700 76px ${SANS}`; g.fillStyle = hot || CSS.graphite; g.fillText(value === null ? "–" : value.toFixed(2), 22, 140);
      const top = 180, bottom = 806, x0 = 30, y = (v) => bottom - v * (bottom - top);
      g.fillStyle = "#d8d2c3"; g.fillRect(x0, top, 34, bottom - top);
      g.strokeStyle = CSS.graphite; g.lineWidth = 2;
      for (let i = 0; i <= 10; i++) { g.beginPath(); g.moveTo(x0 + 34, y(i / 10)); g.lineTo(x0 + (i % 5 ? 50 : 60), y(i / 10)); g.stroke(); }
      if (value !== null) { g.fillStyle = hot || CSS.graphite; g.fillRect(x0, y(value), 34, bottom - y(value)); }
      if (tau !== null) {
        g.strokeStyle = CSS.ink; g.lineWidth = 6; g.beginPath(); g.moveTo(x0 - 12, y(tau)); g.lineTo(x0 + 110, y(tau)); g.stroke();
        g.fillStyle = CSS.ink; g.font = `600 36px ${SANS}`; g.fillText(`limit ${tau}`, x0 + 118, y(tau) + 12);
      }
    };
    draw(null, null);
    const face = printed(c, 2.72, 4.72); face.position.z = 0.16; body.add(face);
    return { set: (v, tau, hot) => { draw(v, tau, hot); face.material.map.needsUpdate = true; } };
  }

  press() {
    const x = STATION.press;
    this.frameC(x, 5.4);
    this.rail = this.at(this.block(9.8, 0.34, 0.5, "steel", 0.03), x, 5.2, 0);
    this.grip = new THREE.Group();
    const rod = this.block(0.26, 4.8, 0.26, "steel", 0.03); rod.position.y = 2.4;
    const jaw = this.block(1.2, 0.3, 0.84, "ink", 0.03);
    this.grip.add(rod, jaw); this.grip.position.set(x, 3, 0);
    this.scene.add(this.grip);
    const p = ink("Fix by the rule repairer. Repairer v1 runs on request", 0.46, { flat: true, color: CSS.graphite, size: 44, weight: 400 });
    p.position.set(x + 7.1, 0.03, 3);
    this.scene.add(p);
  }

  gateRow() {
    this.gates = STATION.gates.map((x) => { this.arch(x, 4.9, 2.3, "bone", 0.26, 0.26); return this.lamp(x, 2.98, 0); });
    const p = ink("FIVE CHECKS", 0.56, { flat: true, color: CSS.graphite, track: 5, size: 46 });
    p.position.set(STATION.gates[2], 0.03, -3.4); this.scene.add(p);
  }

  docks() {
    const x = STATION.dock, bay = (z, name, dz) => {
      const [c, g] = canvas(1080, 560);
      g.strokeStyle = CSS.ink; g.lineWidth = 10; g.strokeRect(8, 8, 1064, 544);
      const m = printed(c, 11.6, 6, { flat: true }); m.position.set(x, 0.022, z); this.scene.add(m);
      const t = ink(name, 1.7, { flat: true, size: 100, weight: 700, track: 6 });
      t.position.set(x - 5.75 + t.geometry.parameters.width / 2, 0.03, z + dz); this.scene.add(t);
    };
    bay(LANE.send, "SENT", -4.1); bay(LANE.hold, "WITHHELD", 4.1);
    this.sentLamp = this.lamp(x + 6.6, 0.22, LANE.send - 2.4); this.holdLamp = this.lamp(x + 6.6, 0.22, LANE.hold + 2.4);
    this.lid = this.at(this.block(11, 0.34, 5.4), x, 8.5, LANE.hold);
    const face = ink("WITHHELD", 1.5, { flat: true, size: 90, weight: 700, track: 8 }); face.position.y = 0.18; this.lid.add(face);
    this.lid.visible = false;
  }

  // ---------------------------------------------------------------- the report
  book() {
    this.bookGroup = new THREE.Group();
    this.bookGroup.position.set(0, 0.2, -11.8);
    this.bookGroup.rotation.x = -0.88;
    const W = 15.4, H = 12, pad = this.block(2 * W + 0.8, H + 0.7, 0.36);
    pad.position.set(0, H / 2, -0.2); this.bookGroup.add(pad);
    this.pageSize = { W, H };
    this.pages = [-1, 1].map((s) => {
      const [c, g] = canvas(2048, 1596);
      const face = printed(c, W, H);
      face.position.set(s * (W / 2 + 0.06), H / 2, 0);
      this.bookGroup.add(face);
      return { c, g, face, tableId: null };
    });
    this.scene.add(this.bookGroup);
  }

  // draws the report's tables on the two pages and notes where every cell sits
  setReport(report) {
    this.cellIndex.clear();
    const tables = (report && report.evidence && report.evidence.tables) || [];
    this.pages.forEach((p, i) => this.drawPage(p, tables[i] || null, report ? report.name : ""));
  }

  drawPage(page, table, reportName) {
    const { c, g } = page, W = c.width, H = c.height;
    g.fillStyle = "#fbf8f0"; g.fillRect(0, 0, W, H);
    if (!table) { page.face.material.map.needsUpdate = true; return; }
    const rows = table.rows, cols = table.columns, m = 56;
    g.fillStyle = CSS.graphite; g.font = `500 28px ${SANS}`; g.textBaseline = "alphabetic"; g.fillText(reportName.toUpperCase(), m, 56);
    g.fillStyle = CSS.ink; g.font = `700 44px ${SANS}`; g.fillText((table.title || "").slice(0, 70), m, 108);
    const unit = `${table.currency || ""}${table.scale === 3 ? " thousands" : table.scale === 6 ? " millions" : ""}`.trim();
    g.fillStyle = CSS.graphite; g.font = `400 26px ${SANS}`; g.textAlign = "right"; g.fillText(unit, W - m, 108); g.textAlign = "left";
    const top = 150, rowH = Math.min(46, (H - top - 40) / (rows.length + 1)), labelW = W * 0.44, colW = (W - 2 * m - labelW) / Math.max(cols.length, 1);
    const size = Math.max(15, Math.floor(rowH * 0.62));
    g.font = `600 ${Math.max(14, size - 4)}px ${SANS}`; g.fillStyle = CSS.graphite; g.textAlign = "right";
    cols.forEach((col, i) => g.fillText(String(col.label || "").slice(0, Math.floor(colW / 9)), m + labelW + (i + 1) * colW - 8, top + rowH * 0.7));
    g.strokeStyle = CSS.ink; g.lineWidth = 2; g.beginPath(); g.moveTo(m, top + rowH); g.lineTo(W - m, top + rowH); g.stroke();
    rows.forEach((row, r) => {
      const y = top + rowH * (r + 1);
      if (r % 2 === 1) { g.fillStyle = "rgba(120,140,136,0.08)"; g.fillRect(m, y, W - 2 * m, rowH); }
      g.textAlign = "left"; g.fillStyle = CSS.ink; g.font = `400 ${size}px ${SANS}`;
      let label = String(row.label || "");
      while (g.measureText(label).width > labelW - 12 && label.length > 4) label = label.slice(0, -2);
      g.fillText(label, m + 6, y + rowH * 0.72);
      g.textAlign = "right"; g.font = `400 ${size}px ${SANS}`;
      row.cells.forEach((cell, i) => {
        if (!cell) return;
        g.fillText(cell.text || "", m + labelW + (i + 1) * colW - 8, y + rowH * 0.72);
        this.cellIndex.set(cell.id, { page, x0: (m + labelW + i * colW) / W, x1: (m + labelW + (i + 1) * colW) / W, y0: y / H, y1: (y + rowH) / H,
          lx0: m / W, label: row.label });
      });
    });
    g.textAlign = "left";
    page.face.material.map.needsUpdate = true;
    page.tableId = table.id;
  }

  cellPoint(id) {
    const e = this.cellIndex.get(id);
    if (!e) return null;
    const { W, H } = this.pageSize, f = e.page.face;
    const p = V(f.position.x - W / 2 + W * (e.x0 + e.x1) / 2, H - H * (e.y0 + e.y1) / 2 + 0, 0.05);
    p.y = f.position.y + H / 2 - H * (e.y0 + e.y1) / 2;
    return this.bookGroup.localToWorld(p);
  }

  mark(id, color, keep = false) {
    const e = this.cellIndex.get(id);
    if (!e) return;
    const { W, H } = this.pageSize, f = e.page.face;
    const w = W * (e.x1 - e.x0), h = H * (e.y1 - e.y0);
    const m = new THREE.Mesh(new THREE.PlaneGeometry(w, h), new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.26, depthWrite: false, toneMapped: false }));
    m.position.set(f.position.x - W / 2 + W * (e.x0 + e.x1) / 2, f.position.y + H / 2 - H * (e.y0 + e.y1) / 2, 0.03);
    const box = new THREE.LineSegments(new THREE.EdgesGeometry(new THREE.PlaneGeometry(w, h)), new THREE.LineBasicMaterial({ color }));
    m.add(box);
    this.bookGroup.add(m); this.temp.push(m);
    return m;
  }

  // ---------------------------------------------------------------- the tray of type
  tokens(d) {
    const spans = [];
    for (const c of d.catch.claims) { spans.push({ start: c.start, end: c.end, claim: c }); if (c.direction_span) spans.push({ start: c.direction_span[0], end: c.direction_span[1], word: true }); }
    const changes = this.changesOf(d);
    for (const ch of changes) spans.push({ start: ch.from, end: ch.to, change: true });
    spans.sort((a, b) => a.start - b.start || b.end - a.end);
    const merged = [];
    for (const s of spans) {
      const last = merged[merged.length - 1];
      if (last && s.start < last.end) { last.end = Math.max(last.end, s.end); last.claim = last.claim || s.claim; continue; }
      merged.push({ ...s });
    }
    const out = [], text = d.answer;
    let pos = 0;
    const plain = (a, b) => { for (const m of text.slice(a, b).matchAll(/\S+/g)) out.push({ text: m[0], start: a + m.index, end: a + m.index + m[0].length }); };
    for (const s of merged) { plain(pos, s.start); out.push({ text: text.slice(s.start, s.end), start: s.start, end: s.end, claim: s.claim, atom: true }); pos = s.end; }
    plain(pos, text.length);
    return out;
  }

  // the changes of the released fix, placed back on the original text
  changesOf(d) {
    const check = d.output.action === "repair" && d.correct.rule && d.correct.rule.check;
    if (!check || !check.changes) return [];
    let shift = 0;
    return check.changes.map((c) => { const from = c.start - shift, to = from + c.old.length; shift += c.new.length - c.old.length; return { ...c, from, to }; });
  }

  paintBlock(b, { color, mark, strike } = {}) {
    const { canvas: c, ctx: x, mesh: top } = b.face;
    x.clearRect(0, 0, c.width, c.height);
    x.fillStyle = color || (b.atom ? CSS.ink : CSS.graphite);
    x.font = `${b.atom ? 600 : 400} ${FONT_PX}px ${SERIF}`; x.textBaseline = "middle"; x.textAlign = "center";
    const room = c.width - (mark ? 76 : 20), wide = x.measureText(b.text).width;
    if (wide > room) { x.font = `${b.atom ? 600 : 400} ${Math.floor(FONT_PX * room / wide)}px ${SERIF}`; }
    x.fillText(b.text, (mark ? (c.width - 58) / 2 : c.width / 2), c.height * 0.53);
    if (strike) { x.strokeStyle = CSS.red; x.lineWidth = 7; x.lineCap = "round"; x.beginPath(); x.moveTo(10, c.height * 0.6); x.lineTo(c.width - 62, c.height * 0.46); x.stroke(); }
    if (mark) tick(x, c.width - 34, c.height / 2, 42, mark, MARK[mark]);
    top.material.map.needsUpdate = true;
  }

  makeBlock(tok, width) {
    const h = tok.atom ? 0.34 : 0.13, w = width;
    const g = new THREE.Group();
    const body = this.block(w, h, BLOCK_DEPTH, tok.atom ? "bone" : "card", 0.035);
    body.position.y = h / 2;
    const [c, x] = canvas(Math.ceil(w * PX), Math.ceil(BLOCK_DEPTH * PX));
    const top = printed(c, w, BLOCK_DEPTH, { flat: true });
    top.position.y = h + 0.006;
    g.add(body, top);
    const b = { ...tok, group: g, width: w, height: h, face: { canvas: c, ctx: x, mesh: top } };
    this.paintBlock(b);
    return b;
  }

  buildTray(d) {
    const [, m] = canvas(8, 8);
    const toks = this.tokens(d), rows = [[]];
    let used = 0;
    for (const t of toks) {
      m.font = `${t.atom ? 600 : 400} ${FONT_PX}px ${SERIF}`;
      const w = Math.min(MAX_ROW, m.measureText(t.text).width / PX + 0.2);
      if (used + w > MAX_ROW && rows[rows.length - 1].length) { rows.push([]); used = 0; }
      rows[rows.length - 1].push({ tok: t, w }); used += w + 0.09;
    }
    rows.length = Math.min(rows.length, MAX_ROWS);
    const n = rows.length, depth = n * ROW + 0.5, inner = Math.max(...rows.map((r) => r.reduce((a, b) => a + b.w + 0.09, -0.09))), width = inner + 0.7;
    const group = new THREE.Group();
    const plate = this.block(width, 0.14, depth, "ink", 0.03);
    plate.position.y = 0.2; group.add(plate);
    const blocks = [];
    rows.forEach((row, r) => {
      let x = -inner / 2;
      for (const { tok, w } of row) {
        const b = this.makeBlock(tok, w);
        b.home = V(x + w / 2, 0.27, (r - (n - 1) / 2) * ROW);
        b.group.position.copy(b.home); b.row = r;
        group.add(b.group); blocks.push(b);
        x += w + 0.09;
      }
    });
    this.scene.add(group);
    return { group, blocks, depth, plate };
  }

  blockFor(start) { return this.tray.blocks.find((b) => b.start <= start && start < b.end); }

  // ---------------------------------------------------------------- motion
  frame() {
    const dt = Math.min(this.clock.getDelta(), 0.05);
    this.time += dt;
    for (const t of [...this.tweens]) {
      if (t.run !== this.run) { this.tweens.splice(this.tweens.indexOf(t), 1); t.done(); continue; }
      t.at += dt * this.pace;
      const k = Math.min(t.at / t.dur, 1);
      t.fn(t.ease(k));
      if (k >= 1) { this.tweens.splice(this.tweens.indexOf(t), 1); t.done(); }
    }
    if (this.aiActive) this.aiLamp.material.color.setHex(Math.sin(this.time * 7) > 0 ? HEX.blue : 0xb5b0a3);
    const { pos, tgt } = this.view;
    const drift = Math.sin(this.time * 0.22) * 0.6;
    this.camera.position.set(pos.x + drift, pos.y, pos.z);
    this.camera.lookAt(tgt);
    this.renderer.render(this.scene, this.camera);
  }

  resize() {
    const w = this.el.clientWidth || window.innerWidth, h = this.el.clientHeight || window.innerHeight;
    this.size = { w, h };
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  tween(dur, fn, e = ease.inOut) {
    const run = this.run;
    if (this.instant) { fn(1); return Promise.resolve(); }  // the browser check runs without waiting for frames
    return new Promise((done) => this.tweens.push({ dur: Math.max(dur, 0.001), at: 0, fn, ease: e, run, done }));
  }

  fly(name, dur = 1.1) {
    const v = typeof name === "string" ? VIEWS[name] : name;
    const a = { pos: this.view.pos.clone(), tgt: this.view.tgt.clone() };
    return this.tween(dur, (k) => { this.view.pos.lerpVectors(a.pos, v.pos, k); this.view.tgt.lerpVectors(a.tgt, v.tgt, k); });
  }

  // look at one table cell (a number was clicked)
  flyToCell(id) {
    const p = this.cellPoint(id);
    if (!p) return false;
    this.showOnly([id]);
    this.fly({ pos: p.clone().add(V(0, 10, 13.5)), tgt: p }, 1.2);
    return true;
  }

  showOnly(ids, color = HEX.blue) {
    this.temp.filter((m) => m.userData.focus).forEach((m) => { m.parent.remove(m); });
    this.temp = this.temp.filter((m) => !m.userData.focus);
    for (const id of ids) { const m = this.mark(id, color); if (m) m.userData.focus = true; }
  }

  thread(from, to, color, lift = 7) {
    const mid = from.clone().lerp(to, 0.5); mid.y += lift;
    const curve = new THREE.QuadraticBezierCurve3(from, mid, to);
    const geo = new THREE.TubeGeometry(curve, 64, 0.045, 6);
    const mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({ color, toneMapped: false, transparent: true }));
    geo.setDrawRange(0, 0);
    this.scene.add(mesh); this.temp.push(mesh);
    return { mesh, curve, draw: (k) => geo.setDrawRange(0, Math.floor(geo.index.count * k)) };
  }

  clearRun() {
    this.run++;
    if (this.tray) { this.scene.remove(this.tray.group); this.tray.blocks.forEach((b) => { b.face.mesh.material.map.dispose(); b.face.mesh.material.dispose(); b.face.mesh.geometry.dispose(); }); this.tray = null; }
    for (const m of this.temp) { m.parent && m.parent.remove(m); if (m.geometry && !m.isGroup) m.geometry.dispose(); if (m.material) m.material.dispose(); }
    this.temp = [];
    this.gaugeA.set(null, null); this.gaugeB.set(null, null);
    this.disk.rotation.y = 0;
    this.gates.forEach((g) => g.material.color.setHex(0xb5b0a3));
    this.sentLamp.material.color.setHex(0xb5b0a3); this.holdLamp.material.color.setHex(0xb5b0a3);
    this.grip.position.set(STATION.press, 3, 0); this.rail.position.z = 0; this.lid.visible = false; this.lid.position.y = 8.5;
    this.scan.material.opacity = 0; this.aiActive = false; this.aiLamp.material.color.setHex(0xb5b0a3);
  }

  async along(path, dur, e = ease.inOut, turn = true) {
    const g = this.tray.group, p = this.paths[path];
    const run = this.run;
    await this.tween(dur, (k) => {
      const at = p.getPointAt(Math.min(k, 0.9999)), t = p.getTangentAt(Math.min(k, 0.9999));
      g.position.set(at.x, 0, at.z);
      if (turn) g.rotation.y = -Math.atan2(t.z, t.x);
    }, e);
    if (run !== this.run) throw STOP;
  }

  // the AI is writing: real wait, ended by the caller
  thinking(on) { this.aiActive = on; if (!on) this.aiLamp.material.color.setHex(HEX.green); }

  // ---------------------------------------------------------------- one answer through the machine
  async play(d, { marks, on = () => {}, skipIntro = false } = {}) {
    this.clearRun();
    this.pace = 1.2;
    const run = this.run;
    const go = async (p) => { await p; if (run !== this.run) throw STOP; };
    const pause = (s) => this.tween(s, () => {}, ease.linear);
    try {
      this.tray = this.buildTray(d);
      const { group, blocks } = this.tray;
      group.position.set(STATION.start, 0, 0);
      const claims = d.catch.claims, action = d.output.action, wanted = d.control.action;

      // the answer is set in type
      on("set");
      await go(this.fly("source", skipIntro ? 0.6 : 0.9));
      blocks.forEach((b) => { b.group.position.y = 3.2; b.group.visible = false; });
      const each = Math.min(0.08, 1.3 / blocks.length);
      await go(Promise.all(blocks.map((b, i) => (async () => {
        await this.tween(each * i, () => {}, ease.linear); b.group.visible = true;
        await this.tween(0.32, (k) => { b.group.position.y = 3.2 + (b.home.y - 3.2) * k; }, ease.out);
      })())));
      await go(pause(0.35));

      // 1 Catch
      on("catch-start");
      await go(Promise.all([this.fly("catch", 1.2), this.along("toCatch", 1.2)]));
      this.scan.material.opacity = 1;
      const stops = claims.length ? Math.min(0.7, 3.4 / claims.length) : 0.5;
      const threads = [];
      let i = 0;
      for (const c of claims) {
        const b = this.blockFor(c.start), mark = marks[c.id] || "unsure";
        if (!b) { on("claim", { claim: c, mark, index: ++i }); continue; }  // past the rows the tray shows
        const color = { ok: HEX.green, bad: HEX.red, unsure: HEX.ochre }[mark];
        const ids = mark === "bad" && c.came_from.length ? c.came_from : c.asked.length ? c.asked : c.cells;
        await go(this.tween(stops * 0.3, (k) => { b.group.position.y = b.home.y + Math.sin(k * Math.PI) * 0.32; }));
        const from = group.localToWorld(b.group.position.clone().add(V(0, b.height, 0)));
        const lines = ids.map((id) => { const to = this.cellPoint(id); return to ? this.thread(from, to, color) : null; }).filter(Boolean);
        await go(this.tween(stops * 0.7, (k) => lines.forEach((l) => l.draw(k)), ease.out));
        threads.push(...lines);
        ids.forEach((id) => this.mark(id, color));
        if (mark === "bad" && c.asked.length) c.asked.forEach((id) => { if (!ids.includes(id)) this.mark(id, HEX.blue); });
        this.paintBlock(b, { color: MARK[mark], mark });
        on("claim", { claim: c, mark, index: ++i });
      }
      if (!claims.length) await go(pause(0.6));
      await go(pause(0.55));
      this.scan.material.opacity = 0;
      threads.forEach((t) => { t.mesh.material.opacity = 0.32; });

      // 2 Control
      on("control-start");
      const o = d.control.outcome;
      threads.forEach((t) => { t.mesh.visible = false; });
      await go(Promise.all([this.fly("control", 1.1), this.along("toControl", 1.1)]));
      if (o) {
        const hotA = o.p_unsafe < o.tau_send ? CSS.green : CSS.red;
        for (let k = 0; k <= 1; k += 0.1) { this.gaugeA.set(o.p_unsafe * ease.out(k), o.tau_send, hotA); await go(pause(0.05)); }
        this.gaugeA.set(o.p_unsafe, o.tau_send, hotA);
        await go(pause(0.25));
        if (o.p_unsafe >= o.tau_send) {
          const hotB = o.p_fix > o.tau_fix ? CSS.green : CSS.red;
          for (let k = 0; k <= 1; k += 0.1) { this.gaugeB.set(o.p_fix * ease.out(k), o.tau_fix, hotB); await go(pause(0.05)); }
          this.gaugeB.set(o.p_fix, o.tau_fix, hotB);
          await go(pause(0.25));
        }
      }
      on("control", { action: wanted });

      // the turntable points the tray at its lane
      const lane = wanted === "send" ? "send" : wanted === "repair" ? "fix" : "hold";
      const start = this.paths[lane].getTangentAt(0.001), angle = -Math.atan2(start.z, start.x);
      await go(this.tween(0.65, (k) => { this.disk.rotation.y = angle * k; group.rotation.y = angle * k; }, ease.back));
      await go(pause(0.2));

      let route = lane;
      if (lane === "fix") {
        // 3 Correct
        on("correct-start");
        await go(Promise.all([this.fly("correct", 1.2), this.along("fix", 1.2)]));
        const rule = d.correct.rule, changes = this.changesOf(d);
        on("program", { rule });
        await go(pause(0.4));
        let lifted = 0;
        for (const ch of changes) {
          const b = this.blockFor(ch.from);
          if (!b) continue;
          const shiftX = b.home.x + (group.position.x - STATION.press);
          const old = b.group;
          // the gripper moves over the block and pulls it out; nothing else on the tray moves
          await go(this.tween(0.4, (k) => { this.grip.position.x = STATION.press + shiftX * k; this.grip.position.z = b.home.z * k; this.rail.position.z = b.home.z * k; }));
          await go(this.tween(0.32, (k) => { this.grip.position.y = 3 + (0.95 - 3) * k; }));
          this.paintBlock(b, { color: CSS.red, mark: "bad", strike: true });
          await go(this.tween(0.42, (k) => { this.grip.position.y = 0.95 + (3 - 0.95) * k; old.position.y = b.home.y + (2.4 - b.home.y) * k; }));
          this.scene.attach(old); this.temp.push(old);
          const p0 = old.position.clone();
          await go(this.tween(0.5, (k) => { old.position.z = p0.z + (3.4 - p0.z) * k; old.position.y = p0.y + (0.02 - p0.y) * k * k; old.rotation.y = 0.4 * k; }, ease.linear));
          lifted++;
          // the new block comes from the table cell it was computed from
          const ids = ch.cells || [];
          const nb = this.makeBlock({ text: ch.new, atom: true, start: ch.from, end: ch.to }, Math.max(b.width, Math.min(4.2, ch.new.length * 0.17 + 0.2)));
          nb.home = b.home.clone(); nb.group.position.copy(b.home); nb.group.position.y = 3.0;
          group.add(nb.group);
          this.paintBlock(nb, { color: CSS.green, mark: "ok" });
          const target = group.localToWorld(nb.group.position.clone());
          ids.forEach((id) => this.mark(id, HEX.green));
          const paths = ids.map((id) => { const f = this.cellPoint(id); return f ? this.thread(f, target, HEX.green, 6) : null; }).filter(Boolean);
          nb.group.visible = false;
          await go(this.tween(0.75, (k) => paths.forEach((l) => l.draw(k)), ease.out));
          nb.group.visible = true;
          await go(this.tween(0.42, (k) => { nb.group.position.y = 3.0 + (b.home.y - 3.0) * k; }, ease.back));
          this.tray.blocks.push(nb);
          // a wider block pushes its neighbours along the row, and only those
          const extra = nb.width - b.width;
          if (extra > 0) {
            const next = this.tray.blocks.filter((x) => x.row === b.row && x !== b && x !== nb && x.home.x > b.home.x);
            await go(this.tween(0.2, (k) => next.forEach((x) => { x.group.position.x = x.home.x + extra * k; })));
          }
          paths.forEach((l) => { l.mesh.material.opacity = 0.25; });
          await go(this.tween(0.3, (k) => { this.grip.position.x = STATION.press + shiftX * (1 - k); this.grip.position.z = b.home.z * (1 - k); this.rail.position.z = b.home.z * (1 - k); }));
          on("changed", { change: ch, index: lifted });
        }
        await go(pause(0.3));
        const checks = (rule && rule.check && rule.check.checks) || [];
        if (checks.length) {
          await go(this.fly("gates", 1.0));
          const dur = 2.3;
          const run2 = this.along("gates", dur, ease.linear);
          for (let n = 0; n < this.gates.length; n++) {
            await go(pause(dur / this.gates.length * 0.92));
            const ok = checks[n] ? checks[n].passed : true;
            this.gates[n].material.color.setHex(ok ? HEX.green : HEX.red);
            on("gate", { index: n, check: checks[n], ok });
          }
          await go(run2);
        } else {
          await go(this.along("gates", 1.4));
        }
        route = action === "repair" ? "pass" : "fail";
      }

      // the end of the line
      const sent = action === "send" || action === "repair";
      on("exit-start");
      const shot = sent ? "sent" : "held";
      const leg = route === "fix" ? "hold" : route;
      await go(Promise.all([this.fly(shot, 1.7), this.along(leg, 1.8)]));
      group.rotation.y = 0;
      if (sent) this.sentLamp.material.color.setHex(HEX.green);
      else {
        this.holdLamp.material.color.setHex(HEX.red);
        this.lid.visible = true;
        await go(this.tween(0.7, (k) => { this.lid.position.y = 8.5 + (1.05 - 8.5) * k; }, ease.out));
      }
      on("done");
    } catch (err) {
      if (err !== STOP) throw err;
    }
  }
}
