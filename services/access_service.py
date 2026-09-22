'''
Secure Data Access for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-10
'''

def check_scope(consent, request):
    requested = set(request.scope)
    allowed = set(consent.scope)
    return requested.issubset(allowed)


def authorize(
    state,
    proof,
    scope_valid
):
    if state != "ACTIVE":
        return False

    if not proof:
        return False

    if not scope_valid:
        return False

    return True


ALLOWED_PURPOSES = {"Treatment", "Research", "Emergency"}


def evaluate_allow(consent, requester_jurisdiction="AU", now=None, verify_sig=None, verify_did=None):
    """Full decision matrix for C=(I,A,P,T,L,E). Returns dict VI,VA,VP,VT,VL,ALLOW (bools)."""
    from datetime import datetime
    now = now or datetime.now()
    vdid = verify_did or (lambda d: isinstance(d, str) and d.startswith("did:"))
    sigs = getattr(consent, "signature_data", {}) or {}
    vi = vdid(consent.requester_did) and vdid(consent.patient_did) and len(consent.signatures) > 0
    if verify_sig is not None:
        vi = vi and all(g in sigs and verify_sig(g, consent.consent_id, sigs[g].get("signature")) for g in consent.signatures)
    va = (len(consent.signatures) >= consent.threshold) and bool(consent.token_id) and not getattr(consent, "revoked", False)
    vp = consent.purpose in ALLOWED_PURPOSES
    try:
        vt = datetime.fromisoformat(consent.start_date) <= now <= datetime.fromisoformat(consent.expiry_date)
    except Exception:
        vt = False
    cj = getattr(consent, "jurisdiction", "") or ""
    vl = (cj == "") or (cj == requester_jurisdiction)
    return {"VI": bool(vi), "VA": bool(va), "VP": bool(vp), "VT": bool(vt), "VL": bool(vl),
            "ALLOW": bool(vi and va and vp and vt and vl)}
