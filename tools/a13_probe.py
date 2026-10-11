"""A13 probe: does the decision accept a requester that holds no valid doctor credential?
Run on the code before and after the credential check:  python3 tools/a13_probe.py
Uses a temporary database; nothing is written to data/halah.db."""
import os, sys, tempfile
os.environ.setdefault("HALAH_DB_PATH", os.path.join(tempfile.mkdtemp(), "probe.db"))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from datetime import datetime, timedelta
from models.consent import Consent
from services.access_service import evaluate_allow
from services.identity_service import sign_consent, verify_signature, verify_vc


def consent(doctor):
    c = Consent("a13-probe", "did:patient:x", doctor, ["did:parent:A", "did:parent:B"], "Treatment", ["Observation"], 2,
                start_date=(datetime.now() - timedelta(days=1)).isoformat(), expiry_date=(datetime.now() + timedelta(days=30)).isoformat(),
                token_id="SBT-1")
    for g in c.guardian_dids:
        s, a = sign_consent(g, c.consent_id); c.signatures.append(g); c.signature_data[g] = {"signer": a, "signature": s}
    return c


for label, doctor in [("doctor DID with no credential", "did:hospital:999"),
                      ("two DIDs typed into one field", "did:hospital:001did:hospital:002"),
                      ("a guardian DID used as the doctor", "did:parent:A")]:
    m = evaluate_allow(consent(doctor), "AU", verify_sig=verify_signature, verify_did=verify_vc)
    print(f"{label:38s} requester={doctor:34s} VI={m['VI']} ALLOW={m['ALLOW']}")
print("verify_vc('did:anything') =", verify_vc("did:anything"))
