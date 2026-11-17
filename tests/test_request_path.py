"""The decision path as the running application performs it (thesis Chapters 6 and 7), with Streamlit's test runner
(no browser) and with the function the clinician screen calls, services/request_service.submit_request.

B1 VA counts the approvals alone, the token and revocation conditions are reported by VL, and every evaluation runs
   Algorithm 6.2 (validate_lifecycle), whose evidence is the STATE_CHECK record.
B2 the time of a decision is the block timestamp when a chain is configured, its source is recorded, and a chain that
   cannot be read refuses the request. Demo mode uses the server clock and says so.
B3 the clinician declares the context, the purpose and the scope. A deny code is shown and recorded only when it is one
   of the nine of Section 6.3.1, and any other failure is named.
B4 on ALLOW the data are delivered by Algorithm 6.5 from the consent-bound encrypted copy, and the DATA_ACCESS record
   is written by release().
C  the proof of the decision is verified on chain after the matrix and before any data are delivered, and the
   transaction of the ConsentVerified event is stored with the DATA_ACCESS record.
D  the role and the labels say Clinician, the jurisdiction field is the context, and the rows carry what Section 6.4.3
   says they carry.

The chain is an in-memory EVM with the real bytecode of blockchain/abi (no network, no Sepolia). The key of the owner is
derived from a label in this file: it is a test key and holds nothing. The proof tests that need the built circuit
(zk/build) are skipped without it. The others replace the Groth16 verifier by MockDecisionVerifier, which proves nothing."""
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest
from web3.logs import DISCARD

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_KEY_LABEL = "halah request path test owner"               # the owner key is derived from this label (not a secret)
PATIENT = "did:patient:x"                                       # holds no record: its modules are empty tables
CLINICIAN, REGISTRAR = "did:hospital:001", "did:hospital:002"   # the named clinician, and another valid clinician
G = ["did:parent:A", "did:parent:B"]
FOUR = ["Observation", "Medication", "Condition", "Procedure"]
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
    """The source record of the treating institution (the Synthea subset of the repository)."""
    import database.repository as repository
    repo = repository.SyntheaRepository(os.path.join(ROOT, "data", "synthea"))
    return SimpleNamespace(repo=repo, patient=repo.get_patient_dids()["DID"].tolist()[0])


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


def _consent(scope=("Observation",), approvals=None, token=True, patient=PATIENT, guardians=G, threshold=None,
             start=None, expiry=None, context="AU"):
    """A consent as the form and the guardian screen leave it: committed, approved over the commitment, and with the
    local token once the threshold is met. `approvals` names the guardians who have approved (default: all)."""
    from database import consent_db
    from services import commitment_service, identity_service as ids
    from services.consent_service import create_consent
    c = create_consent(patient, CLINICIAN, list(guardians), list(scope), "Treatment",
                       (start or datetime.now() - timedelta(days=1)).isoformat(),
                       (expiry or datetime.now() + timedelta(days=30)).isoformat(),
                       threshold=threshold or len(guardians), context=context)
    commitment_service.commit_consent(c)
    for g in (guardians if approvals is None else approvals):
        signature, address = ids.sign_consent_v2(g, c.consent_id, c.commitment)
        c.signatures.append(g)
        c.signature_data[g] = {"scheme": "EIP-712", "version": 2, "signer": address, "signature": signature}
    if token:
        c.token_id = f"SBT-LOCAL-{c.consent_id[:8]}"
    consent_db.save(c)
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


def _guardian_screen(AppTest, cid):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Guardian").run()
    [t for t in at.text_input if t.label == "Enter Target Consent ID"][0].set_value(cid).run()
    return at


def _approve(at, did):
    [s for s in at.selectbox if s.label == "Select Your Guardian DID Identity"][0].set_value(did).run()
    [b for b in at.button if b.label == "Sign Consent via VC"][0].click().run()
    return at


def _clinician_screen(AppTest, cid, requester=CLINICIAN):
    at = AppTest.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Clinician").run()
    [t for t in at.text_input if t.label == "Enter Authorised Consent ID"][0].set_value(cid).run()
    [t for t in at.text_input if t.label == "Your Clinician DID (requester)"][0].set_value(requester).run()
    return at


def _declare(at, scope=None, purpose=None, context=None):
    if context is not None:
        [s for s in at.selectbox if s.label == "Request Context (jurisdiction code)"][0].set_value(context).run()
    if purpose is not None:
        [s for s in at.selectbox if s.label == "Purpose of this request"][0].set_value(purpose).run()
    if scope is not None:
        [m for m in at.multiselect if m.label == "Select Request Scope"][0].set_value(list(scope)).run()
    return at


def _submit(at):
    [b for b in at.button if b.label.startswith("Request Data Access")][0].click().run()
    assert not at.exception
    return at


def _matrix(at):
    return at.table[0].value.to_dict("records")[0]


def _failed(at):
    return [name for name, value in _matrix(at).items() if value == "FAIL" and name != "ALLOW"]


def _rows(cid, action=None):
    from database import audit_db
    return [e for e in audit_db.get() if e["consent_id"] == cid and (action is None or e["action"] == action)]


def _module_expanders(at):
    """The expanders of the delivered modules, not the notices that earlier requests may have left on the page."""
    return [e.label for e in at.expander if e.label in [m.upper() for m in FOUR]]


def _last(cid):
    """The two records of the last submitted request: (STATE_CHECK, DATA_ACCESS)."""
    return _rows(cid, "STATE_CHECK")[-1], _rows(cid, "DATA_ACCESS")[-1]


def _code_fields(row):
    """Every string that a row holds in a field for deny codes."""
    m = row["metadata"]
    found = []
    for holder in (m, m.get("decision_matrix") or {}, m.get("lifecycle") or {}):
        for name in ("deny_code", "deny_codes", "DENY"):
            value = holder.get(name)
            found += value if isinstance(value, list) else ([value] if value else [])
    return found


def _page_text(at):
    groups = (at.error, at.warning, at.caption, at.info, at.success, at.markdown, at.subheader, at.header)
    return " | ".join(str(e.value) for group in groups for e in group)


def _source(patient_did, scope):
    """Stands for the source record: one row for each module asked for."""
    return {module: [{"module": module, "patient": patient_did}] for module in scope}


def _ask(c, requester=CLINICIAN, scope=("Observation",), purpose="Treatment", context="AU", **kw):
    """One request through the function the clinician screen calls."""
    from services import request_service
    return request_service.submit_request(c, requester, list(scope) if scope is not None else None, purpose, context, **kw)


# ---- B1: VA over the approvals alone, the token and the revocation under VL, Algorithm 6.2 ------------------------------

def test_revoked_consent_shows_va_pass_and_vl_fail_on_the_screen_and_in_the_rows(app_test):
    from database import consent_db
    c = _consent()
    consent_db.revoke(c.consent_id)                                   # approved by both guardians, then revoked
    at = _clinician_screen(app_test, c.consent_id)
    assert _matrix(at) == {"VI": "PASS", "VA": "PASS", "VP": "PASS", "VT": "PASS", "VL": "FAIL", "ALLOW": "FAIL"}
    assert any(x.value == "Failed checks: VL | Deny code: REVOKED" for x in at.caption)
    assert any(e.value == "Consent is not active. Current state: REVOKED (deny code: REVOKED)" for e in at.error)
    at = _submit(_declare(at, scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: VL. Deny code: REVOKED. Consent state: REVOKED." + RECORDED for e in at.error)
    check, access = _last(c.consent_id)
    assert check["result"] == "REVOKED" and (check["metadata"]["VA"], check["metadata"]["VL"]) == (True, False)
    m = access["metadata"]
    assert (m["decision_matrix"]["VA"], m["decision_matrix"]["VL"]) == (True, False) and access["result"] == "DENIED"
    assert m["deny_code"] == "REVOKED" and m["deny_codes"] == ["REVOKED"] and m["failed_checks"] == ["VL"]


def test_consent_without_its_token_shows_va_pass_and_vl_fail_and_no_deny_code(app_test):
    c = _consent(token=False)                                         # the threshold is met and no token is recorded
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == ["VL"] and _matrix(at)["VA"] == "PASS"
    assert any(x.value == "Failed checks: VL" for x in at.caption)   # no code of the nine applies, so none is shown
    assert any(e.value == "Consent is not active. Current state: PENDING_TOKEN" for e in at.error)
    assert any(w.value == "The Clinician cannot access patient data because the consent is not currently valid." for w in at.warning)
    assert [b.label for b in at.button] == ["Request Data Access"]
    at = _submit(_declare(at, scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: VL. Consent state: PENDING_TOKEN." + RECORDED for e in at.error)
    check, access = _last(c.consent_id)
    assert check["result"] == "PENDING_TOKEN" and check["metadata"]["DENY"] == [] and check["metadata"]["failed_checks"] == ["VL"]
    assert check["metadata"]["lifecycle"]["VALID"] is False and check["metadata"]["lifecycle"]["deny_code"] is None
    assert "PENDING_TOKEN" in check["metadata"]["lifecycle"]["reason"]
    m = access["metadata"]
    assert m["deny_code"] is None and m["deny_codes"] == [] and m["decision_matrix"]["DENY"] == [] and m["failed_checks"] == ["VL"]
    assert _code_fields(check) == [] and _code_fields(access) == []
    assert not any(word in _page_text(at) for word in INTERNAL)


def test_request_before_the_threshold_names_va_and_vl_and_has_no_deny_code(app_test):
    c = _consent(approvals=["did:parent:A"], token=False)             # one approval of two
    at = _submit(_declare(_clinician_screen(app_test, c.consent_id), scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: VA, VL. Consent state: PENDING_SIGNATURE." + RECORDED for e in at.error)
    check, access = _last(c.consent_id)
    assert check["result"] == "PENDING_SIGNATURE" and access["metadata"]["failed_checks"] == ["VA", "VL"]
    assert _code_fields(check) == [] and _code_fields(access) == [] and access["metadata"]["modules_released"] == []
    assert not any(word in _page_text(at) for word in INTERNAL)


def test_lifecycle_check_records_the_evidence_of_algorithm_6_2_for_an_access_and_for_a_transition():
    from database import consent_db
    from services import request_service
    c = _consent()
    t, _ = request_service.decision_time()
    before = len(_rows(c.consent_id))
    evidence, row = request_service.lifecycle_check(c, t)             # a data access on an ACTIVE consent
    assert evidence["VALID"] is True and evidence["operation"] == "ACCESS" and evidence["state"] == "ACTIVE"
    assert row["action"] == "STATE_CHECK" and row["result"] == "ACTIVE" and row["actor_role"] == "ConsentEngine"
    assert row["metadata"]["lifecycle"] == evidence and row["metadata"]["time"]["source"] == t["source"]
    # lines 16 to 20: the requested transition to REVOKED, checked against the policy and recorded without a matrix
    evidence, row = request_service.lifecycle_check(c, t, target="REVOKED", requested_by="did:parent:B")
    assert evidence["VALID"] is True and evidence["operation"] == "TRANSITION" and evidence["target"] == "REVOKED"
    assert row["result"] == "ACTIVE" and row["metadata"]["requested_by"] == "did:parent:B" and "VI" not in row["metadata"]
    evidence, row = request_service.lifecycle_check(c, t, target="ACTIVE")       # ACTIVE to ACTIVE is no transition of the policy
    assert evidence["VALID"] is False and row["metadata"]["lifecycle"]["deny_code"] is None      # not one of the nine
    assert "does not permit" in row["metadata"]["lifecycle"]["reason"]
    consent_db.revoke(c.consent_id)
    evidence, row = request_service.lifecycle_check(c, t, target="REVOKED")      # revocation is irreversible
    assert evidence["VALID"] is False and row["result"] == "REVOKED" and row["metadata"]["lifecycle"]["deny_code"] == "REVOKED"
    assert len(_rows(c.consent_id)) == before + 4


# ---- B2: the time of the decision -------------------------------------------------------------------------------------

def test_demo_mode_uses_the_server_clock_and_says_so(app_test):
    c = _consent()
    at = _clinician_screen(app_test, c.consent_id)
    assert any(x.value == "Time source: server clock (demo mode, no chain is configured)" for x in at.sidebar.caption)
    assert any(x.value.startswith("Decision time: ") and x.value.endswith(" - source: server clock (demo mode)") for x in at.caption)
    at = _submit(_declare(at, scope=["Observation"]))
    assert any("Access Granted" in s.value for s in at.success)
    check, access = _last(c.consent_id)
    assert access["metadata"]["time_source"] == "system-clock-fallback"
    assert check["metadata"]["time"]["source"] == "system-clock-fallback" and check["metadata"]["time"]["block_number"] is None
    assert abs((datetime.fromisoformat(access["metadata"]["decision_time"]) - datetime.now()).total_seconds()) < 120


def test_on_chain_the_time_of_the_decision_is_the_block_timestamp_and_not_the_server_clock(app_test, onchain):
    c = _consent()
    _anchored(c)
    onchain.tester.time_travel(onchain.w3.eth.get_block("latest").timestamp + 86400)     # the chain is a day ahead of the server
    block = onchain.w3.eth.get_block("latest")
    moment = datetime.fromtimestamp(block.timestamp)
    at = _clinician_screen(app_test, c.consent_id)
    assert any(x.value == "Time source: block timestamp" for x in at.sidebar.caption)
    assert any(x.value == f"Decision time: {moment:%Y-%m-%d %H:%M:%S} - source: block timestamp (block {block.number})" for x in at.caption)
    at = _submit(_declare(at, scope=["Procedure"]))                   # outside the consented scope: refused, no proof is made
    check, access = _last(c.consent_id)
    assert access["result"] == "DENIED" and access["metadata"]["deny_code"] == "OUT-OF-SCOPE"
    assert access["metadata"]["time_source"] == "block-timestamp" and access["metadata"]["decision_time"] == moment.isoformat()
    t = check["metadata"]["time"]
    assert (t["source"], t["unix"], t["block_number"]) == ("block-timestamp", block.timestamp, block.number)
    assert abs(t["clock_skew_seconds"] - 86400) < 3600                # the server clock was not used
    assert check["metadata"]["lifecycle"]["time"] == moment.isoformat()


def test_request_is_refused_and_recorded_when_the_time_of_the_chain_cannot_be_read(app_test, onchain, monkeypatch):
    from services import blockchain_service as bc, data_vault, time_source

    class Down:                                                       # a node that does not answer
        class w3:
            class eth:
                @staticmethod
                def get_block(_):
                    raise ConnectionError("the node does not answer")

    c = _consent()
    monkeypatch.setattr(bc, "token_client", lambda read_only=False: Down())
    with pytest.raises(time_source.TimeSourceError):                  # no fall-back to the server clock
        bc.chain_time()
    at = _clinician_screen(app_test, c.consent_id)
    assert any(e.value == "The time of the chain could not be read (provider failed: the node does not answer). "
               "In on-chain mode the server clock is not used, so the request is refused." for e in at.error)
    assert [b.label for b in at.button] == ["Request Data Access"] and not at.table     # nothing is evaluated
    assert not any(s.value == "Request Patient Data" for s in at.subheader)
    at = _submit(at)
    assert any(e.value == "Access Denied. Failed checks: time source." + RECORDED for e in at.error)
    (row,) = _rows(c.consent_id)                                      # one DATA_ACCESS record and no STATE_CHECK
    assert (row["action"], row["result"], row["actor_did"], row["actor_role"]) == ("DATA_ACCESS", "DENIED", CLINICIAN, "Doctor")
    m = row["metadata"]
    assert m["deny_code"] is None and m["deny_codes"] == [] and m["failed_checks"] == ["time source"]
    assert m["time_source"] == "unavailable" and m["reason"].startswith("the time of the chain could not be read: ")
    assert "the node does not answer" in m["reason"] and m["modules_released"] == []
    assert not data_vault.default_vault().has_copy(c.consent_id)
    at = _guardian_screen(app_test, c.consent_id)                     # the guardian screen derives no state without the time
    assert any(i.value == f"Found consent for Patient: `{PATIENT}` (state: not derived, the time of the chain could not be read)" for i in at.info)


def test_guardian_approval_is_checked_at_the_block_time_and_names_its_time_source(app_test, onchain, monkeypatch):
    from blockchain import onchain_ui
    monkeypatch.setattr(onchain_ui, "render_onchain_anchor_async", lambda c, a, d: None)       # nothing is sent in this test
    c = _consent(approvals=[], token=False)
    onchain.tester.time_travel(onchain.w3.eth.get_block("latest").timestamp + 5 * 86400)        # the chain is five days ahead
    block = datetime.fromtimestamp(onchain.w3.eth.get_block("latest").timestamp)
    assert (block - datetime.now()).days >= 4
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    assert not at.error and any("Multi-sig: 1/2" in s.value for s in at.success)
    identity, signed = _rows(c.consent_id)
    assert (identity["action"], identity["result"], identity["actor_did"]) == ("IDENTITY_VERIFICATION", "VALID", "did:parent:A")
    assert identity["metadata"]["checked_at"] == block.isoformat()    # Algorithm 5.1 ran at the block time, not at the server clock
    assert (signed["action"], signed["result"], signed["metadata"]["time_source"]) == ("SIGN_CONSENT", "SUCCESS", "block-timestamp")
    # a refused approval names the source of its time as well (a clinician named as a guardian)
    other = _consent(approvals=[], token=False, guardians=["did:parent:A", REGISTRAR])
    at = _approve(_guardian_screen(app_test, other.consent_id), REGISTRAR)
    assert any("approval rejected" in e.value for e in at.error)
    (rejected,) = _rows(other.consent_id)
    assert (rejected["action"], rejected["result"], rejected["metadata"]["time_source"]) == ("SIGN_CONSENT", "REJECTED", "block-timestamp")


def test_patient_form_checks_the_credentials_and_the_majority_at_the_block_time(app_test, onchain, monkeypatch):
    from database import consent_db
    from services import identity_service as ids
    onchain.tester.time_travel(onchain.w3.eth.get_block("latest").timestamp + 5 * 86400)        # the chain is five days ahead
    block = datetime.fromtimestamp(onchain.w3.eth.get_block("latest").timestamp)
    checked, verify = [], ids.verify_identity

    def seen(did, **more):
        checked.append((did, more.get("now")))
        return verify(did, **more)
    monkeypatch.setattr(ids, "verify_identity", seen)
    # eighteen in three days by the server clock, and two days ago by the time of the chain
    day = datetime.now().date() + timedelta(days=3)
    born = day.replace(year=day.year - 18, day=28) if (day.month, day.day) == (2, 29) else day.replace(year=day.year - 18)
    before = set(consent_db.CONSENTS)
    at = app_test.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.multiselect[0].set_value(["Observation"]).run()
    [t for t in at.text_input if t.label.startswith("Patient Date of Birth")][0].set_value(born.isoformat()).run()
    [b for b in at.button if b.label == "Initial Consent"][0].click().run()
    assert not at.error and any("created and logged" in s.value for s in at.success)
    assert checked == [(CLINICIAN, block), ("did:parent:A", block), ("did:parent:B", block)]
    (cid,) = set(consent_db.CONSENTS) - before
    # by the time of the chain the patient is of age already, so no transition is scheduled
    assert consent_db.get(cid).transitions == [] and not _rows(cid, "SCHEDULE_TRANSITION")


def test_no_approval_and_no_consent_is_recorded_while_the_time_of_the_chain_cannot_be_read(app_test, onchain, monkeypatch):
    from database import audit_db, consent_db, db
    from services import blockchain_service as bc

    class Down:                                                       # a node that does not answer
        class w3:
            class eth:
                @staticmethod
                def get_block(_):
                    raise ConnectionError("the node does not answer")
    c = _consent(approvals=[], token=False)
    monkeypatch.setattr(bc, "token_client", lambda read_only=False: Down())
    cannot = "The time of the chain could not be read (provider failed: the node does not answer). In on-chain mode the server clock is not used, "
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    assert [e.value for e in at.error] == [cannot + "so the approval cannot be accepted now."]
    assert not any("Multi-sig" in s.value for s in at.success)
    assert not _rows(c.consent_id)                                    # no IDENTITY_VERIFICATION and no SIGN_CONSENT row
    stored = [r for r in db.all_rows("consents") if r["consent_id"] == c.consent_id][0]      # the row in SQLite
    assert stored["signatures"] == [] and not stored["signature_data"]
    # the form: nothing is created, with or without a date of birth
    before, rows = set(consent_db.CONSENTS), len(audit_db.get())
    for born in ("", "2015-01-01"):
        at = app_test.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
        at.multiselect[0].set_value(["Observation"]).run()
        if born:
            [t for t in at.text_input if t.label.startswith("Patient Date of Birth")][0].set_value(born).run()
        [b for b in at.button if b.label == "Initial Consent"][0].click().run()
        assert cannot + "so the consent cannot be created now." in [e.value for e in at.error]
        assert not any("created and logged" in s.value for s in at.success)
    assert set(consent_db.CONSENTS) == before and len(audit_db.get()) == rows     # no CREATE_CONSENT, no SCHEDULE_TRANSITION


def test_chain_time_is_the_latest_block_with_a_chain_and_the_labelled_server_clock_without(onchain, monkeypatch):
    from services import blockchain_service as bc, time_source
    block = onchain.w3.eth.get_block("latest")
    provider, read_through = time_source.block_provider, []
    monkeypatch.setattr(time_source, "block_provider", lambda w3: read_through.append(w3) or provider(w3))
    t = bc.chain_time()
    assert (t["source"], t["unix"], t["block_number"]) == ("block-timestamp", block.timestamp, block.number)
    assert t["time"] == datetime.fromtimestamp(block.timestamp) and t["reason"] is None
    assert len(read_through) == 1                                     # the block provider of services/time_source
    monkeypatch.delenv("CONTRACT_V4_ADDRESS")                         # no chain is configured: demo mode
    t = bc.chain_time()
    assert t["source"] == "system-clock-fallback" and t["block_number"] is None and t["reason"] == "no provider configured"
    assert len(read_through) == 1


def test_older_contract_mode_takes_the_block_time_as_well_and_keeps_the_local_proof(monkeypatch):
    from services import blockchain_service as bc, time_source
    stamp = int(datetime.now().timestamp()) - 40                      # the latest block, a little behind the server clock

    class Client:                                                     # stands for the client of ConsentSBTv3
        class w3:
            class eth:
                @staticmethod
                def get_block(_):
                    return {"timestamp": stamp, "number": 77}

    class Down:
        def __init__(self):
            raise ConnectionError("the node does not answer")

    class Chain:
        ConsentContract = Client

        @staticmethod
        def is_configured():
            return True
    monkeypatch.setattr(bc, "chain", Chain)                           # CONTRACT_ADDRESS without CONTRACT_V4_ADDRESS
    assert bc.onchain_enabled() and not bc.v4_enabled()
    t = bc.chain_time()
    assert (t["source"], t["unix"], t["block_number"]) == ("block-timestamp", stamp, 77)
    out = _ask(_consent(), source=_source)
    assert out["outcome"] == "GRANTED" and out["time_source"] == "block-timestamp" and out["verification"] is None
    assert out["decided_at"] == datetime.fromtimestamp(stamp).isoformat()
    assert out["audit_event"]["metadata"]["proof_mode"] in ("placeholder", "groth16") and "tx_hash" not in out["proof_reference"]
    Chain.ConsentContract = Down
    with pytest.raises(time_source.TimeSourceError):
        bc.chain_time()
    refused = _ask(_consent(), source=_source)
    assert refused["outcome"] == "DENIED" and refused["failed_checks"] == ["time source"] and refused["state_check_event"] is None


# ---- B3: the declared request and the nine deny codes ----------------------------------------------------------------

def test_over_scope_request_made_on_the_screen_is_refused_with_out_of_scope(app_test):
    c = _consent(scope=["Observation"])
    at = _clinician_screen(app_test, c.consent_id)
    selector = [m for m in at.multiselect if m.label == "Select Request Scope"][0]
    assert list(selector.options) == FOUR                             # the record modules, not the consented scope
    at = _declare(at, scope=["Observation", "Procedure"])
    assert _failed(at) == ["VP"] and any(x.value == "Failed checks: VP | Deny code: OUT-OF-SCOPE" for x in at.caption)
    assert any(i.value == "Requested Modules: Observation, Procedure" for i in at.info)
    at = _submit(at)
    assert any(e.value == "Access Denied. Failed checks: VP. Deny code: OUT-OF-SCOPE." + RECORDED for e in at.error)
    assert not any(s.value == "Authorised Medical Records" for s in at.subheader) and not at.dataframe
    check, access = _last(c.consent_id)
    assert access["scope"] == ["Observation", "Procedure"] and access["result"] == "DENIED"
    m = access["metadata"]
    assert m["deny_code"] == "OUT-OF-SCOPE" and m["failed_checks"] == ["VP"] and m["modules_released"] == []
    assert m["zk_proof_verified"] is None and m["proof_reference"] is None        # no proof is made for a denied request
    assert check["metadata"]["VS"] is False and check["metadata"]["request_scope"] == ["Observation", "Procedure"]


def test_empty_selection_is_refused_with_out_of_scope_and_a_hint(app_test):
    c = _consent()
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == []                                          # the scope is compared once a module is chosen
    assert not any(x.value.startswith("Failed checks") for x in at.caption)
    at = _submit(at)
    assert any(e.value == "Access Denied. Failed checks: VP. Deny code: OUT-OF-SCOPE." + RECORDED for e in at.error)
    assert any(w.value == "Please select at least one data module." for w in at.warning)
    _, access = _last(c.consent_id)
    assert access["scope"] == [] and access["metadata"]["deny_code"] == "OUT-OF-SCOPE"
    # after the click the page holds one matrix, and it is the matrix of the submitted request
    assert len(at.table) == 1 and _failed(at) == ["VP"] and _matrix(at)["ALLOW"] == "FAIL"
    assert _matrix(at) == {name: ("PASS" if access["metadata"]["decision_matrix"][name] else "FAIL") for name in _matrix(at)}
    assert [x.value for x in at.caption if x.value.startswith("Failed checks")] == ["Failed checks: VP | Deny code: OUT-OF-SCOPE"]


def test_matrix_on_the_page_of_a_click_is_the_matrix_of_the_submitted_request(app_test, monkeypatch):
    from services import zk_service
    c = _consent()
    # a request the rule refuses: the table and its caption are the same before and after the click
    at = _declare(_clinician_screen(app_test, c.consent_id), scope=["Procedure"])
    before, caption = _matrix(at), [x.value for x in at.caption if x.value.startswith("Failed checks")]
    assert caption == ["Failed checks: VP | Deny code: OUT-OF-SCOPE"]
    at = _submit(at)
    assert len(at.table) == 1 and _matrix(at) == before
    assert [x.value for x in at.caption if x.value.startswith("Failed checks")] == caption
    # a granted request: every check passes, before and after, and no failed check is named
    at = _declare(_clinician_screen(app_test, c.consent_id), scope=["Observation"])
    at = _submit(at)
    assert any("Access Granted" in s.value for s in at.success)
    assert len(at.table) == 1 and set(_matrix(at).values()) == {"PASS"}
    assert not any(x.value.startswith("Failed checks") for x in at.caption)
    # the rule allows and the proof fails: the matrix stays, and the caption names the proof as the answer does
    monkeypatch.setattr(zk_service, "verify_proof", lambda proof: False)
    at = _submit(_declare(_clinician_screen(app_test, c.consent_id), scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: proof." + RECORDED for e in at.error)
    assert len(at.table) == 1 and set(_matrix(at).values()) == {"PASS"}
    assert [x.value for x in at.caption if x.value.startswith("Failed checks")] == ["Failed checks: proof"]


def test_mismatched_purpose_and_context_are_refused_with_their_codes(app_test):
    c = _consent()
    at = _clinician_screen(app_test, c.consent_id)
    assert [s.label for s in at.selectbox if "jurisdiction" in s.label] == ["Request Context (jurisdiction code)"]
    at = _submit(_declare(at, scope=["Observation"], purpose="Research"))
    assert any(e.value == "Access Denied. Failed checks: VP. Deny code: PURPOSE-MISMATCH." + RECORDED for e in at.error)
    _, access = _last(c.consent_id)
    assert (access["purpose"], access["metadata"]["consent_purpose"], access["metadata"]["deny_code"]) == ("Research", "Treatment", "PURPOSE-MISMATCH")
    at = _submit(_declare(at, purpose="Treatment", context="US"))
    assert any(e.value == "Access Denied. Failed checks: VP. Deny code: CONTEXT-MISMATCH." + RECORDED for e in at.error)
    check, access = _last(c.consent_id)
    assert access["metadata"]["context"] == "US" and access["metadata"]["deny_code"] == "CONTEXT-MISMATCH"
    assert (check["metadata"]["VU"], check["metadata"]["VS"], check["metadata"]["VX"]) == (True, True, False)
    at = _submit(_declare(at, purpose="Research", scope=["Procedure"]))      # all three wrong: the purpose is reported
    assert any(e.value == "Access Denied. Failed checks: VP. Deny code: PURPOSE-MISMATCH." + RECORDED for e in at.error)
    assert _last(c.consent_id)[1]["metadata"]["deny_codes"] == ["PURPOSE-MISMATCH", "CONTEXT-MISMATCH", "OUT-OF-SCOPE"]


def test_failure_of_vi_alone_is_named_and_no_code_is_shown_or_recorded(app_test):
    c = _consent()
    at = _declare(_clinician_screen(app_test, c.consent_id, requester=REGISTRAR), scope=["Observation"])
    assert any(w.value == "This DID is not the clinician authorised by this consent." for w in at.warning)
    assert _failed(at) == ["VI"] and any(x.value == "Failed checks: VI" for x in at.caption)
    assert not any(s.value == "Authorised Data Scope" for s in at.subheader)
    at = _submit(at)
    assert any(e.value == "Access Denied. Failed checks: VI." + RECORDED for e in at.error)
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert access["actor_did"] == REGISTRAR and m["deny_code"] is None and m["deny_codes"] == [] and m["failed_checks"] == ["VI"]
    assert _code_fields(check) == [] and _code_fields(access) == []
    assert not any(word in _page_text(at) for word in INTERNAL)


def test_registrar_requesting_procedure_for_research_fails_vi_and_vp_with_purpose_mismatch(app_test):
    c = _consent(scope=FOUR)
    at = _declare(_clinician_screen(app_test, c.consent_id, requester=REGISTRAR), purpose="Research", scope=["Procedure"])
    assert _failed(at) == ["VI", "VP"] and any(x.value == "Failed checks: VI, VP | Deny code: PURPOSE-MISMATCH" for x in at.caption)
    at = _submit(at)
    assert any(e.value == "Access Denied. Failed checks: VI, VP. Deny code: PURPOSE-MISMATCH." + RECORDED for e in at.error)
    check, access = _last(c.consent_id)
    assert (access["actor_did"], access["scope"], access["purpose"], access["result"]) == (REGISTRAR, ["Procedure"], "Research", "DENIED")
    m = access["metadata"]
    assert m["deny_code"] == "PURPOSE-MISMATCH" and m["failed_checks"] == ["VI", "VP"] and m["modules_released"] == []
    assert (m["decision_matrix"]["VI"], m["decision_matrix"]["VU"], m["decision_matrix"]["VS"]) == (False, False, True)
    assert check["metadata"]["requester_identity"]["result"] == "VALID"      # a valid clinician, and not the one the consent names


def test_requester_without_a_credential_is_refused_in_plain_words(app_test):
    c = _consent()
    at = _clinician_screen(app_test, c.consent_id, requester="did:hospital:999")
    assert any(w.value == "No valid clinician credential for this DID (VC_found: no credential is held for this identifier)." for w in at.warning)
    at = _submit(_declare(at, scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: VI." + RECORDED for e in at.error)
    check, access = _last(c.consent_id)
    assert check["metadata"]["requester_identity"] == {"result": "INVALID", "reason": "CREDENTIAL_NOT_FOUND", "credential_id": None, "issuer": None}
    assert not _rows(c.consent_id, "IDENTITY_VERIFICATION")          # evidence is recorded for a valid verification only
    assert "CREDENTIAL_NOT_FOUND" not in _page_text(at)


def test_failed_proof_is_named_and_nothing_is_released(app_test, monkeypatch):
    from services import request_service
    c = _consent()
    monkeypatch.setattr(request_service.zk_service, "verify_proof", lambda proof: False)     # the verifier does not accept the proof
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == []                                          # the decision rule allows the request
    at = _submit(_declare(at, scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: proof." + RECORDED for e in at.error)
    assert not any(s.value == "Authorised Medical Records" for s in at.subheader) and not at.dataframe
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert access["result"] == "DENIED" and m["deny_code"] is None and m["deny_codes"] == [] and m["failed_checks"] == ["proof"]
    assert m["decision_matrix"]["ALLOW"] is True and m["zk_proof_verified"] is False and m["modules_released"] == []
    assert _code_fields(access) == [] and check["result"] == "ACTIVE"
    assert not any(word in _page_text(at) for word in INTERNAL)


def test_missing_copy_is_named_and_recorded_without_a_code():
    from services.data_vault import DataVault
    from services.key_store import KeyStore
    c = _consent()
    out = _ask(c, vault=DataVault(KeyStore()))                        # a vault without the copy, and no source to seal it from
    assert out["outcome"] == "DENIED" and out["failed_checks"] == ["copy"] and out["deny_code"] is None and out["data"] == {}
    m = out["audit_event"]["metadata"]
    assert m["deny_code"] is None and m["deny_codes"] == [] and m["failed_checks"] == ["copy"] and "could not be opened" in m["reason"]
    assert _code_fields(out["audit_event"]) == []


def test_request_without_a_scope_or_without_a_purpose_is_denied():
    c = _consent()
    out = _ask(c, scope=None)
    assert (out["outcome"], out["deny_code"], out["failed_checks"]) == ("DENIED", "OUT-OF-SCOPE", ["VP"])
    assert out["audit_event"]["scope"] == [] and out["state_check_event"]["metadata"]["request_scope"] == []
    out = _ask(c, purpose=None)
    assert (out["outcome"], out["deny_code"], out["failed_checks"]) == ("DENIED", "PURPOSE-MISMATCH", ["VP"])
    assert out["audit_event"]["purpose"] == "" and out["data"] == {}
    out = _ask(c, scope=["Observation", 7])                           # a scope that is not a list of module names
    assert (out["outcome"], out["deny_code"]) == ("DENIED", "OUT-OF-SCOPE")
    assert _ask(c, source=_source)["outcome"] == "GRANTED"            # the same consent allows the complete request


def test_code_shown_is_chosen_by_the_precedence_rule_of_section_6_3_1():
    now = datetime.now()
    expired = _consent(start=now - timedelta(days=3), expiry=now - timedelta(days=1))        # issued, and its window has passed
    out = _ask(expired)
    assert (out["deny_code"], out["failed_checks"], out["state"]) == ("EXPIRED", ["VT", "VL"], "EXPIRED")     # the state code, not POST-VALIDITY
    out = _ask(expired, purpose="Research")
    assert out["deny_code"] == "EXPIRED" and out["deny_codes"] == ["EXPIRED", "PURPOSE-MISMATCH"]
    never = _consent(approvals=["did:parent:A"], token=False, start=now - timedelta(days=3), expiry=now - timedelta(days=1))
    out = _ask(never)                                                 # never issued: the window check reports
    assert (out["deny_code"], out["failed_checks"], out["state"]) == ("POST-VALIDITY", ["VA", "VT", "VL"], "PENDING_SIGNATURE")
    early = _consent(start=now + timedelta(days=2), expiry=now + timedelta(days=30))
    out = _ask(early)
    assert (out["deny_code"], out["failed_checks"], out["state"]) == ("PRE-VALIDITY", ["VT", "VL"], "NOT_STARTED")
    for out in (_ask(expired), _ask(never), _ask(early)):
        for row in (out["state_check_event"], out["audit_event"]):
            assert all(code in NINE for code in _code_fields(row))


def test_release_keyword_keeps_the_default_and_records_only_the_nine_when_it_is_on():
    from services.data_vault import DataVault
    from services.key_store import KeyStore
    from services.release_service import release
    c = _consent()
    vault = DataVault(KeyStore())
    vault.seal(c, {"Observation": [{"code": "8302-2"}]})
    ask = lambda **kw: release(c, kw.pop("requester", CLINICIAN), ["Observation"], "Treatment", "AU", vault=vault, verify_sig=False,
                               proof={"mode": "test"}, verify_proof=kw.pop("verify", lambda proof: True), **kw)
    plain = ask(requester=REGISTRAR)                                  # the default call, as the earlier tests assert it
    assert plain["deny_code"] == "IDENTITY-INVALID" and "failed_checks" not in plain and "failed_checks" not in plain["audit_event"]["metadata"]
    named = ask(requester=REGISTRAR, section_codes_only=True)
    assert named["deny_code"] is None and named["deny_codes"] == [] and named["failed_checks"] == ["VI"]
    assert named["decision"]["DENY"] == [] and named["audit_event"]["metadata"]["decision_matrix"]["DENY"] == []
    assert named["state_check_event"]["metadata"]["DENY"] == [] and named["reason"] == plain["reason"]
    assert ask(verify=lambda proof: False)["deny_code"] == "PROOF-INVALID"
    refused = ask(verify=lambda proof: False, section_codes_only=True)
    assert refused["deny_code"] is None and refused["failed_checks"] == ["proof"] and refused["reason"] == "the proof did not verify"
    granted = ask(section_codes_only=True)
    assert granted["outcome"] == "GRANTED" and granted["failed_checks"] == [] and granted["audit_event"]["metadata"]["failed_checks"] == []
    vault.key_store.destroy(c.consent_id)                             # the keys are destroyed and the record still reads ACTIVE
    gone = ask(section_codes_only=True)
    assert gone["outcome"] == "DENIED" and gone["deny_code"] == "REVOKED" and gone["failed_checks"] == ["copy"] and gone["data"] == {}


# ---- B4: the release by Algorithm 6.5 from the consent-bound copy -----------------------------------------------------

def test_copy_is_sealed_at_issuance_with_one_key_for_each_consented_module(app_test, anchor_calls, records):
    from database import consent_db
    from services import commitment_service, data_vault
    from services.consent_service import create_consent
    c = create_consent(records.patient, CLINICIAN, G, ["Observation", "Medication"], "Treatment",
                       (datetime.now() - timedelta(days=1)).isoformat(), (datetime.now() + timedelta(days=30)).isoformat())
    commitment_service.commit_consent(c)
    consent_db.save(c)
    vault = data_vault.default_vault()
    at = _approve(_guardian_screen(app_test, c.consent_id), "did:parent:A")
    assert not vault.has_copy(c.consent_id) and vault.key_store.key_ids(c.consent_id) == {}   # nothing before the threshold
    at = _approve(at, "did:parent:B")
    assert any("Multi-sig: 2/2" in s.value for s in at.success)
    assert vault.modules(c.consent_id) == ["Medication", "Observation"]       # the consented scope, and no other module
    keys = vault.key_store.key_ids(c.consent_id)
    assert set(keys) == {"Observation", "Medication"} and len(set(keys.values())) == 2      # one key per consent and module
    blob = vault.export_copy(c.consent_id)["Observation"]
    assert blob["key_id"] == keys["Observation"] and "Body Height" not in str(blob)         # ciphertext, and no key in the vault
    out = _ask(c, scope=["Medication"])                               # released from that copy, without a source record
    assert out["outcome"] == "GRANTED" and list(out["data"]) == ["Medication"]
    assert len(out["data"]["Medication"]) == len(records.repo.query_patient(records.patient, ["Medication"])["Medication"])


def test_granted_request_delivers_only_the_requested_modules_from_the_sealed_copy(app_test, records):
    from services import data_vault, revocation_service
    c = _consent(scope=["Observation", "Medication"], patient=records.patient)
    vault = data_vault.default_vault()
    assert not vault.has_copy(c.consent_id)                           # a consent without a copy is sealed at its first use
    at = _clinician_screen(app_test, c.consent_id)
    assert any(s.value == "Authorised Data Scope" for s in at.subheader)
    assert any(b.label == "Request Data Access (integrity proof - ZK placeholder)" or b.label == "Request Data Access (Groth16 ZK proof)" for b in at.button)
    at = _submit(_declare(at, scope=["Observation"]))
    assert any(s.value == "Cryptographic Verification Successful — Access Granted." for s in at.success)
    assert any(x.value.endswith("Released from the consent-bound encrypted copy: Observation.") for x in at.caption)
    assert any(x.value.startswith("Proof mode: ") and x.value.endswith("(demo mode: checked locally, not on chain)") for x in at.caption)
    assert any(s.value == "Authorised Medical Records" for s in at.subheader)
    source = records.repo.query_patient(records.patient, ["Observation"])["Observation"]
    assert _module_expanders(at) == ["OBSERVATION"] and len(at.dataframe) == 1     # the requested module and no other
    shown = at.dataframe[0].value
    assert len(shown) == len(source) > 0 and list(shown.columns) == list(source.columns)
    assert vault.modules(c.consent_id) == ["Medication", "Observation"]
    keys = vault.key_store.key_ids(c.consent_id)
    _, access = _last(c.consent_id)
    m = access["metadata"]
    assert access["result"] == "GRANTED" and access["scope"] == ["Observation"] and m["modules_released"] == ["Observation"]
    assert m["key_references"] == {"Observation": keys["Observation"]}        # a reference to the key, never the key
    # The delivery depends on the copy and its keys, not on the source record: once they are gone the same request
    # delivers nothing, although the source record is unchanged.
    revocation_service.crypto_shred(c.consent_id)
    at = _submit(at)
    assert any(e.value == "Access Denied. Failed checks: copy. Deny code: REVOKED." + RECORDED for e in at.error)
    assert not at.dataframe and _last(c.consent_id)[1]["metadata"]["modules_released"] == []
    assert len(records.repo.query_patient(records.patient, ["Observation"])["Observation"]) == len(source)


def test_every_submitted_request_writes_state_check_and_then_data_access(app_test):
    c = _consent()
    at = _declare(_clinician_screen(app_test, c.consent_id), scope=["Observation"])
    assert _rows(c.consent_id) == []                                  # a page that is only drawn records nothing
    at = _submit(at)
    assert [e["action"] for e in _rows(c.consent_id)] == ["IDENTITY_VERIFICATION", "STATE_CHECK", "DATA_ACCESS"]
    at = _submit(_declare(at, purpose="Emergency"))                   # a denied request is recorded in the same way
    assert [e["action"] for e in _rows(c.consent_id)][3:] == ["IDENTITY_VERIFICATION", "STATE_CHECK", "DATA_ACCESS"]
    assert [e["result"] for e in _rows(c.consent_id, "DATA_ACCESS")] == ["GRANTED", "DENIED"]
    identity = _rows(c.consent_id, "IDENTITY_VERIFICATION")[0]
    assert (identity["actor_did"], identity["actor_role"], identity["result"]) == (CLINICIAN, "Doctor", "VALID")
    assert identity["metadata"]["required_role"] == "doctor" and identity["metadata"]["reason"] == "OK"


# ---- D2: what the two records carry -----------------------------------------------------------------------------------

def test_rows_of_a_granted_and_of_a_denied_request_carry_the_fields_of_section_6_4_3():
    c = _consent(scope=["Observation", "Medication"])
    granted = _ask(c, scope=["Observation"], source=_source)
    denied = _ask(c, scope=["Observation"], purpose="Research", context="US")
    for out, result, code, failed in ((granted, "GRANTED", None, []), (denied, "DENIED", "PURPOSE-MISMATCH", ["VP"])):
        check, access = out["state_check_event"], out["audit_event"]
        # STATE_CHECK: the lifecycle state, with the evidence of Algorithm 6.2 and the request it was evaluated for
        assert (check["action"], check["actor_did"], check["actor_role"], check["result"]) == ("STATE_CHECK", "System", "ConsentEngine", "ACTIVE")
        assert check["scope"] == ["Observation", "Medication"] and check["purpose"] == "Treatment"
        m = check["metadata"]
        assert set(m) == {"VI", "VA", "VP", "VT", "VL", "ALLOW", "VU", "VS", "VX", "DENY", "failed_checks", "lifecycle", "requester_did",
                          "request_purpose", "request_scope", "context", "time", "requester_identity"}
        assert set(m["lifecycle"]) == {"consent_id", "time", "operation", "target", "recorded_state", "state", "window", "revoked",
                                       "VALID", "result", "deny_code", "reason"}
        assert m["lifecycle"]["state"] == "ACTIVE" and m["lifecycle"]["operation"] == "ACCESS" and m["failed_checks"] == failed
        assert set(m["time"]) == {"source", "unix", "block_number", "clock_skew_seconds"} and m["requester_did"] == CLINICIAN
        assert m["requester_identity"]["credential_id"] == "urn:halah:vc:doctor:did:hospital:001"
        # DATA_ACCESS: the requester, the requested scope, the matrix, the declared purpose, the time source, the deny code
        assert (access["action"], access["actor_did"], access["actor_role"], access["result"]) == ("DATA_ACCESS", CLINICIAN, "Doctor", result)
        assert access["scope"] == ["Observation"] and access["purpose"] == out["audit_event"]["purpose"]
        m = access["metadata"]
        assert set(m) == {"consent_state", "decision_matrix", "deny_code", "deny_codes", "failed_checks", "reason", "context",
                          "consent_purpose", "decision_time", "time_source", "zk_proof_verified", "proof_mode", "proof_reference",
                          "modules_released", "key_references"}
        assert set(m["decision_matrix"]) == {"VI", "VA", "VP", "VT", "VL", "ALLOW", "VU", "VS", "VX", "DENY"}
        assert m["deny_code"] == code and m["failed_checks"] == failed and m["consent_purpose"] == "Treatment"
        assert m["time_source"] == check["metadata"]["time"]["source"] and m["decision_time"] == check["metadata"]["lifecycle"]["time"]
        assert not access["onchain"] and access["tx_hash"] is None    # neither record goes on chain
    assert granted["audit_event"]["purpose"] == "Treatment" and denied["audit_event"]["purpose"] == "Research"
    assert denied["audit_event"]["metadata"]["context"] == "US" and denied["audit_event"]["metadata"]["proof_reference"] is None
    reference = granted["audit_event"]["metadata"]["proof_reference"]
    assert reference["digest"].startswith("0x") and reference["mode"] == granted["audit_event"]["metadata"]["proof_mode"]


# ---- C: the proof of the decision, verified on chain before any data are delivered -------------------------------------

def _order_of_events(monkeypatch):
    """Records when the verifier contract is asked and when the vault decrypts."""
    from services import blockchain_service as bc, data_vault
    events, verify, opened = [], bc.verify_decision, data_vault.DataVault.open

    def verify_first(proof):
        events.append("verify")
        return verify(proof)

    def open_later(self, consent_id, modules):
        events.append("open")
        return opened(self, consent_id, modules)
    monkeypatch.setattr(bc, "verify_decision", verify_first)
    monkeypatch.setattr(data_vault.DataVault, "open", open_later)
    return events


def _mock_verifier(chain, monkeypatch):
    """A wrapper whose Groth16 verifier is MockDecisionVerifier, and a prover that gives the one "proof" the mock accepts
    for the public inputs of the request. It proves nothing: it lets the path around the proof run without the circuit."""
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


def test_allowed_request_is_proved_and_verified_on_chain_before_any_data_are_delivered(app_test, onchain, monkeypatch, records):
    from services import commitment_service as cs, zk_decision_service
    if not zk_decision_service.decision_available():
        pytest.skip("the decision circuit is not built (zk/build)")
    c = _consent(scope=["Observation", "Medication"], patient=records.patient)
    _anchored(c)
    events = _order_of_events(monkeypatch)
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == [] and [b.label for b in at.button] == ["Request Data Access (decision proof, verified on chain)"]
    at = _submit(_declare(at, scope=["Observation"]))
    assert any(s.value == "Cryptographic Verification Successful — Access Granted." for s in at.success)
    assert events == ["verify", "open"]                               # verified on chain first, then decrypted
    check, access = _last(c.consent_id)
    m = access["metadata"]
    assert access["result"] == "GRANTED" and m["modules_released"] == ["Observation"] and _module_expanders(at) == ["OBSERVATION"]
    assert m["time_source"] == "block-timestamp" and m["proof_mode"] == "groth16" and m["zk_proof_verified"] is True
    reference = m["proof_reference"]
    assert set(reference) == {"digest", "mode", "tag", "tx_hash", "block_number", "reference"}
    assert reference["reference"]["verifier"] == onchain.stack["verifier"] and reference["reference"]["chain_id"] == onchain.chain_id
    # the reference is the transaction of the ConsentVerified event
    receipt = onchain.w3.eth.get_transaction_receipt(reference["tx_hash"])
    assert receipt["status"] == 1 and receipt["blockNumber"] == reference["block_number"] and receipt["to"] == onchain.stack["verifier"]
    assert receipt["gasUsed"] == reference["reference"]["gas_used"]
    (event,) = onchain.v4.DecisionVerifierContract(w3=onchain.w3, address=onchain.stack["verifier"], read_only=True) \
        .contract.events.ConsentVerified().process_receipt(receipt, errors=DISCARD)
    args = dict(event["args"])
    assert args["result"] is True and args["tag"] == int(reference["tag"]) and args["t"] == check["metadata"]["time"]["unix"]
    assert args["consentRoot"] == onchain.token.consent_root() and args["revocationRoot"] == onchain.token.revocation_root()
    assert set(args) == {"tag", "t", "role", "purpose", "context", "consentRoot", "revocationRoot", "result"}
    # with the nonce of the record the auditor opens the tag to the requester, and to nobody else
    assert cs.open_tag(reference["tag"], CLINICIAN, reference["reference"]["nonce"]) is True
    assert cs.open_tag(reference["tag"], REGISTRAR, reference["reference"]["nonce"]) is False
    badge = " ".join(x.value for x in at.markdown)
    assert "[DECISION PROOF VERIFIED ON CHAIN]" in badge and reference["tx_hash"] in badge and str(reference["tag"]) in badge
    assert any(x.value.startswith("Decision time ") and f"(block timestamp, block {check['metadata']['time']['block_number']})" in x.value for x in at.caption)


def test_proof_reference_of_an_accepted_verification_is_stored_with_the_data_access_record(onchain, monkeypatch):
    wrapper = _mock_verifier(onchain, monkeypatch)
    c = _consent()
    _anchored(c)
    events = _order_of_events(monkeypatch)
    out = _ask(c, source=_source)
    assert out["outcome"] == "GRANTED" and events == ["verify", "open"] and out["proof_error"] is None
    answer = out["verification"]
    assert answer["accepted"] is True and answer["contract"] == wrapper and answer["event"]["result"] is True
    reference = out["audit_event"]["metadata"]["proof_reference"]
    assert (reference["tx_hash"], reference["block_number"]) == (answer["tx_hash"], answer["block_number"])
    assert reference["reference"] == {"nonce": reference["reference"]["nonce"], "gas_used": answer["gas_used"], "verifier": wrapper,
                                      "chain_id": onchain.chain_id}
    assert answer["event"]["t"] == out["time"]["unix"] and out["time"]["source"] == "block-timestamp"
    assert onchain.w3.eth.get_transaction_receipt(reference["tx_hash"])["status"] == 1


def test_granted_request_on_sepolia_links_the_verification_transaction(app_test, onchain, monkeypatch):
    from blockchain import onchain_ui
    _mock_verifier(onchain, monkeypatch)
    c = _consent()
    _anchored(c)
    at = _submit(_declare(_clinician_screen(app_test, c.consent_id), scope=["Observation"]))
    assert any("Access Granted" in s.value for s in at.success)
    reference = _last(c.consent_id)[1]["metadata"]["proof_reference"]
    shown = " ".join(x.value for x in at.markdown)
    assert "[DECISION PROOF VERIFIED ON CHAIN]" in shown and reference["tx_hash"] in shown
    assert "View verification transaction on Etherscan" not in shown          # this chain has no public explorer
    status = dict(onchain.status, is_sepolia=True)                    # the same screen when the chain is Sepolia
    monkeypatch.setattr(onchain_ui, "_cached_status", lambda: status)
    at = _submit(at)
    reference = _last(c.consent_id)[1]["metadata"]["proof_reference"]
    link = f"[View verification transaction on Etherscan](https://sepolia.etherscan.io/tx/{reference['tx_hash']})"
    assert any(x.value == link for x in at.markdown)
    assert len({r["metadata"]["proof_reference"]["tag"] for r in _rows(c.consent_id, "DATA_ACCESS")}) == 2      # a fresh tag for each request


def test_refusal_of_the_verifier_contract_is_named_in_its_own_words_and_nothing_is_released(onchain, monkeypatch):
    from services import blockchain_service as bc
    _mock_verifier(onchain, monkeypatch)
    c, other = _consent(), _consent()
    _anchored(c)
    minted = _anchored(other)
    verify = bc.verify_decision

    def revoked_in_between(proof):                                    # another consent is revoked after the proof was made
        bc.token_client().revoke(minted["token_id"])
        return verify(proof)
    monkeypatch.setattr(bc, "verify_decision", revoked_in_between)
    blocks = onchain.w3.eth.block_number
    out = _ask(c, source=_source)
    assert out["outcome"] == "DENIED" and out["failed_checks"] == ["proof"] and out["deny_code"] is None and out["data"] == {}
    assert out["verification"]["accepted"] is False and out["verification"]["reason_text"] == "revocation root is not current"
    assert onchain.w3.eth.block_number == blocks + 1                  # the revocation, and no transaction for the refused proof
    m = out["audit_event"]["metadata"]
    assert m["zk_proof_verified"] is False and m["deny_code"] is None and m["modules_released"] == []
    assert m["proof_reference"]["reference"] == {"reason_text": "revocation root is not current"} and "tx_hash" not in m["proof_reference"]
    assert _code_fields(out["audit_event"]) == []


def test_request_at_the_local_token_is_refused_naming_the_proof(app_test, onchain):
    c = _consent()                                                    # the threshold is met and the mint is not confirmed yet
    blocks = onchain.w3.eth.block_number
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == []
    at = _submit(_declare(at, scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: proof." + RECORDED for e in at.error)
    assert any(x.value == "No proof could be made: the token of this consent is not confirmed on chain yet. "
               "Repeat the request when the anchoring is confirmed." for x in at.caption)
    _, access = _last(c.consent_id)
    m = access["metadata"]
    assert access["result"] == "DENIED" and m["failed_checks"] == ["proof"] and m["deny_code"] is None and m["modules_released"] == []
    assert m["proof_reference"] == {"reference": {"error": "the token of this consent is not confirmed on chain yet", "predicates": ["ISSUED"]}}
    assert m["time_source"] == "block-timestamp" and m["zk_proof_verified"] is False
    assert onchain.w3.eth.block_number == blocks                      # nothing was sent


def test_request_is_refused_naming_the_proof_when_the_circuit_is_not_built(onchain, monkeypatch):
    from services import zk_decision_service
    c = _consent()
    _anchored(c)
    monkeypatch.setattr(zk_decision_service, "decision_available", lambda depth=16: False)
    out = _ask(c)
    assert out["outcome"] == "DENIED" and out["failed_checks"] == ["proof"] and out["deny_code"] is None
    assert out["proof_error"] == "the decision circuit is not built on this machine" and out["verification"] is None
    assert out["audit_event"]["metadata"]["proof_reference"] == {"reference": {"error": "the decision circuit is not built on this machine"}}


def test_request_is_refused_naming_the_proof_when_the_prover_cannot_run(app_test, onchain, monkeypatch):
    import json
    from services import blockchain_service as bc, zk_decision_service
    c = _consent()
    _anchored(c)

    def prover_cannot_run(consent, requester_did, purpose, context, scope, now_ts):
        # what prove_decision raises when node fails: no predicate of the statement is named
        raise zk_decision_service.DecisionProofError([], "Cannot find module 'snarkjs'" + " x" * 200)
    monkeypatch.setattr(bc, "decision_proof", prover_cannot_run)
    blocks = onchain.w3.eth.block_number
    out = _ask(c)
    assert out["outcome"] == "DENIED" and out["failed_checks"] == ["proof"] and out["deny_code"] is None
    assert out["proof_error"] == "the prover gave no proof on this machine" and out["verification"] is None
    reference = out["audit_event"]["metadata"]["proof_reference"]["reference"]
    assert reference["error"] == "the prover gave no proof on this machine" and "predicates" not in reference
    assert reference["detail"].startswith("Cannot find module 'snarkjs'") and len(reference["detail"]) == 200
    # the record of the consent agrees with the chain, and nothing says otherwise
    row = json.dumps(out["audit_event"], default=str)
    assert "does not match what the chain holds" not in row and "does not match what the chain holds" not in str(out["reason"])
    assert out["audit_event"]["metadata"]["modules_released"] == [] and onchain.w3.eth.block_number == blocks
    # the screen says the same
    at = _submit(_declare(_clinician_screen(app_test, c.consent_id), scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: proof." + RECORDED for e in at.error)
    assert any(x.value == "No proof could be made: the prover gave no proof on this machine." for x in at.caption)
    assert not any("does not match what the chain holds" in x.value for x in at.caption)


def _prover_gives_no_proof(app_test, onchain, monkeypatch, node, detail):
    """The real proof path with node replaced: the request is refused naming the prover, not the chain."""
    import json
    from services import zk_decision_service
    c = _consent()
    _anchored(c)
    monkeypatch.setattr(zk_decision_service, "decision_available", lambda depth=16: True)
    monkeypatch.setattr(zk_decision_service, "_node", node)
    blocks = onchain.w3.eth.block_number
    out = _ask(c)
    assert out["outcome"] == "DENIED" and out["failed_checks"] == ["proof"] and out["deny_code"] is None
    assert out["proof_error"] == "the prover gave no proof on this machine" and out["verification"] is None
    m = out["audit_event"]["metadata"]
    assert m["proof_reference"] == {"reference": {"error": "the prover gave no proof on this machine", "detail": detail}}
    assert "the chain could not be read" not in json.dumps(out["audit_event"], default=str)
    assert m["deny_code"] is None and m["modules_released"] == [] and out["data"] == {}
    assert onchain.w3.eth.block_number == blocks                      # nothing was sent
    at = _submit(_declare(_clinician_screen(app_test, c.consent_id), scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: proof." + RECORDED for e in at.error)
    assert any(x.value == "No proof could be made: the prover gave no proof on this machine." for x in at.caption)
    assert not any("the chain could not be read" in x.value for x in at.caption) and not at.dataframe
    return out


def test_request_is_refused_naming_the_prover_when_it_does_not_answer_in_time(app_test, onchain, monkeypatch):
    import subprocess
    witnesses = []

    def node(script, arg, name, timeout=120):
        witnesses.append(arg)
        raise subprocess.TimeoutExpired(["node", script, arg, name], timeout)
    out = _prover_gives_no_proof(app_test, onchain, monkeypatch, node, "the prover did not answer within 120 seconds")
    assert witnesses and witnesses[0] not in str(out["audit_event"])  # the witness is not written into the record


def test_request_is_refused_naming_the_prover_when_its_output_is_not_json(app_test, onchain, monkeypatch):
    _prover_gives_no_proof(app_test, onchain, monkeypatch, lambda script, arg, name, timeout=120: "not json",
                           "the prover printed no proof: Expecting value: line 1 column 1 (char 0)")


def test_request_is_refused_naming_the_prover_when_its_output_is_not_a_proof_of_the_circuit(app_test, onchain, monkeypatch):
    _prover_gives_no_proof(app_test, onchain, monkeypatch,
                           lambda script, arg, name, timeout=120: '{"proof": {"protocol": "groth16"}, "publicSignals": ["1", "2", "3"]}',
                           "the prover printed no proof: the output is not a proof of this circuit")


def test_request_is_refused_naming_the_proof_when_no_verifier_is_configured(app_test, onchain, monkeypatch):
    from blockchain import onchain_ui
    c = _consent()
    _anchored(c)
    monkeypatch.delenv("VERIFIER_ADDRESS")
    status = dict(onchain.status, verifier=None)
    monkeypatch.setattr(onchain_ui, "_cached_status", lambda: status)
    at = _clinician_screen(app_test, c.consent_id)
    assert any(x.value == "Decision verifier: not configured. A request is refused, naming the proof." for x in at.sidebar.caption)
    at = _submit(_declare(at, scope=["Observation"]))
    assert any(e.value == "Access Denied. Failed checks: proof." + RECORDED for e in at.error)
    assert any(x.value == "No proof could be made: no decision verifier is configured." for x in at.caption)
    m = _last(c.consent_id)[1]["metadata"]
    assert m["proof_reference"] == {"reference": {"error": "no decision verifier is configured"}} and m["modules_released"] == []


def test_trees_rebuilt_from_the_chain_have_the_roots_of_the_contract(onchain):
    from services import blockchain_service as bc
    first, second, third = _consent(), _consent(), _consent()
    for c in (first, second, third):
        _anchored(c)
    bc.revoke_onchain(second)
    consent_tree, revocation_tree = bc.chain_trees()
    assert consent_tree.root == onchain.token.consent_root() and revocation_tree.root == onchain.token.revocation_root()
    assert consent_tree.count == 3 and revocation_tree.revoked() == [1]
    assert consent_tree.index_of(third.commitment) == 2 and consent_tree.index_of(_consent().commitment) is None


# ---- D1: the words --------------------------------------------------------------------------------------------------

def test_role_and_labels_say_clinician_and_the_jurisdiction_field_is_the_context(app_test):
    c = _consent()
    at = app_test.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    assert list(at.sidebar.selectbox[0].options) == ["Patient", "Guardian", "Clinician", "Auditor"]
    labels = lambda page: [w.label for group in (page.text_input, page.text_area, page.selectbox, page.multiselect,
                                                 page.number_input, page.button) for w in group]
    patient = labels(at)
    assert "Authorised Clinician DID" in patient and "Consent Context (jurisdiction code)" in patient
    seen = patient + [_page_text(at)]
    at = _declare(_clinician_screen(app_test, c.consent_id), scope=["Observation"])
    clinician = labels(at)
    assert "Your Clinician DID (requester)" in clinician and "Request Context (jurisdiction code)" in clinician
    assert any(x.value.startswith("Clinician credential verified: ") for x in at.caption)
    at = _submit(at)
    seen += clinician + [_page_text(at)]
    at.sidebar.selectbox[0].set_value("Auditor").run()
    seen += labels(at) + [_page_text(at)]
    # the identifier of the demonstration credential is data of the issuer and keeps its form
    text = " | ".join(seen).replace("urn:halah:vc:doctor:", "")
    assert "doctor" not in text.lower() and "Jurisdiction (policy context)" not in text
    assert "Decision matrix - ALLOW = VI AND VA AND VP AND VT AND VL" in text


def test_auditor_screen_shows_the_stored_role_key_as_clinician(app_test):
    c = _consent()
    _ask(c, source=_source)
    stored = _rows(c.consent_id, "DATA_ACCESS")[-1]
    assert stored["actor_role"] == "Doctor"                           # the key of the stored record is unchanged
    at = app_test.from_file(os.path.join(ROOT, "app.py"), default_timeout=120).run()
    at.sidebar.selectbox[0].set_value("Auditor").run()
    [s for s in at.selectbox if s.label == "Select Consent to Audit"][0].set_value(c.consent_id).run()
    lifecycle = " ".join(x.value for x in at.markdown)
    assert "Role: `Clinician`" in lifecycle and "Role: `Doctor`" not in lifecycle
    for table in at.dataframe:
        roles = set(table.value["actor_role"])
        assert "Clinician" in roles and "Doctor" not in roles


def test_guardian_screen_names_the_consent_with_its_state(app_test, anchor_calls):
    c = _consent(approvals=[], token=False)
    at = _guardian_screen(app_test, c.consent_id)
    assert any(i.value == f"Found consent for Patient: `{PATIENT}` (state: PENDING_SIGNATURE)" for i in at.info)
    lines = lambda at: [i.value for i in at.info if i.value.startswith("Found consent for Patient")]
    at = _approve(at, "did:parent:A")                                 # the page of a click names the state the click left
    assert lines(at) == [f"Found consent for Patient: `{PATIENT}` (state: PENDING_SIGNATURE)"]
    at = _approve(at, "did:parent:B")
    assert lines(at) == [f"Found consent for Patient: `{PATIENT}` (state: ACTIVE)"]
    assert any("Multi-sig: 2/2" in s.value for s in at.success) and any("[SBT MINTED - LOCAL LEDGER]" in m.value for m in at.markdown)
    at = _guardian_screen(app_test, c.consent_id)
    assert any(i.value == f"Found consent for Patient: `{PATIENT}` (state: ACTIVE)" for i in at.info)


# ---- the trigger of Algorithm 6.3 on the clinician screen ------------------------------------------------------------

def test_attestation_is_signed_at_the_trusted_time_and_its_answer_is_shown_after_the_rerun(app_test, monkeypatch):
    from services import blockchain_service as bc, time_source, trigger_service
    c = _consent()
    trigger_service.add_trigger(c, "Hospital admission confirmed", attester_role="doctor", actor_did=PATIENT, actor_role="Patient")
    # the trusted time lies ten minutes behind the server clock, as the latest block of a slow chain does
    monkeypatch.setattr(bc, "chain_time", lambda: time_source.read_time(lambda: datetime.now() - timedelta(minutes=10)))
    at = _clinician_screen(app_test, c.consent_id)
    assert _failed(at) == ["VL"] and any(x.value == "Failed checks: VL | Deny code: AWAITING-TRIGGER" for x in at.caption)
    assert any(x.value == "Event: **Hospital admission confirmed** (attester role: clinician)" for x in at.markdown)
    [b for b in at.button if b.label == f"Attest this event as {CLINICIAN}"][0].click().run()
    assert not at.exception
    assert any(s.value == "Attestation verified and recorded. The trigger is satisfied." for s in at.success)
    (row,) = _rows(c.consent_id, "PRESENT_ATTESTATION")
    assert row["result"] == "SUCCESS" and row["actor_did"] == CLINICIAN
    assert datetime.fromisoformat(row["metadata"]["signed_at"]) <= datetime.fromisoformat(row["metadata"]["presented_at"])
    assert _failed(at) == [] and not trigger_service.waiting_triggers(c)
    at.run()                                                          # the answer is shown once
    assert not any("Attestation verified" in s.value for s in at.success)


def test_refused_attestation_is_explained_in_plain_words():
    from services import trigger_service
    assert trigger_service.refusal_words(trigger_service.ATTESTATION_SIGNATURE_INVALID) == "the attestation is not signed by the attester for this consent"
    assert trigger_service.refusal_words(trigger_service.ATTESTER_NOT_AUTHORISED) == "the attester holds no valid credential with the required role"
    assert trigger_service.refusal_words(trigger_service.CONSENT_REVOKED) == trigger_service.refusal_words(trigger_service.CONSENT_EXPIRED)
    for reason, words in trigger_service.REFUSAL_WORDS.items():
        assert reason not in words and words == words.lower()
    assert trigger_service.refusal_words("SOMETHING-ELSE") == "the attestation could not be verified"
