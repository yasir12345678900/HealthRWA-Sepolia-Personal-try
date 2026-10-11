"""App-level checks with Streamlit's test runner (no browser): the patient form and the doctor screen."""
import os, shutil, tempfile
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def app_test(monkeypatch):
    try:
        from streamlit.testing.v1 import AppTest
    except Exception:
        pytest.skip("streamlit testing API not available")
    monkeypatch.chdir(ROOT)
    for k in ("CONTRACT_ADDRESS", "PRIVATE_KEY", "RPC_URL", "SEPOLIA_RPC_URL"):
        monkeypatch.delenv(k, raising=False)
    return AppTest


def _patient(AppTest, doctor, guardians):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.multiselect[0].set_value(["Observation"]).run()
    [t for t in at.text_input if t.label == "Authorised Doctor DID"][0].set_value(doctor).run()
    [t for t in at.text_area if t.label.startswith("Designated Guardian DIDs")][0].set_value(guardians).run()
    [b for b in at.button if b.label == "Initial Consent"][0].click().run()
    return at


def test_patient_form_checks_the_doctor_and_the_guardians(app_test):
    at = _patient(app_test, "did:hospital:001did:hospital:002", "did:parent:A,did:parent:B")
    assert any("valid doctor credential" in e.value for e in at.error)
    at = _patient(app_test, "did:hospital:001", "did:parent:A,did:parent:Z")
    assert any("valid guardian credential" in e.value for e in at.error)
    at = _patient(app_test, "did:hospital:001", "did:parent:A,did:parent:A")
    assert any("only once" in e.value for e in at.error)
    at = _patient(app_test, "did:hospital:001", "did:parent:A,did:parent:B")
    assert not at.error and any("created and logged" in s.value for s in at.success)


def test_doctor_screen_refuses_another_doctor_and_records_it(app_test):
    from database import consent_db, audit_db
    from services.consent_service import create_consent
    from services.identity_service import sign_consent
    from datetime import datetime, timedelta
    c = create_consent("did:patient:x", "did:hospital:001", ["did:parent:A", "did:parent:B"], ["Observation"], "Treatment",
                       (datetime.now() - timedelta(days=1)).isoformat(), (datetime.now() + timedelta(days=30)).isoformat())
    for g in c.guardian_dids:
        s, a = sign_consent(g, c.consent_id); c.signatures.append(g); c.signature_data[g] = {"signer": a, "signature": s}
    c.token_id = "SBT-LOCAL-test"; consent_db.save(c)
    at = app_test.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Doctor").run()
    [t for t in at.text_input if t.label == "Enter Authorised Consent ID"][0].set_value(c.consent_id).run()
    [t for t in at.text_input if t.label == "Your Doctor DID (requester)"][0].set_value("did:hospital:002").run()
    assert any("(VI) failed" in e.value for e in at.error)
    assert not any(s.value == "Authorised Data Scope" for s in at.subheader)      # nothing about the consent is shown
    [b for b in at.button if b.label == "Request Data Access"][0].click().run()
    rows = [e for e in audit_db.get() if e["consent_id"] == c.consent_id and e["action"] == "DATA_ACCESS"]
    assert rows and rows[-1]["result"] == "DENIED" and rows[-1]["actor_did"] == "did:hospital:002"
    assert rows[-1]["metadata"]["decision_matrix"]["VI"] is False
    [t for t in at.text_input if t.label == "Your Doctor DID (requester)"][0].set_value("did:hospital:001").run()
    assert not any("(VI) failed" in e.value for e in at.error)
    assert any(s.value == "Authorised Data Scope" for s in at.subheader)
