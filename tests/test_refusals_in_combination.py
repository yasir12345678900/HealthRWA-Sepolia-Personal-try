"""Refusals in which more than one check fails, and requests that are repeated, as the running application gives them
(Streamlit's test runner, no browser).

Each test makes its requests on the screens and asserts the failed checks, the one deny code of Section 6.3.1 that the
screen and the DATA_ACCESS record show, the order of the codes that the record keeps, and that no other word stands in
a deny code field: a consent that waits for its trigger, a trigger and a capacity transition together, a request after
the expiry of a consent that was never issued, the three conditions of VP failing together, a revoked consent with a
request outside its scope and with a requester who fails VI, a second revocation in demo mode, a consent whose
token was revoked on chain without the application, a second request for a revocation whose on-chain step had
failed, and a proof reference that names the verification of another request (tools/verify_poc.py).

The chain of the last tests is an in-memory EVM with the real bytecode of blockchain/abi (no network, no Sepolia). The
key of the owner is derived from a label in this file: it is a test key and holds nothing. The last test replaces the
Groth16 verifier by MockDecisionVerifier, which proves nothing."""
import copy
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_KEY_LABEL = "halah refusals in combination test owner"    # the owner key is derived from this label (not a secret)
PATIENT = "did:patient:y"
CLINICIAN, REGISTRAR = "did:hospital:001", "did:hospital:002"
G = ["did:parent:A", "did:parent:B"]
NINE = ("OUT-OF-SCOPE", "PURPOSE-MISMATCH", "CONTEXT-MISMATCH", "PRE-VALIDITY", "POST-VALIDITY", "AWAITING-TRIGGER",
        "TRANSITION-PENDING", "EXPIRED", "REVOKED")
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
    return SimpleNamespace(w3=w3, v4=v4, tester=w3.provider.ethereum_tester, key=key, key_hex=Web3.to_hex(key),
                           stack=stack, chain_id=w3.eth.chain_id)


@pytest.fixture()
def onchain(base, monkeypatch):
    """The application in on-chain mode against the in-memory chain, in its fresh state. The sidebar status is read once."""
    from blockchain import onchain_ui
    from services import blockchain_service as bc
    snapshot = base.tester.take_snapshot()
    monkeypatch.setenv("CHAIN_ID", str(base.chain_id))
    monkeypatch.setenv("CONTRACT_V4_ADDRESS", base.stack["token"])
    monkeypatch.setenv("VERIFIER_ADDRESS", base.stack["verifier"])
    monkeypatch.setenv("PRIVATE_KEY", base.key_hex)
    monkeypatch.setattr(bc, "token_client", lambda read_only=False: base.v4.ConsentContractV4(
        w3=base.w3, address=base.stack["token"], private_key=None if read_only else base.key, read_only=read_only))
    monkeypatch.setattr(bc, "verifier_client", lambda read_only=False: base.v4.DecisionVerifierContract(
        w3=base.w3, address=base.stack["verifier"], private_key=None if read_only else base.key, read_only=read_only))
    status = bc.chain_status()
    monkeypatch.setattr(onchain_ui, "_cached_status", lambda: status)
    base.token = bc.token_client(read_only=True)
    yield base
    base.tester.revert_to_snapshot(snapshot)


def _born(days_to_majority):
    """A date of birth whose eighteenth birthday lies `days_to_majority` days from today (negative: in the past)."""
    day = datetime.now().date() + timedelta(days=days_to_majority)
    try:
        return day.replace(year=day.year - 18)
    except ValueError:                                                # 29 February
        return day.replace(year=day.year - 18, day=28)


def _consent(scope=("Observation",), approvals=None, token=True, start=None, expiry=None, majority_in=None, trigger=None):
    """A consent as the form and the guardian screen leave it: committed, approved over the commitment, and with the
    local token once the threshold is met. `majority_in` schedules the transition at majority as the form does while
    the patient is a minor, and `trigger` attaches a conditional trigger as the form does."""
    from database import consent_db
    from services import capacity_service, commitment_service, identity_service as ids, trigger_service
    from services.consent_service import create_consent
    c = create_consent(PATIENT, CLINICIAN, list(G), list(scope), "Treatment",
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
    if trigger:
        trigger_service.add_trigger(c, trigger, attester_role="doctor", actor_did=PATIENT, actor_role="Patient")
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


def _guardian_screen(AppTest, cid, did):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Guardian").run()
    [t for t in at.text_input if t.label == "Enter Target Consent ID"][0].set_value(cid).run()
    [s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0].set_value(did).run()
    return at


def _clinician_screen(AppTest, cid, requester=CLINICIAN, purpose=None, context=None, scope=("Observation",)):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Clinician").run()
    [t for t in at.text_input if t.label == "Enter Authorised Consent ID"][0].set_value(cid).run()
    [t for t in at.text_input if t.label == "Your Clinician DID (requester)"][0].set_value(requester).run()
    if context is not None:
        [s for s in at.selectbox if s.label == "Request Context (jurisdiction code)"][0].set_value(context).run()
    if purpose is not None:
        [s for s in at.selectbox if s.label == "Purpose of this request"][0].set_value(purpose).run()
    [m for m in at.multiselect if m.label == "Select Request Scope"][0].set_value(list(scope)).run()
    return at


def _click(at, label):
    [b for b in at.button if b.label.startswith(label)][0].click().run()
    assert not at.exception
    return at


def _failed(at):
    return [name for name, value in at.table[0].value.to_dict("records")[0].items() if value == "FAIL" and name != "ALLOW"]


def _rows(cid, action=None):
    from database import audit_db
    return [e for e in audit_db.get() if e["consent_id"] == cid and (action is None or e["action"] == action)]


def _last(cid):
    """The two records of the last submitted request: (STATE_CHECK, DATA_ACCESS)."""
    return _rows(cid, "STATE_CHECK")[-1], _rows(cid, "DATA_ACCESS")[-1]


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


def _source(patient_did, scope):
    """Stands for the source record: one row for each module asked for."""
    return {module: [{"module": module, "patient": patient_did}] for module in scope}


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


def _denied(at, line):
    """The page of a refused request: the one line of the refusal, and no record data."""
    assert any(e.value == line + RECORDED for e in at.error), [e.value for e in at.error]
    assert not at.dataframe


# ---- a consent that waits: its trigger, and a trigger and a transition together ----------------------------------------

def test_request_while_the_trigger_is_awaited_is_refused_with_its_code_on_the_screen(app_test):
    c = _consent(trigger="advance directive in force")
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == ["VL"] and any(x.value == "Failed checks: VL | Deny code: AWAITING-TRIGGER" for x in at.caption)
    assert any(e.value == "Consent is not active. Current state: SUSPENDED (deny code: AWAITING-TRIGGER)" for e in at.error)
    assert not any(s.value == "Authorised Data Scope" for s in at.subheader)
    at = _click(at, "Request Data Access")
    _denied(at, "Access Denied. Failed checks: VL. Deny code: AWAITING-TRIGGER. Consent state: SUSPENDED.")
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert check["result"] == "SUSPENDED" and check["metadata"]["lifecycle"]["deny_code"] == "AWAITING-TRIGGER"
    assert (access["result"], m["deny_code"], m["deny_codes"], m["failed_checks"]) == ("DENIED", "AWAITING-TRIGGER", ["AWAITING-TRIGGER"], ["VL"])
    assert m["modules_released"] == [] and m["proof_reference"] is None and m["consent_state"] == "SUSPENDED"
    moved = _rows(c.consent_id, "CONDITION_CHECK")
    assert len(moved) == 1 and moved[0]["result"] == "SUSPENDED" and moved[0]["metadata"]["deny_codes"] == ["AWAITING-TRIGGER"]


def test_trigger_and_transition_together_show_the_trigger_code_and_the_record_keeps_both(app_test):
    c = _consent(majority_in=-1, trigger="advance directive in force")       # the patient turned eighteen yesterday
    at = _click(_clinician_screen(app_test, c.consent_id), "Request Data Access")
    _denied(at, "Access Denied. Failed checks: VL. Deny code: AWAITING-TRIGGER. Consent state: SUSPENDED.")
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert (m["deny_code"], m["deny_codes"], m["failed_checks"]) == ("AWAITING-TRIGGER", ["AWAITING-TRIGGER", "TRANSITION-PENDING"], ["VL"])
    assert check["metadata"]["DENY"] == ["AWAITING-TRIGGER", "TRANSITION-PENDING"]
    assert set(_code_fields(check) + _code_fields(access)) == {"AWAITING-TRIGGER", "TRANSITION-PENDING"}


# ---- the window of a consent that was never issued -----------------------------------------------------------------------

def test_request_after_the_expiry_of_a_consent_that_was_never_issued_reports_the_window_and_names_va(app_test):
    now = datetime.now()
    c = _consent(approvals=["did:parent:A"], token=False, start=now - timedelta(days=10), expiry=now - timedelta(days=1))
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == ["VA", "VT", "VL"]
    at = _click(at, "Request Data Access")
    # the state has no code of its own, so the window code is the one reported (Section 6.3.1)
    _denied(at, "Access Denied. Failed checks: VA, VT, VL. Deny code: POST-VALIDITY. Consent state: PENDING_SIGNATURE.")
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert check["result"] == "PENDING_SIGNATURE" and check["metadata"]["lifecycle"]["deny_code"] == "POST-VALIDITY"
    assert (m["deny_code"], m["deny_codes"], m["failed_checks"]) == ("POST-VALIDITY", ["POST-VALIDITY"], ["VA", "VT", "VL"])
    assert set(_code_fields(check) + _code_fields(access)) == {"POST-VALIDITY"}


# ---- the three conditions of VP together ---------------------------------------------------------------------------------

def test_three_failed_conditions_of_vp_are_recorded_in_the_order_of_algorithm_6_1(app_test):
    c = _consent()
    at = _clinician_screen(app_test, c.consent_id, purpose="Research", context="US", scope=["Procedure"])
    assert _failed(at) == ["VP"] and any(x.value == "Failed checks: VP | Deny code: PURPOSE-MISMATCH" for x in at.caption)
    at = _click(at, "Request Data Access")
    _denied(at, "Access Denied. Failed checks: VP. Deny code: PURPOSE-MISMATCH.")
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert (m["deny_code"], m["failed_checks"]) == ("PURPOSE-MISMATCH", ["VP"])
    assert m["deny_codes"] == ["PURPOSE-MISMATCH", "CONTEXT-MISMATCH", "OUT-OF-SCOPE"] == check["metadata"]["DENY"]
    assert (m["decision_matrix"]["VU"], m["decision_matrix"]["VX"], m["decision_matrix"]["VS"]) == (False, False, False)
    # the record carries the request as it was declared
    assert (access["actor_did"], access["scope"], access["purpose"], m["context"]) == (CLINICIAN, ["Procedure"], "Research", "US")
    assert (check["metadata"]["request_purpose"], check["metadata"]["request_scope"], check["metadata"]["context"]) == ("Research", ["Procedure"], "US")


# ---- a revoked consent: the state code stands before every other one -----------------------------------------------------

def test_revoked_consent_reports_revoked_before_the_scope_and_for_a_requester_who_fails_vi(app_test):
    from services import notification_service
    c = _consent()
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:A"), "Revoke Consent (as guardian)")
    assert any(s.value == "Consent revoked (local ledger)." for s in at.success)
    at = _click(_clinician_screen(app_test, c.consent_id, scope=["Procedure"]), "Request Data Access")
    _denied(at, "Access Denied. Failed checks: VP, VL. Deny code: REVOKED. Consent state: REVOKED.")
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert check["result"] == "REVOKED" and (m["deny_code"], m["deny_codes"], m["failed_checks"]) == ("REVOKED", ["REVOKED", "OUT-OF-SCOPE"], ["VP", "VL"])
    assert m["decision_matrix"]["VA"] is True and m["modules_released"] == []
    # a requester who is not the named clinician: VI is named, the code of the state is the one code, no state sentence
    at = _click(_clinician_screen(app_test, c.consent_id, requester=REGISTRAR), "Request Data Access")
    _denied(at, "Access Denied. Failed checks: VI, VL. Deny code: REVOKED.")
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert (access["actor_did"], m["deny_code"], m["deny_codes"], m["failed_checks"]) == (REGISTRAR, "REVOKED", ["REVOKED"], ["VI", "VL"])
    assert set(_code_fields(check) + _code_fields(access)) == {"REVOKED"}
    assert notification_service.inbox(REGISTRAR) == []               # a refused requester received nothing and is told nothing


# ---- a second revocation in demo mode ------------------------------------------------------------------------------------

def test_second_revocation_in_demo_mode_is_answered_as_already_revoked_and_changes_nothing(app_test):
    from database import db
    c = _consent(majority_in=3000)                                    # a minor: majority lies years ahead
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:A"), "Revoke Consent (as guardian)")
    assert any(s.value.startswith("Consent revoked by guardian did:parent:A.") for s in at.success)
    first = [r for r in db.all_rows("consents") if r["consent_id"] == c.consent_id][0]
    rows = len(_rows(c.consent_id))
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:B"), "Revoke Consent (as guardian)")
    assert any(i.value == "This consent is already revoked." for i in at.info)
    assert not any("revoked" in s.value.lower() for s in at.success)   # no second revocation is announced
    check, again = _rows(c.consent_id)[rows:]
    lifecycle = check["metadata"]["lifecycle"]
    assert (check["action"], lifecycle["target"], lifecycle["VALID"], lifecycle["deny_code"]) == ("STATE_CHECK", "REVOKED", False, "REVOKED")
    assert (again["action"], again["result"], again["metadata"]["revocation"]) == ("REVOKE_CONSENT", "SUCCESS", "ALREADY_REVOKED")
    stored = [r for r in db.all_rows("consents") if r["consent_id"] == c.consent_id][0]
    assert (stored["revoked_by"], stored["revoked_at"]) == ("did:parent:A", first["revoked_at"])


# ---- on chain: a token revoked without the application, and a revocation whose on-chain step had failed ----------------

def test_token_revoked_on_chain_without_the_application_gets_no_proof_and_nothing_is_released(app_test, onchain):
    c = _consent()
    token = _anchored(c)["token_id"]
    # the owner revokes the token directly on the contract: the record of the application still says ACTIVE
    onchain.v4.ConsentContractV4(w3=onchain.w3, address=onchain.stack["token"], private_key=onchain.key).revoke(token)
    blocks = onchain.w3.eth.block_number
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == [] and any(s.value == "Authorised Data Scope" for s in at.subheader)     # the record alone would allow
    at = _click(at, "Request Data Access")
    _denied(at, "Access Denied. Failed checks: proof.")
    assert any(x.value == "No proof could be made: the record of this consent does not match what the chain holds." for x in at.caption)
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert check["result"] == "ACTIVE" and m["decision_matrix"]["ALLOW"] is True
    assert (access["result"], m["deny_code"], m["deny_codes"], m["failed_checks"]) == ("DENIED", None, [], ["proof"])
    assert m["proof_reference"]["reference"]["predicates"] == ["NOT_REVOKED"] and "tx_hash" not in m["proof_reference"]
    assert m["modules_released"] == [] and m["time_source"] == "block-timestamp"
    assert _code_fields(check) == [] and _code_fields(access) == []
    assert onchain.w3.eth.block_number == blocks                      # no proof was presented and nothing was sent


def test_second_request_for_a_revocation_submits_the_on_chain_revoke_that_had_failed_and_records_it(app_test, onchain, monkeypatch):
    from services import blockchain_service as bc
    c = _consent(majority_in=3000)                                    # a minor: majority lies years ahead
    token = _anchored(c)["token_id"]
    working = bc.revoke_onchain

    def unreachable(consent):
        raise RuntimeError("the node did not answer")
    monkeypatch.setattr(bc, "revoke_onchain", unreachable)
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:A"), "Revoke Consent (as guardian)")
    assert any(w.value == "Local revoke recorded; on-chain revoke failed: the node did not answer" for w in at.warning)
    assert any(x.value == "Still pending: on-chain revoke, link deletion." for x in at.caption)
    first = _rows(c.consent_id, "REVOKE_CONSENT")[-1]["metadata"]
    assert (first["revocation"], first["complete"], first["pending"]) == ("REVOKED", False, ["onchain_revoke", "link_deletion"])
    assert onchain.token.check_valid(token) is True
    # a request in between is refused on the record, whatever the chain still says
    at = _click(_clinician_screen(app_test, c.consent_id), "Request Data Access")
    _denied(at, "Access Denied. Failed checks: VL. Deny code: REVOKED. Consent state: REVOKED.")
    # the other guardian asks again while the node answers: the step that failed is submitted and recorded
    monkeypatch.setattr(bc, "revoke_onchain", working)
    rows = len(_rows(c.consent_id))
    at = _click(_guardian_screen(app_test, c.consent_id, "did:parent:B"), "Revoke Consent (as guardian)")
    assert onchain.token.check_valid(token) is False
    check, sent, again = _rows(c.consent_id)[rows:]
    assert (check["action"], sent["action"], sent["result"], again["action"]) == ("STATE_CHECK", "ONCHAIN_REVOKE", "SUCCESS", "REVOKE_CONSENT")
    assert sent["tx_hash"] and sent["block_number"] == onchain.w3.eth.block_number
    # the screen shows the transaction that this click sent, as the Patient screen does, and announces no second revocation
    assert any(i.value == "This consent is already revoked." for i in at.info)
    assert any(s.value == f"Revoked on-chain. Tx: {sent['tx_hash']}" for s in at.success)
    assert any(x.value == f"Block {sent['block_number']} - gas used {sent['metadata']['gas_used']} - revocation root updated." for x in at.caption)
    assert not any(s.value.startswith("Consent revoked by") for s in at.success)
    m = again["metadata"]
    assert (m["revocation"], m["complete"], m["pending"], m["revoked_by"]) == ("ALREADY_REVOKED", True, [], "did:parent:A")
    assert len(_rows(c.consent_id, "ONCHAIN_REVOKE")) == 2            # the failed attempt and the one that was confirmed


# ---- the independent verification tool: a proof reference that belongs to another request ------------------------------

def test_verification_tool_refuses_a_proof_reference_that_names_the_verification_of_another_request(onchain, monkeypatch):
    from database import db
    from services import blockchain_service as bc, request_service
    from tools import verify_poc
    _mock_verifier(onchain, monkeypatch)
    c = _consent(scope=("Observation", "Medication"))
    _anchored(c)
    for module in ("Observation", "Medication"):
        assert request_service.submit_request(c, CLINICIAN, [module], "Treatment", "AU", source=_source)["outcome"] == "GRANTED"
    events = [e for e in db.all_rows("audit", "ts") if e.get("consent_id") == c.consent_id]
    consents = [r for r in db.all_rows("consents") if r["consent_id"] == c.consent_id]

    def run(rows):
        lines = []
        return verify_poc.verify_v4(bc.token_client(read_only=True), rows, consents, bc.verifier_client(read_only=True), out=lines.append), lines
    assert run(events)[0] is True
    swapped = copy.deepcopy(events)
    one, two = [e["metadata"]["proof_reference"] for e in swapped if e["action"] == "DATA_ACCESS"]
    for name in ("tx_hash", "block_number"):                          # each row names the verification of the other request
        one[name], two[name] = two[name], one[name]
    ok, lines = run(swapped)
    assert ok is False and sum("[XX]   ConsentVerified event" in line for line in lines) == 2
    assert not any("[XX]   the request tag opens to the requester" in line for line in lines)   # each tag still opens to its requester
