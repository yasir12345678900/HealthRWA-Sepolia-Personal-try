"""App-level checks with Streamlit's test runner (no browser): the guardian screen, from approval to the threshold."""
import os
from datetime import datetime, timedelta
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


@pytest.fixture()
def anchor_calls(monkeypatch):
    from blockchain import onchain_ui
    calls = []
    monkeypatch.setattr(onchain_ui, "render_onchain_anchor_async", lambda c, a, d: calls.append(c.consent_id))   # no chain is contacted
    return calls


def _consent(guardians, threshold=2):
    from database import consent_db
    from services.consent_service import create_consent
    c = create_consent("did:patient:x", "did:hospital:001", guardians, ["Observation"], "Treatment",
                       (datetime.now() - timedelta(days=1)).isoformat(), (datetime.now() + timedelta(days=30)).isoformat(),
                       threshold=threshold)
    consent_db.save(c)
    return c


def _guardian_screen(AppTest, cid):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Guardian").run()
    [t for t in at.text_input if t.label == "Enter Target Consent ID"][0].set_value(cid).run()
    return at


def _approve(at, did):
    [s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0].set_value(did).run()
    [b for b in at.button if b.label == "Sign Consent via VC"][0].click().run()
    return at


def _rows(cid, action):
    from database import audit_db
    return [e for e in audit_db.get() if e["consent_id"] == cid and e["action"] == action]


def _stored(cid):
    from database import db
    return [r for r in db.all_rows("consents") if r["consent_id"] == cid][0]                 # the row in SQLite, not the object in memory


def test_guardian_without_valid_credential_is_refused_and_recorded(app_test, anchor_calls):
    c = _consent(["did:parent:A", "did:parent:Z"])                    # did:parent:Z holds no credential
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:Z")
    assert any("Guardian credential is not valid" in e.value for e in at.error)
    rows = _rows(c.consent_id, "SIGN_CONSENT")
    assert len(rows) == 1 and rows[0]["result"] == "REJECTED" and rows[0]["actor_did"] == "did:parent:Z"
    assert rows[0]["metadata"]["credential_checks"]["VC_found"] is False
    stored = _stored(c.consent_id)
    assert stored["signatures"] == [] and "did:parent:Z" not in (stored["signature_data"] or {})
    assert not _rows(c.consent_id, "MINT_SBT") and not stored["token_id"] and not anchor_calls


def test_two_approvals_reach_the_threshold_and_start_anchoring_once(app_test, anchor_calls):
    c = _consent(["did:parent:A", "did:parent:B"])
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    assert not at.error and any("Multi-sig: 1/2" in s.value for s in at.success)
    last = _rows(c.consent_id, "SIGN_CONSENT")[-1]
    assert last["result"] == "SUCCESS" and last["actor_did"] == "did:parent:A"
    assert last["metadata"]["threshold"] == 2 and last["metadata"]["signature_count"] == 1
    assert _stored(c.consent_id)["signatures"] == ["did:parent:A"]
    assert not _rows(c.consent_id, "MINT_SBT") and not _stored(c.consent_id)["token_id"]
    assert anchor_calls == []                                         # below the threshold nothing is anchored
    at = _approve(at, "did:parent:B")
    assert not at.error and any("Multi-sig: 2/2" in s.value for s in at.success)
    assert _rows(c.consent_id, "SIGN_CONSENT")[-1]["metadata"]["signature_count"] == 2
    assert len(_rows(c.consent_id, "MINT_SBT")) == 1
    stored = _stored(c.consent_id)
    assert stored["signatures"] == ["did:parent:A", "did:parent:B"] and stored["token_id"] == f"SBT-LOCAL-{c.consent_id[:8]}"
    assert anchor_calls == [c.consent_id]


def test_repeated_approval_by_the_same_guardian_adds_nothing(app_test, anchor_calls):
    c = _consent(["did:parent:A", "did:parent:B"])
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    at = _approve(at, "did:parent:A")
    assert any("already signed" in w.value for w in at.warning)
    stored = _stored(c.consent_id)
    assert stored["signatures"] == ["did:parent:A"] and not stored["token_id"]
    ok = [e for e in _rows(c.consent_id, "SIGN_CONSENT") if e["actor_did"] == "did:parent:A" and e["result"] == "SUCCESS"]
    assert len(ok) == 1
    assert not _rows(c.consent_id, "MINT_SBT") and anchor_calls == []


def test_only_the_named_guardians_can_be_chosen(app_test):
    c = _consent(["did:parent:A", "did:parent:B"])
    at = _guardian_screen(app_test, c.consent_id)
    sel = [s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0]
    assert list(sel.options) == c.guardian_dids and "did:parent:C" not in sel.options   # the selector offers no other DID
