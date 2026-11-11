'''
Revocation by Crypto-Shredding for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11

Algorithm 6.4 (thesis Sections 6.2.4, 6.3.5 and 6.4.2). Revocation in HALAH is crypto-shredding in four steps:
- the on-chain revoke
- the deletion of the consent-bound encrypted copy where the store permits deletion, and the destruction of its
  keys, so that any copy that remains, in a backup or a replica, is unintelligible to every party, the operator
  included
- the deletion of the off-chain link between the token's per-consent address and the patient, so that nothing on
  chain identifies the patient
- the notification of every requester who received data under the consent, identified from the audit ledger
The audit record of the revocation is preserved.

The three limits of the claim, in the words of Section 6.2.4:
1. Revocation ends all future access, but it cannot recall data already delivered to an authorised recipient,
   which is why Article 19 of the GDPR asks the controller to notify recipients rather than to retrieve the data.
2. It does not erase the source record held by the treating institution, which keeps it under its own legal basis
   (Article 17(3)).
3. And a remaining copy stays unintelligible only while the encryption algorithm holds and the key was never
   compromised, as the final EDPB Guidelines 02/2025 (version 2, 7 July 2026) state at paragraph 51, where they
   also confirm that encrypted personal data is still personal data.
'''
# Who may revoke (thesis Section 6.2.5): the patient, or any one guardian before majority, and the patient alone
# after it. There is no threshold, because revoking only narrows access, and Article 7(3) of the GDPR requires
# withdrawal to be as easy as giving consent. The revoker shows control of a key by an EIP-712 signature over the
# revocation request. The typed data has its own primary type, so an approval signature is not a revocation.
#
# What revoke() does, in the order of Algorithm 6.4:
#   1. authenticates the revocation request and checks the authority of the revoker
#   2. marks the consent REVOKED, so that no decision allows a request while the next steps run, and submits the
#      on-chain revoke through the callable the caller gives
#   3. deletes the consent-bound encrypted copy and destroys its keys in the key store
#   4. deletes the off-chain link between the token and the patient, and the opening of the commitment
#   5. reads from E every requester who received data under the consent and sends each a notice
#   6. records the revoking party, the time and the notifications in E. No record of E is changed or removed.
# A consent that was re-issued at a capacity transition is one consent to the patient. Steps 3 to 5 therefore cover
# the consents that the revoked consent replaced as well: their copies and keys, their openings and links, and the
# requesters who received data under them.
# A failed on-chain revoke does not stop the withdrawal. The copy is deleted, the keys are destroyed, the opening
# is deleted, the recipients are notified and the failure is recorded. Only the link to the token is kept, because
# the token is still needed to revoke it on chain. complete_revocation() finishes what is pending and sends no
# notice twice.
#
# What is deleted in step 4 is the link in the consent record. The audit ledger keeps its records, as the chapter
# requires, and its ONCHAIN_MINT and ONCHAIN_REVOKE records name the transactions of the token beside the consent.
import copy
from datetime import date, datetime

from eth_account import Account
from eth_account.messages import encode_typed_data

from database import audit_db, consent_db
from services import data_vault, identity_service, notification_service

# ---------------------------------------------------------------------------
# The revocation request and its signature
# ---------------------------------------------------------------------------
REVOCATION_DOMAIN = {"name": "HALAH Consent", "version": "2"}
REVOCATION_TYPES = {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                                     {"name": "chainId", "type": "uint256"}],
                    "Revocation": [{"name": "consentId", "type": "string"}, {"name": "revoker", "type": "string"},
                                   {"name": "chainId", "type": "uint256"}, {"name": "action", "type": "string"}]}

# Reasons for which a revocation request is refused.
REFUSED_NOT_A_PARTY = "NOT-A-PARTY"                          # neither the patient nor a guardian of this consent
REFUSED_FORMER_GUARDIAN = "FORMER-GUARDIAN"                  # a guardian of the consent this one replaced
REFUSED_GUARDIAN_AFTER_MAJORITY = "GUARDIAN-AFTER-MAJORITY"  # after majority the patient alone may revoke
REFUSED_SIGNATURE_INVALID = "SIGNATURE-INVALID"              # the request is not signed by the key of the revoker
REFUSED_SUPERSEDED = "CONSENT-SUPERSEDED"                    # the consent was replaced, its successor is the one to revoke

# Passed as onchain_revoke for a consent that has no token on a chain (the demonstration mode without a chain).
NO_CHAIN = "NO_CHAIN"

# The fields of the consent record that hold the opening of a commitment, and the fields that link the patient to
# the token on chain. The openings are deleted with the revocation. The link is deleted once the token is revoked
# on chain, because the on-chain revoke needs the token.
OPENING_FIELDS = ("commitment_opening", "zk_secret")
TOKEN_FIELDS = ("token_address", "token_id", "commitment", "zk_commitment")
LINK_FIELDS = OPENING_FIELDS + TOKEN_FIELDS


def revocation_typed_data(did, consent_id, chain_id=None):
    """The typed data that the revoker signs: the consent identifier, the revoker, the chain identifier and the
    action REVOKE. It is the JSON a wallet takes in eth_signTypedData_v4."""
    chain = int(identity_service.CHAIN_ID if chain_id is None else chain_id)
    return {"types": {name: [dict(f) for f in fields] for name, fields in REVOCATION_TYPES.items()},
            "primaryType": "Revocation", "domain": dict(REVOCATION_DOMAIN, chainId=chain),
            "message": {"consentId": str(consent_id), "revoker": str(did), "chainId": chain, "action": "REVOKE"}}


def _signable(did, consent_id, chain_id):
    return encode_typed_data(full_message=revocation_typed_data(did, consent_id, chain_id))


def sign_revocation(did, consent_id, signer=None, chain_id=None):
    """Sign the request of `did` to revoke `consent_id`. Returns (signature, signer address). `signer` (an
    eth_account LocalAccount) stands for the wallet of the revoker. Without it the demonstration key derived from
    the identifier signs, which is kept for the test harness and the demonstration interface only."""
    signer = signer or identity_service.guardian_account(did)
    signature = signer.sign_message(_signable(did, consent_id, chain_id)).signature.hex()
    return (signature if signature.startswith("0x") else "0x" + signature), signer.address


def verify_revocation_signature(did, consent_id=None, signature=None, address=None, chain_id=None, allow_demo_key=True):
    """True only if `signature` is a valid EIP-712 request of `did` to revoke `consent_id` on this chain.
    `address` is the wallet address registered for the revoker (consent.guardian_addresses): when it is given, the
    recovered signer must equal it. Without an address the demonstration key derived from the identifier is
    accepted, unless allow_demo_key is False or the identifier is a did:key, which has no derived key."""
    if not (isinstance(did, str) and did and consent_id and signature):
        return False
    try:
        recovered = Account.recover_message(_signable(did, consent_id, chain_id), signature=signature)
    except Exception:
        return False
    if address is not None:
        return isinstance(address, str) and recovered.lower() == address.lower()
    if not allow_demo_key or did.startswith("did:key:"):
        return False
    return recovered == identity_service.guardian_address(did)


# ---------------------------------------------------------------------------
# Who may revoke
# ---------------------------------------------------------------------------
def _local(moment):
    return moment.astimezone().replace(tzinfo=None) if moment.tzinfo is not None else moment


def majority_reached(consent, now=None):
    """True when the patient has reached the age of majority at `now`, False when not, and None when the consent
    records neither a majority transition nor a date of birth. A majority transition of the consent decides
    first (it is reached when it is done or due). Otherwise the day of majority is the birthday in the year
    of birth plus majority_age, and 1 March for a birthday on 29 February in a year that has none."""
    now = _local(now or datetime.now())
    for t in (getattr(consent, "transitions", None) or []):
        if isinstance(t, dict) and t.get("kind") == "majority":
            if t.get("done") is True:
                return True
            try:
                return _local(datetime.fromisoformat(str(t["due"]))) <= now
            except Exception:
                continue
    try:
        born = datetime.fromisoformat(str(consent.patient_birth_date)).date()
        years = int(getattr(consent, "majority_age", 18))
    except Exception:
        return None
    try:
        day = born.replace(year=born.year + years)
    except ValueError:
        day = date(born.year + years, 3, 1)
    return now.date() >= day


def revocation_authority(consent, revoker_did, now=None, consent_store=None):
    """The authority rule of Algorithm 6.4: the patient may revoke at any time, any one guardian may revoke alone
    before majority, and after majority the patient alone may revoke. There is no threshold.
    Returns authorised, role (Patient or Guardian), basis or the reason of the refusal, and after_majority."""
    after = majority_reached(consent, now)
    result = {"authorised": False, "role": None, "basis": None, "reason": None, "after_majority": after}
    if isinstance(revoker_did, str) and revoker_did and revoker_did == consent.patient_did:
        result.update(authorised=True, role="Patient", basis="patient")
    elif isinstance(revoker_did, str) and revoker_did in (consent.guardian_dids or []):
        result["role"] = "Guardian"
        if after:
            result["reason"] = REFUSED_GUARDIAN_AFTER_MAJORITY
        else:
            result.update(authorised=True, basis="one guardian before majority")
    else:
        former = any(isinstance(revoker_did, str) and revoker_did in (c.guardian_dids or [])
                     for c in predecessors(consent, consent_store))
        result["reason"] = REFUSED_FORMER_GUARDIAN if former else REFUSED_NOT_A_PARTY
    return result


def predecessors(consent, consent_store=None):
    """The consents that this one replaced after a capacity transition, nearest first."""
    store = consent_store or consent_db
    found, seen, previous = [], {consent.consent_id}, getattr(consent, "predecessor_id", None)
    while previous and previous not in seen:
        seen.add(previous)
        earlier = store.get(previous)
        if earlier is None:
            break
        found.append(earlier)
        previous = getattr(earlier, "predecessor_id", None)
    return found


# ---------------------------------------------------------------------------
# The steps of crypto-shredding
# ---------------------------------------------------------------------------
def crypto_shred(consent_id, vault=None, now=None):
    """Algorithm 6.4, step 3: delete the consent-bound encrypted copy and destroy its keys in the key store.
    Returns the evidence of both, with the number of copies and keys that remain, which is zero. The capacity
    transition calls it for the consent it retires. It sends no notice."""
    vault = vault if vault is not None else data_vault.default_vault()
    deleted = vault.delete(consent_id, now=now)
    destroyed = vault.key_store.destroy(consent_id, now=now)
    return {"consent_id": consent_id, "modules_deleted": deleted["modules_deleted"],
            "copies_remaining": deleted["copies_remaining"], "keys_destroyed": destroyed["keys_destroyed"],
            "key_ids": destroyed["key_ids"], "keys_remaining": destroyed["keys_remaining"],
            "destroyed_at": destroyed["destroyed_at"],
            "shredded": deleted["copies_remaining"] == 0 and destroyed["keys_remaining"] == 0}


def _held(consent, fields):
    return [name for name in fields if getattr(consent, name, None) not in (None, "", {}, [])]


def unlink_consent(consent, fields=LINK_FIELDS):
    """Algorithm 6.4, step 4: delete from the consent record the opening of the commitment and the off-chain link
    between the token and the patient (the per-consent address, the token identifier and the commitment).
    Returns the names of the fields that held a value."""
    cleared = _held(consent, fields)
    for name in fields:
        if hasattr(consent, name):
            setattr(consent, name, None)
    return cleared


def _delete_token_link(consent, delete_link):
    """Delete the link between the token and the patient: first the link that is held outside the consent record,
    through the callable of the caller, which still sees the token, and then the fields of the record. A consent
    whose record holds no token any more has no link left, so the callable is not called for it a second time."""
    if delete_link is not None and _held(consent, TOKEN_FIELDS):
        delete_link(consent)
    return unlink_consent(consent, TOKEN_FIELDS)


def _onchain_confirmed(ledger, consent_id):
    return any(e.get("consent_id") == consent_id and e.get("action") == "ONCHAIN_REVOKE" and e.get("result") == "SUCCESS"
               for e in ledger.get())


def _submit_onchain(consent, onchain_revoke, ledger):
    """Algorithm 6.4, step 2: submit the on-chain revoke through the injected callable and record its receipt.
    The callable takes the consent and returns the receipt of the transaction as a dict: status (1 on success),
    tx_hash, block_number, gas_used and, when the contract keeps a revocation tree, revocation_root, the root
    after the revoke. The record in E holds the receipt and neither the token identifier nor its address."""
    if _onchain_confirmed(ledger, consent.consent_id):
        return {"status": "ALREADY_CONFIRMED"}
    if onchain_revoke == NO_CHAIN or not getattr(consent, "token_id", None):
        return {"status": "NOT_APPLICABLE"}
    if onchain_revoke is None:
        return {"status": "NOT_SUBMITTED", "error": "no on-chain revoke was given"}
    try:
        receipt = dict(onchain_revoke(consent))
        ok = receipt.get("status") in (1, True)
        outcome = {"status": "SUCCESS" if ok else "FAILED", "tx_hash": receipt.get("tx_hash"),
                   "block_number": receipt.get("block_number"), "gas_used": receipt.get("gas_used"),
                   "revocation_root": receipt.get("revocation_root"),
                   "error": None if ok else f"the transaction returned the status {receipt.get('status')!r}"}
    except Exception as failure:
        outcome = {"status": "FAILED", "tx_hash": None, "block_number": None, "gas_used": None,
                   "revocation_root": None, "error": str(failure)[:300]}
    ledger.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_REVOKE",
               patient_did=consent.patient_did, consent_id=consent.consent_id, result=outcome["status"],
               tx_hash=outcome["tx_hash"] if outcome["status"] == "SUCCESS" else None,
               block_number=outcome["block_number"] if outcome["status"] == "SUCCESS" else None,
               metadata={"gas_used": outcome["gas_used"], "revocation_root": outcome["revocation_root"],
                         "error": outcome["error"]})
    return outcome


# ---------------------------------------------------------------------------
# Algorithm 6.4
# ---------------------------------------------------------------------------
def _request_time(now, time_label):
    if now is None:
        return datetime.now(), "system-clock-fallback"
    return _local(now), time_label or "caller-supplied"


def _carry_out(consent, now, onchain_revoke, vault, delete_link, send, ledger, store):
    """Steps 2 to 5 of Algorithm 6.4 for a consent that is marked REVOKED. Every step can be repeated: a step that
    is done is not done twice. Returns the outcome of each step and what is still pending."""
    stamp = now.isoformat()
    replaced = predecessors(consent, store)
    lineage = [consent.consent_id] + [c.consent_id for c in replaced]
    # Step 2: submit the on-chain revoke.
    onchain = _submit_onchain(consent, onchain_revoke, ledger)
    onchain_done = onchain["status"] in ("SUCCESS", "ALREADY_CONFIRMED", "NOT_APPLICABLE")

    # Step 3: delete the encrypted copy and destroy its keys, for this consent and for the consents it replaced.
    shredded = {"consent_ids": lineage, "modules_deleted": [], "keys_destroyed": 0, "key_ids": [], "errors": []}
    for consent_id in lineage:
        try:
            evidence = crypto_shred(consent_id, vault, now=now)
            shredded["modules_deleted"] += [m for m in evidence["modules_deleted"] if m not in shredded["modules_deleted"]]
            shredded["keys_destroyed"] += evidence["keys_destroyed"]
            shredded["key_ids"] += [k for k in evidence["key_ids"] if k not in shredded["key_ids"]]
        except Exception as failure:
            shredded["errors"].append(f"{consent_id}: {str(failure)[:200]}")
    try:
        shredded["copies_remaining"] = sum(len(vault.modules(c)) for c in lineage)
        shredded["keys_remaining"] = sum(len(vault.key_store.key_ids(c)) for c in lineage)
    except Exception as failure:
        shredded["copies_remaining"] = shredded["keys_remaining"] = None
        shredded["errors"].append(str(failure)[:200])
    shredded["shredded"] = (not shredded["errors"] and shredded["copies_remaining"] == 0
                            and shredded["keys_remaining"] == 0)

    # Step 4: delete the opening of the commitment, and the off-chain link between the token and the patient, for
    # this consent and for the consents it replaced. An opening is deleted at once. A link to a token is kept while
    # that token is not revoked on chain, because the revoke needs it. The token of a consent that was replaced is
    # revoked by the capacity transition, which records it in E.
    link = {"status": "DELETED", "deleted": [], "deleted_in_replaced": {}, "kept_for_onchain_revoke": [], "errors": []}
    for member in [consent] + replaced:
        mine = member is consent
        cleared = link["deleted"] if mine else link["deleted_in_replaced"].setdefault(member.consent_id, [])
        try:
            try:
                cleared += unlink_consent(member, OPENING_FIELDS)
                token_revoked = onchain_done if mine else (onchain_revoke == NO_CHAIN or not getattr(member, "token_id", None)
                                                           or _onchain_confirmed(ledger, member.consent_id))
                if token_revoked:
                    cleared += _delete_token_link(member, delete_link)
                elif _held(member, TOKEN_FIELDS):
                    link["kept_for_onchain_revoke"].append(member.consent_id)
            finally:
                store.update(member)               # what is deleted from the record is deleted in the store as well
        except Exception as failure:
            link["errors"].append(f"{member.consent_id}: {str(failure)[:200]}")
    if link["errors"]:
        link["status"] = "FAILED"
    elif link["kept_for_onchain_revoke"]:
        link["status"] = "DEFERRED"

    # Step 5: every requester who received data under the consent is read from E and notified.
    sent = notification_service.notify_withdrawal(consent, withdrawn_at=getattr(consent, "revoked_at", None) or stamp,
                                                  send=send, audit=ledger, consent_ids=lineage[1:])

    pending = []
    if not onchain_done:
        pending.append("onchain_revoke")
    if not shredded["shredded"]:
        pending.append("crypto_shredding")
    if link["status"] != "DELETED":
        pending.append("link_deletion")
    pending += [f"notification:{n['recipient_did']}" for n in sent["notifications"] if n["status"] != notification_service.SENT]
    return {"onchain": onchain, "shredded": shredded, "link": link, "recipients": sent["recipients"],
            "notifications": sent["notifications"], "complete": not pending, "pending": pending}


def revoke(consent, revoker_did, signature=None, now=None, time_label=None, authenticate=None, onchain_revoke=None,
           vault=None, delete_link=None, send=None, audit=None, consent_store=None, allow_demo_key=True):
    """Algorithm 6.4: revoke a consent by crypto-shredding.

    consent         the stored consent
    revoker_did     who asks: the patient, or a guardian of the consent
    signature       the signature of the revoker over the revocation request (sign_revocation)
    now, time_label the time of the request and the label of its source (services/time_source.py)
    authenticate    another authentication, a callable (revoker_did, consent, signature) -> True
    onchain_revoke  callable (consent) -> receipt of the revoke transaction, or NO_CHAIN for a consent that has no
                    token on a chain. Without it the on-chain step is reported as not submitted and stays pending
    vault           the data vault (default: the vault of the Controller). Its key store holds the keys
    delete_link     callable (consent) that deletes a link to the token that is held outside the consent record.
                    It is called once the token is revoked on chain and before the token fields of the record
                    are cleared, for the consent and for each consent it replaced
    send            the transport of the notices (default: the inbox inside the Controller)
    audit           the audit ledger (default: database.audit_db)
    consent_store   the consent store (default: database.consent_db)
    allow_demo_key  False refuses a signature made with the key derived from the identifier

    Returns a dict: result (REVOKED, ALREADY_REVOKED or DENIED), revoked, reason, the revoker with role and basis,
    revoked_at, onchain, shredded, link, recipients, notifications, complete, pending and audit_event. A refused
    request returns result DENIED with the reason, and successor_id names the consent to revoke when the consent
    was replaced."""
    ledger = audit or audit_db
    store = consent_store or consent_db
    vault = vault if vault is not None else data_vault.default_vault()
    now, label = _request_time(now, time_label)
    stamp = now.isoformat()

    # Step 1: authenticate the revocation request. The authority rule has no threshold.
    authority = revocation_authority(consent, revoker_did, now, store)
    reason = authority["reason"]
    if authority["authorised"]:
        if authenticate is not None:
            signed = authenticate(revoker_did, consent, signature) is True
        else:
            addresses = getattr(consent, "guardian_addresses", None) or {}
            signed = verify_revocation_signature(revoker_did, consent.consent_id, signature,
                                                 address=addresses.get(revoker_did) if isinstance(addresses, dict) else None,
                                                 allow_demo_key=allow_demo_key)
        if not signed:
            reason = REFUSED_SIGNATURE_INVALID
        elif getattr(consent, "successor_id", None):
            reason = REFUSED_SUPERSEDED
    if reason is not None:
        event = ledger.log(actor_did=str(revoker_did), actor_role=authority["role"] or "Unknown", action="REVOKE_CONSENT",
                           patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                           purpose=consent.purpose, result="DENIED",
                           metadata={"reason": reason, "after_majority": authority["after_majority"],
                                     "successor_id": getattr(consent, "successor_id", None),
                                     "requested_at": stamp, "time_source": label})
        return {"result": "DENIED", "revoked": bool(getattr(consent, "revoked", False)), "reason": reason,
                "consent_id": consent.consent_id, "revoker_did": revoker_did, "revoker_role": authority["role"],
                "after_majority": authority["after_majority"], "successor_id": getattr(consent, "successor_id", None),
                "audit_event": event}

    # The consent is REVOKED from this moment, so no decision allows a request while the next steps run.
    already = bool(getattr(consent, "revoked", False))
    if not already:
        consent.revoked, consent.state = True, "REVOKED"
        consent.revoked_at, consent.revoked_by = stamp, revoker_did
        store.update(consent)
    steps = _carry_out(consent, now, onchain_revoke, vault, delete_link, send, ledger, store)

    # Step 6: record the revoking party, the time and the notifications in E.
    result = "ALREADY_REVOKED" if already else "REVOKED"
    event = ledger.log(actor_did=revoker_did, actor_role=authority["role"], action="REVOKE_CONSENT",
                       patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                       purpose=consent.purpose, result="SUCCESS",
                       metadata=dict(copy.deepcopy(steps), revocation=result, requested_by=revoker_did,
                                     revoked_by=getattr(consent, "revoked_by", None), revoker_role=authority["role"],
                                     basis=authority["basis"], after_majority=authority["after_majority"],
                                     revoked_at=getattr(consent, "revoked_at", None), requested_at=stamp,
                                     time_source=label))
    return dict(steps, result=result, revoked=True, reason=None, consent_id=consent.consent_id, revoker_did=revoker_did,
                revoker_role=authority["role"], basis=authority["basis"], after_majority=authority["after_majority"],
                revoked_at=getattr(consent, "revoked_at", None), time_source=label, audit_event=event)


def complete_revocation(consent, onchain_revoke=None, now=None, time_label=None, vault=None, delete_link=None, send=None,
                        audit=None, consent_store=None):
    """Finish the steps of a revocation that were left pending, for example after a failed on-chain revoke or a
    failed delivery of a notice. The consent must be revoked already: this function revokes nothing, so it needs
    no revoker, and the Controller may call it on its own. It repeats steps 2 to 5 of Algorithm 6.4, of which a
    step that is done is not done twice, and records the outcome in E as a REVOCATION_COMPLETION record."""
    if not getattr(consent, "revoked", False):
        raise ValueError("the consent is not revoked, a revocation is made by revoke()")
    ledger = audit or audit_db
    store = consent_store or consent_db
    vault = vault if vault is not None else data_vault.default_vault()
    now, label = _request_time(now, time_label)
    steps = _carry_out(consent, now, onchain_revoke, vault, delete_link, send, ledger, store)
    event = ledger.log(actor_did="System", actor_role="ConsentEngine", action="REVOCATION_COMPLETION",
                       patient_did=consent.patient_did, consent_id=consent.consent_id, scope=consent.scope,
                       purpose=consent.purpose, result="SUCCESS" if steps["complete"] else "PENDING",
                       metadata=dict(copy.deepcopy(steps), revoked_by=getattr(consent, "revoked_by", None),
                                     revoked_at=getattr(consent, "revoked_at", None), completed_at=now.isoformat(),
                                     time_source=label))
    return dict(steps, result="COMPLETED" if steps["complete"] else "PENDING", revoked=True,
                consent_id=consent.consent_id, revoked_at=getattr(consent, "revoked_at", None), audit_event=event)


# ---------------------------------------------------------------------------
# The three tests of Section 6.5.3
# ---------------------------------------------------------------------------
def revocation_evidence(consent, vault=None, audit=None, retained_copy=None, consent_store=None):
    """The deletion, unintelligibility and notification tests for a revoked consent, over the consent and the
    consents it replaced.
    deletion: the consent-bound copy is gone from the vault. unintelligibility: no key survives in the key store,
    the keys are recorded as destroyed, and no blob of `retained_copy` (a copy of the ciphertext kept before the
    revocation, as export_copy() gives it) opens. notification: every recipient recorded in E was notified.
    link_deleted: no consent record holds the opening of a commitment or a link to a token any more."""
    vault = vault if vault is not None else data_vault.default_vault()
    keys = vault.key_store
    opened = []
    for module, blob in (retained_copy or {}).items():
        try:
            keys.decrypt(blob["consent_id"], blob["module"], bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ciphertext"]))
            opened.append(module)
        except Exception:
            pass
    replaced = predecessors(consent, consent_store)
    lineage = [consent.consent_id] + [c.consent_id for c in replaced]
    notice = notification_service.notification_check(consent.consent_id, audit, consent_ids=lineage[1:])
    return {"consent_id": consent.consent_id, "consent_ids": lineage,
            "deletion": not any(vault.has_copy(c) for c in lineage),
            "unintelligibility": (not any(keys.has_key(c) for c in lineage) and all(keys.is_destroyed(c) for c in lineage)
                                  and not opened),
            "link_deleted": not any(_held(c, LINK_FIELDS) for c in [consent] + replaced),
            "retained_blobs_tested": len(retained_copy or {}), "retained_blobs_opened": opened,
            "notification": notice["complete"], "recipients": notice["recipients"], "missing_notifications": notice["missing"]}
