'''
# Consent State Machine for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-22, 2026-08-01
'''
from datetime import datetime

def evaluate_state(consent):
    now = datetime.now()
    start = datetime.fromisoformat(consent.start_date)
    expiry = datetime.fromisoformat(consent.expiry_date)

    # if consent.revoked:
    #     consent.state = "REVOKED"
    #     return consent.state

    if len(consent.signatures) < consent.threshold:
        consent.state = "PENDING_SIGNATURE"
        return consent.state

    if consent.token_id is None:
        consent.state = "PENDING_TOKEN"
        return consent.state

    if now < start:
        consent.state = "NOT_STARTED"
        return consent.state

    if now > expiry:
        consent.state = "EXPIRED"
        return consent.state

    consent.state = "ACTIVE"
    return consent.state