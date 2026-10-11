"""Local timings after the credential check was added (no chain access, nothing is written to the ledger).
Run:  python3 tools/measure_local_timing.py
Writes docs/final_check/metrics_local_2026-10-11.json. The decision rule is timed exactly as in tools/collect_metrics.py
(evaluate_allow(consent, "AU") on consent f050c29a, predicates only, 1,000 runs), so the two files can be compared.
It also times the credential check (one credential), EIP-712 signature recovery (one signature), and the decision
rule with the credential and signature checks switched on."""
import json, os, sys, time, statistics, datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database import consent_db
from services.access_service import evaluate_allow
from services.identity_service import verify_signature, verify_vc
N = int(os.environ.get("N_RUNS", "20"))
OUT = "docs/final_check/metrics_local_2026-10-11.json"
cons = consent_db.get("f050c29a-3d92-4131-8605-63bcb1ff8d92") or next(iter(consent_db._load().values()))

def timed(fn, n):
    v = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); v.append(time.perf_counter() - t0)
    return v

timing = {
    "decision_rule_s": timed(lambda: evaluate_allow(cons, "AU"), N * 50),
    "vc_verify_one_credential_s": timed(lambda: verify_vc(cons.requester_did, role="doctor"), N),
    "decision_rule_with_credential_and_signature_checks_s": timed(
        lambda: evaluate_allow(cons, "AU", verify_sig=verify_signature, verify_did=verify_vc), N),
}
sd = getattr(cons, "signature_data", {}) or {}
if sd:
    g, s = next(iter(sd.items()))
    timing["eip712_recover_s"] = timed(lambda: verify_signature(g, cons.consent_id, s.get("signature")), N)

def summ(v):
    return {"n": len(v), "mean_ms": statistics.mean(v) * 1000, "median_ms": statistics.median(v) * 1000,
            "min_ms": min(v) * 1000, "max_ms": max(v) * 1000, "stdev_ms": statistics.stdev(v) * 1000 if len(v) > 1 else 0}

res = {"collected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(), "n_runs": N,
       "consent_id": cons.consent_id[:8], "timing_summary": {k: summ(v) for k, v in timing.items()}, "timing": timing}
os.makedirs(os.path.dirname(OUT), exist_ok=True)
json.dump(res, open(OUT, "w"), indent=1)
print(json.dumps(res["timing_summary"], indent=1))
print("written", OUT)
