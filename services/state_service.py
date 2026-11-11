'''
# Consent State Machine for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-22, 2026-08-01, 2026-10-11, 2026-11-11
'''
from datetime import datetime
# guardian_approvals is not used below any more. It stays in this import because the interface and the tools
# have been able to import it from this module.
from services.access_service import (guardian_approvals, threshold_met, DENY_PRE_VALIDITY, DENY_POST_VALIDITY,
                                     DENY_AWAITING_TRIGGER, DENY_TRANSITION_PENDING, DENY_EXPIRED, DENY_REVOKED,
                                     DENY_APPROVAL_PENDING, DENY_TOKEN_PENDING, DENY_RECORD_INVALID,
                                     DENY_TRANSITION_NOT_PERMITTED)

# The lifecycle states of the prototype (thesis Section 6.2.4): the six states of the report and SUSPENDED,
# the state of a consent that is waiting on a conditional trigger or on a capacity transition.
LIFECYCLE_STATES = ("PENDING_SIGNATURE", "PENDING_TOKEN", "NOT_STARTED", "ACTIVE", "SUSPENDED", "EXPIRED", "REVOKED")
TERMINAL_STATES = ("EXPIRED", "REVOKED")

# Transition policy: the states that each state may move to in one step. CREATED is the label of a consent object
# before its first evaluation. A state that stays as it is makes no transition and is not listed. Revocation is
# accepted from every state that is not REVOKED already, because it only narrows access.
# Central invariant: no path of this table leads from REVOKED or EXPIRED back to ACTIVE.
TRANSITION_POLICY = {
    "CREATED": ("PENDING_SIGNATURE", "REVOKED"),
    "PENDING_SIGNATURE": ("PENDING_TOKEN", "REVOKED"),                             # the threshold N is reached
    "PENDING_TOKEN": ("NOT_STARTED", "ACTIVE", "SUSPENDED", "EXPIRED", "REVOKED"),  # the token is recorded
    "NOT_STARTED": ("ACTIVE", "SUSPENDED", "REVOKED"),                             # the window opens
    "ACTIVE": ("SUSPENDED", "EXPIRED", "REVOKED"),
    "SUSPENDED": ("ACTIVE", "EXPIRED", "REVOKED"),                                 # the trigger or the transition is met
    "EXPIRED": ("REVOKED",),                                                       # an expired consent can still be revoked
    "REVOKED": (),                                                                 # revocation is irreversible
}


def transition_allowed(old, new):
    """Transition policy check (Algorithm 6.2, lines 16 to 20): may a consent move from `old` to `new` in one step?"""
    return new in TRANSITION_POLICY.get(old, ())


def state_reachable(old, new):
    """`new` is `old` itself or can be reached from it through permitted transitions. Used to compare the recorded
    state of a consent with the state derived now, because several steps may lie between two evaluations."""
    seen, todo = {old}, [old]
    while todo:
        for s in TRANSITION_POLICY.get(todo.pop(), ()):
            if s not in seen:
                seen.add(s)
                todo.append(s)
    return new in seen


def reentry_refused(recorded, derived):
    """True when the consent was recorded as EXPIRED or REVOKED and the state derived now is one that the policy
    does not let it reach. This is the check that no REVOKED or EXPIRED consent re-enters ACTIVE."""
    return recorded in TERMINAL_STATES and not state_reachable(recorded, derived)


def _local(moment):
    # the prototype compares local times without a zone, so a time that carries a zone is converted first
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo is not None else moment


def waiting_triggers(consent):
    """Conditional triggers of the consent that are not satisfied yet (Algorithm 6.3 sets `satisfied`).
    An entry that cannot be read counts as not satisfied."""
    return [t for t in (getattr(consent, "triggers", None) or [])
            if not (isinstance(t, dict) and t.get("satisfied") is True)]


def pending_transitions(consent, now=None):
    """Capacity transitions that are due at `now` and not executed yet. An entry whose due time cannot be read
    counts as pending."""
    now = _local(now or datetime.now())
    pending = []
    for t in (getattr(consent, "transitions", None) or []):
        if isinstance(t, dict) and t.get("done") is True:
            continue
        try:
            due = _local(datetime.fromisoformat(str(t["due"]))) <= now
        except Exception:
            due = True
        if due:
            pending.append(t)
    return pending


def suspension_codes(consent, now=None):
    """The deny codes of a SUSPENDED consent: AWAITING-TRIGGER, TRANSITION-PENDING, or both."""
    codes = []
    if waiting_triggers(consent):
        codes.append(DENY_AWAITING_TRIGGER)
    if pending_transitions(consent, now):
        codes.append(DENY_TRANSITION_PENDING)
    return codes


def lifecycle_state(consent, now=None):
    """The consent's lifecycle state at `now`, without changing the consent (used by VL).
    The state is derived from the distinct approvals of members of G, the token identifier, the revocation flag,
    the triggers, the transitions and the time (thesis Section 6.4.1). SUSPENDED is the state of a consent that
    would be ACTIVE and has a trigger that is not satisfied or a transition that is due and not done.
    The state recorded in the consent (written by evaluate_state) is read as well: a consent recorded as REVOKED
    or EXPIRED keeps that state, whatever its other fields say now. A consent without triggers and transitions
    and without such a record gets the same state as before."""
    if getattr(consent, "revoked", False):
        return "REVOKED"
    recorded = getattr(consent, "state", None)
    # A consent recorded as REVOKED stays REVOKED even if its flag has been cleared, and a consent that was
    # replaced after a capacity transition (it has a successor) is retired in the same way.
    if recorded == "REVOKED" or getattr(consent, "successor_id", None):
        return "REVOKED"

    now = now or datetime.now()
    start = datetime.fromisoformat(consent.start_date)
    expiry = datetime.fromisoformat(consent.expiry_date)

    # count distinct approvals from members of G only, as in the decision function, against the threshold N (k-of-n)
    if not threshold_met(consent):
        state = "PENDING_SIGNATURE"
    elif not consent.token_id:
        state = "PENDING_TOKEN"
    elif now < start:
        state = "NOT_STARTED"
    elif now > expiry:
        state = "EXPIRED"
    elif waiting_triggers(consent) or pending_transitions(consent, now):
        # the consent would be ACTIVE, but it waits on a trigger or on a capacity transition
        state = "SUSPENDED"
    else:
        state = "ACTIVE"

    # Invariant: no REVOKED or EXPIRED consent re-enters ACTIVE. A changed window or approval list does not
    # bring an expired consent back.
    if reentry_refused(recorded, state):
        return recorded
    return state


def evaluate_state(consent, now=None):
    consent.state = lifecycle_state(consent, now)
    return consent.state


def validate_lifecycle(consent, now=None, target=None, record=None):
    """Algorithm 6.2, temporal and lifecycle validation, with the transition check of lines 16 to 20.
    target=None validates a data access, which needs the window and the ACTIVE state. target=<state> validates a
    requested transition to that state against the transition policy. The check says whether the policy has the
    step from the current state to the target. It does not make the step: the state itself is always derived by
    lifecycle_state from the approvals, the token, the triggers, the transitions and the time.
    Returns the evidence of the check as a dict with VALID, result, state, deny_code and reason, and passes it to
    `record` when one is given (a callable that writes it to the audit ledger)."""
    now = now or datetime.now()
    ev = {"consent_id": getattr(consent, "consent_id", None), "time": now.isoformat(),
          "operation": "ACCESS" if target is None else "TRANSITION", "target": target,
          "recorded_state": getattr(consent, "state", None), "state": None,
          "window": [getattr(consent, "start_date", None), getattr(consent, "expiry_date", None)],
          "revoked": bool(getattr(consent, "revoked", False)), "VALID": False, "result": "INVALID",
          "deny_code": None, "reason": None}

    def done(valid, code=None, reason=None):
        ev.update(VALID=valid, result="VALID" if valid else "INVALID", deny_code=code, reason=reason)
        if record is not None:
            record(ev)
        return ev

    # lines 1 to 5: the window. A transition is bound to the window only when it leads into ACTIVE or SUSPENDED.
    try:
        start, expiry = datetime.fromisoformat(consent.start_date), datetime.fromisoformat(consent.expiry_date)
        window_code = DENY_PRE_VALIDITY if now < start else DENY_POST_VALIDITY if now > expiry else None
        state = lifecycle_state(consent, now)
    except Exception:
        start = expiry = window_code = None
        state = "REVOKED" if getattr(consent, "revoked", False) or getattr(consent, "state", None) == "REVOKED" else None
    ev["state"] = state
    if target is not None and target not in LIFECYCLE_STATES:
        return done(False, DENY_TRANSITION_NOT_PERMITTED, f"unknown state {target}")
    if state is None and target != "REVOKED":
        return done(False, DENY_RECORD_INVALID, "the window cannot be read")
    if window_code and (target is None or target in ("ACTIVE", "SUSPENDED")):
        # precedence rule of Section 6.3.1: the state code is reported when the state has one
        code = {"REVOKED": DENY_REVOKED, "EXPIRED": DENY_EXPIRED}.get(state, window_code)
        return done(False, code, "the time is outside the validity window")
    # lines 6 to 15: the state must permit the operation, and a revoked consent permits none
    if state == "REVOKED":
        return done(False, DENY_REVOKED, "the consent is revoked")
    if target is None:
        if state == "ACTIVE":
            return done(True)
        if state == "EXPIRED":
            code = DENY_EXPIRED
        elif state == "SUSPENDED":
            code = suspension_codes(consent, now)[0]
        elif state == "PENDING_TOKEN":
            code = DENY_TOKEN_PENDING
        else:                                  # PENDING_SIGNATURE
            code = DENY_APPROVAL_PENDING
        return done(False, code, f"the state {state} does not permit data access")
    # lines 16 to 20: the requested transition against the policy. Revocation is accepted from every state that
    # is not REVOKED, also for a consent whose window cannot be read, because it only narrows access.
    if not (transition_allowed(state, target) or (state is None and target == "REVOKED")):
        return done(False, DENY_TRANSITION_NOT_PERMITTED, f"the policy does not permit {state} -> {target}")
    return done(True)
