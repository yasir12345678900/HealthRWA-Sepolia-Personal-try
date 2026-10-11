'''
# Consent State Machine for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-22, 2026-08-01, 2026-10-11
'''
from datetime import datetime
from services.access_service import guardian_approvals


def lifecycle_state(consent, now=None):
    """The consent's lifecycle state at `now`, without changing the consent (used by VL)."""
    if getattr(consent, "revoked", False):
        return "REVOKED"

    now = now or datetime.now()
    start = datetime.fromisoformat(consent.start_date)
    expiry = datetime.fromisoformat(consent.expiry_date)

    # count distinct approvals from members of G only, as in the decision function
    if len(guardian_approvals(consent)) < consent.threshold:
        return "PENDING_SIGNATURE"

    if consent.token_id is None:
        return "PENDING_TOKEN"

    if now < start:
        return "NOT_STARTED"

    if now > expiry:
        return "EXPIRED"

    return "ACTIVE"


def evaluate_state(consent):
    consent.state = lifecycle_state(consent)
    return consent.state
