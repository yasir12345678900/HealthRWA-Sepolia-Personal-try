"""Conditional triggers and capacity transitions of the thesis design (Chapter 6, Sections 6.2.3 and 6.3.4,
Algorithm 6.3), and the passing of authority at eighteen in the case study of Layan (Section 1.2).
Triggers: a trigger holds the consent back until a credentialed clinician attests the event with a signature that is
bound to the consent, the patient, the event and the chain. Capacity transition: at majority the consent is re-issued
with the patient as its sole guardian and a threshold of one, signed by the patient, which on chain is a mint and a
revocation. Every test runs offline at fixed times with the demonstration keys of the test harness. The chain is
replaced by callables, and one test runs them against the ConsentSBTv3 bytecode on the in-memory chain."""
import copy, json, os, uuid
import pytest
from datetime import date, datetime, timedelta
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3
from models.consent import Consent
from services import capacity_service as cap
from services import identity_service as ids
from services import trigger_service as trg
from services.access_service import evaluate_allow, guardian_approvals
from services.identity_service import issue_credential, sign_consent, verify_signature, verify_vc

NOW = datetime(2026, 11, 11, 12, 0, 0)                     # the consent is given, Layan is sixteen
START, EXPIRY = "2026-11-01T00:00:00", "2029-12-31T23:59:59"
BORN = "2010-03-14"
EIGHTEEN = datetime(2028, 3, 14)                           # the start of the day on which she reaches eighteen
BIRTHDAY, NEXT_DAY = EIGHTEEN + timedelta(hours=9), EIGHTEEN + timedelta(days=1, hours=9)
LAYAN, FATHER, MOTHER, UNCLE = "did:patient:layan", "did:parent:A", "did:parent:B", "did:parent:C"
DR_MITCHELL, CLINICIAN, REGISTRAR = "did:hospital:001", "did:hospital:002", "did:hospital:003"
EVENT = "loss-of-capacity"
TRIGGER_KEYS = {"id", "kind", "event", "attester_role", "satisfied", "attestation_id"}
TRANSITION_KEYS = {"id", "kind", "due", "done"}
ATTESTATION_KEYS = {"id", "event", "attester_did", "signed_at", "signature"}


def approve(c, did):
    sig, addr = sign_consent(did, c.consent_id)
    c.signatures.append(did); c.signature_data[did] = {"scheme": "EIP-712", "signer": addr, "signature": sig}


def consent(approvals=(FATHER, MOTHER), token="SBT-1", **kw):
    """Layan's consent: Dr Mitchell, treatment, four modules, both parents must approve. Approved and anchored
    unless `approvals`, `token` or a field in `kw` says otherwise."""
    c = Consent(f"tc-{uuid.uuid4().hex[:12]}", LAYAN, DR_MITCHELL, [FATHER, MOTHER], "Treatment",
                ["Observation", "Medication", "Condition", "Procedure"], 2, start_date=START, expiry_date=EXPIRY,
                token_id=token)
    for g in approvals:
        approve(c, g)
    for name, value in kw.items():
        setattr(c, name, value)
    return c


def minor(**kw):
    """The same consent with Layan's date of birth and the transition at majority scheduled."""
    c = consent(patient_birth_date=BORN, **kw)
    assert cap.schedule_majority_transition(c, now=NOW) is not None
    return c


def decide(c, now, requester=DR_MITCHELL):
    return evaluate_allow(c, "AU", now=now, verify_sig=verify_signature, verify_did=verify_vc, requester_did=requester)


def rows(consent_id, action=None):
    from database import audit_db
    return [e for e in audit_db.get() if e["consent_id"] == consent_id and action in (None, e["action"])]


def stored(consent_id):
    from database import consent_db
    return consent_db.get(consent_id)


class Chain:
    """Stands for the consent contract. It records everything the service sends to the chain."""

    def __init__(self, fail_mint=False, fail_revoke=False):
        self.calls, self.fail_mint, self.fail_revoke = [], fail_mint, fail_revoke

    def _receipt(self, **more):
        return {"tx_hash": "0x" + f"{len(self.calls):064x}", "block_number": 1000 + len(self.calls), "status": 1, **more}

    def mint(self, c):
        if self.fail_mint:
            raise RuntimeError("the mint was reverted")
        self.calls.append(("mint", c.consent_id))
        return self._receipt(token_id=100 + len(self.calls))

    def revoke(self, c):
        if self.fail_revoke:
            raise RuntimeError("the revoke was reverted")
        self.calls.append(("revoke", c.token_id))
        return self._receipt()


def refused(c, attestation, reason, now=NOW, **kw):
    """Present an attestation that must be refused: nothing in the consent changes and the ledger names the reason."""
    before = (copy.deepcopy(c.triggers), copy.deepcopy(c.attestations))
    r = trg.present_attestation(c, attestation, now=now, **kw)
    assert r["VALID"] is False and r["reason"] == reason, r
    assert (c.triggers, c.attestations) == before
    row = rows(c.consent_id, "PRESENT_ATTESTATION")[-1]
    assert row["result"] == "REJECTED" and row["metadata"]["reason"] == reason
    return r


# ---------------------------------------------------------------------------
# Conditional triggers (Sections 6.2.3 and 6.3.4)
# ---------------------------------------------------------------------------
def test_added_trigger_holds_the_consent_back():
    c = consent()
    assert cap.evaluate_conditions(c, NOW)["state"] == "ACTIVE"
    t = trg.add_trigger(c, EVENT, attester_role="doctor", now=NOW)
    assert set(t) == TRIGGER_KEYS and t["kind"] == "attestation" and t["event"] == EVENT
    assert t["attester_role"] == "doctor" and t["satisfied"] is False and t["attestation_id"] is None
    assert c.triggers == [t] and trg.waiting_triggers(c) == [t]
    ev = cap.evaluate_conditions(c, NOW)
    assert ev["state"] == "SUSPENDED" and ev["suspended"] is True and ev["deny_codes"] == ["AWAITING-TRIGGER"]
    assert ev["waiting_triggers"] == [t["id"]] and ev["pending_transitions"] == [] and c.state == "SUSPENDED"
    assert stored(c.consent_id).triggers == [t]                       # the consent store has the trigger
    added = rows(c.consent_id, "ADD_TRIGGER")
    assert len(added) == 1 and added[0]["actor_did"] == LAYAN and added[0]["metadata"]["trigger"] == t
    moved = rows(c.consent_id, "CONDITION_CHECK")
    assert [m["result"] for m in moved] == ["SUSPENDED"] and moved[0]["metadata"]["deny_codes"] == ["AWAITING-TRIGGER"]
    cap.evaluate_conditions(c, NOW)                                   # a second evaluation changes nothing
    assert len(rows(c.consent_id, "CONDITION_CHECK")) == 1


def test_add_trigger_rejects_bad_input_and_ended_consents():
    c = consent()
    trg.add_trigger(c, EVENT, trigger_id="t-1", now=NOW)
    for bad in ({"event": ""}, {"event": None}, {"event": "death", "attester_role": ""},
                {"event": EVENT},                                      # the same event and role a second time
                {"event": "death", "trigger_id": "t-1"}):              # an identifier that is in use
        with pytest.raises(ValueError):
            trg.add_trigger(c, now=NOW, **bad)
    assert len(c.triggers) == 1
    for ended in (consent(revoked=True), consent(successor_id="next"), consent(expiry_date="2026-11-10T00:00:00"),
                  consent(expiry_date="not a date")):
        with pytest.raises(ValueError):
            trg.add_trigger(ended, EVENT, now=NOW)
        assert ended.triggers == []


def test_clinician_attestation_satisfies_the_trigger_and_is_recorded():
    c = consent()
    t = trg.add_trigger(c, EVENT, now=NOW)
    a = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW)
    assert ATTESTATION_KEYS <= set(a) and a["attester_did"] == CLINICIAN and a["signed_at"] == NOW.isoformat()
    r = trg.present_attestation(c, a, now=NOW)
    assert r["VALID"] is True and r["reason"] is None and r["trigger_id"] == t["id"] and r["attestation_id"] == a["id"]
    assert all(r["checks"][k] is True
               for k in ("Well_formed", "Event_match", "Fresh", "Time_valid", "Sig_valid", "Attester_valid"))
    assert t["satisfied"] is True and t["attestation_id"] == a["id"] and trg.waiting_triggers(c) == []
    assert len(c.attestations) == 1 and ATTESTATION_KEYS <= set(c.attestations[0])
    assert {k: c.attestations[0][k] for k in ATTESTATION_KEYS} == {k: a[k] for k in ATTESTATION_KEYS}
    ev = cap.evaluate_conditions(c, NOW)                               # the consent leaves SUSPENDED
    assert ev["state"] == "ACTIVE" and ev["deny_codes"] == [] and ev["triggers"][0]["satisfied"] is True
    assert decide(c, NOW)["ALLOW"] is True
    row = rows(c.consent_id, "PRESENT_ATTESTATION")[-1]               # the event is recorded in the ledger
    assert row["result"] == "SUCCESS" and row["actor_did"] == CLINICIAN and row["actor_role"] == "Doctor"
    assert row["metadata"]["event"] == EVENT and row["metadata"]["attestation_id"] == a["id"]
    assert row["metadata"]["checks"]["credential_id"] == "urn:halah:vc:doctor:" + CLINICIAN
    assert stored(c.consent_id).triggers[0]["satisfied"] is True and len(stored(c.consent_id).attestations) == 1


def test_attestation_signature_is_bound_to_consent_patient_event_attester_and_chain():
    c = consent()
    trg.add_trigger(c, EVENT, now=NOW); trg.add_trigger(c, "death", now=NOW)
    good = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW)
    forger = Account.from_key(Web3.keccak(text="a key that is not the clinician's"))
    other = consent()
    for_other_consent = trg.sign_attestation(CLINICIAN, other, EVENT, signed_at=NOW)
    other_patient = copy.deepcopy(c); other_patient.patient_did = "did:patient:someone-else"
    approval, _ = sign_consent(CLINICIAN, c.consent_id)               # an approval signature is not an attestation
    bad = [trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW, signer=forger),
           for_other_consent,
           {k: v for k, v in for_other_consent.items() if k != "consent_id"},
           trg.sign_attestation(CLINICIAN, other_patient, EVENT, signed_at=NOW),
           dict(good, event="death"),                                 # the attested event was changed
           dict(good, signed_at=(NOW - timedelta(days=1)).isoformat()),
           dict(good, attester_did=DR_MITCHELL),                      # another clinician is named as the signer
           dict(good, id="att-changed"),
           trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW, chain_id=1),
           dict(good, signature=approval),
           dict(good, signature="0x" + "11" * 65)]
    for a in bad:
        r = refused(c, a, "ATTESTATION-SIGNATURE-INVALID")
        assert r["checks"]["Sig_valid"] is False and r["checks"]["Attester_valid"] is True
    assert trg.verify_attestation_signature(good, c) is True and trg.verify_attestation_signature(good, other) is False
    assert trg.present_attestation(c, good, now=NOW)["VALID"] is True  # positive control: the untouched attestation


def test_attester_needs_a_valid_credential_with_the_role_the_trigger_names():
    c = consent(expiry_date="2035-12-31T23:59:59")
    trg.add_trigger(c, EVENT, attester_role="doctor", now=NOW)
    # a guardian, the patient and an identifier without a credential sign correctly, but none of them is a clinician
    for attester in (FATHER, LAYAN, "did:hospital:999"):
        r = refused(c, trg.sign_attestation(attester, c, EVENT, signed_at=NOW), "ATTESTER-NOT-AUTHORISED")
        assert r["checks"]["Sig_valid"] is True and r["checks"]["Attester_valid"] is False
    a = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW)
    forger = Account.from_key(Web3.keccak(text="attacker key"))
    for credential in (issue_credential(CLINICIAN, "doctor", signer=forger),                       # not the issuer's key
                       issue_credential(CLINICIAN, "doctor", issuer_did="did:example:unknown", signer=forger),
                       issue_credential(CLINICIAN, "guardian"),                                    # the wrong role
                       issue_credential(CLINICIAN, "doctor", valid_until="2026-11-10T00:00:00")):  # expired
        refused(c, a, "ATTESTER-NOT-AUTHORISED",
                verify_did=lambda d, role=None, now=None, cred=credential: verify_vc(d, role=role, credential=cred, now=now))
    # the credential is checked at the time of presentation: the demonstration credentials end on 2030-12-31
    late = datetime(2031, 6, 1)
    refused(c, trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=late), "ATTESTER-NOT-AUTHORISED", now=late)
    assert trg.present_attestation(c, a, now=NOW)["VALID"] is True


def test_injected_identity_check_decides_about_the_attester():
    seen = []

    def check(did, role=None, now=None):
        seen.append((did, role, now)); return did == "did:hospital:777"
    c = consent()
    trg.add_trigger(c, EVENT, attester_role="doctor", now=NOW)
    refused(c, trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW), "ATTESTER-NOT-AUTHORISED", verify_did=check)
    r = trg.present_attestation(c, trg.sign_attestation("did:hospital:777", c, EVENT, signed_at=NOW), now=NOW, verify_did=check)
    assert r["VALID"] is True and seen == [(CLINICIAN, "doctor", NOW), ("did:hospital:777", "doctor", NOW)]
    c2 = consent(); trg.add_trigger(c2, EVENT, now=NOW)                # a checker without a `now` argument
    assert trg.present_attestation(c2, trg.sign_attestation(CLINICIAN, c2, EVENT, signed_at=NOW), now=NOW,
                                   verify_did=lambda did, role=None: role == "doctor")["VALID"] is True


def test_attestation_time_malformed_input_and_unknown_trigger():
    c = consent()
    t = trg.add_trigger(c, EVENT, now=NOW)
    refused(c, trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW + timedelta(hours=1)), "ATTESTATION-TIME-INVALID")
    refused(c, trg.sign_attestation(CLINICIAN, c, EVENT, signed_at="yesterday"), "ATTESTATION-TIME-INVALID")
    good = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW)
    for malformed in (None, "attested", {}, {k: v for k, v in good.items() if k != "signature"}, dict(good, event=""),
                      dict(good, attester_did=None), dict(good, signed_at=20261111)):
        assert refused(c, malformed, "ATTESTATION-MALFORMED")["attestation_id"] is None
    refused(c, trg.sign_attestation(CLINICIAN, c, "death", signed_at=NOW), "TRIGGER-NOT-FOUND")     # no trigger waits for it
    refused(c, good, "TRIGGER-NOT-FOUND", trigger_id="no-such-trigger")
    refused(c, trg.sign_attestation(CLINICIAN, c, "death", signed_at=NOW), "EVENT-MISMATCH", trigger_id=t["id"])
    # a clock that runs a few minutes ahead of the time source is tolerated
    ahead = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW + timedelta(minutes=4))
    assert trg.present_attestation(c, ahead, trigger_id=t["id"], now=NOW)["VALID"] is True


def test_attestation_cannot_be_replayed():
    c = consent()
    first = trg.add_trigger(c, EVENT, attester_role="doctor", now=NOW)
    second = trg.add_trigger(c, EVENT, attester_role="guardian", now=NOW)      # the same event, confirmed by a guardian
    a = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW)
    assert trg.present_attestation(c, a, now=NOW)["trigger_id"] == first["id"]
    refused(c, a, "TRIGGER-ALREADY-SATISFIED", trigger_id=first["id"])
    refused(c, a, "ATTESTATION-REPLAYED", trigger_id=second["id"])
    refused(c, a, "ATTESTATION-REPLAYED")                             # without an identifier the waiting trigger is tried
    assert len(c.attestations) == 1 and cap.evaluate_conditions(c, NOW)["waiting_triggers"] == [second["id"]]
    r = trg.present_attestation(c, trg.sign_attestation(MOTHER, c, EVENT, signed_at=NOW), now=NOW)
    assert r["VALID"] is True and r["trigger_id"] == second["id"]
    assert cap.evaluate_conditions(c, NOW)["state"] == "ACTIVE" and len(c.attestations) == 2


def test_ended_consent_takes_no_attestation():
    for change, reason in (({"revoked": True}, "CONSENT-REVOKED"), ({"successor_id": "next"}, "CONSENT-REVOKED"),
                           ({"expiry_date": "2026-11-11T11:00:00"}, "CONSENT-EXPIRED"),
                           ({"expiry_date": "not a date"}, "RECORD-INVALID")):
        c = consent()
        trg.add_trigger(c, EVENT, now=NOW - timedelta(days=1))
        a = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW)
        for name, value in change.items():
            setattr(c, name, value)
        refused(c, a, reason)


def test_trigger_marked_satisfied_without_a_valid_attestation_is_set_back():
    c = consent()
    t = trg.add_trigger(c, EVENT, now=NOW)
    t.update(satisfied=True, attestation_id="att-never-presented")     # the flag is set, but no event was attested
    ev = cap.evaluate_conditions(c, NOW)
    assert ev["state"] == "SUSPENDED" and ev["deny_codes"] == ["AWAITING-TRIGGER"]
    assert ev["triggers"] == [{"id": t["id"], "event": EVENT, "satisfied": False, "reason": "ATTESTATION-MISSING"}]
    assert t["satisfied"] is False and t["attestation_id"] is None
    check = rows(c.consent_id, "TRIGGER_CHECK")
    assert len(check) == 1 and check[0]["result"] == "WAITING"
    assert check[0]["metadata"]["set_back"][0]["reason"] == "ATTESTATION-MISSING"
    a = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW)
    assert trg.present_attestation(c, a, now=NOW)["VALID"] is True
    assert trg.evaluate_triggers(c)[0] == {"id": t["id"], "event": EVENT, "satisfied": True, "reason": None}
    assert len(rows(c.consent_id, "TRIGGER_CHECK")) == 1               # an intact trigger writes nothing
    c.attestations[0]["attester_did"] = DR_MITCHELL                    # the stored record is changed afterwards
    assert trg.evaluate_triggers(c)[0]["reason"] == "ATTESTATION-SIGNATURE-INVALID" and t["satisfied"] is False
    # a record for another event, and entries that cannot be read, do not satisfy a trigger either
    c2 = consent(); t2 = trg.add_trigger(c2, EVENT, now=NOW); trg.add_trigger(c2, "death", trigger_id="t-death", now=NOW)
    assert trg.present_attestation(c2, trg.sign_attestation(CLINICIAN, c2, EVENT, signed_at=NOW), now=NOW)["VALID"] is True
    c2.triggers[1].update(satisfied=True, attestation_id=t2["attestation_id"])
    c2.triggers += ["not a trigger", {"id": "t-x", "kind": "time-lock", "satisfied": True}]
    assert [(r["satisfied"], r["reason"]) for r in trg.evaluate_triggers(c2)] == [
        (True, None), (False, "EVENT-MISMATCH"), (False, "TRIGGER-MALFORMED"), (False, "TRIGGER-MALFORMED")]
    assert cap.evaluate_conditions(c2, NOW)["state"] == "SUSPENDED" and len(trg.waiting_triggers(c2)) == 3


def test_attester_key_held_in_a_wallet():
    wallet = Account.from_key(Web3.keccak(text="test wallet of the clinician"))
    c = consent()
    t = trg.add_trigger(c, EVENT, now=NOW)
    a = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW, signer=wallet)
    # the wallet signs the typed data that the service publishes, so both sides sign the same bytes
    typed = trg.attestation_typed_data(a, c.patient_did)
    assert typed["primaryType"] == "Attestation"
    assert typed["domain"] == {"name": "HALAH Attestation", "version": "1", "chainId": ids.CHAIN_ID}
    assert typed["message"] == {"attestationId": a["id"], "consentId": c.consent_id, "patient": LAYAN, "event": EVENT,
                                "attester": CLINICIAN, "signedAt": NOW.isoformat()}
    assert "0x" + bytes(wallet.sign_message(encode_typed_data(full_message=typed)).signature).hex() == a["signature"]
    refused(c, a, "ATTESTATION-SIGNATURE-INVALID")                    # it is not the key derived from the identifier
    other = Account.from_key(Web3.keccak(text="another wallet"))
    assert trg.verify_attestation_signature(a, c, address=other.address) is False

    def by_wallet(attestation, consent_):
        return trg.verify_attestation_signature(attestation, consent_, address=wallet.address)
    assert trg.present_attestation(c, a, now=NOW, verify_sig=by_wallet)["VALID"] is True
    ev = cap.evaluate_conditions(c, NOW, verify_sig=by_wallet)
    assert ev["state"] == "ACTIVE" and t["satisfied"] is True
    # the derived key can be switched off, and it never stands for a did:key identifier, which names its own key
    derived = trg.sign_attestation(CLINICIAN, c, EVENT, signed_at=NOW)
    assert trg.verify_attestation_signature(derived, c) is True
    assert trg.verify_attestation_signature(derived, c, allow_demo_key=False) is False
    assert trg.verify_attestation_signature(a, c, address=wallet.address, allow_demo_key=False) is True
    did_key = "did:key:zQ3shokFTS3brHcDQrn82RUDfCZESWL1ZdCEJwekUDPQiYBme"
    with pytest.raises(ValueError):
        trg.sign_attestation(did_key, c, EVENT, signed_at=NOW)
    forged = trg.sign_attestation(did_key, c, EVENT, signed_at=NOW, signer=ids.guardian_account(did_key))
    assert trg.verify_attestation_signature(forged, c) is False        # the key rebuilt from the identifier string
    by_holder = trg.sign_attestation(did_key, c, EVENT, signed_at=NOW, signer=wallet)
    assert trg.verify_attestation_signature(by_holder, c, address=wallet.address) is True


# ---------------------------------------------------------------------------
# Capacity transition: scheduling and evaluation (Sections 6.2.3 and 6.3.4)
# ---------------------------------------------------------------------------
def test_majority_date():
    assert cap.majority_date(BORN) == EIGHTEEN and cap.majority_date("2010-03-14T07:30:00") == EIGHTEEN
    assert cap.majority_date(date(2010, 3, 14)) == EIGHTEEN and cap.majority_date(datetime(2010, 3, 14, 23, 59)) == EIGHTEEN
    assert cap.majority_date(BORN, 21) == datetime(2031, 3, 14)
    assert cap.majority_date("2008-02-29", 16) == datetime(2024, 2, 29)        # a leap year
    assert cap.majority_date("2008-02-29", 18) == datetime(2026, 3, 1)         # no 29 February in 2026
    for bad in ("14/03/2010", "", None, 20100314):
        with pytest.raises(ValueError):
            cap.majority_date(bad)
    for bad_age in (0, -1, 17.5, "18", True, None):
        with pytest.raises(ValueError):
            cap.majority_date(BORN, bad_age)


def test_transition_is_scheduled_for_a_minor_patient_only():
    c = consent(patient_birth_date=BORN)
    t = cap.schedule_majority_transition(c, now=NOW)
    assert set(t) == TRANSITION_KEYS and t["kind"] == "majority" and t["due"] == "2028-03-14T00:00:00" and t["done"] is False
    assert c.transitions == [t] and stored(c.consent_id).transitions == [t]
    row = rows(c.consent_id, "SCHEDULE_TRANSITION")
    assert len(row) == 1 and row[0]["result"] == "SUCCESS" and row[0]["metadata"]["transition"] == t
    assert cap.schedule_majority_transition(c, now=NOW) is t and len(c.transitions) == 1       # scheduled once
    assert len(rows(c.consent_id, "SCHEDULE_TRANSITION")) == 1
    at_21 = consent(patient_birth_date=BORN, majority_age=21)
    assert cap.schedule_majority_transition(at_21, now=NOW)["due"] == "2031-03-14T00:00:00"
    # no transition: no date of birth, an adult patient, a patient who is the sole guardian already
    for c in (consent(), consent(patient_birth_date="2000-01-01"), consent(patient_birth_date="2008-11-11"),
              consent(patient_birth_date=BORN, guardian_dids=[LAYAN], threshold=1)):
        assert cap.schedule_majority_transition(c, now=NOW) is None and c.transitions == []
        assert rows(c.consent_id, "SCHEDULE_TRANSITION") == []
    with pytest.raises(ValueError):
        cap.schedule_majority_transition(consent(patient_birth_date="March 2010"), now=NOW)


def test_consent_is_suspended_from_the_day_of_majority():
    c = minor()
    before = EIGHTEEN - timedelta(seconds=1)
    assert cap.pending_transitions(c, before) == [] and cap.pending_transitions(c, EIGHTEEN) == c.transitions
    ev = cap.evaluate_conditions(c, before)
    assert ev["state"] == "ACTIVE" and ev["pending_transitions"] == [] and ev["deny_codes"] == []
    assert decide(c, before)["ALLOW"] is True                          # the parents' approvals carry until then
    ev = cap.evaluate_conditions(c, EIGHTEEN)
    assert ev["state"] == "SUSPENDED" and ev["deny_codes"] == ["TRANSITION-PENDING"]
    assert ev["pending_transitions"] == [c.transitions[0]["id"]] and c.state == "SUSPENDED"
    moved = rows(c.consent_id, "CONDITION_CHECK")
    assert [m["result"] for m in moved] == ["SUSPENDED"] and moved[0]["metadata"]["previous_state"] == "ACTIVE"
    # a time with a zone is read as the same moment
    assert cap.pending_transitions(c, BIRTHDAY.astimezone()) == c.transitions
    # an entry that cannot be read keeps the consent suspended, and an executed one does not
    unreadable = consent(transitions=["soon", {"kind": "majority", "due": "soon", "done": False}])
    assert len(cap.pending_transitions(unreadable, NOW)) == 2
    executed = consent(transitions=[{"id": "m", "kind": "majority", "due": "2020-01-01T00:00:00", "done": True}])
    assert cap.pending_transitions(executed, NOW) == []


def test_trigger_and_transition_together_report_both_codes():
    c = minor()
    t = trg.add_trigger(c, EVENT, now=NOW)
    assert cap.evaluate_conditions(c, NOW)["deny_codes"] == ["AWAITING-TRIGGER"]
    ev = cap.evaluate_conditions(c, BIRTHDAY)
    assert ev["state"] == "SUSPENDED" and ev["deny_codes"] == ["AWAITING-TRIGGER", "TRANSITION-PENDING"]
    assert ev["waiting_triggers"] == [t["id"]] and ev["pending_transitions"] == [c.transitions[0]["id"]]
    # the conditions do not hide another state: a revoked consent is REVOKED and reports no suspension code
    c.revoked = True
    ev = cap.evaluate_conditions(c, BIRTHDAY)
    assert ev["state"] == "REVOKED" and ev["suspended"] is False and ev["deny_codes"] == []


# ---------------------------------------------------------------------------
# Capacity transition: the re-issue at majority (Section 6.3.4)
# ---------------------------------------------------------------------------
def test_transition_reissues_the_consent_to_the_patient_alone():
    old, chain = minor(), Chain()
    old_before = copy.deepcopy(old)
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY)
    new = r["successor"]
    assert r["status"] == "COMPLETED" and r["reason"] is None and r["transition_id"] == old.transitions[0]["id"]
    assert r["predecessor_id"] == old.consent_id and r["successor_id"] == new.consent_id != old.consent_id
    # the re-issued consent: the patient is the sole guardian, the threshold is one, and she has signed it
    assert new.guardian_dids == [LAYAN] and new.threshold == 1 and new.signatures == [LAYAN]
    assert verify_signature(LAYAN, new.consent_id, new.signature_data[LAYAN]["signature"]) is True
    assert new.signature_data[LAYAN]["signer"] == ids.guardian_address(LAYAN)
    assert guardian_approvals(new) == {LAYAN} and new.token_id == "SBT-101" and new.revoked is False
    # nothing else of the specification has changed
    for name in ("patient_did", "requester_did", "purpose", "scope", "start_date", "expiry_date", "jurisdiction",
                 "patient_birth_date", "majority_age", "triggers", "attestations"):
        assert getattr(new, name) == getattr(old_before, name), name
    assert new.transitions == [dict(old_before.transitions[0], done=True)] and cap.pending_transitions(new, BIRTHDAY) == []
    # the two consents are linked, and the old one is retired
    assert new.predecessor_id == old.consent_id and new.successor_id is None
    assert old.successor_id == new.consent_id and old.predecessor_id is None
    assert old.revoked is True and old.state == "REVOKED" and old.revoked_at == BIRTHDAY.isoformat()
    assert old.revoked_by == "CAPACITY_TRANSITION" and old.transitions[0]["done"] is True
    assert old.guardian_dids == [FATHER, MOTHER] and old.token_id == "SBT-1"   # the record of the old consent is kept
    # on chain: one mint and one revocation, in this order, and nothing else
    assert chain.calls == [("mint", new.consent_id), ("revoke", "SBT-1")]
    assert r["mint"]["token_id"] == 101 and r["revoke"]["status"] == 1
    # both consents are in the store, and the ledger has the transition
    assert stored(new.consent_id) == new and stored(old.consent_id).successor_id == new.consent_id
    assert cap.evaluate_conditions(new, BIRTHDAY)["state"] == "ACTIVE"
    assert cap.evaluate_conditions(old, BIRTHDAY)["state"] == "REVOKED"
    done = rows(old.consent_id, "CAPACITY_TRANSITION")
    assert len(done) == 1 and done[0]["result"] == "SUCCESS" and done[0]["actor_role"] == "ConsentEngine"
    m = done[0]["metadata"]
    assert m["kind"] == "majority" and m["due"] == "2028-03-14T00:00:00" and m["executed_at"] == BIRTHDAY.isoformat()
    assert m["predecessor_id"] == old.consent_id and m["successor_id"] == new.consent_id and m["signed_by"] == LAYAN
    assert m["guardians_before"] == [FATHER, MOTHER] and m["threshold_before"] == 2
    assert m["guardians_after"] == [LAYAN] and m["threshold_after"] == 1 and m["onchain"] == ["mint", "revoke"]
    assert m["old_token_id"] == "SBT-1" and m["new_token_id"] == "SBT-101"
    assert m["mint_tx"] == r["mint"]["tx_hash"] and m["revoke_tx"] == r["revoke"]["tx_hash"]
    assert done[0]["tx_hash"] is None and done[0]["onchain"] is False  # the transition itself is an off-chain record
    signed, minted = rows(new.consent_id, "SIGN_CONSENT"), rows(new.consent_id, "ONCHAIN_MINT")
    assert len(signed) == 1 and signed[0]["actor_did"] == LAYAN and signed[0]["metadata"]["predecessor_id"] == old.consent_id
    assert len(minted) == 1 and minted[0]["tx_hash"] == r["mint"]["tx_hash"] and minted[0]["onchain"] is True
    revoked = rows(old.consent_id, "ONCHAIN_REVOKE")
    assert len(revoked) == 1 and revoked[0]["result"] == "SUCCESS" and revoked[0]["tx_hash"] == r["revoke"]["tx_hash"]
    # the transition happens once
    again = cap.execute_transition(old, chain.mint, chain.revoke, now=NEXT_DAY)
    assert again["status"] == "REFUSED" and again["reason"] == "ALREADY-TRANSITIONED" and len(chain.calls) == 2
    assert cap.execute_transition(new, chain.mint, chain.revoke, now=NEXT_DAY)["reason"] == "NO-TRANSITION-DUE"


def test_layan_at_eighteen_the_authority_passes_to_her():
    """Case study, Event 3: on her eighteenth birthday the consent is re-issued with Layan as its sole guardian,
    and a request by Dr Mitchell on the following day is allowed against the re-issued consent."""
    old, chain = minor(), Chain()
    assert decide(old, NOW)["ALLOW"] is True                            # at sixteen, under her parents' approvals
    # the day before her birthday nothing is due, and an early transition is refused and recorded
    eve = EIGHTEEN - timedelta(hours=1)
    early = cap.execute_transition(old, chain.mint, chain.revoke, now=eve)
    assert early["status"] == "REFUSED" and early["reason"] == "NO-TRANSITION-DUE" and chain.calls == []
    assert old.successor_id is None and old.revoked is False
    assert rows(old.consent_id, "CAPACITY_TRANSITION")[-1]["result"] == "REJECTED"
    # on her birthday the consent waits for the transition
    assert cap.evaluate_conditions(old, BIRTHDAY)["deny_codes"] == ["TRANSITION-PENDING"]
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY)
    new = r["successor"]
    assert r["status"] == "COMPLETED" and new.guardian_dids == [LAYAN] and new.threshold == 1
    assert [kind for kind, _ in chain.calls] == ["mint", "revoke"]      # on chain: a mint and a revocation
    # the next day Dr Mitchell is allowed against the re-issued consent, and refused against the retired one
    assert cap.evaluate_conditions(new, NEXT_DAY)["state"] == "ACTIVE"
    m = decide(new, NEXT_DAY)
    assert m["ALLOW"] is True and all(m[k] for k in ("VI", "VA", "VP", "VT", "VL"))
    m = decide(old, NEXT_DAY)
    assert m["ALLOW"] is False and m["VA"] is False and m["VL"] is False
    assert decide(new, NEXT_DAY, requester=REGISTRAR)["ALLOW"] is False  # the registrar is still not the requester named
    # her parents hold no authority over the re-issued consent: an approval from a former guardian counts for nothing
    approve(new, FATHER)
    assert guardian_approvals(new) == {LAYAN} and FATHER not in new.guardian_dids and MOTHER not in new.guardian_dids
    # the ledger rows of the old consent, in the order of the events
    assert [(e["action"], e["result"]) for e in rows(old.consent_id)] == [
        ("SCHEDULE_TRANSITION", "SUCCESS"), ("CAPACITY_TRANSITION", "REJECTED"), ("CONDITION_CHECK", "SUSPENDED"),
        ("ONCHAIN_REVOKE", "SUCCESS"), ("CAPACITY_TRANSITION", "SUCCESS")]
    assert [(e["action"], e["result"]) for e in rows(new.consent_id)] == [
        ("SIGN_CONSENT", "SUCCESS"), ("ONCHAIN_MINT", "SUCCESS")]


def test_transition_is_refused_for_a_consent_that_cannot_be_reissued():
    cases = [(minor(revoked=True), "CONSENT-REVOKED"),
             (consent(patient_birth_date=BORN, expiry_date="2027-12-31T00:00:00"), "CONSENT-EXPIRED"),
             (consent(patient_birth_date=BORN, expiry_date="not a date"), "RECORD-INVALID"),
             (minor(token=None), "TOKEN-PENDING"),                        # approved, the mint is not recorded yet
             (minor(patient_did="layan"), "PATIENT-IDENTIFIER-INVALID"),
             (consent(), "NO-TRANSITION-DUE"),                            # an adult consent has no transition
             (consent(transitions=[{"id": "m", "kind": "majority", "due": "soon", "done": False}]), "NO-TRANSITION-DUE"),
             (consent(transitions=[{"id": "x", "kind": "guardian-change", "due": "2027-01-01T00:00:00", "done": False}]),
              "NO-TRANSITION-DUE")]
    for c, reason in cases:
        if c.patient_birth_date and not c.transitions:
            c.transitions.append({"id": "m-1", "kind": "majority", "due": EIGHTEEN.isoformat(), "done": False})
        chain, before = Chain(), copy.deepcopy(c)
        r = cap.execute_transition(c, chain.mint, chain.revoke, now=BIRTHDAY)
        assert r["status"] == "REFUSED" and r["reason"] == reason, (reason, r)
        assert chain.calls == [] and c == before and r["successor"] is None
        row = rows(c.consent_id, "CAPACITY_TRANSITION")[-1]
        assert row["result"] == "REJECTED" and row["metadata"]["reason"] == reason


def test_reissue_needs_the_signature_of_the_patient():
    def father_signs(did, consent_id):
        return sign_consent(FATHER, consent_id)                        # a former guardian signs in her place

    def wallet_is_closed(did, consent_id):
        raise RuntimeError("the patient did not sign")
    elsewhere, _ = sign_consent(LAYAN, "another-consent")               # her signature, but for another consent
    for attempt in ({"sign": father_signs}, {"sign": wallet_is_closed}, {"signature": elsewhere},
                    {"signature": "0x" + "22" * 65}, {"signature": ""}, {"verify_sig": lambda did, cid, sig: False}):
        old, chain = minor(), Chain()
        before = copy.deepcopy(old)
        r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY, **attempt)
        assert r["status"] == "REFUSED" and r["reason"] == "PATIENT-SIGNATURE-INVALID", attempt
        assert chain.calls == [] and old == before                      # nothing is minted, the old consent stays
        assert rows(old.consent_id, "CAPACITY_TRANSITION")[-1]["metadata"]["reason"] == "PATIENT-SIGNATURE-INVALID"
        assert cap.evaluate_conditions(old, BIRTHDAY)["deny_codes"] == ["TRANSITION-PENDING"]
    # a did:key names its own key: the key rebuilt from the identifier string does not sign for such a patient
    old, chain = minor(patient_did="did:key:zQ3shokFTS3brHcDQrn82RUDfCZESWL1ZdCEJwekUDPQiYBme"), Chain()
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY)
    assert r["reason"] == "PATIENT-SIGNATURE-INVALID" and chain.calls == [] and old.successor_id is None


def approval_typed_data(did, consent_id):
    return encode_typed_data(domain_data=ids.DOMAIN, message_types=ids.TYPES,
                             message_data={"consentId": consent_id, "guardian": did, "action": "APPROVE"})


def test_patient_signs_the_prepared_consent_with_a_key_in_her_wallet():
    old, chain = minor(), Chain()
    wallet = Account.from_key(Web3.keccak(text="test wallet of the patient"))
    with pytest.raises(ValueError):
        cap.prepare_successor(old, EIGHTEEN - timedelta(days=1))        # nothing is due yet
    new = cap.prepare_successor(old, BIRTHDAY)
    assert new.guardian_dids == [LAYAN] and new.threshold == 1 and new.signatures == [] and new.token_id is None
    assert new.predecessor_id == old.consent_id and old.successor_id is None and stored(new.consent_id) is None
    new.guardian_addresses = {LAYAN: wallet.address}                   # the address her approval must recover to
    new.commitment = "0x" + "5a" * 32                                  # attached by the issuance before she signs
    signature = "0x" + bytes(wallet.sign_message(approval_typed_data(LAYAN, new.consent_id)).signature).hex()

    def wallet_check(did, consent_id, sig):
        return Account.recover_message(approval_typed_data(did, consent_id), signature=sig) == new.guardian_addresses.get(did)
    # the check with the derived key refuses a signature made with the wallet key
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY, successor=new, signature=signature)
    assert r["reason"] == "PATIENT-SIGNATURE-INVALID" and chain.calls == []
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY, successor=new, signature=signature,
                               verify_sig=wallet_check)
    assert r["status"] == "COMPLETED" and r["successor"] is new and old.successor_id == new.consent_id
    assert new.signature_data[LAYAN] == {"scheme": "EIP-712", "signer": wallet.address, "signature": signature}
    assert new.commitment == "0x" + "5a" * 32 and chain.calls == [("mint", new.consent_id), ("revoke", "SBT-1")]


@pytest.mark.parametrize("field, value", [
    ("scope", ["Observation", "Medication", "Condition", "Procedure", "Patient"]),     # a wider scope
    ("purpose", "Research"), ("requester_did", REGISTRAR), ("expiry_date", "2039-12-31T23:59:59"),
    ("start_date", "2026-01-01T00:00:00"), ("jurisdiction", "US"), ("patient_did", "did:patient:someone-else"),
    ("guardian_dids", [LAYAN, UNCLE]), ("guardian_dids", [UNCLE]), ("threshold", 2), ("triggers", []),
    ("transitions", []), ("attestations", [{"id": "att-x"}]), ("predecessor_id", "another-consent"),
    ("token_id", "SBT-77"), ("revoked", True), ("consent_id", None), ("guardian_addresses", {UNCLE: "0x" + "00" * 20}),
    ("patient_birth_date", "2000-01-01"), ("majority_age", 16)])
def test_prepared_consent_may_change_nothing_but_the_guardian_set(field, value):
    old, chain = minor(), Chain()
    trg.add_trigger(old, EVENT, now=NOW)                               # the trigger must be carried over as well
    new = cap.prepare_successor(old, BIRTHDAY)
    setattr(new, field, old.consent_id if field == "consent_id" else value)
    signature, _ = sign_consent(new.patient_did, new.consent_id)
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY, successor=new, signature=signature)
    assert r["status"] == "REFUSED" and r["reason"] == "SUCCESSOR-MISMATCH" and chain.calls == []
    assert old.successor_id is None and old.revoked is False
    assert field in rows(old.consent_id, "CAPACITY_TRANSITION")[-1]["metadata"]["fields"]


def test_failed_mint_changes_nothing_and_the_transition_can_be_repeated():
    old, chain = minor(), Chain(fail_mint=True)
    before = copy.deepcopy(old)
    for mint in (chain.mint, lambda c: {"status": 0, "tx_hash": "0x" + "ee" * 32}, lambda c: {"status": 1}, lambda c: None):
        r = cap.execute_transition(old, mint, chain.revoke, now=BIRTHDAY)
        assert r["status"] == "MINT-FAILED" and r["reason"] == "MINT-FAILED" and r["successor"] is None
        assert old == before and chain.calls == []                      # no link, no retirement, no revocation
        assert rows(old.consent_id, "CAPACITY_TRANSITION")[-1]["result"] == "FAILED"
    assert rows(old.consent_id, "CAPACITY_TRANSITION")[-3]["metadata"]["mint_tx"] == "0x" + "ee" * 32
    assert cap.evaluate_conditions(old, BIRTHDAY)["deny_codes"] == ["TRANSITION-PENDING"]
    chain.fail_mint = False
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY)
    assert r["status"] == "COMPLETED" and [kind for kind, _ in chain.calls] == ["mint", "revoke"]
    assert rows(r["successor_id"], "SIGN_CONSENT") and len(rows(old.consent_id, "CAPACITY_TRANSITION")) == 5


def test_failed_revocation_leaves_the_old_consent_retired_and_is_submitted_again():
    old, chain = minor(), Chain(fail_revoke=True)
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY)
    new = r["successor"]
    assert r["status"] == "REVOKE-PENDING" and r["reason"] == "REVOKE-FAILED" and chain.calls == [("mint", new.consent_id)]
    # off chain the old consent is retired already and gives no access, and the re-issued consent is in force
    assert old.revoked is True and old.successor_id == new.consent_id and new.predecessor_id == old.consent_id
    assert decide(old, NEXT_DAY)["ALLOW"] is False and decide(new, NEXT_DAY)["ALLOW"] is True
    assert old.transitions[0]["done"] is False and new.transitions[0]["done"] is True      # the old side is still open
    assert [(e["action"], e["result"]) for e in rows(old.consent_id)][-2:] == [
        ("ONCHAIN_REVOKE", "FAILED"), ("CAPACITY_TRANSITION", "REVOKE-PENDING")]
    assert cap.execute_transition(old, chain.mint, chain.revoke, now=NEXT_DAY)["status"] == "REVOKE-PENDING"
    assert chain.calls == [("mint", new.consent_id)]                    # the consent is not minted a second time
    chain.fail_revoke = False
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=NEXT_DAY)
    assert r["status"] == "COMPLETED" and r["successor_id"] == new.consent_id
    assert chain.calls == [("mint", new.consent_id), ("revoke", "SBT-1")] and old.transitions[0]["done"] is True
    assert [(e["action"], e["result"]) for e in rows(old.consent_id)][-2:] == [
        ("ONCHAIN_REVOKE", "SUCCESS"), ("CAPACITY_TRANSITION", "SUCCESS")]
    assert cap.execute_transition(old, chain.mint, chain.revoke, now=NEXT_DAY)["reason"] == "ALREADY-TRANSITIONED"
    # a revoke transaction that is mined but reverted counts as failed as well
    old2 = minor()
    r = cap.execute_transition(old2, chain.mint, lambda c: {"status": 0, "tx_hash": "0x" + "dd" * 32}, now=BIRTHDAY)
    assert r["status"] == "REVOKE-PENDING" and old2.revoked is True and old2.transitions[0]["done"] is False


def test_consent_that_was_never_minted_is_reissued_without_a_revocation():
    old, chain = minor(approvals=(FATHER,), token=None), Chain()        # one of two approvals when she turns eighteen
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY)
    new = r["successor"]
    assert r["status"] == "COMPLETED" and r["revoke"] is None and chain.calls == [("mint", new.consent_id)]
    assert old.revoked is True and old.successor_id == new.consent_id and old.transitions[0]["done"] is True
    assert decide(new, NEXT_DAY)["ALLOW"] is True and rows(old.consent_id, "ONCHAIN_REVOKE") == []
    assert rows(old.consent_id, "CAPACITY_TRANSITION")[-1]["metadata"]["onchain"] == ["mint"]


def test_transition_without_a_chain_writes_no_transaction_rows():
    old = minor(token="SBT-LOCAL-old")
    calls = []
    r = cap.execute_transition(old, mint=lambda c: f"SBT-LOCAL-{c.consent_id[:8]}",
                               revoke=lambda c: calls.append(c.token_id), now=BIRTHDAY)
    new = r["successor"]
    assert r["status"] == "COMPLETED" and new.token_id == f"SBT-LOCAL-{new.consent_id[:8]}" and calls == ["SBT-LOCAL-old"]
    assert [e["action"] for e in rows(new.consent_id)] == ["SIGN_CONSENT", "MINT_SBT"]
    assert rows(new.consent_id, "ONCHAIN_MINT") == [] and rows(old.consent_id, "ONCHAIN_REVOKE") == []
    assert all(e["tx_hash"] is None and e["onchain"] is False for e in rows(new.consent_id) + rows(old.consent_id))
    # a mint that records the token in the consent itself and returns nothing else is accepted too
    old2 = minor()
    r = cap.execute_transition(old2, mint=lambda c: setattr(c, "token_id", "7"), revoke=lambda c: None, now=BIRTHDAY)
    assert r["status"] == "COMPLETED" and r["successor"].token_id == "SBT-7"


def test_triggers_and_attestations_are_carried_into_the_reissued_consent():
    old, chain = minor(), Chain()
    done = trg.add_trigger(old, EVENT, now=NOW)
    waiting = trg.add_trigger(old, "second-opinion", now=NOW)
    assert trg.present_attestation(old, trg.sign_attestation(CLINICIAN, old, EVENT, signed_at=NOW), now=NOW)["VALID"] is True
    r = cap.execute_transition(old, chain.mint, chain.revoke, now=BIRTHDAY)
    new = r["successor"]
    assert r["status"] == "COMPLETED" and new.triggers == old.triggers and new.triggers is not old.triggers
    assert new.attestations == old.attestations and new.attestations[0]["consent_id"] == old.consent_id
    # the attestation recorded before the re-issue still satisfies its trigger, and the other trigger still waits
    ev = cap.evaluate_conditions(new, NEXT_DAY)
    assert ev["state"] == "SUSPENDED" and ev["deny_codes"] == ["AWAITING-TRIGGER"] and ev["waiting_triggers"] == [waiting["id"]]
    assert [t["satisfied"] for t in ev["triggers"]] == [True, False] and new.triggers[0]["id"] == done["id"]
    a = trg.sign_attestation(DR_MITCHELL, new, "second-opinion", signed_at=NEXT_DAY)
    assert trg.present_attestation(new, a, now=NEXT_DAY)["VALID"] is True
    assert cap.evaluate_conditions(new, NEXT_DAY)["state"] == "ACTIVE" and decide(new, NEXT_DAY)["ALLOW"] is True
    # the retired consent takes no attestation, and an attestation for an unrelated consent is still refused
    refused(old, trg.sign_attestation(DR_MITCHELL, old, "second-opinion", signed_at=NEXT_DAY), "CONSENT-REVOKED", now=NEXT_DAY)
    assert trg.verify_attestation_signature(new.attestations[0], consent()) is False


def test_transition_on_the_in_memory_chain_is_one_mint_and_one_revocation():
    """The two callables send real transactions to the ConsentSBTv3 bytecode of the report on the in-memory chain.
    The time of the evaluation is the timestamp of the latest block."""
    try:
        from web3 import EthereumTesterProvider
        from web3.logs import DISCARD
        w3 = Web3(EthereumTesterProvider())
    except Exception:
        pytest.skip("eth-tester not installed")
    from blockchain.contract import did_to_address
    with open(os.path.join(os.path.dirname(__file__), "..", "blockchain", "abi", "ConsentSBTv3.json")) as f:
        art = json.load(f)
    owner = w3.eth.accounts[0]
    factory = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    deployed = w3.eth.get_transaction_receipt(factory.constructor().transact({"from": owner}))
    sbt = w3.eth.contract(address=deployed.contractAddress, abi=art["abi"])
    sent = []

    def mint(c):
        window = [int(datetime.fromisoformat(d).timestamp()) for d in (c.start_date, c.expiry_date)]
        tx = sbt.functions.mintConsentV3(did_to_address(c.patient_did), did_to_address(c.requester_did), c.purpose,
                                         window[0], window[1], b"AU", 2).transact({"from": owner})
        receipt = w3.eth.get_transaction_receipt(tx); sent.append(("mint", tx))
        token = sbt.events.Transfer().process_receipt(receipt, errors=DISCARD)[0]["args"]["tokenId"]
        return {"token_id": token, "tx_hash": w3.to_hex(tx), "block_number": receipt.blockNumber, "status": receipt.status,
                "gas_used": receipt.gasUsed}

    def revoke(c):
        tx = sbt.functions.revoke(int(c.token_id[4:])).transact({"from": owner})
        receipt = w3.eth.get_transaction_receipt(tx); sent.append(("revoke", tx))
        return {"tx_hash": w3.to_hex(tx), "block_number": receipt.blockNumber, "status": receipt.status,
                "gas_used": receipt.gasUsed}

    now = datetime.fromtimestamp(w3.eth.get_block("latest").timestamp)   # the time comes from the chain
    yesterday = (now - timedelta(days=1)).date()
    try:
        born = yesterday.replace(year=yesterday.year - 18)
    except ValueError:                                                   # yesterday was 29 February
        born = date(yesterday.year - 18, 2, 28)
    old = consent(token=None, start_date=(now - timedelta(days=10)).isoformat(timespec="seconds"),
                  expiry_date=(now + timedelta(days=30)).isoformat(timespec="seconds"), patient_birth_date=born.isoformat())
    old.transitions.append({"id": "m-1", "kind": "majority", "due": cap.majority_date(born).isoformat(), "done": False})
    old.token_id = f"SBT-{mint(old)['token_id']}"                        # the issuance under the parents' approvals
    old_token = int(old.token_id[4:])
    assert sbt.functions.checkValid(old_token).call() is True
    sent.clear(); block_before = w3.eth.block_number
    r = cap.execute_transition(old, mint, revoke, now=now)
    new = r["successor"]
    assert r["status"] == "COMPLETED" and [kind for kind, _ in sent] == ["mint", "revoke"]
    assert w3.eth.block_number == block_before + 2                       # two transactions, one block each
    new_token = int(new.token_id[4:])
    assert new_token != old_token and sbt.functions.checkValid(new_token).call() is True
    assert sbt.functions.checkValid(old_token).call() is False           # the old token is revoked on chain
    assert rows(new.consent_id, "ONCHAIN_MINT")[0]["block_number"] == r["mint"]["block_number"]
    assert rows(old.consent_id, "ONCHAIN_REVOKE")[0]["tx_hash"] == r["revoke"]["tx_hash"]
    # the revocation carries the token identifier and nothing of the reason
    revoked = sbt.events.ConsentRevoked().process_receipt(w3.eth.get_transaction_receipt(sent[1][1]), errors=DISCARD)
    assert len(revoked) == 1 and revoked[0]["args"]["tokenId"] == old_token
    # neither transaction carries the date of birth or the day of majority, and the window is the one of the old consent
    for _, tx in sent:
        data = bytes(w3.eth.get_transaction(tx)["input"])
        for moment in (datetime(born.year, born.month, born.day), cap.majority_date(born)):
            assert int(moment.timestamp()).to_bytes(32, "big") not in data
        assert born.isoformat().encode() not in data and cap.majority_date(born).isoformat().encode() not in data
    record = sbt.functions.consents(new_token).call()
    assert record[3] == int(datetime.fromisoformat(old.start_date).timestamp()) and record[6] is False
