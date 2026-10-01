"""Read-only metrics collection for the CA2 report (no transactions are sent, the ledger is not modified).
Run in the Codespace with the app's .env present:   python3 tools/collect_metrics.py
Writes docs/final_check/metrics.json with:
  (a) on-chain facts of the five anchored transactions (gas used, effective gas price, fee, block time, confirmation latency),
  (b) the decision-matrix outcomes recorded in the 60-event audit ledger,
  (c) local timings: Groth16 proof generation/verification, decision-rule evaluation, EIP-712 signature recovery,
      on-chain read calls (checkValid / checkValidAt), each repeated N times."""
import json, os, sys, time, statistics, csv, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()
N = int(os.environ.get("N_RUNS", "20"))
OUT = "docs/final_check/metrics.json"
os.makedirs(os.path.dirname(OUT), exist_ok=True)
res = {"collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "n_runs": N}

from database import audit_db, consent_db
events = audit_db.get()
res["ledger"] = {"events": len(events), "by_action": {}}
for e in events:
    res["ledger"]["by_action"][e["action"]] = res["ledger"]["by_action"].get(e["action"], 0) + 1
# decision-matrix outcomes
dm = []
for e in events:
    m = e.get("metadata") or {}
    if isinstance(m, str):
        try: m = json.loads(m)
        except Exception: m = {}
    if e["action"] == "STATE_CHECK" and "ALLOW" in m:
        dm.append({"timestamp": e["timestamp"], "consent_id": e["consent_id"][:8], **{k: m[k] for k in ("VI","VA","VP","VT","VL","ALLOW")}})
    if e["action"] == "DATA_ACCESS":
        dm.append({"timestamp": e["timestamp"], "consent_id": e["consent_id"][:8], "DATA_ACCESS": e["result"], "proof_mode": m.get("proof_mode")})
res["decision_matrix_events"] = dm
# confirmation latency from ledger timestamps (local submit -> ONCHAIN_* row)
def ts(s): return datetime.datetime.fromisoformat(s)
lat = []
by_c = {}
for e in events: by_c.setdefault(e["consent_id"], []).append(e)
for cid, evs in by_c.items():
    acts = {a: [x for x in evs if x["action"] == a] for a in ("MINT_SBT", "ONCHAIN_MINT", "REVOKE_CONSENT", "ONCHAIN_REVOKE")}
    for a, b in (("MINT_SBT", "ONCHAIN_MINT"), ("REVOKE_CONSENT", "ONCHAIN_REVOKE")):
        if acts[a] and acts[b]:
            lat.append({"consent_id": cid[:8], "op": b, "submit_to_confirm_s": (ts(acts[b][0]["timestamp"]) - ts(acts[a][0]["timestamp"])).total_seconds()})
res["anchor_latency_from_ledger"] = lat

# (a) on-chain receipts
onchain = []
try:
    from web3 import Web3
    from blockchain.contract import ConsentContract
    c = ConsentContract()
    w3 = c.w3
    res["chain"] = {"rpc": c.rpc, "chain_id": w3.eth.chain_id, "head_block": w3.eth.block_number, "contract": c.address}
    for e in events:
        if e.get("tx_hash"):
            r = w3.eth.get_transaction_receipt(e["tx_hash"]); b = w3.eth.get_block(r.blockNumber)
            t = w3.eth.get_transaction(e["tx_hash"])
            onchain.append({"action": e["action"], "consent_id": e["consent_id"][:8], "tx_hash": e["tx_hash"], "block": r.blockNumber,
                            "status": r.status, "gas_used": r.gasUsed, "gas_limit": t.gas, "effective_gas_price_gwei": r.effectiveGasPrice / 1e9,
                            "fee_eth": r.gasUsed * r.effectiveGasPrice / 1e18, "block_time_utc": datetime.datetime.fromtimestamp(b.timestamp, datetime.timezone.utc).isoformat(),
                            "to": r.to})
    res["onchain_tx"] = onchain
    # on-chain read latency
    tid = next((int(x["token_id"]) for x in [ (json.loads(e["metadata"]) if isinstance(e.get("metadata"), str) else (e.get("metadata") or {})) for e in events if e["action"] == "ONCHAIN_MINT"] if isinstance(x.get("token_id"), int) and x["token_id"] <= 2), 2)
    tl = []; tla = []
    for _ in range(N):
        t0 = time.perf_counter(); c.check_valid(tid); tl.append(time.perf_counter() - t0)
        t0 = time.perf_counter(); c.check_valid_at(tid, "AU"); tla.append(time.perf_counter() - t0)
    res["timing"] = res.get("timing", {})
    res["timing"]["onchain_checkValid_s"] = tl; res["timing"]["onchain_checkValidAt_s"] = tla
except Exception as ex:
    res["chain_error"] = repr(ex)[:300]

# (c) local timings
res.setdefault("timing", {})
cons = consent_db.get("f050c29a-3d92-4131-8605-63bcb1ff8d92") or next(iter(consent_db._load().values()))
from services.access_service import evaluate_allow
from services.identity_service import verify_signature
from services import zk_service
tt = []
for _ in range(N * 50):
    t0 = time.perf_counter(); evaluate_allow(cons, "AU"); tt.append(time.perf_counter() - t0)
res["timing"]["decision_rule_s"] = tt
sd = getattr(cons, "signature_data", {}) or {}
if sd:
    g, s = next(iter(sd.items())); ts_ = []
    for _ in range(N):
        t0 = time.perf_counter(); verify_signature(g, cons.consent_id, s.get("signature")); ts_.append(time.perf_counter() - t0)
    res["timing"]["eip712_recover_s"] = ts_
res["zk_available"] = zk_service.zk_available()
if res["zk_available"]:
    pg, pv = [], []
    for _ in range(N):
        t0 = time.perf_counter(); p = zk_service.generate_proof(cons); pg.append(time.perf_counter() - t0)
        t0 = time.perf_counter(); ok = zk_service.verify_proof(p); pv.append(time.perf_counter() - t0)
    res["timing"]["groth16_prove_s"] = pg; res["timing"]["groth16_verify_s"] = pv; res["groth16_verify_ok"] = bool(ok)
    try:
        res["zk_artifacts"] = {k: os.path.getsize(os.path.join("zk/build", k)) for k in os.listdir("zk/build")}
    except Exception: pass

def summ(v): return {"n": len(v), "mean_ms": statistics.mean(v) * 1000, "median_ms": statistics.median(v) * 1000, "min_ms": min(v) * 1000, "max_ms": max(v) * 1000, "stdev_ms": (statistics.stdev(v) * 1000 if len(v) > 1 else 0)}
res["timing_summary"] = {k: summ(v) for k, v in res["timing"].items() if v}
json.dump(res, open(OUT, "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in res.items() if k not in ("timing", "decision_matrix_events")}, indent=1, default=str))
print("written", OUT)
