'''
Capacity Transitions for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# A capacity transition is a documented life event that changes who may consent for the patient (thesis
# Sections 3.2.6 and 6.2.3). The thesis delivers one: the patient reaches the age of majority, after which the
# guardian set becomes the patient alone. This module is the transition part of Algorithm 6.3 (Section 6.3.4)
# and the function that evaluates the triggers and the transitions of a consent together:
#   schedule_majority_transition(consent)      the rule is scheduled from the date of birth and the majority age
#   pending_transitions(consent, now)          the transitions that are due and not executed
#   evaluate_conditions(consent, now)          Algorithm 6.3: the triggers against their attestations and the
#                                              transitions against the time, giving SUSPENDED or the state the
#                                              lifecycle derives
#   prepare_successor(consent, now)            the consent as it is re-issued, for the patient to sign
#   execute_transition(consent, mint, revoke)  the re-issue: the patient signs, the new consent is minted, the old
#                                              one is retired, and the two are linked
# From the day of majority until the transition is executed the consent is SUSPENDED and a request is denied with
# the code TRANSITION-PENDING, because the approvals of the former guardians no longer carry authority.
#
# The re-issued consent has the patient as its sole guardian and a threshold of one, and the patient signs it.
# Every other field of the specification is carried over unchanged. On chain the transition is a mint and a
# revocation, made by two callables that the caller supplies, and neither of them is given a reason. The
# transition itself is recorded in the audit ledger, off chain.
#
# The patient's signature is checked with identity_service.verify_signature. With the default signer it is made
# with the demonstration key which identity_service derives from the identifier, and anyone can rebuild that key
# from the source. A wallet-held key signs the consent that prepare_successor returns, and the signature is passed
# to execute_transition together with the check that fits it.
import copy
import uuid
from dataclasses import fields
from datetime import date, datetime
from models.consent import Consent
from services import identity_service as ids
from services import trigger_service
from services.state_service import lifecycle_state
from services.trigger_service import DENY_AWAITING_TRIGGER, _ledger, _local, _store

KIND_MAJORITY = "majority"
DENY_TRANSITION_PENDING = "TRANSITION-PENDING"   # deny code of Section 6.3.1 for a consent whose transition is due
RETIRED_BY = "CAPACITY_TRANSITION"               # recorded in revoked_by of a consent that was re-issued

# Outcomes of execute_transition
COMPLETED = "COMPLETED"                          # minted, linked, the old consent retired and its token revoked
REFUSED = "REFUSED"                              # nothing was changed
MINT_FAILED = "MINT-FAILED"                      # nothing was changed, the transition stays pending
REVOKE_PENDING = "REVOKE-PENDING"                # re-issued and retired off chain, the old token is not revoked yet
# Reasons of a refusal
NO_TRANSITION_DUE = "NO-TRANSITION-DUE"
ALREADY_TRANSITIONED = "ALREADY-TRANSITIONED"
CONSENT_REVOKED = trigger_service.CONSENT_REVOKED
CONSENT_EXPIRED = trigger_service.CONSENT_EXPIRED
RECORD_INVALID = trigger_service.RECORD_INVALID
TOKEN_PENDING = "TOKEN-PENDING"                  # the mint of the old consent is not recorded yet
PATIENT_IDENTIFIER_INVALID = "PATIENT-IDENTIFIER-INVALID"
PATIENT_SIGNATURE_INVALID = "PATIENT-SIGNATURE-INVALID"
SUCCESSOR_MISMATCH = "SUCCESSOR-MISMATCH"        # the prepared consent is not the re-issue of this consent
REVOKE_FAILED = "REVOKE-FAILED"

# Fields in which a prepared successor may differ from the one prepare_successor builds: its own identifier, the
# approval that execute_transition records, the state, and the commitment and key material that the issuance
# attaches before the patient signs.
_FREE_FIELDS = {"consent_id", "signatures", "signature_data", "state", "commitment", "commitment_opening",
                "token_address", "guardian_addresses", "zk_secret", "zk_commitment"}


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------
def _birth_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.strip()).date()
        except ValueError:
            pass
    raise ValueError("the date of birth must be an ISO date, for example 2010-03-14")


def majority_date(birth_date, majority_age=18):
    """The start of the day on which a person born on `birth_date` reaches `majority_age`, as a local time.
    A person born on 29 February reaches the age on 1 March in a year that has no 29 February."""
    born = _birth_date(birth_date)
    if isinstance(majority_age, bool) or not isinstance(majority_age, int) or majority_age < 1:
        raise ValueError("the majority age must be a whole number of years")
    year = born.year + majority_age
    try:
        day = date(year, born.month, born.day)
    except ValueError:
        day = date(year, 3, 1)
    return datetime(day.year, day.month, day.day)


def _majority_entries(consent):
    return [t for t in (getattr(consent, "transitions", None) or [])
            if isinstance(t, dict) and t.get("kind") == KIND_MAJORITY]


def schedule_majority_transition(consent, now=None, audit=None, save=None):
    """Schedule the capacity transition of a minor patient: an entry of `consent.transitions` that falls due on the
    day the patient reaches `consent.majority_age`, computed from `consent.patient_birth_date`. Call it when the
    consent is created. Returns the transition, or None when no transition applies: the consent records no date of
    birth, the patient has reached majority at `now` already, or the patient is the sole guardian already.
    A consent that has a majority transition keeps it, and the existing entry is returned.
    Raises ValueError for a date of birth or a majority age that cannot be read."""
    existing = _majority_entries(consent)
    if existing:
        return existing[0]
    if not getattr(consent, "patient_birth_date", None):
        return None
    due = majority_date(consent.patient_birth_date, consent.majority_age)
    if list(consent.guardian_dids or []) == [consent.patient_did] or due <= _local(now or datetime.now()):
        return None
    transition = {"id": "trn-" + uuid.uuid4().hex[:12], "kind": KIND_MAJORITY, "due": due.isoformat(), "done": False}
    if not isinstance(consent.transitions, list):
        consent.transitions = []
    consent.transitions.append(transition)
    _store(save)(consent)
    _ledger(audit)(actor_did="System", actor_role="ConsentEngine", action="SCHEDULE_TRANSITION",
                   patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                   purpose=consent.purpose, result="SUCCESS",
                   metadata={"algorithm": "6.3", "transition": dict(transition), "majority_age": consent.majority_age})
    return transition


# ---------------------------------------------------------------------------
# Evaluation (Algorithm 6.3)
# ---------------------------------------------------------------------------
def pending_transitions(consent, now=None):
    """The capacity transitions that are due at `now` and not executed. An entry that cannot be read counts as
    pending, so that a damaged record suspends the consent instead of leaving the former guardians in charge."""
    now = _local(now or datetime.now())
    pending = []
    for transition in (getattr(consent, "transitions", None) or []):
        if isinstance(transition, dict) and transition.get("done") is True:
            continue
        try:
            due = _local(datetime.fromisoformat(str(transition["due"]))) <= now
        except Exception:
            due = True
        if due:
            pending.append(transition)
    return pending


def _due_majority(consent, now):
    """The majority transitions that can be executed at `now`: not done, and due by a time that can be read.
    An entry without a readable time is pending, but it is not executed, because nothing shows that the patient
    has reached majority."""
    due = []
    for transition in _majority_entries(consent):
        if transition.get("done") is True:
            continue
        try:
            if _local(datetime.fromisoformat(str(transition["due"]))) <= now:
                due.append(transition)
        except Exception:
            pass
    return due


def _condition_state(consent, now):
    """The lifecycle state with the triggers and the transitions taken into account: a consent that would be
    ACTIVE is SUSPENDED while a trigger waits or a transition is pending. None when the state cannot be derived."""
    try:
        state = lifecycle_state(consent, now)
    except Exception:
        return None
    if state == "ACTIVE" and (trigger_service.waiting_triggers(consent) or pending_transitions(consent, now)):
        return "SUSPENDED"
    return state


def evaluate_conditions(consent, now=None, verify_sig=None, audit=None, save=None):
    """Algorithm 6.3, evaluation: evaluate each trigger of the consent against its attestation and each capacity
    transition against the time `now`, and move the consent between SUSPENDED and ACTIVE. The state is written to
    the consent, and a move into or out of SUSPENDED is written to the audit ledger.
    verify_sig(attestation, consent): the signature check of the recorded attestations (trigger_service).
    Returns the evidence: consent_id, time, triggers (one entry for each trigger), waiting_triggers and
    pending_transitions (identifiers), state, suspended and deny_codes (AWAITING-TRIGGER, TRANSITION-PENDING)."""
    now = _local(now or datetime.now())
    triggers = trigger_service.evaluate_triggers(consent, verify_sig=verify_sig, audit=audit, save=save)
    waiting = [t["id"] for t in triggers if not t["satisfied"]]
    pending = [t.get("id") if isinstance(t, dict) else None for t in pending_transitions(consent, now)]
    state = _condition_state(consent, now)
    suspended = state == "SUSPENDED"
    codes = ([DENY_AWAITING_TRIGGER] if waiting else []) + ([DENY_TRANSITION_PENDING] if pending else [])
    evidence = {"consent_id": consent.consent_id, "time": now.isoformat(), "triggers": triggers,
                "waiting_triggers": waiting, "pending_transitions": pending, "state": state,
                "suspended": suspended, "deny_codes": codes if suspended else []}
    previous = getattr(consent, "state", None)
    if state is not None and state != previous:
        consent.state = state
        _store(save)(consent)
        if "SUSPENDED" in (previous, state):
            _ledger(audit)(actor_did="System", actor_role="ConsentEngine", action="CONDITION_CHECK",
                           patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                           purpose=consent.purpose, result=state,
                           metadata={"algorithm": "6.3", "previous_state": previous, "time": evidence["time"],
                                     "waiting_triggers": waiting, "pending_transitions": pending,
                                     "deny_codes": evidence["deny_codes"]})
    return evidence


# ---------------------------------------------------------------------------
# Execution: the re-issue at majority
# ---------------------------------------------------------------------------
def prepare_successor(consent, now=None):
    """The consent as it is re-issued at the capacity transition that is due at `now`: a new consent identifier,
    the patient as the sole guardian, a threshold of one, no approval and no token yet, and a link back to the
    consent it replaces. The requester, the purpose, the scope, the validity window, the context, the triggers and
    the recorded attestations are carried over unchanged, and the transition is marked done in the new consent.
    Nothing is stored and `consent` is not changed. Raises ValueError when no majority transition is due."""
    now = _local(now or datetime.now())
    due = _due_majority(consent, now)
    if not due:
        raise ValueError("no capacity transition of this consent is due")
    transitions = copy.deepcopy(consent.transitions)
    for old, new in zip(consent.transitions, transitions):
        if any(old is t for t in due):
            new["done"] = True
    return Consent(consent_id=str(uuid.uuid4()), patient_did=consent.patient_did, requester_did=consent.requester_did,
                   guardian_dids=[consent.patient_did], purpose=consent.purpose, scope=list(consent.scope),
                   threshold=1, signatures=[], start_date=consent.start_date, expiry_date=consent.expiry_date,
                   state="PENDING_SIGNATURE", jurisdiction=consent.jurisdiction,
                   triggers=copy.deepcopy(consent.triggers or []), transitions=transitions,
                   attestations=copy.deepcopy(consent.attestations or []),
                   patient_birth_date=consent.patient_birth_date, majority_age=consent.majority_age,
                   predecessor_id=consent.consent_id)


def _successor_mismatch(consent, successor, now):
    """The fields in which a prepared successor is not the re-issue of `consent`. An empty list means that it
    changes nothing but the guardian set and the threshold."""
    if not isinstance(successor, Consent):
        return ["successor"]
    expected = prepare_successor(consent, now)
    differing = [f.name for f in fields(Consent)
                 if f.name not in _FREE_FIELDS and getattr(successor, f.name) != getattr(expected, f.name)]
    if not isinstance(successor.consent_id, str) or not successor.consent_id or successor.consent_id == consent.consent_id:
        differing.append("consent_id")
    if set(successor.guardian_addresses or {}) - {consent.patient_did}:
        differing.append("guardian_addresses")
    return differing


def _failed(receipt):
    return isinstance(receipt, dict) and receipt.get("status") is not None and receipt.get("status") != 1


def _tx(receipt):
    return (receipt.get("tx_hash"), receipt.get("block_number")) if isinstance(receipt, dict) else (None, None)


def _token_id(receipt, consent):
    """The token identifier of a mint, in the form the consent records it (SBT-<number> for a token on chain)."""
    if _failed(receipt):
        raise RuntimeError("the mint transaction failed")
    token = receipt.get("token_id") if isinstance(receipt, dict) else receipt
    if token is None or token == "" or isinstance(token, bool):
        token = consent.token_id               # the callable may have recorded the token in the consent itself
    if isinstance(token, int) and not isinstance(token, bool):
        return f"SBT-{token}"
    if isinstance(token, str) and token:
        return f"SBT-{int(token)}" if token.isdigit() else token
    raise RuntimeError("the mint returned no token identifier")


def execute_transition(consent, mint, revoke, now=None, successor=None, signature=None, sign=None, verify_sig=None,
                       audit=None, save=None):
    """Algorithm 6.3, capacity transition: re-issue `consent` at the majority of the patient.
    The steps: a majority transition must be due at `now`, and the consent must not be revoked, expired or still
    waiting for its own mint. The successor is built (prepare_successor), the patient signs it and the signature
    is verified. mint(successor) mints the new commitment. The two consents are linked through successor_id and
    predecessor_id, the old consent is retired, and revoke(consent) revokes its token. On chain the transition is
    therefore one mint and one revocation. Every outcome is written to the audit ledger.

    mint(successor): mints the token of the re-issued consent. It returns the token identifier or a receipt with
        token_id and, for a transaction on chain, tx_hash, block_number and status. It may attach the commitment
        to the consent it is given. It raises, or returns status 0, when the mint fails.
    revoke(consent): revokes the token of the old consent, with the same conventions. It is called only when the
        old consent has a token.
    successor, signature: a consent prepared with prepare_successor and the patient's signature over it, for a
        key that the patient holds in a wallet. A prepared consent that differs from the re-issue in anything but
        the guardian set and the threshold is refused.
    sign(patient_did, consent_id) -> (signature, address): produces the signature when none is given. The default
        is identity_service.sign_consent with the demonstration key.
    verify_sig(patient_did, consent_id, signature): the signature check, identity_service.verify_signature by
        default. The default knows only the demonstration key, so it refuses a patient with a did:key identifier.

    Returns a dict with status (COMPLETED, REFUSED, MINT-FAILED or REVOKE-PENDING), reason, transition_id,
    predecessor_id, successor_id, successor, mint and revoke (the two receipts).
    MINT-FAILED changes nothing: the transition stays pending and can be executed again. REVOKE-PENDING means that
    the new consent is minted and the old one is retired off chain, so it gives no access, but the revocation of
    its token failed. Calling execute_transition again for the old consent submits only that revocation."""
    now = _local(now or datetime.now())
    log, keep = _ledger(audit), _store(save)
    patient = consent.patient_did
    due = _due_majority(consent, now)
    base = {"algorithm": "6.3", "kind": KIND_MAJORITY, "transition_id": due[0].get("id") if due else None,
            "due": due[0].get("due") if due else None, "evaluated_at": now.isoformat(),
            "predecessor_id": consent.consent_id}

    def record(result, **evidence):
        return log(actor_did="System", actor_role="ConsentEngine", action="CAPACITY_TRANSITION", patient_did=patient,
                   consent_id=consent.consent_id, scope=consent.scope, purpose=consent.purpose, result=result,
                   metadata={**base, **evidence})

    def outcome(status, reason=None, **more):
        return {"status": status, "reason": reason, "transition_id": base["transition_id"],
                "predecessor_id": consent.consent_id, "successor_id": getattr(consent, "successor_id", None),
                "successor": None, "mint": None, "revoke": None, **more}

    def refuse(reason, **evidence):
        record("REJECTED", reason=reason, **evidence)
        return outcome(REFUSED, reason)

    def retire(new, mint_receipt):
        """Revoke the token of the old consent, close the transition and record it."""
        linked = {"successor_id": consent.successor_id, "old_token_id": consent.token_id,
                  "new_token_id": new.token_id if new is not None else None, "mint_tx": _tx(mint_receipt)[0]}
        receipt = None
        if consent.token_id:
            try:
                receipt = revoke(consent)
                if _failed(receipt):
                    raise RuntimeError("the revoke transaction failed")
            except Exception as error:
                log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_REVOKE", patient_did=patient,
                    consent_id=consent.consent_id, result="FAILED",
                    metadata={"token_id": consent.token_id, "error": str(error)[:300],
                              "capacity_transition": base["transition_id"]})
                record(REVOKE_PENDING, reason=REVOKE_FAILED, error=str(error)[:300], **linked)
                return outcome(REVOKE_PENDING, REVOKE_FAILED, successor=new, mint=mint_receipt, error=str(error)[:300])
            if _tx(receipt)[0]:
                log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_REVOKE", patient_did=patient,
                    consent_id=consent.consent_id, result="SUCCESS", tx_hash=_tx(receipt)[0],
                    block_number=_tx(receipt)[1],
                    metadata={"token_id": consent.token_id, "gas_used": receipt.get("gas_used"),
                              "capacity_transition": base["transition_id"]})
        for transition in due:
            transition["done"] = True
        keep(consent)
        record("SUCCESS", executed_at=now.isoformat(), signed_by=patient, guardians_before=list(consent.guardian_dids),
               threshold_before=consent.threshold, guardians_after=[patient], threshold_after=1,
               onchain=["mint"] + (["revoke"] if consent.token_id else []), revoke_tx=_tx(receipt)[0], **linked)
        return outcome(COMPLETED, successor=new, mint=mint_receipt, revoke=receipt)

    # A consent that has a successor was re-issued before. Either the transition is complete, or the revocation of
    # the old token is still outstanding and is submitted again.
    if getattr(consent, "successor_id", None):
        if not due:
            return refuse(ALREADY_TRANSITIONED, successor_id=consent.successor_id)
        return retire(None, None)

    if not due:
        return refuse(NO_TRANSITION_DUE)
    try:
        state = lifecycle_state(consent, now)
    except Exception:
        state = None
    ended = trigger_service.consent_ended(consent, now)
    if state is None or state in ("REVOKED", "EXPIRED") or ended:
        # no REVOKED or EXPIRED consent re-enters ACTIVE, and a re-issue would be a way around that rule
        code = ended or {"REVOKED": CONSENT_REVOKED, "EXPIRED": CONSENT_EXPIRED}.get(state, RECORD_INVALID)
        return refuse(code, state=state)
    if state == "PENDING_TOKEN":
        # the mint of the old consent may still arrive, and its token would then stay valid on chain
        return refuse(TOKEN_PENDING, state=state)
    if not ids.is_valid_did(patient):
        return refuse(PATIENT_IDENTIFIER_INVALID)

    if successor is None:
        successor = prepare_successor(consent, now)
    else:
        differing = _successor_mismatch(consent, successor, now)
        if differing:
            return refuse(SUCCESSOR_MISMATCH, fields=differing)

    # the patient signs the re-issued consent, and the signature is verified before anything is minted
    address = None
    try:
        if verify_sig is None and str(patient).startswith("did:key:"):
            # a did:key names its own key, and the default check knows only the key derived from the identifier
            raise ValueError("a did:key patient signs with the wallet that holds its key: pass the check as verify_sig")
        if signature is None:
            signature, address = (sign or ids.sign_consent)(patient, successor.consent_id)
        signed = bool((verify_sig or ids.verify_signature)(patient, successor.consent_id, signature))
    except Exception:
        signed = False
    if not signed:
        return refuse(PATIENT_SIGNATURE_INVALID, successor_id=successor.consent_id)
    address = address or (successor.guardian_addresses or {}).get(patient)
    successor.signatures = [patient]
    successor.signature_data = {patient: {"scheme": "EIP-712", "signer": address, "signature": signature}}
    successor.state = "PENDING_TOKEN"

    mint_receipt = None
    try:
        mint_receipt = mint(successor)
        successor.token_id = _token_id(mint_receipt, successor)
    except Exception as error:
        # the transaction hash, if there is one, is kept in the ledger, so that the mint can be looked up on chain
        record("FAILED", reason=MINT_FAILED, error=str(error)[:300], patient_signature_verified=True,
               mint_tx=_tx(mint_receipt)[0])
        return outcome(MINT_FAILED, MINT_FAILED, error=str(error)[:300], mint=mint_receipt)

    # Link the two consents and retire the old one. From here the old consent gives no access, whatever happens to
    # the revocation of its token.
    guardians_before, threshold_before = list(consent.guardian_dids), consent.threshold
    consent.successor_id = successor.consent_id
    consent.revoked, consent.state = True, "REVOKED"
    consent.revoked_at, consent.revoked_by = now.isoformat(), RETIRED_BY
    successor.state = _condition_state(successor, now) or "PENDING_TOKEN"
    keep(successor)
    keep(consent)
    origin = {"capacity_transition": base["transition_id"], "predecessor_id": consent.consent_id}
    log(actor_did=patient, actor_role="Patient", action="SIGN_CONSENT", patient_did=patient,
        consent_id=successor.consent_id, scope=successor.scope, purpose=successor.purpose, result="SUCCESS",
        metadata={"threshold": 1, "signature_count": 1, "scheme": "EIP-712", "guardian_address": address,
                  "signature": signature, "guardians_before": guardians_before,
                  "threshold_before": threshold_before, **origin})
    tx_hash, block_number = _tx(mint_receipt)
    if tx_hash:
        log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT", patient_did=patient,
            consent_id=successor.consent_id, scope=successor.scope, purpose=successor.purpose, result="SUCCESS",
            tx_hash=tx_hash, block_number=block_number,
            metadata={"token_id": successor.token_id, "gas_used": mint_receipt.get("gas_used"), **origin})
    else:
        log(actor_did="Blockchain", actor_role="SmartContract", action="MINT_SBT", patient_did=patient,
            consent_id=successor.consent_id, scope=successor.scope, purpose=successor.purpose,
            metadata={"token_id": successor.token_id, **origin})
    return retire(successor, mint_receipt)
