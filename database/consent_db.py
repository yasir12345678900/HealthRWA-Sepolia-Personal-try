"""Consent store: in-memory cache + SQLite write-through."""
from dataclasses import asdict
from models.consent import Consent
from database import db
CONSENTS = {}
def _load():
    for row in db.all_rows("consents"):
        try:
            CONSENTS[row["consent_id"]] = Consent(**row)
        except TypeError:
            known = {k: v for k, v in row.items() if k in Consent.__dataclass_fields__}
            CONSENTS[row["consent_id"]] = Consent(**known)
_load()
def save(consent):
    CONSENTS[consent.consent_id] = consent
    db.put("consents", "consent_id", consent.consent_id, asdict(consent))
def update(consent):
    save(consent)
def get(consent_id):
    return CONSENTS.get(consent_id)
def revoke(consent_id):
    c = get(consent_id)
    if c:
        c.revoked = True
        c.state = "REVOKED"
        update(c)
    return c
def get_patient_consent(patient):
    return [c for c in CONSENTS.values() if c.patient_did == patient]
