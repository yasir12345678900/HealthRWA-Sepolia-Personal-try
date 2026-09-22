"""Base offline tests - no network, no keys."""
import json, os, re


def test_did_to_address_is_deterministic_and_checksummed():
    from blockchain.contract import did_to_address
    a1 = did_to_address("did:patient:alice"); a2 = did_to_address("did:patient:alice")
    assert a1 == a2 and a1.startswith("0x") and len(a1) == 42
    assert did_to_address("did:patient:bob") != a1


def test_not_configured_without_env(monkeypatch):
    monkeypatch.delenv("CONTRACT_ADDRESS", raising=False); monkeypatch.delenv("PRIVATE_KEY", raising=False)
    from blockchain import contract
    assert contract.is_configured() is False


def test_audit_offchain_event_has_no_fake_tx_hash():
    from database import audit_db
    e = audit_db.log("did:patient:x", "Patient", "CREATE_CONSENT", "did:patient:x", "cid-1")
    assert e["tx_hash"] is None and e["block_number"] is None and e["onchain"] is False
    assert re.fullmatch(r"0x[0-9a-f]{64}", e["event_digest"])


def test_audit_onchain_event_keeps_real_tx_hash():
    from database import audit_db
    real = "0x" + "ab" * 32
    e = audit_db.log("Blockchain", "SmartContract", "ONCHAIN_MINT", "did:patient:x", "cid-1", tx_hash=real, block_number=11750000)
    assert e["tx_hash"] == real and e["block_number"] == 11750000 and e["onchain"] is True


def test_v2_abi_has_consent_functions():
    abi = json.load(open(os.path.join("blockchain", "abi", "ConsentSBTv2.json")))["abi"]
    names = {x.get("name") for x in abi if x.get("type") == "function"}
    assert {"mintConsent", "revoke", "checkValid", "owner"} <= names


def test_no_fake_placeholders_left_in_app():
    src = open("app.py", encoding="utf-8").read()
    for bad in ("0x1c8b9f...a4e2d3", "18402195", 'consent.token_id = "SBT001"', "Execute Zero-Knowledge Access"):
        assert bad not in src
