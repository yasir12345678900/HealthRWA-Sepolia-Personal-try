"""Figure 10 (RO4 policy-aware access) in the report's gold flowchart style, laid out with each check beside
its evaluation step so the figure fits the page at a readable size."""
import subprocess, os
D = os.path.dirname(os.path.abspath(__file__))
P = lambda x, y: f'pos="{x*72:.0f},{y*72:.0f}!"'
L = ['digraph G {', 'graph [bgcolor=white, dpi=300, splines=ortho, pad=0.15];',
     'node [shape=box, style="filled", fillcolor="#FFF2CC", color="#D6B656", fontcolor="#000000", fontname="Trebuchet MS Bold", fontsize=13, penwidth=1.5, margin="0.16,0.08"];',
     'edge [color="#D6B656", penwidth=1.6, arrowsize=0.8];']
XP, XQ, XD = 2.3, 5.4, 7.7
rows = [("C", "Verify Requesting Identity\\nand Authority", "Q1", "Identity and\\nAuthority Valid?", 8.55),
        ("Dn", "Evaluate Consent State", "Q2", "Consent\\nActive?", 7.45),
        ("En", "Verify Multi-Party Authorisation", "Q3", "Threshold\\nSatisfied?", 6.35),
        ("F", "Evaluate Requested Purpose", "Q4", "Purpose\\nValid?", 5.25),
        ("G", "Evaluate Requested Data Scope", "Q5", "Scope Within\\nConsent?", 4.15)]
L += [f'A [label="Doctor Requests\\nPatient Data", style="rounded,filled", {P(XP, 10.3)}];', f'B [label="Retrieve Consent Object", {P(XP, 9.5)}];']
for p, pl, q, ql, y in rows:
    L += [f'{p} [label="{pl}", {P(XP, y)}];', f'{q} [label="{ql}", shape=diamond, margin="0.02,0.02", {P(XQ, y)}];']
L += [f'H [label="Generate or Verify\\nAccess Evidence", {P(XP, 3.0)}];', f'I [label="Grant Data Access", {P(XP, 2.15)}];',
      f'J [label="Record Granted Access", style="rounded,filled", {P(XP, 1.35)}];',
      f'X [label="Deny Access", {P(XD, 3.0)}];', f'Y [label="Record Denied Access", style="rounded,filled", {P(XD, 2.15)}];']
# small text labels for the branches
lab = lambda n, t, x, y: f'{n} [label="{t}", shape=plaintext, style="", fixedsize=true, width=0.3, height=0.16, margin=0, fontname="Trebuchet MS", fontsize=11, fontcolor="#333333", {P(x, y)}];'
for i, (p, pl, q, ql, y) in enumerate(rows):
    L.append(lab(f"y{i}", "Yes", XQ - 1.3, y - 0.62))
    L.append(lab(f"n{i}", "No", XQ + 1.3, y + 0.2))
L += ["A -> B; B -> C; C -> Q1; Q1 -> Dn; Dn -> Q2; Q2 -> En; En -> Q3; Q3 -> F; F -> Q4; Q4 -> G; G -> Q5; Q5 -> H; H -> I; I -> J;",
      "Q1 -> X; Q2 -> X; Q3 -> X; Q4 -> X; Q5 -> X; X -> Y;", "}"]
open(f"{D}/fig10.dot", "w").write("\n".join(L))
subprocess.run(["neato", "-n2", "-Tpng", f"{D}/fig10.dot", "-o", f"{D}/fig10.png"], check=True)
