"""The independent verification tool on ConsentSBTv4 (thesis Section 8.4.4): tools/verify_poc.py fetches the receipt of
every anchored transaction, recomputes each token's commitment from the local record, and compares it and the
revocation state with the chain. It holds no key.

The chain is an in-memory EVM with the real bytecode of blockchain/abi (no network, no Sepolia). The key of the owner is
derived from a label in this file: it is a test key and holds nothing. The ledger of each test is built by the functions
the application calls. One test needs the built decision circuit (zk/build) and is skipped without it. The others
replace the Groth16 verifier by MockDecisionVerifier, which proves nothing."""
import copy
import os
from datetime import datetime, timedelta
from types import SimpleNamespace
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_KEY_LABEL = "halah verification tool test owner"          # the owner key is derived from this label (not a secret)
PATIENT, CLINICIAN = "did:patient:x", "did:hospital:001"
G = ["did:parent:A", "did:parent:B"]


# ---- fixtures and helpers ----------------------------------------------------------------------------------------------

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
def onchain(base, monkeypatch):
    """The services in on-chain mode against the in-memory chain, in its fresh state for each test."""
    from services import blockchain_service as bc
    monkeypatch.setenv("CHAIN_ID", str(base.chain_id))
    monkeypatch.setenv("CONTRACT_V4_ADDRESS", base.stack["token"])
    monkeypatch.setenv("VERIFIER_ADDRESS", base.stack["verifier"])
    monkeypatch.setenv("PRIVATE_KEY", base.key_hex)
    monkeypatch.setattr(bc, "token_client", lambda read_only=False: base.v4.ConsentContractV4(
        w3=base.w3, address=base.stack["token"], private_key=None if read_only else base.key, read_only=read_only))
    monkeypatch.setattr(bc, "verifier_client", lambda read_only=False: base.v4.DecisionVerifierContract(
        w3=base.w3, address=base.stack["verifier"], private_key=None if read_only else base.key, read_only=read_only))
    snapshot = base.tester.take_snapshot()
    yield base
    base.tester.revert_to_snapshot(snapshot)


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


def _issued(scope=("Observation",)):
    """A consent created, approved by both guardians over its commitment and minted on ConsentSBTv4, with the ledger
    rows the application writes for it."""
    from database import audit_db, consent_db
    from services import blockchain_service as bc, commitment_service, identity_service as ids
    from services.consent_service import create_consent
    c = create_consent(PATIENT, CLINICIAN, list(G), list(scope), "Treatment", (datetime.now() - timedelta(days=1)).isoformat(),
                       (datetime.now() + timedelta(days=30)).isoformat(), threshold=2, context="AU")
    commitment_service.commit_consent(c)
    for g in G:
        signature, address = ids.sign_consent_v2(g, c.consent_id, c.commitment)
        c.signatures.append(g)
        c.signature_data[g] = {"scheme": "EIP-712", "version": 2, "signer": address, "signature": signature}
    receipt = bc.mint_consent(c)
    c.token_id = f"SBT-{receipt['token_id']}"
    consent_db.save(c)
    audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT", patient_did=c.patient_did,
                 consent_id=c.consent_id, scope=c.scope, purpose=c.purpose, result="SUCCESS", tx_hash=receipt["tx_hash"],
                 block_number=receipt["block_number"], metadata={"token_id": receipt["token_id"], "gas_used": receipt["gas_used"]})
    return c, receipt["token_id"]


def _source(patient_did, scope):
    return {module: [{"module": module, "patient": patient_did}] for module in scope}


def _granted(c):
    from services import request_service
    out = request_service.submit_request(c, CLINICIAN, ["Observation"], "Treatment", "AU", source=_source)
    assert out["outcome"] == "GRANTED"
    return out


def _revoked(c):
    from services import blockchain_service as bc, request_service, revocation_service
    t, _ = request_service.decision_time()
    signature, _ = revocation_service.sign_revocation(c.patient_did, c.consent_id)
    out = revocation_service.revoke(c, c.patient_did, signature=signature, now=t["time"], time_label=t["source"],
                                    onchain_revoke=bc.revoke_onchain)
    assert out["result"] == "REVOKED" and out["complete"] is True
    return out


def _ledger(*consents):
    """The rows of the database file for these consents: (events in order, consent records)."""
    from database import db
    ids = {c.consent_id for c in consents}
    return ([e for e in db.all_rows("audit", "ts") if e.get("consent_id") in ids],
            [r for r in db.all_rows("consents") if r["consent_id"] in ids])


def _run(chain, events, consents, verifier=True):
    """The tool with read-only clients, as an auditor runs it: (passed, the printed lines)."""
    from services import blockchain_service as bc
    from tools import verify_poc
    lines = []
    token = bc.token_client(read_only=True)
    reader = bc.verifier_client(read_only=True) if verifier else None
    assert token.account is None and (reader is None or reader.account is None)          # no key is held
    return verify_poc.verify_v4(token, events, consents, reader, out=lines.append), lines


# ---- the checks --------------------------------------------------------------------------------------------------------

def test_ledger_of_a_mint_a_verified_request_and_a_revocation_passes_without_a_key(onchain, monkeypatch):
    _mock_verifier(onchain, monkeypatch)
    kept, kept_token = _issued()
    gone, gone_token = _issued(scope=["Observation", "Medication"])
    granted = _granted(gone)
    _revoked(gone)
    events, consents = _ledger(kept, gone)
    ok, lines = _run(onchain, events, consents)
    text = "\n".join(lines)
    assert ok is True and lines[-1] == "RESULT: ALL CHECKS PASSED" and "[XX]" not in text
    # every transaction of the ledger was fetched: two mints and one revoke, and the verification behind the request
    anchored = [e for e in events if e.get("tx_hash")]
    assert [e["action"] for e in anchored] == ["ONCHAIN_MINT", "ONCHAIN_MINT", "ONCHAIN_REVOKE"]
    assert all(any(e["tx_hash"] in line and "[OK]" in line and "SUCCESS" in line for line in lines) for e in anchored)
    assert any(granted["verification"]["tx_hash"] in line and "[OK]" in line for line in lines)
    # the token that still has its opening: the commitment is recomputed from the local record and found on chain
    at = lines.index(f"Consent {kept.consent_id} -> token #{kept_token} (mint in block {anchored[0]['block_number']})")
    assert "[OK] commitment recomputed from the opening of the local record == commitment on chain" in lines[at + 2]
    assert "[OK] the local record still holds the values that were committed" in lines[at + 3]
    assert lines[at + 5].endswith("revocation state: chain revoked=False checkValid=True | local revoked=False")
    # the revoked one: its opening is deleted, so the tool says that the revocation state alone is compared
    at = [i for i, line in enumerate(lines) if line.startswith(f"Consent {gone.consent_id} -> token #{gone_token} ")][0]
    assert "cannot be recomputed" in lines[at + 2] and "[--]" in lines[at + 2]
    assert lines[at + 3].endswith("revocation state: chain revoked=True checkValid=False | local revoked=True")
    assert any(f"ConsentRevoked names token [{gone_token}] == token #{gone_token} of consent {gone.consent_id}" in line for line in lines)
    assert any("the request tag opens to the requester of the row with the recorded nonce" in line and "[OK]" in line for line in lines)
    assert any("the proof read back from the transaction verifies again" in line and "[OK]" in line for line in lines)


def test_changed_opening_or_a_changed_record_fails_the_commitment_check(onchain):
    c, _ = _issued()
    events, consents = _ledger(c)
    assert _run(onchain, events, consents)[0] is True
    changed = copy.deepcopy(consents)
    changed[0]["commitment_opening"]["scopeMask"] = "15"              # the opening no longer hashes to the commitment on chain
    ok, lines = _run(onchain, events, changed)
    assert ok is False and lines[-1] == "RESULT: SOME CHECKS FAILED"
    assert any("[XX] commitment recomputed from the opening of the local record == commitment on chain" in line for line in lines)
    changed = copy.deepcopy(consents)
    changed[0]["scope"] = ["Observation", "Procedure"]                # the record was widened after the guardians approved
    ok, lines = _run(onchain, events, changed)
    assert ok is False and any("[XX] the local record still holds the values that were committed" in line for line in lines)
    assert any("[OK] commitment recomputed from the opening" in line for line in lines)   # the opening itself is intact
    changed = copy.deepcopy(consents)
    changed[0]["commitment_opening"] = None                           # an opening that is missing without a revocation
    ok, lines = _run(onchain, events, changed)
    assert ok is False and any("holds no opening although the consent is not revoked" in line for line in lines)


def test_revocation_that_is_missing_on_chain_or_missing_in_the_record_fails(onchain):
    from services import blockchain_service as bc
    c, token = _issued()
    events, consents = _ledger(c)
    marked = copy.deepcopy(consents)
    marked[0]["revoked"] = True                                       # revoked in the record, still valid on chain
    ok, lines = _run(onchain, events, marked)
    assert ok is False and any("[XX] revocation state: chain revoked=False checkValid=True | local revoked=True" in line for line in lines)
    bc.token_client().revoke(token)                                   # revoked on chain, the record knows nothing of it
    ok, lines = _run(onchain, events, consents)
    assert ok is False and any("[XX] revocation state: chain revoked=True checkValid=False | local revoked=False" in line for line in lines)
    assert _run(onchain, events, marked)[0] is True                   # with both in the same state the check passes again


def test_transaction_that_is_unknown_or_in_another_block_fails(onchain):
    c, _ = _issued()
    events, consents = _ledger(c)
    moved = copy.deepcopy(events)
    moved[-1]["block_number"] += 1
    ok, lines = _run(onchain, moved, consents)
    assert ok is False and any("[XX] ONCHAIN_MINT" in line and f"(ledger {moved[-1]['block_number']})" in line for line in lines)
    unknown = copy.deepcopy(events)
    unknown[-1]["tx_hash"] = "0x" + "12" * 32
    ok, lines = _run(onchain, unknown, consents)
    assert ok is False and any("NOT FOUND" in line for line in lines)


def test_revoke_that_names_another_token_fails(onchain):
    first, _ = _issued()
    second, _ = _issued()
    _revoked(second)
    events, consents = _ledger(first, second)
    assert _run(onchain, events, consents)[0] is True
    swapped = copy.deepcopy(events)
    for e in swapped:
        if e["action"] == "ONCHAIN_REVOKE":
            e["consent_id"] = first.consent_id                        # the ledger claims the revoke for the other consent
    ok, lines = _run(onchain, swapped, consents)
    assert ok is False and any("[XX] ONCHAIN_REVOKE" in line and "ConsentRevoked names token" in line for line in lines)


def test_proof_reference_that_does_not_open_to_the_requester_fails(onchain, monkeypatch):
    _mock_verifier(onchain, monkeypatch)
    c, _ = _issued()
    _granted(c)
    events, consents = _ledger(c)
    assert _run(onchain, events, consents)[0] is True
    other = copy.deepcopy(events)
    access = [e for e in other if e["action"] == "DATA_ACCESS"][0]
    access["actor_did"] = "did:hospital:002"                          # the row names another requester than the tag hides
    ok, lines = _run(onchain, other, consents)
    assert ok is False and any("[XX]   the request tag opens to the requester" in line for line in lines)
    ok, lines = _run(onchain, events, consents, verifier=False)       # without the verifier address the proof cannot be checked
    assert ok is False and any("VERIFIER_ADDRESS is not set" in line for line in lines)


def test_decision_that_was_not_taken_at_the_block_timestamp_fails(onchain, monkeypatch):
    from services import blockchain_service as bc, request_service, time_source
    from tools import verify_poc
    _mock_verifier(onchain, monkeypatch)
    c, _ = _issued()
    _granted(c)
    with monkeypatch.context() as m:                                  # one request while the chain cannot be read

        def unreadable():
            raise time_source.TimeSourceError("the node did not answer")
        m.setattr(bc, "chain_time", unreadable)
        refused = request_service.submit_request(c, CLINICIAN, ["Observation"], "Treatment", "AU", source=_source)
        assert (refused["outcome"], refused["time_source"], refused["failed_checks"]) == ("DENIED", "unavailable", ["time source"])
    events, consents = _ledger(c)
    decided = [e for e in events if e["action"] in ("STATE_CHECK", "DATA_ACCESS")]
    assert [(e["action"], e["result"]) for e in decided] == [("STATE_CHECK", "ACTIVE"), ("DATA_ACCESS", "GRANTED"), ("DATA_ACCESS", "DENIED")]
    # every decision at the block timestamp, and the refusal that used no time: the check passes
    ok, lines = _run(onchain, events, consents)
    assert ok is True and "  [OK] time source: the 3 STATE_CHECK and DATA_ACCESS rows that name one name the block timestamp" in lines
    assert verify_poc.time_sources(events) == (decided, [])
    # a request decided at the server clock, and a lifecycle check at the server clock: each row is named and fails
    for action, place in (("DATA_ACCESS", lambda metadata: metadata), ("STATE_CHECK", lambda metadata: metadata["time"])):
        changed = copy.deepcopy(events)
        row = [e for e in changed if e["action"] == action][0]
        place(row["metadata"])["time_source" if action == "DATA_ACCESS" else "source"] = "system-clock-fallback"
        ok, lines = _run(onchain, changed, consents)
        assert ok is False and lines[-1] == "RESULT: SOME CHECKS FAILED"
        (failed,) = [line for line in lines if "[XX]" in line]
        assert failed.startswith(f"  [XX] time source: {action} {row['event_id'][:8]} of consent {c.consent_id} ")
        assert failed.endswith("names system-clock-fallback, not the block timestamp")
        named = verify_poc.time_sources(changed)[1]
        assert [(n["event_id"], n["action"], n["time_source"]) for n in named] == [(row["event_id"], action, "system-clock-fallback")]
    # a lifecycle check that says its time was unavailable is not the refusal of a request: it fails as well
    changed = copy.deepcopy(events)
    [e for e in changed if e["action"] == "STATE_CHECK"][0]["metadata"]["time"]["source"] = "unavailable"
    assert _run(onchain, changed, consents)[0] is False


def test_real_proof_of_a_granted_request_is_verified_again_from_the_chain(onchain):
    from services import zk_decision_service
    if not zk_decision_service.decision_available():
        pytest.skip("the decision circuit is not built (zk/build)")
    c, _ = _issued()
    out = _granted(c)                                                 # the Groth16 proof, accepted by the verifier contract
    assert out["verification"]["accepted"] is True
    events, consents = _ledger(c)
    ok, lines = _run(onchain, events, consents)
    assert ok is True and lines[-1] == "RESULT: ALL CHECKS PASSED"
    assert any("[OK]   the proof read back from the transaction verifies again" in line for line in lines)
    assert any("[OK] the decision verifier reads its roots from this consent contract" in line for line in lines)


def test_main_takes_the_new_contract_when_it_is_configured_and_the_older_one_otherwise(onchain, monkeypatch, capsys):
    from services import blockchain_service as bc
    from tools import verify_poc
    c, _ = _issued()
    events, consents = _ledger(c)
    monkeypatch.setattr(verify_poc, "main_v3", lambda: 3)
    assert verify_poc.main([], token=bc.token_client(read_only=True), verifier=bc.verifier_client(read_only=True),
                           events=events, consents=consents) == 0
    assert capsys.readouterr().out.rstrip().endswith("RESULT: ALL CHECKS PASSED")
    broken = copy.deepcopy(consents)
    broken[0]["revoked"] = True
    assert verify_poc.main([], token=bc.token_client(read_only=True), events=events, consents=broken) == 1
    assert capsys.readouterr().out.rstrip().endswith("RESULT: SOME CHECKS FAILED")
    assert verify_poc.main(["v3"], token=bc.token_client(read_only=True)) == 3       # the older contract on request
    monkeypatch.delenv("CONTRACT_V4_ADDRESS")
    assert verify_poc.main([]) == 3                                   # and when ConsentSBTv4 is not configured
