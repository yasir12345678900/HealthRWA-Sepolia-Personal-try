import subprocess, os
OUTC=os.path.dirname(os.path.abspath(__file__))
HEADC='''
graph [fontname="Trebuchet MS", fontsize=13, bgcolor=white, dpi=300, pad=0.15];
node  [shape=box, style=filled, fillcolor="#ECECFF", color="#9370DB", fontcolor="#333333", fontname="Trebuchet MS", fontsize=12, penwidth=1.3, margin="0.16,0.07"];
edge  [color="#333333", fontname="Trebuchet MS", arrowsize=0.75, penwidth=1.5];
'''
def _fig03():
    P = lambda x, y: f'pos="{x * 72:.0f},{y * 72:.0f}!"'
    X = dict(st=1.0, v=3.35, c=5.85, m=8.35)       # column centres (inches)
    top, bot = 10.25, 1.85                             # frame extent
    fr = lambda n, x, w, lab: (f'{n} [label="{lab}", labelloc=t, fixedsize=true, width={w}, height={top - bot:.2f}, '
                               f'penwidth=1.4, fontsize=13, fillcolor="#FFFFDE", color="#AAAA33", fontcolor="#333333", {P(x, (top + bot) / 2)}];')
    body = [
        'splines=false; node [fontsize=12];',
        fr("FV", X["v"], 2.15, "VIEW LAYER\\nStakeholder Interaction"),
        fr("FC", X["c"], 2.55, "CONTROLLER LAYER\\nTrust & Authorisation\\nEnforcement"),
        fr("FM", X["m"], 2.15, "MODEL LAYER\\nTrust & Governance State"),
    ]
    st = [("sP", "Patients", 9.0), ("sG", "Guardians /\\nAuthorised Parties", 8.1), ("sH", "Healthcare\\nProfessionals", 7.1),
          ("sA", "Auditors", 2.4)]
    vw = [("vP", "Patient Consent\\nInterface", 9.0), ("vG", "Approval Interface", 8.1), ("vH", "Healthcare Access\\nInterface", 7.1),
          ("vA", "Audit / Evidence\\nInterface", 2.4)]
    ct = [("c1", "Request Validation", 9.0), ("c2", "DID / VC Verification", 7.95), ("c3", "Authority Verification", 6.9),
          ("c4", "Multi-Party\\nThreshold Evaluation", 5.85), ("c5", "Policy & Scope\\nEvaluation", 4.8),
          ("c6", "Authorisation Decision", 3.6), ("c7", "Audit Event\\nGeneration", 2.4)]
    md = [("m7", "Identity &\\nDID Records", 7.95), ("m6", "Credential /\\nAuthority Evidence", 6.9), ("m5", "Consent Object", 6.15),
          ("m4", "Approval Evidence", 5.55), ("m3", "Policy & Data Scope", 4.8), ("m1", "Lifecycle State", 3.95),
          ("m2", "Authorisation\\nEvidence", 3.1)]
    for n, l, y in st:
        body.append(f'{n} [label="{l}", {P(X["st"], y)}];')
    for col, rows in (("v", vw), ("c", ct), ("m", md)):
        for n, l, y in rows:
            extra = ""
            body.append(f'{n} [label="{l}"{extra}, {P(X[col], y)}];')
    body.append(f'D [label="Protected\\nHealthcare Data", penwidth=1.3, {P(X["st"], 3.6)}];')
    body.append("""sP -> vP; sG -> vG; sH -> vH; sA -> vA; vP -> c1; vG -> c1; vH -> c1; vA -> c7;
c1 -> c2 -> c3 -> c4 -> c5 -> c6 -> c7; c6 -> D;
c2 -> m7 [dir=both]; c3 -> m6 [dir=both]; c4 -> m5 [dir=both];
c4 -> m4 [dir=both]; c5 -> m3 [dir=both]; c6 -> m1 [dir=both];
c6 -> m2 [dir=both]; c7 -> m2;""")
    src = f"digraph G {{ {HEADC}\n" + "\n".join(body) + "\n}"
    open(f"{OUTC}/fig03.dot", "w").write(src)
    subprocess.run(["neato", "-n2", "-Tpng", f"{OUTC}/fig03.dot", "-o", f"{OUTC}/fig03.png"], check=True)


_fig03()
