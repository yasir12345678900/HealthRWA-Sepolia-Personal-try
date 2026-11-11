'''
Notification of Recipients for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# The notification step of revocation (Algorithm 6.4, thesis Sections 6.2.4 and 6.3.5).
#
# Revocation cannot recall data that was already delivered to an authorised recipient. What the Controller can do,
# and what Article 19 of the GDPR asks of it, is to tell every recipient that the consent was withdrawn. This
# module finds the recipients and tells them.
#
# - recipients_of() reads the audit ledger E. A recipient is a requester with a DATA_ACCESS record whose outcome is
#   GRANTED under the consent. A denied request delivered nothing, so it makes no recipient.
# - notify_withdrawal() sends one notice to every recipient who has not received one for this consent, and
#   records each notice in E as a WITHDRAWAL_NOTIFICATION record.
# - notification_check() is the notification test of Section 6.5.3: every recipient recorded in E was notified.
#
# In the prototype a notice is delivered to the inbox of the recipient inside the Controller: it is recorded in E,
# where inbox() reads it for the clinician interface, and it is placed in OUTBOX. No message leaves the system. A
# deployment passes its own transport as `send`.
import uuid
from datetime import datetime

from database import audit_db

ACTION = "WITHDRAWAL_NOTIFICATION"
NOTICE_TYPE = "CONSENT_WITHDRAWN"
SENT, FAILED = "SENT", "FAILED"

# Notices delivered by the local transport of the prototype, in the order in which they were sent.
OUTBOX = []


def deliver_locally(notice):
    """The transport of the prototype: the notice is placed in the outbox of the Controller."""
    OUTBOX.append(dict(notice))


def _rows(audit, consent_ids):
    wanted = set(consent_ids)
    return [e for e in (audit or audit_db).get() if e.get("consent_id") in wanted]


def recipients_of(consent_ids, audit=None):
    """Every requester who received data under the consent, read from the audit ledger E. `consent_ids` is one
    consent identifier or a list of them (a consent and the consents it replaced). Returns one entry for each
    recipient: the number of releases, the first and the last, the modules received, the DATA_ACCESS records
    that show it, and the consents under which the data was received."""
    if isinstance(consent_ids, str):
        consent_ids = [consent_ids]
    found = {}
    for e in _rows(audit, consent_ids):
        if e.get("action") != "DATA_ACCESS" or e.get("result") != "GRANTED" or not e.get("actor_did"):
            continue
        r = found.setdefault(e["actor_did"], {"recipient_did": e["actor_did"], "releases": 0, "first_release": e.get("timestamp"),
                                              "last_release": e.get("timestamp"), "modules": [], "access_event_ids": [],
                                              "received_under": []})
        r["releases"] += 1
        r["last_release"] = e.get("timestamp")
        r["access_event_ids"].append(e.get("event_id"))
        for module in (e.get("scope") or []):
            if module not in r["modules"]:
                r["modules"].append(module)
        if e.get("consent_id") not in r["received_under"]:
            r["received_under"].append(e.get("consent_id"))
    return list(found.values())


def notified(consent_id, audit=None):
    """The recipients who were sent a notice of the withdrawal of this consent, recipient -> its record in E."""
    return {e["metadata"]["recipient_did"]: e for e in _rows(audit, [consent_id])
            if e.get("action") == ACTION and e.get("result") == SENT and isinstance(e.get("metadata"), dict)
            and e["metadata"].get("recipient_did")}


def build_notice(consent, recipient, withdrawn_at):
    """The notice for one recipient. It names the consent, the patient whose data the recipient received, what
    was received and when, and what the withdrawal means. It carries no record data."""
    return {"notification_id": str(uuid.uuid4()), "type": NOTICE_TYPE, "recipient_did": recipient["recipient_did"],
            "consent_id": consent.consent_id, "patient_did": consent.patient_did, "withdrawn_at": withdrawn_at,
            "releases": recipient["releases"], "first_release": recipient["first_release"],
            "last_release": recipient["last_release"], "modules": list(recipient["modules"]),
            "received_under": list(recipient["received_under"]),
            "message": ("The consent under which you received these record modules has been withdrawn. No further "
                        "access is given under it. The data delivered to you earlier is not recalled by this system.")}


def notify_withdrawal(consent, withdrawn_at=None, send=None, audit=None, consent_ids=None):
    """Algorithm 6.4, the notification step: read from E every requester who received data under the consent and
    send each a notice of the withdrawal. A recipient who already has a notice for this consent is not sent a
    second one, so the step can be repeated after a failed delivery. `send` is the transport, a callable that
    takes the notice and raises when it cannot deliver. `consent_ids` adds the consents this one replaced.
    Every notice is recorded in E with the result SENT or FAILED. Returns the recipients found and one entry for
    each recipient with the status of the notice."""
    ledger = audit or audit_db
    send = send or deliver_locally
    withdrawn_at = withdrawn_at or datetime.now().isoformat()
    ids = [consent.consent_id] + [c for c in (consent_ids or []) if c != consent.consent_id]
    recipients = recipients_of(ids, ledger)
    already = notified(consent.consent_id, ledger)
    outcome = []
    for recipient in recipients:
        did = recipient["recipient_did"]
        if did in already:
            outcome.append({"recipient_did": did, "status": SENT, "new": False,
                            "notification_id": already[did]["metadata"].get("notification_id")})
            continue
        notice = build_notice(consent, recipient, withdrawn_at)
        status, error = SENT, None
        try:
            send(notice)
        except Exception as failure:
            status, error = FAILED, str(failure)[:300]
        ledger.log(actor_did="System", actor_role="NotificationService", action=ACTION,
                   patient_did=consent.patient_did, consent_id=consent.consent_id, scope=list(recipient["modules"]),
                   purpose=consent.purpose, result=status,
                   metadata={"notification_id": notice["notification_id"], "type": NOTICE_TYPE, "recipient_did": did,
                             "withdrawn_at": withdrawn_at, "releases": recipient["releases"],
                             "first_release": recipient["first_release"], "last_release": recipient["last_release"],
                             "access_event_ids": list(recipient["access_event_ids"]),
                             "received_under": list(recipient["received_under"]), "message": notice["message"],
                             "error": error})
        outcome.append({"recipient_did": did, "status": status, "new": True, "notification_id": notice["notification_id"],
                        "error": error})
    return {"recipients": [r["recipient_did"] for r in recipients], "notifications": outcome,
            "all_notified": all(o["status"] == SENT for o in outcome)}


def notification_check(consent_id, audit=None, consent_ids=None):
    """The notification test of Section 6.5.3: every recipient recorded in E was notified. Returns the recipients,
    those with a notice, those without one, and `complete`, which is true when nobody is missing."""
    ids = [consent_id] + [c for c in (consent_ids or []) if c != consent_id]
    recipients = [r["recipient_did"] for r in recipients_of(ids, audit)]
    done = notified(consent_id, audit)
    missing = [r for r in recipients if r not in done]
    return {"consent_id": consent_id, "recipients": recipients, "notified": [r for r in recipients if r in done],
            "missing": missing, "complete": not missing}


def inbox(recipient_did, audit=None):
    """The notices sent to one recipient, read from E, oldest first. The clinician interface shows them."""
    return [dict(e["metadata"], consent_id=e.get("consent_id"), patient_did=e.get("patient_did"),
                 modules=e.get("scope"), recorded_at=e.get("timestamp"))
            for e in (audit or audit_db).get()
            if e.get("action") == ACTION and e.get("result") == SENT and isinstance(e.get("metadata"), dict)
            and e["metadata"].get("recipient_did") == recipient_did]
