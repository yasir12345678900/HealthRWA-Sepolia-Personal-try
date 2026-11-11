'''
Conditional Triggers for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# A conditional trigger is a predicate over an attested event that must hold before a consent becomes active
# (thesis Sections 3.2.6 and 6.2.3). The example of the thesis is an advance directive, which waits for a
# clinician-signed attestation that the patient has lost capacity. This module is the trigger part of
# Algorithm 6.3 (Section 6.3.4):
#   add_trigger(consent, event, attester_role)       a trigger is added to the consent
#   sign_attestation(attester_did, consent, event)   the attester signs the attestation (EIP-712 typed data)
#   present_attestation(consent, attestation)        the attestation is verified, the trigger is marked satisfied
#                                                    and the event is recorded in the consent and in the ledger
#   evaluate_triggers(consent)                       each trigger is evaluated against its recorded attestation
#   waiting_triggers(consent)                        the triggers that still hold the consent back
# A consent with a trigger that is not satisfied is waiting on it: its lifecycle state is SUSPENDED and a request
# is denied with the code AWAITING-TRIGGER.
#
# An event is attested by a credential and is not asserted at the interface (Section 6.2.5). The credential of
# the attester and its role claim are verified with identity_service.check_credential, and the signature must
# recover to the key of the attester. In this prototype that key is the demonstration key which identity_service
# derives from the identifier. Anyone can rebuild it from the source, so the check demonstrates the verification
# and not the secrecy of the key. A wallet-held key is checked by passing its address to
# verify_attestation_signature, or by passing another check as verify_sig.
import uuid
from datetime import datetime, timedelta
from eth_account import Account
from eth_account.messages import encode_typed_data
from services import identity_service as ids

KIND_ATTESTATION = "attestation"
DENY_AWAITING_TRIGGER = "AWAITING-TRIGGER"       # deny code of Section 6.3.1 for a consent that waits on a trigger

# Reasons for which a consent takes no trigger and no attestation any more
CONSENT_REVOKED = "CONSENT-REVOKED"              # revoked, or retired after a capacity transition
CONSENT_EXPIRED = "CONSENT-EXPIRED"
RECORD_INVALID = "RECORD-INVALID"                # the validity window cannot be read
# Reasons for which an attestation is refused
ATTESTATION_MALFORMED = "ATTESTATION-MALFORMED"
TRIGGER_NOT_FOUND = "TRIGGER-NOT-FOUND"          # no trigger of the consent waits for this event
TRIGGER_ALREADY_SATISFIED = "TRIGGER-ALREADY-SATISFIED"
EVENT_MISMATCH = "EVENT-MISMATCH"                # the attested event is not the event of the trigger
ATTESTATION_REPLAYED = "ATTESTATION-REPLAYED"    # the consent has recorded this attestation already
ATTESTATION_TIME_INVALID = "ATTESTATION-TIME-INVALID"            # the signing time is unreadable or in the future
ATTESTATION_SIGNATURE_INVALID = "ATTESTATION-SIGNATURE-INVALID"  # not signed by the attester for this consent
ATTESTER_NOT_AUTHORISED = "ATTESTER-NOT-AUTHORISED"              # no valid credential with the required role
# Reasons for which a trigger is waiting when it is evaluated
AWAITING_ATTESTATION = "AWAITING-ATTESTATION"
ATTESTATION_MISSING = "ATTESTATION-MISSING"      # marked satisfied, but the consent holds no such attestation
TRIGGER_MALFORMED = "TRIGGER-MALFORMED"

# The checks of an attestation in the order in which a failure is reported
_CHECKS = (("Well_formed", ATTESTATION_MALFORMED), ("Event_match", EVENT_MISMATCH), ("Fresh", ATTESTATION_REPLAYED),
           ("Time_valid", ATTESTATION_TIME_INVALID), ("Sig_valid", ATTESTATION_SIGNATURE_INVALID),
           ("Attester_valid", ATTESTER_NOT_AUTHORISED))

# The clock of the attester and the time source of the decision may differ by this much (the tolerance that the
# verifier of Chapter 7 applies to the time of a proof).
CLOCK_TOLERANCE = timedelta(seconds=300)

# The typed data an attester signs. It names the consent, the patient, the event, the attester and the signing
# time, and its domain carries the chain identifier. A signature made for another consent, another patient,
# another event or another chain is therefore rejected, and a guardian approval can never be read as an
# attestation, because the two structures have different types and domain names.
ATTESTATION_DOMAIN = {"name": "HALAH Attestation", "version": "1"}
ATTESTATION_TYPES = {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                      {"name": "chainId", "type": "uint256"}],
                     "Attestation": [{"name": "attestationId", "type": "string"}, {"name": "consentId", "type": "string"},
                                     {"name": "patient", "type": "string"}, {"name": "event", "type": "string"},
                                     {"name": "attester", "type": "string"}, {"name": "signedAt", "type": "string"}]}
# Keys of an attestation as the consent records it. consent_id names the consent that the attester signed for.
_ATTESTATION_KEYS = ("id", "event", "attester_did", "signed_at", "signature")


def _local(moment):
    # the prototype compares local times without a zone, so a time that carries a zone is converted first
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo is not None else moment


def _ledger(audit):
    if audit is not None:
        return audit
    from database import audit_db              # imported here: the ledger opens its database when it is loaded
    return audit_db.log


def _store(save):
    if save is not None:
        return save
    from database import consent_db            # imported here, for the same reason
    return consent_db.save


def consent_ended(consent, now=None):
    """CONSENT-REVOKED, CONSENT-EXPIRED or RECORD-INVALID when the consent can no longer become active, else None.
    A consent that was replaced after a capacity transition (it has a successor) counts as revoked."""
    if (getattr(consent, "revoked", False) or getattr(consent, "successor_id", None)
            or getattr(consent, "state", None) == "REVOKED"):
        return CONSENT_REVOKED
    if getattr(consent, "state", None) == "EXPIRED":
        return CONSENT_EXPIRED
    try:
        expired = _local(now or datetime.now()) > _local(datetime.fromisoformat(str(consent.expiry_date)))
    except Exception:
        return RECORD_INVALID
    return CONSENT_EXPIRED if expired else None


def _readable(trigger):
    return (isinstance(trigger, dict) and trigger.get("kind") == KIND_ATTESTATION
            and all(isinstance(trigger.get(k), str) and trigger.get(k) for k in ("id", "event", "attester_role")))


def waiting_triggers(consent):
    """The triggers of the consent that are not satisfied. An entry that cannot be read counts as not satisfied."""
    return [t for t in (getattr(consent, "triggers", None) or [])
            if not (isinstance(t, dict) and t.get("satisfied") is True)]


def add_trigger(consent, event, attester_role="doctor", trigger_id=None, actor_did=None, actor_role="Patient",
                now=None, audit=None, save=None):
    """Add a conditional trigger to the consent: the consent waits until `event` is attested by a participant who
    holds a valid credential with the role `attester_role`. Returns the trigger.
    A trigger only narrows access, so it may be added in every state before the consent ends. There is no function
    that removes a trigger, because removing one would widen access without the approval of the guardians.
    actor_did, actor_role: who adds the trigger, for the audit ledger (the patient when they are left out).
    Raises ValueError for an empty event or role, a second trigger for the same event and role, an identifier that
    is in use, and a consent that is revoked or expired."""
    event = event.strip() if isinstance(event, str) else ""
    role = attester_role.strip() if isinstance(attester_role, str) else ""
    if not event:
        raise ValueError("the trigger must name the event that is to be attested")
    if not role:
        raise ValueError("the trigger must name the role of the attester")
    ended = consent_ended(consent, now)
    if ended:
        raise ValueError(f"a trigger cannot be added to this consent ({ended})")
    if not isinstance(consent.triggers, list):
        consent.triggers = []
    if any(isinstance(t, dict) and t.get("event") == event and t.get("attester_role") == role for t in consent.triggers):
        raise ValueError("the consent already has a trigger for this event and this attester role")
    trigger_id = str(trigger_id) if trigger_id else "trg-" + uuid.uuid4().hex[:12]
    if any(isinstance(t, dict) and t.get("id") == trigger_id for t in consent.triggers):
        raise ValueError("the consent already has a trigger with this identifier")
    trigger = {"id": trigger_id, "kind": KIND_ATTESTATION, "event": event, "attester_role": role,
               "satisfied": False, "attestation_id": None}
    consent.triggers.append(trigger)
    _store(save)(consent)
    _ledger(audit)(actor_did=actor_did or consent.patient_did, actor_role=actor_role, action="ADD_TRIGGER",
                   patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                   purpose=consent.purpose, result="SUCCESS",
                   metadata={"algorithm": "6.3", "trigger": dict(trigger),
                             "approvals_recorded": len(consent.signatures or [])})
    return trigger


# ---------------------------------------------------------------------------
# The attestation and its signature
# ---------------------------------------------------------------------------
def attestation_typed_data(attestation, patient_did, chain_id=None):
    """The typed data of an attestation: the JSON a wallet takes in eth_signTypedData_v4, so that a wallet-held
    key and the demonstration key sign the same bytes. `attestation` carries id, consent_id, event, attester_did
    and signed_at."""
    chain = int(ids.CHAIN_ID if chain_id is None else chain_id)
    return {"types": {name: [dict(f) for f in fields] for name, fields in ATTESTATION_TYPES.items()},
            "primaryType": "Attestation", "domain": dict(ATTESTATION_DOMAIN, chainId=chain),
            "message": {"attestationId": str(attestation["id"]), "consentId": str(attestation["consent_id"]),
                        "patient": str(patient_did), "event": str(attestation["event"]),
                        "attester": str(attestation["attester_did"]), "signedAt": str(attestation["signed_at"])}}


def _signable(attestation, patient_did, chain_id=None):
    return encode_typed_data(full_message=attestation_typed_data(attestation, patient_did, chain_id))


def sign_attestation(attester_did, consent, event, signed_at=None, attestation_id=None, signer=None, chain_id=None):
    """The attester's side: sign the statement that `event` has occurred for the patient of `consent`.
    Returns the attestation as it is presented: id, event, attester_did, signed_at, signature and consent_id.
    signer: an eth_account LocalAccount that stands for the attester's wallet. Without it the demonstration key
    derived from the identifier signs (see the note at the top of this module). An attester with a did:key
    identifier has no derived key, because the identifier names the key itself: the wallet that holds it signs."""
    if signer is None and str(attester_did).startswith("did:key:"):
        raise ValueError("a did:key attester signs with the wallet that holds its key: pass it as signer")
    if isinstance(signed_at, str):
        when = signed_at
    else:
        when = _local(signed_at or datetime.now()).isoformat(timespec="seconds")
    attestation = {"id": str(attestation_id) if attestation_id else "att-" + uuid.uuid4().hex[:12],
                   "event": str(event), "attester_did": str(attester_did), "signed_at": when,
                   "consent_id": consent.consent_id}
    account = signer or ids.guardian_account(attester_did)
    signature = account.sign_message(_signable(attestation, consent.patient_did, chain_id)).signature.hex()
    attestation["signature"] = signature if signature.startswith("0x") else "0x" + signature
    return attestation


def _well_formed(attestation):
    return (isinstance(attestation, dict)
            and all(isinstance(attestation.get(k), str) and attestation.get(k) for k in _ATTESTATION_KEYS)
            and isinstance(attestation.get("consent_id", ""), str))


def verify_attestation_signature(attestation, consent, address=None, chain_id=None, allow_demo_key=True):
    """True only if the attestation was signed by its attester for this consent, this patient and this chain.
    address: the wallet address of the attester. When it is given, the recovered signer must equal it. Without it
    the signer must be the demonstration key derived from the attester's identifier. That key is never accepted
    for a did:key identifier, which names its own key, and allow_demo_key=False switches it off altogether, so
    that only a signature from a registered wallet address is accepted.
    An attestation that the consent took over at its re-issue (capacity transition) was signed for the consent it
    replaces, so the identifier of the predecessor is accepted as well."""
    try:
        bound = attestation.get("consent_id") or consent.consent_id
        if bound not in {consent.consent_id, getattr(consent, "predecessor_id", None)} - {None}:
            return False
        attester = attestation["attester_did"]
        if address is None:
            if not allow_demo_key or str(attester).startswith("did:key:"):
                return False
            address = ids.guardian_address(attester)
        signable = _signable(dict(attestation, consent_id=bound), consent.patient_did, chain_id)
        recovered = Account.recover_message(signable, signature=attestation["signature"])
    except Exception:
        return False
    return isinstance(address, str) and recovered.lower() == address.lower()


def _attester_valid(did, role, now, verify_did):
    """The credential check of the attester: (valid, credential identifier, issuer). The default is the credential
    check of identity_service. verify_did(did, role=None, now=None) replaces it, for example Algorithm 5.1 in full."""
    if not role:
        return False, None, None               # without a role every credential would do
    if verify_did is None:
        checks = ids.check_credential(did, role=role, now=now)
        return bool(checks["VALID"]), checks.get("credential_id"), checks.get("issuer")
    try:
        return bool(verify_did(did, role=role, now=now)), None, None
    except TypeError:                          # a checker without a `now` argument still gets the role
        return bool(verify_did(did, role=role)), None, None


def check_attestation(consent, trigger, attestation, now=None, verify_did=None, verify_sig=None):
    """Evaluate one attestation against one trigger without changing anything. Returns each condition, VALID and
    the reason of the first condition that fails:
    Well_formed     the attestation carries id, event, attester_did, signed_at and signature
    Event_match     it attests the event of the trigger
    Fresh           the consent has not recorded an attestation with this identifier
    Time_valid      the signing time can be read and is not in the future
    Sig_valid       the signature recovers to the attester's key for this consent (verify_sig(attestation, consent))
    Attester_valid  the attester holds a valid credential with the role the trigger requires, at `now`"""
    now = _local(now or datetime.now())
    r = {"Well_formed": _well_formed(attestation), "Event_match": False, "Fresh": False, "Time_valid": False,
         "Sig_valid": False, "Attester_valid": False, "credential_id": None, "issuer": None}
    if r["Well_formed"] and isinstance(trigger, dict):
        r["Event_match"] = attestation["event"] == trigger.get("event")
        r["Fresh"] = not any(isinstance(a, dict) and a.get("id") == attestation["id"]
                             for a in (consent.attestations or []))
        try:
            r["Time_valid"] = _local(datetime.fromisoformat(attestation["signed_at"])) <= now + CLOCK_TOLERANCE
        except Exception:
            r["Time_valid"] = False
        try:
            r["Sig_valid"] = bool((verify_sig or verify_attestation_signature)(attestation, consent))
        except Exception:
            r["Sig_valid"] = False
        try:
            r["Attester_valid"], r["credential_id"], r["issuer"] = _attester_valid(
                attestation["attester_did"], trigger.get("attester_role"), now, verify_did)
        except Exception:
            r["Attester_valid"] = False
    r["reason"] = next((code for key, code in _CHECKS if not r[key]), None)
    r["VALID"] = r["reason"] is None
    return r


def present_attestation(consent, attestation, trigger_id=None, now=None, verify_did=None, verify_sig=None,
                        audit=None, save=None):
    """Algorithm 6.3, trigger part: present an attestation for a trigger of the consent. When every check of
    check_attestation holds, the attestation is recorded in the consent, the trigger is marked satisfied and the
    event is written to the audit ledger. A refused attestation changes nothing and is written to the ledger with
    its reason.
    trigger_id: the trigger the attestation is meant for. Without it, the triggers that wait for the attested
    event are tried in their order.
    Returns a dict with VALID, reason, trigger_id, attestation_id and checks."""
    now = _local(now or datetime.now())
    formed = _well_formed(attestation)

    def done(valid, reason, trigger=None, checks=None):
        role = trigger.get("attester_role") if isinstance(trigger, dict) else None
        evidence = {"algorithm": "6.3", "trigger_id": trigger.get("id") if isinstance(trigger, dict) else trigger_id,
                    "reason": reason, "presented_at": now.isoformat(), "checks": checks}
        if formed:
            evidence.update(attestation_id=attestation["id"], event=attestation["event"],
                            signed_at=attestation["signed_at"])
        else:
            evidence["attestation"] = repr(attestation)[:200]
        _ledger(audit)(actor_did=attestation["attester_did"] if formed else "unknown",
                       actor_role=role.capitalize() if isinstance(role, str) and role else "Attester",
                       action="PRESENT_ATTESTATION", patient_did=consent.patient_did, consent_id=consent.consent_id,
                       scope=consent.scope, purpose=consent.purpose, result="SUCCESS" if valid else "REJECTED",
                       metadata=evidence)
        return {"VALID": valid, "reason": reason, "trigger_id": evidence["trigger_id"],
                "attestation_id": attestation["id"] if formed else None, "checks": checks}

    ended = consent_ended(consent, now)
    if ended:
        return done(False, ended)
    if not formed:
        return done(False, ATTESTATION_MALFORMED)
    triggers = [t for t in (consent.triggers or []) if _readable(t)]
    if trigger_id is not None:
        candidates = [t for t in triggers if t["id"] == trigger_id]
    else:
        candidates = [t for t in triggers if t["event"] == attestation["event"]]
    if not candidates:
        return done(False, TRIGGER_NOT_FOUND)
    waiting = [t for t in candidates if t.get("satisfied") is not True]
    if not waiting:
        return done(False, TRIGGER_ALREADY_SATISFIED, candidates[0])
    refused = None
    for trigger in waiting:
        checks = check_attestation(consent, trigger, attestation, now, verify_did, verify_sig)
        if checks["VALID"]:
            # the event is recorded with the consent, and the trigger points to it
            record = {k: attestation[k] for k in _ATTESTATION_KEYS}
            record["consent_id"] = attestation.get("consent_id") or consent.consent_id
            if not isinstance(consent.attestations, list):
                consent.attestations = []
            consent.attestations.append(record)
            trigger.update(satisfied=True, attestation_id=record["id"])
            _store(save)(consent)
            return done(True, None, trigger, checks)
        refused = refused or (trigger, checks)
    return done(False, refused[1]["reason"], refused[0], refused[1])


def evaluate_triggers(consent, verify_sig=None, audit=None, save=None):
    """Algorithm 6.3, trigger evaluation: evaluate each trigger of the consent against its recorded attestation.
    A trigger is satisfied only if it is marked satisfied, the consent holds the attestation it points to, the
    attestation names the event of the trigger and its signature still verifies for this consent. A trigger that
    is marked satisfied without such an attestation is set back to waiting, and the change is written to the
    ledger. A trigger that cannot be read, or whose kind this module does not know, is not satisfied.
    The credential of the attester was checked when the attestation was presented and is not checked again, so a
    credential that expires later does not suspend the consent.
    Returns one dict for each trigger with id, event, satisfied and reason."""
    verify = verify_sig or verify_attestation_signature
    recorded = {a.get("id"): a for a in (getattr(consent, "attestations", None) or []) if isinstance(a, dict)}
    results, set_back = [], []
    for trigger in (getattr(consent, "triggers", None) or []):
        if not _readable(trigger):
            known = trigger if isinstance(trigger, dict) else {}
            if known.get("satisfied") is True:
                set_back.append({"trigger_id": known.get("id"), "event": known.get("event"),
                                 "reason": TRIGGER_MALFORMED, "attestation_id": known.get("attestation_id")})
                trigger.update(satisfied=False, attestation_id=None)
            results.append({"id": known.get("id"), "event": known.get("event"), "satisfied": False,
                            "reason": TRIGGER_MALFORMED})
            continue
        reason = None
        if trigger.get("satisfied") is not True:
            reason = AWAITING_ATTESTATION
        else:
            attestation = recorded.get(trigger.get("attestation_id"))
            if not _well_formed(attestation):
                reason = ATTESTATION_MISSING
            elif attestation["event"] != trigger["event"]:
                reason = EVENT_MISMATCH
            else:
                try:
                    signed = bool(verify(attestation, consent))
                except Exception:
                    signed = False
                if not signed:
                    reason = ATTESTATION_SIGNATURE_INVALID
            if reason:
                set_back.append({"trigger_id": trigger["id"], "event": trigger["event"], "reason": reason,
                                 "attestation_id": trigger.get("attestation_id")})
                trigger.update(satisfied=False, attestation_id=None)
        results.append({"id": trigger["id"], "event": trigger["event"], "satisfied": reason is None, "reason": reason})
    if set_back:
        _store(save)(consent)
        _ledger(audit)(actor_did="System", actor_role="ConsentEngine", action="TRIGGER_CHECK",
                       patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                       purpose=consent.purpose, result="WAITING", metadata={"algorithm": "6.3", "set_back": set_back})
    return results
