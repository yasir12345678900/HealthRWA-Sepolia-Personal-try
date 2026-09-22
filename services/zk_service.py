"""Zero-Knowledge access proof for HALAH (v1.1).
REAL MODE (Groth16/BN254, zk/consent_validity.circom) when zk/build exists + node available:
  proves "I know (secret, expiry) with Poseidon(secret, expiry) == commitment AND now <= expiry" without revealing them.
PLACEHOLDER MODE otherwise: SHA-256 integrity digest, labelled mode="placeholder" (NOT zero-knowledge)."""
import hashlib, json, os, secrets, shutil, subprocess, time
from datetime import datetime
ZK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "zk")
_BUILD = os.path.join(ZK_DIR, "build")

def zk_available():
    return shutil.which("node") is not None and os.path.exists(os.path.join(_BUILD, "consent_validity.zkey")) \
        and os.path.exists(os.path.join(_BUILD, "verification_key.json"))

def _node(script, arg, timeout=120):
    r = subprocess.run(["node", os.path.join(ZK_DIR, script), arg], capture_output=True, text=True, timeout=timeout, cwd=ZK_DIR)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "node failed")
    return r.stdout.strip()

def _expiry_ts(consent):
    try:
        return int(datetime.fromisoformat(str(consent.expiry_date)).timestamp())
    except Exception:
        return int(time.time()) + 365 * 86400

def ensure_secret(consent):
    if not getattr(consent, "zk_secret", None):
        consent.zk_secret = str(secrets.randbits(248))
    return consent.zk_secret

def generate_proof(consent, now_ts=None):
    now_ts = int(now_ts or time.time())
    if zk_available():
        ensure_secret(consent)
        out = json.loads(_node("prove.js", json.dumps({"secret": consent.zk_secret, "expiry": str(_expiry_ts(consent)), "now": str(now_ts)})))
        consent.zk_commitment = out["commitment"]
        return {"mode": "groth16", "scheme": "Groth16/BN254 (circom+snarkjs)", "commitment": out["commitment"],
                "proof": out["proof"], "publicSignals": out["publicSignals"], "now": now_ts}
    return {"mode": "placeholder", "scheme": "SHA-256 integrity digest (NOT zero-knowledge)",
            "digest": hashlib.sha256(str(consent.consent_id).encode()).hexdigest()}

def verify_proof(proof):
    if not proof:
        return False
    if isinstance(proof, str):
        return len(proof) == 64
    if proof.get("mode") == "groth16":
        return zk_available() and _node("verify.js", json.dumps({"proof": proof["proof"], "publicSignals": proof["publicSignals"]})) == "true"
    return bool(proof.get("digest"))
