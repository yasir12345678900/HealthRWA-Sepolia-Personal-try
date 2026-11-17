"""Navigation-proof anchoring + chain reconciliation. anchor_async(): background mint that writes the
ledger itself. reconcile(): back-fills a consent that was minted on-chain but never recorded locally."""
import logging, os, threading
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
            return
        _revoke_if_withdrawn(consent)
    threading.Thread(target=run, daemon=True, name=f"anchor-{cid[:8]}").start()
    return job

def _revoke_if_withdrawn(consent):
    """A consent that was revoked while its mint was under way (Algorithm 6.4): the token that the mint issued is
    revoked on chain at once, the link to it is deleted from the record, and the outcome is recorded in the ledger
    as a REVOCATION_COMPLETION record. The time is the time of the chain."""
    if not getattr(consent, "revoked", False) or not bc.has_chain_token(consent): return
    try:
        from services import revocation_service
        t = bc.chain_time()
        revocation_service.complete_revocation(consent, onchain_revoke=bc.revoke_onchain, now=t["time"], time_label=t["source"])
    except Exception as e:
        log.warning("the revocation of %s could not be completed after its mint: %s", consent.consent_id, e)

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

def find_onchain_token_v4(consent, lookback_blocks=60000):
    """ConsentSBTv4: the token of a consent is found by the commitment of the record, the only consent data on chain.
    Returns (token id, per-consent address, tx hash, block number) or None. The transaction of the mint is read from
    the ConsentIssued event. When the node does not serve that query, the token is still returned, without it."""
    if not getattr(consent, "commitment", None): return None
    c = bc.token_client(read_only=True)
    tid = c.token_of_commitment(consent.commitment)
    if tid is None: return None
    tx = blk = None
    try:
        first = max(int(os.environ.get("CONTRACT_V4_DEPLOY_BLOCK") or 0), c.w3.eth.block_number - lookback_blocks, 0)
        for e in c.contract.events.ConsentIssued().get_logs(from_block=first, argument_filters={"tokenId": tid}):
            tx, blk = c.w3.to_hex(e["transactionHash"]), int(e["blockNumber"])
    except Exception as e:
        log.warning("could not read the ConsentIssued event of token %s: %s", tid, e)
    return tid, c.contract.functions.ownerOf(tid).call(), tx, blk

def _reconcile_v4(consent, audit_db, consent_db):
    found = find_onchain_token_v4(consent)
    if not found: return {"status": "none"}
    tid, address, tx, blk = found
    consent.token_id = f"SBT-{tid}"; consent.token_address = address; consent_db.update(consent)
    audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT", patient_did=consent.patient_did,
                 consent_id=consent.consent_id, scope=consent.scope, purpose=consent.purpose, result="SUCCESS", tx_hash=tx, block_number=blk,
                 metadata={"token_id": tid, "reconciled_from_chain": True, "explorer_tx": bc.explorer_tx(tx) if tx else None, "duplicates": 0})
    return {"status": "reconciled", "token_id": tid, "tx_hash": tx, "block_number": blk, "duplicates": 0}   # a commitment is issued once

def reconcile(consent, audit_db, consent_db):
    if _is_real(consent.token_id): return {"status": "already", "token_id": consent.token_id}
    if bc.v4_enabled(): return _reconcile_v4(consent, audit_db, consent_db)
    found = find_onchain_tokens(consent)
    if not found: return {"status": "none"}
    tid, tx, blk = found[0]
    consent.token_id = f"SBT-{tid}"; consent_db.update(consent)
    audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT", patient_did=consent.patient_did,
                 consent_id=consent.consent_id, scope=consent.scope, purpose=consent.purpose, result="SUCCESS", tx_hash=tx, block_number=blk,
                 metadata={"token_id": tid, "reconciled_from_chain": True, "explorer_tx": f"https://sepolia.etherscan.io/tx/{tx}", "duplicates": len(found) - 1})
    return {"status": "reconciled", "token_id": tid, "tx_hash": tx, "block_number": blk, "duplicates": len(found) - 1}
