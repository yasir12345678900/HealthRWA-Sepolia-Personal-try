"""What the application records when the background on-chain mint of a consent fails, and that it can be retried."""
import threading
from datetime import datetime, timedelta
from database import consent_db, audit_db, db
from services import anchor_service, blockchain_service as bc
from services.consent_service import create_consent
from services.identity_service import sign_consent
from services.access_service import guardian_approvals


def _approved_consent():
    c = create_consent("did:patient:x", "did:hospital:001", ["did:parent:A", "did:parent:B"], ["Observation"], "Treatment",
                       (datetime.now() - timedelta(days=1)).isoformat(), (datetime.now() + timedelta(days=30)).isoformat())
    for g in c.guardian_dids:
        s, a = sign_consent(g, c.consent_id); c.signatures.append(g); c.signature_data[g] = {"signer": a, "signature": s}
    assert len(guardian_approvals(c)) == c.threshold
    c.token_id = f"SBT-LOCAL-{c.consent_id[:8]}"; consent_db.save(c)
    return c


def _anchor(c):
    job = anchor_service.anchor_async(consent_db.get(c.consent_id), audit_db, consent_db)
    for t in threading.enumerate():
        if t.name == f"anchor-{c.consent_id[:8]}":
            t.join(timeout=30)
    return job


def _mints(c):
    return [e for e in audit_db.get() if e["consent_id"] == c.consent_id and e["action"] == "ONCHAIN_MINT"]


def _stored_token(c):
    return [r for r in db.all_rows("consents") if r["consent_id"] == c.consent_id][0]["token_id"]


def _raise(consent):
    raise RuntimeError("rpc down")


def test_mint_that_raises_is_recorded_as_failed_and_keeps_the_local_token(monkeypatch):
    monkeypatch.setattr(bc, "mint_consent", _raise)                 # the endpoint is down
    c = _approved_consent()
    job = _anchor(c)
    assert job["status"] == "failed" and "rpc down" in job["error"]
    assert anchor_service.job_status(c.consent_id) is job
    rows = _mints(c)
    assert len(rows) == 1 and rows[0]["result"] == "FAILED"
    assert "rpc down" in rows[0]["metadata"]["error"]
    assert rows[0]["tx_hash"] is None and rows[0]["onchain"] is False
    assert consent_db.get(c.consent_id).token_id == f"SBT-LOCAL-{c.consent_id[:8]}"
    assert _stored_token(c) == f"SBT-LOCAL-{c.consent_id[:8]}"    # no on-chain token number written


def test_reverted_mint_receipt_is_recorded_as_failed_and_keeps_the_local_token(monkeypatch):
    reverted = {"tx_hash": "0x" + "ab" * 32, "status": 0, "block_number": 11, "gas_used": 21000, "token_id": None,
                "explorer_tx": "https://sepolia.etherscan.io/tx/0x" + "ab" * 32}
    monkeypatch.setattr(bc, "mint_consent", lambda consent: reverted)
    c = _approved_consent()
    _anchor(c)
    rows = _mints(c)
    assert len(rows) == 1 and rows[0]["result"] == "FAILED"
    assert consent_db.get(c.consent_id).token_id == f"SBT-LOCAL-{c.consent_id[:8]}"
    assert _stored_token(c) == f"SBT-LOCAL-{c.consent_id[:8]}"


def test_failed_mint_can_be_submitted_again(monkeypatch):
    monkeypatch.setattr(bc, "mint_consent", _raise)
    c = _approved_consent()
    first = _anchor(c)
    assert first["status"] == "failed"
    ok = {"tx_hash": "0x" + "cd" * 32, "status": 1, "block_number": 12, "gas_used": 180000, "token_id": 42,
          "explorer_tx": "https://sepolia.etherscan.io/tx/0x" + "cd" * 32}
    monkeypatch.setattr(bc, "mint_consent", lambda consent: ok)
    second = _anchor(c)
    assert second is not first and second["status"] == "done"     # a new job, not the failed one
    assert anchor_service.job_status(c.consent_id) is second
    rows = _mints(c)
    assert [r["result"] for r in rows] == ["FAILED", "SUCCESS"]
    assert rows[-1]["tx_hash"] == ok["tx_hash"] and rows[-1]["block_number"] == 12
    assert rows[-1]["metadata"]["token_id"] == 42 and rows[-1]["metadata"]["gas_used"] == 180000
    assert consent_db.get(c.consent_id).token_id == "SBT-42"
    assert _stored_token(c) == "SBT-42"
