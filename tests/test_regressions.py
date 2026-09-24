"""Regressions found in the 2026-09-24 end-to-end review."""
from datetime import datetime, timedelta
from types import SimpleNamespace


def _consent(**kw):
    from models.consent import Consent
    c = Consent("reg-1", "did:patient:x", "did:hospital:001", ["did:parent:A"], "Treatment", ["Observation"], 1,
                ["did:parent:A"], datetime.now().isoformat(), (datetime.now() + timedelta(days=30)).isoformat())
    c.token_id = "SBT-1"
    for k, v in kw.items():
        setattr(c, k, v)
    return c


def test_discard_available_for_v3_receipt_decoding():
    # mint_consent_v3 used DISCARD without importing it -> token_id was always None on v3
    from blockchain import contract
    assert hasattr(contract, "DISCARD")


def test_reconcile_reads_v3_expiry_field(monkeypatch):
    from services import anchor_service, blockchain_service as bc
    from blockchain.contract import did_to_address
    c = _consent(token_id=None)
    exp = bc._expiry_ts(c)
    rec = (did_to_address(c.patient_did), did_to_address(c.requester_did), b"p", 1, exp, b"AU", False, 2)
    ev = {"args": {"from": anchor_service.ZERO, "tokenId": 7}, "transactionHash": b"\x01" * 32, "blockNumber": 9}
    fake = SimpleNamespace(
        w3=SimpleNamespace(eth=SimpleNamespace(block_number=100), to_hex=lambda b: "0x" + b.hex()),
        has_v3=lambda: True,
        contract=SimpleNamespace(
            events=SimpleNamespace(Transfer=lambda: SimpleNamespace(get_logs=lambda **k: [ev])),
            functions=SimpleNamespace(consents=lambda t: SimpleNamespace(call=lambda: rec))))
    monkeypatch.setattr(bc.chain, "ConsentContract", lambda: fake)
    assert [t[0] for t in anchor_service.find_onchain_tokens(c)] == [7]


def test_v3_contract_compat_mint_does_not_use_external_self_call():
    src = open("contracts/ConsentSBTv3.sol").read()
    assert "this.mintConsentV3" not in src


def test_jurisdiction_mismatch_denies():
    from services.access_service import evaluate_allow
    m = evaluate_allow(_consent(jurisdiction="AU"), "US")
    assert m["VL"] is False and m["ALLOW"] is False


def test_partially_corrupted_csv_is_salvaged(tmp_path):
    from database.repository import SyntheaRepository
    uid = "fe621c76-a591-b7be-5668-b77f00240d82"
    good = f"2017-01-01,{uid},vital,Body Height,167.7\n".encode()
    (tmp_path / "observations.csv").write_bytes(b"DATE,PATIENT,CATEGORY,DESCRIPTION,VALUE\n" + good + b"\xf7\xdb\x8d garbage,\xad\n" + good)
    frame = SyntheaRepository._load_csv(str(tmp_path), "observations.csv")
    assert len(frame) == 2 and set(frame["PATIENT"]) == {uid}
