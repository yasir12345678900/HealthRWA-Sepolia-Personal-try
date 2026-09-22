"""HALAH local audit ledger. event_digest = SHA-256 tamper-evidence. tx_hash/block_number
are filled ONLY for real Sepolia transactions (ONCHAIN_MINT); otherwise None, onchain=False."""
from datetime import datetime
import hashlib, json, uuid
from database import db
AUDIT = []
try:
    AUDIT.extend(db.all_rows("audit", "ts"))
except Exception:
    pass
def event_digest(e):
    core={k:e.get(k) for k in ("actor_did","action","patient_did","consent_id","result","timestamp")}
    return "0x"+hashlib.sha256(json.dumps(core,sort_keys=True,default=str).encode()).hexdigest()
def log(actor_did, actor_role, action, patient_did, consent_id, scope=None, purpose=None,
        result="SUCCESS", metadata=None, tx_hash=None, block_number=None):
    e={"event_id":str(uuid.uuid4()),"timestamp":datetime.now().isoformat(),"actor_did":actor_did,
       "actor_role":actor_role,"action":action,"patient_did":patient_did,"consent_id":consent_id,
       "scope":scope,"purpose":purpose,"result":result,"metadata":metadata}
    e["event_digest"]=event_digest(e); e["onchain"]=bool(tx_hash)
    e["tx_hash"]=tx_hash; e["block_number"]=block_number
    AUDIT.append(e)
    db.put("audit", "event_id", e["event_id"], e)
    return e
def get(): return AUDIT
