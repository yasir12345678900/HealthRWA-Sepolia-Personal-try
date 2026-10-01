"""Adversarial evaluation of the HALAH authorisation decision (CA2 report, Section 6.8.14).
Twelve attack scenarios A1-A12, each aimed at one component of C = (I, A, P, T, L, E) or at the contract.
Every scenario must end in a refusal. No Sepolia transaction is sent: A12 runs the real ConsentSBTv3
bytecode on an in-memory EVM (eth-tester), and A7/A8 are additionally evidenced on-chain by tools/verify_poc."""
import json, os, pytest
from datetime import datetime, timedelta
from models.consent import Consent
from models.access import AccessRequest
from services.access_service import evaluate_allow, check_scope
from services.identity_service import sign_consent, verify_signature, verify_vc
from services import zk_service as zk
from database import audit_db

G = ["did:parent:A", "did:parent:B"]

def consent(**kw):
    c = Consent(consent_id="adv-1", patient_did="did:patient:x", requester_did="did:hospital:001", guardian_dids=list(G),
                purpose="Treatment", scope=["Observation", "Medication"], threshold=2, signatures=[],
                start_date=(datetime.now() - timedelta(days=1)).isoformat(), expiry_date=(datetime.now() + timedelta(days=30)).isoformat(),
                state="ACTIVE", token_id="SBT-1")
    for g in G:
        sig, addr = sign_consent(g, c.consent_id); c.signatures.append(g); c.signature_data[g] = {"signer": addr, "signature": sig}
    for k, v in kw.items(): setattr(c, k, v)
    return c

def decide(c, jur="AU"):
    return evaluate_allow(c, jur, verify_sig=verify_signature, verify_did=verify_vc)

def test_baseline_allows():
    assert decide(consent())["ALLOW"] is True

# A1 - a signer outside the guardian set G submits a valid signature
def test_A1_signer_outside_G_is_not_counted():
    c = consent(); c.signatures = ["did:parent:A"]; del c.signature_data["did:parent:B"]
    sig, addr = sign_consent("did:parent:Z", c.consent_id)          # cryptographically valid, but Z is not in G
    c.signatures.append("did:parent:Z"); c.signature_data["did:parent:Z"] = {"signer": addr, "signature": sig}
    m = decide(c); assert m["VA"] is False and m["ALLOW"] is False

# A2 - replay of a guardian's signature for a different consent
def test_A2_replayed_signature_is_rejected():
    sig, _ = sign_consent("did:parent:A", "some-other-consent")
    assert verify_signature("did:parent:A", "adv-1", sig) is False
    c = consent(); c.signature_data["did:parent:A"]["signature"] = sig
    m = decide(c); assert m["VI"] is False and m["ALLOW"] is False

# A3 - the same guardian approves twice to reach the threshold
def test_A3_duplicate_approval_does_not_reach_threshold():
    c = consent(); c.signatures = ["did:parent:A", "did:parent:A"]; del c.signature_data["did:parent:B"]
    m = decide(c); assert m["VA"] is False and m["ALLOW"] is False

# A4 - requested scope exceeds the authorised scope (S_R not a subset of S_C)
def test_A4_over_scope_request_is_rejected():
    c = consent()
    r = AccessRequest("did:hospital:001", c.patient_did, ["Observation", "Procedure"], "Treatment", datetime.now().isoformat())
    assert check_scope(c, r) is False

# A5 - empty request scope
def test_A5_empty_scope_is_rejected():
    c = consent()
    r = AccessRequest("did:hospital:001", c.patient_did, [], "Treatment", datetime.now().isoformat())
    assert check_scope(c, r) is False

# A6 - request outside the validity interval (before notBefore, after expiry)
def test_A6_outside_validity_interval_is_denied():
    early = consent(start_date=(datetime.now() + timedelta(days=1)).isoformat())
    late = consent(expiry_date=(datetime.now() - timedelta(hours=1)).isoformat())
    assert decide(early)["VT"] is False and decide(early)["ALLOW"] is False
    assert decide(late)["VT"] is False and decide(late)["ALLOW"] is False

# A7 - requester declares a jurisdiction different from the consent's
def test_A7_jurisdiction_mismatch_is_denied():
    m = decide(consent(), "US"); assert m["VL"] is False and m["ALLOW"] is False
    assert decide(consent(), "AU")["ALLOW"] is True

# A8 - access after revocation
def test_A8_revoked_consent_is_denied():
    m = decide(consent(revoked=True)); assert m["VA"] is False and m["ALLOW"] is False

# A9 - tampered Groth16 proof / public signal
def test_A9_tampered_proof_fails_verification():
    if not zk.zk_available(): pytest.skip("zk build missing")
    p = zk.generate_proof(consent()); assert zk.verify_proof(p) is True
    bad = dict(p); bad["publicSignals"] = list(p["publicSignals"]); bad["publicSignals"][1] = str(int(bad["publicSignals"][1]) ^ 1)
    assert zk.verify_proof(bad) is False
    bad2 = json.loads(json.dumps(p)); bad2["proof"]["pi_a"][0] = str(int(bad2["proof"]["pi_a"][0]) + 1)
    assert zk.verify_proof(bad2) is False

# A10 - proof for an expired consent cannot even be generated (circuit constraint now <= expiry)
def test_A10_expired_consent_cannot_be_proven():
    if not zk.zk_available(): pytest.skip("zk build missing")
    with pytest.raises(RuntimeError):
        zk.generate_proof(consent(expiry_date=(datetime.now() - timedelta(days=1)).isoformat()))

# A11 - modification of a recorded audit event is detected by its digest
def test_A11_ledger_tampering_is_detected():
    e = {"actor_did": "did:hospital:001", "action": "DATA_ACCESS", "patient_did": "did:patient:x", "consent_id": "adv-1",
         "result": "DENIED", "timestamp": datetime.now().isoformat()}
    e["event_digest"] = audit_db.event_digest(e)
    assert audit_db.event_digest(e) == e["event_digest"]
    e["result"] = "GRANTED"                                           # the attacker rewrites the outcome
    assert audit_db.event_digest(e) != e["event_digest"]

# A12 - mint and revoke from an account that is not the contract owner (real bytecode on an in-memory EVM)
def test_A12_non_owner_cannot_mint_or_revoke():
    try:
        from web3 import Web3, EthereumTesterProvider
    except Exception:
        pytest.skip("eth-tester not installed")
    art = json.load(open(os.path.join(os.path.dirname(__file__), "..", "blockchain", "abi", "ConsentSBTv3.json")))
    w3 = Web3(EthereumTesterProvider()); owner, attacker, patient, doctor = w3.eth.accounts[:4]
    C = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    addr = w3.eth.get_transaction_receipt(C.constructor().transact({"from": owner})).contractAddress
    c = w3.eth.contract(address=addr, abi=art["abi"])
    now = w3.eth.get_block("latest").timestamp
    tid = c.functions.mintConsentV3(patient, doctor, "Treatment", now, now + 86400, b"AU", 2).call({"from": owner})
    c.functions.mintConsentV3(patient, doctor, "Treatment", now, now + 86400, b"AU", 2).transact({"from": owner})
    assert c.functions.checkValidAt(tid, b"AU").call() is True and c.functions.checkValidAt(tid, b"US").call() is False
    with pytest.raises(Exception):                                    # Ownable: caller is not the owner
        c.functions.mintConsentV3(attacker, doctor, "Treatment", now, now + 86400, b"AU", 2).transact({"from": attacker})
    with pytest.raises(Exception):
        c.functions.revoke(tid).transact({"from": attacker})
    assert c.functions.checkValid(tid).call() is True                 # still valid: the attacker changed nothing
    with pytest.raises(Exception):                                    # soulbound: transfer is impossible even for the holder
        c.functions.transferFrom(patient, attacker, tid).transact({"from": patient})
    c.functions.revoke(tid).transact({"from": owner})
    assert c.functions.checkValid(tid).call() is False
