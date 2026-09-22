"""EIP-712 signatures, mocked-chain e2e lifecycle, decision matrix, v3 routing."""
import pytest
from datetime import datetime, timedelta


def _consent():
    from models.consent import Consent
    c = Consent(consent_id="g-1", patient_did="did:patient:x", requester_did="did:hospital:001",
                guardian_dids=["did:parent:A", "did:parent:B"], purpose="Treatment", scope=["Observation"],
                threshold=2, signatures=[], start_date=(datetime.now() - timedelta(days=1)).isoformat(),
                expiry_date=(datetime.now() + timedelta(days=30)).isoformat(), state="ACTIVE", token_id="SBT-7")
    c.jurisdiction = "AU"; return c


def _signed(c):
    from services.identity_service import sign_consent
    for g in c.guardian_dids:
        sig, addr = sign_consent(g, c.consent_id); c.signatures.append(g); c.signature_data[g] = {"signer": addr, "signature": sig}
    return c


def test_eip712_roundtrip_and_rejections():
    from services.identity_service import sign_consent, verify_signature, guardian_address
    sig, addr = sign_consent("did:parent:A", "consent-123")
    assert sig.startswith("0x") and len(sig) == 132 and addr == guardian_address("did:parent:A")
    assert verify_signature("did:parent:A", "consent-123", sig) is True
    assert verify_signature("did:parent:B", "consent-123", sig) is False
    assert verify_signature("did:parent:A", "consent-999", sig) is False
    assert verify_signature("did:parent:A") is False


def test_matrix_all_pass_and_each_dimension_fails_independently():
    from services.access_service import evaluate_allow
    from services.identity_service import verify_signature, verify_vc
    assert evaluate_allow(_signed(_consent()), "AU", verify_sig=verify_signature, verify_did=verify_vc)["ALLOW"] is True
    assert evaluate_allow(_signed(_consent()), "US")["VL"] is False
    c = _signed(_consent()); c.expiry_date = (datetime.now() - timedelta(hours=1)).isoformat(); assert evaluate_allow(c, "AU")["VT"] is False
    c = _signed(_consent()); c.revoked = True; assert evaluate_allow(c, "AU")["VA"] is False
    c = _signed(_consent()); c.purpose = "Marketing"; assert evaluate_allow(c, "AU")["VP"] is False
    c = _signed(_consent()); c.signature_data["did:parent:A"]["signature"] = "0x" + "11" * 65
    assert evaluate_allow(c, "AU", verify_sig=verify_signature)["VI"] is False


def test_e2e_lifecycle_with_mocked_chain(monkeypatch):
    from services.consent_service import create_consent
    from services.identity_service import sign_consent, verify_signature
    from services.state_service import evaluate_state
    from services import blockchain_service as bc
    from database import consent_db, audit_db
    class Fake:
        def has_v3(self): return False
        def mint_consent(self, p, r, purpose, exp): return {"tx_hash": "0x" + "ab" * 32, "status": 1, "block_number": 1, "token_id": 4}
        def revoke(self, tid): return {"tx_hash": "0x" + "cd" * 32, "status": 1, "block_number": 2}
    class FakeChain:
        ConsentContract = Fake
    monkeypatch.setattr(bc, "chain", FakeChain)
    c = create_consent("did:patient:x", "did:hospital:001", ["did:parent:A", "did:parent:B"], ["Observation"], "Treatment",
                       "2026-01-01T00:00:00", "2099-12-31T23:59:59")
    consent_db.save(c); assert evaluate_state(c) == "PENDING_SIGNATURE"
    for g in c.guardian_dids:
        sig, addr = sign_consent(g, c.consent_id); assert verify_signature(g, c.consent_id, sig); c.signatures.append(g)
    r = bc.mint_consent(c); c.token_id = f"SBT-{r['token_id']}"; consent_db.update(c)
    assert audit_db.log("Blockchain", "SmartContract", "ONCHAIN_MINT", c.patient_did, c.consent_id, tx_hash=r["tx_hash"], block_number=1)["onchain"] is True
    assert evaluate_state(c) == "ACTIVE"
    consent_db.revoke(c.consent_id); assert bc.revoke(4)["status"] == 1 and evaluate_state(consent_db.get(c.consent_id)) == "REVOKED"


def test_service_routes_to_v3_when_supported(monkeypatch):
    from services import blockchain_service as bc
    calls = {}
    class Fake:
        def has_v3(self): return True
        def mint_consent_v3(self, p, r, purpose, nb, exp, jur, burn_auth=2):
            calls.update(jur=jur, nb=nb, exp=exp); return {"token_id": 1, "version": 3}
    class FakeChain:
        ConsentContract = Fake
    monkeypatch.setattr(bc, "chain", FakeChain)
    assert bc.mint_consent(_consent())["version"] == 3 and calls["jur"] == "AU" and calls["nb"] < calls["exp"]
