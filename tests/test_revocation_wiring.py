"""Revocation and the capacity transition as the running application performs them (thesis Chapter 6), with Streamlit's
test runner (no browser).

B5 Revoke is Algorithm 6.4 (revocation_service.revoke): the on-chain revoke, the deletion of the consent-bound copy, the
   destruction of its keys, the deletion of the link to the token and the notification of every recipient, all recorded.
   The patient screen calls it. The guardian screen has a Revoke control: before majority one guardian revokes alone,
   after the transition a guardian is refused and the refusal is recorded. The clinician screen shows the notice.
B6 at majority the patient takes the consent over: the re-issued consent is committed, signed by the patient over its
   commitment and, with ConsentSBTv4 configured, minted on chain, and the old token is revoked on chain.
Before a revocation and before the old consent is retired, the requested transition to REVOKED is checked against the
transition policy and recorded (Algorithm 6.2, lines 16 to 20).

The chain is an in-memory EVM with the real bytecode of blockchain/abi (no network, no Sepolia). The key of the owner is
derived from a label in this file: it is a test key and holds nothing. The tests that need a proof replace the Groth16
verifier by MockDecisionVerifier, which proves nothing."""
import os, re, threading
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_KEY_LABEL = "halah revocation wiring test owner"          # the owner key is derived from this label (not a secret)
CLINICIAN, REGISTRAR = "did:hospital:001", "did:hospital:002"
G = ["did:parent:A", "did:parent:B"]
RECORDED = " The refused request is recorded in the audit ledger."
AFTER_MAJORITY = "the patient has reached the age of majority, and only the patient may revoke now"


# ---- fixtures and helpers ----------------------------------------------------------------------------------------------

@pytest.fixture()
def app_test(monkeypatch):
    try:
        from streamlit.testing.v1 import AppTest
    except Exception:
        pytest.skip("streamlit testing API not available")
    monkeypatch.chdir(ROOT)
    return AppTest


@pytest.fixture(scope="module")
def patients():
    """Patients of the source record (the Synthea subset of the repository). Each test takes one of its own, so the
    list "My Consents" of a test shows the consents of that test."""
    import database.repository as repository
    return repository.SyntheaRepository(os.path.join(ROOT, "data", "synthea")).get_patient_dids()["DID"].tolist()[3:]


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


def _consent(patient, scope=("Observation",), approvals=None, token=True, majority_in=None, trigger=None):
    """A consent as the form and the guardian screen leave it: committed, approved over the commitment, and with the
    local token once the threshold is met. `majority_in` gives the patient a date of birth and schedules the transition
    at majority, as the form does while the patient is a minor (it is scheduled as of a month ago)."""
    from database import consent_db
    from services import capacity_service, commitment_service, identity_service as ids, trigger_service
    from services.consent_service import create_consent
    c = create_consent(patient, CLINICIAN, list(G), list(scope), "Treatment",
                       (datetime.now() - timedelta(days=40)).isoformat(), (datetime.now() + timedelta(days=30)).isoformat(),
                       threshold=len(G), context="AU",
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
    if trigger:
        trigger_service.add_trigger(c, trigger, attester_role="doctor", actor_did=patient, actor_role="Patient")
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


def _source(patient_did, scope):
    """Stands for the source record: one row for each module asked for."""
    return {module: [{"module": module, "patient": patient_did}] for module in scope}


def _ask(c, requester=CLINICIAN, scope=("Observation",), **kw):
    """One request through the function the clinician screen calls."""
    from services import request_service
    return request_service.submit_request(c, requester, list(scope), "Treatment", "AU", **kw)


def _mock_verifier(chain, monkeypatch):
    """A wrapper whose Groth16 verifier is MockDecisionVerifier, and a prover that gives the one "proof" the mock accepts
    for the public inputs of the request. It proves nothing: it lets a request be granted on chain without the circuit."""
    from eth_abi import encode
    from eth_utils import keccak
    from services import blockchain_service as bc, commitment_service as cs
    mock, _ = chain.v4.deploy_contract(chain.w3, chain.key, "MockDecisionVerifier")
    wrapper, _ = chain.v4.deploy_contract(chain.w3, chain.key, "ConsentDecisionVerifier", mock, chain.stack["token"])
    monkeypatch.setattr(bc, "verifier_client", lambda read_only=False: chain.v4.DecisionVerifierContract(
        w3=chain.w3, address=wrapper, private_key=None if read_only else chain.key, read_only=read_only))

    def decision_proof(consent, requester_did, purpose, context, scope, now_ts):
        roots = bc.token_client(read_only=True).read_roots()
        tag, nonce = cs.request_tag(requester_did)
        public = [int(now_ts), cs.role_code("doctor"), cs.purpose_code(purpose), cs.context_code(context), tag,
                  roots["consent_root"], roots["revocation_root"]]
        b, c = ((21, 22), (23, 24)), (31, 32)
        digest = keccak(encode(["uint256[7]", "uint256", "uint256[2][2]", "uint256[2]"], [public, 11, b, c]))
        return {"mode": "groth16", "circuit": "mock", "proof": ([int.from_bytes(digest, "big") % cs.FIELD, 11], [list(b[0]), list(b[1])], list(c)),
                "publicSignals": [str(x) for x in public], "tag": str(tag),
                "audit": {"requester_did": requester_did, "nonce": str(nonce), "tag": str(tag)}}
    monkeypatch.setattr(bc, "decision_proof", decision_proof)
    return wrapper


def _patient_screen(AppTest, patient):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    [s for s in at.selectbox if s.label == "Patient DID (Identity Pointer)"][0].set_value(patient).run()
    return at


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


def _click(at, label=None, key=None):
    button = at.button(key=key) if key else [b for b in at.button if b.label == label][0]
    button.click().run()
    assert not at.exception
    return at


def _labels(at):
    return [b.label for b in at.button]


def _rows(cid, action=None):
    from database import audit_db
    return [e for e in audit_db.get() if e["consent_id"] == cid and (action is None or e["action"] == action)]


def _stored(cid):
    from database import db
    return [r for r in db.all_rows("consents") if r["consent_id"] == cid][0]                 # the row in SQLite, not the object in memory


def _page_text(at):
    groups = (at.error, at.warning, at.caption, at.info, at.success, at.markdown)
    return " | ".join(str(e.value) for group in groups for e in group)


# ---- B5: the patient's Revoke is Algorithm 6.4 -------------------------------------------------------------------------

def test_patient_revoke_on_the_screen_deletes_the_copy_destroys_the_keys_and_notifies_the_recipient(app_test, patients):
    from services import data_vault, notification_service, revocation_service
    patient = patients[0]
    c = _consent(patient, scope=["Observation", "Medication"])
    assert _ask(c, source=_source)["outcome"] == "GRANTED"            # the clinician received data, so there is a recipient
    vault = data_vault.default_vault()
    assert vault.modules(c.consent_id) == ["Medication", "Observation"] and len(vault.key_store.key_ids(c.consent_id)) == 2
    retained = vault.export_copy(c.consent_id)                        # a copy of the ciphertext kept from before
    before = len(_rows(c.consent_id))
    at = _patient_screen(app_test, patient)
    assert f"rv_{c.consent_id}" in [b.key for b in at.button]
    at = _click(at, key=f"rv_{c.consent_id}")
    # the message survives the rerun that follows the click
    assert any(s.value == "Consent revoked (local ledger)." for s in at.success)
    assert any(i.value == "Consent-bound copy deleted: Medication, Observation. Keys destroyed: 2. "
               f"Recipients notified: {CLINICIAN}." for i in at.info)
    assert f"rv_{c.consent_id}" not in [b.key for b in at.button]     # a revoked consent offers no Revoke
    rows = _rows(c.consent_id)[before:]
    assert [e["action"] for e in rows] == ["STATE_CHECK", "WITHDRAWAL_NOTIFICATION", "REVOKE_CONSENT"]
    check, notice, revoke = rows
    # Algorithm 6.2, lines 16 to 20: the requested transition to REVOKED, recorded before the revocation
    lifecycle = check["metadata"]["lifecycle"]
    assert (lifecycle["operation"], lifecycle["target"], lifecycle["VALID"], lifecycle["state"]) == ("TRANSITION", "REVOKED", True, "ACTIVE")
    assert check["metadata"]["requested_by"] == patient and "VI" not in check["metadata"]
    assert check["metadata"]["time"]["source"] == "system-clock-fallback"
    assert (notice["result"], notice["metadata"]["recipient_did"], notice["metadata"]["releases"]) == ("SENT", CLINICIAN, 1)
    m = revoke["metadata"]
    assert (revoke["result"], revoke["actor_did"], revoke["actor_role"]) == ("SUCCESS", patient, "Patient")
    assert (m["revocation"], m["revoker_role"], m["basis"], m["complete"], m["pending"]) == ("REVOKED", "Patient", "patient", True, [])
    assert m["onchain"]["status"] == "NOT_APPLICABLE" and m["time_source"] == "system-clock-fallback"
    assert m["shredded"]["copies_remaining"] == 0 and m["shredded"]["keys_remaining"] == 0 and m["shredded"]["keys_destroyed"] == 2
    assert m["link"]["status"] == "DELETED" and m["recipients"] == [CLINICIAN]
    # nothing is left to decrypt, and the record holds neither the opening nor the link to the token
    assert not vault.has_copy(c.consent_id) and vault.key_store.key_ids(c.consent_id) == {}
    stored = _stored(c.consent_id)
    assert stored["revoked"] and stored["state"] == "REVOKED" and stored["revoked_by"] == patient
    assert not stored["commitment_opening"] and not stored["commitment"] and not stored["token_id"]
    evidence = revocation_service.revocation_evidence(c, retained_copy=retained)
    assert evidence["deletion"] and evidence["unintelligibility"] and evidence["notification"] and evidence["link_deleted"]
    assert evidence["retained_blobs_tested"] == 2 and evidence["retained_blobs_opened"] == []
    assert [n["consent_id"] for n in notification_service.inbox(CLINICIAN)].count(c.consent_id) == 1
    refused = _ask(c, source=_source)                                 # the request that follows
    assert refused["outcome"] == "DENIED" and refused["deny_code"] == "REVOKED" and refused["failed_checks"] == ["VL"]


def test_my_consents_shows_the_state_without_writing_it_into_the_record(app_test, patients):
    patient = patients[1]
    c = _consent(patient, trigger="Hospital admission confirmed")
    recorded = c.state
    at = _patient_screen(app_test, patient)
    assert any(m.value == "**SUSPENDED**" for m in at.markdown)       # the state at the trusted time, with SUSPENDED
    assert c.state == recorded                                        # drawing the list changes nothing in the record
    out = _ask(c, source=_source)
    assert out["outcome"] == "DENIED" and out["deny_code"] == "AWAITING-TRIGGER"
    moved = _rows(c.consent_id, "CONDITION_CHECK")                    # so the move into SUSPENDED is still recorded
    assert len(moved) == 1 and moved[0]["result"] == "SUSPENDED" and moved[0]["metadata"]["deny_codes"] == ["AWAITING-TRIGGER"]


# ---- B5: the guardian's Revoke -----------------------------------------------------------------------------------------

def test_one_guardian_alone_revokes_before_majority_on_the_guardian_screen(app_test, patients):
    from services import data_vault
    patient = patients[2]
    c = _consent(patient, majority_in=3000)                           # a minor: majority lies years ahead
    assert _ask(c, source=_source)["outcome"] == "GRANTED"
    at = _guardian_screen(app_test, c.consent_id, "did:parent:B")
    assert any(x.value == "Revocation: before the patient's majority any one guardian may revoke alone. "
               "After it only the patient may revoke." for x in at.caption)
    at = _click(at, "Revoke Consent (as guardian)")
    assert any(s.value == "Consent revoked by guardian did:parent:B. One guardian may revoke alone before the patient's majority."
               for s in at.success)
    assert any(i.value == f"Consent-bound copy deleted: Observation. Keys destroyed: 1. Recipients notified: {CLINICIAN}." for i in at.info)
    assert any(i.value == f"Found consent for Patient: `{patient}` (state: REVOKED)" for i in at.info)
    assert not any("NOT anchored" in w.value for w in at.warning)     # a revoked consent is not offered for anchoring again
    assert [e["action"] for e in _rows(c.consent_id)][-3:] == ["STATE_CHECK", "WITHDRAWAL_NOTIFICATION", "REVOKE_CONSENT"]
    revoke = _rows(c.consent_id, "REVOKE_CONSENT")[-1]
    m = revoke["metadata"]
    assert (revoke["result"], revoke["actor_did"], revoke["actor_role"]) == ("SUCCESS", "did:parent:B", "Guardian")
    assert (m["revoker_role"], m["basis"], m["after_majority"], m["complete"]) == ("Guardian", "one guardian before majority", False, True)
    assert _rows(c.consent_id, "STATE_CHECK")[-1]["metadata"]["requested_by"] == "did:parent:B"
    assert not data_vault.default_vault().has_copy(c.consent_id) and _stored(c.consent_id)["revoked_by"] == "did:parent:B"
    # the control stays for a revoked consent, and the second request is answered and changes nothing
    at = _click(at, "Revoke Consent (as guardian)")
    assert any(i.value == "This consent is already revoked." for i in at.info)
    assert _rows(c.consent_id, "REVOKE_CONSENT")[-1]["metadata"]["revocation"] == "ALREADY_REVOKED"


def test_guardian_is_refused_after_majority_and_after_the_take_over_and_the_refusal_is_recorded(app_test, patients):
    from database import consent_db
    patient = patients[3]
    c = _consent(patient, majority_in=-1)                             # the patient turned eighteen yesterday
    at = _guardian_screen(app_test, c.consent_id, "did:parent:A")
    assert any(i.value == f"Found consent for Patient: `{patient}` (state: SUSPENDED)" for i in at.info)
    at = _click(at, "Revoke Consent (as guardian)")
    assert any(e.value == f"Revocation refused: {AFTER_MAJORITY}." + RECORDED for e in at.error)
    assert "GUARDIAN-AFTER-MAJORITY" not in _page_text(at)            # the reason code stays in the ledger
    denied = _rows(c.consent_id, "REVOKE_CONSENT")[-1]
    assert (denied["result"], denied["actor_did"], denied["actor_role"]) == ("DENIED", "did:parent:A", "Guardian")
    assert denied["metadata"]["reason"] == "GUARDIAN-AFTER-MAJORITY" and denied["metadata"]["after_majority"] is True
    assert not _stored(c.consent_id)["revoked"]                       # nothing was revoked
    # the patient takes the consent over, and the guardian asks again on the consent that was replaced
    _click(_patient_screen(app_test, patient), key=f"tr_{c.consent_id}")
    successor = consent_db.get(consent_db.get(c.consent_id).successor_id)
    at = _guardian_screen(app_test, c.consent_id, "did:parent:A")
    assert any(i.value == f"Found consent for Patient: `{patient}` (state: REVOKED)" for i in at.info)
    assert "Revoke Consent (as guardian)" in _labels(at)              # offered for a re-issued consent as well
    at = _click(at, "Revoke Consent (as guardian)")
    assert any(e.value == f"Revocation refused: {AFTER_MAJORITY}." + RECORDED for e in at.error)
    denied = _rows(c.consent_id, "REVOKE_CONSENT")[-1]
    assert denied["result"] == "DENIED" and denied["metadata"]["reason"] == "GUARDIAN-AFTER-MAJORITY"
    assert denied["metadata"]["successor_id"] == successor.consent_id
    # the re-issued consent offers only the patient in the selector, and it stays ACTIVE
    at = _guardian_screen(app_test, successor.consent_id)
    assert list([s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0].options) == [patient]
    assert any(i.value == f"Found consent for Patient: `{patient}` (state: ACTIVE)" for i in at.info)
    assert not _rows(successor.consent_id, "REVOKE_CONSENT")


def test_patient_who_revokes_the_reissued_consent_on_the_guardian_screen_is_named_as_the_patient(app_test, patients):
    from database import consent_db
    patient = patients[17]
    c = _consent(patient, majority_in=-1)                             # the patient turned eighteen yesterday
    _click(_patient_screen(app_test, patient), key=f"tr_{c.consent_id}")
    successor = consent_db.get(consent_db.get(c.consent_id).successor_id)
    # the patient is the sole guardian of the re-issued consent, so the selector of the Guardian screen offers her
    at = _guardian_screen(app_test, successor.consent_id, patient)
    at = _click(at, "Revoke Consent (as guardian)")
    said = [s.value for s in at.success]
    assert [line for line in said if line.startswith("Consent revoked by")] == [f"Consent revoked by the patient {patient}."]
    assert not any("guardian" in line or "before the patient's majority" in line for line in said)
    assert any(s == "Consent revoked (local ledger)." for s in said)  # the lines of the revocation follow, as for a guardian
    assert any(i.value == f"Found consent for Patient: `{patient}` (state: REVOKED)" for i in at.info)
    revoke = _rows(successor.consent_id, "REVOKE_CONSENT")[-1]
    m = revoke["metadata"]
    assert (revoke["result"], revoke["actor_did"], revoke["actor_role"]) == ("SUCCESS", patient, "Patient")
    assert (m["revoker_role"], m["basis"], m["after_majority"], m["complete"]) == ("Patient", "patient", True, True)


def test_refused_revocation_and_unfinished_transition_are_explained_in_plain_words():
    from services import capacity_service as cap, revocation_service as rev
    assert rev.refusal_words(rev.REFUSED_GUARDIAN_AFTER_MAJORITY) == AFTER_MAJORITY
    assert rev.refusal_words(rev.REFUSED_FORMER_GUARDIAN) == "a guardian of the replaced consent cannot revoke the re-issued consent"
    assert rev.refusal_words(rev.REFUSED_NOT_A_PARTY) == "this identifier is neither the patient nor a guardian of this consent"
    assert rev.refusal_words(rev.REFUSED_SIGNATURE_INVALID) == "the request is not signed by the key of the revoker"
    assert rev.refusal_words(rev.REFUSED_SUPERSEDED) == "this consent was re-issued: revoke the re-issued consent"
    assert set(rev.REFUSAL_WORDS) == {rev.REFUSED_NOT_A_PARTY, rev.REFUSED_FORMER_GUARDIAN, rev.REFUSED_GUARDIAN_AFTER_MAJORITY,
                                      rev.REFUSED_SIGNATURE_INVALID, rev.REFUSED_SUPERSEDED}
    assert rev.pending_words(["onchain_revoke", "link_deletion", "notification:did:hospital:001"]) == \
        "on-chain revoke, link deletion, notification of did:hospital:001"
    assert cap.outcome_words({"status": cap.REFUSED, "reason": cap.NO_TRANSITION_DUE}) == "The consent was not re-issued: no transition is due."
    assert cap.outcome_words({"status": cap.REFUSED, "reason": cap.TOKEN_PENDING}) == \
        "The consent was not re-issued: its own token is not confirmed yet. Try again after the anchoring."
    assert cap.outcome_words({"status": cap.REFUSED, "reason": cap.PATIENT_SIGNATURE_INVALID}) == \
        "The consent was not re-issued: the patient's signature or record could not be verified."
    assert cap.outcome_words({"status": cap.MINT_FAILED, "error": "out of gas"}).endswith("Try again. (out of gas)")
    assert "click again to submit it" in cap.outcome_words({"status": cap.REVOKE_PENDING, "reason": cap.REVOKE_FAILED})
    # no reason code of a service is among the words
    shown = list(rev.REFUSAL_WORDS.values()) + [cap.outcome_words({"status": cap.REFUSED, "reason": r}) for r in
                                                (cap.CONSENT_REVOKED, cap.ALREADY_TRANSITIONED, cap.SUCCESSOR_MISMATCH)]
    assert not any(re.search(r"[A-Z]{3,}[-_][A-Z]", words) for words in shown)


# ---- B5: the notice on the clinician screen -----------------------------------------------------------------------------

def test_clinician_screen_shows_the_withdrawal_notice_to_the_recipient_only(app_test, patients):
    from services import notification_service
    patient = patients[4]
    c = _consent(patient, scope=["Observation", "Medication"])
    assert _ask(c, scope=["Medication"], source=_source)["outcome"] == "GRANTED"
    other = _consent(patient)                                         # another consent, on whose page the notice is read
    at = _clinician_screen(app_test, other.consent_id)
    before = len(notification_service.inbox(CLINICIAN))
    assert [e.label for e in at.expander] == ([f"Withdrawal notices for this clinician ({before})"] if before else [])
    _click(_patient_screen(app_test, patient), key=f"rv_{c.consent_id}")
    at = _clinician_screen(app_test, other.consent_id)
    box = [e for e in at.expander if e.label == f"Withdrawal notices for this clinician ({before + 1})"]
    assert len(box) == 1
    lines = [m.value for m in box[0].markdown]
    assert any(line.startswith(f"Consent `{c.consent_id}` - withdrawn at ") and
               line.endswith(" - modules received: Medication - releases: 1") for line in lines)
    assert any("has been withdrawn" in x.value and "is not recalled by this system" in x.value for x in box[0].caption)
    # a clinician who received nothing under the consent has no notice of it
    at = _clinician_screen(app_test, other.consent_id, REGISTRAR)
    assert not any(c.consent_id in m.value for e in at.expander for m in e.markdown)
    assert c.consent_id not in [n["consent_id"] for n in notification_service.inbox(REGISTRAR)]


# ---- B5 on chain: the revoke of ConsentSBTv4 ---------------------------------------------------------------------------

def test_patient_revoke_in_on_chain_mode_revokes_the_token_and_changes_the_revocation_root(app_test, onchain, monkeypatch, patients):
    from web3.logs import DISCARD
    patient = patients[5]
    _mock_verifier(onchain, monkeypatch)
    c = _consent(patient)
    token = _anchored(c)["token_id"]
    assert _ask(c, source=_source)["outcome"] == "GRANTED"            # verified on chain (the mock), so there is a recipient
    root = onchain.token.revocation_root()
    assert onchain.token.check_valid(token) is True
    at = _click(_patient_screen(app_test, patient), key=f"rv_{c.consent_id}")
    rows = _rows(c.consent_id)
    assert [e["action"] for e in rows][-4:] == ["STATE_CHECK", "ONCHAIN_REVOKE", "WITHDRAWAL_NOTIFICATION", "REVOKE_CONSENT"]
    check, onchain_revoke, _, revoke = rows[-4:]
    assert check["metadata"]["time"]["source"] == "block-timestamp" and check["metadata"]["lifecycle"]["target"] == "REVOKED"
    receipt = onchain.w3.eth.get_transaction_receipt(onchain_revoke["tx_hash"])
    assert (onchain_revoke["result"], receipt["status"], receipt["blockNumber"]) == ("SUCCESS", 1, onchain_revoke["block_number"])
    assert receipt["to"] == onchain.stack["token"] and onchain_revoke["metadata"]["gas_used"] == receipt["gasUsed"]
    (event,) = onchain.token.contract.events.ConsentRevoked().process_receipt(receipt, errors=DISCARD)
    assert dict(event["args"]) == {"tokenId": token} and len(receipt["logs"]) == 1
    # the token is not valid any more and the revocation root has moved to the root the record holds
    assert onchain.token.check_valid(token) is False and onchain.token.consent_of(token)["revoked"] is True
    assert onchain.token.revocation_root() != root and onchain_revoke["metadata"]["revocation_root"] == onchain.token.revocation_root()
    assert "token_id" not in onchain_revoke["metadata"]               # the record names the transaction, not the token
    m = revoke["metadata"]
    assert m["onchain"]["status"] == "SUCCESS" and m["complete"] is True and m["time_source"] == "block-timestamp"
    assert m["link"]["status"] == "DELETED" and set(m["link"]["deleted"]) >= {"commitment_opening", "token_address", "token_id", "commitment"}
    stored = _stored(c.consent_id)
    assert not stored["token_id"] and not stored["token_address"] and not stored["commitment"]
    assert any(s.value == f"Revoked on-chain. Tx: {onchain_revoke['tx_hash']}" for s in at.success)
    assert any(x.value == f"Block {receipt['blockNumber']} - gas used {receipt['gasUsed']} - revocation root updated." for x in at.caption)
    assert not any("Etherscan" in x.value for x in at.markdown)       # the in-memory chain has no public explorer
    assert any(m.value == "REVOKED" for m in at.markdown)


def test_failed_on_chain_revoke_is_shown_as_pending_and_completed_from_the_patient_screen(app_test, onchain, monkeypatch, patients):
    from services import blockchain_service as bc
    patient = patients[6]
    c = _consent(patient)
    token = _anchored(c)["token_id"]
    working = bc.revoke_onchain

    def down(consent):
        raise ConnectionError("the node does not answer")
    monkeypatch.setattr(bc, "revoke_onchain", down)
    at = _click(_patient_screen(app_test, patient), key=f"rv_{c.consent_id}")
    assert any(w.value == "Local revoke recorded; on-chain revoke failed: the node does not answer" for w in at.warning)
    assert any(x.value == "Still pending: on-chain revoke, link deletion." for x in at.caption)
    failed = _rows(c.consent_id, "ONCHAIN_REVOKE")[-1]
    assert failed["result"] == "FAILED" and failed["tx_hash"] is None
    m = _rows(c.consent_id, "REVOKE_CONSENT")[-1]["metadata"]
    assert m["pending"] == ["onchain_revoke", "link_deletion"] and m["complete"] is False and m["shredded"]["shredded"] is True
    stored = _stored(c.consent_id)
    assert stored["revoked"] and stored["token_id"] == f"SBT-{token}" and not stored["commitment_opening"]   # the link is kept for the revoke
    assert onchain.token.check_valid(token) is True                   # the token is still valid on chain
    assert _ask(c)["deny_code"] == "REVOKED"                          # and the consent gives no access all the same
    # the row of the consent offers the completion, which submits the revoke again
    assert f"cr_{c.consent_id}" in [b.key for b in at.button]
    monkeypatch.setattr(bc, "revoke_onchain", working)
    at = _click(at, key=f"cr_{c.consent_id}")
    assert any(s.value == "Revocation completed." for s in at.success)
    assert any(s.value.startswith("Revoked on-chain. Tx: 0x") for s in at.success)
    done = _rows(c.consent_id, "REVOCATION_COMPLETION")[-1]
    assert done["result"] == "SUCCESS" and done["metadata"]["pending"] == [] and done["metadata"]["onchain"]["status"] == "SUCCESS"
    assert onchain.token.check_valid(token) is False and not _stored(c.consent_id)["token_id"]
    assert f"cr_{c.consent_id}" not in [b.key for b in at.button]


def _wait_for_anchor(cid):
    for t in threading.enumerate():
        if t.name == f"anchor-{cid[:8]}":
            t.join(timeout=60)
            assert not t.is_alive()


def test_revoke_while_the_anchoring_job_runs_stays_pending_and_the_job_revokes_the_token_it_minted(app_test, onchain, monkeypatch, patients):
    from services import blockchain_service as bc, revocation_service
    patient = patients[13]
    c = _consent(patient, approvals=["did:parent:A"], token=False, majority_in=3000)
    gate, mint = threading.Event(), bc.mint_consent

    def held_mint(consent):                                           # the job runs, and its mint is not on chain yet
        gate.wait(60)
        return mint(consent)
    monkeypatch.setattr(bc, "mint_consent", held_mint)
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:B"), "Sign Consent via VC")
    assert any("Anchoring on" in i.value for i in at.info) and _stored(c.consent_id)["token_id"] == f"SBT-LOCAL-{c.consent_id[:8]}"
    # the other guardian revokes while the anchoring job is still under way
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:A"), "Revoke Consent (as guardian)")
    assert any(w.value == "Local revoke recorded; on-chain revoke failed: the mint of this consent is not confirmed on chain yet"
               for w in at.warning)
    assert any(x.value == "Still pending: on-chain revoke, link deletion." for x in at.caption)
    assert not any(s.value == "Consent revoked (local ledger)." for s in at.success)
    revoke = _rows(c.consent_id, "REVOKE_CONSENT")[-1]
    m = revoke["metadata"]
    assert revoke["result"] == "SUCCESS" and m["complete"] is False and m["pending"] == ["onchain_revoke", "link_deletion"]
    assert m["onchain"]["status"] == "FAILED" and m["link"]["status"] == "DEFERRED" and m["shredded"]["shredded"] is True
    stored = _stored(c.consent_id)
    assert stored["revoked"] and stored["commitment"] and not stored["commitment_opening"]     # the link is kept for the revoke
    assert revocation_service.pending_steps(c.consent_id) == ["onchain_revoke", "link_deletion"]
    assert f"cr_{c.consent_id}" in [b.key for b in _patient_screen(app_test, patient).button]   # Complete Revocation is offered
    assert onchain.token.consent_count() == 0 and _ask(c)["deny_code"] == "REVOKED"
    # the mint arrives: the job records it and revokes the token at once
    gate.set()
    _wait_for_anchor(c.consent_id)
    (minted,) = _rows(c.consent_id, "ONCHAIN_MINT")
    token = minted["metadata"]["token_id"]
    assert minted["result"] == "SUCCESS" and onchain.token.consent_count() == 1
    assert onchain.token.check_valid(token) is False and onchain.token.consent_of(token)["revoked"] is True
    assert [e["result"] for e in _rows(c.consent_id, "ONCHAIN_REVOKE")] == ["FAILED", "SUCCESS"]
    done = _rows(c.consent_id, "REVOCATION_COMPLETION")[-1]
    assert done["result"] == "SUCCESS" and done["metadata"]["pending"] == [] and done["metadata"]["onchain"]["status"] == "SUCCESS"
    assert done["metadata"]["time_source"] == "block-timestamp" and done["metadata"]["link"]["status"] == "DELETED"
    stored = _stored(c.consent_id)
    assert stored["revoked"] and not stored["token_id"] and not stored["token_address"] and not stored["commitment"]
    assert revocation_service.pending_steps(c.consent_id) == []
    at = _guardian_screen(app_test, c.consent_id, "did:parent:A")
    assert any(i.value == f"Found consent for Patient: `{patient}` (state: REVOKED)" for i in at.info)
    assert not any("Already anchored" in s.value for s in at.success)
    assert f"cr_{c.consent_id}" not in [b.key for b in _patient_screen(app_test, patient).button]


def test_revoke_finds_a_mint_that_is_on_chain_and_not_recorded_yet_and_revokes_its_token(app_test, onchain, monkeypatch, patients):
    from services import blockchain_service as bc, revocation_service
    patient = patients[14]
    c = _consent(patient, approvals=["did:parent:A"], token=False, majority_in=3000)
    gate, mined = threading.Event(), threading.Event()

    def confirmed_late(consent):                                      # the mint is in a block, and its receipt has not come back
        address, _ = bc.chain_v4.derive_consent_address(consent.patient_did, consent.consent_id)
        receipt = bc.token_client().mint_consent(address, consent.commitment)
        mined.set()
        gate.wait(60)
        consent.token_address = receipt["token_address"]
        return receipt
    monkeypatch.setattr(bc, "mint_consent", confirmed_late)
    _click(_guardian_screen(app_test, c.consent_id, "did:parent:B"), "Sign Consent via VC")
    assert mined.wait(60) and onchain.token.consent_count() == 1 and _stored(c.consent_id)["token_id"] == f"SBT-LOCAL-{c.consent_id[:8]}"
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:A"), "Revoke Consent (as guardian)")
    assert any(s.value.startswith("Revoked on-chain. Tx: 0x") for s in at.success)
    assert not any(s.value == "Consent revoked (local ledger)." for s in at.success)
    m = _rows(c.consent_id, "REVOKE_CONSENT")[-1]["metadata"]
    assert m["onchain"]["status"] == "SUCCESS" and m["complete"] is True and m["pending"] == []
    assert onchain.token.check_valid(1) is False
    gate.set()
    _wait_for_anchor(c.consent_id)
    # the receipt of the mint arrives after the revocation: nothing of the token is left in the revoked record
    assert [e["result"] for e in _rows(c.consent_id, "ONCHAIN_MINT")] == ["SUCCESS"]
    assert [e["result"] for e in _rows(c.consent_id, "ONCHAIN_REVOKE")] == ["SUCCESS"]       # one revoke, not two
    stored = _stored(c.consent_id)
    assert stored["revoked"] and not stored["token_id"] and not stored["token_address"] and not stored["commitment"]
    assert _rows(c.consent_id, "REVOCATION_COMPLETION")[-1]["result"] == "SUCCESS"
    assert revocation_service.pending_steps(c.consent_id) == [] and onchain.token.check_valid(1) is False


def test_revoke_of_a_consent_whose_mint_no_job_recorded_records_the_mint_and_revokes_on_chain(app_test, onchain, patients):
    from services import blockchain_service as bc
    patient = patients[15]
    c = _consent(patient, majority_in=3000)                           # the local token, and no anchoring job in this process
    address, _ = bc.chain_v4.derive_consent_address(c.patient_did, c.consent_id)
    sent = bc.token_client().mint_consent(address, c.commitment)      # the mint is on chain, the record does not know it
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:A"), "Revoke Consent (as guardian)")
    assert any(s.value.startswith("Revoked on-chain. Tx: 0x") for s in at.success)
    (minted,) = _rows(c.consent_id, "ONCHAIN_MINT")
    assert minted["tx_hash"] == sent["tx_hash"] and minted["metadata"]["reconciled_from_chain"] is True
    assert [e["action"] for e in _rows(c.consent_id)][-4:] == ["STATE_CHECK", "ONCHAIN_MINT", "ONCHAIN_REVOKE", "REVOKE_CONSENT"]
    assert onchain.token.check_valid(sent["token_id"]) is False and not _stored(c.consent_id)["token_id"]
    # a consent with a local token and no mint on chain is revoked in the local ledger, as before
    other = _consent(patients[16], majority_in=3000)
    at = _click(_guardian_screen(app_test, other.consent_id, "did:parent:A"), "Revoke Consent (as guardian)")
    assert any(s.value == "Consent revoked (local ledger)." for s in at.success)
    assert _rows(other.consent_id, "REVOKE_CONSENT")[-1]["metadata"]["onchain"]["status"] == "NOT_APPLICABLE"
    assert not _rows(other.consent_id, "ONCHAIN_REVOKE")


def test_no_consent_is_revoked_or_taken_over_while_the_time_of_the_chain_cannot_be_read(app_test, onchain, monkeypatch, patients):
    from services import blockchain_service as bc
    patient = patients[7]
    c = _consent(patient, majority_in=-1)
    _anchored(c)

    class Down:                                                       # a node that does not answer
        class w3:
            class eth:
                @staticmethod
                def get_block(_):
                    raise ConnectionError("the node does not answer")
    monkeypatch.setattr(bc, "token_client", lambda read_only=False: Down())
    at = _patient_screen(app_test, patient)
    assert any(e.value.startswith("The time of the chain could not be read (provider failed: the node does not answer). "
                                  "In on-chain mode the server clock is not used") for e in at.error)
    assert not {f"rv_{c.consent_id}", f"tr_{c.consent_id}"} & {b.key for b in at.button}
    at = _guardian_screen(app_test, c.consent_id)
    assert "Revoke Consent (as guardian)" not in _labels(at)
    assert any(x.value == "The time of the chain could not be read, so a revocation cannot be requested now." for x in at.caption)
    assert not _rows(c.consent_id, "REVOKE_CONSENT") and not _rows(c.consent_id, "STATE_CHECK")


def test_older_contract_mode_keeps_the_revoke_of_consentsbtv3(app_test, monkeypatch, patients):
    from blockchain import onchain_ui
    from database import consent_db
    from services import blockchain_service as bc
    patient = patients[8]
    c = _consent(patient)
    c.token_id = "SBT-4"                                              # a token of the older contract: no per-consent address
    consent_db.update(c)
    revoked = []

    class Client:                                                     # stands for the client of ConsentSBTv3
        class w3:
            class eth:
                @staticmethod
                def get_block(_):
                    return {"timestamp": int(datetime.now().timestamp()) - 20, "number": 77}

        def revoke(self, token_id):
            revoked.append(token_id)
            return {"tx_hash": "0x" + "ab" * 32, "status": 1, "block_number": 78, "gas_used": 30000, "explorer_tx": ""}

    class Chain:
        ConsentContract = Client

        @staticmethod
        def is_configured():
            return True

        @staticmethod
        def explorer_tx(tx_hash):
            return "https://sepolia.etherscan.io/tx/" + tx_hash
    monkeypatch.setattr(bc, "chain", Chain)                           # CONTRACT_ADDRESS without CONTRACT_V4_ADDRESS
    monkeypatch.setattr(onchain_ui, "_cached_status", lambda: {"mode": "onchain", "chain_id": 1337, "is_sepolia": False, "block": 77,
                                                               "balance_eth": 1.0, "contract": "0x" + "11" * 20,
                                                               "contract_has_code": True, "signer_is_owner": True})
    assert bc.onchain_enabled() and not bc.v4_enabled() and not bc.has_chain_token(c)
    at = _click(_patient_screen(app_test, patient), key=f"rv_{c.consent_id}")
    assert revoked == [4]
    row = _rows(c.consent_id, "ONCHAIN_REVOKE")[-1]
    assert (row["result"], row["tx_hash"], row["block_number"]) == ("SUCCESS", "0x" + "ab" * 32, 78)
    assert any(x.value == "Block 78 - gas used 30000." for x in at.caption)       # the older contract keeps no revocation root
    assert _rows(c.consent_id, "REVOKE_CONSENT")[-1]["metadata"]["time_source"] == "block-timestamp"


# ---- B6: the take-over at majority -------------------------------------------------------------------------------------

def test_take_over_in_demo_mode_reissues_a_committed_consent_signed_by_the_patient_over_its_commitment(app_test, patients):
    from database import consent_db
    from services import commitment_service, identity_service as ids
    patient = patients[9]
    c = _consent(patient, scope=["Observation", "Medication"], majority_in=-1)
    at = _patient_screen(app_test, patient)
    assert any(m.value == "**SUSPENDED**" for m in at.markdown)
    assert any(x.value == f"`{c.consent_id[:8]}...`: the patient has reached the age of majority. "
               "The consent is suspended until the patient takes it over." for x in at.caption)
    before = len(_rows(c.consent_id))
    at = _click(at, key=f"tr_{c.consent_id}")
    old = consent_db.get(c.consent_id)
    new = consent_db.get(old.successor_id)
    assert any(s.value == f"Consent re-issued to the patient: {new.consent_id} (guardian set: the patient, threshold 1)." for s in at.success)
    assert any(m.value == f"RE-ISSUED as `{new.consent_id[:8]}...`" for m in at.markdown) and any(m.value == "**ACTIVE**" for m in at.markdown)
    assert f"tr_{c.consent_id}" not in [b.key for b in at.button] and f"rv_{new.consent_id}" in [b.key for b in at.button]
    # the old consent: the transition to REVOKED was checked first, then the consent was retired
    assert [e["action"] for e in _rows(c.consent_id)[before:]] == ["STATE_CHECK", "CAPACITY_TRANSITION"]
    check, transition = _rows(c.consent_id)[before:]
    assert (check["metadata"]["lifecycle"]["target"], check["metadata"]["lifecycle"]["VALID"], check["result"]) == ("REVOKED", True, "SUSPENDED")
    assert check["metadata"]["requested_by"] == patient and transition["result"] == "SUCCESS"
    assert old.revoked and old.revoked_by == "CAPACITY_TRANSITION"
    # the re-issued consent: the patient alone, threshold one, committed and signed over the commitment
    assert (new.guardian_dids, new.threshold, new.signatures, new.predecessor_id) == ([patient], 1, [patient], c.consent_id)
    assert new.commitment and commitment_service.verify_opening(new.commitment, new.commitment_opening)
    assert commitment_service.opening_matches_consent(new, new.commitment_opening) and new.commitment != c.commitment
    entry = _stored(new.consent_id)["signature_data"][patient]
    assert entry["version"] == 2 and ids.verify_signature_v2(patient, new.consent_id, new.commitment, entry["signature"]) is True
    assert ids.verify_signature(patient, new.consent_id, entry["signature"]) is False       # not the older form
    assert new.token_id == f"SBT-LOCAL-{new.consent_id[:8]}"
    assert [e["action"] for e in _rows(new.consent_id)] == ["SIGN_CONSENT", "MINT_SBT"]
    assert _ask(new, scope=["Medication"], source=_source)["outcome"] == "GRANTED"          # the re-issued consent gives access
    assert _ask(old, source=_source)["deny_code"] == "REVOKED"                              # the replaced one gives none


def test_take_over_in_on_chain_mode_mints_the_reissue_on_consentsbtv4_and_revokes_the_old_token(app_test, onchain, patients):
    from database import consent_db
    from services import request_service
    patient = patients[10]
    c = _consent(patient, majority_in=-1)
    old_token = _anchored(c)["token_id"]
    count, root = onchain.token.consent_count(), onchain.token.revocation_root()
    at = _click(_patient_screen(app_test, patient), key=f"tr_{c.consent_id}")
    old = consent_db.get(c.consent_id)
    new = consent_db.get(old.successor_id)
    assert new is not None and new.token_id == f"SBT-{count + 1}" and new.token_address and new.token_address != c.token_address
    # on chain the transition is one mint and one revocation
    assert onchain.token.consent_count() == count + 1
    assert onchain.token.consent_of(count + 1) == {"commitment": int(new.commitment, 16), "revoked": False}
    assert onchain.token.contract.functions.ownerOf(count + 1).call() == new.token_address
    assert onchain.token.check_valid(count + 1) is True and onchain.token.check_valid(old_token) is False
    assert onchain.token.revocation_root() != root
    (mint,) = _rows(new.consent_id, "ONCHAIN_MINT")
    revoke = _rows(c.consent_id, "ONCHAIN_REVOKE")[-1]
    assert mint["result"] == "SUCCESS" and onchain.w3.eth.get_transaction_receipt(mint["tx_hash"])["status"] == 1
    assert revoke["result"] == "SUCCESS" and onchain.w3.eth.get_transaction_receipt(revoke["tx_hash"])["to"] == onchain.stack["token"]
    assert mint["block_number"] < revoke["block_number"]              # minted first, then the old token revoked
    assert not _rows(new.consent_id, "MINT_SBT")                      # no local token for the re-issue
    actions = [e["action"] for e in _rows(c.consent_id)]
    assert actions[-3:] == ["STATE_CHECK", "ONCHAIN_REVOKE", "CAPACITY_TRANSITION"]
    assert _rows(c.consent_id, "STATE_CHECK")[-1]["metadata"]["time"]["source"] == "block-timestamp"
    transition = _rows(c.consent_id, "CAPACITY_TRANSITION")[-1]
    assert transition["result"] == "SUCCESS" and transition["metadata"]["onchain"] == ["mint", "revoke"]
    assert (transition["metadata"]["mint_tx"], transition["metadata"]["revoke_tx"]) == (mint["tx_hash"], revoke["tx_hash"])
    assert _stored(new.consent_id)["signature_data"][patient]["version"] == 2
    assert any(s.value == f"Consent re-issued to the patient: {new.consent_id} (guardian set: the patient, threshold 1)." for s in at.success)
    assert any(x.value == f"New token #{count + 1} minted in block {mint['block_number']} (tx {mint['tx_hash']}). "
               f"Old token revoked in block {revoke['block_number']} (tx {revoke['tx_hash']})." for x in at.caption)
    # the decision rule allows the named clinician on the re-issued consent at the time of the chain
    t, _ = request_service.decision_time()
    assert request_service.decide(new, CLINICIAN, ["Observation"], "Treatment", "AU", t["time"])["ALLOW"] is True
    assert request_service.decide(old, CLINICIAN, ["Observation"], "Treatment", "AU", t["time"])["DENY"] == ["REVOKED"]


def test_take_over_waits_in_on_chain_mode_until_the_token_of_the_old_consent_is_confirmed(app_test, onchain, patients):
    from database import consent_db
    patient = patients[11]
    c = _consent(patient, majority_in=-1)                             # threshold met, the mint is not confirmed yet
    count = onchain.token.consent_count()
    at = _click(_patient_screen(app_test, patient), key=f"tr_{c.consent_id}")
    assert any(w.value == "The consent was not re-issued: its own token is not confirmed yet. Try again after the anchoring."
               for w in at.warning)
    assert consent_db.get(c.consent_id).successor_id is None and onchain.token.consent_count() == count
    assert not _rows(c.consent_id, "CAPACITY_TRANSITION") and f"tr_{c.consent_id}" in [b.key for b in at.button]
    _anchored(c)                                                      # once the token is on chain the take-over goes through
    at = _click(at, key=f"tr_{c.consent_id}")
    assert consent_db.get(c.consent_id).successor_id and onchain.token.consent_count() == count + 2


def test_failed_revoke_of_the_old_token_is_submitted_again_by_the_same_click(app_test, onchain, monkeypatch, patients):
    from database import consent_db
    from services import blockchain_service as bc
    patient = patients[12]
    c = _consent(patient, majority_in=-1)
    old_token = _anchored(c)["token_id"]
    working = bc.revoke_onchain

    def down(consent):
        raise ConnectionError("the node does not answer")
    monkeypatch.setattr(bc, "revoke_onchain", down)
    at = _click(_patient_screen(app_test, patient), key=f"tr_{c.consent_id}")
    assert any(w.value == "The consent is re-issued and the old consent gives no access any more. The revocation of its "
               "token on chain failed: click again to submit it." for w in at.warning)
    old = consent_db.get(c.consent_id)
    new = consent_db.get(old.successor_id)
    assert old.revoked and new.token_id.startswith("SBT-") and onchain.token.check_valid(old_token) is True
    assert _rows(c.consent_id, "CAPACITY_TRANSITION")[-1]["result"] == "REVOKE-PENDING"
    assert any(m.value == f"RE-ISSUED as `{new.consent_id[:8]}...`" for m in at.markdown)
    assert f"tr_{c.consent_id}" in [b.key for b in at.button]         # the same click is offered again
    monkeypatch.setattr(bc, "revoke_onchain", working)
    at = _click(at, key=f"tr_{c.consent_id}")
    assert onchain.token.check_valid(old_token) is False and _rows(c.consent_id, "CAPACITY_TRANSITION")[-1]["result"] == "SUCCESS"
    assert len(_rows(new.consent_id, "ONCHAIN_MINT")) == 1            # nothing is minted a second time
    assert f"tr_{c.consent_id}" not in [b.key for b in at.button]
    assert any(x.value.startswith("Old token revoked in block ") for x in at.caption)
