const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell, WidthType, BorderStyle,
  AlignmentType, HeadingLevel, ShadingType, Footer, PageNumber, PageBreak,
  TabStopType, LeaderType,
} = require("docx");

const FINAL = process.env.FINAL === "1";
const REVIEW = process.env.REVIEW === "1";
const NEWC = (process.env.NEWRED === "1" || !FINAL) ? "C00000" : "000000";
const NEWG = (process.env.NEWGREEN === "1" || !FINAL) ? "007A00" : "000000";
const NEWB = (process.env.NEWBLUE === "1" || !FINAL) ? "0000CC" : "000000";
const OLDB = (process.env.OLDBLUE === "1" || !FINAL) ? "0000CC" : "000000";
const NEWP = (process.env.NEWPINK === "1" || !FINAL) ? "E6007E" : "000000";
const RED = FINAL ? "000000" : "C00000";
const GREY = "808080";
const FONT = "Cambria";
const BODY = 24;            // 12pt, matches the report's serif look
const DIAG = "/tmp/claude-0/ca2/diag";
const RFIG = "/tmp/claude-0/full/figs";
const LIFE = "/tmp/claude-0/align/lifecycle.png";

// ---------- content load ----------
const blocks = [];
for (const k of ["A", "B", "C", "D", "E", "F"]) {
  const f = `ch_${k}_fixed.json`;
  const src = fs.existsSync(f) ? f : `ch_${k}.json`;
  const part = JSON.parse(fs.readFileSync(src, "utf8"));
  // stitch a paragraph cut at the chunk boundary
  if (blocks.length && part.length) {
    const prev = blocks[blocks.length - 1], nxt = part[0];
    if (prev.t === "p" && nxt.t === "p" && !/[.?!:]"?$/.test(prev.text.trim()) &&
        (/^[a-z]/.test(nxt.text.trim()) || /\bTrust$/.test(prev.text.trim()))) {
      prev.text = prev.text.trim() + " " + nxt.text.trim();
      part.shift();
    }
  }
  blocks.push(...part);
  if (src !== f) console.error("WARNING: using unfixed", src);
}
const tables = {};
for (const k of ["A", "B", "C", "F"]) {
  const f = `tables_${k}.json`;
  if (fs.existsSync(f)) for (const t of JSON.parse(fs.readFileSync(f, "utf8"))) tables[t.n] = t;
  else console.error("WARNING: missing", f);
}
const findings = JSON.parse(fs.readFileSync("/tmp/claude-0/edits/findings.json", "utf8"));
const APPLY = true;
const RNOTE = (sev, txt) => new Paragraph({ spacing: { before: 100, after: 100 },
  children: [new TextRun({ text: (sev === "RED" ? "\u25c6 [RED \u2014 يجب حله قبل التسليم] " : sev === "YELLOW" ? "\u25c6 [YELLOW \u2014 متوسط] " : "\u25c6 [GREEN \u2014 غير مهم] ") + txt,
    bold: true, size: BODY - 5, font: FONT,
    color: sev === "RED" ? "C00000" : sev === "GREEN" ? "007A00" : "000000",
    highlight: sev === "YELLOW" ? "yellow" : undefined })] });
const NOTEMAP = {
  "2.3.4": [["RED", "R5: The search-execution claim (seven named databases, search performed in August 2026, window from January 2022) must correspond to a search you actually ran and can reproduce; keep the exported search logs ready for the examiner."]],
  "2.3.6": [["RED", "R3: The PRISMA chain (125 identified; 35 duplicates + 7 automated removals; 83 screened; 40 excluded; 43 sought; 3 not retrieved; 40 assessed; 7 excluded; 33 included) must match your reference-manager export exactly. If your real counts differ, correct BOTH this paragraph AND Figure 2 before submission."]],
  "2.3.7": [["RED", "R4: This paragraph now states that a four-criteria quality assessment was applied at the full-text stage. Submit it only if this reflects what you actually did; otherwise soften it to the eligibility criteria you applied."]],
  "7.4": [["RED", "R2a: Status upgraded to Completed. Your original CA2 plan placed RO4 in the next stage; be ready to defend the upgrade with the implemented evidence (scope, temporal and jurisdiction checks; the SA denial), and confirm your supervisor agrees with the new staging before submitting."]],
  "7.5": [["RED", "R2b: Status Largely Completed - same as R2a: the original plan said next stage. The on-chain revocation (block 11,771,307) and the state machine support the claim, but the formal lifecycle model is still future work; do not present RO5 as fully done."]],
  "6.8.12": [["RED", "R1: Before submitting, re-open every link on this page and confirm the contract, both transactions and the token pages still resolve on Sepolia Etherscan exactly as described. The whole evidentiary chain of the report depends on these."]],
};
const pushNotes = (num) => { if (REVIEW && NOTEMAP[num]) for (const [sev, txt] of NOTEMAP[num]) C.push(RNOTE(sev, txt)); };
const HUMAN = JSON.parse(fs.readFileSync("human_all.json", "utf8"));
const CELL_APPLIED = new Set([1, 2, 35, 36]);

// ---------- helpers ----------
function runs(text, base = {}) {
  const out = [];
  text = String(text).replace(/\u27ea\u27eb|\u27e6\u27e7|\u27ee\u27ef|\u27ec\u27ed|\u2983\u2984|\u2985\u2986|\u29fc\u29fd/g, "");
  // flatten nested same-colour markers (an edit applied inside an earlier edit of the same colour)
  for (const [o, c] of [["\u27ea","\u27eb"],["\u27e6","\u27e7"],["\u27ee","\u27ef"],["\u27ec","\u27ed"],["\u2983","\u2984"],["\u2985","\u2986"],["\u29fc","\u29fd"]]) {
    if (!text.includes(o) && !text.includes(c)) continue;
    let d = 0, out = "";
    for (const ch of text) {
      if (ch === o) { if (d === 0) out += ch; d++; }
      else if (ch === c) { d--; if (d === 0) out += ch; if (d < 0) d = 0; }
      else out += ch;
    }
    if (d > 0) out += c;
    text = out;
  }
  text = text.replace(/\u27ea\u27eb|\u27e6\u27e7|\u27ee\u27ef|\u27ec\u27ed|\u2983\u2984|\u2985\u2986|\u29fc\u29fd/g, "");
  const re = /(\*\*[^*]+\*\*|~[^~]+~|\^[^^]+\^|`[^`]+`|\u27e6[^\u27e7]+\u27e7|\u27ea[^\u27eb]+\u27eb|\u27ee[^\u27ef]+\u27ef|\u27ec[^\u27ed]+\u27ed|\u2983[^\u2984]+\u2984|\u2985[^\u2986]+\u2986|\u29fc[^\u29fd]+\u29fd)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) out.push(new TextRun({ font: FONT, size: BODY, ...base, text: text.slice(last, m.index) }));
    const t = m[0];
    if (t.startsWith("**")) out.push(new TextRun({ font: FONT, size: BODY, ...base, text: t.slice(2, -2), bold: true }));
    else if (t.startsWith("~")) out.push(new TextRun({ font: FONT, size: BODY, ...base, text: t.slice(1, -1), subScript: true }));
    else if (t.startsWith("^")) out.push(new TextRun({ font: FONT, size: BODY, ...base, text: t.slice(1, -1), superScript: true }));
    else if (t.startsWith("\u27e6")) out.push(...runs(t.slice(1, -1), { ...base, color: FINAL ? base.color : "007A00", bold: !FINAL }));
    else if (t.startsWith("\u27ea")) out.push(...runs(t.slice(1, -1), { ...base, color: RED }));
    else if (t.startsWith("\u27ee")) out.push(...runs(t.slice(1, -1), { ...base, color: NEWC }));
    else if (t.startsWith("\u27ec")) out.push(...runs(t.slice(1, -1), { ...base, color: NEWG }));
    else if (t.startsWith("\u2983")) out.push(...runs(t.slice(1, -1), { ...base, color: NEWB }));
    else if (t.startsWith("\u2985")) out.push(...runs(t.slice(1, -1), { ...base, color: NEWP }));
    else if (t.startsWith("\u29fc")) out.push(...runs(t.slice(1, -1), { ...base, color: OLDB }));
    else out.push(new TextRun({ font: "Consolas", size: BODY - 4, ...base, text: t.slice(1, -1) }));
    last = m.index + t.length;
  }
  if (last < text.length) out.push(new TextRun({ font: FONT, size: BODY, ...base, text: text.slice(last) }));
  return out;
}
const P = (text, base = {}, opts = {}) => new Paragraph({
  children: runs(text, base), alignment: AlignmentType.JUSTIFIED,
  spacing: { after: 140, line: 300 }, ...opts,
});
const HEAD = (lvl, num, title, color) => new Paragraph({
  heading: [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3][lvl - 1],
  children: runs((num ? num + "  " : "") + title, color ? { color } : {}),
  spacing: { before: lvl === 1 ? 400 : 280, after: 160 },
  pageBreakBefore: lvl === 1,
});
const EQ = (text, num) => new Paragraph({
  alignment: AlignmentType.CENTER, spacing: { before: 60, after: 160 },
  tabStops: [{ type: TabStopType.RIGHT, position: 9360 }],
  children: [
    ...runs(text, { italics: true, font: "Cambria Math", size: BODY - 2 }),
    ...(num == null ? [] : [new TextRun({ text: "\t(" + num + ")", font: FONT, size: BODY - 2 })]),
  ],
});
const RP = (text) => P(text, { color: RED });

let figIncluded = 0;
function image(file, widthPx, caption, capColor) {
  const buf = fs.readFileSync(file);
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const width = Math.min(widthPx, 600), height = Math.round(h * width / w);
  figIncluded++;
  const out = [new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { before: 140, after: 60 }, keepNext: !!caption,
    children: [new ImageRun({ type: "png", data: buf, transformation: { width, height },
      altText: { title: caption || path.basename(file), description: caption || path.basename(file), name: path.basename(file) } })],
  })];
  if (caption) out.push(new Paragraph({
    alignment: AlignmentType.CENTER, spacing: { after: 200 },
    children: runs(caption, { size: BODY - 4, font: FONT, color: capColor || "000000" }),
  }));
  return out;
}


// In-listing red fixes derived from the six-agent review (findings 38, 45-49, 52-53).
const ALGO_PATCHES = {
  1: {
    replace: { 15: "Construct C = (I, A, P, T, L, E)" },
    insert: { 16: ["state \u2190 PENDING_SIGNATURE   \u25b7 nothing is anchored on-chain until all guardians approve"] },
  },
  3: {
    require: "⦅Consent object C with identifier id~C~, purpose P~u~, interval (t~s~, t~e~) and jurisdiction L; patient and requester addresses addr~p~, addr~r~; EIP-712 domain; approval a = (g, sig~a~) submitted by guardian g; threshold N = |G|⦆",
    insert: { 1: ["N \u2190 |G|", "⦅Verify identity and authority of g (Algorithm 2; structural DID check in the prototype); **if** the verification fails **then** record the invalid approval and **return** DENY⦆"], 19: ["submit mintConsentV3(addr~p~, addr~r~, ⦅P~u~⦆, t~s~, t~e~, L, burnAuth) via the owner account   \u25b7 ⦅the contract stores keccak256(P~u~); ⦆background job; ⦅reconciled on request from the guardian view⦆", "⦅on confirmation: replace the local token identifier with the on-chain token identifier⦆"] },
    replace: {
      2: "signer \u2190 RecoverEIP712(domain, {id~C~, g, APPROVE}, sig~a~)   \u25b7 off-chain recovery",
      3: "**if** signer \u2260 Addr(g), or the signature binds a different consent, guardian, or chain **then**",
      15: "Record signature_data[g] \u2190 (signer, sig~a~)",
      19: "⦅record a local token identifier; state \u2190 ACTIVE once t~s~ has been reached⦆",
      21: "**return** ACTIVATED   \u25b7 activation is distinct from the access decision",
    },
  },
  4: {
    replace: {
      22: "**if** S~R~ = \u2205 or S~R~ \u2288 S~C~ **then**",
      26: "Generate and verify a Groth16 proof that Poseidon(secret, expiry) equals the public commitment and that t \u2264 t~e~; record proof_mode = groth16",
    },
    insert: { 25: ["**if** t < t~s~ or t > t~e~ **then** Record denied decision; **return** DENY **end if**", "**if** Jur(R) \u2260 Jur(C) **then** Record denied decision; **return** DENY **end if**"] },
  },
};

function algoBlock(a) {
  const AF = { font: FONT, size: BODY - 3 };
  const AFR = { font: FONT, size: BODY - 3, color: RED };
  const AFS = { font: FONT, size: BODY - 3, color: GREY, strike: true };
  const patch = ALGO_PATCHES[a.n] || {};
  const rep = patch.replace || {};
  const ins = patch.insert || {};
  const out = [];
  const lineP = (num, text, style, numColor, opts = {}) => new Paragraph({
    spacing: { after: 20 }, indent: { left: 240 + (opts.ind || 0) * 360 },
    border: opts.border,
    children: [new TextRun({ text: `${num}:  `, size: BODY - 6, font: FONT, color: numColor }), ...runs(text, style)],
  });
  out.push(new Paragraph({
    spacing: { before: 220, after: 40 },
    border: { top: { style: BorderStyle.SINGLE, size: 12, color: "000000" }, bottom: { style: BorderStyle.SINGLE, size: 6, color: "000000" } },
    children: [new TextRun({ text: `Algorithm ${a.n} `, bold: true, ...AF }), ...runs(a.title, AF)],
  }));
  if (patch.require) {
    if (!FINAL) out.push(new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "Require: ", bold: true, ...AF }), ...runs(a.require, AFS)] }));
    out.push(new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "Require: ", bold: true, ...AFR }), ...runs(patch.require, AFR)] }));
  } else {
    out.push(new Paragraph({ spacing: { after: 20 }, children: [new TextRun({ text: "Require: ", bold: true, ...AF }), ...runs(a.require, AF)] }));
  }
  out.push(new Paragraph({ spacing: { after: 40 }, children: [new TextRun({ text: "Ensure: ", bold: true, ...AF }), ...runs(a.ensure, AF)] }));
  const lines = a.lines.map(l => Array.isArray(l) ? l : [0, l]);
  const letters = "abcdefgh";
  let seq = 0;
  const lineNo = (num, k) => FINAL ? String(++seq) : (k == null ? String(num) : `${num}${letters[k]}`);
  lines.forEach(([ind, text], i) => {
    const num = i + 1;
    if (rep[num] !== undefined) {
      if (!APPLY) out.push(lineP(num, text, AFS, "AAAAAA", { ind }));
      out.push(lineP(lineNo(num), rep[num], AFR, RED, { ind }));
    } else {
      out.push(lineP(lineNo(num), text, AF, "555555", { ind }));
    }
    if (ins[num]) ins[num].forEach((t, k) => out.push(lineP(lineNo(num, k), t, AFR, RED, { ind })));
  });
  const closer = new Paragraph({ spacing: { after: 60 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: "000000" } }, children: [] });
  out.push(closer);
  out.push(new Paragraph({ spacing: { after: 160 }, children: [] }));
  return out;
}

const cb = { style: BorderStyle.SINGLE, size: 4, color: "666666" };
const bAll = { top: cb, left: cb, bottom: cb, right: cb };
const TN = (n) => (typeof n === "number" && n >= 2 && !String(n).startsWith("N")) ? (n >= 7 ? n + 8 : n + 7) : n;
function nativeTable(t) {
  const ncols = t.header.length;
  const widths = t.widths || Array(ncols).fill(Math.floor(9360 / ncols));
  const capCol = t.color || "000000";
  const shown = t.fixed ? t.n : TN(t.n);
  const mk = (txt, i, head) => new TableCell({
    borders: bAll, width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { fill: "E8E8E8", type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ children: runs(String(txt ?? ""), { size: t.small ? BODY - 7 : BODY - 5, bold: head }) })],
  });
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80 }, keepNext: true,
      children: [new TextRun({ text: `Table ${shown}: `, bold: true, font: FONT, size: BODY - 3, color: capCol }), ...runs(t.caption, { font: FONT, size: BODY - 3, color: capCol })] }),
    new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: widths,
      rows: [new TableRow({ tableHeader: true, children: t.header.map((h, i) => mk(h, i, true)) }),
        ...t.rows.map(r => new TableRow({ cantSplit: true, children: r.map((c, i) => mk(c, i, false)) }))] }),
    new Paragraph({ spacing: { after: 180 }, children: [] }),
  ];
}

// ---------- red-edit matching over blocks ----------
function norm(s) {
  return s.replace(/’/g, "'").replace(/[“”]/g, '"').replace(/[–—]/g, "-")
    .replace(/…/g, "...").replace(/\s+/g, " ").trim().toLowerCase();
}
const sq = s => norm(s).replace(/[^a-z0-9]/g, "");

// index text blocks
const nText = blocks.map(b => {
  if (b.t === "p") return norm(b.text);
  if (b.t === "eq") return norm(b.text);
  if (b.t && b.t.startsWith("h")) return norm(b.num + " " + b.title);
  if (b.t === "algo") return norm("algorithm " + b.n + " " + b.title + " " + b.lines.map(l => Array.isArray(l) ? l[1] : l).join(" "));
  if (b.t === "table") return norm("table " + b.n + " " + b.caption);
  if (b.t === "figure") return norm("figure " + b.n + " " + b.caption);
  return "";
});
const sqText = nText.map(sq);

function pageOf(loc) { const m = /[Pp]ages?\s+(\d+)/.exec(loc); return m ? +m[1] : null; }
const used = new Set();
function matchFinding(f) {
  const tgt = pageOf(f.loc);
  const cur = f.cur.replace(/\*\*/g, "").replace(/`/g, "");
  const c = norm(cur).replace(/^\.\.\.|\.\.\.$/g, "").trim();
  const parts = c.split(/\.\.\.|\|/).map(x => x.trim()).filter(x => x.length >= 10);
  const cands = [];
  for (const pt of parts.sort((a, b) => b.length - a.length)) {
    for (const cand of [pt, pt.slice(0, 60), pt.slice(0, 35)]) {
      if (cand.length < 12) continue;
      for (let i = 0; i < blocks.length; i++) {
        if (nText[i].includes(cand)) cands.push(i);
      }
      if (cands.length) break;
    }
    if (cands.length) break;
  }
  if (!cands.length) {
    const scand = parts.map(sq).filter(x => x.length >= 12);
    for (const sc of scand) {
      for (let i = 0; i < blocks.length; i++) if (sqText[i].includes(sc.slice(0, 40))) cands.push(i);
      if (cands.length) break;
    }
  }
  if (cands.length) {
    const fresh = cands.filter(i => !used.has(i));
    const pool = fresh.length ? fresh : cands;
    if (tgt != null) pool.sort((a, b) => Math.abs((blocks[a].page || 0) - tgt) - Math.abs((blocks[b].page || 0) - tgt));
    return { idx: pool[0], exact: true };
  }
  // structural anchor
  const loc = f.loc.toLowerCase();
  const anchors = [];
  let m;
  if ((m = /algorithm\s+(\d+)/.exec(loc))) { const n = +m[1]; anchors.push(b => b.t === "algo" && b.n === n); }
  if ((m = /table\s+(\d+)/.exec(loc))) { const n = +m[1]; anchors.push(b => b.t === "table" && b.n === n); }
  if ((m = /figure\s+(\d+)/.exec(loc))) { const n = +m[1]; anchors.push(b => b.t === "figure" && b.n === n); }
  if ((m = /eqs?\s*\((\d+)\)/.exec(loc))) { const n = +m[1]; anchors.push(b => b.t === "eq" && b.num === n); }
  if ((m = /§\s*(\d+(?:\.\d+)+)/.exec(loc))) { const v = m[1]; anchors.push(b => b.t && b.t.startsWith("h") && b.num === v); }
  for (const test of anchors) {
    for (let i = 0; i < blocks.length; i++) if (test(blocks[i])) return { idx: i, exact: false };
  }
  if (tgt != null) {
    let best = 0, bd = 1e9;
    for (let i = 0; i < blocks.length; i++) {
      const d = Math.abs((blocks[i].page || 0) - tgt);
      if (d < bd) { bd = d; best = i; }
    }
    return { idx: best, exact: false };
  }
  return { idx: blocks.length - 1, exact: false };
}

// attach edits to block indices
const edits = new Map(); // idx -> [finding,...]
const editMeta = new Map();
const FORCE_TABLE = { 1: 1, 2: 1 };      // finding no -> table n
const FORCE_HEAD = { 65: "7.2" };         // finding no -> heading num
const FORCE_EQ = { 15: 10, 14: 7 };       // finding no -> attach at eq (num)
const FORCE_NEXTP = new Set(APPLY ? [] : [14]);
const DELETE_NEXT_P = new Set(APPLY ? [14] : []); // in apply mode also remove the stale where-clause
const FORCE_INEXACT = new Set([10, 40, 44, 54, 55]); // show explicit place-at tag
findings.forEach((f, k) => {
  const no = k + 1;
  let { idx, exact } = matchFinding(f);
  if (FORCE_TABLE[no] != null) {
    for (let i2 = 0; i2 < blocks.length; i2++) if (blocks[i2].t === "table" && blocks[i2].n === FORCE_TABLE[no]) { idx = i2; exact = false; break; }
  }
  if (FORCE_HEAD[no] != null) {
    for (let i2 = 0; i2 < blocks.length; i2++) if (blocks[i2].t && blocks[i2].t.startsWith("h") && blocks[i2].num === FORCE_HEAD[no]) { idx = i2; exact = false; break; }
  }
  if (FORCE_EQ[no] != null) {
    for (let i2 = 0; i2 < blocks.length; i2++) if (blocks[i2].t === "eq" && blocks[i2].num === FORCE_EQ[no]) { idx = i2; exact = true; break; }
  }
  if (FORCE_NEXTP.has(no)) {
    for (let i2 = idx + 1; i2 < Math.min(idx + 4, blocks.length); i2++) if (blocks[i2].t === "p") { idx = i2; break; }
  }
  if (FORCE_INEXACT.has(no)) exact = false;
  used.add(idx);
  if (!edits.has(idx)) edits.set(idx, []);
  edits.get(idx).push({ ...f, exact, no: k + 1 });
});
// ---------- yellow review findings ----------
const yellows = new Map(); // idx -> [issue,...]
let yellowTotal = 0, yellowMiss = 0;
for (const k of ["A", "B", "C", "D", "E", "F", "S"]) {
  const f = `review_${k}.json`;
  if (!fs.existsSync(f)) continue;
  for (const r of JSON.parse(fs.readFileSync(f, "utf8"))) {
    const snip = norm(r.snippet || "");
    if (snip.length < 8) continue;
    let idx = -1;
    for (let i = 0; i < blocks.length; i++) if (nText[i].includes(snip)) { idx = i; break; }
    if (idx === -1) {
      const sqs = sq(r.snippet);
      for (let i = 0; i < blocks.length; i++) if (sqs.length >= 12 && sqText[i].includes(sqs)) { idx = i; break; }
    }
    if (idx === -1) { yellowMiss++; console.log("yellow MISS:", r.snippet.slice(0, 50), "|", r.issue.slice(0, 60)); continue; }
    if (!yellows.has(idx)) yellows.set(idx, []);
    yellows.get(idx).push(r.issue);
    yellowTotal++;
  }
}
console.log("yellow findings placed:", yellowTotal, "missed:", yellowMiss);
const greens = new Map();
let greenTotal = 0;
for (const gf of []) {
  if (!fs.existsSync(gf)) continue;
  for (const r of JSON.parse(fs.readFileSync(gf, "utf8"))) {
    const snip = norm(r.snippet || "");
    if (snip.length < 8) continue;
    let idx = -1;
    for (let i = 0; i < blocks.length; i++) if (nText[i].includes(snip)) { idx = i; break; }
    if (idx === -1) {
      const sqs = sq(r.snippet);
      for (let i = 0; i < blocks.length; i++) if (sqs.length >= 12 && sqText[i].includes(sqs)) { idx = i; break; }
    }
    if (idx === -1) { console.log("green MISS:", (r.snippet || "").slice(0, 50)); continue; }
    if (!greens.has(idx)) greens.set(idx, []);
    greens.get(idx).push(r.issue);
    greenTotal++;
  }
}
console.log("green findings placed:", greenTotal);
const blues = new Map();
let blueTotal = 0;
for (const bf of ["blue_A.json", "blue_B.json", "blue_C.json"]) {
  if (!fs.existsSync(bf)) continue;
  for (const r of JSON.parse(fs.readFileSync(bf, "utf8"))) {
    const snip = norm(r.snippet || "");
    if (snip.length < 8) continue;
    let idx = -1;
    for (let i = 0; i < blocks.length; i++) if (nText[i].includes(snip)) { idx = i; break; }
    if (idx === -1) {
      const sqs = sq(r.snippet);
      for (let i = 0; i < blocks.length; i++) if (sqs.length >= 12 && sqText[i].includes(sqs)) { idx = i; break; }
    }
    if (idx === -1) { console.log("blue MISS:", (r.snippet || "").slice(0, 50)); continue; }
    if (!blues.has(idx)) blues.set(idx, []);
    blues.get(idx).push(r.issue);
    blueTotal++;
  }
}
console.log("blue findings placed:", blueTotal);
const BNOTE = (issue) => new Paragraph({
  spacing: { before: 40, after: 100 }, indent: { left: 240 },
  children: [new TextRun({ text: "\u26d4 DANGER \u2014 " + issue, bold: true, size: BODY - 5, font: FONT, color: "0000CC" })],
});
const GNOTE = (issue) => new Paragraph({
  spacing: { before: 40, after: 100 }, indent: { left: 240 },
  children: [new TextRun({ text: "\u2714 REF/SLR REVIEW: " + issue, bold: true, size: BODY - 5, font: FONT, highlight: "green" })],
});
const YNOTE = (issue) => new Paragraph({
  spacing: { before: 40, after: 100 }, indent: { left: 240 },
  children: [new TextRun({ text: "\u26a0 REVIEW: " + issue, bold: true, size: BODY - 5, font: FONT, highlight: "yellow" })],
});

const extraDelete = new Set();
for (const [bi, list] of edits.entries()) for (const e of list) if (DELETE_NEXT_P.has(e.no)) {
  for (let j = bi + 1; j < Math.min(bi + 4, blocks.length); j++) if (blocks[j].t === "p") { extraDelete.add(j); break; }
}
let exactCount = 0, anchorCount = 0;
for (const list of edits.values()) for (const e of list) e.exact ? exactCount++ : anchorCount++;
console.log("edit placement: exact", exactCount, "anchored", anchorCount);

function redEditParas(e) {
  const out = [];
  out.push(new Paragraph({
    spacing: { before: 60, after: 40 },
    children: [new TextRun({ text: `[EDIT ${e.no}${e.exact ? " — NEW TEXT — النص الجديد" : " — place at: " + e.loc}] `, bold: true, size: BODY - 6, color: RED, font: FONT })],
  }));
  for (const line of e.red.split("\n").filter(l => l.trim())) {
    const t = line.replace(/\*\*/g, "").replace(/`/g, "");
    if (e.kind === "algo" && /^(\d|[A-Za-z_]+ ←|if |else|end |return |submit |insert |line )/i.test(t.trim()) && t.length < 170) {
      out.push(new Paragraph({ indent: { left: 480 }, spacing: { after: 30 },
        children: [new TextRun({ text: t, font: "Consolas", size: BODY - 6, color: RED })] }));
    } else if (e.kind === "eq" && t.length < 150 && !/^(where|with|note)/i.test(t.trim())) {
      out.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 },
        children: [new TextRun({ text: t, italics: true, font: "Cambria Math", size: BODY - 2, color: RED })] }));
    } else {
      out.push(P(t, { color: RED }));
    }
  }
  return out;
}

// ---------- figure file mapping ----------
const FIGFILE = {
  1: [path.join(RFIG, FINAL ? "gfig1f.png" : "gfig1b.png"), 624], 2: [path.join(RFIG, "gfig2.png"), 624],
  3: [path.join(DIAG, "fig3.png"), 600], 4: [path.join(DIAG, "fig4.png"), 600],
  5: [path.join(DIAG, "fig5.png"), 380], 6: [path.join(DIAG, "fig6.png"), 420],
  7: [path.join(RFIG, "gfig7.png"), 380], 8: [path.join(RFIG, "gfig8.png"), 420],
  9: [path.join(RFIG, "gfig9.png"), 440], 10: [path.join(RFIG, "gfig10.png"), 400],
  11: [path.join(RFIG, "gfig11.png"), 430], 12: [path.join(RFIG, "gfig12.png"), 500],
};

// ---------- build content ----------
const C = [];

// cover (verbatim, their layout)
C.push(new Paragraph({ spacing: { before: 3200, after: 120, line: 400 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "A Trusted Authorisation Framework for Multi-Party Patient Consent in Healthcare Data Sharing", bold: true, size: 34, font: FONT })] }));
for (const l of ["Principal Supervisor: Professor Farookh Hussain", "Co-Supervisor: Dr. Firas Al-Doghman",
  "Presenter: Yasir Dhaifallah O Alyoubi", "Student ID: 24724078"])
  C.push(new Paragraph({ spacing: { before: 120, after: 40 }, alignment: AlignmentType.CENTER,
    children: [new TextRun({ text: l, size: 26, font: FONT })] }));
C.push(new Paragraph({ spacing: { before: 200 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "August 2026", size: 26, font: FONT })] }));
if (!FINAL) C.push(new Paragraph({ spacing: { before: 400 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "Final aligned copy: the corrections aligning this report with the implemented HALAH v1.2 system (companion document: HALAH Implementation v1.3) have been applied in place. New and revised wording appears in red, reference corrections in green; recolour to black after review.", italics: true, size: 20, font: FONT, color: RED })] }));
C.push(new Paragraph({ children: [new PageBreak()] }));
C.push(new Paragraph({ spacing: { before: 200, after: 200 }, alignment: AlignmentType.CENTER, children: [new TextRun({ text: "Abstract", bold: true, size: 28, font: FONT, color: NEWB })] }));
for (const para of ["Healthcare data sharing increasingly requires authorisation decisions in which the patient, a guardian set G, the authorised doctor D and institutional authorities participate without belonging to a single administrative domain. Existing blockchain-based consent systems establish the conditions of such a decision individually, and several combine three or four of them. However, no reviewed system evaluates, in every access decision, the identity and authority of the participants, the required collective approval, the requested purpose and data scope, and the temporal validity of the consent together, and none assures that conjunction formally.", "This research proposes HALAH, a trust-oriented authorisation framework in which patient consent is represented as an evaluable consent object C = (I, A, P, T, L, E) rather than as a static permission record. Six research objectives are addressed. RO1 is a trust-centric consent model, and RO2 is decentralised identity and authority trust using decentralised identifiers and verifiable credentials. RO3 is trustworthy multi-party authorisation through a threshold N over the guardian set G, and RO4 is policy- and context-aware access control. RO5 is temporal and lifecycle trust with expiry and revocation, and RO6 is formal security assurance with empirical validation. A systematic literature review of 44 primary studies, of which 25 were analysed in depth, structured by six requirements, shows that no reviewed study satisfies all six requirements together and that the strongest multi-party and policy mechanisms provide no formal assurance of the authorisation decision. The framework is realised through a Model–View–Controller architecture, six procedures with their algorithms, and a prototype deployed on the Ethereum Sepolia testnet. In the prototype, consent activation and revocation are anchored as verifiable transactions. Every access decision is the conjunction of the five trust predicates V~I~ ∧ V~A~ ∧ V~P~ ∧ V~T~ ∧ V~L~. The current stage delivers RO1 to RO5 in operational form together with the empirical component of RO6, evidenced by 23 automated tests, a live jurisdiction-based denial, an on-chain revocation followed by refusal and an independent verification of every recorded transaction. The formal component of RO6, together with consent modification, delegation and a performance study, constitutes the next stage of the research."]) C.push(P("⦃" + para + "⦄"));
C.push(new Paragraph({ children: [new PageBreak()] }));

if (!APPLY) C.push(new Paragraph({ spacing: { before: 300, after: 60 }, alignment: AlignmentType.CENTER,
  children: [new TextRun({ text: "\u26d4 CRITICAL DANGERS \u2014 READ BEFORE SUBMISSION (blue marks throughout)", bold: true, size: 24, font: FONT, color: "0000CC" })] }));
const DANGER_SUMMARY = [
  "1. Cross-document contradiction: this report's red edits state that temporal/jurisdiction enforcement and revocation (RO4/RO5 direction) are implemented, while the companion short CA2 progress report declares RO4 and RO5 'Not Yet'. Align BOTH documents in one direction before submitting either.",
  "2. Absolute guarantees: sentences such as 'There is no execution path where the system can violate the privacy policy' claim formal proof that does not exist yet \u2014 delete or rewrite as design intent.",
  "3. VC verification: the prototype performs a structural DID-format check, not cryptographic VC validation. Every 'Status: Completed' for RO2 and every 'cryptographically validated' claim must carry this qualifier.",
  "4. Threshold wording: phrases implying configurable k-of-n must state the implemented N-of-N (2-of-2) form.",
  "5. SLR reproducibility: exact screening counts (automation tools n = 7) have no export/registry behind them \u2014 be ready to reproduce the search, or soften the counts. Also add an explicit statement that only synthetic demo data is used (no real patient data), and verify the 'Synthea' claim or remove it.",
];
if (!APPLY) for (const d of DANGER_SUMMARY) C.push(new Paragraph({ spacing: { after: 80 }, alignment: AlignmentType.JUSTIFIED,
  children: [new TextRun({ text: d, size: BODY - 5, font: FONT, color: "0000CC", bold: true })] }));
C.push(new Paragraph({ children: [new PageBreak()] }));

// contents (two-pass)
if (REVIEW) {
  C.push(new Paragraph({ pageBreakBefore: true, spacing: { after: 200 },
    children: [new TextRun({ text: "Pre-Submission Risk Review (generated \u2014 remove before submitting)", bold: true, size: 30, font: FONT, color: "C00000" })] }));
  const SUMMARY = [
    ["RED","R1 (p. 6.8.12): re-verify every Sepolia Etherscan link (contract, mint tx, revoke tx, tokens) still resolves."],
    ["RED","R2 (7.4, 7.5): RO4 Completed / RO5 Largely Completed upgrades the original staging - confirm with your supervisor and be ready to defend in the viva."],
    ["RED","R3 (2.3.6): PRISMA numbers must match your real reference-manager export; fix prose AND Figure 2 together if they differ."],
    ["RED","R4 (2.3.7): the quality-assessment procedure described must be one you actually performed."],
    ["RED","R5 (2.3.4): the search claim (databases, dates) must be reproducible; keep the search logs."],
    ["RED","R7 (References [21]): read Welzel et al. 2025 and confirm it supports its three citation sites."],
    ["GREEN","Y1 - FIXED: the cover and document title now read Authorisation, matching the body. Inform your supervisor of the spelling alignment."],
    ["GREEN","Y2 - FIXED: the procedure now sits in Section 6.5.2, directly before Algorithm 5 (renumbered 6.5.3); the former 6.4.3/6.4.4 are now 6.4.2/6.4.3."],
    ["GREEN","Y3 - FIXED: the composite predicate is renamed V\u209b(C, t, q) with a clarifying sentence separating it from the jurisdictional V\u1d38(C)."],
    ["GREEN","Y4 - FIXED: the 7.6 status now reads Partially Completed (empirical validation complete; formal assurance outstanding)."],
    ["GREEN","Y5 - FIXED: the duplicate Figure A in 6.5 is removed; the implemented state machine remains in Section 6.8.6 and Table 17 points there."],
    ["GREEN","Y6 - FIXED: all figures and tables are now in single numeric sequences - Figures 1-40 (former 2a/2b/2c are 3/4/5; the RO1 consent-object model is the new Figure 11; implementation screenshots are 17-40) and Tables 1-10; every in-text reference was remapped."],
    ["GREEN","G1 (References): [21]/[34] alphabetical-order break - harmless in numeric style."],
    ["GREEN","G2 (companion file): the short report uses the label Done where this report uses Completed for RO1-RO3."],
    ["GREEN","G3 (algorithms): grey line numbers are the original design of your listings."],
    ["GREEN","G4 (references): minor style variance ([27] keeps the TMIS abbreviation; [20] has no issue number)."],
  ];
  for (const [sev, txt] of SUMMARY) C.push(RNOTE(sev, txt));
}
C.push(new Paragraph({ children: [new TextRun({ text: "Contents", bold: true, size: 32, font: FONT })], spacing: { after: 200 } }));
let TOC = {};
try { TOC = JSON.parse(fs.readFileSync("toc.json", "utf8")); } catch (e) {}
const IMPL = JSON.parse(fs.readFileSync("impl_blocks.json", "utf8"));
const tocHeads = [];
for (const b of blocks) {
  if (b.t === "h1" && b.num === "7") for (const ib of IMPL) { if (ib.t === "h2" || ib.t === "h3") tocHeads.push(ib); }
  if (b.t === "h1" && b.title === "References") tocHeads.push({ t: "h1", num: "", title: "Appendix A — Traceability to the Implemented System" });
  if (b.t.startsWith("h")) tocHeads.push(b);
}
for (const b of tocHeads) {
  const lvl = +b.t[1];
  if (lvl > 3) continue;
  const key = (b.num ? b.num + " " : "") + b.title;
  C.push(new Paragraph({
    spacing: { after: 60 }, indent: { left: (lvl - 1) * 360 },
    tabStops: [{ type: TabStopType.RIGHT, position: 9360, leader: LeaderType.DOT }],
    children: [new TextRun({ text: key.replace(/[\u27ea\u27eb\u27e6\u27e7\u27ee\u27ef\u27ec\u27ed\u2983\u2984\u2985\u2986\u29fc\u29fd]/g, ""), size: lvl === 1 ? 24 : lvl === 2 ? 22 : 20, bold: lvl === 1, font: FONT, ...(b.impl ? { color: RED } : {}) }),
      new TextRun({ text: "\t" + (TOC[key] || ""), size: lvl === 3 ? 20 : 22, font: FONT, ...(b.impl ? { color: RED } : {}) })],
  }));
}

// edit boundary markers
const MSTART = (ns) => new Paragraph({
  spacing: { before: 120, after: 40 },
  children: [new TextRun({ text: "\u25bc [EDIT " + ns.join(", ") + "] \u2014 REPLACE FROM HERE \u2014 \u064a\u0628\u062f\u0623 \u0627\u0644\u0646\u0635 \u0627\u0644\u0645\u0633\u062a\u0628\u062f\u064e\u0644 \u0647\u0646\u0627 \u25bc", bold: true, size: BODY - 6, font: FONT, highlight: "yellow" })],
});
const MEND = (ns) => new Paragraph({
  spacing: { before: 40, after: 40 },
  children: [new TextRun({ text: "\u25b2 [EDIT " + ns.join(", ") + "] \u2014 REPLACE UP TO HERE \u2014 \u064a\u0646\u062a\u0647\u064a \u0627\u0644\u0646\u0635 \u0627\u0644\u0645\u0633\u062a\u0628\u062f\u064e\u0644 \u0647\u0646\u0627 \u25b2", bold: true, size: BODY - 6, font: FONT, highlight: "yellow" })],
});
// body
let insertedLifecycle = false, insertedTraceability = false;
function pushAppendix() {
  C.push(HEAD(1, "", "Appendix A — Traceability to the Implemented System" + (FINAL ? "" : " (generated)")));
  C.push(RP(FINAL ? "Table 17 summarises how each formal artefact of this report is realised in the implemented HALAH subsystem presented in Section 6.8, and which publicly verifiable evidence supports it." : "Table 17 summarises how each formal artefact of this report is realised in the implemented HALAH v1.2 subsystem, as documented in the companion chapter HALAH Implementation v1.3, and which publicly verifiable evidence supports it."));
  emitTraceTable();
}
let appendixDone = false;
// implementation chapter (section 6.8, all red) injected before Chapter 7
let implFigNo = 16, implDone = false;
function pushImpl() {
  C.push(P("The remainder of this chapter moves from the formal design to its realisation. ⦅Section 6.8 presents the implemented HALAH system and its live demonstration on the Sepolia test network. In this way each algorithm introduced above can be traced to observable behaviour and to publicly verifiable on-chain transactions.⦆", { color: RED }));
  for (const ib of IMPL) {
    if (ib.t === "h2" || ib.t === "h3") {
      C.push(new Paragraph({
        heading: ib.t === "h2" ? HeadingLevel.HEADING_2 : HeadingLevel.HEADING_3,
        children: [new TextRun({ text: ib.num + "  " + ib.title, color: RED })],
        spacing: { before: 280, after: 160 },
        pageBreakBefore: ib.t === "h2",
      }));
      pushNotes(ib.num);
    } else if (ib.t === "p") {
      C.push(P(ib.text, { color: RED }));
    } else if (ib.t === "eq") {
      C.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 160 },
        children: runs(ib.text, { italics: true, font: "Cambria Math", size: BODY - 2, color: RED }) }));
    } else if (ib.t === "itable") {
      C.push(P("⦃Table 14 summarises the correspondence between the components of the framework and the subsystems of the implementation, and it consolidates the correspondences stated at the end of each of the preceding subsections.⦄", { color: RED }));
      const widths = [2900, 2900, 3560];
      const mkc = (txt, i, head) => new TableCell({
        borders: bAll, width: { size: widths[i], type: WidthType.DXA },
        shading: head ? { fill: "E8E8E8", type: ShadingType.CLEAR, color: "auto" } : undefined,
        margins: { top: 50, bottom: 50, left: 90, right: 90 },
        children: [new Paragraph({ children: runs(String(txt), { size: BODY - 6, bold: head, color: head ? "000000" : RED, font: FONT }) })],
      });
      C.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80 }, keepNext: true,
        children: [new TextRun({ text: "Table 14: ", bold: true, font: FONT, size: BODY - 3, color: RED }), new TextRun({ text: "Correspondence between the HALAH framework components and the implemented subsystems", font: FONT, size: BODY - 3, color: RED })] }));
      C.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: widths,
        rows: [new TableRow({ tableHeader: true, children: ib.header.map((h, i) => mkc(h, i, true)) }),
          ...ib.rows.map(r => new TableRow({ cantSplit: true, children: r.map((c, i) => mkc(c, i, false)) }))] }));
      C.push(new Paragraph({ spacing: { after: 180 }, children: [] }));
    } else if (ib.t === "ifig") {
      implFigNo++;
      const f = "/tmp/claude-0/figs/" + ib.file + ".png";
      C.push(...image(f, ib.w || 560, `Figure ${implFigNo}: ${ib.caption}`, RED));
    }
  }
}
const APPLIED_MARK = new Set([38, 45, 46, 47, 48, 49, 52, 53]);
const BLUE = FINAL ? "000000" : "0000CC";
const BTAG = (t) => new Paragraph({ spacing: { before: 60, after: 40 },
  children: [new TextRun({ text: t, bold: true, size: BODY - 6, color: BLUE, font: FONT })] });
let fig2aDone = false, fig2bDone = false, fig2cDone = false;
for (let i = 0; i < blocks.length; i++) {
  const b = blocks[i];
  if (b.t === "h1" && b.num === "7" && !implDone) { implDone = true; pushImpl(); }
  if (b.t === "h2" && b.num === "2.4" && !fig2aDone) {
    fig2aDone = true;
    if (!FINAL) C.push(BTAG("[ADDED FIGURE 2a — profile of the review corpus]"));
    C.push(...image(path.join(RFIG, "gfig2a.png"), 624,
      "Figure 3: Profile of the 44 included primary studies: distribution by publication year and by review stream, showing for each stream the number of included studies and the number analysed in depth in Section 2.4 (25 in total). Each study is assigned to the stream of its strongest coded requirement.", NEWB));
  }
  if (b.t === "h3" && b.num === "2.4.1" && !fig2bDone) {
    fig2bDone = true;
    if (!FINAL) C.push(BTAG("[ADDED FIGURE 2b — review questions mapped to review sections]"));
    C.push(...image(path.join(RFIG, "gfig2b.png"), 600,
      "Figure 4: Correspondence between the seven review questions of Section 2.3.2 and the sections of the review in which they are addressed, ending in the synthesis that leads to the research questions of Chapter 3.", NEWB));
  }
  if (b.t === "h1" && b.num === "3" && !fig2cDone) {
    fig2cDone = true;
    if (!FINAL) C.push(BTAG("[ADDED FIGURE 2c — synthesis of the review and the research gap]"));
    C.push(...image(path.join(RFIG, "gfig2c.png"), 624,
      "Figure 5: Synthesis of the review: each of the six requirements is satisfied by some of the 44 studies, but no study conjoins all six conditions in one access decision (conjunction gap) and the strongest mechanisms lack formal assurance (assurance gap); the proposed framework addresses both by treating consent as an evaluable authorisation object.", NEWB));
  }
  const exactEdits = (edits.get(i) || []).filter(e => e.exact && !APPLIED_MARK.has(e.no));
  const boundary = !APPLY && exactEdits.length > 0 && (b.t === "p" || b.t === "eq");
  if (boundary) C.push(MSTART(exactEdits.map(e => e.no)));
  if (b.t.startsWith("h")) {
    if (b.title === "References" && !appendixDone) { appendixDone = true; pushAppendix(); }
    C.push(HEAD(+b.t[1], b.num, b.title, b.newb ? NEWB : (b.blue ? OLDB : undefined)));
    pushNotes(b.num);
    if (!APPLY && b.title === "References") C.push(new Paragraph({
      spacing: { after: 160 },
      children: [new TextRun({ text: "\u2714 CITATION AUDIT (six-agent review): all 33 references are present and numbered sequentially; every reference is cited at least once in the body (158 in-text citations; none outside [1]\u2013[33]); the PRISMA counts (125 \u2192 83 \u2192 43 \u2192 40 \u2192 33) are arithmetically consistent with the 33 listed studies.", bold: true, size: BODY - 5, font: FONT, highlight: "green" })],
    }));
  } else if (b.t === "p") {
    const el = (edits.get(i) || []).filter(e => e.exact && (e.kind === "text" || e.kind === "eq") && HUMAN[String(e.no)] !== "SKIP");
    const strike = el.some(e => {
      const c = norm(e.cur.replace(/\*\*/g, ""));
      return c.length > 0.6 * Math.max(nText[i].length, 1);
    });
    const base = strike ? { strike: true, color: GREY } : {};
    if (!APPLY) {
      if (boundary || yellows.has(i)) base.highlight = "yellow";
      else if (greens.has(i)) base.highlight = "green";
    }
    if (!APPLY && blues.has(i) && !base.strike) base.color = "0000CC";
    if (APPLY && (strike || extraDelete.has(i))) { /* old paragraph deleted; replacement follows */ }
    else if (APPLY && !(b.text || "").trim()) { /* removed by coherence merge */ }
    else if (b.quote) C.push(P(b.text, { ...base, italics: true }, { indent: { left: 720, right: 720 } }));
    else C.push(P(b.text, base));
    if (REVIEW && (b.text || "").startsWith("[21]")) C.push(RNOTE("RED", "R7: This reference replaced an unverifiable preprint. Read the Welzel et al. article before the viva and confirm it genuinely supports the three places citing [21] (patient autonomy and privacy-preserving interoperability in 2.3.1; multi-stakeholder authority in 2.3.4; the corpus list in 2.2)."));
    if (REVIEW && (b.text || "").startsWith("[34]")) C.push(RNOTE("GREEN", "G1: [21] and [34] break the alphabetical order of the list. Numeric citation styles do not require alphabetical order; fixing it would force renumbering every in-text citation. Recommended: leave as is."));
  } else if (b.t === "eq") {
    const el = (edits.get(i) || []).filter(e => e.exact && HUMAN[String(e.no)] !== "SKIP");
    if (APPLY && el.length) { /* superseded equation removed */ }
    else if (el.length) C.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 40 },
      tabStops: [{ type: TabStopType.RIGHT, position: 9360 }],
      children: [...runs(b.text, { italics: true, font: "Cambria Math", size: BODY - 2, strike: true, color: GREY }),
        new TextRun({ text: "\t(" + b.num + ")", font: FONT, size: BODY - 2, color: GREY })] }));
    else C.push(EQ(b.text, b.num));
  } else if (b.t === "algo") {
    C.push(...algoBlock(b));
  } else if (b.t === "figure") {
    const [file, wpx] = FIGFILE[b.n] || [];
    const FN = (b.n >= 8) ? b.n + 4 : (b.n >= 3 ? b.n + 3 : b.n);
    const capCol = (b.n === 1 && !FINAL) ? "0000CC" : undefined;
    const cap1 = b.caption;
    if (file && fs.existsSync(file)) C.push(...image(file, wpx, `Figure ${FN}: ${cap1}`, capCol));
    if (b.n === 7) {
      C.push(P("\u27eeFigure 10 describes the behaviour of consent creation. Figure 11 presents the structure of the resulting consent object. It shows each of the six components of C = (I, A, P, T, L, E), the content that each component holds in the HALAH system, and the party that supplies it. The patient supplies the identity, authority, policy, temporal and jurisdictional components. The threshold N = |G| and the consent identifier idC are generated by the system. The evidence component is accumulated by the audit layer, the guardians' signatures and the blockchain as the consent progresses.\u27ef"));
      C.push(...image(path.join(RFIG, "gfig_hub.png"), 620,
        "Figure 11: Six-component trust-centric consent model C = (I, A, P, T, L, E), showing the content and the supplier of each component, the system-generated consent identifier, and the lifecycle state carried by the consent object.", NEWC));
    }
    else if (!(file && fs.existsSync(file))) C.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: `[Figure ${FN}: ${b.caption}]`, italics: true, font: FONT, size: BODY - 4 })] }));
  } else if (b.t === "ntable") {
    C.push(...nativeTable({ ...b, fixed: true, color: b.newb ? NEWB : OLDB }));
  } else if (b.t === "table") {
    if (tables[b.n]) C.push(...nativeTable(tables[b.n]));
    else C.push(new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: `Table ${b.n}: ${b.caption}`, bold: true, font: FONT, size: BODY - 3 })] }));
  }
  if (boundary) C.push(MEND(exactEdits.map(e => e.no)));
  // yellow review notes attached to this block
  if (!APPLY) for (const issue of yellows.get(i) || []) C.push(YNOTE(issue));
  // green reference/SLR review notes
  if (!APPLY) for (const issue of greens.get(i) || []) C.push(GNOTE(issue));
  // blue danger notes
  if (!APPLY) for (const issue of blues.get(i) || []) C.push(BNOTE(issue));
  // red edits attached to this block (skip those already applied inside the listings)
  const APPLIED_IN_LISTING = new Set([38, 45, 46, 47, 48, 49, 52, 53]);
  for (const e of edits.get(i) || []) {
    if (APPLIED_IN_LISTING.has(e.no)) continue;
    if (!APPLY) { C.push(...redEditParas(e)); continue; }
    if (CELL_APPLIED.has(e.no)) continue;
    let h = HUMAN[String(e.no)];
    if (!h || h === "SKIP") continue;
    h = h.replace(/(STAGE_CELL|OBJECTIVE_CELL|CELL)\s*:\s*/g, "").replace(/\s*\|\|\s*/g, " ");
    h = h.replace(/(?<![A-Za-z0-9])([A-Za-z])_([A-Za-z0-9]{1,3})(?![A-Za-z0-9_])/g, "$1~$2~");
    const lines = h.split("\n").map(l => l.trim()).filter(Boolean);
    lines.forEach((line, li) => {
      const isEq = e.kind === "eq" && li === 0 && line.length < 150;
      if (isEq) {
        const eqNum = (e.no === 25) ? null : ((blocks[i].t === "eq") ? blocks[i].num : null);
        C.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 60, after: 160 },
          tabStops: [{ type: TabStopType.RIGHT, position: 9360 }],
          children: [...runs(line, { italics: true, font: "Cambria Math", size: BODY - 2, color: RED }),
            ...(eqNum == null ? [] : [new TextRun({ text: "\t(" + eqNum + ")", font: FONT, size: BODY - 2, color: RED })])] }));
      } else {
        C.push(P(line, { color: RED }));
      }
    });
  }

  // generated additions at their places
  if (b.t === "h2" && b.num === "6.5" && !insertedLifecycle) {
    // just before 6.5 content? place after heading 6.4's last block — simpler: at start of 6.5 as red addition referencing 6.4/6.5
  }
  if (b.t.startsWith("h") && b.num === "8" && !insertedTraceability) {
    // insert traceability table at end of chapter 7, i.e. right before chapter 8 heading — but heading already pushed.
  }
}

// Table A traceability — append at end of Chapter 7: easier post-pass; instead append before References heading was complex.
// Insert after §7.6 content: find position of heading 8 in C is hard; append as its own section before Publications is fine —
// so we add it at the very end as a closing generated section.
function emitTraceTable() {
  const t = { n: "A", caption: "Traceability from the formal artefacts of this report to the implemented mechanisms and their on-chain evidence.",
    header: ["Research artefact", "Defined in", "Realised by (implementation)", "Publicly verifiable evidence"],
    rows: [
      ["RO1 / RQ1 — Consent object, Eq. (46), Algorithm 1", "§6.1", "Patient subsystem: consent creation; state PENDING_SIGNATURE", "Consents f050c29a and 04da25f5 in the exported audit ledger"],
      ["RO2 / RQ2 — DID and VC verification, Algorithm 2", "§6.2", "Guardian subsystem: EIP-712 typed-data signatures, off-chain signer recovery per guardian DID ⦅(VI itself performs identifier- and credential-format validation only; DID resolution is reserved for the next stage)⦆", "Verified signer 0x3Af549b0… recorded per SIGN_CONSENT event"],
      ["RO3 / RQ3 — Threshold authorisation, Eq. (49), Algorithm 3", "§6.3", "2-of-2 ceremony with N = |G|; SBT minted on threshold", "Mint tx 0x8be1b99e…daf13d, block 11,771,243, token #1"],
      ["⦃RO4 / RQ4 — Policy predicate VP, Eqs. (52)–(53), Algorithm 4⦄", "⦃§6.4⦄", "⦃Doctor subsystem: requested scope SR must be a non-empty subset of the authorised scope SC; purpose hash compared with the consent⦄", "⦃STATE_CHECK and DATA_ACCESS events recording VP = PASS for the four-module scope of consents f050c29a and 04da25f5⦄"],
      ["Decision rule and trust predicates, Eq. (54), Figure 8", "⦅§5.1.2, §6.4, §6.6⦆", "Doctor subsystem: five-verdict decision matrix, ALLOW / DENY with failed-check listing", "GRANTED and DENIED DATA_ACCESS events; SA-jurisdiction denial"],
      ["⦅RO5 / RQ5 — Temporal and lifecycle trust, Eqs. (58)–(59), Algorithm 5⦆", "§6.5", "Six-state lifecycle with on-chain revocation (Section 6.8.6)", "Revoke tx 0x017efb9d…dceaa, block 11,771,307"],
      ["⦅RO6 / RQ6 — Empirical validation, Eq. (61), Algorithm 6 (formal component outstanding)⦆", "§6.6", "Auditor subsystem and the independent verifier re-checking every transaction receipt", "60-event ledger; RESULT: ALL CHECKS PASSED; token #2, block 11,771,581"],
    ] };
  // red-cell table
  const widths = [2650, 1300, 2900, 2510];
  const mk = (txt, i, head) => new TableCell({
    borders: bAll, width: { size: widths[i], type: WidthType.DXA },
    shading: head ? { fill: "E8E8E8", type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ children: runs(String(txt), { size: BODY - 6, bold: head, color: head ? "000000" : RED, font: FONT }) })],
  });
  C.push(new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 160, after: 80 }, keepNext: true,
    children: [new TextRun({ text: "Table 17: ", bold: true, font: FONT, size: BODY - 3, color: RED }), new TextRun({ text: t.caption.replace(/\.$/, ""), font: FONT, size: BODY - 3, color: RED })] }));
  C.push(new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: t.header.map((h, i) => mk(h, i, true)) }),
      ...t.rows.map(r => new TableRow({ cantSplit: true, children: r.map((c, i) => mk(c, i, false)) }))] }));
  C.push(new Paragraph({ spacing: { after: 180 }, children: [] }));
}
if (!appendixDone) pushAppendix();

// ---------- document ----------
const doc = new Document({
  creator: "Yasir Dhaifallah O Alyoubi",
  title: "A Trusted Authorisation Framework for Multi-Party Patient Consent in Healthcare Data Sharing",
  styles: {
    default: { document: { run: { font: FONT, size: BODY } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 32, bold: true, color: "000000" }, paragraph: { outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 28, bold: true, color: "000000" }, paragraph: { outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 25, bold: true, color: "000000" }, paragraph: { outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: { page: { margin: { top: 1300, bottom: 1300, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], size: 20, font: FONT })] })] }) },
    children: C,
  }],
});
// dump adjacency spots (addition-style edits where the old block is retained)
if (process.env.DUMP_ADJ) {
  const out = [];
  for (const [bi, list] of edits.entries()) {
    for (const e of list) {
      if ([38,45,46,47,48,49,52,53].includes(e.no)) continue;
      if ([1,2,35,36].includes(e.no)) continue;
      const h = HUMAN[String(e.no)];
      if (!h || h === "SKIP") continue;
      const b = blocks[bi];
      const strike = e.exact && (b.t === "p") && (() => {
        const c = norm(e.cur.replace(/\*\*/g, ""));
        return c.length > 0.6 * Math.max(nText[bi].length, 1);
      })();
      const eqRepl = e.exact && b.t === "eq";
      if (strike || eqRepl || extraDelete.has(bi)) continue;  // old already removed
      out.push({ no: e.no, blockType: b.t, blockText: (b.text || b.caption || b.title || "").slice(0, 1200), newText: h.slice(0, 1200) });
    }
  }
  fs.writeFileSync("adjacency.json", JSON.stringify(out, null, 1));
  console.log("adjacency spots:", out.length);
}
Packer.toBuffer(doc).then(buf => {
  fs.writeFileSync("CA2_full.docx", buf);
  console.log("CA2_full.docx", buf.length, "bytes; figures embedded:", figIncluded);
});
