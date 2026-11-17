"""The whole path of one consent in demo mode (no chain is configured), through the four screens of the running
application, with Streamlit's test runner (no browser).

The consent is created in the patient form, approved by its two guardians on the guardian screen, requested by the
named clinician on the clinician screen, revoked by the patient on the patient screen and read on the auditor screen.
Nothing is prepared in the stores by hand: every record of the test is one that a screen wrote.

In demo mode the time is the server clock and every row that names its source says so, the token is the token of the
local ledger, the proof is checked locally, no row carries a transaction, and a deny code field holds one of the nine
codes of Section 6.3.1 or nothing."""
import os
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLINICIAN, REGISTRAR = "did:hospital:001", "did:hospital:002"
G = ["did:parent:A", "did:parent:B"]
NINE = ("OUT-OF-SCOPE", "PURPOSE-MISMATCH", "CONTEXT-MISMATCH", "PRE-VALIDITY", "POST-VALIDITY", "AWAITING-TRIGGER",
        "TRANSITION-PENDING", "EXPIRED", "REVOKED")
SERVER_CLOCK = "system-clock-fallback"
RECORDED = " The denied request is recorded in the audit ledger."


@pytest.fixture()
def app_test(monkeypatch):
    try:
        from streamlit.testing.v1 import AppTest
    except Exception:
        pytest.skip("streamlit testing API not available")
    monkeypatch.chdir(ROOT)
    return AppTest


def _app(AppTest, role=None):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    if role is not None:
        at.sidebar.selectbox[0].set_value(role).run()
    assert not at.exception
    return at


def _click(at, label=None, key=None):
    [b for b in at.button if (b.key == key if key else b.label.startswith(label))][0].click().run()
    assert not at.exception
    return at


def _guardian(AppTest, cid, did):
    at = _app(AppTest, "Guardian")
    [t for t in at.text_input if t.label == "Enter Target Consent ID"][0].set_value(cid).run()
    [s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0].set_value(did).run()
    return at


def _clinician(AppTest, cid, requester=CLINICIAN, scope=()):
    at = _app(AppTest, "Clinician")
    [t for t in at.text_input if t.label == "Enter Authorised Consent ID"][0].set_value(cid).run()
    [t for t in at.text_input if t.label == "Your Clinician DID (requester)"][0].set_value(requester).run()
    if scope:
        [m for m in at.multiselect if m.label == "Select Request Scope"][0].set_value(list(scope)).run()
    return at


def _rows(cid, action=None):
    from database import audit_db
    return [e for e in audit_db.get() if e["consent_id"] == cid and (action is None or e["action"] == action)]


def _stored(cid):
    from database import db
    return [r for r in db.all_rows("consents") if r["consent_id"] == cid][0]


def _code_fields(row):
    """Every string that a ledger row holds in a field for deny codes, at any depth of its metadata."""
    found = []

    def walk(value):
        if isinstance(value, dict):
            for name, inner in value.items():
                if name in ("deny_code", "deny_codes", "DENY"):
                    found.extend(inner if isinstance(inner, list) else ([inner] if inner else []))
                else:
                    walk(inner)
        elif isinstance(value, list):
            for inner in value:
                walk(inner)
    walk(row.get("metadata") or {})
    return found


def _time_sources(row):
    """Every source of a time that a ledger row names."""
    m = row.get("metadata") or {}
    named = [m.get("time_source"), (m.get("time") or {}).get("source") if isinstance(m.get("time"), dict) else None]
    return [s for s in named if s is not None]


def test_one_consent_from_the_patient_form_to_the_auditor_screen_in_demo_mode(app_test):
    import database.repository as repository
    from database import consent_db
    from services import blockchain_service as bc, data_vault, notification_service
    assert not bc.onchain_enabled()                                   # no chain is configured: demo mode
    patient = repository.SyntheaRepository(os.path.join(ROOT, "data", "synthea")).get_patient_dids()["DID"].tolist()[100]

    # ---- Patient: the form ----
    before = set(consent_db.CONSENTS)
    at = _app(app_test)
    assert any(c.value == "Time source: server clock (demo mode, no chain is configured)" for c in at.sidebar.caption)
    [s for s in at.selectbox if s.label == "Patient DID (Identity Pointer)"][0].set_value(patient).run()
    [m for m in at.multiselect if m.label.startswith("Data Access Scope")][0].set_value(["Observation", "Medication"]).run()
    at = _click(at, "Initial Consent")
    assert not at.error and any("created and logged" in s.value for s in at.success)
    (cid,) = set(consent_db.CONSENTS) - before
    stored = _stored(cid)
    assert stored["guardian_dids"] == G and stored["requester_did"] == CLINICIAN and stored["threshold"] == 2
    assert stored["commitment"] and stored["commitment_opening"] and not stored["token_id"] and not stored["signatures"]

    # ---- Guardian: the first approval, and a request before the threshold ----
    at = _click(_guardian(app_test, cid, "did:parent:A"), "Sign Consent via VC")
    assert any("signature over the consent commitment verified" in s.value and s.value.endswith("Multi-sig: 1/2") for s in at.success)
    assert not _stored(cid)["token_id"]
    at = _click(_clinician(app_test, cid, scope=["Observation"]), "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VA, VL. Consent state: PENDING_SIGNATURE." + RECORDED for e in at.error)
    early = _rows(cid, "DATA_ACCESS")[-1]
    assert (early["result"], early["metadata"]["deny_code"], early["metadata"]["failed_checks"]) == ("DENIED", None, ["VA", "VL"])

    # ---- Guardian: the same guardian again, then the second guardian ----
    at = _click(_guardian(app_test, cid, "did:parent:A"), "Sign Consent via VC")
    assert any(w.value.startswith("This guardian has already signed this consent") for w in at.warning)
    assert _stored(cid)["signatures"] == ["did:parent:A"] and not _stored(cid)["token_id"]
    at = _click(_guardian(app_test, cid, "did:parent:B"), "Sign Consent via VC")
    assert any("[SBT MINTED - LOCAL LEDGER]" in m.value for m in at.markdown)
    stored = _stored(cid)
    assert stored["signatures"] == G and stored["token_id"] == f"SBT-LOCAL-{cid[:8]}" and not stored["token_address"]
    assert [e["metadata"]["version"] for e in _rows(cid, "SIGN_CONSENT")] == [2, 2]          # both over the commitment
    vault = data_vault.default_vault()
    assert vault.modules(cid) == ["Medication", "Observation"] and len(vault.key_store.key_ids(cid)) == 2

    # ---- Clinician: the allowed request, and three refused ones ----
    at = _click(_clinician(app_test, cid, scope=["Observation"]), "Request Data Access")
    assert any(s.value == "Cryptographic Verification Successful — Access Granted." for s in at.success)
    assert any("demo mode: checked locally, not on chain" in c.value for c in at.caption)
    assert any("(server clock, demo mode). Released from the consent-bound encrypted copy: Observation." in c.value for c in at.caption)
    assert not any("VERIFIED ON CHAIN" in m.value for m in at.markdown)
    assert [e.label for e in at.expander if e.label in ("OBSERVATION", "MEDICATION")] == ["OBSERVATION"]
    check, granted = _rows(cid)[-2:]
    m = granted["metadata"]
    assert (check["action"], check["result"], granted["action"], granted["result"]) == ("STATE_CHECK", "ACTIVE", "DATA_ACCESS", "GRANTED")
    assert (granted["actor_did"], granted["scope"], granted["purpose"]) == (CLINICIAN, ["Observation"], "Treatment")
    assert m["modules_released"] == ["Observation"] and m["time_source"] == SERVER_CLOCK and m["deny_code"] is None
    assert all(m["decision_matrix"][name] is True for name in ("VI", "VA", "VP", "VT", "VL", "ALLOW"))
    assert m["zk_proof_verified"] is True and m["proof_mode"] and "tx_hash" not in m["proof_reference"]

    at = _click(_clinician(app_test, cid, scope=["Observation", "Procedure"]), "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VP. Deny code: OUT-OF-SCOPE." + RECORDED for e in at.error)
    at = _click(_clinician(app_test, cid), "Request Data Access")                            # no module chosen
    assert any(e.value == "Access Denied. Failed checks: VP. Deny code: OUT-OF-SCOPE." + RECORDED for e in at.error)
    at = _click(_clinician(app_test, cid, requester=REGISTRAR, scope=["Observation"]), "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VI." + RECORDED for e in at.error)
    assert [e["metadata"]["modules_released"] for e in _rows(cid, "DATA_ACCESS")[-3:]] == [[], [], []]

    # ---- Patient: the revocation, and the request that follows ----
    at = _app(app_test)
    [s for s in at.selectbox if s.label == "Patient DID (Identity Pointer)"][0].set_value(patient).run()
    at = _click(at, key=f"rv_{cid}")
    assert any(s.value == "Consent revoked (local ledger)." for s in at.success)
    assert any(i.value == "Consent-bound copy deleted: Medication, Observation. Keys destroyed: 2. "
               f"Recipients notified: {CLINICIAN}." for i in at.info)
    revoke = _rows(cid, "REVOKE_CONSENT")[-1]
    assert revoke["result"] == "SUCCESS" and revoke["metadata"]["onchain"]["status"] == "NOT_APPLICABLE"
    assert revoke["metadata"]["complete"] is True and revoke["metadata"]["time_source"] == SERVER_CLOCK
    assert not vault.has_copy(cid) and vault.key_store.key_ids(cid) == {}
    stored = _stored(cid)
    assert stored["revoked"] and not stored["commitment_opening"] and not stored["token_id"]
    assert [n["consent_id"] for n in notification_service.inbox(CLINICIAN)].count(cid) == 1
    assert not [n for n in notification_service.inbox(REGISTRAR) if n["consent_id"] == cid]      # he received nothing

    at = _clinician(app_test, cid, scope=["Observation"])
    assert any(e.label.startswith("Withdrawal notices for this clinician") for e in at.expander)
    at = _click(at, "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VL. Deny code: REVOKED. Consent state: REVOKED." + RECORDED for e in at.error)
    assert not [e for e in at.expander if e.label in ("OBSERVATION", "MEDICATION")]
    at = _click(_guardian(app_test, cid, "did:parent:A"), "Revoke Consent (as guardian)")    # the second revocation
    assert any(i.value == "This consent is already revoked." for i in at.info)
    assert len([e for e in _rows(cid, "REVOKE_CONSENT") if e["result"] == "SUCCESS" and e["metadata"]["revocation"] == "REVOKED"]) == 1

    # ---- the ledger of the consent, as the screens wrote it ----
    rows = _rows(cid)
    assert [e["action"] for e in rows[:2]] == ["CREATE_CONSENT", "IDENTITY_VERIFICATION"]
    assert [(e["result"], e["metadata"]["deny_code"]) for e in rows if e["action"] == "DATA_ACCESS"] == [
        ("DENIED", None), ("GRANTED", None), ("DENIED", "OUT-OF-SCOPE"), ("DENIED", "OUT-OF-SCOPE"), ("DENIED", None),
        ("DENIED", "REVOKED")]
    assert len(_rows(cid, "STATE_CHECK")) == 6 + 2                    # one for each request and one for each revocation request
    assert all(code in NINE for e in rows for code in _code_fields(e))
    assert all(not e.get("tx_hash") and not e.get("block_number") and not e.get("onchain") for e in rows)
    named = [source for e in rows for source in _time_sources(e)]
    assert named and set(named) == {SERVER_CLOCK}                     # demo mode keeps the server clock and says so
    assert all(_time_sources(e) for e in rows if e["action"] in ("STATE_CHECK", "DATA_ACCESS", "SIGN_CONSENT", "REVOKE_CONSENT"))

    # ---- Auditor ----
    at = _app(app_test, "Auditor")
    [s for s in at.selectbox if s.label == "Select Consent to Audit"][0].set_value(cid).run()
    assert not at.exception
    shown = at.dataframe[0].value
    assert list(shown["action"]) == [e["action"] for e in rows]
    assert set(shown["actor_role"]) >= {"Patient", "Guardian", "Clinician"} and "Doctor" not in set(shown["actor_role"])


def test_withdrawal_notices_are_shown_to_a_requester_with_a_valid_credential_only(app_test, monkeypatch):
    from test_refusals_on_screens import _consent, _forged, _source
    from services import notification_service, request_service, revocation_service
    c = _consent(patient="did:patient:notices")
    assert request_service.submit_request(c, CLINICIAN, ["Observation"], "Treatment", "AU", source=_source)["outcome"] == "GRANTED"
    signature, _ = revocation_service.sign_revocation(c.patient_did, c.consent_id)
    done = revocation_service.revoke(c, c.patient_did, signature=signature, onchain_revoke=revocation_service.NO_CHAIN)
    assert done["result"] == "REVOKED" and done["recipients"] == [CLINICIAN]
    assert [n for n in notification_service.inbox(CLINICIAN) if n["consent_id"] == c.consent_id]
    at = _clinician(app_test, c.consent_id)
    assert any(e.label.startswith("Withdrawal notices for this clinician") for e in at.expander)
    # the same identifier, presented with a credential that the issuer did not sign: the notices stay closed
    _forged(monkeypatch, CLINICIAN, "doctor")
    at = _clinician(app_test, c.consent_id)
    assert any(w.value.startswith("No valid clinician credential for this DID") for w in at.warning)
    assert not any(e.label.startswith("Withdrawal notices") for e in at.expander)
    assert c.consent_id not in " ".join(str(x.value) for x in list(at.caption) + list(at.markdown) if "withdrawn" in str(x.value))
