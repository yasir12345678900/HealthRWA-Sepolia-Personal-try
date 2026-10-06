const pptxgen = require("pptxgenjs");
const fs = require("fs");
const { applyTheme } = require("/root/.claude/skills/synced/00578ed4-301e-40ae-af05-0dbb005ee2ab_49610a22-0858-4237-b254-3a64e4f62ac5/pptx/scripts/apply_theme.js");
const D = JSON.parse(fs.readFileSync("/tmp/deck/data.json", "utf8"));
const IMG = n => "/tmp/deck/img/" + n + ".png";

const THEME = {
  name: "Trust Consent",
  headFontFace: "Arial", bodyFontFace: "Calibri",
  colors: { dk1: "0B1F33", lt1: "FFFFFF", dk2: "0B2A4A", lt2: "E8F4F8",
    accent1: "1FB5D6", accent2: "0B2A4A", accent3: "2E7D32", accent4: "F2A900", accent5: "C62828", accent6: "5B6B7A",
    hlink: "1FB5D6", folHlink: "5B6B7A" },
};
const W = 13.333, H = 7.5;
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.subject = "Candidature Reassessment";
pres.author = "Yasir Dhaifallah O Alyoubi";
pres.title = "A Trusted Authorisation Framework for Multi-Party Patient Consent in Healthcare Data Sharing";
pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
const C = pres.SchemeColor;
const NOTES2 = fs.existsSync("/tmp/deck/notes_simple.json") ? JSON.parse(fs.readFileSync("/tmp/deck/notes2.json", "utf8")) : {};
let SLN = 0; const _add = pres.addSlide.bind(pres);
pres.addSlide = (o) => { const sl = _add(o); const k = String(++SLN); const _n = sl.addNotes.bind(sl); let done = false;
  sl.addNotes = (t) => { if (!done) { done = true; _n(NOTES2[k] || t); } return sl; };
  ALLSL.push(() => { if (!done && NOTES2[k]) sl.addNotes(NOTES2[k]); });
  return sl; };
const ALLSL = [];
const WHITE = "FFFFFF", NAVY = "0B2A4A", CYAN = "1FB5D6", INK = "0B1F33";

// ---------- layouts ----------
pres.defineSlideMaster({ title: "CONTENT", background: { path: IMG("bg") },
  objects: [{ placeholder: { options: { name: "title", type: "title", x: 0.9, y: 0.25, w: 11.5, h: 0.8, fontSize: 30, bold: true, color: WHITE, align: "center", valign: "middle", fontFace: "Arial" }, text: "" } }],
  slideNumber: { x: 12.45, y: 6.95, w: 0.6, h: 0.35, color: WHITE, fontSize: 11, align: "right" } });
pres.defineSlideMaster({ title: "COVER", background: { path: IMG("bgtitle") }, objects: [] });

// ---------- helpers ----------
let sec = "";
function slide(title, notes, section) {
  if (section && section !== sec) { pres.addSection({ title: section }); sec = section; }
  const s = pres.addSlide({ masterName: "CONTENT", sectionTitle: sec });
  if (title) s.addText(title, { placeholder: "title" });
  if (notes) s.addNotes(notes);
  return s;
}
function panel(s, x, y, w, h, name) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: WHITE }, line: { color: WHITE }, objectName: name || "panel",
    shadow: { type: "outer", color: "000000", opacity: 0.35, blur: 8, offset: 3, angle: 90 } });
}
function fig(s, key, x, y, w, h, pad = 0.12) {
  panel(s, x, y, w, h, key + " panel");
  const [iw, ih] = D.dims[key]; const bw = w - 2 * pad, bh = h - 2 * pad;
  const sc = Math.min(bw / iw, bh / ih); const fw = iw * sc, fh = ih * sc;
  s.addImage({ path: IMG(key), x: x + pad + (bw - fw) / 2, y: y + pad + (bh - fh) / 2, w: fw, h: fh, objectName: key });
}
function bullets(s, items, x, y, w, h, size = 18) {
  s.addText(items.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < items.length - 1 } })),
    { x, y, w, h, fontSize: size, color: WHITE, valign: "top", paraSpaceAfter: 10, isTextBox: true, objectName: "bullets" });
}
function caption(s, t, x, y, w) {
  s.addText(t, { x, y, w, h: 0.35, fontSize: 12, italic: true, color: WHITE, align: "center", isTextBox: true, objectName: "caption" });
}
function table(s, header, rows, x, y, w, colW, size = 11, opts = {}) {
  const hdr = header.map(h => ({ text: h, options: { bold: true, color: WHITE, fill: { color: NAVY }, fontSize: size, valign: "middle" } }));
  const body = rows.map(r => r.map((c, i) => {
    const o = { color: INK, fill: { color: WHITE }, fontSize: size, valign: "middle" };
    if (opts.grade && i > 0) { o.align = "center"; o.bold = true;
      o.color = c === "Yes" ? "2E7D32" : c === "No" ? "C62828" : "8A6D00"; }
    if (opts.firstBold && i === 0) o.bold = true;
    return { text: c, options: o };
  }));
  s.addTable([hdr, ...body], { x, y, w, colW, border: { type: "solid", pt: 0.75, color: "9FB3C8" }, margin: [0.03, 0.08, 0.03, 0.08], rowH: opts.rowH, autoPage: false, objectName: "table" });
}
function card(s, x, y, w, h, head, body, color) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.1, fill: { color: WHITE, transparency: 8 }, line: { color: color || CYAN, width: 1.5 }, objectName: "card " + head });
  s.addText([{ text: head, options: { bold: true, fontSize: 19, color: color || NAVY, breakLine: true } },
    { text: body, options: { fontSize: 16, color: INK } }],
    { x: x + 0.15, y: y + 0.1, w: w - 0.3, h: h - 0.2, valign: "top", isTextBox: true, paraSpaceAfter: 4, objectName: "card text " + head });
}
function chip(s, x, y, text, color) {
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: text.length > 20 ? 3.5 : 2.6, h: 0.45, rectRadius: 0.2, fill: { color }, line: { color }, objectName: "status chip" });
  s.addText(text, { x, y, w: text.length > 20 ? 3.5 : 2.6, h: 0.45, fontSize: 14, bold: true, color: WHITE, align: "center", valign: "middle", isTextBox: true, objectName: "status text" });
}


// ================= SIMPLE DECK =================
const SUB = (s, t) => s.addText(t, { x: 0.8, y: 1.05, w: 11.7, h: 0.45, fontSize: 18, italic: true, color: CYAN, isTextBox: true, objectName: "subtitle" });
const BIG = (s, x, y, n, l, w = 3.6) => {
  s.addText(n, { x, y, w, h: 0.95, fontSize: 44, bold: true, color: CYAN, isTextBox: true, margin: 0, objectName: "stat " + l });
  s.addText(l, { x, y: y + 0.95, w, h: 0.7, fontSize: 16, color: WHITE, isTextBox: true, margin: 0, objectName: "stat label " + l });
};

// 1 cover
pres.addSection({ title: "Cover" }); sec = "Cover";
{
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: "Cover" });
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 10.6, y: 0.3, w: 2.3, h: 1.25, rectRadius: 0.1, fill: { color: WHITE }, line: { color: WHITE }, objectName: "logo card" });
  s.addImage({ path: IMG("uts"), x: 10.75, y: 0.33, w: 2.0, h: 1.28, objectName: "UTS logo" });
  s.addText("A Trusted Authorisation Framework for Multi-Party Patient Consent in Healthcare Data Sharing",
    { x: 1.4, y: 1.7, w: 10.5, h: 1.6, fontSize: 32, bold: true, italic: true, color: WHITE, align: "center", valign: "middle", fontFace: "Arial", isTextBox: true, objectName: "deck title" });
  s.addText("Candidature Reassessment", { x: 4.4, y: 3.35, w: 4.5, h: 0.5, fontSize: 20, bold: true, color: CYAN, align: "center", isTextBox: true, objectName: "subtitle" });
  s.addText([
    { text: "Principal Supervisor: Professor Farookh Hussain", options: { breakLine: true } },
    { text: "Co-Supervisor: Dr. Firas Al-Doghman", options: { breakLine: true } },
    { text: "Presenter: Yasir Dhaifallah O Alyoubi", options: { breakLine: true } },
    { text: "STUDENT ID #: 24724078" }],
    { x: 2.4, y: 4.2, w: 8.5, h: 1.9, fontSize: 18, bold: true, italic: true, color: WHITE, align: "center", isTextBox: true, paraSpaceAfter: 4, objectName: "people" });
  s.addNotes("Good morning everyone. My name is Yasir Alyoubi. My principal supervisor is Professor Farookh Hussain and my co-supervisor is Dr Firas Al-Doghman. This is my candidature reassessment. My research is about one question: how can a hospital system be sure that a request for a patient's data is really allowed? Not only who is asking, but also whether the patient and the guardians agreed, whether the request is inside the agreed data, and whether the consent is still valid. I will show the problem, the literature, my framework, the working prototype, and the results.");
}

// 2 outline
{
  const s = slide("OUTLINE", "Here is the plan of my talk. First the problem and the literature review. Then the gaps, the questions and the objectives. Then the framework and the prototype. Then the validation and the evaluation results. Then what is still open and the research plan. I close with a demonstration of the prototype through the slides: one real consent from creation to revocation.");
  const L = ["THE PROBLEM", "LITERATURE REVIEW", "GAPS, QUESTIONS AND OBJECTIVES", "THE FRAMEWORK", "VALIDATION AND EVALUATION", "WHY THIS MATTERS"];
  const R = ["WHAT IS STILL OPEN", "RESEARCH PLAN", "DEMO: THE HALAH PROTOTYPE", "REFERENCES"];
  [L, R].forEach((col, ci) => col.forEach((t, i) => {
    const x = ci === 0 ? 1.6 : 7.1, y = 1.35 + i * 0.95, n = String(ci * 6 + i + 1).padStart(2, "0");
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w: 0.8, h: 0.7, rectRadius: 0.08, fill: { color: ci ? CYAN : "2F6FB0" }, line: { color: WHITE, width: 1 }, objectName: "number " + n });
    s.addText(n, { x, y, w: 0.8, h: 0.7, fontSize: 20, bold: true, color: WHITE, align: "center", valign: "middle", isTextBox: true, objectName: "number text " + n });
    s.addText(t, { x: x + 1.0, y, w: 4.6, h: 0.7, fontSize: 18, bold: true, color: WHITE, valign: "middle", isTextBox: true, objectName: "item " + n });
  }));
}

// 3 problem
{
  const s = slide("THE PROBLEM", "Healthcare data is very sensitive. One decision to share it can involve many people: the patient, one or more guardians, the doctor and the hospital. Today, consent is usually just a stored record. The record says that permission was given, but it does not check anything when someone asks for the data. A valid login is not the same as the right to see this patient's data. And even with approval, a request can ask for more data than the patient allowed, or come after the consent has expired or was revoked. So the problem is: there is no single trusted decision that checks all of these things together.", "The Problem");
  bullets(s, ["Healthcare data is shared between many independent parties: patient, guardians, doctor, hospital.",
    "Today, consent is a stored record. It shows that permission was given, but it checks nothing at access time.",
    "A valid identity does not prove the right to see this patient's data.",
    "A request can ask for more data than allowed, or arrive after the consent expired or was revoked.",
    "None of the reviewed studies proves or tests the whole decision."], 0.9, 1.4, 6.8, 5.4, 19);
  card(s, 8.1, 1.6, 4.3, 4.5, "In one sentence", "There is no trusted mechanism that checks identity, authority, multi-party approval, policy, time and lifecycle together in one access decision, with evidence that it is secure.");
}

// 4 key idea
{
  const s = slide("THE KEY IDEA", "My answer is simple to say. Consent becomes an object that the system can check, not a record that it stores. I call it C, and it has six parts. I is identity: who is involved. A is authority: the guardians who must approve and how many are needed. P is policy: the purpose and the data scope. T is time: the validity window. L is jurisdiction. E is evidence: the signatures, the token and whether the consent is revoked. At every request, the system checks all six parts. If one check fails, the answer is no.", "The Problem");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.9, y: 1.3, w: 11.4, h: 1.5, rectRadius: 0.1, fill: { color: NAVY, transparency: 15 }, line: { color: CYAN, width: 1.5 }, objectName: "idea box" });
  s.addText([{ text: "Consent is not a stored record. It is an object checked at every request.", options: { bold: true, fontSize: 20, color: WHITE, breakLine: true } },
    { text: "C = (I, A, P, T, L, E)", options: { bold: true, fontSize: 28, color: CYAN } }],
    { x: 1.1, y: 1.35, w: 11.0, h: 1.4, align: "center", valign: "middle", isTextBox: true, objectName: "idea text" });
  const items = [["I  Identity", "Who is the patient, the doctor and each guardian (DID)."], ["A  Authority", "The guardian set G and how many approvals are needed (N)."],
    ["P  Policy", "The purpose and the data scope that were agreed."], ["T  Time", "When the consent starts and when it expires."],
    ["L  Jurisdiction", "Where the request may come from."], ["E  Evidence", "Signatures, the token, and whether it is revoked."]];
  items.forEach(([h, b], i) => card(s, 0.9 + (i % 3) * 3.9, 3.05 + Math.floor(i / 3) * 1.95, 3.6, 1.7, h, b));
}

// 5 SLR process
{
  const s = slide("LITERATURE REVIEW: HOW I DID IT", "I did a systematic literature review following PRISMA 2020. A written protocol fixed the questions, the databases, one search query, the criteria and the quality items before screening started. I searched seven databases. They returned 9,256 records. After removing duplicates, 6,039 were screened by title, 3,129 by abstract, and 1,800 full texts were prioritised. At the reporting checkpoint, 64 full texts were assessed and 47 met the criteria. From these I analysed 25 primary studies in depth: 23 core studies and 2 supporting studies.", "Literature Review");
  fig(s, "F2", 0.7, 1.2, 6.3, 5.95);
  BIG(s, 7.6, 1.4, "9,256", "records from seven databases");
  BIG(s, 7.6, 3.2, "47", "studies met the criteria at the checkpoint");
  BIG(s, 7.6, 5.0, "25", "primary studies analysed (23 core + 2)");
}

// 6 findings
{
  const s = slide("LITERATURE REVIEW: WHAT I FOUND", "This figure summarises the review. The good news: every requirement is met by some study. The problem: no study puts all the conditions together in one access decision. I call this the conjunction gap. And no study proves or tests the whole decision. Formal proofs exist in only 4 of the 25 studies, and they cover a small part. I call this the assurance gap. These two gaps are what my research fills.", "Literature Review");
  fig(s, "F5", 0.7, 1.2, 7.6, 5.95);
  card(s, 8.6, 1.4, 4.0, 2.6, "Conjunction gap", "Each condition exists somewhere, but no study joins identity, authority, approval, policy and time in one decision.", CYAN);
  card(s, 8.6, 4.3, 4.0, 2.6, "Assurance gap", "The whole decision is neither formally proved nor systematically tested. Proofs exist in only 4 of 25 studies.", "F2A900");
}

// 7 gaps
{
  const s = slide("SIX RESEARCH GAPS", "From the comparison of the 25 studies I defined six gaps, one for each requirement. Gap 1: consent is only a record. Gap 2: identity does not prove authority. Gap 3: multi-party approval is not a standing condition of every access. Gap 4: purpose and scope are rarely checked with identity and approval. Gap 5: time and revocation are checked at registration, not at each request. Gap 6: the whole decision is not proved or tested.", "Gaps, Questions and Objectives");
  const G = ["Consent is treated as a record of permission, not as something the system evaluates.",
    "Identity shows who a person is, not what they may do. Only 10 of 25 studies check authority separately.",
    "Multi-party approval is a backup path or a one-time step, not a condition of every access.",
    "Purpose, data scope and jurisdiction are rarely checked in the same decision as identity and approval.",
    "Time, lifecycle and revocation are often checked once, at registration, not at each request.",
    "The decision as a whole is neither formally proved nor systematically tested."];
  G.forEach((t, i) => card(s, 0.7 + (i % 2) * 6.05, 1.3 + Math.floor(i / 2) * 1.85, 5.85, 1.65, "Gap " + (i + 1), t));
}

// 8 RQs
{
  const s = slide("RESEARCH QUESTIONS", "The main question is: how can a trust-oriented computing framework establish and enforce trustworthy multi-party consent for decentralised healthcare data sharing, under identity, authority and policy constraints? It has six sub-questions, one per gap: modelling consent, identity and authority, multi-party approval, policy and scope, time and lifecycle, and formal and empirical assurance.", "Gaps, Questions and Objectives");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.8, y: 1.25, w: 11.7, h: 1.45, rectRadius: 0.12, fill: { color: NAVY, transparency: 15 }, line: { color: CYAN, width: 2 }, objectName: "rq box" });
  s.addText("How can a trust-oriented computing framework establish and enforce trustworthy multi-party consent for decentralised healthcare data sharing under identity, authority, and policy constraints?",
    { x: 1.0, y: 1.3, w: 11.3, h: 1.35, fontSize: 18, italic: true, color: WHITE, align: "center", valign: "middle", isTextBox: true, objectName: "rq text" });
  const Q = [["RQ1", "How can consent be modelled as an object that carries identity, authority, policy and evidence?"],
    ["RQ2", "How can DIDs and credentials prove who a person is and, separately, what they may do?"],
    ["RQ3", "How can several guardians approve together, so that no single person can approve alone?"],
    ["RQ4", "How can purpose and data scope stop valid identities from reaching data they were not given?"],
    ["RQ5", "How can time and lifecycle controls reject access after expiry or revocation?"],
    ["RQ6", "How can the security properties be formally defined and empirically tested?"]];
  Q.forEach(([h, b], i) => card(s, 0.8 + (i % 3) * 3.95, 2.95 + Math.floor(i / 3) * 2.05, 3.75, 1.85, h, b));
}

// 9 ROs
{
  const s = slide("RESEARCH OBJECTIVES AND STATUS", "Each question has one objective. RO1 to RO4 are done and validated with the prototype. RO5, time and lifecycle, is in progress: the validity window and revocation work now, and consent changes, delegation and guardian-set changes are for the next stage. RO6 is partially completed: the automated tests, the attack tests and the measurements are done, and the formal proofs are for the next stage.", "Gaps, Questions and Objectives");
  table(s, ["Objective", "In simple words", "Status"], [
    ["RO1", "Make consent an object the system can check: C = (I, A, P, T, L, E)", "Done"],
    ["RO2", "Check who a person is (DID) separately from what they may do (credential)", "Done"],
    ["RO3", "Require approval from all listed guardians, each with a verified signature", "Done"],
    ["RO4", "Allow only requests inside the agreed purpose, data scope and jurisdiction", "Done"],
    ["RO5", "Reject access after expiry or revocation, and control the consent lifecycle", "In Progress"],
    ["RO6", "Define the security properties, prove them formally and test them empirically", "Partially completed"]],
    0.8, 1.4, 11.7, [1.5, 7.6, 2.6], 16, { firstBold: true, rowH: 0.82 });
}

// 10 methodology
{
  const s = slide("RESEARCH METHODOLOGY", "These are the steps I followed. One: identify the problem. Two: the systematic review. Three: the gaps and the questions. Four: the objectives. Five: the design: the MVC architecture, the consent object and four algorithms. Six: the prototype on the Sepolia test network. Seven: the evaluation with live scenarios, measurements and attack tests. The formal assurance is the next stage.", "Gaps, Questions and Objectives");
  const steps = [["Problem", "Consent is a passive record; no single trusted decision"], ["Literature review", "PRISMA 2020; 25 primary studies"], ["Gaps and questions", "Gap 1 to Gap 6; RQ1 to RQ6"], ["Objectives", "RO1 to RO6"],
    ["Design", "MVC architecture, consent object C, Algorithms 1 to 4"], ["Prototype", "HALAH; ConsentSBTv3 on Sepolia"], ["Evaluation", "Live scenarios, measurements and 12 attack tests; formal proofs next"]];
  steps.forEach(([h, b], i) => {
    const x = 0.55 + i * 1.78, y = 1.7;
    s.addShape(pres.shapes.OVAL, { x: x + 0.53, y, w: 0.6, h: 0.6, fill: { color: i < 6 ? CYAN : "6D5BA8" }, line: { color: WHITE, width: 1.5 }, objectName: "step number " + (i + 1) });
    s.addText(String(i + 1), { x: x + 0.53, y, w: 0.6, h: 0.6, fontSize: 20, bold: true, color: WHITE, align: "center", valign: "middle", isTextBox: true, objectName: "step num text " + (i + 1) });
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: y + 0.8, w: 1.66, h: 3.2, rectRadius: 0.1, fill: { color: WHITE }, line: { color: CYAN, width: 1.5 }, objectName: "step box " + (i + 1) });
    s.addText([{ text: h, options: { bold: true, fontSize: 14, color: NAVY, breakLine: true } }, { text: b, options: { fontSize: 13, color: INK } }],
      { x: x + 0.05, y: y + 0.9, w: 1.56, h: 3.0, valign: "top", align: "center", paraSpaceAfter: 8, isTextBox: true, objectName: "step text " + (i + 1) });
  });
  s.addShape(pres.shapes.RIGHT_ARROW, { x: 0.55, y: 6.0, w: 12.3, h: 0.45, fill: { color: CYAN, transparency: 25 }, line: { color: CYAN }, objectName: "process arrow" });
  s.addText("From the problem to the evaluated prototype", { x: 0.8, y: 6.0, w: 11.5, h: 0.45, fontSize: 14, bold: true, color: WHITE, align: "center", valign: "middle", isTextBox: true, objectName: "arrow label" });
}

// 11 MVC
{
  const s = slide("THE FRAMEWORK: ARCHITECTURE", "The framework uses the Model, View, Controller pattern. The View is the four interfaces: patient, guardian, doctor and auditor. The View never decides access. Every security decision is made in the Controller: it checks identity and authority, collects the approvals, enforces the policy and records the evidence. The Model keeps the consent, the approvals and the evidence. Health data are released only when the Controller says ALLOW.", "The Framework");
  fig(s, "F6", 1.2, 1.2, 10.9, 5.95);
}

// 12 decision rule
{
  const s = slide("THE FRAMEWORK: THE DECISION RULE", "This is the heart of the framework. Access is allowed only when five checks are all true. VI: the identity and the authority are valid. VA: all required guardians approved, the token exists, and the consent is not revoked. VP: the purpose and the requested data are inside what was agreed. VT: the request is inside the validity window. VL: the jurisdiction matches. If any one check fails, the answer is DENY. In the prototype, a Groth16 zero-knowledge proof must also verify before any data is released, and every decision on an active consent is written to the audit ledger.", "The Framework");
  s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: 0.8, y: 1.3, w: 11.7, h: 1.2, rectRadius: 0.1, fill: { color: NAVY, transparency: 15 }, line: { color: CYAN, width: 1.5 }, objectName: "decision box" });
  s.addText("Decision(C, R, t) = ALLOW  ⟺  VI(u) ∧ VA(C) ∧ VP(C, R) ∧ VT(C, t) ∧ VL(C, R)", { x: 0.9, y: 1.35, w: 11.5, h: 1.1, fontSize: 24, bold: true, color: WHITE, align: "center", valign: "middle", fontFace: "Cambria", isTextBox: true, objectName: "decision text" });
  const P = [["VI", "Identity and authority are valid"], ["VA", "All guardians approved; token exists; not revoked"], ["VP", "Purpose and data scope are inside the consent"], ["VT", "Inside the validity window"], ["VL", "Jurisdiction matches"]];
  P.forEach(([h, b], i) => card(s, 0.8 + i * 2.37, 2.85, 2.2, 1.75, h, b));
  bullets(s, ["One failed check is enough to say DENY.", "A Groth16 zero-knowledge proof must also verify before any data is released.", "Every decision on an ACTIVE consent is written to the audit ledger with its decision matrix."], 0.9, 4.9, 11.5, 2.0, 18);
}

// 13-18 RO slides
const RO = [
  ["RO1", "STEP 1: THE PATIENT CREATES THE CONSENT", "Trust-centric consent model", "F10", "Done",
    ["The patient chooses the doctor, the guardians, the data modules, the start and expiry time, and the jurisdiction.", "In this prototype the purpose is fixed to Treatment.", "Bad input is rejected, for example an empty data scope or a malformed guardian DID.", "The consent object C is built and stored as PENDING_SIGNATURE.", "Nothing goes on the blockchain until all guardians approve."],
    "Step one. The patient creates the consent. The patient chooses the doctor, the guardians, the data modules, the start and expiry time, and the jurisdiction. The system checks every field: an empty data scope or a malformed guardian DID is rejected. Then the consent object C is built and stored as pending. Nothing goes on the blockchain yet. This is RO1, and it is done."],
  ["RO2", "STEP 2: WHO ARE YOU, AND WHAT MAY YOU DO?", "Decentralised identity and authority", "F12", "Done",
    ["Identity is checked through the DID; authority through a verifiable credential.", "Identity is not authority: a valid DID alone never gives access.", "In the prototype: a DID-format check and EIP-712 signature recovery for each guardian.", "Full DID resolution and credential validation are planned for the next stage."],
    "Step two. I separate two questions: who are you, and what may you do? The DID answers the first. The credential answers the second. A valid identity alone never gives access. To be clear about the current state: the prototype checks the DID format and recovers each guardian's EIP-712 signature. Full DID resolution and credential validation are planned for the next stage. RO2 is done at the design and prototype level."],
  ["RO3", "STEP 3: THE GUARDIANS APPROVE TOGETHER", "Multi-party authorisation", "F13", "Done",
    ["The guardian set G is fixed when the consent is created.", "Each guardian signs an EIP-712 approval; the system recovers the signer and checks it is in G.", "Approvals from outsiders, replays and duplicates are not counted.", "N-of-N rule: every listed guardian must sign (2-of-2 in the demo).", "When all have signed, a soulbound token is minted on Sepolia in the background.", "In the prototype the guardian keys are derived from the guardian DIDs; wallet-held keys are for the next stage."],
    "Step three. No single person can approve alone. Each guardian signs with an EIP-712 signature. The system recovers the signer and checks it is one of the listed guardians. Outsiders, replays and duplicates are not counted. In the demo, two of two guardians must sign. When both have signed, a soulbound consent token is minted on the Sepolia test network in the background. RO3 is done."],
  ["RO4", "STEP 4: ONLY THE AGREED DATA AND PURPOSE", "Policy- and context-aware access", "F14", "Done",
    ["The requested data must be a non-empty subset of the agreed data scope.", "The purpose must be a supported purpose of the consent.", "Time and jurisdiction are checked in the same decision.", "A Groth16 proof must verify before any data is retrieved.", "Example: asking for Procedure when only Observation and Medication were agreed gives DENY."],
    "Step four. A valid identity and all approvals are still not enough. The requested data must be inside the agreed data scope. For example, if the consent allows Observation and Medication, a request that also asks for Procedure is denied. The purpose, the time and the jurisdiction are checked in the same decision, and a Groth16 proof must verify before any data is released. RO4 is done."],
  ["RO5", "STEP 5: TIME AND LIFECYCLE", "Time and lifecycle control", "F35", "In Progress",
    ["Working now: the validity window is stored on-chain and checked at every request.", "Working now: revocation end to end, including an on-chain revoke transaction.", "Working now: a clear lifecycle: PENDING_SIGNATURE, PENDING_TOKEN, NOT_STARTED, ACTIVE, EXPIRED, REVOKED.", "Next stage: the lifecycle transition check, consent modification, delegation, guardian-set changes and a formal lifecycle model."],
    "Step five. Time and lifecycle. What works now: the validity window is stored on-chain and checked at every request, revocation works end to end with an on-chain transaction, and the consent moves through a clear lifecycle. What is still open: the lifecycle transition check, consent modification, delegation, changes to the guardian set, and a formal lifecycle model. That is why RO5 is in progress."],
  ["RO6", "STEP 6: PROVE IT AND TEST IT", "Formal assurance and validation", "F16", "Partially completed",
    ["Done: 36 automated tests pass, including 12 attack scenarios A1 to A12.", "Done: gas, confirmation latency and processing time measured.", "Done: a live request from the wrong jurisdiction was refused against a Sepolia-anchored consent.", "Next stage: formal proofs or model checking of the security properties, and a larger evaluation under load."],
    "Step six. Prove it and test it. The testing part is done: 36 automated tests pass, including twelve attack scenarios, and I measured the cost and the timing. The proof part is the next stage: formal proofs or model checking of the security properties, and a larger evaluation under load. That is why RO6 is partially completed."],
];
RO.forEach(([ro, title, sub, figKey, status, pts, notes]) => {
  const s = slide(title, notes, "The Framework");
  s.addText(ro + ": " + sub, { x: 0.8, y: 1.05, w: 7.0, h: 0.45, fontSize: 20, bold: true, italic: true, color: CYAN, isTextBox: true, objectName: "objective subtitle" });
  chip(s, 0.8, 1.6, "Status: " + status, status === "Done" ? "2E7D32" : status === "In Progress" ? "B7791F" : "6D5BA8");
  bullets(s, pts, 0.8, 2.3, 6.7, 4.7, 16);
  const tall = D.dims[figKey][1] > D.dims[figKey][0];
  if (ro === "RO2") {
    fig(s, figKey, 8.2, 1.1, 4.4, 5.4);
    s.addText("Target design. The prototype now performs a DID-format check and EIP-712 signature recovery.", { x: 8.2, y: 6.6, w: 4.4, h: 0.6, fontSize: 12, italic: true, color: WHITE, align: "center", valign: "top", isTextBox: true, objectName: "caption" });
  } else if (tall) fig(s, figKey, 8.2, 1.1, 4.4, 6.05); else fig(s, figKey, 7.8, 2.0, 5.1, 3.6);
});

// 22 validation
{
  const s = slide("VALIDATION: DOES IT DO WHAT IT SHOULD?", "Validation asks: does the system do what it should? I used five kinds of evidence. Valid scenarios: the legitimate requests were allowed. Negative scenarios: the wrong jurisdiction and the revoked consent were refused. Adversarial scenarios: eleven of twelve attacks are refused after the hardening. Automated tests: all 36 pass. And an independent check: the on-chain state matches the local state.", "Validation and Evaluation");
  table(s, ["Evidence", "What it checks", "Pass rule", "Result"], [
    ["Valid scenarios", "Legitimate requests get access", "Observed = expected", "Scenarios 1 to 3: consent created, 2-of-2 approval, ALLOW"],
    ["Negative scenarios", "Wrong requests are refused", "Any failed check gives DENY", "Scenario 4: wrong jurisdiction refused. Scenario 5: revoked consent refused"],
    ["Attack scenarios", "Deliberate attempts to bypass a check, A1 to A12", "Every attack is refused", "11 of 12 refused after the hardening (A11: the changed digest is not yet compared)"],
    ["Automated tests", "23 functional tests and 13 adversarial tests", "All pass", "36 of 36 pass"],
    ["Independent check", "On-chain receipts against the local consent state", "Local state = on-chain state", "Scenario 6: all checks passed"]],
    0.7, 1.3, 11.9, [2.3, 3.4, 2.8, 3.4], 14, { firstBold: true, rowH: [0.55, 0.95, 0.95, 0.95, 0.95, 0.95] });
}

// 23 attacks
{
  const s = slide("VALIDATION: TWELVE ATTACK SCENARIOS", "I also attacked my own system twelve times. For example: a signer who is not a guardian, a replayed or duplicate approval, a request outside the data scope, an expired or revoked consent, and a tampered proof. Before the hardening on 1 October, three attacks were accepted when the service functions were called directly. After the hardening, eleven of twelve are refused. The one that remains, A11, changes a stored digest: the prototype does not yet compare the digest, so it is marked neutral, and that is on the list for the next stage.", "Validation and Evaluation");
  fig(s, "F43", 0.7, 1.2, 7.2, 5.95);
  BIG(s, 8.3, 1.35, "12", "attack scenarios, A1 to A12", 4.3);
  BIG(s, 8.3, 3.25, "11 / 12", "refused after the hardening", 4.3);
  BIG(s, 8.3, 5.15, "36", "automated tests pass", 4.3);
}

// 24 evaluation
{
  const s = slide("EVALUATION: HOW FAST AND HOW MUCH?", "Evaluation asks: how fast is it, and what does it cost? The decision rule itself takes about 2 microseconds. One guardian signature takes about 11 milliseconds. The Groth16 proof is the slowest part: about 1.4 seconds to generate and 0.47 seconds to verify. Anchoring on Sepolia takes about 11.5 seconds, but it runs in the background, so users do not wait. A revoke uses about one sixth of the gas of a mint. The timings were measured on 1 October 2026; the gas and the anchoring times come from the five Sepolia transactions of September 2026. They are indicative.", "Validation and Evaluation");
  table(s, ["Component", "Median", "Min", "Max", "n"], [
    ["Decision rule, five checks", "2.37 µs", "2.32 µs", "31.59 µs", "1,000"],
    ["One EIP-712 signature", "10.93 ms", "10.55 ms", "15.64 ms", "20"],
    ["Groth16 proof generation", "1,401.1 ms", "1,342.8 ms", "5,349.6 ms", "20"],
    ["Groth16 proof verification", "465.3 ms", "441.0 ms", "525.1 ms", "20"],
    ["On-chain checkValid read", "573.5 ms", "568.2 ms", "715.5 ms", "20"],
    ["On-chain checkValidAt read", "574.6 ms", "568.2 ms", "745.6 ms", "20"],
    ["Anchoring confirmation", "11.5 s", "4.9 s", "22.1 s", "5"]],
    0.8, 1.4, 6.4, [2.3, 1.3, 1.0, 1.1, 0.7], 12, { firstBold: true, rowH: 0.6 });
  s.addText("Gas used: mint #1 196,406; revoke #1 32,980. No fee above 0.00021 ETH.", { x: 0.8, y: 6.3, w: 6.4, h: 0.5, fontSize: 14, bold: true, color: WHITE, isTextBox: true, objectName: "gas line" });
  fig(s, "F42", 7.45, 1.4, 5.15, 4.3);
  caption(s, "Timings measured on 1 October 2026; gas and anchoring from the five Sepolia transactions of September 2026; indicative only", 7.45, 5.8, 5.15);
}

// 25 comparison
{
  const s = slide("WHAT IS DIFFERENT FROM TODAY'S SYSTEMS", "Here is the difference in plain terms. Today, a central identity provider logs you in and a static permission decides. Consent is a stored record. In HALAH, every participant has a DID, and identity is separate from authority. Consent is an object checked at every request. All the guardians must approve. Five checks and a proof run before any data is released. Time and revocation are checked each time, and every decision on an active consent is logged with the reason.", "Contribution");
  table(s, ["Aspect", "Traditional EHR access control", "HALAH framework"], [
    ["Identity", "Central identity provider; institution login", "A DID for every participant; identity kept separate from authority"],
    ["Consent", "A stored record that permission was given", "An object C = (I, A, P, T, L, E), checked at every request"],
    ["Approval", "A static permission set by one party", "All listed guardians sign (EIP-712); no single party can approve alone"],
    ["Access check", "Log in, then check a static permission", "VI ∧ VA ∧ VP ∧ VT ∧ VL, plus a Groth16 proof before data is released"],
    ["Time and revocation", "Hard to verify once the permission is stored", "Validity window and revocation checked each time; on-chain revoke"],
    ["Audit", "A record that consent occurred", "Each decision on an active consent logged with its decision matrix; state anchored on Sepolia"]],
    0.7, 1.4, 11.9, [2.0, 4.4, 5.5], 14, { firstBold: true, rowH: 0.8 });
}

// 26 privacy
{
  const s = slide("DATA AND PRIVACY", "A few important points about data. No real patient data is used; the records are synthetic Synthea data. The medical records stay off-chain. The token on Sepolia stores only pseudonymous addresses, a hash of the purpose, the validity window, a jurisdiction code and a revocation flag. Data are released only on ALLOW and only inside the agreed scope. One known limitation: the plaintext purpose is visible in the mint transaction input, and I will address this in the next stage.", "Contribution");
  table(s, ["Aspect", "Key points"], [
    ["Data source", "No real patient data. Synthetic records from the Synthea dataset (Observation, Medication, Condition, Procedure)."],
    ["Data storage", "Medical records stay off-chain in the application. No medical content is written to the chain."],
    ["On-chain record", "Pseudonymous patient and requester addresses, a hash of the purpose, the validity window, a jurisdiction code and a revocation flag."],
    ["Access to data", "Records are released only on ALLOW and only within the agreed data scope."],
    ["Audit", "Each decision on an ACTIVE consent is recorded with its decision matrix."],
    ["Known limitation", "The plaintext purpose is passed in the mint transaction and is visible in the public transaction input."]],
    0.7, 1.35, 11.9, [2.4, 9.5], 15, { firstBold: true, rowH: 0.78 });
}

// 27 significance
{
  const s = slide("WHY THIS MATTERS", "Why does this matter? Scientifically: consent becomes an object that is evaluated, not stored; multi-party approval is a condition of every access; identity is separated from authority; and the whole decision is checked in one place and tested. Socially: patients and guardians decide together who sees the data, no single person can approve alone, every decision can be explained to an auditor, and medical records never go on the blockchain.", "Contribution");
  s.addText("Scientific", { x: 0.8, y: 1.15, w: 5.6, h: 0.45, fontSize: 20, bold: true, italic: true, color: CYAN, isTextBox: true, objectName: "sci heading" });
  s.addText("Social", { x: 6.9, y: 1.15, w: 5.6, h: 0.45, fontSize: 20, bold: true, italic: true, color: CYAN, isTextBox: true, objectName: "soc heading" });
  bullets(s, ["Consent is an evaluable object, C = (I, A, P, T, L, E), not a stored record.",
    "Multi-party approval is a standing condition of every access decision, and the patient defines who must approve.",
    "Identity is separated from authority, and all conditions are checked in one decision.",
    "A PRISMA 2020 review of 25 studies names the conjunction gap and the assurance gap.",
    "A working prototype on Sepolia, measured and attacked twelve times."], 0.8, 1.7, 5.7, 5.3, 16);
  bullets(s, ["Patients and their guardians decide together who may see the patient's data.",
    "No single person can approve access to sensitive health data alone.",
    "Every decision can be explained to an auditor: which check passed, which failed.",
    "Medical records stay off-chain; only consent evidence is shared.",
    "Supports trust when data move between hospitals and other independent parties."], 6.9, 1.7, 5.7, 5.3, 16);
}

// 28 open items
{
  const s = slide("WHAT IS STILL OPEN", "I want to be clear about what is not done yet, because this is what the next stage is for. First, the formal proofs: the properties are tested, but not yet proved by a formal model or model checking. Second, the rest of the lifecycle: consent modification, delegation and guardian-set changes. Third, full DID resolution, credential validation and wallet-held guardian keys; today it is a format check, a signature, and keys derived from the guardian DIDs. Fourth, the one open attack, A11, where a changed digest is not yet compared. Fifth, a larger evaluation under load with more users and consents. Sixth, the plaintext purpose in the mint transaction.", "What is Still Open");
  const O = [["Formal proofs", "The security properties are tested, not yet proved. Next: a formal model and model checking or proofs (RO6)."],
    ["Lifecycle", "Consent modification, delegation and guardian-set changes, with a formal lifecycle model (RO5)."],
    ["Identity and keys", "Full DID resolution, credential validation and wallet-held guardian keys. Today: a DID-format check, signature recovery and keys derived from the guardian DIDs (RO2, RO3)."],
    ["Attack A11", "A changed audit digest is not yet compared by any component. It is marked neutral, not refused."],
    ["Scale", "A larger evaluation under load, with more users, consents and concurrent requests."],
    ["Purpose on-chain", "The plaintext purpose is visible in the mint transaction input."]];
  O.forEach(([h, b], i) => card(s, 0.7 + (i % 3) * 4.05, 1.4 + Math.floor(i / 3) * 2.75, 3.85, 2.45, h, b, i < 2 ? "F2A900" : CYAN));
}

// 29 plan
{
  const s = slide("RESEARCH PLAN", "This is the plan. Chapters 1 to 6 are done. The conference paper was submitted to BWCCA 2026 in September. The SLR journal paper is in progress. Next: the complete evaluation, the paper on formal assurance and lifecycle trust, and the conclusion. The final assessment is planned for January 2027 and the thesis submission for March 2027.", "Research Plan");
  table(s, ["Task", "Description", "Target date", "Status"], [
    ["Chapters 1–4", "Introduction, SLR, Research Questions and Objectives, Research Methodology", "Completed", "Done"],
    ["Chapter 5", "Research Architecture (MVC) and framework design", "May 2026", "Done"],
    ["Chapter 6", "Proposed solution for RQ1 to RQ4 and the HALAH prototype", "Jul–Oct 2026", "Done"],
    ["Publication 1", "Conference paper submission, BWCCA 2026", "Sep 2026", "Done"],
    ["Publication 2", "SLR paper journal submission", "Oct 2026", "In Progress"],
    ["Chapter 7", "Complete prototype evaluation and integrated results", "Nov 2026", "Planned"],
    ["Publication 3", "Journal paper on formal security assurance, lifecycle trust and the evaluation of HALAH", "Dec 2026", "Planned"],
    ["Chapter 8", "Conclusion and future work", "Dec 2026", "Planned"],
    ["Final assessment", "Final candidature assessment defence", "Jan 2027", "Planned"],
    ["Thesis", "Complete thesis submission", "Mar 2027", "Planned"]],
    0.8, 1.2, 11.7, [1.9, 6.6, 1.6, 1.6], 13, { firstBold: true, rowH: 0.5 });
}

// 30 timeline
{
  const s = slide("RESEARCH TIMELINE", "The same plan as a timeline: what is completed, what is in progress, and the planned steps to the thesis submission in March 2027.", "Research Plan");
  fig(s, "Fplan", 0.8, 1.4, 11.7, 5.4);
}

// ---------- DEMO THROUGH THE SLIDES ----------
function demo(title, ro, roLabel, pts, notes, figs) {
  const s = slide(title, notes, "Demo: The HALAH Prototype");
  chip(s, 0.8, 1.1, ro, "2F6FB0");
  s.addText(roLabel, { x: 3.6, y: 1.1, w: 9.0, h: 0.45, fontSize: 16, italic: true, color: CYAN, valign: "middle", isTextBox: true, objectName: "ro label" });
  if (figs.length === 1) {
    fig(s, figs[0][0], 0.7, 1.75, 7.6, 5.15); caption(s, figs[0][1], 0.7, 6.95, 7.6);
    bullets(s, pts, 8.6, 1.75, 4.1, 5.2, 16);
  } else {
    s.addText(pts.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < pts.length - 1 } })),
      { x: 0.8, y: 1.6, w: 11.8, h: 0.95, fontSize: 14, color: WHITE, valign: "top", isTextBox: true, objectName: "bullets" });
    const fh = figs[2] || 4.0;
    fig(s, figs[0][0], 0.7, 2.6, 5.9, fh); caption(s, figs[0][1], 0.7, 2.65 + fh, 5.9);
    fig(s, figs[1][0], 6.75, 2.6, 5.9, fh); caption(s, figs[1][1], 6.75, 2.65 + fh, 5.9);
  }
  return s;
}
{
  const s = slide("DEMO: THE HALAH PROTOTYPE", "Now the demonstration, through the slides. HALAH means History Access Link for Authorised Healthcare. These are its parts: four interfaces, a soulbound token contract on the Sepolia test network, EIP-712 guardian signatures, a Groth16 proof at access time, synthetic Synthea data, and an audit ledger. In the next slides I walk through one real consent from creation to revocation. What you will see covers RO1 to RO4 in full, and the parts of RO5 and RO6 that are already working.", "Demo: The HALAH Prototype");
  s.addText("One real consent, from creation to revocation: RO1 to RO4 in full, and the working parts of RO5 and RO6.", { x: 0.8, y: 1.05, w: 11.7, h: 0.45, fontSize: 17, italic: true, color: CYAN, isTextBox: true, objectName: "demo subtitle" });
  const Cc = [["Four interfaces", "Patient, guardian, doctor and auditor"], ["Smart contract", "ConsentSBTv3, a soulbound ERC-721 token (ERC-5484) on the Sepolia testnet"],
    ["Guardian approval", "EIP-712 typed signatures, verified by signature recovery"], ["Access proof", "Groth16 zero-knowledge proof over a Poseidon commitment"],
    ["Data", "Synthetic Synthea records: Observation, Medication, Condition, Procedure"], ["Evidence", "Audit ledger of every decision on an active consent; no medical content on-chain"]];
  Cc.forEach(([h, b], i) => card(s, 0.7 + (i % 3) * 4.05, 1.7 + Math.floor(i / 3) * 2.6, 3.85, 2.3, h, b));
}
demo("DEMO 1: THE PATIENT CREATES THE CONSENT", "RO1", "Consent as an evaluable object",
  ["The patient chooses the doctor, two guardians, the data modules, the validity time and the jurisdiction AU.", "The purpose is fixed to Treatment in this prototype.", "An empty data scope or a malformed guardian DID is rejected.", "The consent is stored as PENDING_SIGNATURE. Nothing is on the blockchain yet."],
  "Demo step one. The patient creates the consent. Here you see the four data modules, the two guardians, the jurisdiction AU, and the state PENDING_SIGNATURE. The system checked every field before saving. Nothing has gone to the blockchain yet. This is RO1: consent as an object the system can check.",
  [["F21", "Patient subsystem after creation: four modules, two guardians, jurisdiction AU, state PENDING_SIGNATURE"]]);
demo("DEMO 2: THE FIRST GUARDIAN APPROVES", "RO3", "Multi-party approval: one signature is not enough",
  ["The first guardian signs an EIP-712 approval.", "The system recovers the signer and confirms it is a listed guardian.", "The counter shows 1 of 2. The consent stays pending.", "Approvals from outsiders, replays and duplicates would not be counted."],
  "Demo step two. The first guardian signs. The system recovers the signer from the EIP-712 signature and confirms that this address is one of the two listed guardians. The counter shows one of two. The consent is still pending, because one approval is never enough. This is RO3.",
  [["F22", "Guardian subsystem at the first approval: signature verified, multi-signature count 1/2"]]);
demo("DEMO 3: SECOND APPROVAL, TOKEN MINTED", "RO3", "Threshold reached: 2 of 2, then anchoring in the background",
  ["Second signature verified; threshold 2 of 2 reached", "A soulbound token is minted on Sepolia in the background; the user does not wait", "Later the same screen reads: already anchored on Sepolia"],
  "Demo step three. The second guardian signs. The threshold two of two is reached, and the system records the token locally and starts the mint on Sepolia in the background. The guardian does not wait for the blockchain. On the right, the same screen a little later: already anchored on Sepolia, with the token number. RO3 is complete.",
  [["F23", "Second approval: 2/2 reached, SBT minted in the background"], ["F25", "Revisited after the background job: already anchored on Sepolia"], 3.0]);
demo("DEMO 4: THE DOCTOR IS ALLOWED", "RO2 + RO4", "Five checks and a proof before any data is released",
  ["The doctor selects the consent and a scope inside the agreed modules.", "A Groth16 proof is generated and verified.", "The decision matrix shows VI, VA, VP, VT, VL all PASS, so ALLOW.", "Identity, authority, approvals, scope, time and jurisdiction are checked in one decision."],
  "Demo step four. The doctor asks for the patient's data. The proof is generated and verified, then the five checks run. Identity and authority, VI. Approvals and token, VA. Purpose and scope, VP. Time, VT. Jurisdiction, VL. All five pass, so the answer is ALLOW. This is RO2 and RO4 together in one decision.",
  [["F27", "Doctor subsystem, requester jurisdiction AU: all five checks PASS, ALLOW"]]);
demo("DEMO 5: ONLY THE AUTHORISED RECORDS", "RO4", "Data scope enforced: nothing outside the consent",
  ["Records are displayed per module: Observation, Medication, Condition, Procedure.", "Only the modules inside the consent scope are returned.", "A request for a module outside the scope is refused (attack test A4).", "The decision is written to the audit ledger with its matrix."],
  "Demo step five. After ALLOW, the authorised records are displayed per module. Only the modules inside the consent scope are returned. If the doctor asked for a module that was not agreed, the request would be refused; that case is covered by attack test A4. The decision and its matrix are written to the audit ledger.",
  [["F29", "Doctor subsystem after verification: access granted, records displayed per module"]]);
demo("DEMO 6: THE WRONG JURISDICTION", "RO4", "One failed check is enough to deny",
  ["Same doctor, same active consent, jurisdiction declared as SA instead of AU", "VL = FAIL, so ALLOW = FAIL", "The refusal names the failed check: Security Exception, failed checks: VL"],
  "Demo step six. The same doctor repeats the request, but declares the jurisdiction as SA. The consent was issued for AU. Everything else passes, but VL fails, and one failed check is enough: access is denied. The message tells the auditor exactly which check failed. This is the conjunctive rule of RO4 in action.",
  [["F31", "Requester jurisdiction SA: VL reports FAIL, ALLOW = FAIL"], ["F32", "The refused request names the failed check: VL"]]);
demo("DEMO 7: THE PATIENT REVOKES THE CONSENT", "RO5", "Revocation end to end, with an on-chain transaction",
  ["The patient revokes the consent", "The revoke transaction is sent to Sepolia and waits for block confirmation", "The consent becomes REVOKED, token #1"],
  "Demo step seven. The patient revokes the consent. On the left, the system is sending the revoke transaction to Sepolia and waiting for confirmation. On the right, the consent is now REVOKED, with its token number. This is the working part of RO5.",
  [["F33", "During revocation: waiting for block confirmation"], ["F34", "After revocation: the consent is REVOKED, token #1"], 3.9]);
demo("DEMO 8: AFTER REVOCATION, REFUSED", "RO5", "A revoked consent cannot be used",
  ["The same doctor repeats the request.", "VA reports FAIL: the consent is not active, current state REVOKED.", "Access is refused.", "Expired consents are refused the same way through VT."],
  "Demo step eight. The doctor tries again. Now VA fails, because the consent is not active: its state is REVOKED. Access is refused. An expired consent is refused in the same way, through the time check VT. So a consent that was valid yesterday does not stay usable forever.",
  [["F36", "Doctor subsystem after revocation: VA FAIL, state REVOKED"]]);
demo("DEMO 9: PUBLIC EVIDENCE ON SEPOLIA", "RO5 + RO6", "The mint and the revoke are public, verifiable transactions",
  ["Mint of the evaluated consent: block 11,771,243", "Revoke of token #1: block 11,771,307, decoded input revoke(uint256 tokenId)", "No medical data is on the chain, only the consent state"],
  "Demo step nine. Both the mint and the revoke are public transactions on Sepolia. On the left, the anchoring transaction of the evaluated consent in block 11,771,243. On the right, the revocation in block 11,771,307, with the decoded function revoke and token id 1. Anyone can verify them. No medical data is on the chain.",
  [["F26", "Anchoring transaction: status Success, block 11,771,243"], ["F37", "Revocation transaction: status Success, block 11,771,307"]]);
demo("DEMO 10: THE AUDITOR SEES EVERYTHING", "RO6", "Every event in order, and the chain agrees with the local records",
  ["The lifecycle of the consent: thirteen recorded events in order, from creation to revocation", "Aggregate indicators of the exported ledger: 60 events, 9 access requests, 5 on-chain anchors", "An independent tool re-checked Sepolia: all anchored transactions found in their recorded blocks"],
  "Demo step ten, the last one. The auditor can rebuild the full lifecycle of the consent: thirteen events in order, from creation to revocation, each with its decision matrix. The dashboard shows the exported ledger: 60 events, 9 access requests and 5 on-chain anchors. And a separate tool re-checked Sepolia and found every anchored transaction in its recorded block: all checks passed. This is the working part of RO6: evidence that can be audited.",
  [["F38", "Auditor subsystem: lifecycle of the evaluated consent, thirteen events in order"], ["F39", "Auditor dashboard: 60 events, 9 access requests, 5 on-chain anchors"]]);

// references
{
  const per = 12; const n = Math.ceil(D.refs.length / per);
  for (let k = 0; k < n; k++) {
    const part = D.refs.slice(k * per, (k + 1) * per);
    const s = slide("REFERENCES" + (n > 1 ? ` (${k + 1}/${n})` : ""), k === 0 ? "These are the references used in my report and in this presentation." : "", "References");
    panel(s, 0.5, 1.15, 11.8, 6.05, "references panel");
    s.addText(part.map((t, i) => ({ text: t, options: { breakLine: i < part.length - 1 } })),
      { x: 0.7, y: 1.25, w: 11.4, h: 5.85, fontSize: 10, color: INK, valign: "top", paraSpaceAfter: 4, isTextBox: true, objectName: "reference list" });
  }
}

// thanks
{
  pres.addSection({ title: "Thank You" }); sec = "Thank You";
  const s = pres.addSlide({ masterName: "COVER", sectionTitle: "Thank You" });
  s.addText("Thank You", { x: 2.5, y: 2.6, w: 8.3, h: 1.4, fontSize: 54, bold: true, color: WHITE, align: "center", valign: "middle", isTextBox: true, objectName: "thanks" });
  s.addText("Questions and discussion", { x: 2.5, y: 4.0, w: 8.3, h: 0.6, fontSize: 22, italic: true, color: CYAN, align: "center", isTextBox: true, objectName: "questions" });
  s.addNotes("Thank you for listening. I am happy to take your questions.\n\nLikely questions and short answers:\n1. Why blockchain if the data stay off-chain? It gives a shared, tamper-evident record of the consent state and the revocation. No medical data is on-chain.\n2. What is new? The consent object carries all the conditions; multi-party approval is a condition of every access; and the whole decision is tested against attacks.\n3. Why is RO6 only partial? The testing is done; the formal proofs are the next stage.\n4. Why Groth16? The doctor proves knowledge of the secret and the expiry behind the Poseidon commitment stored in the consent, and that the consent has not expired, without revealing them. It is the slowest part, about 1.4 seconds, and that is acceptable for a consent decision.\n5. Why did three attacks pass before the hardening? They passed only when the service functions were called directly, not through the interface. The hardening moved the checks into the service layer, so they are now refused on every path.");
}

(async () => {
  ALLSL.forEach(f => f());
  await pres.writeFile({ fileName: "/tmp/deck/Simple_Slides.pptx" });
  await applyTheme("/tmp/deck/Simple_Slides.pptx", THEME);
  console.log("done");
})();
