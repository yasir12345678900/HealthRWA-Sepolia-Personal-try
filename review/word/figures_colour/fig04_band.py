"""Figure 4 (functional decomposition) in the original Mermaid design, stacked so every label is readable."""
import subprocess, os
D = os.path.dirname(os.path.abspath(__file__))
P = lambda x, y: f'pos="{x*72:.0f},{y*72:.0f}!"'
def bb(x1, y1, x2, y2): return f'bb="{x1*72:.0f},{y1*72:.0f},{x2*72:.0f},{y2*72:.0f}"'
CL = 'style=filled; fillcolor="#FFFFDE"; color="#AAAA33"; fontsize=13;'
view = [("Patient", 1.9), ("Guardian / Authorised\\nParticipant", 3.75), ("Doctor", 5.55), ("Auditor", 6.95)]
ctrl = [("Identity\\nVerification", 0.85), ("Authority\\nVerification", 2.45), ("Approval\\nAggregation", 4.05),
        ("Policy\\nEnforcement", 5.65), ("Decision\\nEngine", 7.2), ("Audit\\nCoordinator", 8.75)]
model = [("DID", 0.6), ("VC", 1.5), ("Consent", 2.5), ("Approval", 3.6), ("Policy", 4.65), ("Evidence", 5.7), ("Lifecycle", 6.8)]
L = ['digraph G {', 'splines=false;',
     'graph [fontname="Trebuchet MS", fontsize=13, fontcolor="#333333", bgcolor=white, dpi=300, pad=0.15];',
     'node [shape=box, style=filled, fillcolor="#ECECFF", color="#9370DB", fontcolor="#333333", fontname="Trebuchet MS", fontsize=12, penwidth=1.3, margin="0.12,0.06"];',
     'edge [color="#333333", arrowsize=0.8, penwidth=1.5];']
L += [f'subgraph cluster_v {{ label="VIEW"; {CL} {bb(0.9, 4.75, 7.9, 5.85)};']
L += [f'v{i} [label="{l}", {P(x, 5.2)}];' for i, (l, x) in enumerate(view)] + ['}']
L += [f'subgraph cluster_c {{ label="CONTROLLER"; {CL} {bb(0.05, 2.95, 9.6, 4.05)};']
L += [f'c{i} [label="{l}", {P(x, 3.4)}];' for i, (l, x) in enumerate(ctrl)] + ['}']
L += [f'subgraph cluster_m {{ label="MODEL"; {CL} {bb(0.05, 0.9, 7.45, 1.95)};']
L += [f'm{i} [label="{l}", {P(x, 1.35)}];' for i, (l, x) in enumerate(model)] + ['}']
L += [f'subgraph cluster_r {{ label="PROTECTED RESOURCE"; labelloc=b; {CL} {bb(7.65, 0.75, 9.6, 1.95)};', f'hd [label="Healthcare Data", {P(8.625, 1.5)}];', '}']
pt = lambda n, x, y: f'{n} [shape=point, width=0.01, style=invis, {P(x, y)}];'
L += [pt("a1", 2.8, 4.75), pt("a2", 2.8, 4.05), pt("b1", 2.0, 2.95), pt("b2", 2.0, 1.95), pt("r1", 8.625, 2.95), pt("r2", 8.625, 1.95)]
L += ["a1 -> a2; b1 -> b2 [dir=both]; r1 -> r2 [dir=both];", "}"]
open(f"{D}/fig04b.dot", "w").write("\n".join(L))
subprocess.run(["neato", "-n2", "-Tpng", f"{D}/fig04b.dot", "-o", f"{D}/fig04b.png"], check=True)
