'''
Request Path of the Clinician Interface for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-17
'''
# One access request as the running application carries it out (thesis Chapters 6 and 7), in this order:
#
#   1. the time t of the decision, from the block timestamp of the chain when a chain is configured
#      (services/blockchain_service.chain_time). When the chain cannot be read the request is refused and the
#      reason is recorded: the server clock is not used in its place
#   2. the requester, by Algorithm 5.1 (identity_service.verify_identity), with the evidence recorded
#   3. the triggers and the capacity transitions, by Algorithm 6.3 (capacity_service.evaluate_conditions)
#   4. the decision matrix, by Algorithm 6.1 (access_service.decision_matrix), with VA over the approvals alone
#   5. the lifecycle check, by Algorithm 6.2 (state_service.validate_lifecycle), which writes the STATE_CHECK record
#   6. for a request the rule allows, the proof of the decision (Algorithms 7.1 and 7.2) and its verification on
#      chain by the verifier contract (Algorithm 7.3), before any data are delivered
#   7. the release, by Algorithm 6.5 (release_service.release), which decrypts the requested modules of the
#      consent-bound copy inside the Controller and writes the DATA_ACCESS record with the proof reference
#
# submit_request() is that path. The clinician screen calls it once for each click, and a test or a tool can
# call it with a ledger, a vault and a store of its own.
#
# A deny code is recorded and shown only when it is one of the nine of Section 6.3.1. A failure that has none
# (VI, VA, a consent without its token, the proof, the copy, the time source) is named in failed_checks.
import functools

from database import audit_db
from services import access_service, blockchain_service as bc, capacity_service, release_service, state_service
from services import identity_service as ids
from services import time_source, zk_decision_service, zk_service

GRANTED, DENIED = release_service.GRANTED, release_service.DENIED

# Names of the failures that are not predicates of the decision rule.
CHECK_PROOF, CHECK_COPY, CHECK_TIME = "proof", "copy", "time source"
TIME_UNAVAILABLE = "unavailable"

# Why no proof could be made, in the words the screen shows and the ledger keeps.
NO_VERIFIER = "no decision verifier is configured"
NO_CIRCUIT = "the decision circuit is not built on this machine"
TOKEN_NOT_CONFIRMED = "the token of this consent is not confirmed on chain yet"
STATEMENT_NOT_MET = "the record of this consent does not match what the chain holds"
PROVER_FAILED = "the prover gave no proof on this machine"
CHAIN_NOT_READ = "the chain could not be read"


def shown_code(decision):
    """The one deny code to show and to record for a decision: the first entry of its DENY list that is one of
    the nine codes of Section 6.3.1, or None. `decision` is a matrix or the list itself."""
    codes = decision.get("DENY", []) if isinstance(decision, dict) else list(decision or [])
    return next((code for code in codes if code in access_service.DENY_CODES), None)


def failed_checks(matrix):
    """The predicates of the decision rule that are false, by name."""
    return release_service.failed_checks(matrix)


def request_scope(scope):
    """The requested modules as a list of names without repeats. A scope that is missing or is not a list of
    module names is the empty list, which the decision rule refuses."""
    if not isinstance(scope, (list, tuple, set, frozenset)) or not all(isinstance(m, str) for m in scope):
        return []
    return list(dict.fromkeys(scope))


def decide(consent, requester_did, scope, purpose, context, now):
    """Algorithm 6.1 as the application decides a stored consent: VI with Algorithm 5.1 for the requester and the
    approval check that fits the record, VA over the distinct approvals alone, the token and revocation
    conditions under VL. A scope or a purpose given as None is not compared (the screen shows the matrix before
    a module is chosen), so submit_request never passes None."""
    return access_service.decision_matrix(consent, context, now=now, verify_sig=ids.approval_check(consent),
                                          verify_did=ids.verify_identity, requester_did=requester_did,
                                          request_purpose=purpose, request_scope=scope, va_approvals_only=True)


def decision_time():
    """The time of a decision as (evidence, None), or (None, reason) when a chain is configured and it cannot be
    read. The evidence is that of services/time_source.read_time."""
    try:
        return bc.chain_time(), None
    except time_source.TimeSourceError as error:
        return None, str(error)


def _time_record(time):
    return {name: time.get(name) for name in ("source", "unix", "block_number", "clock_skew_seconds")}


def lifecycle_check(consent, time, target=None, matrix=None, request=None, identity=None, requested_by=None,
                    audit=None):
    """Algorithm 6.2 for one evaluation, with its STATE_CHECK record in the audit ledger.
    target=None is the check of a data access: the record carries the lifecycle state, the decision matrix of the
    request, the failed checks, the request as declared, the time with its source and the outcome of the identity
    check. target=<state> is the transition check of lines 16 to 20, for example "REVOKED" before a revocation:
    the record carries the evidence, who requested the transition and the time, and no matrix.
    time is the evidence of decision_time(). Returns (evidence, ledger row)."""
    ledger = audit or audit_db
    rows = []

    def record(evidence):
        lifecycle = dict(evidence)
        if lifecycle.get("deny_code") not in access_service.DENY_CODES:
            lifecycle["deny_code"] = None                  # a code is recorded only when it is one of the nine
        metadata = {}
        if matrix is not None:
            metadata.update({name: matrix[name] for name in access_service.MATRIX_KEYS + ("VU", "VS", "VX")})
            metadata["DENY"] = release_service.section_codes(matrix.get("DENY"))
            metadata["failed_checks"] = failed_checks(matrix)
        metadata["lifecycle"] = lifecycle
        metadata.update(request or {})
        if requested_by is not None:
            metadata["requested_by"] = requested_by
        metadata["time"] = _time_record(time)
        if identity is not None:
            metadata["requester_identity"] = {"result": identity.result, "reason": identity.reason,
                                              "credential_id": identity.evidence.get("credential_id"),
                                              "issuer": identity.evidence.get("issuer")}
        rows.append(ledger.log(actor_did="System", actor_role="ConsentEngine", action="STATE_CHECK",
                               patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                               purpose=consent.purpose, result=evidence.get("state") or "UNKNOWN", metadata=metadata))

    evidence = state_service.validate_lifecycle(consent, time["time"], target=target, record=record)
    return evidence, rows[0] if rows else None


def _refuse_without_time(consent, requester, scope, purpose, context, reason, ledger):
    """The one DATA_ACCESS record that the request path writes itself: a chain is configured and its time could
    not be read, so nothing was evaluated. No STATE_CHECK record goes with it."""
    reason = f"the time of the chain could not be read: {reason}"
    event = ledger.log(actor_did=requester, actor_role="Doctor", action="DATA_ACCESS", patient_did=consent.patient_did,
                       consent_id=consent.consent_id, scope=scope, purpose=purpose, result=DENIED,
                       metadata={"deny_code": None, "deny_codes": [], "failed_checks": [CHECK_TIME], "reason": reason,
                                 "context": context, "consent_purpose": consent.purpose,
                                 "time_source": TIME_UNAVAILABLE, "modules_released": []})
    return {"outcome": DENIED, "allow": False, "deny_code": None, "deny_codes": [], "failed_checks": [CHECK_TIME],
            "reason": reason, "decision": None, "state": None, "data": {}, "modules": [], "proof_verified": None,
            "proof_reference": None, "decided_at": None, "time_source": TIME_UNAVAILABLE, "audit_event": event,
            "state_check_event": None, "time": None, "identity": None, "lifecycle": None, "verification": None,
            "proof_error": None}


def _decision_proof(consent, requester, scope, purpose, context, time):
    """The proof condition of Algorithm 6.5 for a request the rule allows: (proof, verifier, reference, answer).
    With ConsentSBTv4 configured the proof is the proof of the decision rule and the verifier is the verifier
    contract. `reference` goes to the DATA_ACCESS record with the proof: it is filled when the contract answers,
    and `answer` receives what the contract returned. Without a verifier contract, without the built circuit, when
    the prover fails, or for a consent whose token is not on chain, no proof is presented and the release is refused.
    In demo mode the proof of services/zk_service is made and checked locally, with its mode recorded."""
    if not bc.v4_enabled():
        return zk_service.generate_proof(consent), zk_service.verify_proof, None, None
    reference, answer = {}, {}
    if not bc.proof_enabled():
        reference["error"] = NO_VERIFIER
        return None, None, reference, answer
    try:
        proof = bc.decision_proof(consent, requester, purpose, context, scope, time["unix"])
    except zk_decision_service.ProofUnavailable:
        reference["error"] = NO_CIRCUIT
        return None, None, reference, answer
    except zk_decision_service.DecisionProofError as error:
        if not error.failed:
            # every predicate of the statement holds and the prover itself failed (for example node cannot load
            # snarkjs): the record is not at fault, so the reason names the prover
            reference.update(error=PROVER_FAILED, detail=str(error.detail)[:200])
            return None, None, reference, answer
        waiting = "ISSUED" in error.failed and not bc.has_chain_token(consent)
        reference.update(error=TOKEN_NOT_CONFIRMED if waiting else STATEMENT_NOT_MET, predicates=list(error.failed))
        return None, None, reference, answer
    except Exception as error:
        reference.update(error=CHAIN_NOT_READ, detail=str(error)[:200])
        return None, None, reference, answer

    def on_chain(presented):
        try:
            answer.update(bc.verify_decision(presented))
        except Exception as error:
            reference.update(error=CHAIN_NOT_READ, detail=str(error)[:200])
            return False
        if answer.get("accepted") is not True:
            reference["reason_text"] = answer.get("reason_text")
            return False
        # the transaction of the ConsentVerified event is the proof reference of the DATA_ACCESS record
        presented["tx_hash"], presented["block_number"] = answer["tx_hash"], answer["block_number"]
        reference.update(nonce=presented["audit"]["nonce"], gas_used=answer.get("gas_used"),
                         verifier=answer.get("contract"), chain_id=answer.get("chain_id"))
        return True
    return proof, on_chain, reference, answer


def submit_request(consent, requester_did, scope, purpose, context="AU", source=None, time=None, vault=None,
                   audit=None, save=None):
    """One submitted access request, from the time of the decision to the DATA_ACCESS record.

    consent        the stored consent the request is made against
    requester_did  the requester u
    scope          the record modules requested. A missing scope is the empty scope
    purpose        the purpose the request declares. A missing purpose is the empty purpose
    context        the context of the request (the jurisdiction code that VP compares)
    source         callable (patient_did, scope) -> {module: records}: the source record, from which the
                   consent-bound copy is sealed when the vault holds none
    time           the evidence of decision_time(), when the caller has read it for this request already
    vault, audit   the data vault and the audit ledger (default: those of the Controller)
    save           callable (consent) that stores a consent whose state moved (default: the consent store)

    Returns the dict of release_service.release (outcome, allow, deny_code, deny_codes, failed_checks, reason,
    decision, state, data, modules, proof_verified, proof_reference, decided_at, time_source, audit_event) and
    time, identity, lifecycle, state_check_event, verification (the answer of the verifier contract) and
    proof_error (why no proof could be made). deny_code is one of the nine codes or None."""
    ledger = audit or audit_db
    requester = requester_did if isinstance(requester_did, str) else ""
    scope = request_scope(scope)
    purpose = purpose if isinstance(purpose, str) else ""
    if time is None:
        time, reason = decision_time()
        if time is None:
            return _refuse_without_time(consent, requester, scope, purpose, context, reason, ledger)
    now = time["time"]

    # Algorithm 5.1 for the requester. The evidence of a valid verification is recorded (line 21).
    record = functools.partial(ids.record_identity_evidence, consent_id=consent.consent_id,
                               patient_did=consent.patient_did, actor_role="Doctor", audit=audit)
    identity = ids.verify_identity(requester, role="doctor", now=now, record=record)

    # Algorithm 6.3: triggers and capacity transitions are evaluated before the decision.
    capacity_service.evaluate_conditions(consent, now, audit=None if audit is None else ledger.log, save=save)

    # Algorithms 6.1 and 6.2: the matrix of this request and the lifecycle check with its STATE_CHECK record.
    matrix = decide(consent, requester, scope, purpose, context, now)
    lifecycle, check_event = lifecycle_check(
        consent, time, matrix=matrix, identity=identity, audit=audit,
        request={"requester_did": requester, "request_purpose": purpose, "request_scope": scope, "context": context})

    # Chapter 7: after the matrix and before any data are delivered, the proof and its verification.
    proof = verify = reference = answer = None
    if matrix["ALLOW"]:
        proof, verify, reference, answer = _decision_proof(consent, requester, scope, purpose, context, time)

    # Algorithm 6.5: the release from the consent-bound copy and the DATA_ACCESS record.
    out = release_service.release(consent, requester, scope, purpose, context, proof=proof, verify_proof=verify,
                                  proof_ref=reference, now=now, time_label=time["source"],
                                  decide=lambda *request: dict(matrix), vault=vault, audit=audit, source=source,
                                  state_check=False, section_codes_only=True)
    out.update(time=time, identity=identity, lifecycle=lifecycle, state_check_event=check_event,
               verification=answer or None, proof_error=(reference or {}).get("error"))
    return out
