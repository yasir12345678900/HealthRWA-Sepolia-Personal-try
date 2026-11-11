'''
Credential Status List for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# The credential status check that Algorithm 5.1 adds at line 13.
#
# revoke_credential(credential)        -> the issuer sets the credential's bit and publishes the next signed list
# is_revoked(credential)               -> the verifier reads that bit from a list whose signature it has checked
# check_status(credential)             -> the same answer with the list, the position and the sequence, for the evidence
# sign_status_list / verify_status_list / publish_status_list -> the issuer and verifier steps, one by one
# The first three take the credential itself, or the identifier of its subject when the credential is in the store.
#
# MECHANISM: a bitstring status list in the encoding of the W3C Bitstring Status List v1.0 recommendation. The issuer
# keeps one list of LIST_SIZE bits for the purpose "revocation". Bit i is 1 once the credential at position i is
# revoked. The list is compressed with GZIP, written as multibase base64url and signed by the issuer as EIP-712 typed
# data, the same proof type the role credentials carry. A verifier accepts a list only when its signature recovers to
# the registered address of the issuer of the credential.
# POSITION: a credential issued with a status entry (issue_credential(..., status_index=i)) carries its position in
# credentialStatus, under the issuer's signature. The seven demonstration credentials were issued before this check
# and carry no entry. Their position is derived from the credential identifier, which the issuer did sign, so they
# need no re-issue. Two identifiers can derive the same position. That revokes a second credential with the first
# and never hides a revocation, and it does not occur among the demonstration credentials.
# REVOCATION IS NOT REVERSIBLE: a published list never clears a bit and never lowers its sequence number. The verifier
# also remembers the newest sequence it has seen while the process runs and refuses an older list. A restart forgets
# that sequence, so a published file that is rolled back while the server is stopped is not detected.
# STORE: the published lists are kept in one JSON file (status_list_path), one shelf for each issuer. The file stands
# for the place where an issuer publishes its list. Nothing is fetched from a network.
# DEMONSTRATION ISSUER MODEL: until the issuer publishes a list, the empty list signed with the demonstration issuer
# key stands in for it, and revoke_credential signs with that key unless another signer is passed. The key can be
# rebuilt from the source (services/identity_service.py), so this shows the status check, not the secrecy of the key.
import base64
import gzip
import json
import os
import threading
import zlib
from datetime import datetime
from eth_account import Account
from eth_account.messages import encode_typed_data
from eth_utils import keccak
from database import db
from services import identity_service as ids

LIST_SIZE = 131072                   # bits. The smallest list the recommendation allows, so that a position hides in a crowd.
STATUS_PURPOSE = "revocation"
ENTRY_TYPE = "BitstringStatusListEntry"
STATUS_DOMAIN = {"name": "HALAH Credential Status", "version": "1"}
STATUS_TYPES = {"StatusList": [{"name": "id", "type": "string"}, {"name": "issuer", "type": "string"},
                               {"name": "statusPurpose", "type": "string"}, {"name": "encodedList", "type": "string"},
                               {"name": "sequence", "type": "uint256"}, {"name": "validFrom", "type": "string"}]}
INITIAL_VALID_FROM = "2026-01-01T00:00:00"

_LOCK = threading.Lock()
_seen = {}            # (store path, issuer, list identifier) -> newest sequence this process has accepted
_verified = {}        # signed list (as text) and trusted address -> its decoded bits
_initial = {}         # stand-in empty lists of the demonstration issuer


class StatusListError(Exception):
    """The status of a credential cannot be established. The caller must treat the credential as not valid."""


# ---------------------------------------------------------------------------
# The bitstring
# ---------------------------------------------------------------------------
def encode_list(bits):
    """GZIP, then base64url without padding, with the multibase prefix u."""
    if len(bits) != LIST_SIZE // 8:
        raise StatusListError("the status list has the wrong length")
    return "u" + base64.urlsafe_b64encode(gzip.compress(bytes(bits), mtime=0)).decode().rstrip("=")


def decode_list(encoded):
    """The LIST_SIZE bits of an encoded list. Nothing longer is ever expanded."""
    try:
        if not encoded.startswith("u"):
            raise ValueError("not multibase base64url")
        raw = base64.urlsafe_b64decode(encoded[1:] + "=" * (-len(encoded[1:]) % 4))
        unpack = zlib.decompressobj(wbits=31)
        bits = unpack.decompress(raw, LIST_SIZE // 8 + 1)
        if len(bits) != LIST_SIZE // 8 or not unpack.eof or unpack.unconsumed_tail or unpack.unused_data:
            raise ValueError("wrong length")
    except Exception as e:
        raise StatusListError(f"the encoded status list cannot be read ({e})")
    return bits


def _bit(bits, index):
    # Position 0 is the left-most bit of the first byte, as the recommendation orders the list.
    return bool(bits[index // 8] & (0x80 >> (index % 8)))


# ---------------------------------------------------------------------------
# Where a credential sits
# ---------------------------------------------------------------------------
def _credential(credential):
    """A credential, given as itself or as the identifier of its subject (then read from the credential store)."""
    if isinstance(credential, str):
        found = ids.get_credential(credential)
        if found is None:
            raise StatusListError("the credential store holds no credential for this identifier")
        return found
    return credential


def _issuer_of(credential):
    issuer = credential.get("issuer") if isinstance(credential, dict) else None
    issuer = issuer.get("id") if isinstance(issuer, dict) else issuer
    if not isinstance(issuer, str) or not issuer:
        raise StatusListError("the credential names no issuer")
    return issuer


def default_list_id(issuer_did):
    return f"urn:halah:status:{issuer_did}:{STATUS_PURPOSE}"


def status_entry(credential):
    """(list identifier, position) of a credential. Read the entry only from a credential whose signature has been
    verified: an entry is trusted because the issuer signed it."""
    issuer = _issuer_of(credential)
    entry = credential.get("credentialStatus")
    if entry is None:
        cred_id = credential.get("id")
        if not isinstance(cred_id, str) or not cred_id:
            raise StatusListError("the credential has neither a status entry nor an identifier")
        return default_list_id(issuer), int.from_bytes(keccak(text=cred_id), "big") % LIST_SIZE
    try:
        if entry.get("type") != ENTRY_TYPE or entry.get("statusPurpose") != STATUS_PURPOSE:
            raise ValueError("not a revocation entry")
        list_id, text = entry.get("statusListCredential"), entry.get("statusListIndex")
        if not (isinstance(list_id, str) and list_id and isinstance(text, str) and text.isascii() and text.isdigit()):
            raise ValueError("malformed entry")
        index = int(text)
        if index >= LIST_SIZE:
            raise ValueError("position outside the list")
    except Exception as e:
        raise StatusListError(f"the status entry cannot be read ({e})")
    return list_id, index


# ---------------------------------------------------------------------------
# Issuer side: sign a list
# ---------------------------------------------------------------------------
def _signable(status_list):
    subject = status_list.get("credentialSubject") or {}
    return encode_typed_data(domain_data=STATUS_DOMAIN, message_types=STATUS_TYPES, message_data={
        "id": str(status_list.get("id", "")), "issuer": str(status_list.get("issuer", "")),
        "statusPurpose": str(subject.get("statusPurpose", "")), "encodedList": str(subject.get("encodedList", "")),
        "sequence": status_list.get("sequence"), "validFrom": str(status_list.get("validFrom", ""))})


def sign_status_list(issuer_did, bits, sequence, list_id=None, signer=None, valid_from=None):
    """The status list credential of `issuer_did` over `bits`. `signer` (an eth_account LocalAccount) defaults to
    the demonstration issuer key."""
    list_id = list_id or default_list_id(issuer_did)
    status_list = {"@context": ["https://www.w3.org/ns/credentials/v2"], "id": list_id,
                   "type": ["VerifiableCredential", "BitstringStatusListCredential"], "issuer": issuer_did,
                   "validFrom": valid_from or datetime.now().isoformat(timespec="seconds"), "sequence": int(sequence),
                   "credentialSubject": {"id": f"{list_id}#list", "type": "BitstringStatusList",
                                         "statusPurpose": STATUS_PURPOSE, "encodedList": encode_list(bits)}}
    acct = signer or ids._issuer_account(issuer_did)
    sig = acct.sign_message(_signable(status_list)).signature.hex()
    status_list["proof"] = {"type": "EthereumEip712Signature2021", "proofPurpose": "assertionMethod",
                            "verificationMethod": ids.assertion_method(issuer_did),
                            "proofValue": sig if sig.startswith("0x") else "0x" + sig}
    return status_list


# ---------------------------------------------------------------------------
# Verifier side: check a list
# ---------------------------------------------------------------------------
def verify_status_list(status_list, issuer_did=None, list_id=None):
    """The bits of a status list, after checking that it is the list asked for, that its issuer is trusted and that
    its signature recovers to the issuer's registered address. Raises StatusListError otherwise."""
    if not isinstance(status_list, dict) or not isinstance(status_list.get("credentialSubject"), dict):
        raise StatusListError("the status list is malformed")
    issuer, subject, sequence = status_list.get("issuer"), status_list["credentialSubject"], status_list.get("sequence")
    if issuer_did is not None and issuer != issuer_did:
        raise StatusListError("the status list comes from another issuer")
    if list_id is not None and status_list.get("id") != list_id:
        raise StatusListError("this is not the status list the credential names")
    expected = ids.TRUSTED_ISSUERS.get(issuer) if isinstance(issuer, str) else None
    if expected is None:
        raise StatusListError("the issuer of the status list is not trusted")
    if subject.get("statusPurpose") != STATUS_PURPOSE:
        raise StatusListError("the status list does not record revocation")
    if type(sequence) is not int or sequence < 0:
        raise StatusListError("the status list has no sequence number")
    key = (json.dumps(status_list, sort_keys=True, default=str), expected)
    if key not in _verified:
        try:
            recovered = Account.recover_message(_signable(status_list), signature=(status_list.get("proof") or {}).get("proofValue"))
        except Exception:
            recovered = None
        if recovered != expected:
            raise StatusListError("the status list is not signed by its issuer")
        if len(_verified) >= 16:
            _verified.clear()
        _verified[key] = decode_list(subject.get("encodedList"))
    return _verified[key]


# ---------------------------------------------------------------------------
# The published list
# ---------------------------------------------------------------------------
def status_list_path():
    """File that holds the published lists: env HALAH_STATUS_LIST_PATH, or credential_status.json beside the database."""
    return os.environ.get("HALAH_STATUS_LIST_PATH") or os.path.join(os.path.dirname(db.db_path()), "credential_status.json")


def _read_store():
    """The published lists: issuer identifier -> list identifier -> signed list. Each issuer has its own shelf, so
    one issuer cannot publish under a list identifier that another issuer uses."""
    try:
        with open(status_list_path(), encoding="utf-8") as f:
            lists = json.load(f).get("statusLists")
    except FileNotFoundError:
        return {}
    except Exception as e:                     # a store that cannot be read is not the same as nothing revoked
        raise StatusListError(f"the published status lists cannot be read ({e})")
    if not isinstance(lists, dict) or not all(isinstance(shelf, dict) for shelf in lists.values()):
        raise StatusListError("the published status lists are malformed")
    return lists


def _initial_list(issuer_did, list_id):
    """The empty list of the demonstration issuer, used until a list is published."""
    key = (issuer_did, list_id)
    if key not in _initial:
        _initial[key] = sign_status_list(issuer_did, bytes(LIST_SIZE // 8), 0, list_id=list_id, valid_from=INITIAL_VALID_FROM)
    return _initial[key]


def current_status_list(issuer_did, list_id=None):
    """The newest published list of `issuer_did`. It is returned as stored: the caller verifies it."""
    list_id = list_id or default_list_id(issuer_did)
    return _read_store().get(issuer_did, {}).get(list_id) or _initial_list(issuer_did, list_id)


def _accept_sequence(issuer_did, list_id, sequence):
    # A list older than the newest one this process has seen is a replay of a state before a revocation.
    key = (status_list_path(), issuer_did, list_id)
    if sequence < _seen.get(key, 0):
        raise StatusListError("the status list is older than the newest list seen")
    _seen[key] = sequence


def publish_status_list(status_list):
    """Store a signed list as the current one. The list must verify, carry a higher sequence number than the list it
    replaces and keep every bit that list has set."""
    with _LOCK:
        return _publish(status_list)


def _publish(status_list):
    new_bits = verify_status_list(status_list)
    list_id, issuer = status_list.get("id"), status_list["issuer"]
    if not isinstance(list_id, str) or not list_id:
        raise StatusListError("the status list has no identifier")
    lists = _read_store()
    stored = lists.get(issuer, {}).get(list_id)
    if stored is None:
        old_bits, old_sequence = bytes(LIST_SIZE // 8), 0
    else:                                      # the list it replaces must itself be a genuine list of this issuer
        old_bits, old_sequence = verify_status_list(stored, issuer_did=issuer, list_id=list_id), stored["sequence"]
    if status_list["sequence"] <= old_sequence:
        raise StatusListError("the sequence number must increase")
    if any(o & ~n for o, n in zip(old_bits, new_bits)):
        raise StatusListError("revocation is not reversible: the new list clears a revoked position")
    lists.setdefault(issuer, {})[list_id] = status_list
    path = status_list_path()
    if os.path.dirname(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"statusLists": lists}, f, indent=1)
        f.write("\n")
    os.replace(path + ".tmp", path)
    _accept_sequence(issuer, list_id, status_list["sequence"])
    return status_list


def revoke_credential(credential, signer=None, now=None):
    """Issuer step: mark `credential` revoked and publish the next list. `credential` is the credential, or the
    identifier of its subject when the credential is in the store. `signer` defaults to the demonstration issuer key.
    A signer that is not the issuer of the credential is refused. Revoking twice changes nothing."""
    credential = _credential(credential)
    issuer = _issuer_of(credential)
    list_id, index = status_entry(credential)
    acct = signer or ids._issuer_account(issuer)
    if ids.TRUSTED_ISSUERS.get(issuer) != acct.address:
        raise StatusListError("only the issuer of a credential can revoke it")
    with _LOCK:
        current = _read_store().get(issuer, {}).get(list_id)
        if current is None:
            bits, sequence = bytearray(LIST_SIZE // 8), 0
        else:
            bits, sequence = bytearray(verify_status_list(current, issuer_did=issuer, list_id=list_id)), current["sequence"]
            if _bit(bits, index):
                return current
        bits[index // 8] |= 0x80 >> (index % 8)
        valid_from = (now or datetime.now()).isoformat(timespec="seconds")
        return _publish(sign_status_list(issuer, bits, sequence + 1, list_id=list_id, signer=acct, valid_from=valid_from))


def check_status(credential, status_list=None):
    """Verifier step: the status of `credential` with the list that answered. Verify the credential's own signature
    first (see status_entry). `status_list` defaults to the published list. Raises StatusListError when no trusted,
    current list answers."""
    credential = _credential(credential)
    issuer = _issuer_of(credential)
    list_id, index = status_entry(credential)
    status_list = status_list if status_list is not None else current_status_list(issuer, list_id)
    bits = verify_status_list(status_list, issuer_did=issuer, list_id=list_id)
    _accept_sequence(issuer, list_id, status_list["sequence"])
    return {"revoked": _bit(bits, index), "status_list": list_id, "index": index, "sequence": status_list["sequence"]}


def is_revoked(credential, status_list=None):
    """True when the issuer has revoked `credential` (the credential, or the identifier of its subject when the
    credential is in the store). Raises StatusListError when the status cannot be established."""
    return check_status(credential, status_list=status_list)["revoked"]
