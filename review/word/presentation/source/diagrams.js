// Native, editable PowerPoint versions of the report's flowcharts (same content as the report figures,
// re-laid out for a 16:9 slide so every label is 10-12 pt). Coordinates are inches relative to (ox, oy).
module.exports = function makeDiagrams(ctx) {
  const { T, runs } = ctx;
  const GOLD = { fill: "FFF2CC", line: "D6B656" };
  const EDGE = "A8842A";           // darker gold for edges: readable on white
  const INK = "1C2B31", MUTED = "5E6E73";

  function canvas(slide, ox, oy) {
    const N = {};
    const P = (x, y) => [ox + x, oy + y];
    function anchors(id, x, y, w, h) {
      const n = { x, y, w, h, cx: x + w / 2, cy: y + h / 2 };
      n.t = [n.cx, y]; n.b = [n.cx, y + h]; n.l = [x, n.cy]; n.r = [x + w, n.cy];
      N[id] = n; return n;
    }
    function node(id, x, y, w, h, label, o = {}) {
      const shape = o.shape || "rect";
      const fill = o.fill || GOLD.fill, line = o.line || GOLD.line;
      const [X, Y] = P(x, y);
      const kind = { rect: "rect", round: "roundRect", pill: "roundRect", diamond: "diamond", hex: "hexagon" }[shape];
      const so = { x: X, y: Y, w, h, fill: { color: fill }, line: { color: line, width: o.lw || 1.5 } };
      if (shape === "round") so.rectRadius = Math.min(0.12, h / 2);
      if (shape === "pill") so.rectRadius = h / 2;
      if (o.dash) so.line.dashType = o.dash;
      slide.addShape(kind, so);
      const ix = shape === "diamond" ? w * 0.17 : shape === "hex" ? w * 0.14 : 0.07;
      const iy = shape === "diamond" ? h * 0.13 : 0.03;
      const size = o.size || 11;
      let text;
      if (o.runs) text = o.runs;
      else if (Array.isArray(label)) { // [main, small] -> two paragraphs
        text = runs(label[0], { bold: o.bold !== false });
        text[text.length - 1].options.breakLine = true;
        text = text.concat(runs(label[1], { bold: false, italic: true, fontSize: size - 1.5, color: o.tagColor || MUTED }));
      } else text = runs(label, { bold: o.bold !== false });
      T(slide, text, { x: X + ix, y: Y + iy, w: w - 2 * ix, h: h - 2 * iy, fontSize: size, color: o.color || INK, align: o.align || "center", valign: "middle", lineSpacingMultiple: 0.95 });
      return anchors(id, x, y, w, h);
    }
    function band(x, y, w, h, o = {}) {
      const [X, Y] = P(x, y);
      const so = { x: X, y: Y, w, h, fill: { color: o.fill || "FFFFDE" }, line: { color: o.line || "AAAA33", width: 1 }, rectRadius: 0.08 };
      if (o.dash) so.line.dashType = o.dash;
      slide.addShape("roundRect", so);
    }
    function lab(x, y, w, h, text, o = {}) {
      const [X, Y] = P(x, y);
      T(slide, runs(text, { bold: !!o.bold, italic: !!o.italic }), { x: X, y: Y, w, h, fontSize: o.size || 10, color: o.color || MUTED, align: o.align || "left", valign: o.valign || "middle", rotate: o.rotate });
    }
    function seg(a, b, o, endArrow, beginArrow) {
      const [x1, y1] = P(a[0], a[1]), [x2, y2] = P(b[0], b[1]);
      const line = { color: o.color || EDGE, width: o.width || 1.5 };
      if (o.dash) line.dashType = o.dash;
      if (endArrow) line.endArrowType = "triangle";
      if (beginArrow) line.beginArrowType = "triangle";
      slide.addShape("line", { x: Math.min(x1, x2), y: Math.min(y1, y2), w: Math.abs(x2 - x1), h: Math.abs(y2 - y1), flipH: x2 < x1, flipV: y2 < y1, line });
    }
    // polyline through points (relative); arrow on the last segment (and optionally the first)
    function path(pts, o = {}) {
      for (let i = 0; i < pts.length - 1; i++) seg(pts[i], pts[i + 1], o, o.arrow !== false && i === pts.length - 2, !!o.both && i === 0);
    }
    const down = (a, b, o) => path([a.b, [a.cx, b.y]].map((p, i) => i ? [a.cx, b.y] : [a.cx, a.y + a.h]), o);
    const right = (a, b, o) => path([a.r, [b.x, a.cy]], o);
    // decision -> next step below-left: diamond bottom, down to ym, across, down into the step
    function yesDown(q, s, label = "Yes", o = {}) {
      const ym = (q.y + q.h + s.y) / 2;
      const tx = o.tx != null ? o.tx : s.cx;
      path([q.b, [q.cx, ym], [tx, ym], [tx, s.y]], o);
      if (label) lab(q.cx + 0.06, q.y + q.h - 0.02, 0.5, 0.18, label, { size: 9.5 });
    }
    function noRight(q, box, label = "No") {
      path([q.r, [box.x, q.cy]]);
      if (label) lab(q.x + q.w + 0.04, q.cy - 0.2, 0.5, 0.18, label, { size: 9.5 });
    }
    function noBus(q, box, bx, label = "No") {
      path([q.r, [bx, q.cy], [bx, box.y]]);
      if (label) lab(q.x + q.w + 0.04, q.cy - 0.2, 0.5, 0.18, label, { size: 9.5 });
    }
    return { N, node, band, lab, path, seg, down, right, yesDown, noRight, noBus };
  }

  // ------------------------------------------------------------------ lane geometry for the RO workflows
  const L = { c1x: 0.1, c1w: 2.8, qcx: 4.3, qw: 2.1, c3x: 5.65, c3w: 1.5 };
  L.c1cx = L.c1x + L.c1w / 2;
  function step(d, id, cy, label, h = 0.42, o = {}) { return d.node(id, o.x != null ? o.x : L.c1x, cy - h / 2, o.w || L.c1w, h, label, o); }
  function dia(d, id, cy, label, h = 0.5, o = {}) { const w = o.w || L.qw; return d.node(id, (o.cx || L.qcx) - w / 2, cy - h / 2, w, h, label, { shape: "diamond", size: o.size || 10.5, ...o }); }
  function side(d, id, cy, label, h = 0.42, o = {}) { return d.node(id, L.c3x, cy - h / 2, L.c3w, h, label, { size: 10.5, ...o }); }

  const F = {};

  // Figure 2.1: SLR search string, one row per concept group (terms joined by OR, groups joined by AND)
  F.f2_1 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const rows = [
      ["Multi-Party Trust Management", ["distributed trust", "multiparty trust", "decentralisation"], "E8F0FB", "5B8FD0", "22508A"],
      ["Healthcare Context", ["healthcare", "EHR", "health data", "medical data"], "E8F5E4", "6AAB50", "2E6B2A"],
      ["Consent Management", ["consent", "patient consent", "dynamic consent", "consent management"], "FFF2CC", "D3A128", "7A5A00"],
      ["Supporting Requirements", ["access control", "authentication", "DID", "verifiable credential", "privacy", "auditability", "interoperability"], "FDE3D8", "E0875A", "9A3B12"],
    ];
    const tx = 0.25, tw = 2.1, mx = 2.6, mw = 4.55, rh = 0.62, gap = 0.32, y0 = 0.62, tcx = tx + tw / 2;
    const q = d.node("q", tcx - 1.05, 0.0, 2.1, 0.42, "SLR Search Query", { shape: "pill", fill: "1B3A5C", line: "1B3A5C", color: "FFFFFF", size: 12 });
    let prev = q;
    rows.forEach((r, i) => {
      const y = y0 + i * (rh + gap);
      const tag = d.node("t" + i, tx, y, tw, rh, r[0], { fill: r[2], line: r[3], color: r[4], size: 12.5 });
      const rr = [];
      r[1].forEach((t, k) => {
        if (k) rr.push({ text: "  OR  ", options: { bold: true, color: r[4], fontSize: 10.5 } });
        rr.push({ text: t.replace(/ /g, "\u00a0"), options: { color: INK } });
      });
      d.node("m" + i, mx, y, mw, rh, "", { fill: "FFFFFF", line: r[3], size: 12, bold: false, align: "left", runs: rr });
      d.path([tag.r, [mx, tag.cy]], { arrow: false, color: r[3] });
      if (i === 0) d.path([q.b, [tcx, tag.y]]);
      else {
        const ay = y - gap / 2;
        d.path([[tcx, prev.y + prev.h], [tcx, ay - 0.13]], { arrow: false });
        d.node("a" + i, tcx - 0.36, ay - 0.13, 0.72, 0.26, "AND", { shape: "hex", fill: "F0F0F0", line: "999999", color: "333333", size: 10 });
        d.path([[tcx, ay + 0.13], [tcx, y]]);
      }
      prev = tag;
    });
    const ry = y0 + 4 * rh + 3 * gap + 0.24;
    const res = d.node("res", tcx - 1.15, ry, 2.3, 0.42, "Final Search Results", { shape: "pill", fill: "4E7F2E", line: "4E7F2E", color: "FFFFFF", size: 12 });
    d.path([[tcx, prev.y + prev.h], [tcx, res.y]]);
    d.lab(mx, 0.0, mw, 0.42, "Terms within a group are joined by OR; the four groups are joined by AND.", { italic: true, size: 10.5, color: MUTED });
  };

  // Figure 5.1: layered MVC architecture (full width)
  F.f5_1 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const LAV = { fill: "ECECFF", line: "9370DB", color: "333333", size: 10.5 };
    const cx0 = 0.5, sp = 1.47, bw = 1.25, X = i => cx0 + i * sp;
    // bands
    d.band(0.38, 0.52, X(6) + bw + 0.08 - 0.38, 0.8);
    d.band(0.38, 1.52, X(6) + bw + 0.08 - 0.38, 0.98);
    d.band(0.38, 2.64, X(7) + bw + 0.08 - 0.38, 0.94);
    d.lab(0.17 - 0.4, 0.92 - 0.17, 0.8, 0.34, "VIEW", { bold: true, size: 9.5, color: "0E3B43", align: "center", rotate: 270 });
    d.lab(-0.3, 1.52 + 0.49 - 0.17, 0.95, 0.34, "CONTROLLER", { bold: true, size: 9.5, color: "0E3B43", align: "center", rotate: 270 });
    d.lab(-0.13, 2.64 + 0.47 - 0.17, 0.6, 0.34, "MODEL", { bold: true, size: 9.5, color: "0E3B43", align: "center", rotate: 270 });
    // stakeholders and interfaces
    const S = [[0, "Patients", "Patient Consent Interface"], [1, "Guardians / Authorised Parties", "Approval Interface"], [2, "Healthcare Professionals", "Healthcare Access Interface"], [6, "Auditors", "Audit / Evidence Interface"]];
    const v = {};
    S.forEach(([c, s, iface]) => {
      const sn = d.node("s" + c, X(c), 0.0, bw, 0.42, s, { ...LAV, size: 10, fill: "FFFFFF" });
      v[c] = d.node("v" + c, X(c), 0.62, bw, 0.6, iface, LAV);
      d.path([sn.b, [sn.cx, v[c].y]]);
    });
    // controller
    const CT = ["Request Validation", "DID / VC Verification", "Authority Verification", "Multi-Party Threshold Evaluation", "Policy & Scope Evaluation", "Authorisation Decision", "Audit Event Generation"];
    const c = CT.map((t, i) => d.node("c" + i, X(i), 1.6, bw, 0.82, t, LAV));
    const D = d.node("D", X(7), 1.6, bw, 0.82, "Protected Healthcare Data", { ...LAV, fill: "FFE6CC", line: "D79B00" });
    for (let i = 0; i < 6; i++) d.path([c[i].r, [c[i + 1].x, c[i].cy]]);
    // interfaces -> request validation; audit event generation -> audit interface
    d.path([[X(0) + 0.35, v[0].y + v[0].h], [X(0) + 0.35, c[0].y]]);
    d.path([[v[1].cx, v[1].y + v[1].h], [v[1].cx, 1.36], [X(0) + 0.7, 1.36], [X(0) + 0.7, c[0].y]]);
    d.path([[v[2].cx, v[2].y + v[2].h], [v[2].cx, 1.44], [X(0) + 1.02, 1.44], [X(0) + 1.02, c[0].y]]);
    d.path([c[6].t, [c[6].cx, v[6].y + v[6].h]]);
    // decision -> protected data (over the top of the audit function)
    d.path([[c[5].cx, c[5].y], [c[5].cx, 1.47], [D.cx, 1.47], [D.cx, D.y]]);
    // model
    const M = [[1, "Identity & DID Records"], [2, "Credential / Authority Evidence"], [3, "Consent Object"], [4, "Approval Evidence"], [5, "Policy & Data Scope"], [6, "Lifecycle State"], [7, "Authorisation Evidence"]];
    const m = {};
    M.forEach(([col, t]) => { m[col] = d.node("m" + col, X(col), 2.75, bw, 0.72, t, LAV); });
    const link = (cn, cxo, mn, mxo, both = true) => d.path([[cn.x + cxo, cn.y + cn.h], [mn.x + mxo, mn.y]], { both });
    link(c[1], 0.35, m[1], 0.35);         // DID/VC <-> identity records
    link(c[1], 0.95, m[2], 0.3);          // DID/VC <-> credential evidence
    link(c[2], 0.625, m[2], 0.8);         // authority <-> credential evidence
    link(c[3], 0.35, m[3], 0.35);         // threshold <-> consent object
    link(c[3], 0.95, m[4], 0.5);          // threshold <-> approval evidence
    link(c[4], 0.625, m[5], 0.4);         // policy <-> policy & scope
    link(c[5], 0.35, m[6], 0.4);          // decision <-> lifecycle state
    link(c[5], 0.95, m[7], 0.35);         // decision <-> authorisation evidence
    link(c[6], 0.625, m[7], 0.9, false);  // audit generation -> authorisation evidence
  };

  // Figure 5.3: trust predicate evaluation
  F.f5_3 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const mdl = d.node("md", 0.3, 0.0, 6.6, 0.84, ["MODEL — trust and governance state", "identity and DID records · credentials and authority evidence · consent object · approvals · policy and data scope · validity period · lifecycle state"], { fill: "ECECFF", line: "9370DB", size: 11.5, tagColor: "333333" });
    d.band(0.1, 1.14, 7.0, 2.2);
    d.lab(0.25, 1.17, 4.5, 0.26, "CONTROLLER — trust predicate evaluation", { bold: true, size: 10.5, color: "333333" });
    d.path([mdl.b, [mdl.cx, 1.14]], { dash: "dash" });
    d.lab(mdl.cx + 0.08, 0.86, 1.0, 0.26, "evidence", { italic: true, size: 9.5 });
    const P = ["V_I(u)", "V_A(C)", "V_P(C, R)", "V_T(C, t)", "V_L(C)"];
    const bx = P.map((t, i) => d.node("p" + i, 0.35 + i * 1.37, 1.55, 1.05, 0.5, t, { shape: "round", size: 12.5 }));
    for (let i = 0; i < 4; i++) d.right(bx[i], bx[i + 1]);
    const q = d.node("q", 2.4, 2.36, 2.4, 0.72, "All Required Predicates = TRUE?", { shape: "diamond", fill: "F8CECC", line: "B85450", size: 10.5 });
    d.path([bx[4].b, [bx[4].cx, q.cy], [q.x + q.w, q.cy]]);
    const al = d.node("al", 0.75, 3.62, 1.3, 0.42, "ALLOW", { shape: "round", fill: "FFE6CC", line: "D79B00", size: 12 });
    const de = d.node("de", 5.15, 3.62, 1.3, 0.42, "DENY", { shape: "round", fill: "FFE6CC", line: "D79B00", size: 12 });
    d.path([q.l, [al.cx, q.cy], [al.cx, al.y]]); d.lab(1.45, q.cy - 0.22, 0.5, 0.2, "YES", { size: 9.5, bold: true });
    d.path([q.b, [q.cx, 3.46], [de.cx, 3.46], [de.cx, de.y]]); d.lab(q.cx + 0.06, q.y + q.h + 0.02, 0.4, 0.18, "NO", { size: 9.5, bold: true });
    const ev = d.node("ev", 2.35, 4.22, 2.5, 0.42, "Generate Authorisation Evidence", { fill: "FFE6CC", line: "D79B00", size: 11 });
    d.path([al.b, [al.cx, ev.cy], [ev.x, ev.cy]]);
    d.path([de.b, [de.cx, ev.cy], [ev.x + ev.w, ev.cy]]);
  };

  // Figure 5.4: end-to-end workflow
  F.f5_4 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const A = d.node("A", 0.1, 0.03, 1.55, 0.5, "Patient Creates Consent", { shape: "round", size: 10.5 });
    const B = d.node("B", 1.85, 0.03, 3.1, 0.5, "Consent Specification: Purpose · Data Scope · Conditions", { size: 10.5 });
    d.right(A, B);
    const QO = { w: 2.3 };
    const C = step(d, "C", 0.95, "DID / VC Verification: Identity & Authority Validation", 0.44, { size: 10.5 });
    const Q0 = dia(d, "Q0", 0.95, "Identity and\nAuthority Valid?", 0.42, QO);
    d.path([B.b, [B.cx, 0.62], [C.cx, 0.62], [C.cx, C.y]]);
    d.right(C, Q0);
    const Dn = step(d, "Dn", 1.55, "Identify Authorisation Participants", 0.4);
    d.yesDown(Q0, Dn);
    const E = step(d, "E", 2.15, "Multi-Party Approval: Collect Independent Approvals", 0.44, { size: 10.5 });
    d.down(Dn, E);
    const Q1 = dia(d, "Q1", 2.15, "Threshold Satisfied?", 0.42, QO); d.right(E, Q1);
    const G = step(d, "G", 2.75, "Policy Evaluation: Purpose & Data-Scope Validation", 0.44, { size: 10.5 });
    d.yesDown(Q1, G);
    const Q2 = dia(d, "Q2", 2.75, "Policy Compliant?", 0.42, QO); d.right(G, Q2);
    const I = step(d, "I", 3.35, "Authorisation Decision: V_I ∧ V_A ∧ V_P (Eq. 6)", 0.44, { size: 10.5 });
    d.yesDown(Q2, I);
    const Q3 = dia(d, "Q3", 3.35, "Decision = ALLOW?", 0.42, QO); d.right(I, Q3);
    const J = d.node("J", 0.1, 3.72, 1.3, 0.5, "ALLOW: Grant Data Access", { shape: "round", size: 10.5 });
    const K = d.node("K", 1.55, 3.72, 1.35, 0.5, "Access Healthcare Data", { size: 10.5 });
    d.yesDown(Q3, J, "Allow");
    d.right(J, K);
    const M = step(d, "M", 4.5, "Record Audit Evidence", 0.4);
    d.path([K.b, [K.cx, M.y]]);
    const Ld = d.node("L", L.c3x, 3.72, L.c3w, 0.5, "DENY: Reject Access", { shape: "round", size: 10.5 });
    [[Q0, 7.05], [Q1, 6.75], [Q2, 6.45], [Q3, 6.15]].forEach(([q, bx], i) => d.noBus(q, Ld, bx, i === 3 ? "Deny" : "No"));
    d.path([Ld.b, [Ld.cx, M.cy], [M.x + M.w, M.cy]]);
  };

  // Figure 6.1: RO1 consent creation (two columns)
  F.f6_1 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const ax = 0.1, aw = 2.5, bx = 2.95, bw = 2.5, rows = [0.28, 0.98, 1.68, 2.38, 3.08, 3.78, 4.48];
    const colA = ["Patient Creates Consent", "Collect Patient DID", "Specify Authorised Doctor", "Specify Guardian DIDs", "Specify Purpose and Data Scope", "Specify Consent Validity"];
    const a = colA.map((t, i) => d.node("a" + i, ax, rows[i] - 0.2, aw, 0.4, t, { shape: i === 0 ? "round" : "rect" }));
    for (let i = 0; i < 5; i++) d.down(a[i], a[i + 1]);
    const q = d.node("q", bx + bw / 2 - 1.1, rows[0] - 0.3, 2.2, 0.6, "Consent Specification Valid?", { shape: "diamond", size: 10.5 });
    d.path([a[5].r, [2.78, a[5].cy], [2.78, q.cy], [q.x, q.cy]]);
    const r = d.node("r", 5.75, rows[0] - 0.24, 1.4, 0.48, "Reject Consent Request", { size: 10.5 });
    d.noRight(q, r);
    const colB = ["Define Authorisation Requirement", "Generate Consent Identifier", "Create Trust-Aware Consent Object C\u00a0=\u00a0(I,\u00a0A,\u00a0P,\u00a0E)", "Persist Consent Record", "Record Consent Creation Audit", "Return Consent Object C"];
    const b = colB.map((t, i) => d.node("b" + i, bx, rows[i + 1] - (i === 2 ? 0.26 : 0.2), bw, i === 2 ? 0.52 : 0.4, t, { shape: i === 5 ? "round" : "rect", size: i === 2 ? 10.5 : 11 }));
    d.path([q.b, [q.cx, b[0].y]]); d.lab(q.cx + 0.06, q.y + q.h - 0.02, 0.5, 0.18, "Yes", { size: 9.5 });
    for (let i = 0; i < 5; i++) d.down(b[i], b[i + 1]);
  };

  // Figure 6.2: RO2 identity and authority verification
  F.f6_2 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const r = [0.3, 1.08, 1.86, 2.64, 3.42, 4.2];
    const A = step(d, "A", r[0], "Participant Requests Participation", 0.44, { shape: "round" });
    const B = step(d, "B", r[1], "Resolve Participant DID"); d.down(A, B);
    const Q1 = dia(d, "Q1", r[1], "DID Valid?"); d.right(B, Q1);
    const C = step(d, "C", r[2], "Retrieve Verifiable Credential"); d.yesDown(Q1, C);
    const Q2 = dia(d, "Q2", r[2], "VC Retrieved and Valid?"); d.right(C, Q2);
    const Dd = step(d, "D", r[3], "Extract Role and Authority Claims"); d.yesDown(Q2, Dd);
    const Q3 = dia(d, "Q3", r[3], "Authority Matches Consent?"); d.right(Dd, Q3);
    const E = step(d, "E", r[4], "Record Verification Evidence"); d.yesDown(Q3, E);
    const Fz = step(d, "F", r[5], "Return Verified Identity and Authority", 0.46, { shape: "round" }); d.down(E, Fz);
    const R = d.node("R", L.c3x, 3.2, L.c3w, 0.46, "Reject Participant", { size: 10.5 });
    d.noBus(Q1, R, 7.0); d.noBus(Q2, R, 6.6); d.noBus(Q3, R, 6.2);
  };

  // Figure 6.3: RO3 threshold-based multi-party authorisation
  F.f6_3 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const top = ["Consent Requires Multi-Party Approval", "Identify Required Participants", "Define Authorisation Threshold N", "Participant Submits Approval"];
    const t = top.map((s, i) => d.node("t" + i, i * 1.85, 0.0, 1.65, 0.5, i === 0 ? "Consent Requires\nMulti-Party Approval" : s, { shape: i === 0 ? "round" : "rect", size: 10.5 }));
    for (let i = 0; i < 3; i++) d.right(t[i], t[i + 1]);
    const r = [0, 0.9, 1.5, 2.1, 2.7, 3.3, 3.9, 4.5];
    const Dd = step(d, "D", r[1], "Verify DID and VC", 0.4);
    d.path([t[3].b, [t[3].cx, 0.6], [Dd.cx, 0.6], [Dd.cx, Dd.y]]);
    const o = { size: 10 }, qh = 0.42;
    const Q1 = dia(d, "Q1", r[1], "Participant Verified?", qh, o); d.right(Dd, Q1);
    const R1 = side(d, "R1", r[1], "Reject Invalid Approval", 0.44); d.noRight(Q1, R1);
    const E = step(d, "E", r[2], "Check Membership of Required Set G", 0.4, { size: 10.5 }); d.yesDown(Q1, E);
    const Q2 = dia(d, "Q2", r[2], "Participant in\nRequired Set G?", qh, o); d.right(E, Q2);
    const R2 = side(d, "R2", r[2], "Reject Unauthorised Approval", 0.44); d.noRight(Q2, R2);
    const Fz = step(d, "F", r[3], "Check for Prior Approval", 0.4); d.yesDown(Q2, Fz);
    const Q3 = dia(d, "Q3", r[3], "Already Approved?", qh, o); d.right(Fz, Q3);
    const R3 = side(d, "R3", r[3], "Reject Duplicate Approval", 0.44); d.noRight(Q3, R3, "Yes");
    const G = step(d, "G", r[4], "Record Valid Approval", 0.4); d.yesDown(Q3, G, "No");
    const H = step(d, "H", r[5], "Update Approval Count", 0.4); d.down(G, H);
    const Q4 = dia(d, "Q4", r[5], "Threshold Satisfied?", qh, o); d.right(H, Q4);
    const Pn = side(d, "P", r[5], "Consent Remains Pending", 0.44); d.noRight(Q4, Pn);
    const P2 = side(d, "P2", r[6], "Record Threshold-Pending Event", 0.44); d.down(Pn, P2);
    const I = step(d, "I", r[6], "Activate Authorisation", 0.4); d.yesDown(Q4, I);
    const J = step(d, "J", r[7], "Generate Activation or Token Evidence", 0.4, { size: 10.5 }); d.down(I, J);
    const K = d.node("K", 3.25, r[7] - 0.2, 2.2, 0.4, "Record Threshold-Satisfied Event", { size: 10.5 }); d.right(J, K);
  };

  // Figure 6.4: RO4 policy- and context-aware access
  F.f6_4 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const A = d.node("A", 0.1, 0.02, 1.3, 0.52, "Doctor Requests Patient Data", { shape: "round", size: 10.5 });
    const B = d.node("B", 1.55, 0.02, 1.35, 0.52, "Retrieve Consent Object", { size: 10.5 });
    d.right(A, B);
    const rows = [0.97, 1.57, 2.17, 2.77, 3.37];
    const spec = [["Verify Requesting Identity and Authority", "Identity and Authority Valid?"], ["Evaluate Consent State", "Consent Active?"], ["Verify Multi-Party Authorisation", "Threshold Satisfied?"], ["Evaluate Requested Purpose", "Purpose Valid?"], ["Evaluate Requested Data Scope", "Scope Within Consent?"]];
    const S = [], Q = [];
    spec.forEach(([s, q], i) => {
      S[i] = step(d, "S" + i, rows[i], s, i === 0 ? 0.44 : 0.4, { size: i === 0 ? 10.5 : 11 });
      Q[i] = dia(d, "Q" + i, rows[i], i === 0 ? "Identity and\nAuthority Valid?" : q, 0.42, { w: 2.3 });
      d.right(S[i], Q[i]);
      if (i > 0) d.yesDown(Q[i - 1], S[i]);
    });
    d.path([B.b, [B.cx, 0.63], [S[0].cx, 0.63], [S[0].cx, S[0].y]]);
    const H = step(d, "H", 3.97, "Generate or Verify Access Evidence", 0.4); d.yesDown(Q[4], H);
    const I = d.node("I", 0.1, 4.3, 1.3, 0.4, "Grant Data Access", { size: 10.5 });
    const J = d.node("J", 1.55, 4.3, 1.35, 0.4, "Record Granted Access", { shape: "round", size: 10.5 });
    d.path([H.b, [H.cx, 4.18], [I.cx, 4.18], [I.cx, I.y]]); d.right(I, J);
    const X = d.node("X", L.c3x, 3.77, L.c3w, 0.4, "Deny Access", { size: 10.5 });
    const Y = d.node("Y", L.c3x, 4.3, L.c3w, 0.4, "Record Denied Access", { shape: "round", size: 10.5 });
    d.down(X, Y);
    [7.05, 6.8, 6.55, 6.3, 6.05].forEach((bx, i) => d.noBus(Q[i], X, bx));
  };

  // Figure 6.5: RO5 temporal and lifecycle validation
  F.f6_5 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const A = d.node("A", 0.1, 0.04, 1.3, 0.52, "Access Request", { shape: "round", size: 10.5 });
    const B = d.node("B", 1.55, 0.04, 1.35, 0.52, "Retrieve Consent Validity Interval", { size: 10.5 });
    d.right(A, B);
    const rows = [1.02, 1.7, 2.38, 3.06];
    const spec = [["Check Consent Validity Interval", "Within Valid Time?", "Yes", "No"], ["Retrieve and Check Lifecycle State", "State Permits Operation?", "Yes", "No"], ["Evaluate Revocation Status", "Revoked?", "No", "Yes"], ["Validate Requested Transition", "Transition Permitted?", "Yes", "No"]];
    const S = [], Q = [];
    spec.forEach(([s, q], i) => {
      S[i] = step(d, "S" + i, rows[i], s, 0.4, { size: 10.5 });
      Q[i] = dia(d, "Q" + i, rows[i], q, 0.52);
      d.right(S[i], Q[i]);
      if (i > 0) d.yesDown(Q[i - 1], S[i], spec[i - 1][2]);
    });
    d.path([B.b, [B.cx, 0.66], [S[0].cx, 0.66], [S[0].cx, S[0].y]]);
    const H = step(d, "H", 3.74, "Record Temporal and Lifecycle Evidence", 0.4, { size: 10.5 }); d.yesDown(Q[3], H);
    const G = step(d, "G", 4.42, "Continue Authorisation Evaluation", 0.44, { shape: "round" }); d.down(H, G);
    const X = d.node("X", L.c3x, 3.5, L.c3w, 0.48, "Record Lifecycle-Based Denial", { size: 10.5 });
    const Y = d.node("Y", L.c3x, 4.2, L.c3w, 0.44, "Deny Access", { shape: "round", size: 10.5 });
    d.down(X, Y);
    [7.05, 6.75, 6.45, 6.15].forEach((bx, i) => d.noBus(Q[i], X, bx, spec[i][3]));
  };

  // Figure 6.6: RO6 formal assurance and empirical validation
  F.f6_6 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const A = d.node("A", 0.0, 0.02, 2.25, 0.56, "Define Security and Authorisation Properties", { shape: "round", size: 10.5 });
    const B = d.node("B", 2.45, 0.02, 2.3, 0.56, "Define Valid, Negative and Adversarial Scenarios", { size: 10.5 });
    const C = d.node("C", 4.95, 0.02, 2.25, 0.56, "Construct Validation Scenario Set", { size: 10.5 });
    d.right(A, B); d.right(B, C);
    const E = d.node("E", 4.875, 0.8, 2.4, 0.52, "Execute Negative and Adversarial Scenarios", { size: 10.5 });
    const Dd = d.node("D", 1.2, 0.84, 2.4, 0.44, "Execute Valid Consent Workflow", { size: 10.5 });
    d.path([C.b, [C.cx, E.y]]);
    d.path([[C.cx, 0.69], [Dd.cx, 0.69], [Dd.cx, Dd.y]]);
    const Fz = d.node("F", 2.2, 1.56, 2.8, 0.4, "Collect Decision and Audit Evidence", { size: 10.5 });
    d.path([Dd.b, [Dd.cx, 1.43], [Fz.cx - 0.35, 1.43], [Fz.cx - 0.35, Fz.y]]);
    d.path([E.b, [E.cx, 1.43], [Fz.cx + 0.35, 1.43], [Fz.cx + 0.35, Fz.y]]);
    const G = d.node("G", 2.1, 2.2, 3.0, 0.4, "Compare Observed and Expected Decisions", { size: 10.5 }); d.down(Fz, G);
    const H = d.node("H", 1.5, 2.82, 4.2, 0.54, "Evaluate Security Properties (soundness, denial, threshold, policy scope, audit consistency)", { size: 10.5 }); d.down(G, H);
    const Q = d.node("Q", 2.55, 3.56, 2.1, 0.52, "Properties Satisfied?", { shape: "diamond", size: 10.5 }); d.down(H, Q);
    const K = d.node("K", 5.35, 3.6, 1.8, 0.44, "Analyse Failures and Limitations", { size: 10.5 });
    d.noRight(Q, K);
    const J = d.node("J", 2.1, 4.26, 3.0, 0.44, "Document Evidence and Limitations", { shape: "round", size: 10.5 });
    d.path([Q.b, [Q.cx, J.y]]); d.lab(Q.cx + 0.06, Q.y + Q.h - 0.02, 0.5, 0.18, "Yes", { size: 9.5 });
    d.path([K.b, [K.cx, J.cy], [J.x + J.w, J.cy]]);
  };

  // Figure 7.6: HALAH prototype workflow (full width, three lanes)
  F.f7_6 = (slide, ox, oy) => {
    const d = canvas(slide, ox, oy);
    const lanes = [[0.0, 3.6, "Patient view (Section 7.2)"], [3.8, 4.5, "Guardian view (Section 7.3)"], [8.5, 3.63, "Doctor view (Section 7.4)"]];
    lanes.forEach(([x, w, t]) => { d.band(x, 0.3, w, 2.98, { dash: "dash" }); d.lab(x + 0.05, 0.02, w - 0.1, 0.26, t, { bold: true, size: 10.5, color: "333333" }); });
    const tag = s => ["", s];
    // patient
    const p1 = d.node("p1", 0.3, 0.45, 2.6, 0.8, "Create consent: patient DID, doctor DID, EMR-module scope, guardian DIDs, start / expiry", { shape: "round", size: 10.5 });
    const pv = d.node("pv", 0.45, 1.44, 2.3, 0.6, "Expiry later than start?", { shape: "diamond", size: 10.5 });
    const pr = d.node("pr", 2.95, 1.53, 0.55, 0.42, "Reject input", { size: 9.5 });
    const p2 = d.node("p2", 0.3, 2.3, 2.6, 0.66, ["Consent stored; state = PENDING_SIGNATURE", "audit: CREATE_CONSENT"], { size: 10.5 });
    d.down(p1, pv); d.noRight(pv, pr);
    d.path([pv.b, [pv.cx, p2.y]]); d.lab(pv.cx + 0.06, pv.y + pv.h - 0.02, 0.5, 0.18, "Yes", { size: 9.5 });
    // guardian
    const g1 = d.node("g1", 5.0, 0.42, 2.5, 0.58, ["Guardian signs EIP-712 approval", "audit: SIGN_CONSENT"], { size: 10.5 });
    const gv = d.node("gv", 4.95, 1.12, 2.6, 0.64, "Signature valid and not a duplicate?", { shape: "diamond", size: 10 });
    const gr = d.node("gr", 3.95, 1.23, 0.75, 0.42, "Reject approval", { size: 9.5 });
    const gt = d.node("gt", 5.1, 1.92, 2.3, 0.56, "Approvals = N = |G| ?", { shape: "diamond", size: 10.5 });
    const g2 = d.node("g2", 4.85, 2.64, 2.8, 0.62, ["Mint consent SBT (local ID + Sepolia anchor); consent becomes ACTIVE", "audit: MINT_SBT, ONCHAIN_MINT"], { size: 10 });
    d.path([p2.r, [3.7, p2.cy], [3.7, g1.cy], [g1.x, g1.cy]]);
    d.down(g1, gv);
    d.path([gv.l, [gr.x + gr.w, gv.cy]]); d.lab(gr.x + gr.w + 0.04, gv.cy - 0.22, 0.24, 0.18, "No", { size: 9.5 });
    d.path([gv.b, [gv.cx, gt.y]]); d.lab(gv.cx + 0.06, gv.y + gv.h - 0.02, 0.5, 0.18, "Yes", { size: 9.5 });
    d.path([gt.b, [gt.cx, g2.y]]); d.lab(gt.cx + 0.06, gt.y + gt.h - 0.02, 0.5, 0.18, "Yes", { size: 9.5 });
    d.path([gt.r, [7.7, gt.cy], [7.7, g1.cy], [g1.x + g1.w, g1.cy]], { dash: "dash" });
    d.lab(7.86 - 0.9, 1.5 - 0.11, 1.8, 0.22, "No: wait for next guardian", { italic: true, size: 9.5, align: "center", rotate: 270 });
    // doctor
    const d1 = d.node("d1", 8.75, 0.42, 3.0, 0.56, "Doctor enters consent ID and selects EMR modules", { size: 10.5 });
    const dv = d.node("dv", 8.6, 1.14, 2.75, 0.96, ["State = ACTIVE, access proof valid and S_R ⊆ S_C ?", "audit: STATE_CHECK"], { shape: "diamond", size: 10 });
    const dg = d.node("dg", 8.65, 2.42, 2.05, 0.7, ["ACCESS GRANTED: release Synthea modules", "audit: DATA_ACCESS"], { shape: "round", size: 10 });
    const dd = d.node("dd", 10.85, 2.42, 1.2, 0.7, ["ACCESS DENIED", "audit: DATA_ACCESS"], { shape: "round", size: 10 });
    d.path([g2.r, [8.4, g2.cy], [8.4, d1.cy], [d1.x, d1.cy]]);
    d.down(d1, dv);
    d.path([dv.b, [dv.cx, 2.26], [dg.cx, 2.26], [dg.cx, dg.y]]); d.lab(dv.cx + 0.06, dv.y + dv.h - 0.02, 0.5, 0.18, "Yes", { size: 9.5 });
    d.path([dv.r, [dd.cx, dv.cy], [dd.cx, dd.y]]); d.lab(dv.x + dv.w + 0.02, dv.cy - 0.22, 0.4, 0.18, "No", { size: 9.5 });
    // audit log
    const au = d.node("au", 0.4, 3.42, 11.4, 0.48, "Audit log (Section 7.5): CREATE_CONSENT · SIGN_CONSENT · MINT_SBT · ONCHAIN_MINT · STATE_CHECK · DATA_ACCESS (GRANTED / DENIED)", { shape: "round", fill: "ECECFF", line: "9370DB", size: 11 });
    [p2, g2, dg, dd].forEach(n => d.path([n.b, [n.cx, au.y]], { dash: "sysDot" }));
  };

  return F;
};
