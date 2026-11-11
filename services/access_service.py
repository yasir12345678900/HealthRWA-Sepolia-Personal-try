'''
Secure Data Access for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-10, 2026-10-11, 2026-11-11
'''
from datetime import datetime
from services.identity_service import is_valid_did, verify_vc

# ---------------------------------------------------------------------------
# Deny codes (thesis Section 6.3.1). This is the one place where they are defined.
# Each code is tied to the check that fails. The first three report the three conditions of the policy
# predicate VP, the next two report the window check of VT, and the last four report the state of VL.
# ---------------------------------------------------------------------------
DENY_OUT_OF_SCOPE = "OUT-OF-SCOPE"                # VS: the requested scope is empty or not inside the consented scope
DENY_PURPOSE_MISMATCH = "PURPOSE-MISMATCH"        # VU: the declared purpose is not the purpose of the consent
DENY_CONTEXT_MISMATCH = "CONTEXT-MISMATCH"        # VX: the request context is not the context of the consent
DENY_PRE_VALIDITY = "PRE-VALIDITY"                # VT: the request arrives before the start of the window
DENY_POST_VALIDITY = "POST-VALIDITY"              # VT: the request arrives after the end of the window
DENY_AWAITING_TRIGGER = "AWAITING-TRIGGER"        # VL: SUSPENDED, a conditional trigger is not satisfied yet
DENY_TRANSITION_PENDING = "TRANSITION-PENDING"    # VL: SUSPENDED, a capacity transition is due and not executed
DENY_EXPIRED = "EXPIRED"                          # VL: the state is EXPIRED
DENY_REVOKED = "REVOKED"                          # VL: the state is REVOKED
DENY_CODES = (DENY_OUT_OF_SCOPE, DENY_PURPOSE_MISMATCH, DENY_CONTEXT_MISMATCH, DENY_PRE_VALIDITY, DENY_POST_VALIDITY,
              DENY_AWAITING_TRIGGER, DENY_TRANSITION_PENDING, DENY_EXPIRED, DENY_REVOKED)

# Codes outside the nine of Section 6.3.1. That section names the codes of the Enforcement Module only (VP, VT and VL)
# for a consent that has been issued. A request can also fail on VI or VA, which belong to the Issuance Module, on a
# consent that is not issued yet, or on a record that cannot be read. These codes make sure that a denied request
# never has an empty list of codes.
DENY_IDENTITY_INVALID = "IDENTITY-INVALID"        # VI: requester, credential, named clinician or an approval signature
DENY_APPROVAL_PENDING = "APPROVAL-PENDING"        # VA: fewer than N distinct approvals from members of G
DENY_TOKEN_PENDING = "TOKEN-PENDING"              # VL: PENDING_TOKEN, the threshold is met and no token is recorded yet
DENY_RECORD_INVALID = "RECORD-INVALID"            # the window cannot be read or the state cannot be derived (fail closed)
DENY_TRANSITION_NOT_PERMITTED = "TRANSITION-NOT-PERMITTED"   # Algorithm 6.2, lines 16 to 20 (a requested transition)
DENY_CODES_OTHER = (DENY_IDENTITY_INVALID, DENY_APPROVAL_PENDING, DENY_TOKEN_PENDING, DENY_RECORD_INVALID,
                    DENY_TRANSITION_NOT_PERMITTED)

# The check that each code reports: (predicate of the decision rule, condition inside it).
DENY_CODE_CHECK = {
    DENY_OUT_OF_SCOPE: ("VP", "VS"), DENY_PURPOSE_MISMATCH: ("VP", "VU"), DENY_CONTEXT_MISMATCH: ("VP", "VX"),
    DENY_PRE_VALIDITY: ("VT", "t < ts"), DENY_POST_VALIDITY: ("VT", "t > te"),
    DENY_AWAITING_TRIGGER: ("VL", "SUSPENDED"), DENY_TRANSITION_PENDING: ("VL", "SUSPENDED"),
    DENY_EXPIRED: ("VL", "EXPIRED"), DENY_REVOKED: ("VL", "REVOKED"),
    DENY_IDENTITY_INVALID: ("VI", "identity and authority"), DENY_APPROVAL_PENDING: ("VA", "threshold N"),
    DENY_TOKEN_PENDING: ("VL", "PENDING_TOKEN"),
    DENY_RECORD_INVALID: ("VL", "state not derivable"), DENY_TRANSITION_NOT_PERMITTED: ("VL", "transition policy"),
}

MATRIX_KEYS = ("VI", "VA", "VP", "VT", "VL", "ALLOW")           # the matrix of the report, returned to existing callers
MATRIX_KEYS_FULL = MATRIX_KEYS + ("VU", "VS", "VX", "DENY")    # with the three conditions of VP and the deny codes


def guardian_approvals(consent):
    """Distinct approvals from members of the guardian set G (a signer outside G, or the same
    guardian twice, does not advance the count towards the threshold N)."""
    return {g for g in (consent.signatures or []) if g in (consent.guardian_dids or [])}


def threshold_valid(consent):
    """The patient-defined threshold N of a k-of-n consent lies in 1 <= N <= |G| (thesis Section 3.2.4),
    with |G| the number of distinct guardians. A threshold of zero would be met by no approval at all."""
    k = getattr(consent, "threshold", None)
    n = len(set(getattr(consent, "guardian_dids", None) or []))
    return isinstance(k, int) and not isinstance(k, bool) and 1 <= k <= n


def threshold_met(consent):
    """Algorithm 5.2: the number of distinct approvals from members of G has reached a valid threshold N."""
    return threshold_valid(consent) and len(guardian_approvals(consent)) >= consent.threshold


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


def _scope_within(consent, request_scope):
    """VS for a scope given to the decision function: non-empty and inside the consented scope (Equation 9.1).
    A scope that is not a list, tuple or set of module names fails the check."""
    if not isinstance(request_scope, (list, tuple, set, frozenset)):
        return False
    try:
        requested = set(request_scope)
        allowed = set(consent.scope or [])
    except TypeError:
        return False
    return len(requested) > 0 and requested.issubset(allowed)


def _decide(consent, context, now, verify_sig, verify_did, requester_did, request_purpose, request_scope, full,
            va_approvals_only=False):
    """The decision rule ALLOW = VI and VA and VP and VT and VL for one request (Algorithm 6.1, the decision part).
    full=False returns the six keys of the report, full=True adds VU, VS, VX and the deny codes."""
    from services.state_service import lifecycle_state, suspension_codes   # imported here: state_service imports this module
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
    # VA: only distinct approvals from members of the guardian set G count towards the patient-defined threshold N
    # (k-of-n, 1 <= N <= |G|). The report also evaluates the token and the revocation flag inside VA, and that stays
    # the default. With va_approvals_only, VA is the predicate of thesis Section 3.2.8, defined over the approvals
    # alone, and the token and revocation conditions are reported by VL only.
    met = threshold_met(consent)
    va = met if va_approvals_only else (met and bool(consent.token_id) and not getattr(consent, "revoked", False))
    # VP = VU and VS and VX: purpose, data scope and context (thesis Section 6.2.2).
    # VU: the consent purpose is in the supported vocabulary and, when the request declares a purpose, it is the same one.
    vu = consent.purpose in ALLOWED_PURPOSES and (request_purpose is None or request_purpose == consent.purpose)
    # VS: when the request names a scope, it is non-empty and inside the consented scope.
    vs = True if request_scope is None else _scope_within(consent, request_scope)
    # VX: the request context (the jurisdiction) must match the consent's.
    cj = getattr(consent, "jurisdiction", "") or ""
    vx = (cj == "") or (cj == context)
    vp = vu and vs and vx
    # VT: the validity window ts <= t <= te.
    window_code = None
    try:
        start, expiry = datetime.fromisoformat(consent.start_date), datetime.fromisoformat(consent.expiry_date)
        vt = start <= now <= expiry
        if not vt:
            window_code = DENY_PRE_VALIDITY if now < start else DENY_POST_VALIDITY
    except Exception:
        vt = False
        window_code = DENY_RECORD_INVALID
    # VL: consent lifecycle validity - the lifecycle state must be ACTIVE (ValidState). SUSPENDED and the rule that
    # no REVOKED or EXPIRED consent re-enters ACTIVE (ValidTransition) are part of the state derivation, so VL can
    # refuse a request on its own.
    try:
        state = lifecycle_state(consent, now)
    except Exception:
        state = None
    vl = state == "ACTIVE"
    allow = bool(vi and va and vp and vt and vl)
    m = {"VI": bool(vi), "VA": bool(va), "VP": bool(vp), "VT": bool(vt), "VL": bool(vl), "ALLOW": allow}
    if not full:
        return m

    # Deny codes, in the order in which Algorithm 6.1 makes its checks: the requester, the consent state
    # (Algorithm 6.2), the multi-party authorisation, the purpose with the context beside it, and the scope.
    deny = []
    if not vi:
        deny.append(DENY_IDENTITY_INVALID)
    if state == "REVOKED":
        state_codes = [DENY_REVOKED]
    elif state == "EXPIRED":
        state_codes = [DENY_EXPIRED]
    elif state == "SUSPENDED":
        state_codes = suspension_codes(consent, now)
    elif state is None:
        state_codes = [DENY_RECORD_INVALID]
    else:
        state_codes = []
    # Precedence rule of Section 6.3.1: when both VT and VL fail, the state code is reported and not the window code.
    if state_codes:
        deny.extend(state_codes)
    elif not vt:
        deny.append(window_code)
    # A consent that is not issued yet: the threshold is not met (VA), or it is met and the token is not recorded.
    if not met:
        deny.append(DENY_APPROVAL_PENDING)
    elif state == "PENDING_TOKEN":
        deny.append(DENY_TOKEN_PENDING)
    if not vu:
        deny.append(DENY_PURPOSE_MISMATCH)
    if not vx:
        deny.append(DENY_CONTEXT_MISMATCH)
    if not vs:
        deny.append(DENY_OUT_OF_SCOPE)
    if not allow and not deny:                 # a state without a code of its own still gives a reason
        deny.append(DENY_RECORD_INVALID)
    m.update({"VU": bool(vu), "VS": bool(vs), "VX": bool(vx), "DENY": deny})
    return m


def evaluate_allow(consent, requester_jurisdiction="AU", now=None, verify_sig=None, verify_did=None, requester_did=None,
                   request_purpose=None, request_scope=None, va_approvals_only=False):
    """Full decision matrix for C=(I,A,P,T,L,E). Returns dict VI,VA,VP,VT,VL,ALLOW (bools).
    requester_did: the DID entered by the participant making the request (None = the consent's authorised doctor,
    for offline tools). The DID is entered, not authenticated: VI shows that this DID holds a valid doctor credential
    and is the doctor named in the consent; proof that the user controls the DID is next-stage work.
    verify_did(did, role=None, now=None): identity and credential check; defaults to identity_service.verify_vc.
    Timing tools that measure the predicates only pass a DID-syntax checker explicitly.
    request_purpose: the purpose the request declares. When given, it must equal the consent purpose (VU).
    request_scope: the record modules the request names. When given, it must be non-empty and inside the consent
    scope (VS). requester_jurisdiction is the request context (VX), and VP = VU and VS and VX.
    With request_purpose and request_scope both left as None the result has the six keys above and nothing else, as
    before. When either is given the result also has VU, VS, VX and DENY, the list of deny codes (empty on ALLOW).
    va_approvals_only: False keeps VA as the report evaluates it (threshold met, token recorded, not revoked). True
    gives VA of thesis Section 3.2.8, the distinct approvals of members of G against N and nothing else. ALLOW is the
    same in both forms, because VL holds only in ACTIVE, which needs the token and no revocation."""
    full = request_purpose is not None or request_scope is not None
    return _decide(consent, requester_jurisdiction, now, verify_sig, verify_did, requester_did,
                   request_purpose, request_scope, full, va_approvals_only)


def decision_matrix(consent, context="AU", now=None, verify_sig=None, verify_did=None, requester_did=None,
                    request_purpose=None, request_scope=None, va_approvals_only=False):
    """Algorithm 6.1, the decision: the same rule as evaluate_allow, always with the keys VI, VA, VP, VT, VL, ALLOW,
    VU, VS, VX and DENY. A purpose or a scope that the request does not give is not compared."""
    return _decide(consent, context, now, verify_sig, verify_did, requester_did, request_purpose, request_scope, True,
                   va_approvals_only)


def evaluate_request(consent, request, context="AU", now=None, verify_sig=None, verify_did=None, va_approvals_only=False):
    """Algorithm 6.1 for an access request R (models.access.AccessRequest): the requester, the declared purpose and
    the requested scope are read from R and are always compared, so a request without a purpose or without a scope
    is denied. A request that names another patient than the consent fails VI. The time t is the `now` of the
    caller (services.time_source), never the request_time field, which the requester writes."""
    m = decision_matrix(consent, context, now=now, verify_sig=verify_sig, verify_did=verify_did,
                        requester_did=request.doctor_did if request.doctor_did is not None else "",
                        request_purpose=request.purpose if request.purpose is not None else "",
                        request_scope=request.scope if request.scope is not None else [],
                        va_approvals_only=va_approvals_only)
    if request.patient_did != consent.patient_did:
        m["VI"] = m["ALLOW"] = False
        if DENY_IDENTITY_INVALID not in m["DENY"]:
            m["DENY"].insert(0, DENY_IDENTITY_INVALID)
    return m


def deny_code(decision):
    """The one deny code to report for a decision: the first of the nine codes of Section 6.3.1 in the list, else the
    first other code, else None (ALLOW). `decision` is a matrix with a DENY list, or the list itself."""
    codes = decision.get("DENY", []) if isinstance(decision, dict) else list(decision or [])
    for c in codes:
        if c in DENY_CODES:
            return c
    return codes[0] if codes else None
