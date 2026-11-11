'''
Consent-Bound Data Release for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# Algorithm 6.5, consent-bound data release (thesis Section 6.3.6).
#
# release() is the only path from a request to record data. It releases data on two conditions together: the
# decision rule of Algorithm 6.1 returns ALLOW for the request, and the proof of Chapter 7 presented with the
# request verifies. Then it decrypts, inside the Controller, the modules of the requested scope and no other
# module, and delivers them for this request. The keys stay in the key store, and the requester receives decrypted
# modules and never a key.
#
# Every call writes a DATA_ACCESS record to the audit ledger E, off chain: with the outcome GRANTED, the scope,
# the requester, the time and a reference to the proof, or, on any failure, with the outcome DENIED and the deny
# code. Neither record goes on chain, because the scope and the requester would identify the consent. The
# STATE_CHECK record of the evaluation is written before it, as the interface has done since 11 October 2026.
#
# The decision is taken by services.access_service.evaluate_allow. The proof is verified by a callable that the
# caller gives (the verifier of Chapter 7). Without a verifier nothing is released.
#
# A module outside the consent scope cannot be released even if a decision were wrong, because the vault holds no
# sealed copy of it and the key store holds no key for it. A revoked consent cannot release anything even if its
# record were changed back, because its keys are destroyed. This is the data side of the invariant that no
# REVOKED or EXPIRED consent re-enters ACTIVE.
import hashlib
import inspect
import json
from datetime import datetime

from database import audit_db
from models.access import AccessRequest
from services import access_service, data_vault, key_store
from services.identity_service import verify_signature
from services.state_service import lifecycle_state

GRANTED, DENIED = "GRANTED", "DENIED"


def _code(name, text):
    # The deny codes are defined in one place, services/access_service.py. The text is used only with an access
    # service that does not define the codes yet.
    return getattr(access_service, name, text)


# The nine deny codes of Section 6.3.1, each tied to the check that fails.
DENY_OUT_OF_SCOPE = _code("DENY_OUT_OF_SCOPE", "OUT-OF-SCOPE")
DENY_PURPOSE_MISMATCH = _code("DENY_PURPOSE_MISMATCH", "PURPOSE-MISMATCH")
DENY_CONTEXT_MISMATCH = _code("DENY_CONTEXT_MISMATCH", "CONTEXT-MISMATCH")
DENY_PRE_VALIDITY = _code("DENY_PRE_VALIDITY", "PRE-VALIDITY")
DENY_POST_VALIDITY = _code("DENY_POST_VALIDITY", "POST-VALIDITY")
DENY_AWAITING_TRIGGER = _code("DENY_AWAITING_TRIGGER", "AWAITING-TRIGGER")
DENY_TRANSITION_PENDING = _code("DENY_TRANSITION_PENDING", "TRANSITION-PENDING")
DENY_EXPIRED = _code("DENY_EXPIRED", "EXPIRED")
DENY_REVOKED = _code("DENY_REVOKED", "REVOKED")
SECTION_CODES = (DENY_OUT_OF_SCOPE, DENY_PURPOSE_MISMATCH, DENY_CONTEXT_MISMATCH, DENY_PRE_VALIDITY, DENY_POST_VALIDITY,
                 DENY_AWAITING_TRIGGER, DENY_TRANSITION_PENDING, DENY_EXPIRED, DENY_REVOKED)
# Codes for a request that fails on VI or VA, or on a record that cannot be read.
DENY_IDENTITY_INVALID = _code("DENY_IDENTITY_INVALID", "IDENTITY-INVALID")
DENY_APPROVAL_PENDING = _code("DENY_APPROVAL_PENDING", "APPROVAL-PENDING")
DENY_TOKEN_PENDING = _code("DENY_TOKEN_PENDING", "TOKEN-PENDING")
DENY_RECORD_INVALID = _code("DENY_RECORD_INVALID", "RECORD-INVALID")
# The two codes of the release step itself (Algorithm 6.5). They are not among the nine of Section 6.3.1, because
# they report no predicate of the decision rule: the rule returned ALLOW and the release still failed.
DENY_PROOF_INVALID = "PROOF-INVALID"            # no proof, no verifier, or the proof did not verify
DENY_COPY_UNAVAILABLE = "COPY-UNAVAILABLE"      # the vault has no sealed copy of a requested module that opens

SOURCE_SYSTEM_CLOCK = "system-clock-fallback"   # the label services/time_source.py gives the same source
SOURCE_CALLER = "caller-supplied"


def _decision_time(now, time_label):
    """The time t of the request and the label of its source. The caller passes the time it read from a source
    the server does not control, with the label of that source. Without it the system clock is used and labelled."""
    if now is None:
        return datetime.now(), SOURCE_SYSTEM_CLOCK
    if now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)       # the consent window is stored as local time without a zone
    return now, time_label or SOURCE_CALLER


def _scope_list(request_scope):
    """The requested modules as a list without repeats. A scope that is missing or is not a list of module names
    becomes the empty list, which the decision rule refuses."""
    if not isinstance(request_scope, (list, tuple, set, frozenset)) or not all(isinstance(m, str) for m in request_scope):
        return []
    return list(dict.fromkeys(request_scope))


def _window_code(consent, now):
    try:
        start, expiry = datetime.fromisoformat(consent.start_date), datetime.fromisoformat(consent.expiry_date)
    except Exception:
        return DENY_RECORD_INVALID
    return DENY_PRE_VALIDITY if now < start else DENY_POST_VALIDITY if now > expiry else None


def _state(consent, now):
    try:
        return lifecycle_state(consent, now)
    except Exception:
        return None


def _codes_for(consent, m, now):
    """Deny codes for a matrix that comes without them, in the order of Algorithm 6.1 and with the precedence rule
    of Section 6.3.1: when both VT and VL fail, the state code is reported and not the window code."""
    state = _state(consent, now)
    codes = []
    if not m["VI"]:
        codes.append(DENY_IDENTITY_INVALID)
    if state in ("REVOKED", "EXPIRED"):
        codes.append(DENY_REVOKED if state == "REVOKED" else DENY_EXPIRED)
    elif state is None:
        codes.append(DENY_RECORD_INVALID)
    elif not m["VT"]:
        codes.append(_window_code(consent, now) or DENY_RECORD_INVALID)
    if state == "PENDING_SIGNATURE":
        codes.append(DENY_APPROVAL_PENDING)
    elif state == "PENDING_TOKEN":
        codes.append(DENY_TOKEN_PENDING)
    if not m["VU"]:
        codes.append(DENY_PURPOSE_MISMATCH)
    if not m["VX"]:
        codes.append(DENY_CONTEXT_MISMATCH)
    if not m["VS"]:
        codes.append(DENY_OUT_OF_SCOPE)
    if not m["ALLOW"] and not codes:
        codes.append(DENY_RECORD_INVALID)
    return codes


def decide_request(consent, requester_did, request_scope, request_purpose, context="AU", now=None,
                   verify_sig=verify_signature, verify_did=None):
    """Algorithm 6.1 for one request, through services.access_service.evaluate_allow. Returns the matrix with VI,
    VA, VP, VT, VL, ALLOW, the three conditions of VP (VU purpose, VS scope, VX context) and DENY, the list of
    deny codes. The declared purpose and the requested scope are always compared.
    An evaluate_allow that takes the request purpose and scope does all of it. With the earlier evaluate_allow,
    which does not take them, the two conditions of the request and the deny codes are added here."""
    now = now or datetime.now()
    # A request that declares no purpose or names no scope is compared as well, and it is refused: the empty
    # purpose equals no consent purpose and the empty scope fails the scope condition.
    request_purpose = request_purpose if isinstance(request_purpose, str) else ""
    request_scope = _scope_list(request_scope)
    takes = inspect.signature(access_service.evaluate_allow).parameters
    if "request_purpose" in takes and "request_scope" in takes:
        return dict(access_service.evaluate_allow(consent, context, now=now, verify_sig=verify_sig, verify_did=verify_did,
                                                  requester_did=requester_did, request_purpose=request_purpose,
                                                  request_scope=request_scope))
    m = dict(access_service.evaluate_allow(consent, context, now=now, verify_sig=verify_sig, verify_did=verify_did,
                                           requester_did=requester_did))
    consent_context = getattr(consent, "jurisdiction", "") or ""
    vu = consent.purpose in access_service.ALLOWED_PURPOSES and request_purpose == consent.purpose
    vs = access_service.check_scope(consent, AccessRequest(requester_did, consent.patient_did, request_scope,
                                                           request_purpose, now.isoformat()))
    vx = consent_context == "" or consent_context == context
    m.update(VU=bool(vu), VS=bool(vs), VX=bool(vx), VP=bool(vu and vs and vx), ALLOW=bool(m["ALLOW"] and vu and vs))
    m["DENY"] = _codes_for(consent, m, now)
    return m


def primary_deny_code(codes):
    """The one deny code to report: the first of the nine codes of Section 6.3.1 in the list, else the first other
    code, else None."""
    pick = getattr(access_service, "deny_code", None)
    if pick is not None:
        return pick(list(codes))
    for code in codes:
        if code in SECTION_CODES:
            return code
    return codes[0] if codes else None


def proof_reference(proof, proof_ref=None):
    """The reference to the proof that is written to E: the SHA-256 digest of the proof as it was presented, its
    mode, and the request tag and the verifying transaction when the proof carries them. `proof_ref` is a
    reference of the caller's own, for example the transaction of the on-chain verification, and is kept as given."""
    if proof is None and proof_ref is None:
        return None
    reference = {}
    if proof is not None:
        canonical = json.dumps(proof, sort_keys=True, separators=(",", ":"), default=str)
        reference["digest"] = "0x" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if isinstance(proof, dict):
        for name in ("mode", "tag", "tx_hash", "block_number"):
            if proof.get(name) is not None:
                reference[name] = proof[name]
    if proof_ref is not None:
        reference["reference"] = proof_ref
    return reference


def _verify(proof, verify_proof):
    """The proof condition of Algorithm 6.5. True only when a proof was presented, a verifier was given and the
    verifier returned True. Everything else fails closed, with the reason."""
    if proof is None:
        return False, "no proof was presented"
    if verify_proof is None:
        return False, "no proof verifier was given"
    try:
        verified = verify_proof(proof)
    except Exception as error:
        return False, f"the proof verifier failed: {str(error)[:200]}"
    if verified is True:
        return True, None
    return False, "the proof did not verify"


def release(consent, requester_did, request_scope, request_purpose, context="AU", proof=None, verify_proof=None,
            proof_ref=None, now=None, time_label=None, verify_sig=None, verify_did=None, decide=None, vault=None,
            audit=None, source=None, state_check=True):
    """Algorithm 6.5: judge the request, verify its proof, release the requested modules and record the outcome.

    consent           the stored consent the request is made against
    requester_did     the requester u
    request_scope     the record modules requested
    request_purpose   the purpose the request declares
    context           the context of the request (the two-letter code that the consent context is compared with)
    proof             the proof of Chapter 7 presented with the request
    verify_proof      callable (proof) -> True when the proof verifies. Without it nothing is released. The
                      release does not read the format of the proof: the caller gives the verifier that belongs
                      to this request, and that verifier answers for the public inputs of the proof as well
    proof_ref         a reference of the caller's own to the proof, recorded with its digest
    now, time_label   the time t of the request and the label of its source (services/time_source.py)
    verify_sig        approval check passed to the decision rule. None uses identity_service.verify_signature,
                      False switches the check off
    verify_did        identity check passed to the decision rule (default: the credential check)
    decide            another decision function (consent, requester, scope, purpose, context, now) -> matrix
    vault             the data vault (default: the vault of the Controller)
    audit             the audit ledger (default: database.audit_db)
    source            callable (patient_did, scope) -> {module: records}. When it is given and the vault has no
                      copy of a requested module, the consent-bound copy is sealed from it first
    state_check       write the STATE_CHECK record of the evaluation before the DATA_ACCESS record

    Returns a dict: outcome (GRANTED or DENIED), allow, deny_code, deny_codes, reason, decision (the matrix),
    state, data ({module: records}, empty unless GRANTED), modules, proof_verified, proof_reference, decided_at,
    time_source, audit_event and state_check_event. It holds no key."""
    ledger = audit or audit_db
    vault = vault if vault is not None else data_vault.default_vault()
    now, label = _decision_time(now, time_label)
    requester = requester_did if isinstance(requester_did, str) else ""
    scope = _scope_list(request_scope)
    purpose = request_purpose if isinstance(request_purpose, str) else ""
    reason = None

    # Algorithm 6.1: the decision for this request, with its matrix and its deny codes.
    try:
        if decide is not None:
            matrix = dict(decide(consent, requester, scope, purpose, context, now))
        else:
            matrix = decide_request(consent, requester, scope, purpose, context, now=now, verify_did=verify_did,
                                    verify_sig=verify_signature if verify_sig is None else (verify_sig or None))
    except Exception as error:
        matrix = {"VI": False, "VA": False, "VP": False, "VT": False, "VL": False, "ALLOW": False,
                  "DENY": [DENY_RECORD_INVALID]}
        reason = f"the decision could not be evaluated: {str(error)[:200]}"
    allow = matrix.get("ALLOW") is True
    codes = list(matrix.get("DENY") or [])
    if not allow and not codes:
        codes.append(DENY_RECORD_INVALID)
    state = _state(consent, now)

    # The proof is verified only for a request that the decision rule allows.
    proof_verified = None
    if allow:
        proof_verified, reason = _verify(proof, verify_proof)
        if not proof_verified:
            codes.append(DENY_PROOF_INVALID)

    # Decrypt, inside the Controller, the modules of the requested scope and no other module.
    data = {}
    if allow and proof_verified:
        try:
            if source is not None and not all(vault.has_copy(consent.consent_id, m) for m in scope):
                vault.seal_from_source(consent, source, now=now)
            data = vault.open(consent.consent_id, scope)
        except key_store.KeyDestroyedError:
            codes.append(DENY_REVOKED)
            reason = "the keys of the consent were destroyed"
        except Exception as error:
            codes.append(DENY_COPY_UNAVAILABLE)
            reason = f"the consent-bound copy could not be opened: {str(error)[:200]}"
    granted = allow and proof_verified is True and not codes
    if not granted:
        data = {}
    code = None if granted else primary_deny_code(codes)
    reference = proof_reference(proof, proof_ref)

    # Record the evaluation and the outcome in E, off chain.
    check_event = None
    if state_check:
        check_event = ledger.log(actor_did="System", actor_role="ConsentEngine", action="STATE_CHECK",
                                 patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                                 purpose=consent.purpose, result=state or "UNKNOWN", metadata=dict(matrix))
    released = list(data)
    references = vault.key_store.key_ids(consent.consent_id) if granted else {}
    event = ledger.log(actor_did=requester or str(requester_did), actor_role="Doctor", action="DATA_ACCESS",
                       patient_did=consent.patient_did, consent_id=consent.consent_id, scope=scope, purpose=purpose,
                       result=GRANTED if granted else DENIED,
                       metadata={"consent_state": state, "decision_matrix": dict(matrix), "deny_code": code,
                                 "deny_codes": [] if granted else codes, "reason": reason, "context": context,
                                 "consent_purpose": consent.purpose, "decision_time": now.isoformat(),
                                 "time_source": label, "zk_proof_verified": proof_verified,
                                 "proof_mode": proof.get("mode") if isinstance(proof, dict) else None,
                                 "proof_reference": reference, "modules_released": released,
                                 "key_references": {m: references.get(m) for m in released}})
    return {"outcome": GRANTED if granted else DENIED, "allow": allow, "deny_code": code,
            "deny_codes": [] if granted else codes, "reason": reason, "decision": matrix, "state": state, "data": data,
            "modules": released, "proof_verified": proof_verified, "proof_reference": reference,
            "decided_at": now.isoformat(), "time_source": label, "audit_event": event, "state_check_event": check_event}
