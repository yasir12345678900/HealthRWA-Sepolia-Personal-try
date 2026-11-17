"""The independent verification tool (tools/verify_poc.py) on the verification of a decision proof: the transaction
that a DATA_ACCESS row names as its proof reference must have gone to the decision verifier of the configuration, and
the proof read back from that transaction must hold against the Groth16 verifier behind it.

The chain is an in-memory EVM with the real bytecode of blockchain/abi (no network, no Sepolia). The fixtures and the
helpers are those of tests/test_verify_poc_v4.py. The granted request of these tests is verified by a wrapper whose
Groth16 verifier is MockDecisionVerifier, which proves nothing."""
from test_verify_poc_v4 import base, onchain, _granted, _issued, _ledger, _mock_verifier, _run      # fixtures and helpers


def test_verification_that_went_to_another_contract_than_the_configured_verifier_fails(onchain, monkeypatch):
    from services import blockchain_service as bc
    from tools import verify_poc
    configured = bc.verifier_client                                   # the decision verifier that the settings name
    wrapper = _mock_verifier(onchain, monkeypatch)                    # the request is verified by another contract
    c, _ = _issued()
    out = _granted(c)
    events, consents = _ledger(c)
    assert _run(onchain, events, consents)[0] is True                 # read with the contract that verified, the ledger passes
    lines = []
    reader = configured(read_only=True)
    assert reader.address.lower() == onchain.stack["verifier"].lower() != wrapper.lower()
    ok = verify_poc.verify_v4(bc.token_client(read_only=True), events, consents, reader, out=lines.append)
    assert ok is False and lines[-1] == "RESULT: SOME CHECKS FAILED"
    tx = out["verification"]["tx_hash"]
    named = [line for line in lines if f"verification {tx}" in line]
    assert len(named) == 1 and named[0].startswith("  [XX] DATA_ACCESS ") and named[0].lower().endswith(f"to {wrapper.lower()}")


def test_proof_that_does_not_hold_when_it_is_read_back_fails(onchain, monkeypatch):
    _mock_verifier(onchain, monkeypatch)
    c, _ = _issued()
    _granted(c)
    events, consents = _ledger(c)
    ok, lines = _run(onchain, events, consents)
    assert ok is True and any("[OK]   the proof read back from the transaction verifies again" in line for line in lines)
    # the Groth16 verifier answers that the proof of the transaction does not hold
    monkeypatch.setattr(onchain.v4.DecisionVerifierContract, "reverify", lambda self, proof, public_signals=None: False)
    ok, lines = _run(onchain, events, consents)
    assert ok is False and any("[XX]   the proof read back from the transaction verifies again" in line for line in lines)
