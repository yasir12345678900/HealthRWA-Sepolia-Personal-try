"""Redraw every report flowchart/diagram in black and white (Graphviz, 300 dpi PNG). Content unchanged
except Australian spelling inside the diagrams (Authorisation, decentralised)."""
import os, subprocess

D = os.path.dirname(os.path.abspath(__file__))
OUT = f"{D}/media_bw"
os.makedirs(OUT, exist_ok=True)

HEAD = """
graph [fontname="Liberation Serif", fontsize=13, bgcolor=white, dpi=300, nodesep=0.35, ranksep=0.38, pad=0.15];
node  [shape=box, style=solid, color=black, fontcolor=black, fontname="Liberation Serif", fontsize=13, penwidth=1.3, margin="0.18,0.07"];
edge  [color=black, fontcolor=black, fontname="Liberation Serif", fontsize=12, arrowsize=0.75, penwidth=1.1];
"""
START = 'shape=box, style="rounded", penwidth=1.6'
DEC = 'shape=diamond, margin="0.05,0.04"'
END = 'shape=box, style="rounded,bold"'


def g(name, body, direction="TB", engine="dot"):
    src = f"digraph G {{ rankdir={direction}; {HEAD}\n{body}\n}}"
    open(f"{OUT}/{name}.dot", "w").write(src)
    subprocess.run([engine, "-Tpng", f"{OUT}/{name}.dot", "-o", f"{OUT}/{name}.png"], check=True)


# ---------------------------------------------------------------- Figure 1: SLR search string
g("fig01", r"""
Q [label="SLR Search Query", shape=box, style="rounded,bold"];
C1 [label="Multi-Party Trust\nManagement"]; T1 [label="distributed trust\nmultiparty trust\ndecentralisation"];
C2 [label="Healthcare\nContext"]; T2 [label="healthcare\nEHR\nhealth data\nmedical data"];
C3 [label="Consent\nManagement"]; T3 [label="consent\npatient consent\ndynamic consent\nconsent management"];
C4 [label="Supporting\nRequirements"]; T4 [label="access control\nauthentication\nDID\nverifiable credential\nprivacy\nauditability\ninteroperability"];
O1 [label="OR", shape=hexagon, fontsize=11]; O2 [label="OR", shape=hexagon, fontsize=11];
O3 [label="OR", shape=hexagon, fontsize=11]; O4 [label="OR", shape=hexagon, fontsize=11];
A [label="AND", shape=hexagon, fontsize=11, penwidth=1.6];
R [label="Final Search Results", shape=box, style="rounded,bold"];
Q -> {C1 C2 C3 C4};
C1 -> T1 -> O1; C2 -> T2 -> O2; C3 -> T3 -> O3; C4 -> T4 -> O4;
{O1 O2 O3 O4} -> A -> R;
""", direction="LR")

# ---------------------------------------------------------------- Figure 2: PRISMA 2020 flow
g("fig02", r"""
node [width=3.2];
subgraph cluster_id { label="Identification"; labeljust=l; style=dashed; fontsize=12; labeljust=l;
  I [label="Records identified from:\nDatabases (n = 125)\nRegisters (n = 0)"];
  IR [label="Records removed before screening:\nDuplicate records removed (n = 35)\nRecords marked as ineligible by automation tools (n = 7)\nRecords removed for other reasons (n = 0)"]; }
subgraph cluster_sc { label="Screening"; labeljust=l; style=dashed; fontsize=12; labeljust=l;
  S [label="Records screened\n(n = 83)"];
  SX [label="Records excluded (n = 40)\nReason: unrelated to healthcare data sharing,\nconsent, or decentralised identity"];
  R [label="Reports sought for retrieval\n(n = 43)"];
  RX [label="Reports not retrieved (n = 3)\nReason: full text inaccessible"];
  E [label="Reports assessed for eligibility\n(n = 40)"];
  EX [label="Reports excluded:\nReason 1: insufficient technical/architectural detail (n = 3)\nReason 2: scope mismatch with consent/DID integration (n = 4)"]; }
subgraph cluster_in { label="Included"; labeljust=l; style=dashed; fontsize=12; labeljust=l;
  N [label="Studies included in review (n = 33)\nReports of included studies (n = 33)", penwidth=2]; }
I -> S -> R -> E -> N;
I -> IR; S -> SX; R -> RX; E -> EX;
{rank=same; I; IR} {rank=same; S; SX} {rank=same; R; RX} {rank=same; E; EX}
""")

# ---------------------------------------------------------------- Figure 3: layered MVC (fixed column layout)
def _fig03():
    P = lambda x, y: f'pos="{x * 72:.0f},{y * 72:.0f}!"'
    X = dict(st=1.0, v=3.35, c=5.85, m=8.35)       # column centres (inches)
    top, bot = 10.25, 1.85                             # frame extent
    fr = lambda n, x, w, lab: (f'{n} [label="{lab}", labelloc=t, fixedsize=true, width={w}, height={top - bot:.2f}, '
                               f'penwidth=1.4, fontsize=13, {P(x, (top + bot) / 2)}];')
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
        body.append(f'{n} [label="{l}", style=rounded, penwidth=1.6, {P(X["st"], y)}];')
    for col, rows in (("v", vw), ("c", ct), ("m", md)):
        for n, l, y in rows:
            extra = ", penwidth=2.2" if n == "c6" else ""
            body.append(f'{n} [label="{l}"{extra}, {P(X[col], y)}];')
    body.append(f'D [label="Protected\\nHealthcare Data", shape=cylinder, penwidth=1.6, {P(X["st"], 3.6)}];')
    body.append("""sP -> vP; sG -> vG; sH -> vH; sA -> vA; vP -> c1; vG -> c1; vH -> c1; vA -> c7;
c1 -> c2 -> c3 -> c4 -> c5 -> c6 -> c7; c6 -> D;
c2 -> m7 [dir=both, style=dashed]; c3 -> m6 [dir=both, style=dashed]; c4 -> m5 [dir=both, style=dashed];
c4 -> m4 [dir=both, style=dashed]; c5 -> m3 [dir=both, style=dashed]; c6 -> m1 [dir=both, style=dashed];
c6 -> m2 [dir=both, style=dashed]; c7 -> m2 [style=dashed];""")
    src = f"digraph G {{ {HEAD}\n" + "\n".join(body) + "\n}"
    open(f"{OUT}/fig03.dot", "w").write(src)
    subprocess.run(["neato", "-n2", "-Tpng", f"{OUT}/fig03.dot", "-o", f"{OUT}/fig03.png"], check=True)


_fig03()

# ---------------------------------------------------------------- Figure 5: predicate flow
g("fig05", r"""
p1 [label=<V<SUB>I</SUB>(u)>]; p2 [label=<V<SUB>A</SUB>(C)>]; p3 [label=<V<SUB>P</SUB>(C, R)>];
p4 [label=<V<SUB>T</SUB>(C, t)>]; p5 [label=<V<SUB>L</SUB>(C)>];
q [label="All Required\nPredicates = TRUE?", %s];
A [label="ALLOW", %s]; Dn [label="DENY", %s];
E [label="Generate Authorisation Evidence"];
p1 -> p2 -> p3 -> p4 -> p5 -> q; q -> A [label=" YES"]; q -> Dn [label=" NO"]; A -> E; Dn -> E;
""" % (DEC, END, END))

# ---------------------------------------------------------------- Figure 6: end-to-end workflow
g("fig06", r"""
s [label="Patient Creates Consent", %s];
a [label="Consent Specification\nPurpose • Data Scope • Conditions"];
b [label="DID / VC Verification\nIdentity & Authority Validation"];
c [label="Identify Authorisation Participants"];
d [label="Multi-Party Approval\nCollect Independent Approvals"];
t [label="Threshold\nSatisfied?", %s];
p [label="Policy Evaluation\nPurpose & Data-Scope Validation"];
q [label="Policy\nCompliant?", %s];
z [label="Authorisation Decision", penwidth=2];
al [label="ALLOW\nGrant Data Access", %s]; dn [label="DENY\nReject Access", %s];
h [label="Access Healthcare Data"]; r [label="Record Audit Evidence"];
s -> a -> b -> c -> d -> t; t -> p [label=" Yes"]; t -> z [label=" No"];
p -> q; q -> z [label=" Yes"]; q -> z [label=" No"];
z -> al [label=" Allow"]; z -> dn [label=" Deny"]; al -> h -> r; dn -> r;
""" % (START, DEC, DEC, END, END))

# ---------------------------------------------------------------- Figure 7: RO1 consent creation
g("fig07", r"""
s [label="Patient Creates Consent", %s];
a [label="Collect Patient DID"]; b [label="Specify Authorised Doctor"]; c [label="Specify Guardian DIDs"];
d [label="Specify Purpose and Data Scope"]; e [label="Specify Consent Validity"];
q [label="Consent Specification\nValid?", %s];
y0 [label="Define Authorisation Requirement"]; y2 [label="Generate Consent Identifier"];
y1 [label="Create Trust-Aware Consent Object\nC = (I, A, P, E)"];
y3 [label="Persist Consent Record"]; y4 [label="Record Consent Creation Audit", %s];
n [label="Reject Consent Request", %s];
s -> a -> b -> c -> d -> e -> q; q -> y0 [label=" Yes"]; q -> n [label=" No"]; y0 -> y2 -> y1 -> y3 -> y4;
""" % (START, DEC, END, END))

# ---------------------------------------------------------------- Figure 8: RO2 identity & authority
g("fig08", r"""
s [label="Participant Requests\nParticipation", %s];
a [label="Resolve Participant DID"]; q1 [label="DID Valid?", %s];
b [label="Retrieve Verifiable Credential"]; q2 [label="VC Valid?", %s];
c [label="Extract Role and Authority Claims"]; q3 [label="Authority Matches\nConsent?", %s];
r [label="Reject Participant", %s]; ev [label="Record Verification Evidence"]; ok [label="Return Verified Identity\nand Authority", %s];
s -> a -> q1; q1 -> b [label=" Yes"]; q1 -> r [label=" No"];
b -> q2; q2 -> c [label=" Yes"]; q2 -> r [label=" No"];
c -> q3; q3 -> ev [label=" Yes"]; q3 -> r [label=" No"]; ev -> ok;
{rank=same; r; ev}
""" % (START, DEC, DEC, DEC, END, END))

# ---------------------------------------------------------------- Figure 9: RO3 multi-party
g("fig09", r"""
s [label="Consent Requires\nMulti-Party Approval", %s];
a [label="Identify Required Participants"]; b [label="Participant Submits Approval"]; c [label="Verify DID and VC"];
q1 [label="Participant\nVerified?", %s]; r [label="Reject Invalid Approval", %s];
qg [label="Participant in\nRequired Set G?", %s]; rg [label="Reject Unauthorised\nApproval", %s];
qd [label="Already\nApproved?", %s]; rd [label="Reject Duplicate\nApproval", %s];
d [label="Record Valid Approval"]; e [label=<Update Valid Approval Set A<SUB>v</SUB>>];
q2 [label=<|A<SUB>v</SUB>| &#8805; N ?>, %s]; p [label="Consent Remains Pending", %s];
f [label="Activate Authorisation"]; g [label="Record Approval Evidence"];
h [label="Issue Consent Token or\nActivation Record", %s];
s -> a -> b -> c -> q1; q1 -> r [label=" No"]; q1 -> qg [label=" Yes"]; qg -> rg [label=" No"]; qg -> qd [label=" Yes"];
qd -> rd [label=" Yes"]; qd -> d [label=" No"]; d -> e -> q2;
q2 -> p [label=" No"]; q2 -> f [label=" Yes"]; f -> g -> h;
""" % (START, DEC, END, DEC, END, DEC, END, DEC, END, END))

# ---------------------------------------------------------------- Figure 10: RO4 policy-aware access
g("fig10", r"""
s [label="Doctor Requests\nPatient Data", %s];
a [label="Retrieve Consent Object"]; b [label="Verify Requesting Identity\nand Authority"];
q1 [label="Identity\nValid?", %s]; cs [label="Evaluate Consent State"]; qs [label="Consent\nActive?", %s];
c [label="Verify Multi-Party Authorisation"];
q2 [label="Threshold\nSatisfied?", %s]; d [label="Evaluate Requested Purpose"];
q3 [label="Purpose\nValid?", %s]; e [label="Evaluate Requested Data Scope"];
q4 [label=<S<SUB>R</SUB> &#8838; S<SUB>C</SUB> ?>, %s];
x [label="Deny Access"]; xr [label="Record Denied Access", %s];
f [label="Generate Proof or\nAccess Evidence"]; g [label="Grant Data Access"]; gr [label="Record Granted Access", %s];
s -> a -> b -> q1; q1 -> cs [label=" Yes"]; cs -> qs; qs -> c [label=" Yes"]; c -> q2; q2 -> d [label=" Yes"]; d -> q3; q3 -> e [label=" Yes"]; e -> q4;
q4 -> f [label=" Yes"]; f -> g -> gr;
q1 -> x [label=" No"]; qs -> x [label=" No"]; q2 -> x [label=" No"]; q3 -> x [label=" No"]; q4 -> x [label=" No"]; x -> xr;
""" % (START, DEC, DEC, DEC, DEC, DEC, END, END))

# ---------------------------------------------------------------- Figure 11: RO5 temporal/lifecycle
g("fig11", r"""
s [label="Access Request", %s];
a [label="Retrieve Consent State"]; b [label="Check Consent Validity Interval"];
q1 [label="Within Valid\nTime?", %s]; c [label="Check Lifecycle State"];
q2 [label="State Permits\nAccess?", %s]; d [label="Evaluate Revocation Status"];
q3 [label="Revoked?", %s];
x [label="Deny Access"]; xr [label="Record Lifecycle-Based Denial", %s];
t [label="Validate Requested Transition"]; qt [label="Transition\nPermitted?", %s];
ok [label="Continue Authorisation Evaluation", %s];
s -> a -> b -> q1; q1 -> c [label=" Yes"]; c -> q2; q2 -> d [label=" Yes"]; d -> q3;
q3 -> t [label=" No"]; q3 -> x [label=" Yes"]; t -> qt; qt -> ok [label=" Yes"]; qt -> x [label=" No"]; q1 -> x [label=" No"]; q2 -> x [label=" No"]; x -> xr;
""" % (START, DEC, DEC, DEC, END, DEC, END))

# ---------------------------------------------------------------- Figure 12: RO6 assurance loop
g("fig12", r"""
s [label="Define Security and\nAuthorisation Properties", %s];
a [label="Define Threat and Failure Conditions"]; b [label="Implement Validation Scenarios"];
c1 [label="Execute Valid Consent Workflow"]; c2 [label="Execute Negative and\nAdversarial Scenarios"];
d [label="Collect Decision and Audit Evidence"]; cmp [label="Compare Observed and\nExpected Decisions"];
e1 [label="Evaluate Security Properties\n(soundness, denial, threshold,\npolicy scope, audit consistency)"]; e2 [label="Evaluate Functional and\nPractical Performance"];
q [label="Properties\nSatisfied?", %s];
y [label="Document Evidence and Limitations", %s];
n [label="Identify Security or\nFunctional Failure"]; r [label="Refine Framework"];
s -> a -> b; b -> c1; b -> c2; c1 -> d; c2 -> d; d -> cmp; cmp -> e1; cmp -> e2; e1 -> q; e2 -> q;
q -> y [label=" Yes"]; q -> n [label=" No"]; n -> r; r -> b [constraint=false, style=dashed, label=" iterate"];
""" % (START, DEC, END))

# ---------------------------------------------------------------- NEW: HALAH prototype workflow (Section 7.10)
g("fig_halah", r"""
node [fontsize=12];
subgraph cluster_p { label="Patient view (Section 7.2)"; style=dashed; fontsize=12; labeljust=l;
  p1 [label="Create consent:\npatient DID, doctor DID,\nEMR-module scope, guardian DIDs,\nstart / expiry", %s];
  pv [label="Expiry later\nthan start?", %s]; pr [label="Reject input"];
  p2 [label="Consent stored\nstate = PENDING_SIGNATURE"]; }
subgraph cluster_g { label="Guardian view (Section 7.3)"; style=dashed; fontsize=12; labeljust=l;
  g1 [label="Guardian signs EIP-712 approval"];
  gv [label="Signature valid and\nnot a duplicate?", %s]; gr [label="Reject approval"];
  gt [label=<Approvals = N = |G| ?>, %s];
  g2 [label="Mint consent SBT\n(local ID + Sepolia anchor)"]; }
subgraph cluster_d { label="Doctor view (Section 7.4)"; style=dashed; fontsize=12; labeljust=l;
  d1 [label="Doctor enters consent ID\nand selects EMR modules"];
  dv [label=<State = ACTIVE and<BR/>S<SUB>R</SUB> ⊆ S<SUB>C</SUB> ?>, %s];
  dg [label="ACCESS GRANTED\nrelease Synthea modules", %s]; dd [label="ACCESS DENIED", %s]; }
A [label="Audit log (Section 7.5)\nCREATE_CONSENT • SIGN_CONSENT • MINT_SBT\nSTATE_CHECK • DATA_ACCESS (GRANTED / DENIED)", shape=cylinder, penwidth=1.6];
p1 -> pv; pv -> p2 [label=" Yes"]; pv -> pr [label=" No"];
p2 -> g1 -> gv; gv -> gt [label=" Yes"]; gv -> gr [label=" No"]; gt -> g1 [label=" No: wait for\n next guardian", style=dashed, constraint=false];
gt -> g2 [label=" Yes"]; g2 -> d1 [label=" consent ACTIVE"]; d1 -> dv; dv -> dg [label=" Yes"]; dv -> dd [label=" No"];
{p2 g2 dg dd} -> A [style=dotted, arrowhead=vee];
""" % (START, DEC, DEC, DEC, DEC, END, END))
print(sorted(f for f in os.listdir(OUT) if f.endswith(".png")))
