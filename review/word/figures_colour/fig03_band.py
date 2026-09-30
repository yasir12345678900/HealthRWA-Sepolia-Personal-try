"""Figure 3 in the original Mermaid banded design (actors / View / Controller / Model), laid out so labels are readable."""
import subprocess, os
D = os.path.dirname(os.path.abspath(__file__))
SPL = os.environ.get("SPL", "ortho")
W = 9.8   # mirror so the stakeholders read Auditors, Healthcare Professionals, Guardians, Patients as in the original
P = lambda x, y: f'pos="{(W - x)*72:.0f},{y*72:.0f}!"'
def bb(x1, y1, x2, y2): return f'bb="{(W - x2)*72:.0f},{y1*72:.0f},{(W - x1)*72:.0f},{y2*72:.0f}"'
st = [("sP", "Patients", 1.3), ("sG", "Guardians / Authorised Parties", 3.7), ("sH", "Healthcare Professionals", 6.1), ("sA", "Auditors", 8.7)]
vw = [("vP", "Patient Consent Interface", 1.3), ("vG", "Approval Interface", 3.7), ("vH", "Healthcare Access Interface", 6.1), ("vA", "Audit / Evidence Interface", 8.7)]
ct = [("c1", "Request Validation", 3.7, 8.35), ("c2", "DID / VC Verification", 4.3, 7.65), ("c3", "Authority Verification", 4.9, 6.95),
      ("c4", "Multi-Party Threshold Evaluation", 5.5, 6.25), ("c5", "Policy & Scope Evaluation", 6.1, 5.55),
      ("c6", "Authorisation Decision", 6.1, 4.85), ("c7", "Audit Event Generation", 8.7, 4.15)]
md = [("m7", "Identity &\\nDID Records", 0.7), ("m6", "Credential /\\nAuthority\\nEvidence", 2.05), ("m5", "Consent\\nObject", 3.4),
      ("m4", "Approval\\nEvidence", 4.7), ("m3", "Policy &\\nData Scope", 6.0), ("m1", "Lifecycle\\nState", 7.3), ("m2", "Authorisation\\nEvidence", 8.7)]
L = ['digraph G {', f'splines={SPL}; outputorder=edgesfirst;',
     'graph [fontname="Trebuchet MS", fontsize=13, fontcolor="#333333", bgcolor=white, dpi=300, pad=0.15];',
     'node [shape=box, style=filled, fillcolor="#ECECFF", color="#9370DB", fontcolor="#333333", fontname="Trebuchet MS", fontsize=12, penwidth=1.3, margin="0.12,0.06"];',
     'edge [color="#333333", arrowsize=0.7, penwidth=1.3];',
     f'subgraph cluster_v {{ label=""; style=filled; fillcolor="#FFFFDE"; color="#AAAA33"; {bb(0.05, 9.35, 9.75, 10.6)};']
L += [f'{n} [label="{l}", {P(x, 9.72)}];' for n, l, x in vw] + ['}']
L += [f'subgraph cluster_c {{ label=""; style=filled; fillcolor="#FFFFDE"; color="#AAAA33"; {bb(1.95, 3.7, 9.75, 9.05)};']
L += [f'{n} [label="{l}", {P(x, y)}];' for n, l, x, y in ct] + ['}']
L += [f'subgraph cluster_m {{ label=""; style=filled; fillcolor="#FFFFDE"; color="#AAAA33"; {bb(0.05, 1.55, 9.75, 3.05)};']
L += [f'{n} [label="{l}", {P(x, 2.55)}];' for n, l, x in md] + ['}']
L += [f'{n} [label="{l}", {P(x, 11.3)}];' for n, l, x in st]
L += [f'lv [label="VIEW LAYER\\nStakeholder Interaction", shape=plaintext, style="", fontsize=12.5, {P(7.4, 10.28)}];',
      f'lc [label="CONTROLLER LAYER\\nTrust & Authorisation Enforcement", shape=plaintext, style="", fontsize=12.5, {P(7.05, 7.6)}];',
      f'lm [label="MODEL LAYER\\nTrust & Governance State", shape=plaintext, style="", fontsize=12.5, {P(4.9, 1.78)}];']
L += [f'D [label="Protected\\nHealthcare Data", {P(0.85, 4.85)}];']
L += ["sP -> vP; sG -> vG; sH -> vH; sA -> vA; vP -> c1; vG -> c1; vH -> c1; c7 -> vA;",
      "c1 -> c2 -> c3 -> c4 -> c5 -> c6; c6 -> c7; c6 -> D;",
      "c2 -> m7 [dir=both]; c2 -> m6 [dir=both]; c3 -> m6 [dir=both]; c4 -> m5 [dir=both]; c4 -> m4 [dir=both]; c5 -> m3 [dir=both];",
      "c6 -> m1 [dir=both]; c6 -> m2 [dir=both]; c7 -> m2;", "}"]
open(f"{D}/fig03b.dot", "w").write("\n".join(L))
for fmt in ("png", "pdf", "svg"):
    subprocess.run(["neato", "-n2", f"-T{fmt}", f"{D}/fig03b.dot", "-o", f"{D}/fig03b.{fmt}"], check=True)
