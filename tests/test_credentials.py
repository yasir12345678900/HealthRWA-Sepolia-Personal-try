"""Verifiable credentials (original report, RO2 Steps 3-6), the requester binding in VI, and VL as the lifecycle check."""
import json
from datetime import datetime, timedelta


def _active():
    from models.consent import Consent
    from services.identity_service import sign_consent
    c = Consent("vc-1", "did:patient:x", "did:hospital:001", ["did:parent:A", "did:parent:B"], "Treatment", ["Observation"], 2,
                start_date=(datetime.now() - timedelta(days=1)).isoformat(), expiry_date=(datetime.now() + timedelta(days=30)).isoformat(),
                token_id="SBT-1")
    for g in c.guardian_dids:
        sig, addr = sign_consent(g, c.consent_id); c.signatures.append(g); c.signature_data[g] = {"signer": addr, "signature": sig}
    return c


def test_demo_credentials_verify_and_are_reproducible():
    from services.identity_service import load_credentials, verify_vc, issue_credential
    store = load_credentials()
    for g in ("did:parent:A", "did:parent:B", "did:parent:C"):
        assert verify_vc(g, role="guardian") is True and verify_vc(g, role="doctor") is False
    for d in ("did:hospital:001", "did:hospital:002"):
        assert verify_vc(d, role="doctor") is True and verify_vc(d, role="guardian") is False
    c = store["did:parent:A"]                                    # the stored credential is exactly what the demo issuer signs
    assert issue_credential("did:parent:A", "guardian") == c


def test_each_credential_condition_fails_on_its_own():
    from services.identity_service import check_credential, get_credential, issue_credential
    did = "did:hospital:001"
    ok = check_credential(did, role="doctor"); assert ok["VALID"] is True
    t = json.loads(json.dumps(get_credential(did))); t["validUntil"] = "2099-12-31T23:59:59"     # claim changed after signing
    r = check_credential(did, role="doctor", credential=t); assert r["Sig_VC"] is False and r["VALID"] is False
    r = check_credential(did, role="doctor", credential=issue_credential(did, "doctor", issuer_did="did:example:other"))
    assert r["Issuer_valid"] is False and r["VALID"] is False
    r = check_credential(did, role="doctor", credential=get_credential("did:hospital:002"))
    assert r["Subject_match"] is False and r["VALID"] is False
    r = check_credential(did, role="doctor", now=datetime(2028, 1, 1)); assert r["Time_valid"] is False and r["VALID"] is False
    r = check_credential(did, role="guardian"); assert r["Role_match"] is False and r["VALID"] is False
    r = check_credential("did:hospital:999", role="doctor"); assert r["VC_found"] is False and r["VALID"] is False


def test_did_syntax():
    from services.identity_service import is_valid_did
    assert is_valid_did("did:patient:5f01f823-c8e8-9e40-c911-54b7b1ad843a") and is_valid_did("did:hospital:001")
    for bad in ("", "did:", "did:x", "hospital:001", "did:hospital:00 1", "did:Hospital:001", None, 7):
        assert is_valid_did(bad) is False


def test_vi_binds_the_requester_to_the_consent_doctor():
    from services.access_service import evaluate_allow
    from services.identity_service import verify_signature, verify_vc
    c = _active()
    assert evaluate_allow(c, "AU", verify_sig=verify_signature, verify_did=verify_vc, requester_did="did:hospital:001")["ALLOW"] is True
    m = evaluate_allow(c, "AU", verify_sig=verify_signature, verify_did=verify_vc, requester_did="did:hospital:002")
    assert m["VI"] is False and m["ALLOW"] is False             # a valid doctor credential, but not the doctor in this consent


def test_vl_is_the_lifecycle_check():
    from services.access_service import evaluate_allow
    from services.state_service import lifecycle_state
    c = _active(); assert lifecycle_state(c) == "ACTIVE" and evaluate_allow(c, "AU")["VL"] is True
    c = _active(); c.revoked = True; assert lifecycle_state(c) == "REVOKED" and evaluate_allow(c, "AU")["VL"] is False
    c = _active(); c.expiry_date = (datetime.now() - timedelta(hours=1)).isoformat()
    assert lifecycle_state(c) == "EXPIRED" and evaluate_allow(c, "AU")["VL"] is False
    c = _active(); c.signatures = ["did:parent:A"]
    assert lifecycle_state(c) == "PENDING_SIGNATURE" and evaluate_allow(c, "AU")["VL"] is False
    c = _active(); assert evaluate_allow(c, "US")["VL"] is True and evaluate_allow(c, "US")["VP"] is False   # policy context is VP, not VL
