# Applies the confirmed QA wording fixes to content.json (in place); prints every change.
import json, re
P = "content.json"
c = json.load(open(P, encoding="utf-8"))
S = {s["id"]: s for g in c["groups"] for s in g["slides"]}
log = []
NB = " "

def setv(sid, path, val):
    o = S[sid]
    for k in path[:-1]:
        o = o[k]
    old = o.get(path[-1]) if isinstance(o, dict) else o[path[-1]]
    o[path[-1]] = val
    log.append((sid, "/".join(map(str, path)), old, val))

def sub(sid, path, a, b):
    o = S[sid]
    for k in path[:-1]:
        o = o[k]
    t = o[path[-1]]
    assert a in t, (sid, path, a)
    o[path[-1]] = t.replace(a, b)
    log.append((sid, "/".join(map(str, path)), a, b))

F = lambda sid: S[sid]["fields"]

# 2 agenda
setv(2, ["fields", "items", 4, "sub"], "Chapters 8–10: progress per RO, publications and next-stage work (RO5–RO6)")
# 5 context
setv(5, ["subtitle"], "Sections 1.1, 2.2, 2.4.1 and 5.1: authorisation as a distributed governance problem in the Australian setting")
sub(5, ["notes"], "This slide summarises the research context from Section 1.1.", "This slide summarises the research context from Section 1.1, with the participant roles drawn from Sections 2.2, 2.4.1 and 5.1.")
setv(5, ["fields", "cards", 5, "body"], "My Health Records Act 2012: consumers control provider access; Healthcare Identifiers Act 2010: IHI, HPI-I, HPI-O")
for i, ic in enumerate(["FaHospitalUser", "FaUserShield", "FaUserDoctor", "FaBuildingColumns", "FaScaleBalanced", "FaNotesMedical"]):
    F(5)["cards"][i]["icon"] = ic
# 6 scope
setv(6, ["fields", "stages", 1, "items", 1, "name"], "Formal Security Assurance and Empirical Validation")
F(6)["stages"][1]["items"][0]["desc"] = "Validity periods, expiration, revocation and controlled consent-state transitions"
F(6)["stages"][1]["items"][1]["desc"] = "Formal security and authorisation properties; empirical evaluation with negative and adversarial scenarios"
# 7 SLR steps
setv(7, ["fields", "steps", 0, "body"], "Seven databases, Boolean search string (Figure 2.1), 2022–2026; searched 15 August 2026")
setv(7, ["fields", "steps", 1, "body"], "Six inclusion and six exclusion criteria set before screening, e.g. peer-reviewed, full text and English")
# 8 PRISMA notes: one item per removal step
setv(8, ["fields", "notes"], [
    {"head": "42 removed before screening", "body": "35 duplicate records (same DOI, title and authors) and 7 marked ineligible by automation tools"},
    {"head": "40 excluded at screening", "body": "Unrelated to healthcare data sharing, consent, identity, access control, privacy or auditability"},
    {"head": "3 full texts not retrieved", "body": "43 reports were sought for retrieval; 3 could not be obtained, so 40 were assessed"},
    {"head": "7 excluded at full text", "body": "3 scored below 2.5 on QA1–QA5; 4 were outside the review scope"},
])
F(8)["notes"][2]["icon"] = "FaBan"; F(8)["notes"][3]["icon"] = "FaFilter"
# 9 requirements
setv(9, ["fields", "intro"], "The framework must meet five requirements for a trustworthy data-access decision; each of the 33 studies is assessed against them.")
for i, (ic, n) in enumerate([("FaFileCircleCheck", 9), ("FaIdCard", 11), ("FaUsers", 3), ("FaFilter", 17), ("FaClock", 18)]):
    F(9)["cards"][i]["icon"] = ic
    F(9)["cards"][i]["foot"] = f"Addressed by {n} of 33 studies"
# 10 categories
setv(10, ["fields", "points", 1, "head"], "Security layers stay separate")
setv(10, ["fields", "points", 1, "body"], "Identity (7), access control (7) and blockchain (5) each secure one layer; no single mechanism makes the access decision trustworthy")
# 11 matrix
F(11)["points"][1]["icon"] = "FaUsers"
# 12 gaps
setv(12, ["fields", "rows", 1, "head"], "Identity verified, authority not")
# 13 streams
setv(13, ["fields", "rows", 3, 2], "Limited integration between collective approval thresholds, consent and access decisions")
# 15 research question
setv(15, ["fields", "statement"], "How can a trust-oriented computing framework establish and enforce trustworthy multi-party consent for decentralised healthcare data sharing under identity, authority and policy constraints?")
setv(15, ["subtitle"], "Research gap (Section 3.1) and main research question (Section 3.2)")
# 16 SRQ / RO
setv(16, ["subtitle"], "SRQ1–SRQ6 map one-to-one onto RO1–RO6 (Tables 4.1–4.2); RO1–RO4 in CA2, RO5–RO6 in CA3")
setv(16, ["fields", "rows", 1, 2], "RO2: Decentralised Identity and Authority Trust")
setv(16, ["fields", "rows", 5, 2], "RO6: Formal Security Assurance and Empirical Validation")
# 17 equations
setv(17, ["subtitle"], "Eq. 6 decides access now (CA2); Eq. 24 adds temporal and lifecycle checks in CA3")
setv(17, ["fields", "predicates", 0, "meaning"], "VerifyDID(u) ∧ VerifyVC(u): DID shows who u is, VC shows role or authority (Eq. 8)")
setv(17, ["fields", "predicates", 1, "meaning"], "Holds only if |A_v| ≥ N verified approvals; |A_v| < N ⇒ DENY (Eqs." + NB + "9–10)")
# 18 divider
setv(18, ["title"], "Architecture and solution")
# 20 security properties
setv(20, ["fields", "points", 0, "body"], "Identity and authority evidence checked separately; authentication alone does not authorise")
setv(20, ["fields", "points", 1, "head"], "Multi-party authorisation integrity")
setv(20, ["fields", "points", 1, "body"], "Threshold on verified approvals; no unilateral access when collective approval is required")
setv(20, ["fields", "points", 2, "body"], "Purpose and requested scope checked against the consent; approvals cannot exceed its scope")
for i, ic in enumerate(["FaIdCard", "FaUsers", "FaFilter", "FaFileShield"]):
    F(20)["points"][i]["icon"] = ic
# 21 workflow icons
for i, ic in enumerate(["FaFileSignature", "FaIdCard", "FaUsers", "FaScaleBalanced"]):
    F(21)["points"][i]["icon"] = ic
# 22 RO1
setv(22, ["fields", "points", 0, "body"], "I = identity, A = authorisation requirements, P = purpose and data-scope policy, E = authorisation evidence")
setv(22, ["fields", "points", 3, "body"], "Patient, doctor and guardian checks (Steps 1–3) not yet enforced at creation; VC authority checks in CA3; t_e > t_s check (Step 6) implemented")
for i, ic in enumerate(["FaFileSignature", "FaListCheck", "FaFileShield", "FaCode"]):
    F(22)["points"][i]["icon"] = ic
# 23 RO2
setv(23, ["fields", "points", 3, "body"], "Guardian DID syntax check; EIP-712 approval signatures; W3C VC verification scheduled for CA3")
for i, ic in enumerate(["FaIdCard", "FaUserCheck", "FaFileShield", "FaCode"]):
    F(23)["points"][i]["icon"] = ic
# 24 RO3
setv(24, ["title"], "RO3: no unilateral activation below the threshold")
setv(24, ["fields", "points", 3, "body"], "N" + NB + "=" + NB + "|G| (all guardians sign); EIP-712 signatures verified, duplicates refused, Sepolia SBT minted; k-of-n in CA3")
for i, ic in enumerate(["FaUsers", "FaBan", "FaFileShield", "FaUserShield"]):
    F(24)["points"][i]["icon"] = ic
# 25 RO4
setv(25, ["title"], "RO4: a valid approval is not unlimited access")
setv(25, ["fields", "points", 3, "head"], "Prototype: purpose partly checked")
sub(25, ["fields", "points", 3, "body"], "P_R ⊨ P_C", "P_R" + NB + "⊨" + NB + "P_C")
for i, ic in enumerate(["FaListCheck", "FaVectorSquare", "FaShieldHalved", "FaCircleHalfStroke"]):
    F(25)["points"][i]["icon"] = ic
# 26 RO5
setv(26, ["title"], "RO5: an existing consent is not always usable")
for i, ic in enumerate(["FaClock", "FaListOl", "FaBan", "FaHourglassHalf"]):
    F(26)["points"][i]["icon"] = ic
# 27 RO6
setv(27, ["title"], "RO6: successful execution is not proof of security")
setv(27, ["fields", "points", 1, "body"], "P_sound, P_deny, P_threshold, P_policy, P_scope, P_audit; every ALLOW needs V_I ∧ V_A ∧ V_P (Eq." + NB + "33)")
setv(27, ["fields", "points", 3, "body"], "HALAH logs consent, approval, minting, state-check and access events (Sections 7.11–7.12)")
for i, ic in enumerate(["FaFlask", "FaShieldHalved", "FaCodeCompare", "FaCode"]):
    F(27)["points"][i]["icon"] = ic
# 28 algorithms
R = F(28)["rows"]
R[1][0] = "2: DID and VC Identity and Authority Verification"; R[1][1] = "RO2: Decentralised Identity and Authority Trust"
R[2][0] = "3: Threshold-Based Multi-Party Authorisation"; R[2][1] = "RO3: Trustworthy Multi-Party Authorisation"
R[3][1] = "RO4: Policy- and Context-Aware Access Control"
R[5][0] = "6: Formal and Empirical Authorisation Validation"; R[5][1] = "RO6: Formal Security Assurance and Empirical Validation"
log.append((28, "rows", "short names", "full algorithm and RO names"))
# 30 overview: short role strip under the full-width diagram
setv(30, ["fields", "points"], [
    {"head": "Patient: create consent", "body": "Patient, doctor and guardian DIDs, module scope and start / expiry time"},
    {"head": "Guardian: approve, activate", "body": "Verifies guardian identities, records 2-of-2 signatures, mints the SBT"},
    {"head": "Doctor: verified access", "body": "Checks the consent is ACTIVE; access limited to the authorised modules"},
    {"head": "Auditor: trace the evidence", "body": "Rebuilds the lifecycle from event-level records and the audit ledger"},
])
# 32 doctor
setv(32, ["fields", "items", 1, "body"], "Requested modules are verified, then only MEDICATION and PROCEDURE records are released; the ZK integrity proof is a v1 placeholder")
# 33 auditor
setv(33, ["fields", "takeaway"], "The auditor can reconstruct who accessed the data and why: in the demo, DATA_ACCESS is GRANTED only after consent is ACTIVE")
for i, ic in enumerate(["FaClock", "FaListCheck", "FaLink"]):
    F(33)["points"][i]["icon"] = ic
# 35 tests notes
sub(35, ["notes"], "Stage 2 (CA3) still has to add insufficient approvals at the release gate, a duplicate approval, and out-of-scope and mismatched-purpose requests.",
    "Stage 2 (CA3) still has to add insufficient approvals at the release gate, a duplicate approval, an out-of-scope request submitted directly to the service interface, and a request with a mismatched declared purpose.")
# 37 limitations
setv(37, ["fields", "intro"], "v1.1 records EIP-712 guardian approvals, reports on-chain anchoring per event and labels the data-access proof a placeholder unless the ZK circuit is built.")
setv(37, ["fields", "cards", 0, "body"], "Guardian keys derived from the DID for demonstration; DID check is syntactic; no W3C VC yet (CA3)")
setv(37, ["fields", "cards", 2, "body"], "Fixed purpose list; per-request binding in CA3; release gated by state, proof and scope, not the full decision matrix")
setv(37, ["fields", "cards", 4, "body"], "Groth16 circuit covers consent validity only; development-only trusted setup; not built for the test run (T9 skipped)")
setv(37, ["fields", "cards", 5, "body"], "18 automated tests to date; performance and adversarial measurements are CA3 work")
for i, ic in enumerate(["FaIdCard", "FaUsers", "FaFilter", "FaDatabase", "FaLock", "FaFlask"]):
    F(37)["cards"][i]["icon"] = ic
# 39 progress
setv(39, ["fields", "rows", 2, "evidence"], "|A_v| ≥ N (Eq. 9); 1/2 approvals: consent PENDING_SIGNATURE; 2/2 plus SBT mint: ACTIVE (T3)")
sub(39, ["notes"], "This slide condenses Chapter 8, one row per objective, with each status line taken from the report and shortened to fit. Where Chapter 8 says Stage 2, I write CA3, as Section 1.3 defines it.",
    "This slide summarises Chapter 8, one row per objective. The report's Stage 2 is the next stage, CA3, as Section 1.3 defines it.")
# 41 plan outcomes (Table 10.1, Expected Outcome column, plain wording)
for i, (tag, out) in enumerate([("RO5", "A mechanism that checks whether consent is still active at the point of access"),
                                ("RO6", "A formal security model with explicit security guarantees"),
                                ("RO6", "Empirical evidence and benchmark datasets on enforcement"),
                                ("RO5–RO6", "One integrated, validated framework for multi-party consent")]):
    F(41)["steps"][i]["tag"] = tag; F(41)["steps"][i]["outcome"] = out
log.append((41, "steps/outcome", "", "Table 10.1 outcomes"))
# 42 contributions
setv(42, ["fields", "cards", 0, "body"], "C = (I, A, P, E)\nDecision(C, R) = ALLOW\n⇔ V_I ∧ V_A ∧ V_P\nConsent is evaluated, not just stored as a record")
for i, (ic, ev) in enumerate([("FaFileSignature", "Eq. (6), Eq. (7); Chapter 5"), ("FaSitemap", "Chapter 5; Table 7.2"),
                              ("FaCode", "Chapter 7; Tables 7.1 and 7.4"), ("FaFlask", "Table 7.3: 16 passed, 2 skipped, 0 failed")]):
    F(42)["cards"][i]["icon"] = ic; F(42)["cards"][i]["foot"] = "Evidence: " + ev

# en dash for every numeric or ID range (EIP-712, ERC-5484, 2-of-2, k-of-n and ISO dates are left alone)
RANGE = re.compile(r"(?<![\w.])((?:QA|SRQ|RO|S|T)?\d+(?:\.\d+)?)-((?:QA|SRQ|RO|S|T)?\d+(?:\.\d+)?)(?![\w.-])")
def dash(o, where):
    if isinstance(o, str):
        n = RANGE.sub(r"\1–\2", o)
        if n != o:
            for m in RANGE.finditer(o): log.append((where, "range", m.group(0), m.group(0).replace("-", "–")))
        return n
    if isinstance(o, list): return [dash(x, where) for x in o]
    if isinstance(o, dict): return {k: (dash(v, where) if k not in ("icon",) else v) for k, v in o.items()}
    return o
for g in c["groups"]:
    g["slides"] = [dash(s, s["id"]) for s in g["slides"]]
json.dump(c, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for x in log: print(x)

# second pass after the visual check
c = json.load(open(P, encoding="utf-8"))
S = {s["id"]: s for g in c["groups"] for s in g["slides"]}
S[30]["fields"]["points"][1]["body"] = "Verifies guardian identities, records both signatures and mints the SBT"
S[2]["fields"]["items"][2]["head"] = "Architecture and solution"
S[7]["fields"]["steps"][0]["body"] = "Seven databases, 2022–2026, Boolean search string (Figure 2.1); searched 15 August 2026"
S[7]["fields"]["steps"][1]["body"] = "Six inclusion and six exclusion criteria set before screening (peer-reviewed, full text, English)"
S[7]["fields"]["steps"][2]["body"] = "Title-abstract, then full-text screening; each study scored 1, 0.5 or 0 on QA1–QA5; below 2.5 of 5 excluded"
S[37]["fields"]["cards"][4]["body"] = "Groth16 circuit covers consent validity only; development-only trusted setup; not built for the test run (T9 skipped)"
json.dump(c, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
c = json.load(open(P, encoding="utf-8"))
S = {s["id"]: s for g in c["groups"] for s in g["slides"]}
if "arranged" not in S[33]["notes"]:
    S[33]["notes"] = S[33]["notes"].replace("Repeated state checks are left out of the figure.", "Repeated state checks are left out of the figure, and on this slide I have arranged its six event blocks in time order, numbered 1 to 6.")
json.dump(c, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
# third pass: confirmed findings of the final review
c = json.load(open(P, encoding="utf-8"))
S = {s["id"]: s for g in c["groups"] for s in g["slides"]}
S[17]["fields"]["predicates"][2]["meaning"] = "R must meet the consent's purpose and scope; S_R" + NB + "⊈" + NB + "S_C ⇒ reject (Eqs. 11, 5)"
S[24]["fields"]["points"][3]["body"] = "N" + NB + "=" + NB + "|G| (all guardians sign); EIP-712 signatures verified, duplicates refused, Sepolia SBT minted; configurable k-of-n in CA3"
S[32]["title"] = "Consent is checked before data are released"
json.dump(c, open(P, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
