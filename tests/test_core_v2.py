"""Core decision rule and lifecycle of the thesis design (Chapters 5 and 6): the patient-defined threshold k-of-n,
the purpose, scope and context conditions inside VP, the deny codes of Section 6.3.1 with their precedence rule,
the SUSPENDED state, the transition policy with the invariant that no REVOKED or EXPIRED consent re-enters ACTIVE,
Algorithm 6.2 with its transition check, and the trusted time source.
Every decision is evaluated at a fixed time, offline, with the demonstration keys of the test harness."""
import copy
import functools
import itertools
import random
import pytest
from datetime import date, datetime, timedelta
from models.consent import Consent
from models.access import AccessRequest
from services import access_service as acc
from services import state_service as sm
from services import time_source
from services.access_service import decision_matrix, evaluate_allow, evaluate_request, deny_code, guardian_approvals
from services.consent_service import create_consent
from services.identity_service import sign_consent, verify_signature, verify_vc, is_valid_did

NOW = datetime(2026, 11, 11, 12, 0, 0)
START, EXPIRY = (NOW - timedelta(days=1)).isoformat(), (NOW + timedelta(days=30)).isoformat()
EARLIER, LATER = (NOW - timedelta(hours=1)).isoformat(), (NOW + timedelta(days=1)).isoformat()
PATIENT, DOCTOR, OTHER_DOCTOR = "did:patient:x", "did:hospital:001", "did:hospital:002"
G = ["did:parent:A", "did:parent:B", "did:parent:C", "did:parent:D", "did:parent:E"]
TRIGGER = {"id": "t-1", "kind": "attestation", "event": "loss-of-capacity", "attester_role": "doctor",
           "satisfied": False, "attestation_id": None}
ALL_KEYS = ["VI", "VA", "VP", "VT", "VL", "ALLOW", "VU", "VS", "VX", "DENY"]


def majority(due, done=False):
    return {"id": "m-1", "kind": "majority", "due": due if isinstance(due, str) else due.isoformat(), "done": done}


def approve(c, guardian):
    sig, addr = sign_consent(guardian, c.consent_id)
    c.signatures.append(guardian); c.signature_data[guardian] = {"signer": addr, "signature": sig}


def consent(k=2, n=2, signers=None, token="SBT-1", **kw):
    """A k-of-n consent for Observation and Medication, approved by its first k guardians and anchored,
    unless `signers`, `token` or a field in `kw` says otherwise."""
    c = Consent(f"core-{k}of{n}", PATIENT, DOCTOR, G[:n], "Treatment", ["Observation", "Medication"], k,
                start_date=START, expiry_date=EXPIRY, token_id=token)
    for g in (G[:k] if signers is None else signers):
        approve(c, g)
    for name, value in kw.items():
        setattr(c, name, value)
    return c


# The credential check and the signature check give the same answer for the same arguments, so the sweeps over many
# consents and requests keep their answers instead of recovering every signer again.
CHECK_DID = functools.lru_cache(maxsize=None)(verify_vc)
CHECK_SIGNATURE = functools.lru_cache(maxsize=None)(verify_signature)


def decide(c, context="AU", now=NOW, **request):
    return decision_matrix(c, context, now=now, verify_sig=CHECK_SIGNATURE, verify_did=CHECK_DID, **request)


def state(c, now=NOW):
    return sm.lifecycle_state(c, now)


# ---------------------------------------------------------------------------
# Patient-defined threshold k-of-n (Sections 5.2.4 and 5.3.3)
# ---------------------------------------------------------------------------
def test_default_threshold_keeps_the_n_of_n_rule():
    c = create_consent(PATIENT, DOCTOR, G[:2], ["Observation"], "Treatment", START, EXPIRY)
    assert c.threshold == 2 and c.guardian_dids == G[:2] and c.state == "PENDING_SIGNATURE"
    assert c.jurisdiction == "AU" and c.patient_birth_date is None and c.token_id is None and c.signatures == []


@pytest.mark.parametrize("k,n", [(2, 2), (2, 3), (3, 5), (1, 3)])
def test_k_of_n_consent_is_issued_by_the_kth_distinct_approval(k, n):
    c = create_consent(PATIENT, DOCTOR, G[:n], ["Observation", "Medication"], "Treatment", START, EXPIRY, threshold=k)
    assert c.threshold == k and len(c.guardian_dids) == n
    for count, guardian in enumerate(G[n - k:n], start=1):            # any k members of G, here the last k
        assert state(c) == "PENDING_SIGNATURE" and decide(c)["VA"] is False
        approve(c, guardian)
        assert len(guardian_approvals(c)) == count
    assert state(c) == "PENDING_TOKEN" and decide(c)["VA"] is False   # threshold met, token not recorded yet
    c.token_id = "SBT-7"
    assert sm.evaluate_state(c, NOW) == "ACTIVE"
    m = decide(c, request_purpose="Treatment", request_scope=["Observation"])
    assert m["VA"] is True and m["ALLOW"] is True and m["DENY"] == []


def test_approval_beyond_the_threshold_changes_nothing():
    c = consent(k=2, n=3); approve(c, G[2])
    assert len(guardian_approvals(c)) == 3 and state(c) == "ACTIVE" and decide(c)["ALLOW"] is True


def test_k_of_n_counts_only_distinct_members_of_G():
    # A1 and A3 for a 2-of-3 consent: one member, a signer outside G with a valid signature, and the member again
    c = consent(k=2, n=3, signers=[G[0]])
    approve(c, "did:parent:Z")
    c.signatures.append(G[0])
    m = decide(c)
    assert guardian_approvals(c) == {G[0]} and m["VI"] is True and m["VA"] is False and m["ALLOW"] is False
    assert state(c) == "PENDING_SIGNATURE" and m["DENY"] == ["APPROVAL-PENDING"]
    approve(c, G[2])                                                  # a second member of G reaches the threshold
    assert guardian_approvals(c) == {G[0], G[2]} and decide(c)["ALLOW"] is True


@pytest.mark.parametrize("bad", [0, -1, 4, "2", 2.0, True])
def test_threshold_outside_the_range_is_rejected_at_creation(bad):
    with pytest.raises(ValueError):
        create_consent(PATIENT, DOCTOR, G[:3], ["Observation"], "Treatment", START, EXPIRY, threshold=bad)


@pytest.mark.parametrize("guardians", [[], [G[0], G[0]], [G[0], G[1], G[0]], "did:parent:A", None])
def test_empty_or_duplicated_guardian_set_is_rejected(guardians):
    with pytest.raises(ValueError):
        create_consent(PATIENT, DOCTOR, guardians, ["Observation"], "Treatment", START, EXPIRY)
    with pytest.raises(ValueError):
        create_consent(PATIENT, DOCTOR, guardians, ["Observation"], "Treatment", START, EXPIRY, threshold=1)


def test_threshold_outside_the_range_never_satisfies_VA():
    # A record with N = 0 would be met by no approval at all, and one valid signature from outside G satisfies VI.
    c = consent(k=0, n=2, signers=["did:parent:Z"])
    m = decide(c)
    assert m["VI"] is True and m["VA"] is False and m["VL"] is False and m["ALLOW"] is False
    assert state(c) == "PENDING_SIGNATURE" and m["DENY"] == ["APPROVAL-PENDING"]
    for k in (3, -1, None, "2", True):                                # every guardian approved, N is not in 1..|G|
        c = consent(); c.threshold = k
        assert acc.threshold_valid(c) is False and decide(c)["VA"] is False and state(c) == "PENDING_SIGNATURE"
    assert acc.threshold_valid(consent(k=1, n=3)) and acc.threshold_valid(consent(k=3, n=3))


def test_context_and_birth_date_are_recorded_at_creation():
    c = create_consent(PATIENT, DOCTOR, G[:3], ["Observation"], "Treatment", START, EXPIRY, threshold=2,
                       context="SA", patient_birth_date="2008-11-20")
    assert c.jurisdiction == "SA" and c.patient_birth_date == "2008-11-20" and c.majority_age == 18
    for born in (date(2008, 11, 20), datetime(2008, 11, 20, 9, 30), "2008-11-20T09:30:00"):   # stored as the date
        c = create_consent(PATIENT, DOCTOR, G[:1], ["Observation"], "Treatment", START, EXPIRY, patient_birth_date=born)
        assert c.patient_birth_date == "2008-11-20" and c.threshold == 1
    for bad in ("", "au", "AUS", "A1", 61):
        with pytest.raises(ValueError):
            create_consent(PATIENT, DOCTOR, G[:2], ["Observation"], "Treatment", START, EXPIRY, context=bad)
    for bad in ("20 November 2008", "2008-13-40", "", 20081120):
        with pytest.raises(ValueError):
            create_consent(PATIENT, DOCTOR, G[:2], ["Observation"], "Treatment", START, EXPIRY, patient_birth_date=bad)


# ---------------------------------------------------------------------------
# Decision rule: VU, VS and VX inside VP, and the deny codes (Sections 6.2.2, 6.3.1 and 6.3.2)
# ---------------------------------------------------------------------------
def test_call_without_request_arguments_returns_the_six_keys_of_the_report():
    variants = [{}, {"revoked": True}, {"token": None}, {"start_date": LATER}, {"expiry_date": EARLIER},
                {"jurisdiction": "SA"}, {"purpose": "Marketing"}, {"signers": [G[0]]}, {"triggers": [dict(TRIGGER)]}]
    for kw in variants:
        old = evaluate_allow(consent(**kw), "AU", now=NOW, verify_sig=verify_signature, verify_did=verify_vc)
        assert list(old) == ["VI", "VA", "VP", "VT", "VL", "ALLOW"] and all(isinstance(v, bool) for v in old.values())
        full = decide(consent(**kw))
        assert list(full) == ALL_KEYS and {key: full[key] for key in old} == old
        assert tuple(old) == acc.MATRIX_KEYS and tuple(full) == acc.MATRIX_KEYS_FULL
    assert all(evaluate_allow(consent(), "AU", now=NOW).values())      # the default call of the offline tools


def test_request_inside_the_consent_is_allowed_with_no_deny_code():
    m = evaluate_allow(consent(), "AU", now=NOW, verify_sig=verify_signature, verify_did=verify_vc,
                       request_purpose="Treatment", request_scope=["Observation", "Medication"])
    assert m == {"VI": True, "VA": True, "VP": True, "VT": True, "VL": True, "ALLOW": True,
                 "VU": True, "VS": True, "VX": True, "DENY": []}
    for scope in (["Observation"], ("Medication",), {"Observation", "Medication"}):
        assert decide(consent(), request_scope=scope)["ALLOW"] is True


def test_declared_purpose_must_equal_the_consent_purpose():
    m = decide(consent(), request_purpose="Research", request_scope=["Observation"])
    assert m["VU"] is False and m["VS"] is True and m["VX"] is True and m["VP"] is False and m["ALLOW"] is False
    assert m["DENY"] == ["PURPOSE-MISMATCH"] and deny_code(m) == "PURPOSE-MISMATCH"
    assert evaluate_allow(consent(), "AU", now=NOW, request_purpose="treatment")["DENY"] == ["PURPOSE-MISMATCH"]
    # a consent purpose outside the supported vocabulary is compatible with no request
    m = decide(consent(purpose="Marketing"), request_purpose="Marketing")
    assert m["VU"] is False and m["DENY"] == ["PURPOSE-MISMATCH"]


def test_requested_scope_must_be_non_empty_and_inside_the_consented_scope():
    # Observation and Medication consented, Observation, Medication and Procedure requested (A4)
    m = decide(consent(), request_purpose="Treatment", request_scope=["Observation", "Medication", "Procedure"])
    assert m["VS"] is False and m["VU"] is True and m["VP"] is False and m["ALLOW"] is False
    assert m["DENY"] == ["OUT-OF-SCOPE"]
    m = decide(consent(), request_scope=[])                            # A5, now refused by the decision function
    assert m["VS"] is False and m["ALLOW"] is False and m["DENY"] == ["OUT-OF-SCOPE"]
    for malformed in ("Observation", {"Observation": True}, 7, [["Observation"]]):
        m = decide(consent(), request_scope=malformed)
        assert m["VS"] is False and m["ALLOW"] is False and m["DENY"] == ["OUT-OF-SCOPE"]


def test_request_context_must_match_the_consent_context():
    m = decide(consent(), "US", request_purpose="Treatment", request_scope=["Observation"])
    assert m["VX"] is False and m["VP"] is False and m["VL"] is True and m["ALLOW"] is False
    assert m["DENY"] == ["CONTEXT-MISMATCH"]
    c = consent(jurisdiction="SA")
    assert decide(c, "SA")["ALLOW"] is True and decide(c, "AU")["DENY"] == ["CONTEXT-MISMATCH"]


@pytest.mark.parametrize("purpose_ok,scope_ok,context_ok", list(itertools.product([True, False], repeat=3)))
def test_VP_is_the_conjunction_of_purpose_scope_and_context(purpose_ok, scope_ok, context_ok):
    m = decide(consent(), "AU" if context_ok else "GB",
               request_purpose="Treatment" if purpose_ok else "Emergency",
               request_scope=["Medication"] if scope_ok else ["Condition"])
    assert (m["VU"], m["VS"], m["VX"]) == (purpose_ok, scope_ok, context_ok)
    assert m["VP"] is (purpose_ok and scope_ok and context_ok) and m["ALLOW"] is m["VP"]
    expected = [code for ok, code in ((purpose_ok, "PURPOSE-MISMATCH"), (context_ok, "CONTEXT-MISMATCH"),
                                      (scope_ok, "OUT-OF-SCOPE")) if not ok]
    assert m["DENY"] == expected


def test_window_codes_and_the_precedence_of_the_state_code():
    early = consent(start_date=LATER)
    m = decide(early)
    assert state(early) == "NOT_STARTED" and m["VT"] is False and m["VL"] is False and m["DENY"] == ["PRE-VALIDITY"]
    # Once the window of an issued consent has passed, VT and VL both fail and the state code is the one reported.
    late = consent(expiry_date=EARLIER)
    m = decide(late)
    assert state(late) == "EXPIRED" and m["VT"] is False and m["VL"] is False and m["DENY"] == ["EXPIRED"]
    # A consent that was never issued has no state code, so the window code is reported.
    never_issued = consent(signers=[G[0]], expiry_date=EARLIER)
    m = decide(never_issued)
    assert state(never_issued) == "PENDING_SIGNATURE" and m["VT"] is False
    assert m["DENY"] == ["POST-VALIDITY", "APPROVAL-PENDING"] and deny_code(m) == "POST-VALIDITY"
    assert decide(consent(revoked=True, start_date=LATER))["DENY"] == ["REVOKED"]
    assert decide(consent(revoked=True, expiry_date=EARLIER))["DENY"] == ["REVOKED"]


def test_every_deny_code_of_section_6_3_1_is_reached():
    reached = {
        "OUT-OF-SCOPE": decide(consent(), request_scope=["Procedure"]),
        "PURPOSE-MISMATCH": decide(consent(), request_purpose="Research"),
        "CONTEXT-MISMATCH": decide(consent(), "GB"),
        "PRE-VALIDITY": decide(consent(start_date=LATER)),
        "POST-VALIDITY": decide(consent(token=None, expiry_date=EARLIER)),
        "AWAITING-TRIGGER": decide(consent(triggers=[dict(TRIGGER)])),
        "TRANSITION-PENDING": decide(consent(transitions=[majority(EARLIER)])),
        "EXPIRED": decide(consent(expiry_date=EARLIER)),
        "REVOKED": decide(consent(revoked=True)),
    }
    for code, m in reached.items():
        assert m["ALLOW"] is False and deny_code(m) == code and code in m["DENY"]
    assert tuple(reached) == acc.DENY_CODES and len(acc.DENY_CODES) == 9
    # each code is tied to the check it reports
    checks = {code: acc.DENY_CODE_CHECK[code][0] for code in acc.DENY_CODES}
    assert [checks[c] for c in acc.DENY_CODES] == ["VP", "VP", "VP", "VT", "VT", "VL", "VL", "VL", "VL"]
    assert set(acc.DENY_CODE_CHECK) == set(acc.DENY_CODES) | set(acc.DENY_CODES_OTHER)
    for code, m in reached.items():
        assert m[checks[code]] is False


def test_a_denied_request_always_carries_a_code_and_an_allowed_one_never():
    consents = [{}, {"revoked": True}, {"token": None}, {"signers": [G[0]]}, {"signers": []}, {"start_date": LATER},
                {"expiry_date": EARLIER}, {"start_date": "not a date"}, {"purpose": "Marketing"}, {"jurisdiction": ""},
                {"triggers": [dict(TRIGGER)]}, {"transitions": [majority(EARLIER)]}, {"k": 0}, {"successor_id": "next"},
                {"state": "EXPIRED"}, {"state": "REVOKED"}, {"expiry_date": EARLIER, "revoked": True}]
    requests = [{}, {"request_purpose": "Treatment", "request_scope": ["Observation"]}, {"request_purpose": "Research"},
                {"request_scope": []}, {"request_scope": ["Procedure"]}, {"requester_did": OTHER_DOCTOR}]
    known = set(acc.DENY_CODES) | set(acc.DENY_CODES_OTHER)
    allowed = 0
    for kw, request, context in itertools.product(consents, requests, ("AU", "US")):
        m = decide(consent(**kw), context, **request)
        assert m["ALLOW"] is (m["VI"] and m["VA"] and m["VP"] and m["VT"] and m["VL"])
        assert m["VP"] is (m["VU"] and m["VS"] and m["VX"])
        assert (m["DENY"] == []) is m["ALLOW"], (kw, request, context, m)
        assert set(m["DENY"]) <= known and len(set(m["DENY"])) == len(m["DENY"])
        for code in m["DENY"]:                                         # every code names a predicate that failed
            assert m[acc.DENY_CODE_CHECK[code][0]] is False, (kw, request, context, m)
        allowed += m["ALLOW"]
    # The two requests that fit are allowed for the unchanged consent in its own context, and for the consent
    # without a context in both contexts: 2 + 4.
    assert allowed == 6


def test_a_state_without_a_code_still_gives_a_reason(monkeypatch):
    monkeypatch.setattr(sm, "lifecycle_state", lambda consent, now=None: "FROZEN")
    m = decide(consent())
    assert m["VL"] is False and m["ALLOW"] is False and m["DENY"] == ["RECORD-INVALID"]


def test_registrar_request_is_denied_on_identity_and_on_policy():
    # Case study, Event 1: the named clinician requests Observation and Medication for treatment.
    r = AccessRequest(DOCTOR, PATIENT, ["Observation", "Medication"], "Treatment", "2020-01-01T00:00:00")
    m = evaluate_request(consent(), r, "AU", now=NOW, verify_sig=verify_signature, verify_did=verify_vc)
    assert m["ALLOW"] is True and m["VT"] is True       # the time is `now`, not the request_time the requester wrote
    # Event 2: another requester asks for Procedure records for a study. The matrix records both failures.
    r = AccessRequest(OTHER_DOCTOR, PATIENT, ["Procedure"], "Research", NOW.isoformat())
    m = evaluate_request(consent(), r, "AU", now=NOW, verify_sig=verify_signature, verify_did=verify_vc)
    assert m["VI"] is False and m["VP"] is False and m["VA"] and m["VT"] and m["VL"] and m["ALLOW"] is False
    assert m["DENY"] == ["IDENTITY-INVALID", "PURPOSE-MISMATCH", "OUT-OF-SCOPE"]
    assert deny_code(m) == "PURPOSE-MISMATCH"           # the policy reason of the denial


def test_failures_of_VI_and_VA_have_codes_outside_the_nine():
    m = decide(consent(), requester_did=OTHER_DOCTOR)
    assert m["VI"] is False and m["DENY"] == ["IDENTITY-INVALID"] and deny_code(m) == "IDENTITY-INVALID"
    m = decide(consent(signers=[G[0]]))                                # PENDING_SIGNATURE: the threshold is not met
    assert m["VA"] is False and m["VL"] is False and m["DENY"] == ["APPROVAL-PENDING"]
    m = decide(consent(token=None))                                    # PENDING_TOKEN: met, and no token recorded
    assert m["VA"] is False and state(consent(token=None)) == "PENDING_TOKEN" and m["DENY"] == ["TOKEN-PENDING"]
    m = decide(consent(token=None, expiry_date=EARLIER))
    assert m["DENY"] == ["POST-VALIDITY", "TOKEN-PENDING"] and deny_code(m) == "POST-VALIDITY"
    m = decide(consent(start_date="not a date"))
    assert m["VT"] is False and m["VL"] is False and m["DENY"] == ["RECORD-INVALID"]
    assert not set(acc.DENY_CODES) & set(acc.DENY_CODES_OTHER)
    assert deny_code([]) is None and deny_code({"DENY": []}) is None
    assert deny_code(["IDENTITY-INVALID", "REVOKED", "PURPOSE-MISMATCH"]) == "REVOKED"


def test_request_must_state_its_requester_purpose_scope_and_patient():
    def ask(**change):
        fields = {"doctor_did": DOCTOR, "patient_did": PATIENT, "scope": ["Observation"], "purpose": "Treatment",
                  "request_time": NOW.isoformat()}
        fields.update(change)
        return evaluate_request(consent(), AccessRequest(**fields), "AU", now=NOW, verify_sig=verify_signature,
                                verify_did=verify_vc)
    assert ask()["ALLOW"] is True and ask()["DENY"] == []
    # a field that the request leaves out is not skipped, it fails its check
    assert ask(purpose=None)["DENY"] == ["PURPOSE-MISMATCH"] and ask(purpose="")["DENY"] == ["PURPOSE-MISMATCH"]
    assert ask(scope=None)["DENY"] == ["OUT-OF-SCOPE"] and ask(scope=[])["DENY"] == ["OUT-OF-SCOPE"]
    m = ask(doctor_did=None)
    assert m["VI"] is False and m["ALLOW"] is False and m["DENY"] == ["IDENTITY-INVALID"]
    # a request for another patient is not a request under this consent
    m = ask(patient_did="did:patient:y")
    assert m["VI"] is False and m["VP"] is True and m["ALLOW"] is False and m["DENY"] == ["IDENTITY-INVALID"]
    assert ask(patient_did=None)["ALLOW"] is False
    m = ask(patient_did="did:patient:y", doctor_did=OTHER_DOCTOR, scope=["Procedure"])
    assert m["DENY"] == ["IDENTITY-INVALID", "OUT-OF-SCOPE"]


def test_VA_over_the_approvals_alone_leaves_the_token_and_the_revocation_to_VL():
    # Thesis Section 3.2.8: VA is defined over the distinct approvals of members of G, and the token and
    # revocation conditions that the report evaluates inside VA belong to VL.
    def both(c, context="AU", **request):
        return decide(c, context, **request), decide(c, context, va_approvals_only=True, **request)
    report, thesis = both(consent(revoked=True))
    assert report["VA"] is False and thesis["VA"] is True and report["VL"] is False and thesis["VL"] is False
    assert report["DENY"] == thesis["DENY"] == ["REVOKED"]
    report, thesis = both(consent(token=None))
    assert report["VA"] is False and thesis["VA"] is True and thesis["VL"] is False
    assert report["DENY"] == thesis["DENY"] == ["TOKEN-PENDING"]
    report, thesis = both(consent(k=2, n=3, signers=[G[0]]))
    assert report["VA"] is False and thesis["VA"] is False and thesis["DENY"] == ["APPROVAL-PENDING"]
    # The decision, the other predicates and the codes are the same in both forms.
    consents = [{}, {"revoked": True}, {"token": None}, {"signers": [G[0]]}, {"k": 2, "n": 3}, {"k": 0},
                {"token": None, "revoked": True}, {"signers": [], "revoked": True}, {"expiry_date": EARLIER},
                {"start_date": LATER, "token": None}, {"triggers": [dict(TRIGGER)]}, {"state": "REVOKED"},
                {"successor_id": "core-next"}, {"start_date": "not a date"}]
    requests = [{}, {"request_purpose": "Research", "request_scope": ["Procedure"]}, {"requester_did": OTHER_DOCTOR}]
    for kw, request, context in itertools.product(consents, requests, ("AU", "US")):
        report, thesis = both(consent(**kw), context, **request)
        assert {k: v for k, v in report.items() if k != "VA"} == {k: v for k, v in thesis.items() if k != "VA"}
        assert thesis["VA"] is acc.threshold_met(consent(**kw))
        assert (thesis["VA"] is False) is ("APPROVAL-PENDING" in thesis["DENY"])   # a failed VA has its own code
        assert thesis["ALLOW"] is (thesis["VI"] and thesis["VA"] and thesis["VP"] and thesis["VT"] and thesis["VL"])
    six = evaluate_allow(consent(revoked=True), "AU", now=NOW, va_approvals_only=True)
    assert six == {"VI": True, "VA": True, "VP": True, "VT": True, "VL": False, "ALLOW": False}
    r = AccessRequest(DOCTOR, PATIENT, ["Observation"], "Treatment", NOW.isoformat())
    m = evaluate_request(consent(revoked=True), r, "AU", now=NOW, va_approvals_only=True)
    assert m["VA"] is True and m["VL"] is False and m["DENY"] == ["REVOKED"]


def report_rule(c, context, now, requester, check_did, check_signature):
    """The decision rule and the state derivation of the report, written out again as the reference against which
    the default call of evaluate_allow is compared."""
    approvals = {g for g in c.signatures if g in c.guardian_dids}
    requester = c.requester_did if requester is None else requester
    vi = (check_did(requester, role="doctor", now=now) and requester == c.requester_did and is_valid_did(c.patient_did)
          and len(c.signatures) > 0)
    if check_signature is not None:
        vi = vi and all(g in c.signature_data and check_signature(g, c.consent_id, c.signature_data[g].get("signature"))
                        for g in c.signatures)
    va = len(approvals) >= c.threshold and bool(c.token_id) and not c.revoked
    vp = c.purpose in {"Treatment", "Research", "Emergency"} and (c.jurisdiction or "") in ("", context)
    start, expiry = datetime.fromisoformat(c.start_date), datetime.fromisoformat(c.expiry_date)
    vt = start <= now <= expiry
    if c.revoked:
        derived = "REVOKED"
    elif len(approvals) < c.threshold:
        derived = "PENDING_SIGNATURE"
    elif not c.token_id:
        derived = "PENDING_TOKEN"
    elif now < start:
        derived = "NOT_STARTED"
    elif now > expiry:
        derived = "EXPIRED"
    else:
        derived = "ACTIVE"
    vl = derived == "ACTIVE"
    return {"VI": vi, "VA": va, "VP": vp, "VT": vt, "VL": vl, "ALLOW": vi and va and vp and vt and vl}, derived


def test_default_call_gives_the_matrix_and_the_state_of_the_report():
    # Every consent that the report could describe (no trigger, no transition, a threshold in 1..|G|, no record of
    # an ended consent) gets the same six values and the same state as before, at every time and for every requester.
    check_did, check_signature = CHECK_DID, CHECK_SIGNATURE
    outsider = consent(signers=[G[0]])
    approve(outsider, "did:parent:Z")
    twice = consent(signers=[G[0]])
    twice.signatures.append(G[0])
    forged = consent()
    forged.signature_data[G[1]] = dict(forged.signature_data[G[0]])
    consents = [consent(), consent(state="ACTIVE"), consent(state="PENDING_SIGNATURE"), consent(revoked=True),
                consent(revoked=True, state="REVOKED"), consent(token=None), consent(token=""), consent(signers=[G[0]]),
                consent(signers=[]), outsider, twice, forged, consent(k=1, n=2, signers=[G[1]]), consent(k=2, n=3),
                consent(k=3, n=5, signers=[G[4], G[0], G[2]]), consent(k=3, n=5, signers=[G[4], G[0]]),
                consent(purpose="Marketing"), consent(purpose="Research"), consent(jurisdiction="SA"),
                consent(jurisdiction=""), consent(jurisdiction=None), consent(patient_did="patient-x"),
                consent(requester_did="did:hospital:999"), consent(requester_did=OTHER_DOCTOR),
                consent(token=None, revoked=True), consent(start_date=LATER, expiry_date=EXPIRY),
                consent(start_date=START, expiry_date=EARLIER)]
    times = [NOW - timedelta(days=2), NOW, NOW + timedelta(days=31)]
    compared = 0
    for c, context, now, requester in itertools.product(consents, ("AU", "SA", "US"), times, (None, DOCTOR, OTHER_DOCTOR)):
        for sig in (check_signature, None):
            expected, expected_state = report_rule(c, context, now, requester, check_did, sig)
            got = evaluate_allow(c, context, now=now, verify_sig=sig, verify_did=check_did, requester_did=requester)
            assert got == expected and list(got) == list(expected), (c, context, now, requester)
            assert sm.lifecycle_state(c, now) == expected_state
            compared += 1
    assert compared == len(consents) * 3 * 3 * 3 * 2
    # the call with no checker uses the credential check, as before
    assert evaluate_allow(consent(), "AU", now=NOW) == report_rule(consent(), "AU", NOW, None, verify_vc, None)[0]
    assert evaluate_allow(consent(requester_did="did:hospital:999"), "AU", now=NOW)["VI"] is False


# ---------------------------------------------------------------------------
# Lifecycle: SUSPENDED, the transition policy and the invariant (Sections 6.2.3, 6.2.4, 6.3.3 and 6.4.1)
# ---------------------------------------------------------------------------
def test_existing_states_are_derived_as_before():
    assert state(consent(signers=[G[0]])) == "PENDING_SIGNATURE"
    assert state(consent(token=None)) == "PENDING_TOKEN"
    assert state(consent(start_date=LATER)) == "NOT_STARTED"
    assert state(consent()) == "ACTIVE"
    assert state(consent(expiry_date=EARLIER)) == "EXPIRED"
    assert state(consent(revoked=True)) == "REVOKED"
    assert set(sm.LIFECYCLE_STATES) == {"PENDING_SIGNATURE", "PENDING_TOKEN", "NOT_STARTED", "ACTIVE", "SUSPENDED",
                                        "EXPIRED", "REVOKED"}


def test_consent_waiting_on_a_trigger_is_SUSPENDED():
    c = consent(triggers=[dict(TRIGGER)])
    assert state(c) == "SUSPENDED" and sm.waiting_triggers(c) == c.triggers
    m = decide(c, request_purpose="Treatment", request_scope=["Observation"])
    assert m["VI"] and m["VA"] and m["VP"] and m["VT"] and m["VL"] is False and m["ALLOW"] is False
    assert m["DENY"] == ["AWAITING-TRIGGER"]
    assert acc.authorize(state(c), True, True) is False
    c.triggers[0].update(satisfied=True, attestation_id="att-1")       # the attested event is presented
    assert state(c) == "ACTIVE" and sm.waiting_triggers(c) == []
    assert decide(c, request_purpose="Treatment", request_scope=["Observation"])["ALLOW"] is True


def test_consent_with_a_due_transition_is_SUSPENDED():
    c = consent(transitions=[majority(NOW)])                           # the patient reaches majority at NOW
    before = NOW - timedelta(seconds=1)
    assert state(c, before) == "ACTIVE" and decide(c, now=before)["ALLOW"] is True
    assert state(c) == "SUSPENDED" and sm.pending_transitions(c, NOW) == c.transitions
    m = decide(c)
    assert m["VL"] is False and m["VT"] is True and m["ALLOW"] is False and m["DENY"] == ["TRANSITION-PENDING"]
    c.transitions[0]["done"] = True
    assert state(c) == "ACTIVE" and sm.pending_transitions(c, NOW) == []
    # a due time written with a zone is read as the same moment
    zoned = consent(transitions=[majority(NOW.astimezone().isoformat())])
    assert state(zoned, before) == "ACTIVE" and state(zoned) == "SUSPENDED"


def test_trigger_and_transition_together_report_both_codes():
    c = consent(triggers=[dict(TRIGGER)], transitions=[majority(EARLIER)])
    assert state(c) == "SUSPENDED" and sm.suspension_codes(c, NOW) == ["AWAITING-TRIGGER", "TRANSITION-PENDING"]
    m = decide(c)
    assert m["DENY"] == ["AWAITING-TRIGGER", "TRANSITION-PENDING"] and deny_code(m) == "AWAITING-TRIGGER"


def test_SUSPENDED_only_takes_the_place_of_ACTIVE():
    waiting = {"triggers": [dict(TRIGGER)], "transitions": [majority(EARLIER)]}
    assert state(consent(signers=[G[0]], **waiting)) == "PENDING_SIGNATURE"
    assert state(consent(token=None, **waiting)) == "PENDING_TOKEN"
    assert state(consent(start_date=LATER, **waiting)) == "NOT_STARTED"
    assert state(consent(expiry_date=EARLIER, **waiting)) == "EXPIRED"
    assert state(consent(revoked=True, **waiting)) == "REVOKED"
    assert state(consent(**waiting)) == "SUSPENDED"


def test_unreadable_trigger_or_transition_keeps_the_consent_suspended():
    for bad in ("satisfied", {"satisfied": "yes"}, {"satisfied": 1}, {}, None):
        assert state(consent(triggers=[dict(TRIGGER, satisfied=True), bad])) == "SUSPENDED"
    for bad in ({"due": "soon", "done": False}, {"done": False}, "majority", {"due": EARLIER, "done": "yes"}):
        assert state(consent(transitions=[bad])) == "SUSPENDED"
    assert state(consent(triggers=[dict(TRIGGER, satisfied=True)], transitions=[majority(LATER)])) == "ACTIVE"


def test_transition_policy_table():
    permitted = [("CREATED", "PENDING_SIGNATURE"), ("CREATED", "REVOKED"), ("PENDING_SIGNATURE", "PENDING_TOKEN"),
                 ("PENDING_TOKEN", "ACTIVE"),
                 ("PENDING_TOKEN", "NOT_STARTED"), ("NOT_STARTED", "ACTIVE"), ("NOT_STARTED", "SUSPENDED"),
                 ("ACTIVE", "SUSPENDED"), ("SUSPENDED", "ACTIVE"), ("ACTIVE", "EXPIRED"), ("SUSPENDED", "EXPIRED"),
                 ("PENDING_SIGNATURE", "REVOKED"), ("ACTIVE", "REVOKED"), ("SUSPENDED", "REVOKED"), ("EXPIRED", "REVOKED")]
    refused = [("REVOKED", "ACTIVE"), ("EXPIRED", "ACTIVE"), ("REVOKED", "SUSPENDED"), ("EXPIRED", "SUSPENDED"),
               ("REVOKED", "EXPIRED"), ("REVOKED", "REVOKED"), ("EXPIRED", "NOT_STARTED"), ("ACTIVE", "PENDING_SIGNATURE"),
               ("ACTIVE", "NOT_STARTED"), ("ACTIVE", "ACTIVE"), ("PENDING_SIGNATURE", "ACTIVE"), ("ACTIVE", "FROZEN"),
               ("FROZEN", "ACTIVE"), (None, "ACTIVE")]
    for old, new in permitted:
        assert sm.transition_allowed(old, new) is True, (old, new)
    for old, new in refused:
        assert sm.transition_allowed(old, new) is False, (old, new)
    assert set(sm.LIFECYCLE_STATES) <= set(sm.TRANSITION_POLICY) and sm.TRANSITION_POLICY["REVOKED"] == ()
    assert all(new in sm.LIFECYCLE_STATES for targets in sm.TRANSITION_POLICY.values() for new in targets)
    assert all(sm.transition_allowed(s, "REVOKED") for s in sm.TRANSITION_POLICY if s != "REVOKED")


def test_no_path_of_the_policy_leads_from_REVOKED_or_EXPIRED_back_to_ACTIVE():
    def reach(old):
        return {s for s in sm.LIFECYCLE_STATES if sm.state_reachable(old, s)}
    assert reach("REVOKED") == {"REVOKED"} and reach("EXPIRED") == {"EXPIRED", "REVOKED"}
    for dead in sm.TERMINAL_STATES:
        assert "ACTIVE" not in reach(dead) and "SUSPENDED" not in reach(dead)
        assert sm.reentry_refused(dead, "ACTIVE") is True and sm.reentry_refused(dead, "REVOKED") is False
    # the states before the end still lead to ACTIVE, through the steps between them
    for alive in ("CREATED", "PENDING_SIGNATURE", "PENDING_TOKEN", "NOT_STARTED", "SUSPENDED"):
        assert sm.state_reachable(alive, "ACTIVE") and sm.reentry_refused(alive, "ACTIVE") is False
    assert sm.state_reachable("PENDING_SIGNATURE", "ACTIVE") and not sm.transition_allowed("PENDING_SIGNATURE", "ACTIVE")


def test_revoked_consent_does_not_re_enter_ACTIVE():
    c = consent()
    assert sm.evaluate_state(c, NOW) == "ACTIVE"
    c.revoked = True
    assert sm.evaluate_state(c, NOW) == "REVOKED" and c.state == "REVOKED"
    c.revoked = False                                                  # the flag is cleared in the record
    assert state(c) == "REVOKED" and sm.evaluate_state(c, NOW) == "REVOKED"
    m = decide(c, request_purpose="Treatment", request_scope=["Observation"])
    assert m["VI"] and m["VA"] and m["VP"] and m["VT"] and m["VL"] is False and m["ALLOW"] is False
    assert m["DENY"] == ["REVOKED"]
    assert state(consent()) == "ACTIVE"                                # control: the same facts with no REVOKED record


def test_expired_consent_does_not_re_enter_ACTIVE():
    c = consent(expiry_date=EARLIER)
    assert sm.evaluate_state(c, NOW) == "EXPIRED" and c.state == "EXPIRED"
    c.expiry_date = EXPIRY                                             # the window is extended in the record
    assert state(c) == "EXPIRED" and sm.evaluate_state(c, NOW) == "EXPIRED"
    m = decide(c, request_purpose="Treatment", request_scope=["Observation"])
    assert m["VI"] and m["VA"] and m["VP"] and m["VT"] and m["VL"] is False and m["ALLOW"] is False
    assert m["DENY"] == ["EXPIRED"]
    c.start_date = LATER                                               # nor does a window moved into the future
    assert state(c) == "EXPIRED" and decide(c)["DENY"] == ["EXPIRED"]
    c.signatures = []                                                  # nor a cleared approval list
    assert state(c) == "EXPIRED"
    c.revoked = True                                                   # an expired consent can still be revoked
    assert sm.evaluate_state(c, NOW) == "REVOKED"
    assert state(consent(expiry_date=EXPIRY)) == "ACTIVE"              # control: the same window with no EXPIRED record


def test_consent_replaced_after_a_capacity_transition_is_retired():
    c = consent(successor_id="core-next", transitions=[majority(EARLIER, done=True)])
    m = decide(c)
    assert state(c) == "REVOKED" and m["VL"] is False and m["ALLOW"] is False and m["DENY"] == ["REVOKED"]


def test_no_history_of_changes_brings_a_REVOKED_or_EXPIRED_consent_back():
    # The invariant over many recorded histories: the record of a consent is changed in every way that the
    # application or a later package could change it, the clock is moved forwards and backwards, and the state is
    # recorded after each change. Once a consent has been recorded as REVOKED or EXPIRED it never becomes ACTIVE
    # or SUSPENDED again, and no request is allowed. The sequence is fixed by the seed.
    rng = random.Random(20261111)
    changes = [
        lambda c: setattr(c, "revoked", True), lambda c: setattr(c, "revoked", False),
        lambda c: setattr(c, "expiry_date", EARLIER), lambda c: setattr(c, "expiry_date", EXPIRY),
        lambda c: setattr(c, "expiry_date", (NOW + timedelta(days=365)).isoformat()),
        lambda c: setattr(c, "start_date", LATER), lambda c: setattr(c, "start_date", START),
        lambda c: setattr(c, "signatures", []), lambda c: setattr(c, "signatures", list(c.guardian_dids)),
        lambda c: setattr(c, "token_id", None), lambda c: setattr(c, "token_id", "SBT-9"),
        lambda c: setattr(c, "threshold", 1), lambda c: setattr(c, "threshold", 2),
        lambda c: c.triggers.append(dict(TRIGGER)), lambda c: [t.update(satisfied=True) for t in c.triggers],
        lambda c: c.transitions.append(majority(EARLIER)), lambda c: [t.update(done=True) for t in c.transitions],
        lambda c: setattr(c, "successor_id", "core-next"), lambda c: setattr(c, "successor_id", None),
        lambda c: setattr(c, "jurisdiction", "AU"), lambda c: None, lambda c: None, lambda c: None,
    ]
    times = [NOW - timedelta(days=2), NOW - timedelta(minutes=30), NOW, NOW + timedelta(days=31), NOW + timedelta(days=400)]

    def syntax_only(did, role=None, now=None):
        return is_valid_did(did)
    base, seen, ended_then_checked = consent(), set(), 0
    for _ in range(300):
        c = copy.deepcopy(base)
        for _ in range(40):
            before = c.state
            rng.choice(changes)(c)
            now = rng.choice(times)
            after = sm.evaluate_state(c, now)
            seen.add(after)
            assert after in sm.LIFECYCLE_STATES
            if before == "REVOKED":
                assert after == "REVOKED"
            if before == "EXPIRED":
                assert after in ("EXPIRED", "REVOKED")
            if before in sm.TERMINAL_STATES:
                ended_then_checked += 1
                for t in times:
                    m = decision_matrix(c, "AU", now=t, verify_did=syntax_only, va_approvals_only=rng.random() < 0.5)
                    assert m["VL"] is False and m["ALLOW"] is False and deny_code(m) in ("REVOKED", "EXPIRED")
    assert seen == set(sm.LIFECYCLE_STATES) and ended_then_checked > 3000


def test_algorithm_6_2_validates_a_data_access():
    ok = sm.validate_lifecycle(consent(), NOW)
    assert ok["VALID"] is True and ok["result"] == "VALID" and ok["state"] == "ACTIVE" and ok["deny_code"] is None
    cases = [(consent(start_date=LATER), "PRE-VALIDITY", "NOT_STARTED"),
             (consent(expiry_date=EARLIER), "EXPIRED", "EXPIRED"),
             (consent(signers=[G[0]], expiry_date=EARLIER), "POST-VALIDITY", "PENDING_SIGNATURE"),
             (consent(revoked=True), "REVOKED", "REVOKED"),
             (consent(revoked=True, expiry_date=EARLIER), "REVOKED", "REVOKED"),
             (consent(triggers=[dict(TRIGGER)]), "AWAITING-TRIGGER", "SUSPENDED"),
             (consent(transitions=[majority(EARLIER)]), "TRANSITION-PENDING", "SUSPENDED"),
             (consent(signers=[G[0]]), "APPROVAL-PENDING", "PENDING_SIGNATURE"),
             (consent(token=None), "TOKEN-PENDING", "PENDING_TOKEN"),
             (consent(state="EXPIRED"), "EXPIRED", "EXPIRED"),
             (consent(start_date="not a date"), "RECORD-INVALID", None)]
    for c, code, expected_state in cases:
        r = sm.validate_lifecycle(c, NOW)
        assert r["VALID"] is False and r["result"] == "INVALID" and r["operation"] == "ACCESS", (code, r)
        assert r["deny_code"] == code and r["state"] == expected_state and r["reason"]
        assert decide(c)["VL"] is False and code in decide(c)["DENY"]   # the decision rule gives the same answer


def test_algorithm_6_2_checks_a_requested_transition_against_the_policy():
    def ask(c, target):
        r = sm.validate_lifecycle(c, NOW, target=target)
        assert r["operation"] == "TRANSITION" and r["target"] == target
        return r["VALID"], r["deny_code"]
    suspended = consent(triggers=[dict(TRIGGER)])
    assert ask(suspended, "ACTIVE") == (True, None)                    # resume
    assert ask(consent(), "SUSPENDED") == (True, None) and ask(consent(), "EXPIRED") == (True, None)
    assert ask(consent(token=None), "ACTIVE") == (True, None)          # activation when the token is recorded
    # no way back into ACTIVE from REVOKED or EXPIRED
    assert ask(consent(revoked=True), "ACTIVE") == (False, "REVOKED")
    assert ask(consent(expiry_date=EARLIER), "ACTIVE") == (False, "EXPIRED")
    assert ask(consent(state="EXPIRED"), "ACTIVE") == (False, "TRANSITION-NOT-PERMITTED")
    assert ask(consent(state="EXPIRED"), "SUSPENDED") == (False, "TRANSITION-NOT-PERMITTED")
    # a transition into ACTIVE is bound to the window, and steps that the table does not list are refused
    assert ask(consent(start_date=LATER), "ACTIVE") == (False, "PRE-VALIDITY")
    assert ask(consent(signers=[G[0]]), "ACTIVE") == (False, "TRANSITION-NOT-PERMITTED")
    assert ask(consent(), "PENDING_SIGNATURE") == (False, "TRANSITION-NOT-PERMITTED")
    assert ask(consent(), "ACTIVE") == (False, "TRANSITION-NOT-PERMITTED")
    assert ask(consent(), "FROZEN") == (False, "TRANSITION-NOT-PERMITTED")
    # revocation is accepted from every state that is not REVOKED, inside or outside the window
    for c in (consent(), suspended, consent(signers=[G[0]]), consent(token=None), consent(start_date=LATER),
              consent(expiry_date=EARLIER), consent(state="EXPIRED"), consent(start_date="not a date")):
        assert ask(c, "REVOKED") == (True, None)
    assert ask(consent(revoked=True), "REVOKED") == (False, "REVOKED")
    assert ask(consent(state="REVOKED", start_date="not a date"), "REVOKED") == (False, "REVOKED")


def test_algorithm_6_2_hands_its_evidence_to_the_recorder():
    seen = []
    r = sm.validate_lifecycle(consent(revoked=True), NOW, record=seen.append)
    assert seen == [r] and r["consent_id"] == "core-2of2" and r["time"] == NOW.isoformat()
    assert r["window"] == [START, EXPIRY] and r["revoked"] is True and r["recorded_state"] == "CREATED"
    assert sm.validate_lifecycle(consent(), NOW, target="REVOKED", record=seen.append)["VALID"] is True and len(seen) == 2


def test_evaluate_state_records_the_state_at_the_given_time():
    c = consent()
    assert c.state == "CREATED"
    assert sm.evaluate_state(c, NOW - timedelta(days=2)) == "NOT_STARTED" and c.state == "NOT_STARTED"
    assert sm.evaluate_state(c, NOW) == "ACTIVE" and c.state == "ACTIVE"
    assert state(c, NOW + timedelta(days=31)) == "EXPIRED" and c.state == "ACTIVE"   # lifecycle_state writes nothing


# ---------------------------------------------------------------------------
# Trusted time source (Section 6.2.5)
# ---------------------------------------------------------------------------
BLOCK = {"number": 11771243, "timestamp": 1794300000}
BLOCK_TIME = datetime.fromtimestamp(1794300000)


def test_trusted_time_is_the_timestamp_of_the_latest_block():
    assert time_source.trusted_now(lambda: BLOCK) == (BLOCK_TIME, "block-timestamp")
    ev = time_source.read_time(lambda: BLOCK, system_clock=lambda: BLOCK_TIME - timedelta(seconds=12))
    assert ev["time"] == BLOCK_TIME and ev["source"] == time_source.SOURCE_BLOCK and ev["unix"] == 1794300000
    assert ev["block_number"] == 11771243 and ev["reason"] is None and ev["clock_skew_seconds"] == 12.0

    class Block:
        timestamp = 1794300000
        number = 5
    for shape in (1794300000, 1794300000.9, Block()):
        assert time_source.trusted_now(lambda: shape) == (BLOCK_TIME, "block-timestamp")

    def beacon():
        return NOW
    beacon.source = "stated-beacon"
    assert time_source.trusted_now(beacon) == (NOW, "stated-beacon")
    assert time_source.trusted_now(lambda: NOW.astimezone()) == (NOW, "block-timestamp")   # a zoned time, same moment
    assert state(consent(), time_source.trusted_now(lambda: int(NOW.timestamp()))[0]) == "ACTIVE"


def test_system_clock_is_a_labelled_fallback():
    def clock():
        return NOW

    def broken():
        raise ConnectionError("no route to the node")
    providers = (None, broken, lambda: None, lambda: {"number": 1}, lambda: {"timestamp": 0}, lambda: {"timestamp": -5},
                 lambda: "1794300000", lambda: True, lambda: float("nan"), lambda: float("inf"))
    for provider in providers:
        ev = time_source.read_time(provider, system_clock=clock)
        assert ev["time"] == NOW and ev["source"] == "system-clock-fallback" and ev["reason"]
        assert ev["block_number"] is None and ev["clock_skew_seconds"] is None
        assert time_source.trusted_now(provider, system_clock=clock) == (NOW, time_source.SOURCE_SYSTEM)
    assert time_source.read_time(None, system_clock=clock)["reason"] == "no provider configured"
    assert "no route to the node" in time_source.read_time(broken, system_clock=clock)["reason"]
    before = datetime.now(); t, source = time_source.trusted_now(); after = datetime.now()
    assert before <= t <= after and source == "system-clock-fallback"


def test_fallback_to_the_system_clock_can_be_refused():
    def broken():
        raise ConnectionError("no route to the node")
    for provider in (None, broken, lambda: {"timestamp": 0}):
        with pytest.raises(time_source.TimeSourceError):
            time_source.trusted_now(provider, allow_fallback=False)
    assert time_source.trusted_now(lambda: BLOCK, allow_fallback=False) == (BLOCK_TIME, "block-timestamp")


def test_trusted_time_far_behind_the_system_clock_can_be_refused():
    def clock():
        return BLOCK_TIME + timedelta(seconds=900)                     # the node stopped 15 minutes ago
    assert time_source.trusted_now(lambda: BLOCK, system_clock=clock) == (BLOCK_TIME, "block-timestamp")   # no limit
    assert time_source.read_time(lambda: BLOCK, system_clock=clock)["clock_skew_seconds"] == -900.0
    assert time_source.trusted_now(lambda: BLOCK, system_clock=clock, max_lag_seconds=900)[1] == "block-timestamp"
    ev = time_source.read_time(lambda: BLOCK, system_clock=clock, max_lag_seconds=300)
    assert ev["source"] == "system-clock-fallback" and ev["time"] == clock() and "900 seconds behind" in ev["reason"]
    with pytest.raises(time_source.TimeSourceError):
        time_source.trusted_now(lambda: BLOCK, system_clock=clock, max_lag_seconds=300, allow_fallback=False)
    # a chain time ahead of the system clock is not a lag
    ahead = time_source.read_time(lambda: BLOCK, system_clock=lambda: BLOCK_TIME - timedelta(hours=1), max_lag_seconds=0)
    assert ahead["source"] == "block-timestamp" and ahead["clock_skew_seconds"] == 3600.0


def test_decision_follows_the_block_time_and_not_the_server_clock():
    # The expiry run on the in-memory chain: a window of five minutes, passed by moving the chain time.
    try:
        from web3 import Web3, EthereumTesterProvider
    except Exception:
        pytest.skip("eth-tester not installed")
    w3 = Web3(EthereumTesterProvider())
    provider = time_source.block_provider(w3)

    def syntax_only(did, role=None, now=None):
        return is_valid_did(did)
    t0, source = time_source.trusted_now(provider)
    assert source == "block-timestamp" and t0 == datetime.fromtimestamp(w3.eth.get_block("latest").timestamp)
    c = consent(start_date=(t0 - timedelta(minutes=1)).isoformat(), expiry_date=(t0 + timedelta(minutes=5)).isoformat())
    assert evaluate_allow(c, "AU", now=t0, verify_did=syntax_only)["ALLOW"] is True
    w3.provider.ethereum_tester.time_travel(w3.eth.get_block("latest").timestamp + 600)
    t1, source = time_source.trusted_now(provider, allow_fallback=False)
    assert source == "block-timestamp" and t1 > t0 + timedelta(minutes=5)
    m = decision_matrix(c, "AU", now=t1, verify_did=syntax_only)
    assert sm.lifecycle_state(c, t1) == "EXPIRED" and m["VT"] is False and m["VL"] is False and m["ALLOW"] is False
    assert m["DENY"] == ["EXPIRED"]
    # a server clock that still showed the earlier time would have allowed the same request
    assert evaluate_allow(c, "AU", now=t0, verify_did=syntax_only)["ALLOW"] is True


def test_services_do_not_replace_the_names_the_interface_imports():
    # app.py imports the services with a star after `from datetime import datetime, date`
    import datetime as dt
    names = {}
    exec("from datetime import datetime, date\nfrom services.consent_service import *\n"
         "from services.state_service import *\nfrom services.access_service import *", names)
    assert names["datetime"] is dt.datetime and names["date"] is dt.date and "time" not in names
    for old in ("create_consent", "lifecycle_state", "evaluate_state", "guardian_approvals", "check_scope", "authorize",
                "evaluate_allow", "ALLOWED_PURPOSES"):
        assert old in names
