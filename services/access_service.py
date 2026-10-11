'''
Secure Data Access for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-10, 2026-10-11
'''
from datetime import datetime
from services.identity_service import is_valid_did, verify_vc

def guardian_approvals(consent):
    """Distinct approvals from members of the guardian set G (a signer outside G, or the same
    guardian twice, does not advance the count towards the threshold N)."""
    return {g for g in (consent.signatures or []) if g in (consent.guardian_dids or [])}


def check_scope(consent, request):
    requested = set(request.scope)
    allowed = set(consent.scope)
    # A request must name at least one module and every module must lie inside the authorised scope.
    return len(requested) > 0 and requested.issubset(allowed)


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


def evaluate_allow(consent, requester_jurisdiction="AU", now=None, verify_sig=None, verify_did=None, requester_did=None):
    """Full decision matrix for C=(I,A,P,T,L,E). Returns dict VI,VA,VP,VT,VL,ALLOW (bools).
    requester_did: the DID entered by the participant making the request (None = the consent's authorised doctor,
    for offline tools). The DID is entered, not authenticated: VI shows that this DID holds a valid doctor credential
    and is the doctor named in the consent; proof that the user controls the DID is next-stage work.
    verify_did(did, role=None, now=None): identity and credential check; defaults to identity_service.verify_vc.
    Timing tools that measure the predicates only pass a DID-syntax checker explicitly."""
    from services.state_service import lifecycle_state       # imported here: state_service imports this module
    now = now or datetime.now()
    requester = consent.requester_did if requester_did is None else requester_did

    check = verify_did or verify_vc

    def vdid(did, role=None):
        try:
            return bool(check(did, role=role, now=now))
        except TypeError:                      # a checker without a `now` argument still gets the role
            return bool(check(did, role=role))

    sigs = getattr(consent, "signature_data", {}) or {}
    # VI: the requester's DID and credential (role doctor), bound to the consent's authorised doctor,
    # a well-formed patient DID, and every recorded guardian approval verifies.
    vi = (vdid(requester, role="doctor") and requester == consent.requester_did
          and is_valid_did(consent.patient_did) and len(consent.signatures) > 0)
    if verify_sig is not None:
        vi = vi and all(g in sigs and verify_sig(g, consent.consent_id, sigs[g].get("signature")) for g in consent.signatures)
    # VA: only distinct approvals from members of the guardian set G count towards the threshold N.
    approvers = guardian_approvals(consent)
    va = (len(approvers) >= consent.threshold) and bool(consent.token_id) and not getattr(consent, "revoked", False)
    # VP: purpose and policy context (the requester's jurisdiction must match the consent's).
    cj = getattr(consent, "jurisdiction", "") or ""
    vp = consent.purpose in ALLOWED_PURPOSES and ((cj == "") or (cj == requester_jurisdiction))
    try:
        vt = datetime.fromisoformat(consent.start_date) <= now <= datetime.fromisoformat(consent.expiry_date)
    except Exception:
        vt = False
    # VL: consent lifecycle validity - the lifecycle state must be ACTIVE (ValidState).
    # The transition check (ValidTransition) and the SUSPENDED state are next-stage work. In this prototype every
    # non-ACTIVE state also fails VA or VT, so VL never refuses a request on its own.
    try:
        vl = lifecycle_state(consent, now) == "ACTIVE"
    except Exception:
        vl = False
    return {"VI": bool(vi), "VA": bool(va), "VP": bool(vp), "VT": bool(vt), "VL": bool(vl),
            "ALLOW": bool(vi and va and vp and vt and vl)}
