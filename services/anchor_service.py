"""Navigation-proof anchoring + chain reconciliation. anchor_async(): background mint that writes the
ledger itself. reconcile(): back-fills a consent that was minted on-chain but never recorded locally."""
import logging, threading
from services import blockchain_service as bc
log = logging.getLogger("halah.anchor")
_JOBS = {}; _LOCK = threading.Lock()
ZERO = "0x0000000000000000000000000000000000000000"

def _is_real(token_id):
    t = str(token_id or ""); return t.startswith("SBT-") and t[4:].isdigit()

def job_status(consent_id):
    return _JOBS.get(consent_id)

def anchor_async(consent, audit_db, consent_db):
    cid = consent.consent_id
    with _LOCK:
        j = _JOBS.get(cid)
        if j and j.get("status") == "running": return j
        job = {"status": "running", "consent_id": cid}; _JOBS[cid] = job
    def run():
        try:
            r = bc.mint_consent(consent)
            if r.get("token_id") is not None: consent.token_id = f"SBT-{r['token_id']}"
            consent_db.update(consent)
            audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT",
                         patient_did=consent.patient_did, consent_id=cid, scope=consent.scope, purpose=consent.purpose,
                         result="SUCCESS" if r.get("status") == 1 else "FAILED", tx_hash=r.get("tx_hash"),
                         block_number=r.get("block_number"),
                         metadata={"token_id": r.get("token_id"), "gas_used": r.get("gas_used"), "explorer_tx": r.get("explorer_tx"), "async": True})
            job.update(status="done", result=r)
        except Exception as e:
            log.warning("async anchor failed for %s: %s", cid, e)
            audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT",
                         patient_did=consent.patient_did, consent_id=cid, result="FAILED", metadata={"error": str(e)[:300], "async": True})
            job.update(status="failed", error=str(e)[:300])
    threading.Thread(target=run, daemon=True, name=f"anchor-{cid[:8]}").start()
    return job

def find_onchain_tokens(consent, lookback_blocks=60000):
    from blockchain.contract import did_to_address
    c = bc.chain.ConsentContract(); w3 = c.w3
    patient = did_to_address(consent.patient_did); requester = did_to_address(consent.requester_did); expiry = bc._expiry_ts(consent)
    exp_idx = 4 if c.has_v3() else 3  # v3 struct: (patient, requester, purposeHash, notBefore, expiry, ...)
    out = []
    for e in c.contract.events.Transfer().get_logs(from_block=max(0, w3.eth.block_number - lookback_blocks)):
        if e["args"]["from"] != ZERO: continue
        tid = int(e["args"]["tokenId"]); rec = c.contract.functions.consents(tid).call()
        if rec[0] == patient and rec[1] == requester and int(rec[exp_idx]) == expiry:
            out.append((tid, w3.to_hex(e["transactionHash"]), int(e["blockNumber"])))
    return out

def reconcile(consent, audit_db, consent_db):
    if _is_real(consent.token_id): return {"status": "already", "token_id": consent.token_id}
    found = find_onchain_tokens(consent)
    if not found: return {"status": "none"}
    tid, tx, blk = found[0]
    consent.token_id = f"SBT-{tid}"; consent_db.update(consent)
    audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT", patient_did=consent.patient_did,
                 consent_id=consent.consent_id, scope=consent.scope, purpose=consent.purpose, result="SUCCESS", tx_hash=tx, block_number=blk,
                 metadata={"token_id": tid, "reconciled_from_chain": True, "explorer_tx": f"https://sepolia.etherscan.io/tx/{tx}", "duplicates": len(found) - 1})
    return {"status": "reconciled", "token_id": tid, "tx_hash": tx, "block_number": blk, "duplicates": len(found) - 1}
