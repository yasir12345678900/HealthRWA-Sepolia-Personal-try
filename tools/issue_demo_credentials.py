"""Issue the demo role credentials used by the prototype (verifiable credentials, original report RO2 Steps 3-6).
Run:  python3 tools/issue_demo_credentials.py
Writes data/credentials/demo_credentials.json. The demo issuer key is derived from a fixed tag (see
services/identity_service.py, DEMO ISSUER MODEL), so the output is the same every time."""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.identity_service import issue_credential, ISSUER_DID, TRUSTED_ISSUERS, CREDENTIALS_PATH

GUARDIANS = ["did:parent:A", "did:parent:B", "did:parent:C", "did:parent:D"]
DOCTORS = [("did:hospital:001", "Hospital 001"), ("did:hospital:002", "Hospital 002"), ("did:hospital:003", "Hospital 003")]

creds = [issue_credential(g, "guardian") for g in GUARDIANS] + [issue_credential(d, "doctor", org) for d, org in DOCTORS]
out = {"issuer": ISSUER_DID, "issuer_address": TRUSTED_ISSUERS[ISSUER_DID],
       "note": "Demo credentials for the HALAH prototype. Signed with the demo issuer key; not for real use.",
       "credentials": creds}
os.makedirs(os.path.dirname(CREDENTIALS_PATH), exist_ok=True)
with open(CREDENTIALS_PATH, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=1)
    f.write("\n")
print(f"{len(creds)} credentials written to {CREDENTIALS_PATH}")
