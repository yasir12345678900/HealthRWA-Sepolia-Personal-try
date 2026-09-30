// CA2 deck generator: reads plan.json + content.json (or mock.json) and writes the .pptx
const fs = require("fs");
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const fa = require("react-icons/fa6");

const D = __dirname;
const CONTENT = process.argv[2] || path.join(D, "content.json");
const OUT = process.argv[3] || path.join(D, "Yasir_Alyoubi_CA2_Presentation.pptx");
const plan = JSON.parse(fs.readFileSync(path.join(D, "plan.json"), "utf8"));
const raw = JSON.parse(fs.readFileSync(CONTENT, "utf8"));
const content = {};
(raw.groups ? raw.groups.flatMap(g => g.slides) : raw.slides).forEach(s => { content[s.id] = s; });

// ---------------------------------------------------------------- design tokens
const C = {
  petrol: "0E3B43", teal: "13707B", tealDark: "0B5560", gold: "D4A12A", goldDark: "9A7414",
  ink: "1C2B31", muted: "5E6E73", card: "EEF4F5", panel: "F4F8F9", goldTint: "FBF1D3",
  line: "D5E0E2", white: "FFFFFF", mist: "CFE3E6", grey: "8A989C",
};
const HF = "Cambria", BF = "Calibri";
const W = 13.333, H = 7.5, MX = 0.6;
const TOTAL = plan.length;

// ---------------------------------------------------------------- helpers
const iconCache = {};
async function iconPng(name, color) {
  const key = name + color;
  if (iconCache[key]) return iconCache[key];
  const Comp = fa[name] || fa.FaCircleCheck;
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { size: 256, color: "#" + color }));
  const buf = await sharp(Buffer.from(svg)).resize(256, 256, { fit: "contain", background: { r: 0, g: 0, b: 0, alpha: 0 } }).png().toBuffer();
  iconCache[key] = "image/png;base64," + buf.toString("base64");
  return iconCache[key];
}
const ICONS = [
  [/guardian|parent/i, "FaUserShield"], [/patient/i, "FaHospitalUser"],
  [/doctor|professional|clinician|practitioner|requester/i, "FaUserDoctor"],
  [/auditor|audit|traceab/i, "FaMagnifyingGlassChart"], [/institution|organisation|hospital/i, "FaBuildingColumns"],
  [/privacy act|act 19|act 20|\blaw|regulat|principle|legal/i, "FaScaleBalanced"],
  [/identifier|identity|\bdid|credential|\bvc\b/i, "FaIdCard"],
  [/threshold|multi-party|approval|collective/i, "FaUsers"], [/policy|purpose|scope/i, "FaFilter"],
  [/lifecycle|temporal|time|expir|revoc/i, "FaClock"], [/evidence|record|ledger|log/i, "FaFileShield"],
  [/blockchain|chain|token|sbt|anchor|sepolia/i, "FaLink"], [/consent/i, "FaFileSignature"],
  [/\bmodel\b|data|state/i, "FaDatabase"], [/controller|enforce|decision/i, "FaGears"], [/\bview\b|interface/i, "FaDisplay"],
  [/test|valid|assurance|formal|scenario/i, "FaFlask"], [/architecture|layer|mvc/i, "FaSitemap"],
  [/implementation|prototype|halah|code|software/i, "FaCode"], [/publication|paper|journal/i, "FaBookOpen"],
  [/limitation|mock|placeholder|not yet|gap/i, "FaTriangleExclamation"], [/secur|protect|trust/i, "FaShieldHalved"],
];
function iconMatch(text) { for (const [re, n] of ICONS) if (re.test(text || "")) return n; return null; }
function iconFor(text) { return iconMatch(text) || "FaCircleCheck"; }
function iconOf(p, head, body) { return (p && p.icon) || iconMatch(head) || iconFor(head + " " + body); }

// plain text with V_I style subscripts -> pptxgenjs runs
const SUB = /(^|[^A-Za-z0-9_])([A-Za-z]|id)_([A-Za-z]{1,10}|\d)(?![A-Za-z0-9])/g;
function runs(text, opts = {}) {
  text = String(text == null ? "" : text);
  if (text.includes("\n")) {
    const lines = text.split("\n"), out = [];
    lines.forEach((ln, i) => { const r = runs(ln, opts); if (i < lines.length - 1) r[r.length - 1].options.breakLine = true; out.push(...r); });
    return out;
  }
  const out = []; let last = 0; let m;
  SUB.lastIndex = 0;
  while ((m = SUB.exec(text))) {
    const start = m.index + m[1].length;
    if (start > last) out.push({ text: text.slice(last, start), options: { ...opts } });
    out.push({ text: m[2], options: { ...opts } });
    out.push({ text: m[3], options: { ...opts, baseline: -500, _sub: true } });
    last = start + m[2].length + 1 + m[3].length;
  }
  if (last < text.length) out.push({ text: text.slice(last), options: { ...opts } });
  return out.length ? out : [{ text: "", options: { ...opts } }];
}
// several paragraphs -> runs with breakLine between
function paras(list, opts = {}, spaceAfter = 0) {
  const out = [];
  list.forEach((p, i) => {
    const r = runs(p.text, { ...opts, ...(p.options || {}) });
    if (i < list.length - 1) { r[r.length - 1].options.breakLine = true; }
    if (spaceAfter) r.forEach(x => { x.options.paraSpaceAfter = spaceAfter; });
    out.push(...r);
  });
  return out;
}
const arr = (x) => Array.isArray(x) ? x : (x ? [x] : []);
const pick = (o, ...keys) => { for (const k of keys) if (o && o[k] != null && o[k] !== "") return o[k]; return undefined; };
function imgSize(file) {
  const b = fs.readFileSync(file); // PNG IHDR
  return { w: b.readUInt32BE(16), h: b.readUInt32BE(20) };
}
function fit(file, bx, by, bw, bh) {
  const { w, h } = imgSize(file); const r = w / h;
  let iw = bw, ih = bw / r; if (ih > bh) { ih = bh; iw = bh * r; }
  return { x: bx + (bw - iw) / 2, y: by + (bh - ih) / 2, w: iw, h: ih };
}
function subFix(text, fsz) {
  if (!Array.isArray(text)) return { text, has: false };
  let has = false;
  const out = text.map(r => {
    if (!r || !r.options || !r.options._sub) return r;
    has = true;
    const { _sub, ...rest } = r.options;
    return { text: r.text, options: { ...rest, fontSize: +(((rest.fontSize || fsz) * 1.18).toFixed(1)) } };
  });
  return { text: out, has };
}
// text measurement with the metric-compatible fonts (Carlito = Calibri, Caladea = Cambria)
const MET = JSON.parse(fs.readFileSync(path.join(D, "metrics.json"), "utf8"));
function tw(str, face, bold, italic, size) {
  const key = face === HF ? (bold ? "Cambria-b" : "Cambria") : ("Calibri" + (bold && italic ? "-bi" : bold ? "-b" : italic ? "-i" : ""));
  const m = MET[key] || MET.Calibri; let w = 0;
  for (const ch of str) w += m[ch] != null ? m[ch] : 0.55;
  return w * size / 72;
}
// lines needed for a run list in a box of width widthIn (greedy wrap at spaces, explicit breaks respected)
function wrapCount(text, widthIn, o) {
  const list = Array.isArray(text) ? text : [{ text: String(text), options: {} }];
  let lines = 1, cur = 0, word = 0;
  const flush = () => { if (cur + word > widthIn + 1e-6 && cur > 0) { lines++; cur = word; } else cur += word; word = 0; };
  for (const r of list) {
    const ro = r.options || {};
    const size = (ro.fontSize || o.fontSize || 18) * (ro._sub || ro.baseline ? 0.66 : 1);
    const face = ro.fontFace || o.fontFace || BF, bold = ro.bold != null ? ro.bold : o.bold, italic = ro.italic != null ? ro.italic : o.italic;
    for (const ch of String(r.text)) {
      if (ch === " ") { flush(); cur += tw(" ", face, bold, italic, size); }
      else { word += tw(ch, face, bold, italic, size); if (ch === "-" || ch === "/") flush(); }
    }
    if (ro.breakLine) { flush(); lines++; cur = 0; }
  }
  flush();
  return lines;
}
function estLines(text, widthIn, fsz, k, face = BF, bold = false) { return wrapCount([{ text, options: {} }], widthIn, { fontSize: fsz, fontFace: face, bold }); }
const WARN = []; let CUR = 0;
function T(slide, text, o) {
  const fsz = o.fontSize || 18;
  const f = subFix(text, fsz);
  const extra = (f.has && !o.lineSpacing && !o.lineSpacingMultiple) ? { lineSpacing: Math.round(fsz * 1.22) } : {};
  if (o.w && o.h && !o.rotate && !o.fit) {
    const n = wrapCount(Array.isArray(text) ? text : [{ text: String(text), options: {} }], o.w - (o.margin ? 0.1 : 0) - 0.02, o);
    const lh = (extra.lineSpacing || o.lineSpacing || fsz * 1.2 * (o.lineSpacingMultiple || 1)) / 72;
    const need = n * lh;
    if (need > o.h + 0.04) WARN.push(`slide ${CUR}: ${n} lines need ${need.toFixed(2)} in > box ${o.h.toFixed(2)} in: "${(Array.isArray(text) ? text.map(r => r.text).join("") : String(text)).slice(0, 70)}"`);
  }
  slide.addText(f.text, { isTextBox: true, fontFace: BF, color: C.ink, margin: 0, valign: "top", ...o, ...extra });
}

// ---------------------------------------------------------------- frames
const NUM = {}; plan.forEach((p, i) => { NUM[p.id] = i + 1; });
function footer(slide, id) {
  T(slide, "A Trusted Authorisation Framework for Multi-Party Patient Consent  ·  CA2", { x: MX, y: 7.02, w: 8, h: 0.28, fontSize: 10, color: C.muted, valign: "middle" });
  T(slide, `${NUM[id]} / ${TOTAL}`, { x: W - MX - 1.5, y: 7.02, w: 1.5, h: 0.28, fontSize: 10, color: C.muted, align: "right", valign: "middle" });
}
function frame(pres, id, s, opt = {}) {
  const slide = pres.addSlide();
  slide.background = { color: C.white };
  if (s && s.notes) slide.addNotes(s.notes);
  if (opt.bare) return slide;
  const title = (s && s.title) || "";
  const size = title.length > 50 ? 26 : title.length > 40 ? 28 : 30;
  T(slide, runs(title), { x: MX, y: 0.42, w: W - 2 * MX, h: 0.75, fontFace: HF, fontSize: size, bold: true, color: C.petrol, valign: "middle", fit: "shrink" });
  if (s && s.subtitle && !opt.noSubtitle) T(slide, runs(s.subtitle), { x: MX, y: 1.17, w: W - 2 * MX, h: 0.42, fontSize: 15, color: C.muted, valign: "middle" });
  footer(slide, id);
  return slide;
}
function dark(pres, s) {
  const slide = pres.addSlide();
  slide.background = { color: C.petrol };
  if (s && s.notes) slide.addNotes(s.notes);
  return slide;
}
async function badge(slide, x, y, d, iconName, fill = C.teal, iconColor = C.white) {
  slide.addShape("ellipse", { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
  const pad = d * 0.24;
  slide.addImage({ data: await iconPng(iconName, iconColor), x: x + pad, y: y + pad, w: d - 2 * pad, h: d - 2 * pad });
}
function numBadge(slide, x, y, d, label, fill = C.teal, color = C.white, size = 14) {
  slide.addShape("ellipse", { x, y, w: d, h: d, fill: { color: fill }, line: { color: fill } });
  T(slide, String(label), { x, y, w: d, h: d, fontSize: size, bold: true, color, align: "center", valign: "middle", fontFace: BF });
}
function figPanel(slide, file, bx, by, bw, bh, caption) {
  slide.addShape("roundRect", { x: bx, y: by, w: bw, h: bh, fill: { color: C.panel }, line: { color: C.line, width: 0.75 }, rectRadius: 0.08 });
  const capH = caption ? 0.34 : 0;
  const f = fit(file, bx + 0.15, by + 0.15, bw - 0.3, bh - 0.3 - capH);
  slide.addImage({ path: file, ...f, altText: caption || path.basename(file) });
  f.px = imgSize(file);
  if (caption) T(slide, caption, { x: bx + 0.15, y: by + bh - 0.42, w: bw - 0.3, h: 0.32, fontSize: 10.5, italic: true, color: C.muted, align: "center", valign: "middle" });
  return f;
}
// gold outlines with a short label over regions of a screenshot (region coordinates in image pixels)
function highlights(slide, f, list) {
  const kx = f.w / f.px.w, ky = f.h / f.px.h;
  for (const [x0, y0, x1, y1, label, where] of list || []) {
    const X = f.x + x0 * kx, Y = f.y + y0 * ky, Wd = (x1 - x0) * kx, Hd = (y1 - y0) * ky;
    slide.addShape("roundRect", { x: X, y: Y, w: Wd, h: Hd, fill: { color: C.gold, transparency: 100 }, line: { color: C.gold, width: 2.25 }, rectRadius: 0.04 });
    const lw = Math.min(3.4, 0.2 + label.length * 0.085), lh = 0.28;
    const ly = where === "below" ? Y + Hd + 0.03 : where === "inside" ? Y + Hd - lh - 0.04 : where === "insideTop" ? Y + 0.05 : Y - lh - 0.03;
    const lx = (where === "inside" || where === "insideTop" || where === "aboveRight") ? X + Wd - lw - 0.06 : X;
    slide.addShape("roundRect", { x: lx, y: ly, w: lw, h: lh, fill: { color: C.gold }, line: { color: C.gold }, rectRadius: 0.06 });
    T(slide, label, { x: lx, y: ly, w: lw, h: lh, fontSize: 11, bold: true, color: C.petrol, align: "center", valign: "middle" });
  }
}
// stacked point list with icon badges
async function pointList(slide, points, x, y, w, h, opt = {}) {
  points = arr(points); if (!points.length) return;
  const gap = opt.gap != null ? opt.gap : 0.18;
  const rowH = (h - gap * (points.length - 1)) / points.length;
  const d = opt.badge || 0.46;
  for (let i = 0; i < points.length; i++) {
    const p = points[i]; const head = pick(p, "head", "label", "title") || ""; const body = pick(p, "body", "text", "desc") || "";
    const yy = y + i * (rowH + gap);
    if (opt.numbers) numBadge(slide, x, yy, d, i + 1, opt.fill || C.teal, opt.numColor || C.white, opt.numSize || 14);
    else await badge(slide, x, yy, d, iconOf(p, head, body), opt.fill || C.teal);
    T(slide, runs(head, { bold: true }), { x: x + d + 0.2, y: yy - 0.02, w: w - d - 0.2, h: 0.36, fontSize: opt.headSize || 16, color: C.petrol });
    T(slide, runs(body), { x: x + d + 0.2, y: yy + 0.34, w: w - d - 0.2, h: rowH - 0.34, fontSize: opt.bodySize || 13, color: C.ink });
  }
}
function styledTable(slide, header, rows, x, y, w, colW, opt = {}) {
  const hdr = header.map(hh => ({ text: runs(hh, { bold: true, color: C.white }), options: { fill: { color: C.petrol }, bold: true, color: C.white, valign: "middle" } }));
  const tfs = opt.fontSize || 12;
  const body = rows.map((r, ri) => r.map((cell, ci) => {
    const hi = opt.highlight && opt.highlight(r, ri);
    return { text: subFix(runs(cell, hi ? { bold: true } : {}), tfs).text, options: { fill: { color: hi ? C.goldTint : (opt.tint && opt.tint(r, ri)) ? C.goldTint : (ri % 2 ? C.panel : C.white) }, valign: "middle", bold: !!hi || (ci === 0 && opt.boldFirst) } };
  }));
  slide.addTable([hdr, ...body], { x, y, w, colW, fontFace: BF, fontSize: opt.fontSize || 12, color: C.ink, border: { type: "solid", pt: 0.5, color: C.line }, margin: opt.margin || [0.05, 0.08, 0.05, 0.08], rowH: opt.rowH, autoPage: false });
}
function blend(hex, t) { // t 0..1 from white to hex
  const a = [0, 2, 4].map(i => parseInt(hex.slice(i, i + 2), 16));
  return a.map(v => Math.round(255 + (v - 255) * t).toString(16).padStart(2, "0")).join("").toUpperCase();
}

// ---------------------------------------------------------------- layouts
const DG = require("./diagrams")({ T, runs });
const L = {};
L.title = async (pres, id, s) => {
  const slide = dark(pres, s);
  T(slide, "UTS  ·  CANDIDATURE ASSESSMENT 2", { x: MX, y: 0.6, w: 8, h: 0.35, fontSize: 13, bold: true, color: C.gold, charSpacing: 2 });
  T(slide, "A Trusted Authorisation Framework for Multi-Party Patient Consent in Healthcare Data Sharing", { x: MX, y: 1.25, w: 8.6, h: 2.3, fontFace: HF, fontSize: 38, bold: true, color: C.white, valign: "top" });
  T(slide, "Design, HALAH prototype and evidence for RO1–RO4, with the plan for RO5–RO6", { x: MX, y: 3.65, w: 8.6, h: 0.45, fontSize: 18, color: C.mist });
  T(slide, [
    { text: "Yasir Dhaifallah O Alyoubi", options: { bold: true, color: C.white, fontSize: 18, breakLine: true } },
    { text: "Student ID 24724078", options: { color: C.mist, fontSize: 14, breakLine: true } },
    { text: "Principal Supervisor: Professor Farookh Hussain", options: { color: C.mist, fontSize: 14, breakLine: true } },
    { text: "Co-Supervisor: Dr Firas Al-Doghman", options: { color: C.mist, fontSize: 14, breakLine: true } },
    { text: "September 2026", options: { color: C.gold, fontSize: 14, bold: true } },
  ], { x: MX, y: 4.55, w: 7, h: 2.2 });
  // motif: the five trust predicates
  const P = [["V_I", "Identity and authority"], ["V_A", "Approval"], ["V_P", "Policy"], ["V_T", "Time"], ["V_L", "Lifecycle"]];
  P.forEach(([sym, lab], i) => {
    const y = 0.95 + i * 1.12, x = 10.35, d = 0.86, cur = i < 3;
    slide.addShape("ellipse", { x, y, w: d, h: d, fill: { color: cur ? C.teal : C.petrol }, line: { color: C.gold, width: cur ? 0.75 : 1.5 } });
    T(slide, runs(sym, { bold: true }), { x, y, w: d, h: d, fontSize: 20, color: C.white, align: "center", valign: "middle", fontFace: HF });
    T(slide, lab, { x: x + d + 0.2, y: y + 0.08, w: 1.55, h: 0.7, fontSize: 14, color: cur ? C.white : C.mist, valign: "middle" });
  });
  slide.addShape("ellipse", { x: 10.35, y: 6.68, w: 0.2, h: 0.2, fill: { color: C.teal }, line: { color: C.gold, width: 0.75 } });
  T(slide, "current stage", { x: 10.62, y: 6.62, w: 1.25, h: 0.32, fontSize: 12, color: C.mist, valign: "middle" });
  slide.addShape("ellipse", { x: 11.85, y: 6.68, w: 0.2, h: 0.2, fill: { color: C.petrol }, line: { color: C.gold, width: 1.2 } });
  T(slide, "next stage", { x: 12.12, y: 6.62, w: 1.05, h: 0.32, fontSize: 12, color: C.mist, valign: "middle" });
};
L.agenda = async (pres, id, s) => {
  const slide = frame(pres, id, s, { noSubtitle: true });
  const items = arr(pick(s.fields, "items"));
  const letters = "ABCDE";
  const top = 1.55, rowH = 1.02;
  for (let i = 0; i < Math.min(items.length, 5); i++) {
    const it = items[i], y = top + i * rowH;
    numBadge(slide, MX + 0.1, y + 0.05, 0.72, letters[i], i % 2 ? C.teal : C.petrol, C.white, 22);
    T(slide, runs(pick(it, "head", "title") || "", { bold: true }), { x: MX + 1.1, y: y + 0.02, w: 10.8, h: 0.42, fontSize: 21, color: C.petrol, fontFace: HF });
    T(slide, runs(pick(it, "sub", "body") || ""), { x: MX + 1.1, y: y + 0.45, w: 10.8, h: 0.38, fontSize: 15, color: C.muted });
  }
};
L.divider = async (pres, id, s) => {
  const slide = dark(pres, s);
  const p = plan.find(x => x.id === id);
  slide.addShape("ellipse", { x: 1.1, y: 1.9, w: 3.4, h: 3.4, fill: { color: C.petrol }, line: { color: C.gold, width: 3 } });
  T(slide, p.part || "", { x: 1.1, y: 1.9, w: 3.4, h: 3.4, fontFace: HF, fontSize: 120, bold: true, color: C.gold, align: "center", valign: "middle" });
  const dt = s.title || ""; const dsz = 40;
  const tl = estLines(dt, 7.35, dsz, 0, HF, true), th = tl * dsz * 1.18 / 72;
  const line = pick(s.fields, "line") || s.subtitle || "";
  const dl = estLines(line, 7.15, 18), dh = dl * 18 * 1.22 / 72;
  const gh = 0.4 + 0.12 + th + 0.28 + dh, top = 3.6 - gh / 2;
  T(slide, `PART ${p.part}  ·  ${String(p.chapters || "").toUpperCase()}`, { x: 5.3, y: top, w: 7.4, h: 0.4, fontSize: 14, bold: true, color: C.gold, charSpacing: 2, valign: "middle" });
  T(slide, runs(dt), { x: 5.3, y: top + 0.52, w: 7.4, h: th + 0.05, fontFace: HF, fontSize: dsz, bold: true, color: C.white, valign: "top" });
  T(slide, runs(line), { x: 5.3, y: top + 0.52 + th + 0.28, w: 7.2, h: dh + 0.1, fontSize: 18, color: C.mist });
  T(slide, `${NUM[id]} / ${TOTAL}`, { x: W - MX - 1.5, y: 7.02, w: 1.5, h: 0.28, fontSize: 10, color: C.mist, align: "right", valign: "middle" });
};
L.statement = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const st = pick(s.fields, "statement") || "";
  const long = st.length > 100, fsz = long ? 22 : 28;
  const textH = estLines(st, 4.75, fsz, 0, HF, true) * fsz * 1.2 / 72;
  const cardY = 1.85, cardH = 4.2, groupH = 0.7 + 0.28 + textH, top = cardY + (cardH - groupH) / 2;
  slide.addShape("roundRect", { x: MX, y: cardY, w: 5.6, h: cardH, fill: { color: C.petrol }, line: { color: C.petrol }, rectRadius: 0.12 });
  await badge(slide, MX + 0.4, top, 0.7, long ? "FaCircleQuestion" : "FaKey", C.gold, C.petrol);
  T(slide, runs(st, { bold: true }), { x: MX + 0.4, y: top + 0.98, w: 4.8, h: textH + 0.1, fontFace: HF, fontSize: fsz, color: C.white, valign: "top" });
  await pointList(slide, pick(s.fields, "support", "points"), 6.75, 1.95, W - MX - 6.75, 4.1, { numbers: true, fill: C.gold, numColor: C.petrol, numSize: 16, headSize: 17, bodySize: 14, badge: 0.5 });
};
L.cards = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const cards = arr(pick(s.fields, "cards", "points"));
  const intro = pick(s.fields, "intro");
  let top = 1.8;
  if (intro) { T(slide, runs(intro), { x: MX, y: top, w: W - 2 * MX, h: 0.62, fontSize: 15, color: C.ink }); top += 0.8; }
  const n = cards.length, cols = n === 6 ? 3 : n, rows = Math.ceil(n / cols);
  const gap = 0.3, cw = (W - 2 * MX - gap * (cols - 1)) / cols, ch = (6.8 - top - gap * (rows - 1)) / rows;
  for (let i = 0; i < n; i++) {
    const c = cards[i], r = Math.floor(i / cols), k = i % cols;
    const x = MX + k * (cw + gap), y = top + r * (ch + gap);
    let head = pick(c, "head", "title") || ""; const body = pick(c, "body", "text") || "", foot = pick(c, "foot");
    slide.addShape("roundRect", { x, y, w: cw, h: ch, fill: { color: C.card }, line: { color: C.card }, rectRadius: 0.1 });
    const footH = foot ? 0.64 : 0;
    if (foot) T(slide, runs(foot, { bold: true }), { x: x + 0.22, y: y + ch - 0.62, w: cw - 0.44, h: 0.48, fontSize: 12.5, color: /\b3 of 33\b/.test(foot) ? C.goldDark : C.teal, valign: "bottom" });
    const req = head.match(/^Req (\d)\s+(.*)$/);
    if (req) {
      await badge(slide, x + 0.22, y + 0.22, 0.56, iconOf(c, req[2], body));
      T(slide, "REQ " + req[1], { x: x + 0.9, y: y + 0.22, w: cw - 1.1, h: 0.56, fontSize: 12.5, bold: true, color: C.teal, charSpacing: 1.5, valign: "middle" });
      T(slide, runs(req[2], { bold: true }), { x: x + 0.22, y: y + 0.95, w: cw - 0.44, h: 0.62, fontSize: 15, color: C.petrol, valign: "top" });
      T(slide, runs(body), { x: x + 0.22, y: y + 1.72, w: cw - 0.44, h: ch - 1.72 - footH - 0.05, fontSize: 14, color: C.ink });
    } else if (cw < 3.2) {
      await badge(slide, x + 0.25, y + 0.25, 0.6, iconOf(c, head, body));
      T(slide, runs(head, { bold: true }), { x: x + 0.25, y: y + 1.0, w: cw - 0.5, h: 0.72, fontSize: 16, color: C.petrol, valign: "top" });
      T(slide, runs(body), { x: x + 0.25, y: y + 1.8, w: cw - 0.5, h: ch - 1.8 - footH - 0.05, fontSize: foot ? 15 : 14, color: C.ink });
    } else {
      await badge(slide, x + 0.22, y + 0.25, 0.56, iconOf(c, head, body));
      T(slide, runs(head, { bold: true }), { x: x + 0.92, y: y + 0.2, w: cw - 1.12, h: 0.66, fontSize: 16, color: C.petrol, valign: "middle" });
      T(slide, runs(body), { x: x + 0.22, y: y + 1.0, w: cw - 0.44, h: ch - 1.1 - footH, fontSize: 13.5, color: C.ink });
    }
  }
};
L.stages = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const stages = arr(pick(s.fields, "stages"));
  const take = pick(s.fields, "takeaway");
  const colW = (W - 2 * MX - 0.4) / 2, top = 1.85, hh = take ? 4.1 : 4.8;
  for (let i = 0; i < Math.min(2, stages.length); i++) {
    const st = stages[i], x = MX + i * (colW + 0.4), cur = i === 0;
    slide.addShape("roundRect", { x, y: top, w: colW, h: hh, fill: { color: cur ? C.card : C.goldTint }, line: { color: cur ? C.card : C.goldTint }, rectRadius: 0.1 });
    slide.addShape("roundRect", { x: x + 0.3, y: top + 0.3, w: colW - 0.6, h: 0.55, fill: { color: cur ? C.teal : C.gold }, line: { color: cur ? C.teal : C.gold }, rectRadius: 0.08 });
    T(slide, runs(pick(st, "label", "head") || ""), { x: x + 0.3, y: top + 0.3, w: colW - 0.6, h: 0.55, fontSize: 17, bold: true, color: cur ? C.white : C.ink, align: "center", valign: "middle" });
    const items = arr(st.items), hasDesc = items.some(it => it.desc);
    const rowH = hasDesc ? (hh - 1.25) / Math.max(1, items.length) : Math.min(0.72, (hh - 1.25) / Math.max(1, items.length));
    items.forEach((it, j) => {
      const y = top + 1.1 + j * rowH;
      numBadge(slide, x + 0.35, y + (hasDesc ? 0.05 : 0), 0.52, pick(it, "ro") || "", cur ? C.petrol : C.goldDark, C.white, 12);
      T(slide, runs(pick(it, "name", "head") || ""), { x: x + 1.05, y: y, w: colW - 1.3, h: hasDesc ? 0.62 : 0.52, fontSize: 16, color: C.ink, valign: "middle", bold: hasDesc });
      if (it.desc) T(slide, runs(it.desc), { x: x + 1.05, y: y + 0.66, w: colW - 1.3, h: rowH - 0.72, fontSize: 13.5, color: C.muted });
    });
  }
  if (take) T(slide, runs(take), { x: MX, y: 6.15, w: W - 2 * MX, h: 0.6, fontSize: 15, italic: true, color: C.tealDark, valign: "middle" });
};
L.process_fig = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const p = plan.find(x => x.id === id);
  const steps = arr(pick(s.fields, "steps"));
  const x0 = MX, w0 = 4.3, top = 1.85, h0 = 4.9, rowH = h0 / Math.max(1, steps.length);
  slide.addShape("line", { x: x0 + 0.27, y: top + 0.3, w: 0, h: rowH * (steps.length - 1), line: { color: C.line, width: 2 } });
  steps.forEach((st, i) => {
    const y = top + i * rowH;
    numBadge(slide, x0, y, 0.55, i + 1, C.gold, C.ink, 16);
    T(slide, runs(pick(st, "head") || "", { bold: true }), { x: x0 + 0.8, y: y - 0.02, w: w0 - 0.8, h: 0.38, fontSize: 16, color: C.petrol });
    T(slide, runs(pick(st, "body") || ""), { x: x0 + 0.8, y: y + 0.36, w: w0 - 0.8, h: rowH - 0.45, fontSize: 13, color: C.ink });
  });
  diagramPanel(slide, p, 5.2, 1.68, W - MX - 5.2, 5.24);
};
function diagramPanel(slide, p, px, py, pw, ph) {
  slide.addShape("roundRect", { x: px, y: py, w: pw, h: ph, fill: { color: C.panel }, line: { color: C.line, width: 0.75 }, rectRadius: 0.08 });
  const dw = p.dw || 7.2, dh = p.dh || 4.7;
  const capH = p.caption ? 0.36 : 0;
  DG[p.diagram](slide, px + (pw - dw) / 2, py + 0.1 + Math.max(0, (ph - 0.2 - capH - dh) / 2));
  if (p.caption) T(slide, runs(p.caption), { x: px + 0.15, y: py + ph - 0.38, w: pw - 0.3, h: 0.32, fontSize: 10.5, italic: true, color: C.muted, align: "center", valign: "middle" });
}
L.diagram = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const p = plan.find(x => x.id === id);
  const px = 5.2;
  diagramPanel(slide, p, px, 1.68, W - MX - px, 5.24);
  await pointList(slide, pick(s.fields, "points"), MX, 1.82, px - MX - 0.3, 4.95, { headSize: 15, bodySize: 12.5, badge: 0.42, gap: 0.2 });
};
L.diagram_wide = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const p = plan.find(x => x.id === id);
  const py = 1.62, ph = p.dh + 0.1 + 0.38;
  diagramPanel(slide, p, MX, py, W - 2 * MX, ph);
  const pts = arr(pick(s.fields, "points"));
  const y = py + ph + 0.14, hh = 6.95 - y;
  const cw = (W - 2 * MX - 0.3 * (pts.length - 1)) / Math.max(1, pts.length);
  const bd = p.compact ? 0 : 0.4, tx = p.compact ? 0 : 0.52;
  for (let i = 0; i < pts.length; i++) {
    const x = MX + i * (cw + 0.3), head = pick(pts[i], "head") || "", body = pick(pts[i], "body") || "";
    if (bd) await badge(slide, x, y + 0.02, bd, iconOf(pts[i], head, body));
    T(slide, runs(head, { bold: true }), { x: x + tx, y, w: cw - tx, h: 0.32, fontSize: 14, color: C.petrol, valign: "middle" });
    T(slide, runs(body), { x: x + tx, y: y + 0.34, w: cw - tx, h: hh - 0.34, fontSize: 12.5, color: C.ink });
  }
};
L.funnel = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const vals = [125, 83, 43, 40, 33];
  const labels = arr(pick(s.fields, "labels"));
  const fills = [C.petrol, C.tealDark, C.teal, "3E8E97", C.gold];
  const top = 1.9, bh = 0.78, gap = 0.2, maxW = 4.63, lx = MX + maxW + 0.22;
  vals.forEach((v, i) => {
    const w = maxW * (v / 125), y = top + i * (bh + gap);
    slide.addShape("roundRect", { x: MX, y, w, h: bh, fill: { color: fills[i] }, line: { color: fills[i] }, rectRadius: 0.06 });
    T(slide, String(v), { x: MX + 0.15, y, w: 1.0, h: bh, fontSize: 30, bold: true, fontFace: HF, color: i === 4 ? C.ink : C.white, valign: "middle" });
    const lab = labels[i] ? (typeof labels[i] === "string" ? labels[i] : pick(labels[i], "label", "head", "text")) : "";
    T(slide, runs(lab || ""), { x: lx, y, w: 8.1 - lx, h: bh, fontSize: 15, bold: true, color: C.petrol, valign: "middle" });
  });
  // one callout per removal step, level with the bar it removes records from
  const notes = arr(pick(s.fields, "notes", "points"));
  for (let i = 0; i < notes.length; i++) {
    const n = notes[i], y = top + i * (bh + gap), head = pick(n, "head") || "", body = pick(n, "body") || "";
    await badge(slide, 8.35, y, 0.42, iconOf(n, head, body));
    T(slide, runs(head, { bold: true }), { x: 8.97, y: y - 0.02, w: W - MX - 8.97, h: 0.34, fontSize: 15, color: C.petrol });
    T(slide, runs(body), { x: 8.97, y: y + 0.34, w: W - MX - 8.97, h: 0.55, fontSize: 12.5, color: C.ink });
  }
};
L.chart = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const labels = ["Healthcare consent and privacy governance", "Blockchain-based healthcare data governance", "Decentralised identity and verifiable credentials", "Multi-party and decentralised governance", "Policy-based and healthcare access control", "Trusted Computing and secure execution"];
  const values = [9, 5, 7, 4, 7, 1];
  slide.addShape("roundRect", { x: MX, y: 1.8, w: 7.5, h: 4.95, fill: { color: C.panel }, line: { color: C.line, width: 0.75 }, rectRadius: 0.08 });
  slide.addChart(pres.charts.BAR, [{ name: "Studies", labels: labels.slice().reverse(), values: values.slice().reverse() }], {
    x: MX + 0.15, y: 1.9, w: 7.2, h: 4.75, barDir: "bar", chartColors: [C.teal], showValue: true, dataLabelPosition: "outEnd", dataLabelFontSize: 13, dataLabelColor: C.ink, dataLabelFontBold: true, dataLabelFontFace: BF, catAxisMajorTickMark: "none", catAxisLineShow: false,
    catAxisLabelColor: C.ink, catAxisLabelFontSize: 12, catAxisLabelFontFace: BF, valAxisHidden: true, valGridLine: { style: "none" }, catGridLine: { style: "none" }, showLegend: false,
    showTitle: true, title: "Shortlisted studies per category (n = 33)", titleFontSize: 14, titleColor: C.petrol, titleFontFace: BF, barGapWidthPct: 45, valAxisMaxVal: 10,
  });
  await pointList(slide, pick(s.fields, "points"), 8.5, 1.9, W - MX - 8.5, 4.8, { headSize: 15, bodySize: 13, badge: 0.42 });
};
L.matrix = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const rows = [["Healthcare consent and privacy governance", 9, [7, 1, 0, 1, 5]], ["Blockchain-based healthcare data governance", 5, [1, 0, 0, 4, 5]], ["Decentralised identity and verifiable credentials", 7, [0, 7, 1, 2, 1]], ["Multi-party and decentralised governance", 4, [1, 2, 2, 3, 2]], ["Policy-based and healthcare access control", 7, [0, 1, 0, 7, 5]], ["Trusted Computing and secure execution", 1, [0, 0, 0, 0, 0]]];
  const hdr = ["Category", "Studies", "Req 1", "Req 2", "Req 3", "Req 4", "Req 5"].map(h => ({ text: h, options: { fill: { color: C.petrol }, color: C.white, bold: true, align: h === "Category" ? "left" : "center", valign: "middle" } }));
  const body = rows.map(([name, n, v]) => [
    { text: name, options: { fill: { color: C.white }, valign: "middle" } },
    { text: String(n), options: { fill: { color: C.white }, align: "center", valign: "middle", bold: true } },
    ...v.map(x => ({ text: String(x), options: { fill: { color: x === 0 ? "F3F5F6" : x === n ? blend(C.teal, 0.9) : blend(C.teal, 0.15 + 0.5 * (x / n)) }, color: x === n ? C.white : (x === 0 ? C.muted : C.ink), align: "center", valign: "middle", bold: x > 0 } })),
  ]);
  const tot = [9, 11, 3, 17, 18];
  body.push([{ text: "All studies", options: { bold: true, fill: { color: C.goldTint }, valign: "middle" } }, { text: "33", options: { bold: true, align: "center", fill: { color: C.goldTint }, valign: "middle" } },
    ...tot.map(x => ({ text: String(x), options: { bold: true, align: "center", fill: { color: C.goldTint }, valign: "middle" } }))]);
  slide.addTable([hdr, ...body], { x: MX, y: 1.85, w: 8.1, colW: [3.35, 0.95, 0.76, 0.76, 0.76, 0.76, 0.76], fontFace: BF, fontSize: 12.5, color: C.ink, border: { type: "solid", pt: 0.5, color: C.line }, rowH: 0.52, margin: [0.04, 0.08, 0.04, 0.08] });
  T(slide, "Number = studies addressing the requirement (√ in Tables 2.4–2.9); shade = share of the category's studies.", { x: MX, y: 6.1, w: 8.1, h: 0.45, fontSize: 11.5, italic: true, color: C.muted });
  const take = pick(s.fields, "takeaway");
  slide.addShape("roundRect", { x: 9.0, y: 1.85, w: W - MX - 9.0, h: 1.75, fill: { color: C.petrol }, line: { color: C.petrol }, rectRadius: 0.1 });
  T(slide, runs(take || "", { bold: true }), { x: 9.25, y: 1.98, w: W - MX - 9.5, h: 1.5, fontSize: 14.5, color: C.white, valign: "middle" });
  await pointList(slide, pick(s.fields, "points"), 9.0, 3.9, W - MX - 9.0, 2.8, { headSize: 15, bodySize: 12.5, badge: 0.42 });
};
L.gaps = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const rows = arr(pick(s.fields, "rows"));
  const closing = pick(s.fields, "closing");
  const top = 1.8, avail = closing ? 4.3 : 4.95, gap = 0.12, rh = (avail - gap * (rows.length - 1)) / Math.max(1, rows.length);
  rows.forEach((r, i) => {
    const y = top + i * (rh + gap);
    slide.addShape("roundRect", { x: MX, y, w: W - 2 * MX, h: rh, fill: { color: i % 2 ? C.white : C.card }, line: { color: C.card }, rectRadius: 0.06 });
    slide.addShape("roundRect", { x: MX + 0.2, y: y + (rh - 0.46) / 2, w: 1.05, h: 0.46, fill: { color: C.teal }, line: { color: C.teal }, rectRadius: 0.08 });
    T(slide, pick(r, "req") || `Req ${i + 1}`, { x: MX + 0.2, y: y + (rh - 0.46) / 2, w: 1.05, h: 0.46, fontSize: 14, bold: true, color: C.white, align: "center", valign: "middle" });
    T(slide, runs(pick(r, "head") || "", { bold: true }), { x: MX + 1.5, y, w: 3.4, h: rh, fontSize: 15, color: C.petrol, valign: "middle" });
    T(slide, runs(pick(r, "gap", "body") || ""), { x: MX + 5.05, y, w: W - 2 * MX - 5.25, h: rh, fontSize: 13, color: C.ink, valign: "middle" });
  });
  if (closing) T(slide, runs(closing), { x: MX, y: 6.25, w: W - 2 * MX, h: 0.55, fontSize: 15, italic: true, color: C.tealDark, valign: "middle" });
};
L.table = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const header = arr(pick(s.fields, "header")); const rows = arr(pick(s.fields, "rows")).map(r => Array.isArray(r) ? r : Object.values(r));
  const n = header.length || (rows[0] || []).length;
  const tw = W - 2 * MX;
  const widths = {
    13: [2.9, 4.4, 4.83], 16: [0.9, 4.7, 4.8, 1.73], 28: [2.15, 2.45, 2.6, 2.75, 2.18], 34: [1.65, 4.6, 5.88], 40: [4.2, 3.4, 4.53],
  }[id] || Array(n).fill(tw / n);
  const fs = { 13: 13.5, 16: 13.5, 28: 13, 34: 13, 40: 15.5 }[id] || (rows.length > 7 ? 12 : 13.5);
  const rowH = { 13: 0.56, 16: 0.62, 28: 0.7, 34: 0.46, 40: [0.6, 1.15, 1.15, 1.15] }[id];
  const margin = id === 40 ? [0.08, 0.1, 0.08, 0.1] : undefined;
  styledTable(slide, header, rows, MX, 1.85, tw, widths, { fontSize: fs, rowH, margin, boldFirst: true, highlight: (r) => /proposed framework/i.test(r[0] || ""), tint: (r) => /Next \(CA3\)/.test(r[r.length - 1] || "") });
};
L.equation = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const eqs = [
    ["Consent object (Eq. 7)", "C = (I, A, P, E)", C.card, C.petrol],
    ["Current-stage decision (Eq. 6)", "Decision(C, R) = ALLOW  ⇔  V_I(u) ∧ V_A(C) ∧ V_P(C, R)", C.card, C.petrol],
    ["Next-stage decision (Eq. 24)", "Decision(C, R, t) = ALLOW  ⇔  V_I(u) ∧ V_A(C) ∧ V_P(C, R) ∧ V_T(C, t) ∧ V_L(C)", C.goldTint, C.ink],
  ];
  eqs.forEach(([lab, eq, fill, col], i) => {
    const y = 1.8 + i * 0.95;
    slide.addShape("roundRect", { x: MX, y, w: W - 2 * MX, h: 0.8, fill: { color: fill }, line: { color: fill }, rectRadius: 0.08 });
    T(slide, lab, { x: MX + 0.25, y, w: 2.6, h: 0.8, fontSize: 14, bold: true, color: C.muted, valign: "middle" });
    T(slide, runs(eq), { x: MX + 2.9, y, w: W - 2 * MX - 3.1, h: 0.8, fontFace: HF, fontSize: 20, color: col, valign: "middle" });
    if (i === 0) T(slide, "I identity  ·  A authority and authorisation requirements  ·  P policy and data scope  ·  E evidence", { x: 5.3, y, w: W - MX - 5.45, h: 0.8, fontSize: 12.5, color: C.muted, valign: "middle" });
  });
  const preds = arr(pick(s.fields, "predicates"));
  const pw = (W - 2 * MX - 0.2 * 4) / 5;
  preds.slice(0, 5).forEach((p, i) => {
    const x = MX + i * (pw + 0.2), y = 4.75, cur = i < 3;
    slide.addShape("ellipse", { x: x + 0.05, y, w: 0.75, h: 0.75, fill: { color: cur ? C.teal : C.white }, line: { color: cur ? C.teal : C.gold, width: 2 } });
    T(slide, runs(pick(p, "sym") || "", { bold: true }), { x: x + 0.05, y, w: 0.75, h: 0.75, fontFace: HF, fontSize: 17, color: cur ? C.white : C.goldDark, align: "center", valign: "middle" });
    T(slide, runs(pick(p, "name") || "", { bold: true }), { x: x + 0.9, y: y + 0.02, w: pw - 0.9, h: 0.72, fontSize: 13.5, color: C.petrol, valign: "middle" });
    T(slide, runs(pick(p, "meaning") || ""), { x, y: y + 0.85, w: pw, h: 0.85, fontSize: 13, color: C.ink, lineSpacing: 16 });
  });
  const take = pick(s.fields, "takeaway");
  if (take) T(slide, runs(take), { x: MX, y: 6.5, w: W - 2 * MX, h: 0.4, fontSize: 14, italic: true, color: C.tealDark, valign: "middle" });
};
L.figure = async (pres, id, s) => {
  const p = plan.find(x => x.id === id);
  const file = path.join(D, "fig", p.figure);
  const { w, h } = imgSize(file); const wide = w / h >= 1.1;
  const slide = frame(pres, id, s, { bare: !wide });
  const top = 1.8, bh = 4.95;
  if (wide) {
    figPanel(slide, file, MX, top, 7.75, bh, p.caption);
    await pointList(slide, pick(s.fields, "points"), 8.65, top + 0.05, W - MX - 8.65, bh - 0.05, { headSize: 15, bodySize: 12.5, badge: 0.42 });
  } else {
    // tall figure: full-height panel on the right, title confined to the text column
    const ph = 6.55, fw = Math.min(6.3, Math.max(3.4, (ph - 0.64) * (w / h) + 0.3));
    const tw = W - 2 * MX - fw - 0.4;
    const title = s.title || "";
    T(slide, runs(title), { x: MX, y: 0.4, w: tw, h: 1.05, fontFace: HF, fontSize: title.length > 44 ? 22 : 24, bold: true, color: C.petrol, valign: "middle" });
    if (s.subtitle) T(slide, runs(s.subtitle), { x: MX, y: 1.5, w: tw, h: 0.7, fontSize: 14, color: C.muted, valign: "top" });
    footer(slide, id);
    figPanel(slide, file, W - MX - fw, 0.35, fw, ph, p.caption);
    await pointList(slide, pick(s.fields, "points"), MX, 2.4, tw, 4.45, { headSize: 16, bodySize: 13.5, badge: 0.48 });
  }
};
L.two_figs = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const p = plan.find(x => x.id === id);
  const items = arr(pick(s.fields, "items", "figs", "panels", "points"));
  const gap = 0.4, cw = (W - 2 * MX - gap) / 2;
  for (let i = 0; i < 2; i++) {
    const x = MX + i * (cw + gap);
    const f = figPanel(slide, path.join(D, "fig", p.figures[i]), x, 1.7, cw, 4.32, p.captions[i]);
    if (p.hl) highlights(slide, f, p.hl[i]);
    const it = items[i] || {};
    T(slide, runs(pick(it, "label", "head") || "", { bold: true }), { x, y: 6.1, w: cw, h: 0.32, fontSize: 15, color: C.petrol });
    T(slide, runs(pick(it, "body", "text") || ""), { x, y: 6.42, w: cw, h: 0.52, fontSize: 12.5, color: C.ink });
  }
};
L.figure_wide = async (pres, id, s) => {
  // evidence grid on the left, points stacked on the right, takeaway along the bottom
  const slide = frame(pres, id, s);
  const p = plan.find(x => x.id === id);
  const pw = 9.05;
  const f = figPanel(slide, path.join(D, "fig", p.figure), MX, 1.66, pw, 4.62, p.caption);
  if (p.chips) {
    const g = JSON.parse(fs.readFileSync(path.join(D, "fig", p.chips), "utf8"));
    const k = f.w / g.size[0];
    g.pos.forEach(([x, y], i) => numBadge(slide, f.x + x * k, f.y + (y - g.top * 0.88) * k, 0.3, i + 1, C.gold, C.petrol, 12));
  }
  await pointList(slide, pick(s.fields, "points"), MX + pw + 0.35, 1.72, W - MX - (MX + pw + 0.35), 4.5, { headSize: 14.5, bodySize: 12.5, badge: 0.4, gap: 0.22 });
  const take = pick(s.fields, "takeaway");
  if (take) T(slide, runs(take), { x: MX, y: 6.4, w: W - 2 * MX, h: 0.5, fontSize: 14, italic: true, color: C.tealDark, valign: "middle" });
};
L.stats_table = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const stats = [["16", "tests passed", C.teal, C.white], ["2", [{ text: "skipped", options: { bold: true, fontSize: 14, breakLine: true } }, { text: "ZK circuit not built", options: { bold: false, fontSize: 12 } }], C.gold, C.ink], ["0", "failed", C.petrol, C.white]];
  stats.forEach(([v, l, f, col], i) => {
    const y = 1.85 + i * 1.5;
    slide.addShape("roundRect", { x: MX, y, w: 3.1, h: 1.3, fill: { color: f }, line: { color: f }, rectRadius: 0.1 });
    T(slide, v, { x: MX + 0.2, y, w: 1.2, h: 1.3, fontFace: HF, fontSize: 48, bold: true, color: col, valign: "middle" });
    T(slide, l, { x: MX + 1.35, y, w: 1.65, h: 1.3, fontSize: 14, bold: typeof l === "string", color: col, valign: "middle" });
  });
  const rows = arr(pick(s.fields, "rows")).map(r => Array.isArray(r) ? r : [pick(r, "id"), pick(r, "scenario"), pick(r, "predicate"), pick(r, "result")]);
  styledTable(slide, ["ID", "Scenario", "Predicate", "Result"], rows, 4.1, 1.85, W - MX - 4.1, [0.7, 4.4, 1.35, 2.18], { fontSize: 12, rowH: 0.43, boldFirst: true });
  const note = pick(s.fields, "note");
  if (note) T(slide, runs(note), { x: MX, y: 6.4, w: W - 2 * MX, h: 0.48, fontSize: 13, italic: true, color: C.tealDark, valign: "middle" });
};
L.onchain = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  slide.addShape("roundRect", { x: MX, y: 1.8, w: 5.3, h: 2.35, fill: { color: C.petrol }, line: { color: C.petrol }, rectRadius: 0.1 });
  await badge(slide, MX + 0.3, 2.05, 0.62, "FaLink", C.gold, C.petrol);
  T(slide, [
    { text: "Ethereum Sepolia testnet", options: { bold: true, fontSize: 18, color: C.white, breakLine: true } },
    { text: "Chain ID 11155111", options: { fontSize: 14, color: C.mist, breakLine: true } },
    { text: "ConsentSBTv2 contract", options: { fontSize: 14, color: C.mist } },
  ], { x: MX + 1.15, y: 2.02, w: 3.95, h: 1.2 });
  T(slide, "0xb0dA0440Abd6bd74bE0aebE226D593492124A6e7", { x: MX + 0.3, y: 3.4, w: 4.8, h: 0.4, fontFace: "Courier New", fontSize: 11.5, color: C.gold, valign: "middle" });
  const toks = [["#1", "11750525", "0x5bfb45ee…c0de105367"], ["#2", "11750632", "0x1b964596…e56fc522907"], ["#3", "11750702", "0x6812ab16…aabef251121"], ["#4", "11750722", "0xa4c4156b…eff497e014a"]];
  styledTable(slide, ["Token", "Block", "Transaction hash (shortened)"], toks, 6.3, 1.8, W - MX - 6.3, [1.0, 1.6, 3.83], { fontSize: 12.5, rowH: 0.47, boldFirst: true });
  T(slide, "Full hashes: Table 7.4 in the report.", { x: 6.3, y: 4.2, w: 6.4, h: 0.3, fontSize: 10.5, italic: true, color: C.muted });
  const pts = arr(pick(s.fields, "points"));
  const cw = (W - 2 * MX - 0.3 * (pts.length - 1)) / Math.max(1, pts.length);
  for (let i = 0; i < pts.length; i++) {
    const x = MX + i * (cw + 0.3), y = 4.65;
    slide.addShape("roundRect", { x, y, w: cw, h: 1.55, fill: { color: C.card }, line: { color: C.card }, rectRadius: 0.08 });
    T(slide, runs(pick(pts[i], "head") || "", { bold: true }), { x: x + 0.2, y: y + 0.12, w: cw - 0.4, h: 0.36, fontSize: 14.5, color: C.petrol });
    T(slide, runs(pick(pts[i], "body") || ""), { x: x + 0.2, y: y + 0.5, w: cw - 0.4, h: 1.0, fontSize: 12.5, color: C.ink });
  }
  const note = pick(s.fields, "note");
  if (note) T(slide, runs(note), { x: MX, y: 6.35, w: W - 2 * MX, h: 0.5, fontSize: 13, italic: true, color: C.tealDark, valign: "middle" });
};
L.status = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const rows = arr(pick(s.fields, "rows"));
  const top = 1.8, gap = 0.12, rh = (4.95 - gap * (rows.length - 1)) / Math.max(1, rows.length);
  rows.forEach((r, i) => {
    const y = top + i * (rh + gap);
    const st = pick(r, "status") || "";
    const done = /^completed/i.test(st), part = /partial/i.test(st);
    slide.addShape("roundRect", { x: MX, y, w: W - 2 * MX, h: rh, fill: { color: i % 2 ? C.white : C.card }, line: { color: C.card }, rectRadius: 0.06 });
    numBadge(slide, MX + 0.18, y + (rh - 0.56) / 2, 0.56, pick(r, "ro") || "", i < 4 ? C.petrol : C.goldDark, C.white, 12);
    T(slide, runs(pick(r, "name") || "", { bold: true }), { x: MX + 0.95, y, w: 3.35, h: rh, fontSize: 14.5, color: C.petrol, valign: "middle" });
    const fill = done ? C.teal : part ? C.gold : C.grey;
    slide.addShape("roundRect", { x: MX + 4.4, y: y + (rh - 0.5) / 2, w: 3.0, h: 0.5, fill: { color: fill }, line: { color: fill }, rectRadius: 0.1 });
    T(slide, runs(st), { x: MX + 4.45, y: y + (rh - 0.5) / 2, w: 2.9, h: 0.5, fontSize: 11.5, bold: true, color: part ? C.ink : C.white, align: "center", valign: "middle" });
    T(slide, runs(pick(r, "evidence") || ""), { x: MX + 7.6, y, w: W - 2 * MX - 7.75, h: rh, fontSize: 12.5, color: C.ink, valign: "middle" });
  });
};
L.timeline = async (pres, id, s) => {
  const slide = frame(pres, id, s);
  const steps = arr(pick(s.fields, "steps"));
  const n = steps.length, cw = (W - 2 * MX) / Math.max(1, n), cy = 2.45;
  slide.addShape("line", { x: MX + cw / 2, y: cy + 0.4, w: cw * (n - 1), h: 0, line: { color: C.gold, width: 2.5 } });
  for (let i = 0; i < n; i++) {
    const x = MX + i * cw, st = steps[i];
    numBadge(slide, x + cw / 2 - 0.4, cy, 0.8, i + 1, C.goldDark, C.white, 20);
    if (st.tag) T(slide, st.tag, { x: x + cw / 2 + 0.5, y: cy - 0.04, w: cw / 2 - 0.55, h: 0.36, fontSize: 13, bold: true, color: C.goldDark, valign: "middle" });
    slide.addShape("roundRect", { x: x + 0.12, y: cy + 1.1, w: cw - 0.24, h: 3.25, fill: { color: C.goldTint }, line: { color: C.goldTint }, rectRadius: 0.08 });
    T(slide, runs(pick(st, "head") || "", { bold: true }), { x: x + 0.3, y: cy + 1.25, w: cw - 0.6, h: 0.7, fontSize: 16, color: C.petrol });
    T(slide, runs(pick(st, "body") || ""), { x: x + 0.3, y: cy + 1.95, w: cw - 0.6, h: 1.35, fontSize: 14, color: C.ink });
    if (st.outcome) T(slide, [{ text: "Outcome: ", options: { bold: true } }, ...runs(st.outcome)], { x: x + 0.3, y: cy + 3.35, w: cw - 0.6, h: 0.9, fontSize: 13, color: C.tealDark });
  }
  T(slide, "Next stage (CA3): RO5 and RO6", { x: MX, y: 1.75, w: 6, h: 0.4, fontSize: 14, bold: true, color: C.goldDark });
};
L.closing = async (pres, id, s) => {
  const slide = dark(pres, s);
  T(slide, "Thank you", { x: MX, y: 2.0, w: 8, h: 1.2, fontFace: HF, fontSize: 60, bold: true, color: C.white });
  T(slide, "Questions and feedback", { x: MX, y: 3.25, w: 8, h: 0.6, fontSize: 24, color: C.gold });
  T(slide, [
    { text: "Yasir Dhaifallah O Alyoubi", options: { bold: true, color: C.white, fontSize: 16, breakLine: true } },
    { text: "YasirDhaifallahO.Alyoubi@student.uts.edu.au", options: { color: C.mist, fontSize: 14, breakLine: true } },
    { text: "Principal Supervisor: Professor Farookh Hussain  ·  Co-Supervisor: Dr Firas Al-Doghman", options: { color: C.mist, fontSize: 13 } },
  ], { x: MX, y: 4.55, w: 9, h: 1.3 });
  slide.addShape("ellipse", { x: 9.9, y: 1.7, w: 2.7, h: 2.7, fill: { color: C.petrol }, line: { color: C.gold, width: 3 } });
  const ic = await iconPng("FaShieldHalved", C.gold);
  slide.addImage({ data: ic, x: 10.55, y: 2.35, w: 1.4, h: 1.4 });
};

// ---------------------------------------------------------------- build
(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";
  pres.author = "Yasir Dhaifallah O Alyoubi";
  pres.title = "A Trusted Authorisation Framework for Multi-Party Patient Consent in Healthcare Data Sharing";
  pres.company = "University of Technology Sydney";
  const only = process.env.ONLY ? process.env.ONLY.split(",").map(Number) : null;
  for (const p of plan) {
    if (only && !only.includes(NUM[p.id])) continue;
    CUR = NUM[p.id];
    const s = content[p.id] || { title: "", subtitle: "", fields: {}, notes: "" };
    s.fields = s.fields || {};
    const fn = L[p.layout];
    if (!fn) throw new Error("no layout " + p.layout);
    await fn(pres, p.id, s);
  }
  await pres.writeFile({ fileName: OUT });
  const JSZip = require("jszip");
  const zip = await JSZip.loadAsync(fs.readFileSync(OUT));
  let nLang = 0;
  for (const name of Object.keys(zip.files)) {
    if (!/^ppt\/(slides|notesSlides|slideMasters|slideLayouts|notesMasters)\/[^/]+\.xml$/.test(name) && name !== "ppt/presentation.xml") continue;
    const xml = await zip.file(name).async("string");
    let out = xml.replace(/lang="en-US"/g, () => { nLang++; return 'lang="en-AU"'; });
    // pptxgenjs writes an <a:pPr> before every run of a paragraph; the schema allows one, so keep the first
    out = out.replace(/<a:p>([\s\S]*?)<\/a:p>/g, (m, inner) => {
      let first = true;
      return "<a:p>" + inner.replace(/<a:pPr\b[^>]*?(?:\/>|>[\s\S]*?<\/a:pPr>)/g, t => (first ? ((first = false), t) : "")) + "</a:p>";
    });
    if (out !== xml) zip.file(name, out);
  }
  fs.writeFileSync(OUT, await zip.generateAsync({ type: "nodebuffer", compression: "DEFLATE" }));
  console.log("wrote", OUT, "en-AU runs:", nLang);
  if (WARN.length) { console.log("fit warnings:"); WARN.forEach(w => console.log("  " + w)); }
})().catch(e => { console.error(e); process.exit(1); });
