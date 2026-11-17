"""The issuance path as the running application performs it (thesis Chapter 5), with Streamlit's test runner (no browser).

A1 the guardian is verified with Algorithm 5.1 before an approval is accepted, and a refused credential is recorded.
A2 the approval is an EIP-712 signature over the consent commitment c, not over the consent identifier.
A3 the threshold N decides activation: the N-th distinct valid approval from a member of G reaches it.
A4 the mint is the mint of ConsentSBTv4: a per-consent address and the commitment, nothing else, as a background job.
E  the deployment command deploys the four contracts, reads them back and writes their addresses into the env file.

The chain is an in-memory EVM with the real bytecode of blockchain/abi (no network, no Sepolia). The key of the owner is
derived from a label in this file: it is a test key and holds nothing. Every test that revokes a credential reads and
writes its own status list file."""
import json, os, threading
from web3.logs import DISCARD
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_KEY_LABEL = "halah issuance wiring test owner"            # the owner key is derived from this label (not a secret)
PATIENT = "did:patient:x"
CLINICIAN = "did:hospital:001"


# ---- fixtures and helpers ----------------------------------------------------------------------------------------------

@pytest.fixture()
def app_test(monkeypatch):
    try:
        from streamlit.testing.v1 import AppTest
    except Exception:
        pytest.skip("streamlit testing API not available")
    monkeypatch.chdir(ROOT)
    return AppTest


@pytest.fixture()
def anchor_calls(monkeypatch):
    from blockchain import onchain_ui
    calls = []
    monkeypatch.setattr(onchain_ui, "render_onchain_anchor_async", lambda c, a, d: calls.append(c.consent_id))   # no chain is contacted
    return calls


@pytest.fixture()
def status_store(tmp_path, monkeypatch):
    path = tmp_path / "credential_status.json"
    monkeypatch.setenv("HALAH_STATUS_LIST_PATH", str(path))        # a revocation made in one test reaches no other
    return path


@pytest.fixture(scope="module")
def base():
    """One in-memory chain for the module, with a funded test key and the four contracts deployed from it."""
    pytest.importorskip("eth_tester", reason="eth-tester not installed")
    from web3 import Web3, EthereumTesterProvider
    from blockchain import contract_v4 as v4, deploy_v4
    w3 = Web3(EthereumTesterProvider())
    key = Web3.keccak(text=TEST_KEY_LABEL)
    signer = w3.eth.account.from_key(key).address
    w3.eth.send_transaction({"from": w3.eth.accounts[0], "to": signer, "value": 10 ** 19, "gas": 21000})
    stack = {}
    for name, k in deploy_v4.ORDER:
        args = {"token": ("poseidon",), "verifier": ("groth16", "token")}.get(k, ())
        stack[k], _ = v4.deploy_contract(w3, key, name, *[stack[x] for x in args])
    return SimpleNamespace(w3=w3, Web3=Web3, v4=v4, deploy=deploy_v4, tester=w3.provider.ethereum_tester, key=key,
                           key_hex=Web3.to_hex(key), signer=signer, stack=stack, chain_id=w3.eth.chain_id)


@pytest.fixture()
def chain(base, monkeypatch):
    """The chain in its fresh state: whatever a test does is undone after it. The expected chain is this one."""
    monkeypatch.setenv("CHAIN_ID", str(base.chain_id))
    snapshot = base.tester.take_snapshot()
    yield base
    base.tester.revert_to_snapshot(snapshot)


@pytest.fixture()
def onchain(chain, monkeypatch):
    """The application in on-chain mode against the in-memory chain: the settings name the deployed contracts and the
    two client factories of the adapter give clients on that chain. The sidebar status is read once."""
    from blockchain import onchain_ui
    from services import blockchain_service as bc
    monkeypatch.setenv("CONTRACT_V4_ADDRESS", chain.stack["token"])
    monkeypatch.setenv("VERIFIER_ADDRESS", chain.stack["verifier"])
    monkeypatch.setenv("PRIVATE_KEY", chain.key_hex)
    monkeypatch.setattr(bc, "token_client", lambda read_only=False: chain.v4.ConsentContractV4(
        w3=chain.w3, address=chain.stack["token"], private_key=None if read_only else chain.key, read_only=read_only))
    monkeypatch.setattr(bc, "verifier_client", lambda read_only=False: chain.v4.DecisionVerifierContract(
        w3=chain.w3, address=chain.stack["verifier"], private_key=None if read_only else chain.key, read_only=read_only))
    status = bc.chain_status()
    monkeypatch.setattr(onchain_ui, "_cached_status", lambda: status)
    chain.status, chain.token = status, bc.token_client(read_only=True)
    return chain


def _consent(guardians, threshold=2, commit=True, patient=PATIENT):
    from database import consent_db
    from services import commitment_service
    from services.consent_service import create_consent
    c = create_consent(patient, CLINICIAN, guardians, ["Observation"], "Treatment",
                       (datetime.now() - timedelta(days=1)).isoformat(), (datetime.now() + timedelta(days=30)).isoformat(),
                       threshold=threshold)
    if commit:
        commitment_service.commit_consent(c)                         # as the patient form does
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


def _wait_for_anchor(cid):
    for t in threading.enumerate():
        if t.name == f"anchor-{cid[:8]}":
            t.join(timeout=60)


def _decision(c, requester=CLINICIAN):
    """The decision as the request screen takes it: the approval check that fits the record."""
    from services import identity_service as ids
    from services.access_service import decision_matrix
    return decision_matrix(c, "AU", verify_sig=ids.approval_check(c), verify_did=ids.verify_identity, requester_did=requester,
                           request_purpose="Treatment", request_scope=["Observation"], va_approvals_only=True)


# ---- A1: Algorithm 5.1 before an approval ----------------------------------------------------------------------------

def test_guardian_with_a_revoked_credential_is_refused_and_recorded(app_test, anchor_calls, status_store):
    from services import credential_status
    c = _consent(["did:parent:A", "did:parent:D"])
    credential_status.revoke_credential("did:parent:D")              # the issuer publishes the next status list
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:D")
    errors = [e.value for e in at.error]
    assert any("Guardian credential is not valid (Status_valid: the credential was revoked by its issuer)" in e for e in errors)
    assert not any("CREDENTIAL_REVOKED" in e for e in errors)        # the screen shows words, the ledger the reason code
    rows = _rows(c.consent_id, "SIGN_CONSENT")
    assert len(rows) == 1 and rows[0]["result"] == "REJECTED" and rows[0]["actor_did"] == "did:parent:D"
    assert rows[0]["metadata"]["reason"] == "CREDENTIAL_REVOKED"
    checks = rows[0]["metadata"]["credential_checks"]
    assert checks["Status_valid"] is False and checks["Sig_VC"] is True and checks["DID_resolved"] is True
    assert not _rows(c.consent_id, "IDENTITY_VERIFICATION")           # evidence is recorded for a valid verification only
    stored = _stored(c.consent_id)
    assert stored["signatures"] == [] and not stored["signature_data"] and not stored["token_id"] and not anchor_calls
    at = _approve(at, "did:parent:A")                                 # the other guardian is not touched by it
    assert not at.error and any("Multi-sig: 1/2" in s.value for s in at.success)


def test_guardian_whose_credential_carries_another_role_is_refused(app_test, anchor_calls):
    c = _consent(["did:parent:A", "did:hospital:002"])               # a clinician named as a guardian
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:hospital:002")
    assert any("Role_match: the credential does not carry the role this step requires" in e.value for e in at.error)
    rows = _rows(c.consent_id, "SIGN_CONSENT")
    assert [r["result"] for r in rows] == ["REJECTED"] and rows[0]["metadata"]["reason"] == "AUTHORITY_MISMATCH"
    assert _stored(c.consent_id)["signatures"] == []


def test_accepted_approval_records_the_identity_verification_first(app_test, anchor_calls):
    from database import audit_db
    c = _consent(["did:parent:A", "did:parent:B"])
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    assert any("Guardian identity and credential verified" in s.value for s in at.success)
    mine = [e for e in audit_db.get() if e["consent_id"] == c.consent_id]
    assert [e["action"] for e in mine] == ["IDENTITY_VERIFICATION", "SIGN_CONSENT"]
    ident, sign = mine
    assert (ident["actor_did"], ident["actor_role"], ident["result"], ident["patient_did"]) == ("did:parent:A", "Guardian", "VALID", PATIENT)
    ev = ident["metadata"]
    assert ev["reason"] == "OK" and ev["required_role"] == "guardian" and ev["claims"]["role"] == "guardian"
    assert all(ev["checks"].values()) and len(ev["checks"]) == 9 and ev["status_sequence"] == 0
    assert sign["metadata"]["credential_id"] == ev["credential_id"] == "urn:halah:vc:guardian:did:parent:A"
    assert sign["metadata"]["credential_issuer"] == ev["issuer"]
    at = _approve(at, "did:parent:A")                                 # the second click writes nothing at all
    assert any("already signed" in w.value for w in at.warning)
    assert len([e for e in audit_db.get() if e["consent_id"] == c.consent_id]) == 2


def test_patient_form_refuses_a_guardian_or_clinician_whose_credential_is_revoked(app_test, status_store):
    from database import consent_db
    from services import credential_status, identity_service as ids

    def create(clinician, guardians):
        at = app_test.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
        at.multiselect[0].set_value(["Observation"]).run()
        [t for t in at.text_input if t.label.startswith("Authorised ") and t.label.endswith(" DID")][0].set_value(clinician).run()
        [t for t in at.text_area if t.label.startswith("Designated Guardian DIDs")][0].set_value(guardians).run()
        [b for b in at.button if b.label == "Initial Consent"][0].click().run()
        return at

    credential_status.revoke_credential("did:parent:D")
    credential_status.revoke_credential("did:hospital:003")
    assert ids.verify_vc("did:parent:D", role="guardian") is True     # the four conditions alone do not see the status list
    before = set(consent_db.CONSENTS)
    at = create(CLINICIAN, "did:parent:A,did:parent:D")
    assert any("valid guardian credential" in e.value for e in at.error)
    at = create("did:hospital:003", "did:parent:A,did:parent:B")
    assert any("The authorised" in e.value and "credential" in e.value for e in at.error)
    assert set(consent_db.CONSENTS) == before                         # nothing was created
    at = create("did:hospital:002", "did:parent:A,did:parent:B")
    assert not at.error and any("created and logged" in s.value for s in at.success)


# ---- A2: the approval is signed over the consent commitment -------------------------------------------------------------

def test_consent_created_in_the_form_carries_a_commitment_and_keeps_its_opening_off_the_ledger(app_test):
    from database import audit_db, consent_db
    from models.consent import Consent
    from services import commitment_service as cs
    before = set(consent_db.CONSENTS)
    at = app_test.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.multiselect[0].set_value(["Observation", "Medication"]).run()
    [b for b in at.button if b.label == "Initial Consent"][0].click().run()
    assert not at.error and any("created and logged" in s.value for s in at.success)
    (cid,) = set(consent_db.CONSENTS) - before
    stored = _stored(cid)
    c = Consent(**stored)
    assert stored["commitment"].startswith("0x") and len(stored["commitment"]) == 66
    assert list(stored["commitment_opening"]) == list(cs.OPENING_FIELDS)
    assert all(isinstance(v, str) and v.isdigit() for v in stored["commitment_opening"].values())
    assert cs.verify_opening(stored["commitment"], stored["commitment_opening"]) is True
    assert cs.opening_matches_consent(c, stored["commitment_opening"]) is True
    assert stored["signatures"] == [] and stored["token_id"] is None and stored["token_address"] is None
    assert any(f"Commitment:</b> {stored['commitment'][:18]}..." in m.value for m in at.markdown)   # shown shortened in the badge
    row = _rows(cid, "CREATE_CONSENT")[0]
    text = json.dumps(row, default=str)
    assert stored["commitment"] not in text and stored["commitment_opening"]["blinding"] not in text
    assert stored["commitment"][2:] not in json.dumps([e for e in audit_db.get() if e["consent_id"] == cid], default=str)


def test_approval_on_the_screen_is_signed_over_the_commitment(app_test, anchor_calls):
    from services import identity_service as ids
    c = _consent(["did:parent:A", "did:parent:B"])
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    assert any("EIP-712 signature over the consent commitment verified" in s.value and "Multi-sig: 1/2" in s.value for s in at.success)
    stored = _stored(c.consent_id)
    entry = stored["signature_data"]["did:parent:A"]
    assert entry["scheme"] == "EIP-712" and entry["version"] == 2 and entry["signer"] == ids.guardian_address("did:parent:A")
    assert stored["commitment"] == c.commitment                       # the approval did not change what was committed
    assert ids.verify_signature_v2("did:parent:A", c.consent_id, stored["commitment"], entry["signature"]) is True
    assert ids.verify_signature("did:parent:A", c.consent_id, entry["signature"]) is False      # not the older approval
    assert ids.verify_signature_v2("did:parent:A", c.consent_id, int(stored["commitment"], 16) + 1, entry["signature"]) is False
    assert ids.verify_signature_v2("did:parent:B", c.consent_id, stored["commitment"], entry["signature"]) is False
    meta = _rows(c.consent_id, "SIGN_CONSENT")[-1]["metadata"]
    assert meta["version"] == 2 and meta["signature"] == entry["signature"] and meta["guardian_address"] == entry["signer"]
    assert meta["signature_count"] == 1 and meta["threshold"] == 2


def test_record_without_a_commitment_is_committed_at_its_first_approval(app_test, anchor_calls):
    from services import commitment_service as cs, identity_service as ids
    c = _consent(["did:parent:A", "did:parent:B"], commit=False)     # made before the commitment existed, no approval yet
    assert _stored(c.consent_id)["commitment"] is None
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    stored = _stored(c.consent_id)
    assert not at.error and cs.verify_opening(stored["commitment"], stored["commitment_opening"]) is True
    assert stored["signature_data"]["did:parent:A"]["version"] == 2
    at = _approve(at, "did:parent:B")
    assert _stored(c.consent_id)["commitment"] == stored["commitment"]                       # committed once
    sig = _stored(c.consent_id)["signature_data"]["did:parent:B"]["signature"]
    assert ids.verify_signature_v2("did:parent:B", c.consent_id, stored["commitment"], sig) is True


def test_old_record_with_approvals_over_the_identifier_keeps_that_form(app_test, anchor_calls):
    from database import consent_db
    from services import identity_service as ids
    c = _consent(["did:parent:A", "did:parent:B"], commit=False)
    sig, addr = ids.sign_consent("did:parent:A", c.consent_id)       # an approval of the earlier build
    c.signatures.append("did:parent:A"); c.signature_data["did:parent:A"] = {"signer": addr, "signature": sig}
    consent_db.save(c)
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:B")
    assert not at.error and any("Multi-sig: 2/2" in s.value and "commitment" not in s.value for s in at.success)
    stored = _stored(c.consent_id)
    entry = stored["signature_data"]["did:parent:B"]
    assert stored["commitment"] is None and "version" not in entry
    assert ids.verify_signature("did:parent:B", c.consent_id, entry["signature"]) is True
    assert "version" not in _rows(c.consent_id, "SIGN_CONSENT")[-1]["metadata"]
    m = _decision(consent_db.get(c.consent_id))
    assert m["VI"] is True and m["ALLOW"] is True                     # the old record still opens


def test_guardian_with_a_registered_wallet_address_is_not_approved_by_the_derived_key(app_test, anchor_calls):
    from database import consent_db
    from eth_account import Account
    from eth_utils import keccak
    from services import identity_service as ids
    c = _consent(["did:parent:A", "did:parent:B"])
    wallet = Account.from_key(keccak(text="halah issuance wiring test wallet of guardian A"))   # a key the server does not hold
    c.guardian_addresses = {"did:parent:A": wallet.address}
    consent_db.save(c)
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    assert any("EIP-712 signature verification failed" in e.value for e in at.error)
    stored = _stored(c.consent_id)
    assert stored["signatures"] == [] and not stored["signature_data"] and not _rows(c.consent_id, "SIGN_CONSENT")
    sig, addr = ids.sign_consent_v2("did:parent:A", c.consent_id, c.commitment, signer=wallet)   # what the wallet itself would sign
    assert addr == wallet.address and ids.verify_signature_v2("did:parent:A", c.consent_id, c.commitment, sig, address=wallet.address) is True
    at = _approve(at, "did:parent:B")                                 # a guardian without a registered address is not affected
    assert not at.error and any("Multi-sig: 1/2" in s.value for s in at.success)


def test_A2_screen_approval_replayed_into_another_consent_fails_VI(app_test, anchor_calls):
    from database import consent_db
    first, second = _consent(["did:parent:A", "did:parent:B"]), _consent(["did:parent:A", "did:parent:B"])
    for c in (first, second):
        at = _guardian_screen(app_test, c.consent_id)
        _approve(_approve(at, "did:parent:A"), "did:parent:B")
    first, second = consent_db.get(first.consent_id), consent_db.get(second.consent_id)
    assert _decision(first)["ALLOW"] is True and _decision(second)["ALLOW"] is True
    own = second.signature_data["did:parent:A"]
    second.signature_data["did:parent:A"] = dict(first.signature_data["did:parent:A"])       # the approval of the other consent
    m = _decision(second)
    assert m["VI"] is False and m["ALLOW"] is False and m["VA"] is True
    assert not [code for code in m["DENY"] if code in ("OUT-OF-SCOPE", "PURPOSE-MISMATCH", "CONTEXT-MISMATCH", "PRE-VALIDITY",
                                                         "POST-VALIDITY", "AWAITING-TRIGGER", "TRANSITION-PENDING", "EXPIRED", "REVOKED")]
    second.signature_data["did:parent:A"] = own
    assert _decision(second)["ALLOW"] is True


def test_approval_check_fits_the_record():
    from models.consent import Consent
    from services import commitment_service as cs, identity_service as ids
    c = Consent("fit-1", PATIENT, CLINICIAN, ["did:parent:A"], "Treatment", ["Observation"], 1,
                start_date=(datetime.now() - timedelta(days=1)).isoformat(), expiry_date=(datetime.now() + timedelta(days=30)).isoformat())
    old, _ = ids.sign_consent("did:parent:A", c.consent_id)
    c.signature_data["did:parent:A"] = {"signature": old}
    assert ids.approval_check(c)("did:parent:A", c.consent_id, old) is True                  # no commitment: the older approval
    cs.commit_consent(c)
    new, addr = ids.sign_consent_v2("did:parent:A", c.consent_id, c.commitment)
    assert ids.approval_check(c)("did:parent:A", c.consent_id, old) is False                 # with a commitment only an approval over it
    c.signature_data["did:parent:A"] = {"scheme": "EIP-712", "version": 2, "signer": addr, "signature": new}
    assert ids.approval_check(c)("did:parent:A", c.consent_id, new) is True
    assert ids.approval_check(c)("did:parent:A", "another-consent", new) is False
    c.commitment = None                                               # the commitment is gone and the consent is not revoked
    assert ids.approval_check(c)("did:parent:A", c.consent_id, new) is False
    c.signature_data["did:parent:A"] = {"signer": addr, "signature": new}                    # passed off as an older approval
    assert ids.approval_check(c)("did:parent:A", c.consent_id, new) is False
    c.signature_data["did:parent:A"] = {"scheme": "EIP-712", "version": 2, "signer": addr, "signature": new}
    c.revoked = True                                                  # a revocation deletes the commitment: nothing is verified again
    assert ids.approval_check(c)("did:parent:A", c.consent_id, new) is True
    assert ids.approval_check(c)("did:parent:Z", c.consent_id, new) is False                 # only for an approval that is recorded


def test_request_screen_accepts_approvals_made_over_the_commitment(app_test, anchor_calls):
    c = _consent(["did:parent:A", "did:parent:B"])
    _approve(_approve(_guardian_screen(app_test, c.consent_id), "did:parent:A"), "did:parent:B")
    at = app_test.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value(at.sidebar.selectbox[0].options[2]).run()               # the role of the requester
    [t for t in at.text_input if t.label == "Enter Authorised Consent ID"][0].set_value(c.consent_id).run()
    [t for t in at.text_input if t.label.endswith("DID (requester)")][0].set_value(CLINICIAN).run()
    assert not any("(VI) failed" in e.value for e in at.error)
    assert any(s.value == "Authorised Data Scope" for s in at.subheader)


# ---- A3: the threshold N decides activation ----------------------------------------------------------------------------

def test_two_of_three_is_issued_at_the_second_approval_and_the_third_mints_nothing(app_test, anchor_calls):
    c = _consent(["did:parent:A", "did:parent:B", "did:parent:C"], threshold=2)
    state_lines = lambda at: [i.value for i in at.info if i.value.startswith("Found consent for Patient")]
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:B")
    assert any("Multi-sig: 1/2" in s.value for s in at.success)
    assert state_lines(at) == [f"Found consent for Patient: `{PATIENT}` (state: PENDING_SIGNATURE)"]
    assert not _rows(c.consent_id, "MINT_SBT") and not _stored(c.consent_id)["token_id"] and anchor_calls == []
    from database import consent_db
    m = _decision(consent_db.get(c.consent_id))                       # a request before the threshold
    assert (m["VI"], m["VA"], m["VL"], m["ALLOW"]) == (True, False, False, False)
    assert set(m["DENY"]) == {"APPROVAL-PENDING"}                    # no deny code of the nine applies
    at = _approve(at, "did:parent:C")
    assert any("Multi-sig: 2/2" in s.value for s in at.success)
    assert state_lines(at) == [f"Found consent for Patient: `{PATIENT}` (state: ACTIVE)"]     # the state the click left
    assert len(_rows(c.consent_id, "MINT_SBT")) == 1 and anchor_calls == [c.consent_id]
    assert _stored(c.consent_id)["token_id"] == f"SBT-LOCAL-{c.consent_id[:8]}"
    assert _decision(consent_db.get(c.consent_id))["ALLOW"] is True
    at = _approve(at, "did:parent:A")                                 # the third guardian approves after the threshold
    assert not at.error and any("Multi-sig: 3/2" in s.value for s in at.success)
    assert state_lines(at) == [f"Found consent for Patient: `{PATIENT}` (state: ACTIVE)"]
    assert any("The threshold was reached before this approval" in x.value for x in at.caption)
    stored = _stored(c.consent_id)
    assert stored["signatures"] == ["did:parent:B", "did:parent:C", "did:parent:A"]
    assert stored["signature_data"]["did:parent:A"]["version"] == 2
    assert [r["metadata"]["signature_count"] for r in _rows(c.consent_id, "SIGN_CONSENT")] == [1, 2, 3]
    assert len(_rows(c.consent_id, "MINT_SBT")) == 1 and anchor_calls == [c.consent_id]       # one token, one anchoring
    assert stored["token_id"] == f"SBT-LOCAL-{c.consent_id[:8]}"


def test_three_of_five_stays_pending_at_two_and_is_issued_at_the_third(app_test, anchor_calls):
    guardians = ["did:parent:A", "did:parent:B", "did:parent:C", "did:parent:D", "did:parent:E"]
    c = _consent(guardians, threshold=3)
    at = _guardian_screen(app_test, c.consent_id)
    for n, did in enumerate(["did:parent:E", "did:parent:A"], start=1):
        at = _approve(at, did)
        assert not at.error and any(f"Multi-sig: {n}/3" in s.value for s in at.success)
        assert not _stored(c.consent_id)["token_id"] and anchor_calls == []
    at = _approve(at, "did:parent:C")
    assert any("Multi-sig: 3/3" in s.value for s in at.success)
    stored = _stored(c.consent_id)
    assert stored["signatures"] == ["did:parent:E", "did:parent:A", "did:parent:C"] and stored["threshold"] == 3
    assert stored["token_id"] == f"SBT-LOCAL-{c.consent_id[:8]}" and anchor_calls == [c.consent_id]
    assert len(_rows(c.consent_id, "MINT_SBT")) == 1 and len(_rows(c.consent_id, "IDENTITY_VERIFICATION")) == 3


def test_no_token_is_recorded_for_a_revoked_consent_that_reaches_its_threshold(app_test, anchor_calls):
    from database import consent_db
    c = _consent(["did:parent:A", "did:parent:B"])
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    consent_db.revoke(c.consent_id)                                   # revoked while it waits for the second approval
    before = _stored(c.consent_id)
    rows = len(_rows(c.consent_id, "SIGN_CONSENT")), len(_rows(c.consent_id, "IDENTITY_VERIFICATION"))
    at = _approve(at, "did:parent:B")
    # an approval is not added to a revoked consent: nothing is signed, committed or recorded
    assert [w.value for w in at.warning] == ["This consent is revoked: an approval cannot be added."]
    assert not any("Multi-sig" in s.value for s in at.success) and not at.error
    assert any(i.value == f"Found consent for Patient: `{PATIENT}` (state: REVOKED)" for i in at.info)
    stored = _stored(c.consent_id)
    assert stored["signatures"] == ["did:parent:A"] and list(stored["signature_data"]) == ["did:parent:A"]
    assert all(stored[name] == before[name] for name in ("signatures", "signature_data", "commitment", "commitment_opening"))
    assert (len(_rows(c.consent_id, "SIGN_CONSENT")), len(_rows(c.consent_id, "IDENTITY_VERIFICATION"))) == rows == (1, 1)
    assert not _rows(c.consent_id, "MINT_SBT") and not _stored(c.consent_id)["token_id"] and anchor_calls == []


def test_consent_revoked_before_any_approval_is_not_committed_again_by_a_click_on_sign(app_test, anchor_calls):
    from database import consent_db
    from services import revocation_service
    c = _consent(["did:parent:A", "did:parent:B"])                    # committed by the form, no approval yet
    assert _stored(c.consent_id)["commitment"] and _stored(c.consent_id)["commitment_opening"]
    at = _guardian_screen(app_test, c.consent_id)
    [s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0].set_value("did:parent:A").run()
    [b for b in at.button if b.label == "Revoke Consent (as guardian)"][0].click().run()
    assert any(s.value.startswith("Consent revoked by guardian did:parent:A.") for s in at.success)
    revoked = _stored(c.consent_id)
    assert revoked["revoked"] and not revoked["commitment"] and not revoked["commitment_opening"]   # deleted with the revocation
    assert _rows(c.consent_id, "REVOKE_CONSENT")[-1]["metadata"]["link"]["status"] == "DELETED"
    # the other guardian clicks Sign on the revoked consent
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:B")
    assert [w.value for w in at.warning] == ["This consent is revoked: an approval cannot be added."]
    assert not at.success and not at.error
    stored = _stored(c.consent_id)
    assert not stored["commitment"] and not stored["commitment_opening"] and stored["signatures"] == [] and not stored["signature_data"]
    assert not stored["token_id"] and anchor_calls == []
    assert not _rows(c.consent_id, "SIGN_CONSENT") and not _rows(c.consent_id, "IDENTITY_VERIFICATION") and not _rows(c.consent_id, "MINT_SBT")
    assert revocation_service.revocation_evidence(consent_db.get(c.consent_id))["link_deleted"] is True


# ---- A4: the mint of ConsentSBTv4 -----------------------------------------------------------------------------------

def test_second_approval_mints_on_consentsbtv4_with_a_per_consent_address_and_the_commitment_only(app_test, onchain):
    from blockchain.contract import did_to_address
    c = _consent(["did:parent:A", "did:parent:B"], patient="did:patient:layan")
    at = _guardian_screen(app_test, c.consent_id)
    assert any(f"chain {onchain.chain_id} - block" in s.value for s in at.sidebar.success)
    assert any(x.value == f"Consent contract: ConsentSBTv4 {onchain.stack['token']}" for x in at.sidebar.caption)
    assert any(x.value == f"Decision verifier: {onchain.stack['verifier']}" for x in at.sidebar.caption)
    at = _approve(at, "did:parent:A")
    assert onchain.token.consent_count() == 0 and not _rows(c.consent_id, "ONCHAIN_MINT")     # below the threshold nothing is sent
    at = _approve(at, "did:parent:B")
    assert any("Anchoring on" in i.value for i in at.info)            # the mint is a background job
    assert len(_rows(c.consent_id, "MINT_SBT")) == 1
    _wait_for_anchor(c.consent_id)

    (row,) = _rows(c.consent_id, "ONCHAIN_MINT")
    assert row["result"] == "SUCCESS" and row["onchain"] is True and row["metadata"]["token_id"] == 1
    stored = _stored(c.consent_id)
    assert stored["token_id"] == "SBT-1" and onchain.Web3.is_checksum_address(stored["token_address"])
    assert onchain.token.consent_of(1) == {"commitment": int(stored["commitment"], 16), "revoked": False}
    assert onchain.token.check_valid(1) is True and onchain.token.token_of_commitment(stored["commitment"]) == 1
    assert onchain.token.contract.functions.ownerOf(1).call() == stored["token_address"]
    # the address is per consent: neither the address ConsentSBTv3 gave the patient nor that of any participant
    people = {did_to_address(d) for d in ("did:patient:layan", CLINICIAN, "did:parent:A", "did:parent:B")}
    assert stored["token_address"] not in people
    # the transaction carries the selector, the address and the commitment, and nothing else
    tx = onchain.w3.eth.get_transaction(row["tx_hash"])
    fn, args = onchain.token.contract.decode_function_input(tx["input"])
    assert fn.fn_name == "mintConsent" and args == {"to": stored["token_address"], "commitment": int(stored["commitment"], 16)}
    assert len(bytes(tx["input"])) == 4 + 32 + 32 and tx["to"] == onchain.stack["token"] and tx["from"] == onchain.signer
    assert not any(bytes.fromhex(a[2:]) in bytes(tx["input"]) for a in people)
    receipt = onchain.w3.eth.get_transaction_receipt(row["tx_hash"])
    assert receipt["blockNumber"] == row["block_number"] and row["metadata"]["gas_used"] == receipt["gasUsed"]
    (issued,) = onchain.token.contract.events.ConsentIssued().process_receipt(receipt, errors=DISCARD)
    assert dict(issued["args"]) == {"tokenId": 1, "commitment": int(stored["commitment"], 16)}
    # the opening stays in the record and reaches neither the chain nor the ledger
    assert stored["commitment_opening"]["blinding"] not in json.dumps(_rows(c.consent_id, "ONCHAIN_MINT") + _rows(c.consent_id, "MINT_SBT"))
    assert stored["token_address"] not in json.dumps(row)

    at = _guardian_screen(app_test, c.consent_id)                     # the screen after the confirmation
    assert any(f"Already anchored on chain {onchain.chain_id} - token #1" in s.value for s in at.success)
    assert any(f"Per-consent address: {stored['token_address']}." in x.value for x in at.caption)
    # the transaction of the mint is named with its block and its gas, from the row of the ledger
    assert any(x.value == f"Minted in block {receipt['blockNumber']} (tx {row['tx_hash']}) - gas used {receipt['gasUsed']}."
               for x in at.caption)
    assert not any("Etherscan" in m.value for m in at.markdown)       # the in-memory chain has no public explorer
    from database import consent_db
    assert _decision(consent_db.get(c.consent_id))["ALLOW"] is True


def test_two_consents_of_one_patient_sit_at_unrelated_addresses(onchain):
    from services import blockchain_service as bc
    first, second = _consent(["did:parent:A"], threshold=1), _consent(["did:parent:A"], threshold=1)
    r1, r2 = bc.mint_consent(first), bc.mint_consent(second)
    assert (r1["status"], r1["token_id"], r2["token_id"], r1["version"]) == (1, 1, 2, 4)
    assert first.token_address == r1["token_address"] != second.token_address == r2["token_address"]
    assert bc.has_chain_token(first) is False                         # the caller records the token number (anchor_service does)
    first.token_id = "SBT-1"
    assert bc.has_chain_token(first) is True
    plain = _consent(["did:parent:A"], threshold=1, commit=False)
    with pytest.raises(RuntimeError, match="no commitment"):
        bc.mint_consent(plain)
    assert onchain.token.consent_count() == 2
    with pytest.raises(Exception, match="commitment already issued"):  # the same commitment is not issued twice
        bc.mint_consent_v4(first)
    assert onchain.token.consent_count() == 2


def test_mint_route_stays_on_consentsbtv3_without_the_new_address(monkeypatch):
    from services import blockchain_service as bc
    calls = {}

    class FakeV3:
        def has_v3(self): return True
        def mint_consent_v3(self, p, r, purpose, nb, exp, jur, burn_auth=2):
            calls["v3"] = (p, r, purpose, jur); return {"token_id": 1, "version": 3}
        def revoke(self, tid): return {"status": 1, "token_id": tid}

    class FakeChain:
        ConsentContract = FakeV3
        @staticmethod
        def is_configured(): return True

    class FakeV4:
        def mint_consent(self, to, commitment):
            calls["v4"] = (to, commitment); return {"status": 1, "token_id": 9, "token_address": to, "version": 4}
        def revoke(self, tid):
            calls["v4_revoke"] = tid; return {"status": 1, "token_id": tid}

    monkeypatch.setattr(bc, "chain", FakeChain)
    monkeypatch.setattr(bc, "token_client", lambda read_only=False: FakeV4())
    c = _consent(["did:parent:A"], threshold=1)
    assert bc.v4_enabled() is False and bc.proof_enabled() is False and bc.onchain_enabled() is True
    assert bc.mint_consent(c)["version"] == 3 and calls["v3"] == (c.patient_did, c.requester_did, "Treatment", "AU") and "v4" not in calls
    assert c.token_address is None and bc.revoke(4) == {"status": 1, "token_id": 4}
    c.token_id = "SBT-4"
    assert bc.has_chain_token(c) is False                             # a ConsentSBTv3 token is not a token of the new contract
    with pytest.raises(RuntimeError, match="no token on ConsentSBTv4"):
        bc.revoke_onchain(c)

    monkeypatch.setenv("CONTRACT_V4_ADDRESS", "0x" + "11" * 20)
    assert bc.v4_enabled() is False                                   # the address alone is not enough: the key is needed
    monkeypatch.setenv("PRIVATE_KEY", "0x" + "22" * 32)
    assert bc.v4_enabled() is True and bc.proof_enabled() is False and bc.onchain_enabled() is True
    monkeypatch.setenv("VERIFIER_ADDRESS", "0x" + "33" * 20)
    assert bc.proof_enabled() is True
    c.token_id = None
    r = bc.mint_consent(c)
    assert r["version"] == 4 and calls["v4"] == (c.token_address, c.commitment) and len(calls) == 2
    assert bc.has_chain_token(c) is False
    c.token_id = "SBT-9"
    assert bc.has_chain_token(c) is True and bc.revoke_onchain(c) == {"status": 1, "token_id": 9} and calls["v4_revoke"] == 9
    with pytest.raises(RuntimeError, match="revoke_onchain"):         # a bare token number is never sent to the older contract
        bc.revoke(9)
    old = _consent(["did:parent:A"], threshold=1); old.token_id = "SBT-9"
    assert bc.has_chain_token(old) is False                           # same number, no per-consent address: an older record


def test_chain_status_in_on_chain_mode_has_what_the_sidebar_reads(onchain):
    s = onchain.status
    assert s["mode"] == "onchain" and s["version"] == 4 and s["chain_id"] == onchain.chain_id and s["is_sepolia"] is False
    assert s["contract"] == onchain.stack["token"] and s["contract_has_code"] is True and s["signer_is_owner"] is True
    assert s["signer"] == onchain.signer and s["balance_eth"] > 0 and s["block"] >= 1 and s["verifier"] == onchain.stack["verifier"]
    assert s["consent_count"] == 0 and onchain.key_hex not in json.dumps(s)


def test_sync_finds_a_consentsbtv4_token_by_the_commitment_of_the_record(app_test, onchain):
    from database import audit_db, consent_db
    from services import anchor_service, blockchain_service as bc, identity_service as ids
    never = _consent(["did:parent:A"], threshold=1)
    assert anchor_service.reconcile(never, audit_db, consent_db) == {"status": "none"}
    c = _consent(["did:parent:A", "did:parent:B"])
    for g in c.guardian_dids:
        sig, addr = ids.sign_consent_v2(g, c.consent_id, c.commitment)
        c.signatures.append(g); c.signature_data[g] = {"scheme": "EIP-712", "version": 2, "signer": addr, "signature": sig}
    c.token_id = f"SBT-LOCAL-{c.consent_id[:8]}"; consent_db.save(c)
    # the mint reached the chain and the application stopped before it recorded it
    address, _ = onchain.v4.derive_consent_address(c.patient_did, c.consent_id)
    sent = bc.token_client().mint_consent(address, c.commitment)
    assert sent["status"] == 1 and _stored(c.consent_id)["token_id"].startswith("SBT-LOCAL-")

    at = _guardian_screen(app_test, c.consent_id)
    assert any("reached but NOT anchored" in w.value for w in at.warning)
    [b for b in at.button if b.label.startswith("Sync from")][0].click().run()
    assert any(f"Found on-chain: token #{sent['token_id']} block {sent['block_number']}" in s.value for s in at.success)
    stored = _stored(c.consent_id)
    assert stored["token_id"] == f"SBT-{sent['token_id']}" and stored["token_address"] == address
    (row,) = _rows(c.consent_id, "ONCHAIN_MINT")
    assert row["result"] == "SUCCESS" and row["tx_hash"] == sent["tx_hash"] and row["block_number"] == sent["block_number"]
    assert row["metadata"]["reconciled_from_chain"] is True and row["metadata"]["token_id"] == sent["token_id"]
    assert anchor_service.reconcile(consent_db.get(c.consent_id), audit_db, consent_db)["status"] == "already"
    assert len(_rows(c.consent_id, "ONCHAIN_MINT")) == 1


# ---- E: the deployment command -----------------------------------------------------------------------------------------

def test_deploy_command_deploys_the_four_contracts_and_writes_their_addresses(chain, circuit_build, tmp_path, capsys):
    d, v4, w3 = chain.deploy, chain.v4, chain.w3
    env = tmp_path / "deploy.env"
    kept = "# settings of the older contract\nRPC_URL=http://127.0.0.1:1\nCONTRACT_ADDRESS=0x0EC3617581DEC63A7f2bb162DC14d088916ADc73\nCONTRACT_VERSION=3\n"
    env.write_text(kept)
    blocks = w3.eth.block_number
    out = d.main(["--env-file", str(env)], w3=w3, private_key=chain.key)
    printed = capsys.readouterr().out
    assert out["sent"] == 4 and w3.eth.block_number == blocks + 4 and out["deployer"] == chain.signer
    assert all(len(w3.eth.get_code(out[k])) > 0 for k in ("groth16", "poseidon", "token", "verifier"))
    assert len({out[k] for k in ("groth16", "poseidon", "token", "verifier")}) == 4 and out["token"] != chain.stack["token"]
    # read back from the chain
    token = v4.ConsentContractV4(w3=w3, address=out["token"], private_key=chain.key)
    verifier = v4.DecisionVerifierContract(w3=w3, address=out["verifier"], private_key=chain.key)
    assert token.status()["signer_is_owner"] is True and token.contract.functions.hasher().call() == out["poseidon"]
    assert verifier.status()["proof_verifier"] == out["groth16"] and verifier.status()["consent_token"] == out["token"]
    assert out["read_back"] == {"owner": chain.signer, "hasher": out["poseidon"], "consent_count": 0,
                                "proof_verifier": out["groth16"], "consent_token": out["token"]}
    assert token.mint_consent(v4.derive_consent_address("did:patient:x", "after-deploy")[0], 12345)["token_id"] == 1
    # the env file: the six lines are added and every earlier line is as it was
    text = env.read_text()
    assert text.startswith(kept)
    lines = dict(line.split("=", 1) for line in text[len(kept):].splitlines())
    assert lines == {"CONTRACT_V4_ADDRESS": out["token"], "VERIFIER_ADDRESS": out["verifier"], "POSEIDON_ADDRESS": out["poseidon"],
                     "GROTH16_VERIFIER_ADDRESS": out["groth16"], "CHAIN_ID": str(chain.chain_id),
                     "CONTRACT_V4_DEPLOY_BLOCK": str(out["receipts"]["token"]["block_number"])} == out["env"]
    # every address, transaction and block is printed, and the key is neither printed nor written
    for k in ("groth16", "poseidon", "token", "verifier"):
        assert out[k] in printed and out["receipts"][k]["tx_hash"] in printed and "block %s" % out["receipts"][k]["block_number"] in printed
    assert "Deployer          " + chain.signer in printed and "Gas price" in printed and "Estimated cost" in printed and "READY" in printed
    assert "Verification key  zk/build matches blockchain/abi/HalahDecisionVerifier.json" in printed
    # what was printed is kept beside the env file: the deployer, and each address with its transaction, block and gas
    first = min(r["block_number"] for r in out["receipts"].values())
    assert out["record"] == str(tmp_path / f"deployment_chain{chain.chain_id}_block{first}.txt") and ("Record of this deployment: " + out["record"]) in printed
    record = open(out["record"]).read()
    assert record.startswith("Deployment of 20") and "Deployer          " + chain.signer in record and "READY" in record
    for name, k in d.ORDER:
        r = out["receipts"][k]
        assert f"{name:<24} {out[k]}  tx {r['tx_hash']}  block {r['block_number']}  gas {r['gas_used']:,}" in record
    assert "Total gas         " in record and ("CONTRACT_V4_ADDRESS=" + out["token"]) in record
    for secret in (chain.key_hex, chain.key_hex[2:], chain.key_hex.upper()):
        assert secret not in printed and secret not in text and secret not in json.dumps(out, default=str) and secret not in record
    # a second start does not deploy again by accident
    with pytest.raises(d.DeployError, match="already"):
        d.main(["--env-file", str(env)], w3=w3, private_key=chain.key)
    assert w3.eth.block_number == blocks + 5                           # the one block is the mint above
    again = d.main(["--env-file", str(env), "--force"], w3=w3, private_key=chain.key)
    assert again["token"] != out["token"] and ("CONTRACT_V4_ADDRESS=" + again["token"]) in env.read_text()
    assert env.read_text().count("CONTRACT_V4_ADDRESS=") == 1 and env.read_text().startswith(kept)


def test_deploy_command_reads_the_key_and_the_expected_chain_from_the_env_file(chain, circuit_build, tmp_path, monkeypatch, capsys):
    d = chain.deploy
    env = tmp_path / "own.env"
    env.write_text(f"PRIVATE_KEY={chain.key_hex}\nCHAIN_ID={chain.chain_id}\n")
    monkeypatch.delenv("CHAIN_ID")                                    # the file gives the expected chain
    out = d.main(["--env-file", str(env), "--dry-run"], w3=chain.w3)
    assert out["deployer"] == chain.signer and out["sent"] == 0
    assert env.read_text() == f"PRIVATE_KEY={chain.key_hex}\nCHAIN_ID={chain.chain_id}\n"     # a dry run writes nothing
    assert os.environ.get("PRIVATE_KEY") is None                      # and the file is not loaded into the process
    assert chain.key_hex not in capsys.readouterr().out


def test_deploy_command_stops_with_a_plain_message_before_anything_is_sent(chain, circuit_build, tmp_path, monkeypatch, capsys):
    d, w3 = chain.deploy, chain.w3
    env = tmp_path / "deploy.env"
    blocks = w3.eth.block_number
    with pytest.raises(d.DeployError, match="PRIVATE_KEY is not set"):
        d.main(["--env-file", str(env)], w3=w3)
    with pytest.raises(d.DeployError, match="not a usable key"):
        d.main(["--env-file", str(env)], w3=w3, private_key="0x1234")
    poor = chain.Web3.keccak(text="halah issuance wiring test key without funds")
    with pytest.raises(d.DeployError, match="balance is below twice the estimated cost"):
        d.main(["--env-file", str(env)], w3=w3, private_key=poor)
    monkeypatch.setenv("CHAIN_ID", "11155111")                        # the default: Sepolia is expected
    with pytest.raises(d.DeployError, match=f"chain {chain.chain_id} and chain 11155111 is expected"):
        d.main(["--env-file", str(env)], w3=w3, private_key=chain.key)
    monkeypatch.setenv("CHAIN_ID", str(chain.chain_id))
    out = d.main(["--env-file", str(env), "--dry-run"], w3=w3, private_key=chain.key)
    printed = capsys.readouterr().out
    assert out["sent"] == 0 and "DRY RUN: nothing was sent." in printed and chain.signer in printed
    assert w3.eth.block_number == blocks and not env.exists()         # nothing was mined and nothing was written
    assert [name for name in os.listdir(tmp_path) if name.startswith("deployment_")] == []    # and there is nothing to keep a record of


def test_deploy_command_stops_when_the_verification_key_is_not_the_one_of_the_verifier(chain, circuit_build, tmp_path, monkeypatch):
    d, w3 = chain.deploy, chain.w3
    code = bytes.fromhex(chain.v4.load_artifact("HalahDecisionVerifier")["bytecode"][2:])
    built = d.verification_key_constants()                            # the key of the committed verifier (fixture circuit_build)
    assert len(built) == 30 and d.holds_constants(code, built) is True
    key = {"vk_alpha_1": ["11", "12", "1"], "vk_beta_2": [["13", "14"], ["15", "16"], ["1", "0"]], "vk_gamma_2": [["17", "18"], ["19", "20"], ["1", "0"]],
           "vk_delta_2": [["21", "22"], ["23", "24"], ["1", "0"]], "IC": [[str(2 ** 200 + i), str(2 ** 201 + i), "1"] for i in range(8)]}
    other = tmp_path / "verification_key.json"
    other.write_text(json.dumps(key))
    constants = d.verification_key_constants(str(other))
    assert len(constants) == 30 and d.holds_constants(code, constants) is False and d.holds_constants(code, []) is False
    assert d.verification_key_constants(str(tmp_path / "missing.json")) is None
    monkeypatch.setattr(d, "VERIFICATION_KEY", str(other))            # another build of the circuit lies in zk/build
    blocks = w3.eth.block_number
    with pytest.raises(d.DeployError, match="verification key of zk/build is not the one inside"):
        d.main(["--env-file", str(tmp_path / "deploy.env")], w3=w3, private_key=chain.key)
    with pytest.raises(d.DeployError, match="does not hold the verification key"):
        d.check_deployment(w3, chain.stack, key_constants=constants)
    assert w3.eth.block_number == blocks and not (tmp_path / "deploy.env").exists()


def test_deploy_command_stops_when_zk_build_holds_no_circuit_build(chain, tmp_path, monkeypatch, capsys):
    """zk/build is not in the repository. On a machine without the build no proof can be made for the contracts that
    would be deployed, and a new build would make another key: the command sends nothing and says what to bring."""
    d, w3, s = chain.deploy, chain.w3, chain.stack
    env = tmp_path / "deploy.env"
    monkeypatch.setattr(d, "VERIFICATION_KEY", str(tmp_path / "zk_build" / "halah_decision_verification_key.json"))   # no such file
    blocks = w3.eth.block_number
    given = ["--check", "--poseidon", s["poseidon"], "--token", s["token"], "--groth16", s["groth16"], "--verifier", s["verifier"]]
    for arguments in ([], ["--dry-run"], given):
        with pytest.raises(d.DeployError) as stopped:
            d.main(["--env-file", str(env)] + arguments, w3=w3, private_key=chain.key)
        message = str(stopped.value)
        assert message.startswith("zk/build holds no circuit build: bring zk/build/halah_decision.zkey, ")
        assert "zk/build/halah_decision_js/halah_decision.wasm" in message and "zk/build/halah_decision_verification_key.json" in message
        assert "Do not run zk/build_decision.sh: it makes a new key." in message and message.endswith("Nothing was sent.")
    assert w3.eth.block_number == blocks and os.listdir(tmp_path) == []        # nothing was mined, no env file, no record
    assert "READY" not in capsys.readouterr().out
    # the one option that lets the command go on, for a machine that only deploys
    out = d.main(["--env-file", str(env), "--dry-run", "--without-circuit-build"], w3=w3, private_key=chain.key)
    assert out["sent"] == 0 and "the comparison with the Groth16 verifier is skipped (--without-circuit-build)" in capsys.readouterr().out
    assert d.main(["--env-file", str(env), "--without-circuit-build"] + given, w3=w3, private_key=chain.key)["read_back"]["owner"] == chain.signer
    out = d.main(["--env-file", str(env), "--without-circuit-build", "--force"], w3=w3, private_key=chain.key)
    assert out["sent"] == 4 and w3.eth.block_number == blocks + 4 and "READY" in capsys.readouterr().out


def test_deployment_that_breaks_off_keeps_the_record_of_what_was_sent(chain, circuit_build, tmp_path, monkeypatch, capsys):
    d, v4, w3 = chain.deploy, chain.v4, chain.w3
    env = tmp_path / "deploy.env"
    deploy, sent = v4.deploy_contract, []

    def third_fails(w3_, key, name, *arguments, **options):
        if len(sent) == 2:
            raise RuntimeError("the node did not answer")
        sent.append(name)
        return deploy(w3_, key, name, *arguments, **options)
    monkeypatch.setattr(v4, "deploy_contract", third_fails)
    with pytest.raises(d.DeployError, match="the deployment of ConsentSBTv4 failed: the node did not answer"):
        d.main(["--env-file", str(env)], w3=w3, private_key=chain.key)
    assert sent == ["HalahDecisionVerifier", "PoseidonT3"] and not env.exists()
    (name,) = [n for n in os.listdir(tmp_path) if n.startswith("deployment_")]
    record = open(tmp_path / name).read()
    printed = capsys.readouterr().out
    assert f"Record of this deployment: {tmp_path / name}" in printed
    # the two contracts that were deployed stand in the record with their transactions, and so does the reason of the stop
    assert record.count("  tx 0x") == 2 and "HalahDecisionVerifier    0x" in record and "PoseidonT3               0x" in record
    assert "STOPPED: the deployment of ConsentSBTv4 failed: the node did not answer. Deployed before it: HalahDecisionVerifier 0x" in record
    assert "READY" not in record and chain.key_hex[2:] not in record


def test_deploy_check_accepts_a_correct_deployment_and_refuses_a_wrong_one(chain, circuit_build, tmp_path, capsys):
    d, v4, w3, s = chain.deploy, chain.v4, chain.w3, chain.stack
    env = tmp_path / "remix.env"
    env.write_text("RPC_URL=http://127.0.0.1:1\n")
    blocks = w3.eth.block_number
    given = ["--poseidon", s["poseidon"], "--token", s["token"], "--groth16", s["groth16"], "--verifier", s["verifier"]]
    out = d.main(["--env-file", str(env), "--check", "--deploy-block", "7"] + given, w3=w3)   # no key is needed to check
    printed = capsys.readouterr().out
    assert out["sent"] == 0 and w3.eth.block_number == blocks and "READY" in printed and "no key configured" in printed
    assert out["read_back"]["owner"] == chain.signer and out["read_back"]["consent_token"] == s["token"]
    assert env.read_text().splitlines() == ["RPC_URL=http://127.0.0.1:1", "CONTRACT_V4_ADDRESS=" + s["token"], "VERIFIER_ADDRESS=" + s["verifier"],
                                            "POSEIDON_ADDRESS=" + s["poseidon"], "GROTH16_VERIFIER_ADDRESS=" + s["groth16"],
                                            "CONTRACT_V4_DEPLOY_BLOCK=7", f"CHAIN_ID={chain.chain_id}"]
    assert d.main(["--env-file", str(env), "--check"], w3=w3, private_key=chain.key)["read_back"]["owner"] == chain.signer   # from the file
    stranger = chain.Web3.keccak(text="halah issuance wiring test key that owns nothing")
    with pytest.raises(d.DeployError, match="is not the owner of ConsentSBTv4"):
        d.main(["--env-file", str(env), "--check"], w3=w3, private_key=stranger)
    with pytest.raises(d.DeployError, match="no address given for: verifier"):
        d.main(["--env-file", str(tmp_path / "empty.env"), "--check"] + given[:6], w3=w3)

    # a second token, and a decision verifier that reads its roots from it
    token2, _ = v4.deploy_contract(w3, chain.key, "ConsentSBTv4", s["poseidon"])
    wrapper2, _ = v4.deploy_contract(w3, chain.key, "ConsentDecisionVerifier", s["groth16"], token2)
    mock, _ = v4.deploy_contract(w3, chain.key, "MockDecisionVerifier")
    wrapper3, _ = v4.deploy_contract(w3, chain.key, "ConsentDecisionVerifier", mock, s["token"])
    wrong = {"reads its roots from another token": dict(s, verifier=wrapper2),
             "calls another Groth16 verifier": dict(s, verifier=wrapper3),
             "uses another Poseidon contract": dict(s, poseidon=s["groth16"]),
             "is not the HalahDecisionVerifier of this repository": dict(s, groth16=mock, verifier=wrapper3),
             "no contract code at": dict(s, poseidon=chain.signer),
             "did not answer as ConsentSBTv4": dict(s, token=s["poseidon"]),
             "four addresses are needed": {k: v for k, v in s.items() if k != "groth16"}}
    for message, addresses in wrong.items():
        with pytest.raises(d.DeployError, match=message):
            d.check_deployment(w3, addresses)
    assert d.check_deployment(w3, dict(s, token=token2, verifier=wrapper2))["consent_token"] == token2


def test_deployed_code_is_compared_without_the_compiler_metadata(chain):
    """The same contract compiled from another path (as in Remix) ends in another metadata hash and is still accepted.
    A contract with one changed instruction is not."""
    d, v4, w3 = chain.deploy, chain.v4, chain.w3
    art = v4.load_artifact("ConsentSBTv4")
    creation = bytearray.fromhex(art["bytecode"][2:])
    size = int.from_bytes(creation[-2:], "big")
    assert creation[-size - 2] == 0xA2 and b"ipfs" in creation[-size - 2:] and b"solc" in creation[-size - 2:]
    creation[-size + 10] ^= 0xFF                                      # one byte of the hash inside the metadata record
    account = w3.eth.account.from_key(chain.key)

    def deploy(code):
        factory = w3.eth.contract(abi=art["abi"], bytecode="0x" + bytes(code).hex())
        _, receipt = v4._sign_and_send(w3, account, factory.constructor(chain.stack["poseidon"]))
        return receipt["contractAddress"]

    moved = deploy(creation)
    code = bytes(w3.eth.get_code(moved))
    assert code != bytes(w3.eth.get_code(chain.stack["token"]))
    assert d.code_matches(code, "ConsentSBTv4", (chain.stack["poseidon"],)) is True
    assert d.code_matches(code, "ConsentSBTv4") is False              # the Poseidon address in the code must be the one given
    assert d.code_matches(code, "ConsentDecisionVerifier", (chain.stack["poseidon"],)) is False
    assert d.code_matches(b"", "ConsentSBTv4") is False
    changed = bytearray(code); changed[len(changed) // 2] ^= 0x01
    assert d.code_matches(bytes(changed), "ConsentSBTv4", (chain.stack["poseidon"],)) is False
    wrapper, _ = v4.deploy_contract(w3, chain.key, "ConsentDecisionVerifier", chain.stack["groth16"], moved)
    assert d.check_deployment(w3, dict(chain.stack, token=moved, verifier=wrapper), signer=chain.signer)["owner"] == chain.signer
