"""Phase-red: revoke state, sqlite persistence round-trip, honest labels."""
import importlib


def _consent(cid="c-1"):
    from models.consent import Consent
    return Consent(consent_id=cid, patient_did="did:patient:x", requester_did="did:hospital:001",
                   guardian_dids=["did:parent:A", "did:parent:B"], purpose="Treatment", scope=["Observation"],
                   threshold=2, start_date="2026-01-01T00:00:00", expiry_date="2099-12-31T23:59:59")


def test_revoked_consent_state_is_REVOKED():
    from services.state_service import evaluate_state
    c = _consent(); c.signatures = ["a", "b"]; c.token_id = "SBT-9"
    assert evaluate_state(c) == "ACTIVE"
    c.revoked = True
    assert evaluate_state(c) == "REVOKED"


def test_consent_persists_across_reload():
    from database import consent_db
    c = _consent("persist-1"); consent_db.save(c)
    c.signatures.append("did:parent:A"); consent_db.update(c)
    importlib.reload(consent_db)
    assert consent_db.get("persist-1").signatures == ["did:parent:A"]


def test_revoke_persists_and_flags():
    from database import consent_db
    consent_db.save(_consent("rv-1")); consent_db.revoke("rv-1"); importlib.reload(consent_db)
    assert consent_db.get("rv-1").revoked is True and consent_db.get("rv-1").state == "REVOKED"


def test_audit_persists_across_reload():
    from database import audit_db
    e = audit_db.log("did:patient:x", "Patient", "REVOKE_CONSENT", "did:patient:x", "rv-1")
    importlib.reload(audit_db)
    assert e["event_id"] in {x["event_id"] for x in audit_db.get()}


def test_ui_labels_are_honest():
    src = open("app.py", encoding="utf-8").read(); theme = open("halah_theme.py", encoding="utf-8").read()
    assert "Execute Zero-Knowledge Access" not in src and "ZK placeholder" in src
    assert "C = (I, A, P, T, L, E)" in theme
