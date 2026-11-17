"""Refusals as the running application gives them, with Streamlit's test runner (no browser) and with the function the
clinician screen calls, services/request_service.submit_request.

Each test makes one request that must be refused, through a screen where the screen can make it, and asserts the check
that fails, the deny code of Section 6.3.1 where there is one, and that nothing else stands in a deny code field:
a forged credential at the approval and at the request, an approval of a signer outside G, a request while a capacity
transition is pending, a request before the start and after the expiry at the time of the chain, a second revocation
on chain, a tampered proof and a replayed proof.

The chain is an in-memory EVM with the real bytecode of blockchain/abi (no network, no Sepolia). The key of the owner is
derived from a label in this file: it is a test key and holds nothing. The two proof tests need the built circuit
(zk/build) and are skipped without it."""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_KEY_LABEL = "halah refusals on screens test owner"        # the owner key is derived from this label (not a secret)
PATIENT = "did:patient:x"
CLINICIAN, REGISTRAR = "did:hospital:001", "did:hospital:002"
G = ["did:parent:A", "did:parent:B"]
NINE = ("OUT-OF-SCOPE", "PURPOSE-MISMATCH", "CONTEXT-MISMATCH", "PRE-VALIDITY", "POST-VALIDITY", "AWAITING-TRIGGER",
        "TRANSITION-PENDING", "EXPIRED", "REVOKED")
INTERNAL = ("IDENTITY-INVALID", "APPROVAL-PENDING", "TOKEN-PENDING", "RECORD-INVALID", "PROOF-INVALID", "COPY-UNAVAILABLE",
            "TRANSITION-NOT-PERMITTED")
RECORDED = " The denied request is recorded in the audit ledger."


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


@pytest.fixture(scope="module")
def records():
    """A patient of the source record (the Synthea subset of the repository) whom no other test file uses."""
    import database.repository as repository
    repo = repository.SyntheaRepository(os.path.join(ROOT, "data", "synthea"))
    return SimpleNamespace(repo=repo, patient=repo.get_patient_dids()["DID"].tolist()[20])


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
    return SimpleNamespace(w3=w3, Web3=Web3, v4=v4, tester=w3.provider.ethereum_tester, key=key, key_hex=Web3.to_hex(key),
                           signer=signer, stack=stack, chain_id=w3.eth.chain_id)


@pytest.fixture()
def chain(base, monkeypatch):
    """The chain in its fresh state: whatever a test does is undone after it."""
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


def _born(days_to_majority):
    """A date of birth whose eighteenth birthday lies `days_to_majority` days from today (negative: in the past)."""
    day = datetime.now().date() + timedelta(days=days_to_majority)
    try:
        return day.replace(year=day.year - 18)
    except ValueError:                                                # 29 February
        return day.replace(year=day.year - 18, day=28)


def _consent(scope=("Observation",), approvals=None, token=True, patient=PATIENT, start=None, expiry=None, majority_in=None):
    """A consent as the form and the guardian screen leave it: committed, approved over the commitment, and with the
    local token once the threshold is met. `majority_in` gives the patient a date of birth and schedules the transition
    at majority, as the form does while the patient is a minor (it is scheduled as of a month ago)."""
    from database import consent_db
    from services import capacity_service, commitment_service, identity_service as ids
    from services.consent_service import create_consent
    c = create_consent(patient, CLINICIAN, list(G), list(scope), "Treatment",
                       (start or datetime.now() - timedelta(days=40)).isoformat(),
                       (expiry or datetime.now() + timedelta(days=30)).isoformat(), threshold=len(G), context="AU",
                       patient_birth_date=None if majority_in is None else _born(majority_in))
    commitment_service.commit_consent(c)
    for g in (G if approvals is None else approvals):
        signature, address = ids.sign_consent_v2(g, c.consent_id, c.commitment)
        c.signatures.append(g)
        c.signature_data[g] = {"scheme": "EIP-712", "version": 2, "signer": address, "signature": signature}
    if token:
        c.token_id = f"SBT-LOCAL-{c.consent_id[:8]}"
    consent_db.save(c)
    if majority_in is not None:
        assert capacity_service.schedule_majority_transition(c, datetime.now() - timedelta(days=30)) is not None
    return c


def _anchored(c):
    """Mint the token of the consent on the in-memory chain and record it, as the background job does."""
    from database import consent_db
    from services import blockchain_service as bc
    receipt = bc.mint_consent(c)
    assert receipt["status"] == 1
    c.token_id = f"SBT-{receipt['token_id']}"
    consent_db.update(c)
    return receipt


def _guardian_screen(AppTest, cid, did=None):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Guardian").run()
    [t for t in at.text_input if t.label == "Enter Target Consent ID"][0].set_value(cid).run()
    if did is not None:
        [s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0].set_value(did).run()
    return at


def _clinician_screen(AppTest, cid, requester=CLINICIAN):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Clinician").run()
    [t for t in at.text_input if t.label == "Enter Authorised Consent ID"][0].set_value(cid).run()
    [t for t in at.text_input if t.label == "Your Clinician DID (requester)"][0].set_value(requester).run()
    return at


def _patient_screen(AppTest, patient):
    """The Patient screen with the list "My Consents" of one patient."""
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    [s for s in at.selectbox if s.label == "Patient DID (Identity Pointer)"][0].set_value(patient).run()
    return at


def _click(at, label):
    [b for b in at.button if b.label.startswith(label)][0].click().run()
    assert not at.exception
    return at


def _scope(at, scope):
    [m for m in at.multiselect if m.label == "Select Request Scope"][0].set_value(list(scope)).run()
    return at


def _matrix(at):
    return at.table[0].value.to_dict("records")[0]


def _failed(at):
    return [name for name, value in _matrix(at).items() if value == "FAIL" and name != "ALLOW"]


def _rows(cid, action=None):
    from database import audit_db
    return [e for e in audit_db.get() if e["consent_id"] == cid and (action is None or e["action"] == action)]


def _stored(cid):
    from database import db
    return [r for r in db.all_rows("consents") if r["consent_id"] == cid][0]                 # the row in SQLite, not the object in memory


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


def _page_text(at):
    groups = (at.error, at.warning, at.caption, at.info, at.success, at.markdown, at.subheader, at.header)
    return " | ".join(str(e.value) for group in groups for e in group)


def _source(patient_did, scope):
    """Stands for the source record: one row for each module asked for."""
    return {module: [{"module": module, "patient": patient_did}] for module in scope}


def _forged(monkeypatch, did, role):
    """The credential store answers for `did` with a credential that carries the right role and subject and is signed
    by a key that is not the issuer's."""
    from eth_account import Account
    from eth_utils import keccak
    from services import identity_service as ids
    forger = Account.from_key(keccak(text="halah refusals on screens test forger"))          # a key that issues nothing
    forged = ids.issue_credential(did, role, signer=forger)
    held = ids.get_credential
    monkeypatch.setattr(ids, "get_credential", lambda d: forged if d == did else held(d))
    return forged


# ---- a forged credential -------------------------------------------------------------------------------------------------

def test_forged_guardian_credential_is_refused_at_the_approval_and_recorded(app_test, anchor_calls, monkeypatch):
    c = _consent(approvals=[], token=False)
    _forged(monkeypatch, "did:parent:B", "guardian")
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:B"), "Sign Consent via VC")
    assert any(e.value == "Guardian credential is not valid (Sig_VC: the signature of the credential is not valid) - approval rejected."
               for e in at.error)
    assert "CREDENTIAL_SIGNATURE_INVALID" not in _page_text(at)      # the screen shows words, the ledger the reason code
    (row,) = _rows(c.consent_id)
    assert (row["action"], row["result"], row["actor_did"], row["actor_role"]) == ("SIGN_CONSENT", "REJECTED", "did:parent:B", "Guardian")
    assert row["metadata"]["reason"] == "CREDENTIAL_SIGNATURE_INVALID"
    checks = row["metadata"]["credential_checks"]
    assert checks["Issuer_valid"] is True and checks["Sig_VC"] is False and checks["Role_match"] is False
    stored = _stored(c.consent_id)
    assert stored["signatures"] == [] and not stored["signature_data"] and not stored["token_id"] and not anchor_calls
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:A"), "Sign Consent via VC")   # the other guardian is not touched
    assert not at.error and any("Multi-sig: 1/2" in s.value for s in at.success)


def test_forged_clinician_credential_fails_vi_at_the_request_and_no_code_is_shown_or_recorded(app_test, monkeypatch):
    c = _consent()
    _forged(monkeypatch, CLINICIAN, "doctor")
    at = _clinician_screen(app_test, c.consent_id)
    assert any(w.value == "No valid clinician credential for this DID (Sig_VC: the signature of the credential is not valid)."
               for w in at.warning)
    at = _scope(at, ["Observation"])
    assert _failed(at) == ["VI"] and any(x.value == "Failed checks: VI" for x in at.caption)
    assert not any(s.value == "Authorised Data Scope" for s in at.subheader)
    at = _click(at, "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VI." + RECORDED for e in at.error)
    assert not at.dataframe and not any(word in _page_text(at) for word in INTERNAL + NINE)
    assert [e["action"] for e in _rows(c.consent_id)] == ["STATE_CHECK", "DATA_ACCESS"]     # no evidence of a valid verification
    check, access = _rows(c.consent_id)
    assert check["metadata"]["requester_identity"]["reason"] == "CREDENTIAL_SIGNATURE_INVALID"
    m = access["metadata"]
    assert access["result"] == "DENIED" and m["failed_checks"] == ["VI"] and m["deny_code"] is None and m["modules_released"] == []
    assert _code_fields(check) == [] and _code_fields(access) == []


# ---- an approval of a signer outside G -----------------------------------------------------------------------------------

def test_signer_outside_g_is_not_offered_on_the_screen_and_an_approval_of_his_does_not_reach_the_threshold(app_test):
    from database import consent_db
    from services import identity_service as ids
    c = _consent(approvals=["did:parent:A"], token=False)             # one approval of two
    at = _guardian_screen(app_test, c.consent_id)
    assert list([s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0].options) == G
    # the uncle holds a valid guardian credential and signs the same commitment with his own key
    assert ids.verify_identity("did:parent:C", role="guardian").valid
    signature, address = ids.sign_consent_v2("did:parent:C", c.consent_id, c.commitment)
    c.signatures.append("did:parent:C")
    c.signature_data["did:parent:C"] = {"scheme": "EIP-712", "version": 2, "signer": address, "signature": signature}
    consent_db.update(c)
    at = _scope(_clinician_screen(app_test, c.consent_id), ["Observation"])
    assert _failed(at) == ["VA", "VL"] and any(x.value == "Failed checks: VA, VL" for x in at.caption)
    at = _click(at, "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VA, VL. Consent state: PENDING_SIGNATURE." + RECORDED for e in at.error)
    check, access = _rows(c.consent_id)[-2:]
    assert check["result"] == "PENDING_SIGNATURE" and access["metadata"]["failed_checks"] == ["VA", "VL"]
    assert _code_fields(check) == [] and _code_fields(access) == [] and access["metadata"]["modules_released"] == []
    at = _guardian_screen(app_test, c.consent_id)                     # the screen counts the members of G alone
    assert any(i.value == f"Found consent for Patient: `{PATIENT}` (state: PENDING_SIGNATURE)" for i in at.info)
    assert not any("reached but NOT anchored" in w.value for w in at.warning) and not _stored(c.consent_id)["token_id"]


# ---- a capacity transition that is pending -------------------------------------------------------------------------------

def test_request_while_the_transition_is_pending_is_refused_with_its_code_on_the_screen(app_test):
    c = _consent(majority_in=-1)                                      # the patient turned eighteen yesterday
    at = _scope(_clinician_screen(app_test, c.consent_id), ["Observation"])
    assert _failed(at) == ["VL"] and any(x.value == "Failed checks: VL | Deny code: TRANSITION-PENDING" for x in at.caption)
    assert any(e.value == "Consent is not active. Current state: SUSPENDED (deny code: TRANSITION-PENDING)" for e in at.error)
    at = _click(at, "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VL. Deny code: TRANSITION-PENDING. Consent state: SUSPENDED." + RECORDED
               for e in at.error)
    assert not at.dataframe
    check, access = _rows(c.consent_id, "STATE_CHECK")[-1], _rows(c.consent_id, "DATA_ACCESS")[-1]
    assert check["result"] == "SUSPENDED" and check["metadata"]["lifecycle"]["deny_code"] == "TRANSITION-PENDING"
    m = access["metadata"]
    assert (access["result"], m["deny_code"], m["deny_codes"], m["failed_checks"]) == ("DENIED", "TRANSITION-PENDING", ["TRANSITION-PENDING"], ["VL"])
    assert m["modules_released"] == [] and m["proof_reference"] is None
    moved = _rows(c.consent_id, "CONDITION_CHECK")
    assert len(moved) == 1 and moved[0]["result"] == "SUSPENDED" and moved[0]["metadata"]["deny_codes"] == ["TRANSITION-PENDING"]


# ---- the window, at the time of the chain --------------------------------------------------------------------------------

def test_window_is_judged_at_the_block_time_and_not_at_the_server_clock(app_test, onchain):
    now = datetime.now()
    c = _consent(start=now - timedelta(days=1), expiry=now + timedelta(hours=1))      # in its window by the server clock
    late = _consent(start=now + timedelta(hours=1), expiry=now + timedelta(days=30))  # not started by the server clock
    _anchored(c)
    _anchored(late)
    onchain.tester.time_travel(onchain.w3.eth.get_block("latest").timestamp + 2 * 3600)      # the chain is two hours ahead
    at = _scope(_clinician_screen(app_test, c.consent_id), ["Observation"])
    assert _failed(at) == ["VT", "VL"] and any(x.value == "Failed checks: VT, VL | Deny code: EXPIRED" for x in at.caption)
    at = _click(at, "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VT, VL. Deny code: EXPIRED. Consent state: EXPIRED." + RECORDED for e in at.error)
    check, access = _rows(c.consent_id, "STATE_CHECK")[-1], _rows(c.consent_id, "DATA_ACCESS")[-1]
    m = access["metadata"]
    assert (access["result"], m["deny_code"], m["failed_checks"], m["time_source"]) == ("DENIED", "EXPIRED", ["VT", "VL"], "block-timestamp")
    assert check["result"] == "EXPIRED" and check["metadata"]["time"]["source"] == "block-timestamp"
    assert datetime.fromisoformat(m["decision_time"]) > now + timedelta(hours=1) and m["modules_released"] == []
    # the consent that has not started by the server clock has started by the time of the chain
    at = _scope(_clinician_screen(app_test, late.consent_id), ["Observation"])
    assert _failed(at) == [] and any(s.value == "Authorised Data Scope" for s in at.subheader)


def test_request_before_the_start_is_refused_with_pre_validity_on_the_screen_at_the_block_time(app_test, onchain):
    block = datetime.fromtimestamp(onchain.w3.eth.get_block("latest").timestamp)
    c = _consent(start=block + timedelta(days=2), expiry=block + timedelta(days=30))
    _anchored(c)
    blocks = onchain.w3.eth.block_number
    at = _scope(_clinician_screen(app_test, c.consent_id), ["Observation"])
    assert _failed(at) == ["VT", "VL"] and any(x.value == "Failed checks: VT, VL | Deny code: PRE-VALIDITY" for x in at.caption)
    at = _click(at, "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VT, VL. Deny code: PRE-VALIDITY. Consent state: NOT_STARTED." + RECORDED
               for e in at.error)
    check, access = _rows(c.consent_id, "STATE_CHECK")[-1], _rows(c.consent_id, "DATA_ACCESS")[-1]
    m = access["metadata"]
    assert (m["deny_code"], m["deny_codes"], m["failed_checks"], m["time_source"]) == ("PRE-VALIDITY", ["PRE-VALIDITY"], ["VT", "VL"], "block-timestamp")
    assert check["result"] == "NOT_STARTED" and m["proof_reference"] is None
    assert onchain.w3.eth.block_number == blocks                      # no proof is made and nothing is sent for a denied request


# ---- majority, at the time of the chain ------------------------------------------------------------------------------------

def test_majority_is_judged_at_the_block_time_on_the_guardian_and_the_patient_screen(app_test, onchain, records):
    from database import consent_db
    patient = records.patient
    c = _consent(patient=patient, majority_in=1)                      # the patient turns eighteen tomorrow by the server clock
    old_token = _anchored(c)["token_id"]
    at = _guardian_screen(app_test, c.consent_id, "did:parent:A")
    assert any(i.value == f"Found consent for Patient: `{patient}` (state: ACTIVE)" for i in at.info)
    onchain.tester.time_travel(onchain.w3.eth.get_block("latest").timestamp + 2 * 86400)     # the chain is two days ahead
    block = datetime.fromtimestamp(onchain.w3.eth.get_block("latest").timestamp)
    # the guardian: the consent is suspended and his revocation is refused, although the server clock is a day short
    at = _guardian_screen(app_test, c.consent_id, "did:parent:A")
    assert any(i.value == f"Found consent for Patient: `{patient}` (state: SUSPENDED)" for i in at.info)
    at = _click(at, "Revoke Consent (as guardian)")
    assert any(e.value.startswith("Revocation refused: the patient has reached the age of majority") for e in at.error)
    check, denied = _rows(c.consent_id)[-2:]
    assert (check["action"], check["result"], check["metadata"]["time"]["source"]) == ("STATE_CHECK", "SUSPENDED", "block-timestamp")
    assert (denied["action"], denied["result"], denied["metadata"]["reason"]) == ("REVOKE_CONSENT", "DENIED", "GUARDIAN-AFTER-MAJORITY")
    assert denied["metadata"]["time_source"] == "block-timestamp" and denied["metadata"]["after_majority"] is True
    assert datetime.fromisoformat(denied["metadata"]["requested_at"]) == block and not _stored(c.consent_id)["revoked"]
    assert onchain.token.check_valid(old_token) is True               # nothing was sent for the refused request
    # the patient: the take-over is offered and carried out at the time of the chain
    at = _patient_screen(app_test, patient)
    assert f"tr_{c.consent_id}" in [b.key for b in at.button]
    at.button(key=f"tr_{c.consent_id}").click().run()
    assert not at.exception
    old = consent_db.get(c.consent_id)
    new = consent_db.get(old.successor_id)
    assert new is not None and new.guardian_dids == [patient] and new.threshold == 1 and new.token_id.startswith("SBT-")
    transition = _rows(c.consent_id, "CAPACITY_TRANSITION")[-1]
    assert transition["result"] == "SUCCESS" and datetime.fromisoformat(transition["metadata"]["evaluated_at"]) >= block
    assert onchain.token.check_valid(old_token) is False and onchain.token.check_valid(int(new.token_id[4:])) is True


# ---- a second revocation -------------------------------------------------------------------------------------------------

def test_second_revocation_on_chain_sends_no_second_transaction_and_notifies_nobody_twice(app_test, onchain):
    from services import notification_service
    c = _consent(majority_in=3000)                                    # a minor: majority lies years ahead
    token = _anchored(c)["token_id"]
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:A"), "Revoke Consent (as guardian)")
    assert any(s.value.startswith("Revoked on-chain. Tx: 0x") for s in at.success)
    assert onchain.token.check_valid(token) is False
    blocks, root = onchain.w3.eth.block_number, onchain.token.revocation_root()
    rows = len(_rows(c.consent_id))
    notices = len(notification_service.inbox(CLINICIAN))
    # the other guardian asks for the same revocation
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:B"), "Revoke Consent (as guardian)")
    assert any(i.value == "This consent is already revoked." for i in at.info)
    assert not any("revoked" in s.value.lower() for s in at.success)   # no second revocation is announced
    assert onchain.w3.eth.block_number == blocks and onchain.token.revocation_root() == root     # nothing was sent
    new = _rows(c.consent_id)[rows:]
    assert [e["action"] for e in new] == ["STATE_CHECK", "REVOKE_CONSENT"]
    check, again = new
    lifecycle = check["metadata"]["lifecycle"]
    assert (lifecycle["target"], lifecycle["VALID"], lifecycle["state"], lifecycle["deny_code"]) == ("REVOKED", False, "REVOKED", "REVOKED")
    assert again["metadata"]["revocation"] == "ALREADY_REVOKED" and again["metadata"]["onchain"]["status"] == "ALREADY_CONFIRMED"
    assert _stored(c.consent_id)["revoked_by"] == "did:parent:A"      # the revocation stays that of the first guardian
    assert len(_rows(c.consent_id, "ONCHAIN_REVOKE")) == 1 and len(notification_service.inbox(CLINICIAN)) == notices


# ---- a tampered proof and a replayed proof -------------------------------------------------------------------------------

def _needs_circuit():
    from services import zk_decision_service
    if not zk_decision_service.decision_available():
        pytest.skip("the decision circuit is not built (zk/build)")


def test_tampered_proof_is_refused_by_the_verifier_contract_and_nothing_is_released(onchain, monkeypatch):
    from services import blockchain_service as bc, data_vault, request_service
    _needs_circuit()
    c = _consent()
    _anchored(c)
    made = bc.decision_proof

    def tampered(*request, **more):                                   # the purpose among the public signals is changed
        proof = dict(made(*request, **more))
        signals = [str(s) for s in proof["publicSignals"]]
        signals[2] = str(int(signals[2]) + 1)
        proof["publicSignals"] = signals
        return proof
    monkeypatch.setattr(bc, "decision_proof", tampered)
    opened = []
    monkeypatch.setattr(data_vault.DataVault, "open", lambda self, consent_id, modules: opened.append(modules) or {})
    blocks = onchain.w3.eth.block_number
    out = request_service.submit_request(c, CLINICIAN, ["Observation"], "Treatment", "AU", source=_source)
    assert (out["outcome"], out["failed_checks"], out["deny_code"], out["data"]) == ("DENIED", ["proof"], None, {})
    assert out["decision"]["ALLOW"] is True and out["verification"]["accepted"] is False
    assert out["verification"]["reason_text"] == "proof is not valid"
    assert opened == [] and onchain.w3.eth.block_number == blocks     # nothing was decrypted and nothing was sent
    m = out["audit_event"]["metadata"]
    assert m["zk_proof_verified"] is False and m["modules_released"] == [] and m["deny_code"] is None and m["deny_codes"] == []
    assert m["proof_reference"]["reference"] == {"reason_text": "proof is not valid"} and "tx_hash" not in m["proof_reference"]
    assert _code_fields(out["audit_event"]) == [] and _code_fields(out["state_check_event"]) == []


def test_replayed_proof_is_refused_on_its_tag_and_nothing_is_released_a_second_time(onchain, monkeypatch):
    from services import blockchain_service as bc, request_service
    _needs_circuit()
    c = _consent()
    _anchored(c)
    made, kept = bc.decision_proof, []

    def keep(*request, **more):
        kept.append(made(*request, **more))
        return kept[-1]
    monkeypatch.setattr(bc, "decision_proof", keep)
    first = request_service.submit_request(c, CLINICIAN, ["Observation"], "Treatment", "AU", source=_source)
    assert first["outcome"] == "GRANTED" and first["verification"]["accepted"] is True and list(first["data"]) == ["Observation"]
    blocks = onchain.w3.eth.block_number
    replay = {name: value for name, value in kept[0].items() if name not in ("tx_hash", "block_number")}
    monkeypatch.setattr(bc, "decision_proof", lambda *request, **more: dict(replay))       # the same proof, presented again
    out = request_service.submit_request(c, CLINICIAN, ["Observation"], "Treatment", "AU", source=_source)
    assert (out["outcome"], out["failed_checks"], out["deny_code"], out["data"]) == ("DENIED", ["proof"], None, {})
    assert out["verification"]["accepted"] is False and out["verification"]["reason_text"] == "tag already seen"
    assert onchain.w3.eth.block_number == blocks                      # the refusal costs no transaction
    m = out["audit_event"]["metadata"]
    assert m["modules_released"] == [] and m["proof_reference"]["reference"] == {"reason_text": "tag already seen"}
    assert "tx_hash" not in m["proof_reference"] and _code_fields(out["audit_event"]) == []
    assert [e["result"] for e in _rows(c.consent_id, "DATA_ACCESS")] == ["GRANTED", "DENIED"]
