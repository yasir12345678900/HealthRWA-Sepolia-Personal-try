"""Gold-style flowcharts laid out with each decision beside its step (Graphviz neato, fixed positions)."""
import subprocess, os
D = os.path.dirname(os.path.abspath(__file__))
P = lambda x, y: f'pos="{x*72:.0f},{y*72:.0f}!"'
HEAD = ['digraph G {', 'graph [bgcolor=white, dpi=300, splines=ortho, pad=0.15];',
        'node [shape=box, style="filled", fillcolor="#FFF2CC", color="#D6B656", fontcolor="#000000", fontname="Trebuchet MS Bold", fontsize=13, penwidth=1.5, margin="0.16,0.08"];',
        'edge [color="#D6B656", penwidth=1.6, arrowsize=0.8];']
lab = lambda n, t, x, y: f'{n} [label="{t}", shape=plaintext, style="", fixedsize=true, width=0.3, height=0.16, margin=0, fontname="Trebuchet MS", fontsize=11, fontcolor="#333333", {P(x, y)}];'
XP, XQ, XD = 2.3, 6.1, 9.4

def build(name, seq, deny, extra_edges=()):
    """seq: list of (id, label, kind, [qid, qlabel, yes_side_ok_label, no_label]) top to bottom; kind in box|round|q
       deny: list of (id, label, kind) in the deny lane, top to bottom, attached at the first decision row"""
    L = list(HEAD); y = 10.3; edges = []; prev = None; i = 0; first_q_y = None
    for item in seq:
        nid, text, kind = item[:3]
        st = 'style="rounded,filled", ' if kind == "round" else ""
        lb = f'label=<{text}>' if text.startswith("<") is False and "<SUB>" in text else f'label="{text}"'
        L.append(f'{nid} [{lb}, {st}{P(XP, y)}];')
        if prev: edges.append(f"{prev} -> {nid};")
        prev = nid
        if len(item) > 3:
            qid, ql, okl, nol = item[3:7]
            L.append(f'{qid} [label="{ql}", shape=diamond, margin="0.02,0.02", {P(XQ, y)}];')
            edges.append(f"{nid} -> {qid};"); edges.append(f"{qid} -> {deny[0][0]};"); prev = qid
            L.append(lab(f"y{i}", okl, XP + 1.1, y - 0.6)); L.append(lab(f"n{i}", nol, XQ + 2.3, y + 0.22)); i += 1
            if first_q_y is None: first_q_y = y
        y -= 1.1 if len(item) > 3 else 0.85
    yd = 3.0 if name == "fig06" else (first_q_y - 1.1 * (len([x for x in seq if len(x) > 3]) - 1) - 1.6)
    for k, (nid, text, kind) in enumerate(deny):
        st = 'style="rounded,filled", ' if kind == "round" else ""
        L.append(f'{nid} [label="{text}", {st}{P(XD, yd - 0.85 * k)}];')
        if k: edges.append(f"{deny[k-1][0]} -> {nid};")
    L += edges + list(extra_edges) + ["}"]
    open(f"{D}/{name}.dot", "w").write("\n".join(L))
    subprocess.run(["neato", "-n2", "-Tpng", f"{D}/{name}.dot", "-o", f"{D}/{name}.png"], check=True)

# Figure 5.4 (fig06): end-to-end workflow
build("fig06", [
    ("A", "Patient Creates Consent", "round"),
    ("B", "Consent Specification\\nPurpose · Data Scope · Conditions", "box"),
    ("C", "DID / VC Verification\\nIdentity & Authority Validation", "box", "Q0", "Identity and\\nAuthority Valid?", "Yes", "No"),
    ("Dn", "Identify Authorisation Participants", "box"),
    ("E", "Multi-Party Approval\\nCollect Independent Approvals", "box", "Q1", "Threshold\\nSatisfied?", "Yes", "No"),
    ("G", "Policy Evaluation\\nPurpose & Data-Scope Validation", "box", "Q2", "Policy\\nCompliant?", "Yes", "No"),
    ("I", "Authorisation Decision<BR/>V<SUB>I</SUB> ∧ V<SUB>A</SUB> ∧ V<SUB>P</SUB> (Eq. (6))", "box", "Q3", "Decision =\\nALLOW?", "Allow", "Deny"),
    ("J", "ALLOW\\nGrant Data Access", "round"),
    ("K", "Access Healthcare Data", "box"),
    ("M", "Record Audit Evidence", "box"),
], [("Ld", "DENY\\nReject Access", "round")], ["Ld -> M;"])

# Figure 6.5 (fig11): temporal and lifecycle validation
build("fig11", [
    ("A", "Access Request", "round"),
    ("B", "Retrieve Consent Validity Interval", "box"),
    ("C", "Check Consent Validity Interval", "box", "Q1", "Within Valid\\nTime?", "Yes", "No"),
    ("Dn", "Retrieve and Check Lifecycle State", "box", "Q2", "State Permits\\nOperation?", "Yes", "No"),
    ("E", "Evaluate Revocation Status", "box", "Q3", "Revoked?", "No", "Yes"),
    ("F", "Validate Requested Transition", "box", "Q4", "Transition\\nPermitted?", "Yes", "No"),
    ("H", "Record Temporal and\\nLifecycle Evidence", "box"),
    ("G", "Continue Authorisation Evaluation", "round"),
], [("X", "Record Lifecycle-\\nBased Denial", "box"), ("Y", "Deny Access", "round")])
print("done")

def build2(name, seq):
    """like build, but each decision's No-branch has its own box(es) in the right lane at the same row"""
    XD = 10.2
    L = list(HEAD); y = 10.3; edges = []; prev = None; i = 0
    for item in seq:
        nid, text, kind = item[:3]
        st = 'style="rounded,filled", ' if kind == "round" else ""
        L.append(f'{nid} [label="{text}", {st}{P(XP, y)}];')
        if prev: edges.append(f"{prev} -> {nid};")
        prev = nid
        if len(item) > 3:
            qid, ql, okl, nol, dens = item[3:8]
            L.append(f'{qid} [label="{ql}", shape=diamond, margin="0.02,0.02", {P(XQ, y)}];')
            edges.append(f"{nid} -> {qid};"); prev = qid
            L.append(lab(f"y{i}", okl, XP + 1.1, y - 0.6)); L.append(lab(f"n{i}", nol, XQ + 2.3, y + 0.22)); i += 1
            last = qid
            for k, (did, dl) in enumerate(dens):
                L.append(f'{did} [label="{dl}", {P(XD, y - 0.85 * k)}];'); edges.append(f"{last} -> {did};"); last = did
        y -= 1.1 if len(item) > 3 else 0.85
    L += edges + ["}"]
    open(f"{D}/{name}.dot", "w").write("\n".join(L))
    subprocess.run(["neato", "-n2", "-Tpng", f"{D}/{name}.dot", "-o", f"{D}/{name}.png"], check=True)

# Figure 6.2 (fig08): identity and authority verification
build("fig08", [
    ("A", "Participant Requests Participation", "round"),
    ("B", "Resolve Participant DID", "box", "Q1", "DID Valid?", "Yes", "No"),
    ("C", "Retrieve Verifiable Credential", "box", "Q2", "VC Retrieved\\nand Valid?", "Yes", "No"),
    ("Dn", "Extract Role and Authority Claims", "box", "Q3", "Authority Matches\\nConsent?", "Yes", "No"),
    ("E", "Record Verification Evidence", "box"),
    ("F", "Return Verified Identity\\nand Authority", "round"),
], [("R", "Reject Participant", "box")])

# Figure 6.3 (fig09): threshold-based multi-party authorisation
build2("fig09", [
    ("A", "Consent Requires\\nMulti-Party Approval", "round"),
    ("B", "Identify Required Participants", "box"),
    ("B2", "Define Authorisation Threshold N", "box"),
    ("C", "Participant Submits Approval", "box"),
    ("Dn", "Verify DID and VC", "box", "Q1", "Participant\\nVerified?", "Yes", "No", [("R1", "Reject Invalid Approval")]),
    ("E", "Check Membership of Required Set G", "box", "Q2", "Participant in\\nRequired Set G?", "Yes", "No", [("R2", "Reject Unauthorised Approval")]),
    ("F", "Check for Prior Approval", "box", "Q3", "Already\\nApproved?", "No", "Yes", [("R3", "Reject Duplicate Approval")]),
    ("G", "Record Valid Approval", "box"),
    ("H", "Update Approval Count", "box", "Q4", "Threshold\\nSatisfied?", "Yes", "No", [("P", "Consent Remains Pending"), ("P2", "Record Threshold-Pending Event")]),
    ("I", "Activate Authorisation", "box"),
    ("J", "Generate Activation or\\nToken Evidence", "box"),
    ("K", "Record Threshold-Satisfied Event", "box"),
])
