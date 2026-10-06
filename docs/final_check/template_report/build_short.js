// Builder for the 13-section CA2 report (template structure). usage: node build_short.js [toc.json]
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, BorderStyle,
  AlignmentType, HeadingLevel, ShadingType, Footer, PageNumber, PageBreak, TabStopType, LeaderType,
} = require("/tmp/claude-0/full/node_modules/docx");

const D = "/tmp/claude-0/short/";
const FONT = "Times New Roman", BODY = 22, TEXTW = 9128; // A4 with 2.45 cm margins
const FIGS = JSON.parse(fs.readFileSync(D + "figs.json", "utf8"));
const TABS = JSON.parse(fs.readFileSync(D + "tables.json", "utf8"));
const EQS = JSON.parse(fs.readFileSync(D + "eqs.json", "utf8"));
const ALGS = JSON.parse(fs.readFileSync(D + "algos.json", "utf8"));
const REFS = JSON.parse(fs.readFileSync(D + "refs.json", "utf8"));
const BLOCKS = JSON.parse(fs.readFileSync(D + "blocks.json", "utf8"));
const TOC = fs.existsSync(process.argv[2] || "") ? JSON.parse(fs.readFileSync(process.argv[2], "utf8")) : {};

// ---------- numbering pass ----------
const num = { F: {}, T: {}, E: {}, A: {} }, cnt = { F: 0, T: 0, E: 0, A: 0 };
const kindOf = { fig: "F", table: "T", eq: "E", algo: "A" };
for (const b of BLOCKS) {
  const k = kindOf[b.t]; if (!k) continue;
  const key = b.ref || b.key; if (!key) throw new Error("block without ref " + JSON.stringify(b).slice(0, 80));
  if (num[k][key]) throw new Error("duplicate placement " + key);
  num[k][key] = ++cnt[k];
}
const problems = [];
const citeMap = {}; let citeN = 0;
function fixText(s) {
  s = String(s);
  s = s.replace(/\{([FTEA])(\d+[a-z]?|[A-Za-z_]+)\}/g, (m, k, id) => {
    const key = k + id, n = num[k][key];
    if (!n) { problems.push("unplaced token " + m); return m; }
    return k === "F" ? `Figure ${n}` : k === "T" ? `Table ${n}` : k === "E" ? `Equation (${n})` : `Algorithm ${n}`;
  });
  s = s.replace(/\[(\d+(?:\s*[,–-]\s*\d+)*)\]/g, (m, g) => {
    const parts = [];
    for (const piece of g.split(/\s*,\s*/)) {
      const r = piece.split(/\s*[–-]\s*/).map(Number);
      const list = r.length === 2 ? Array.from({ length: r[1] - r[0] + 1 }, (_, i) => r[0] + i) : [r[0]];
      for (const o of list) { if (!REFS[o]) problems.push("unknown ref " + o); if (!citeMap[o]) citeMap[o] = ++citeN; parts.push(citeMap[o]); }
    }
    const u = [...new Set(parts)].sort((a, b) => a - b);
    // compress consecutive runs
    const out = []; for (let i = 0; i < u.length; i++) { let j = i; while (j + 1 < u.length && u[j + 1] === u[j] + 1) j++; out.push(j - i >= 2 ? `${u[i]}–${u[j]}` : (j > i ? `${u[i]}, ${u[j]}` : `${u[i]}`)); i = j; }
    return "[" + out.join(", ") + "]";
  });
  return s;
}
function runs(text, base = {}) {
  const out = []; const re = /(⟦r⟧[\s\S]*?⟦\/r⟧|⟦b⟧[\s\S]*?⟦\/b⟧|⟦d⟧[\s\S]*?⟦\/d⟧|⟦n⟧[\s\S]*?⟦\/n⟧|\*\*[^*]+\*\*|~[^~]+~|\^[^^]+\^|;)/g; let last = 0, m;
  text = String(text);
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(...plain(text.slice(last, m.index), base));
    const t = m[0];
    if (t.startsWith("⟦r⟧")) out.push(...runs(t.slice(3, -4), process.env.RED === "1" ? { ...base, color: "FF0000" } : base));
    else if (t.startsWith("⟦b⟧")) out.push(...runs(t.slice(3, -4), process.env.RED === "1" ? { ...base, color: "00B0F0" } : base));
    else if (t.startsWith("⟦d⟧")) { if (process.env.DIFF === "1") out.push(...runs(t.slice(3, -4), { ...base, color: "FF0000", strike: true })); }
    else if (t.startsWith("⟦n⟧")) out.push(...runs(t.slice(3, -4), process.env.DIFF === "1" ? { ...base, color: "FF0000" } : base));
    else if (t === ";") out.push(new TextRun({ font: FONT, size: BODY, ...base, text: ";", highlight: process.env.GREEN === "1" ? "yellow" : undefined }));
    else if (t.startsWith("**")) out.push(...runs(t.slice(2, -2), { ...base, bold: true }));
    else if (t.startsWith("~")) out.push(new TextRun({ font: FONT, size: BODY, ...base, text: t.slice(1, -1), subScript: true }));
    else out.push(new TextRun({ font: FONT, size: BODY, ...base, text: t.slice(1, -1), superScript: true }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(...plain(text.slice(last), base));
  return out;
}
// YELLOW copy: every printed citation [n, n–n] gets a yellow highlight, text unchanged
function plain(t, base) {
  if (process.env.YELLOW !== "1") return [new TextRun({ font: FONT, size: BODY, ...base, text: t })];
  const out = []; const re = /\[(\d+(?:\s*[,–]\s*\d+)*)\]/g; let last = 0, m;
  while ((m = re.exec(t))) {
    if (m.index > last) out.push(new TextRun({ font: FONT, size: BODY, ...base, text: t.slice(last, m.index) }));
    out.push(new TextRun({ font: FONT, size: BODY, ...base, text: m[0], highlight: "yellow" }));
    last = m.index + m[0].length;
  }
  if (last < t.length) out.push(new TextRun({ font: FONT, size: BODY, ...base, text: t.slice(last) }));
  return out;
}
const GREEN = process.env.GREEN === "1" ? { color: "00A000" } : {};
const P = (text, opts = {}, base = {}) => new Paragraph({ children: runs(fixText(text), { ...GREEN, ...base }), alignment: AlignmentType.JUSTIFIED, spacing: { after: 110, line: 264 }, ...opts });
// GREEN copy: sentences taken from the original report stay black, the rest are green
const SEGR = segs => segs.flatMap(([t, o], i) => runs(fixText((i ? " " : "") + t.replace(/⟦d⟧[\s\S]*?⟦\/d⟧/g, "").replace(/⟦\/?[rbn]⟧/g, "")), o ? {} : GREEN));
const SEGP = segs => new Paragraph({ children: SEGR(segs), alignment: AlignmentType.JUSTIFIED, spacing: { after: 110, line: 264 } });
const cb = { style: BorderStyle.SINGLE, size: 4, color: "666666" };
const bAll = { top: cb, left: cb, bottom: cb, right: cb };

// ---------- renderers ----------
let h1n = 0, h2n = 0; const headsForToc = [];
function h1(title) {
  h1n++; h2n = 0; headsForToc.push(`${h1n}. ${title}`);
  return new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: h1n > 1 || true, spacing: { before: 120, after: 200 },
    children: [new TextRun({ text: `${h1n}.  ${title}`, font: FONT, size: 32, bold: true })] });
}
function h2(title) {
  h2n++;
  return new Paragraph({ heading: HeadingLevel.HEADING_2, keepNext: true, spacing: { before: 240, after: 120 },
    children: [new TextRun({ text: `${h1n}.${h2n}  `, font: FONT, size: 26, bold: true }), ...runs(title, { size: 26, bold: true })] });
}
function statusLine(text) {
  const m = /^\s*Status:\s*(.*)$/i.exec(text); const v = m ? m[1] : text;
  return new Paragraph({ spacing: { before: 60, after: 200 }, border: { left: { style: BorderStyle.SINGLE, size: 18, color: "000000", space: 8 } },
    indent: { left: 160 }, children: [new TextRun({ text: "Status: ", bold: true, font: FONT, size: BODY + 2 }), new TextRun({ text: v, bold: true, font: FONT, size: BODY + 2 })] });
}
function figure(b) {
  const f = FIGS[String(b.ref).slice(1)]; if (!f) { problems.push("missing figure " + b.ref); return []; }
  const buf = fs.readFileSync(D + f.file);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const n = +String(b.ref).slice(1);
  const shot = n >= 17 && n <= 40;                       // interface and Etherscan screenshots
  let width = Math.min(b.w || (shot ? 470 : 600), 600), height = Math.round(h * width / w);
  const maxH = b.maxH || (shot ? 400 : 450);
  if (height > maxH) { height = maxH; width = Math.round(w * height / h); }
  const cap = (b.caption || f.caption).replace(/\s*\.$/, "");
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 160, after: 60 },
      children: [new ImageRun({ type: "png", data: buf, transformation: { width, height }, altText: { title: fixText(cap).replace(/⟦\/?[rb]⟧|\*\*|[~^]/g, ""), description: fixText(cap).replace(/⟦\/?[rb]⟧|\*\*|[~^]/g, ""), name: path.basename(f.file) } })] }),
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 220 },
      children: [new TextRun({ text: `Figure ${num.F[b.ref]}: `, bold: true, font: FONT, size: BODY - 4 }), ...runs(fixText(cap) + ".", { size: BODY - 4 })] }),
  ];
}
function table(b) {
  let t;
  if (b.custom) t = b.custom; else {
    const src = TABS[String(b.ref).slice(1)]; if (!src) { problems.push("missing table " + b.ref); return []; }
    const rows = src.rows.map(r => r.slice());
    const body = b.keep_rows && b.keep_rows.length ? b.keep_rows.map(i => rows[i]).filter(Boolean) : rows.slice(1);
    t = { caption: b.caption || src.caption, header: rows[0], rows: body, widths: src.widths };
  }
  const ncol = t.header.length;
  let widths = t.widths && t.widths.length === ncol ? t.widths : Array(ncol).fill(1);
  const tot = widths.reduce((a, c) => a + c, 0); widths = widths.map(x => Math.floor(x * TEXTW / tot));
  widths[ncol - 1] += TEXTW - widths.reduce((a, c) => a + c, 0);
  const fs_ = t.small ? BODY - 7 : BODY - 5;
  const cell = (txt, i, head, keep) => new TableCell({ borders: bAll, width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { fill: "E7E6E6", type: ShadingType.CLEAR, color: "auto" } : undefined, margins: { top: 40, bottom: 40, left: 80, right: 80 },
    children: String(txt).split("\n").map(line => new Paragraph({ keepNext: head ? !!b.keep : !!keep, alignment: t.center && i > 0 ? AlignmentType.CENTER : AlignmentType.LEFT, children: runs(fixText(line).replace(/_(?=[A-Za-z0-9])/g, "_\u200b"), { size: fs_, bold: head }) })) });
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, keepNext: true, spacing: { before: 200, after: 80 },
      children: [new TextRun({ text: `Table ${num.T[b.ref || b.key]}: `, bold: true, font: FONT, size: BODY - 4 }), ...runs(fixText(String(t.caption).replace(/\s*\.$/, "")), { size: BODY - 4 })] }),
    new Table({ width: { size: TEXTW, type: WidthType.DXA }, columnWidths: widths,
      rows: [new TableRow({ tableHeader: true, cantSplit: true, children: t.header.map((h, i) => cell(h, i, true)) }),
        ...t.rows.map((r, ri) => new TableRow({ cantSplit: true, children: Array.from({ length: ncol }, (_, i) => cell(r[i] ?? "", i, false, b.keep && ri < t.rows.length - 1)) }))] }),
    new Paragraph({ spacing: { after: 160 }, children: [] }),
  ];
}
function equation(b) {
  const e = EQS[String(b.ref).slice(1)]; if (!e) { problems.push("missing equation " + b.ref); return []; }
  return [new Paragraph({ spacing: { before: 80, after: 160 }, keepLines: true,
    tabStops: [{ type: TabStopType.CENTER, position: Math.round(TEXTW / 2) }, { type: TabStopType.RIGHT, position: TEXTW }],
    children: [new TextRun({ text: "\t", font: FONT }), ...runs(fixText(e), { font: "Cambria Math", size: e.replace(/~|⟦\/?[rb]⟧/g, "").length > 78 ? BODY - 6 : e.replace(/~|⟦\/?[rb]⟧/g, "").length > 62 ? BODY - 4 : BODY - 1, italics: false }), new TextRun({ text: `\t(${num.E[b.ref]})`, font: FONT, size: BODY })] })];
}
function algorithm(b) {
  const a = ALGS[String(b.ref).slice(1)]; if (!a) { problems.push("missing algorithm " + b.ref); return []; }
  const AF = { size: BODY - 3 };
  const out = [new Paragraph({ keepNext: true, spacing: { before: 220, after: 40 },
    border: { top: { style: BorderStyle.SINGLE, size: 12, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 6, color: "000000" } },
    children: [new TextRun({ text: `Algorithm ${num.A[b.ref]} `, bold: true, font: FONT, ...AF }), ...runs(a.title, AF)] }),
    new Paragraph({ keepNext: true, spacing: { after: 20 }, children: [new TextRun({ text: "Require: ", bold: true, font: FONT, ...AF }), ...runs(a.require, AF)] }),
    new Paragraph({ keepNext: true, spacing: { after: 40 }, children: [new TextRun({ text: "Ensure: ", bold: true, font: FONT, ...AF }), ...runs(a.ensure, AF)] })];
  a.lines.forEach(([ind, txt], i) => out.push(new Paragraph({ keepNext: i < a.lines.length - 1, spacing: { after: 10 }, indent: { left: 240 + ind * 360 },
    children: [new TextRun({ text: `${i + 1}:  `, font: FONT, size: BODY - 6, color: "555555" }), ...runs(txt, AF)] })));
  out.push(new Paragraph({ spacing: { after: 200 }, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: "000000" } }, children: [] }));
  return out;
}

// ---------- document ----------
const C = [];
// title page (template)
const TP = (t, o = {}) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: o.after ?? 120, before: o.before ?? 0 }, children: [new TextRun({ text: t, font: FONT, size: o.size || 28, bold: !!o.bold })] });
C.push(TP("Suggested Title:", { size: 28, before: 1800, after: 200 }));
C.push(TP("A Trusted Authorization Framework for Multi-Party Patient Consent in Healthcare Data Sharing", { size: 40, bold: true, after: 1400 }));
C.push(TP("Principal Supervisor: Professor Farookh Hussain", { size: 26 }));
C.push(TP("Co-Supervisor: Dr. Firas Al-Doghman", { size: 26, after: 600 }));
C.push(TP("Presenter: Yasir Dhaifallah O Alyoubi", { size: 26 }));
C.push(TP("STUDENT ID #: 24724078", { size: 26 }));
C.push(new Paragraph({ children: [new PageBreak()] }));
// contents
C.push(new Paragraph({ spacing: { after: 240 }, children: [new TextRun({ text: "Contents", font: FONT, size: 32, bold: true })] }));
const tocTitles = BLOCKS.filter(b => b.t === "h1").map((b, i) => `${i + 1}. ${b.text}`).concat(["References"]);
for (const t of tocTitles) C.push(new Paragraph({ spacing: { after: 100 }, tabStops: [{ type: TabStopType.RIGHT, position: TEXTW, leader: LeaderType.DOT }],
  children: [new TextRun({ text: t + "\t" + (TOC[t] || ""), font: FONT, size: BODY })] }));
// body
for (const b of BLOCKS) {
  if (b.t === "h1") C.push(h1(b.text));
  else if (b.t === "h2") C.push(h2(b.text));
  else if (b.t === "status") C.push(statusLine(b.text));
  else if (b.t === "sub") C.push(new Paragraph({ spacing: { before: 0, after: 140 }, children: [new TextRun({ text: b.text, bold: true, italics: true, font: FONT, size: BODY + 4 })] }));
  else if (b.t === "p") C.push(GREEN.color && b.segs ? SEGP(b.segs) : P(b.text));
  else if (b.t === "bullets") for (const it of b.items || []) C.push(new Paragraph({ bullet: { level: 0 }, alignment: AlignmentType.JUSTIFIED, spacing: { after: 80, line: 288 }, children: GREEN.color && b.isegs ? SEGR(b.isegs[b.items.indexOf(it)]) : runs(fixText(it), GREEN) }));
  else if (b.t === "fig") C.push(...figure(b));
  else if (b.t === "table") C.push(...table(b));
  else if (b.t === "eq") C.push(...equation(b));
  else if (b.t === "algo") C.push(...algorithm(b));
  else problems.push("unknown block " + b.t);
}
// references
C.push(new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, spacing: { after: 200 }, children: [new TextRun({ text: "References", font: FONT, size: 32, bold: true })] }));
const order = Object.entries(citeMap).sort((a, b) => a[1] - b[1]);
fs.writeFileSync(D + "citeorder.json", JSON.stringify(order));
const HL = new Set(["8", "10", "18", "29", "82"]);
const BLUE = new Set(fs.existsSync(D + "refs_changed.json") ? JSON.parse(fs.readFileSync(D + "refs_changed.json", "utf8")).map(String) : []);
for (const [orig, n] of order) C.push(new Paragraph({ spacing: { after: 50, line: 240 }, indent: { left: 560, hanging: 560 }, alignment: AlignmentType.LEFT,
  children: [new TextRun({ text: `[${n}]\t`, font: FONT, size: BODY - 4, highlight: process.env.GREEN === "1" && HL.has(String(orig)) ? "yellow" : undefined }), ...runs(REFS[orig], { size: BODY - 4, color: process.env.RED === "1" && BLUE.has(String(orig)) ? "00B0F0" : undefined, highlight: process.env.GREEN === "1" && HL.has(String(orig)) ? "yellow" : undefined })], tabStops: [{ type: TabStopType.LEFT, position: 560 }] }));

const doc = new Document({
  creator: "Yasir Dhaifallah O Alyoubi", title: "CA2 Report: A Trusted Authorization Framework for Multi-Party Patient Consent in Healthcare Data Sharing",
  styles: { default: { document: { run: { font: FONT, size: BODY } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 32, bold: true, color: "000000" }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { font: FONT, size: 26, bold: true, color: "000000" }, paragraph: { outlineLevel: 1 } },
    ] },
  numbering: { config: [] },
  sections: [{ properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1389, bottom: 1389, left: 1389, right: 1389 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 20 })] })] }) },
    children: C }],
});
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync(D + (process.env.YELLOW === "1" ? "CA2_short_yellow.docx" : process.env.DIFF === "1" ? "CA2_short_diff.docx" : process.env.GREEN === "1" ? "CA2_short_green.docx" : process.env.RED === "1" ? "CA2_short_red.docx" : "CA2_short.docx"), buf);
  fs.writeFileSync(D + "build_report.json", JSON.stringify({ problems, figures: cnt.F, tables: cnt.T, equations: cnt.E, algorithms: cnt.A, references: citeN, toc: tocTitles }, null, 1));
  console.log("figures", cnt.F, "tables", cnt.T, "equations", cnt.E, "algorithms", cnt.A, "refs", citeN, "problems", problems.length);
  problems.slice(0, 30).forEach(p => console.log("  ", p));
});
