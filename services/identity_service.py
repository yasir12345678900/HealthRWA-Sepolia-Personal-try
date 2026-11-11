"""
DID/VC + EIP-712 guardian approval for SRQ2 (HALAH v1.3), extended to the thesis design of Chapter 5
is_valid_did(did)                      -> DID syntax check (W3C DID Core: did:<method>:<method-specific-id>)
verify_vc(did, role=None, credential=None, now=None)
                                       -> the participant's verifiable credential is valid (original report, RO2 Step 4):
                                          VC_valid = Sig_VC AND Issuer_valid AND Subject_match AND Time_valid,
                                          and its role claim matches the role the step requires (RO2 Steps 5-6)
check_credential(...)                  -> the same checks, one by one, for the screens and the audit evidence
verify_identity(did, role=None, now=None)
                                       -> Algorithm 5.1 in full: resolve the DID (services/did_resolver.py), verify its
                                          document, retrieve the credential, verify its four conditions and its status
                                          (services/credential_status.py), match the role claim to the authority the
                                          step requires and record the evidence. Returns an IdentityResult, VALID or
                                          INVALID with one reason code, that can be passed as verify_did to evaluate_allow
guardian_address(did) | sign_consent(did, consent_id) -> (sig, addr)
verify_signature(did, consent_id, signature) -> bool  (ecrecover of typed data == guardian address)
sign_consent_v2(did, consent_id, commitment) -> (sig, addr)
verify_signature_v2(did, consent_id, commitment, signature, address=None) -> bool
                                       -> the approval of Algorithm 5.2: EIP-712 typed data over the consent identifier,
                                          the guardian identifier, the consent commitment c and the chain identifier
approval_typed_data(did, consent_id, commitment) -> the JSON a wallet signs (eth_signTypedData_v4)
approval_verifier(consent)             -> the same check for one consent, as the verify_sig argument of evaluate_allow
DEMO KEY MODEL: the guardian key is derived from its DID so the prototype can sign without wallets.
In production the guardian's own wallet signs the SAME typed data; only verify_signature() is used.
WALLET-HELD KEYS: verify_signature_v2 takes the guardian's wallet address (consent.guardian_addresses) and accepts only
a signature that recovers to it, so the server cannot produce the approval. Without an address, a did:key guardian is
checked against the key in its own identifier, and any other identifier against the derived key. The derived key can
be rebuilt by anyone from the identifier, and it is kept for the automated test harness only: a caller outside the
harness passes allow_demo_key=False, and an approval without a registered wallet address or a did:key is then refused.
The address registered for a demonstration identifier is a field of the consent record, which the server holds, so
that binding rests on the server. The binding of a did:key guardian is the identifier itself and rests on nobody.
DEMO ISSUER MODEL: the credentials in data/credentials/demo_credentials.json are signed by one demo issuer whose key is
derived from a fixed tag (tools/issue_demo_credentials.py). In production the issuer signs with its own key and the
verifier only needs the issuer's registered address (TRUSTED_ISSUERS). Like the guardian demo keys, the demo issuer
key can be reproduced from the source, so the credential check demonstrates the verification, not the secrecy of the
issuer key. DID resolution is implemented for the did:key method, and the demonstration identifiers resolve through a
local resolver. Proof that a requester controls the DID they enter (holder binding by challenge and response) is not
implemented yet; a guardian shows control of a wallet key through the approval signature.
"""
import json
import os
import re
from datetime import datetime
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

DEMO_KEY_TAG = os.environ.get("HALAH_DEMO_KEY_TAG", "HALAH-DEMO-GUARDIAN-KEY-v1")
CHAIN_ID = int(os.environ.get("CHAIN_ID", "11155111"))
DOMAIN = {"name": "HALAH Consent", "version": "1", "chainId": CHAIN_ID}
TYPES = {"Approval": [{"name": "consentId", "type": "string"}, {"name": "guardian", "type": "string"}, {"name": "action", "type": "string"}]}

# ---------------------------------------------------------------------------
# DID syntax (W3C DID Core 1.0, section 3.1): did:<method-name>:<method-specific-id>
# ---------------------------------------------------------------------------
_IDCHAR = r"(?:[A-Za-z0-9._-]|%[0-9A-Fa-f]{2})"
_DID_RE = re.compile(r"^did:[a-z0-9]+:(?:" + _IDCHAR + r"*:)*" + _IDCHAR + r"+$")


def is_valid_did(did):
    return isinstance(did, str) and bool(_DID_RE.fullmatch(did))


# ---------------------------------------------------------------------------
# Verifiable credentials (demo issuer)
# ---------------------------------------------------------------------------
DEMO_ISSUER_KEY_TAG = os.environ.get("HALAH_DEMO_ISSUER_KEY_TAG", "HALAH-DEMO-ISSUER-KEY-v1")
ISSUER_DID = "did:halah:issuer:demo-health-authority"
CRED_DOMAIN = {"name": "HALAH Credential", "version": "1"}
CRED_TYPES = {"Credential": [{"name": "id", "type": "string"}, {"name": "issuer", "type": "string"},
                             {"name": "subject", "type": "string"}, {"name": "role", "type": "string"},
                             {"name": "organisation", "type": "string"}, {"name": "validFrom", "type": "string"},
                             {"name": "validUntil", "type": "string"}]}
CREDENTIALS_PATH = os.environ.get(
    "HALAH_CREDENTIALS_PATH",
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "credentials", "demo_credentials.json"))


def _issuer_account(issuer_did):
    return Account.from_key(Web3.keccak(text=f"{DEMO_ISSUER_KEY_TAG}|{issuer_did}"))


# Registry of trusted issuers: issuer DID -> the address its credential signatures must recover to.
TRUSTED_ISSUERS = {ISSUER_DID: _issuer_account(ISSUER_DID).address}


def _cred_message(cred):
    s = cred.get("credentialSubject", {}) or {}
    iss = cred.get("issuer", "")
    iss = iss.get("id", "") if isinstance(iss, dict) else iss          # W3C allows the issuer as an object with an id
    return {"id": str(cred.get("id", "")), "issuer": str(iss), "subject": str(s.get("id", "")),
            "role": str(s.get("role", "")), "organisation": str(s.get("organisation", "")),
            "validFrom": str(cred.get("validFrom", "")), "validUntil": str(cred.get("validUntil", ""))}


# A credential issued with a status entry signs the entry as well, so its position in the status list cannot be
# changed or removed after issue. A credential without an entry is signed exactly as before.
CRED_STATUS_TYPES = {"Credential": CRED_TYPES["Credential"] + [{"name": "statusListCredential", "type": "string"},
                                                              {"name": "statusListIndex", "type": "string"},
                                                              {"name": "statusPurpose", "type": "string"}]}


def _cred_signable(cred):
    status = cred.get("credentialStatus")
    if status is None:
        return encode_typed_data(domain_data=CRED_DOMAIN, message_types=CRED_TYPES, message_data=_cred_message(cred))
    message = dict(_cred_message(cred), statusListCredential=str(status.get("statusListCredential", "")),
                   statusListIndex=str(status.get("statusListIndex", "")), statusPurpose=str(status.get("statusPurpose", "")))
    return encode_typed_data(domain_data=CRED_DOMAIN, message_types=CRED_STATUS_TYPES, message_data=message)


def assertion_method(issuer_did):
    """The verification method an issuer names in its proofs: the assertion method of its DID document, or #key-1
    for an identifier this prototype does not resolve."""
    from services import did_resolver                         # imported here: did_resolver imports this module
    try:
        return did_resolver.resolve(issuer_did)["assertionMethod"][0]
    except Exception:
        return f"{issuer_did}#key-1"


def issue_credential(subject_did, role, organisation="", valid_from="2026-01-01T00:00:00",
                     valid_until="2030-12-31T23:59:59", issuer_did=ISSUER_DID, signer=None, status_index=None):
    """Issue a role credential for subject_did. `signer` (an eth_account LocalAccount) defaults to the demo issuer key;
    tests pass another key to forge a credential. `status_index` gives the credential its own position in the issuer's
    revocation list (a W3C Bitstring Status List entry, signed with the credential). Without it the credential is
    issued exactly as before and its position is derived from its identifier (services/credential_status.py)."""
    cred = {"@context": ["https://www.w3.org/ns/credentials/v2"],
            "id": f"urn:halah:vc:{role}:{subject_did}",
            "type": ["VerifiableCredential", "HALAHRoleCredential"],
            "issuer": issuer_did, "validFrom": valid_from, "validUntil": valid_until,
            "credentialSubject": {"id": subject_did, "role": role, "organisation": organisation}}
    if status_index is not None:
        from services import credential_status as status      # imported here: credential_status imports this module
        index = int(status_index)
        if not 0 <= index < status.LIST_SIZE:
            raise ValueError("status_index is outside the status list")
        list_id = status.default_list_id(issuer_did)
        cred["id"] = f"{cred['id']}:{index}"                   # a re-issued credential is a new credential
        cred["credentialStatus"] = {"id": f"{list_id}#{index}", "type": status.ENTRY_TYPE,
                                    "statusPurpose": status.STATUS_PURPOSE, "statusListIndex": str(index),
                                    "statusListCredential": list_id}
    acct = signer or _issuer_account(issuer_did)
    sig = acct.sign_message(_cred_signable(cred)).signature.hex()
    cred["proof"] = {"type": "EthereumEip712Signature2021", "proofPurpose": "assertionMethod",
                     "verificationMethod": assertion_method(issuer_did), "proofValue": sig if sig.startswith("0x") else "0x" + sig}
    return cred


_store = {"path": None, "mtime": None, "creds": {}}


def load_credentials():
    """Credential store (the demo wallet): subject DID -> credential."""
    try:
        mtime = os.path.getmtime(CREDENTIALS_PATH)
    except OSError:
        return {}
    if _store["path"] != CREDENTIALS_PATH or _store["mtime"] != mtime:
        with open(CREDENTIALS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        _store.update(path=CREDENTIALS_PATH, mtime=mtime,
                      creds={c["credentialSubject"]["id"]: c for c in data.get("credentials", [])})
    return _store["creds"]


def get_credential(did):
    return load_credentials().get(did)


def check_credential(did, role=None, credential=None, now=None):
    """Original report, RO2 Steps 3-6: returns each condition and VALID. Steps 1-2 (DID resolution and DID document
    verification) are reduced to a DID syntax check in this function. verify_identity performs them, and the credential
    status check, around it. Sig_VC is checked against the registered key of the trusted issuer, so an untrusted issuer
    fails both Sig_VC and Issuer_valid. Any malformed field fails the check."""
    now = now or datetime.now()
    cred = credential if credential is not None else get_credential(did)
    r = {"DID_syntax": is_valid_did(did), "VC_found": cred is not None, "Sig_VC": False, "Issuer_valid": False,
         "Subject_match": False, "Time_valid": False, "Role_match": False, "credential_id": None, "issuer": None}
    if isinstance(cred, dict):
        try:
            iss = cred.get("issuer")
            iss = iss.get("id") if isinstance(iss, dict) else iss
            r["credential_id"], r["issuer"] = cred.get("id"), iss
            expected = TRUSTED_ISSUERS.get(iss) if isinstance(iss, str) else None
            r["Issuer_valid"] = expected is not None
            try:
                recovered = Account.recover_message(_cred_signable(cred), signature=(cred.get("proof") or {}).get("proofValue"))
                r["Sig_VC"] = expected is not None and recovered == expected
            except Exception:
                r["Sig_VC"] = False
            subj = cred.get("credentialSubject") or {}
            r["Subject_match"] = isinstance(subj, dict) and subj.get("id") == did
            try:
                r["Time_valid"] = datetime.fromisoformat(cred["validFrom"]) <= now <= datetime.fromisoformat(cred["validUntil"])
            except Exception:
                r["Time_valid"] = False
            r["Role_match"] = isinstance(subj, dict) and (role is None or subj.get("role") == role)
        except Exception:
            for k in ("Sig_VC", "Issuer_valid", "Subject_match", "Time_valid", "Role_match"):
                r[k] = False
    r["VALID"] = r["VC_found"] and isinstance(cred, dict) and all(r[k] for k in ("DID_syntax", "VC_found", "Sig_VC", "Issuer_valid", "Subject_match", "Time_valid", "Role_match"))
    return r


def verify_vc(did, role=None, credential=None, now=None):
    """True only if `did` is a valid DID holding a valid credential (VC_valid) with the required role claim."""
    return check_credential(did, role=role, credential=credential, now=now)["VALID"]


# ---------------------------------------------------------------------------
# EIP-712 guardian approvals
# ---------------------------------------------------------------------------
def _demo_private_key(did):
    return Web3.keccak(text=f"{DEMO_KEY_TAG}|{did}")

def guardian_account(did):
    return Account.from_key(_demo_private_key(did))

def guardian_address(did):
    return guardian_account(did).address

def _signable(consent_id, did):
    return encode_typed_data(domain_data=DOMAIN, message_types=TYPES,
                             message_data={"consentId": str(consent_id), "guardian": did, "action": "APPROVE"})

def sign_consent(did, consent_id):
    acct = guardian_account(did)
    sig = acct.sign_message(_signable(consent_id, did)).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    return sig, acct.address

def verify_signature(did, consent_id=None, signature=None):
    """True only if `signature` is a valid EIP-712 approval of `consent_id` by guardian `did`."""
    if not (consent_id and signature):
        return False
    try:
        recovered = Account.recover_message(_signable(consent_id, did), signature=signature)
    except Exception:
        return False
    return recovered == guardian_address(did)


# ---------------------------------------------------------------------------
# EIP-712 guardian approvals over the consent commitment (Algorithm 5.2)
# ---------------------------------------------------------------------------
# The approval above binds the consent identifier, the guardian and the chain. It does not detect a change of scope,
# purpose, requester, expiry or context after approval. This approval adds the consent commitment c, so a signature
# is valid for one consent, one guardian, one commitment and one chain.
DOMAIN_V2 = {"name": "HALAH Consent", "version": "2"}
TYPES_V2 = {"EIP712Domain": [{"name": "name", "type": "string"}, {"name": "version", "type": "string"},
                             {"name": "chainId", "type": "uint256"}],
            "Approval": [{"name": "consentId", "type": "string"}, {"name": "guardian", "type": "string"},
                         {"name": "commitment", "type": "uint256"}, {"name": "chainId", "type": "uint256"},
                         {"name": "action", "type": "string"}]}
_SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def commitment_value(commitment):
    """The consent commitment c as an integer. Accepted forms: an integer, 32 bytes, a 0x-prefixed hexadecimal string,
    a string of exactly 64 hexadecimal characters, or a decimal string. Anything else, and a value outside
    1 .. 2^256 - 1, raises ValueError."""
    if isinstance(commitment, bool):
        raise ValueError("the commitment is not a number")
    if isinstance(commitment, int):
        value = commitment
    elif isinstance(commitment, (bytes, bytearray)):
        value = int.from_bytes(commitment, "big")
    elif isinstance(commitment, str) and re.fullmatch(r"0[xX][0-9a-fA-F]{1,64}", commitment):
        value = int(commitment[2:], 16)
    elif isinstance(commitment, str) and re.fullmatch(r"[0-9a-fA-F]{64}", commitment):
        value = int(commitment, 16)
    elif isinstance(commitment, str) and re.fullmatch(r"[0-9]+", commitment):
        value = int(commitment)
    else:
        raise ValueError("the commitment is not a number")
    if not 0 < value < 2 ** 256:
        raise ValueError("the commitment is outside 1 .. 2^256 - 1")
    return value


def approval_typed_data(did, consent_id, commitment, chain_id=None, action="APPROVE"):
    """The typed data a guardian signs: the consent identifier, the guardian identifier, the consent commitment c
    and the chain identifier. The chain identifier is also in the domain, where a wallet compares it with its network.
    The dictionary is the JSON a wallet takes in eth_signTypedData_v4, so a wallet-held key and the test harness sign
    the same bytes."""
    chain = int(CHAIN_ID if chain_id is None else chain_id)
    return {"types": {name: [dict(f) for f in fields] for name, fields in TYPES_V2.items()},
            "primaryType": "Approval", "domain": dict(DOMAIN_V2, chainId=chain),
            "message": {"consentId": str(consent_id), "guardian": str(did), "commitment": str(commitment_value(commitment)),
                        "chainId": chain, "action": str(action)}}


def _signable_v2(did, consent_id, commitment, chain_id, action):
    return encode_typed_data(full_message=approval_typed_data(did, consent_id, commitment, chain_id, action))


def sign_consent_v2(did, consent_id, commitment, signer=None, chain_id=None, action="APPROVE"):
    """Sign the approval of `consent_id` by guardian `did` over `commitment`. Returns (signature, signer address).
    `signer` (an eth_account LocalAccount) stands for the guardian's wallet. Without it the derived demonstration key
    signs, which is kept for the automated test harness only. A did:key guardian has no derived key: the wallet that
    holds the key of the identifier signs."""
    if signer is None:
        if str(did).startswith("did:key:"):
            raise ValueError("a did:key guardian signs with the wallet that holds its key: pass it as signer")
        signer = guardian_account(did)
    sig = signer.sign_message(_signable_v2(did, consent_id, commitment, chain_id, action)).signature.hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    return sig, signer.address


def recover_signer_v2(did, consent_id, commitment, signature, chain_id=None, action="APPROVE"):
    """The recovery step of Algorithm 5.2: the address whose key signed this approval, or None when the approval or
    the signature is malformed."""
    try:
        if isinstance(signature, str):
            raw = bytes.fromhex(signature[2:] if signature[:2] in ("0x", "0X") else signature)
        else:
            raw = bytes(signature)
        if len(raw) != 65:
            return None
        r, s = int.from_bytes(raw[:32], "big"), int.from_bytes(raw[32:64], "big")
        # One approval has one encoding: the second signature that ECDSA allows for the same message (high s) is refused.
        if not (0 < r < _SECP256K1_N and 0 < s <= _SECP256K1_N // 2):
            return None
        return Account.recover_message(_signable_v2(did, consent_id, commitment, chain_id, action), signature=raw)
    except Exception:
        return None


def verify_signature_v2(did, consent_id=None, commitment=None, signature=None, address=None, chain_id=None, action="APPROVE",
                        allow_demo_key=True):
    """True only if `signature` is a valid EIP-712 approval of `consent_id` and `commitment` by guardian `did` on this
    chain. `address` is the guardian's wallet address (consent.guardian_addresses): when it is given, the recovered
    signer must equal it. A did:key guardian with a secp256k1 key must always have signed with the key of its own
    identifier, and an address registered for it that is not the address of that key refuses the approval. Without an
    address, any other guardian is checked against the derived demonstration key (test harness only).
    `allow_demo_key=False` switches the derived key off: an approval is then accepted only from a registered wallet
    address or from the key of a did:key."""
    if not (did and consent_id and signature) or commitment is None:
        return False
    recovered = recover_signer_v2(did, consent_id, commitment, signature, chain_id, action)
    if recovered is None:
        return False
    is_did_key, own = str(did).startswith("did:key:"), None
    if is_did_key:
        from services import did_resolver                     # imported here: did_resolver imports this module
        try:
            own = did_resolver.ethereum_address(did_resolver.resolve(did))      # None for a key that is not secp256k1
        except Exception:
            return False
    if own is not None:
        # The identifier is the key. No registered address can put another key in its place.
        if address is not None and not (isinstance(address, str) and address.lower() == own.lower()):
            return False
        expected = own
    elif address is not None:
        expected = address
    elif allow_demo_key and not is_did_key:
        expected = guardian_address(did)
    else:
        return False
    return isinstance(expected, str) and recovered.lower() == expected.lower()


def approval_verifier(consent, commitment=None, chain_id=None, allow_demo_key=True):
    """The approval check of one consent, in the form evaluate_allow takes as its verify_sig argument: a function
    (did, consent_id, signature) -> bool. Each approval is verified over the consent commitment and against the wallet
    address registered for that guardian in consent.guardian_addresses. `commitment` defaults to consent.commitment as
    it is stored when the check runs. Pass the commitment recomputed from the current fields of the consent and its
    stored opening, and an approval given before a change of scope, purpose, requester, expiry or context no longer
    verifies. An approval presented for another consent identifier is refused."""
    def verify(did, consent_id=None, signature=None):
        c = getattr(consent, "commitment", None) if commitment is None else commitment
        addresses = getattr(consent, "guardian_addresses", None) or {}
        if consent_id is None or str(consent_id) != str(getattr(consent, "consent_id", "")) or not isinstance(addresses, dict):
            return False
        address = addresses.get(did) if isinstance(did, str) else None
        return verify_signature_v2(did, consent_id, c, signature, address=address, chain_id=chain_id, allow_demo_key=allow_demo_key)
    return verify


# ---------------------------------------------------------------------------
# Identity and authority verification (Algorithm 5.1)
# ---------------------------------------------------------------------------
class IdentityReason:
    """Reason codes of Algorithm 5.1, defined once. Every result carries exactly one."""
    OK = "OK"
    DID_RESOLUTION_FAILED = "DID_RESOLUTION_FAILED"                  # lines 1-4
    DID_DOCUMENT_INVALID = "DID_DOCUMENT_INVALID"                    # lines 5-8
    CREDENTIAL_NOT_FOUND = "CREDENTIAL_NOT_FOUND"                    # lines 9-12
    CREDENTIAL_ISSUER_UNTRUSTED = "CREDENTIAL_ISSUER_UNTRUSTED"      # lines 13-16, the four conditions
    CREDENTIAL_SIGNATURE_INVALID = "CREDENTIAL_SIGNATURE_INVALID"
    CREDENTIAL_SUBJECT_MISMATCH = "CREDENTIAL_SUBJECT_MISMATCH"
    CREDENTIAL_TIME_INVALID = "CREDENTIAL_TIME_INVALID"
    CREDENTIAL_STATUS_UNAVAILABLE = "CREDENTIAL_STATUS_UNAVAILABLE"  # lines 13-16, the status check
    CREDENTIAL_REVOKED = "CREDENTIAL_REVOKED"
    AUTHORITY_MISMATCH = "AUTHORITY_MISMATCH"                        # lines 17-20
    EVIDENCE_NOT_RECORDED = "EVIDENCE_NOT_RECORDED"                  # line 21


class IdentityResult:
    """Outcome of Algorithm 5.1 for one participant. The object is true only when the result is VALID, so
    verify_identity can be passed as the verify_did argument of evaluate_allow."""
    VALID, INVALID = "VALID", "INVALID"

    def __init__(self, did, role, result, reason, checks, claims, evidence):
        self.did, self.role, self.result, self.reason = did, role, result, reason
        self.checks, self.claims, self.evidence = checks, claims, evidence

    @property
    def valid(self):
        return self.result == self.VALID

    def __bool__(self):
        return self.valid

    def __repr__(self):
        return f"IdentityResult({self.result}, {self.reason}, {self.did!r})"

    def as_dict(self):
        return {"did": self.did, "required_role": self.role, "result": self.result, "reason": self.reason,
                "checks": dict(self.checks), "claims": dict(self.claims), "evidence": dict(self.evidence)}


def verify_identity(did, role=None, now=None, credential=None, resolver=None, record=None):
    """Algorithm 5.1: the identity and the authority of participant `did` for the role the step requires.
    `credential` defaults to the participant's credential in the store. `resolver` defaults to
    did_resolver.resolve. `record` is called with the evidence before VALID is returned (line 21), for example
    record_identity_evidence. Without `record` the evidence is returned in the result and nothing is written: the
    decision function calls this check at every request, and the caller chooses which verifications enter the ledger.
    The procedure stops at the first failed condition and never raises."""
    from services import did_resolver, credential_status     # imported here: both modules import this one
    now = now or datetime.now()
    if isinstance(now, datetime) and now.tzinfo is not None:
        now = now.astimezone().replace(tzinfo=None)           # the credentials carry local times without a zone
    checks = {"DID_resolved": False, "DID_document_valid": False, "VC_found": False, "Issuer_valid": False, "Sig_VC": False,
              "Subject_match": False, "Time_valid": False, "Status_valid": False, "Role_match": False}
    claims = {}
    evidence = {"did": did, "required_role": role, "checked_at": now.isoformat() if isinstance(now, datetime) else str(now),
                "did_method": None, "verification_method": None,
                "key_address": None, "credential_id": None, "issuer": None, "status_list": None, "status_index": None,
                "status_sequence": None}

    def finish(reason):
        result = IdentityResult.VALID if reason == IdentityReason.OK else IdentityResult.INVALID
        evidence.update(claims=dict(claims), checks=dict(checks), result=result, reason=reason)
        return IdentityResult(did, role, result, reason, checks, claims, evidence)

    # Lines 1-4: resolve the DID of u.
    try:
        if not is_valid_did(did):
            raise ValueError("not a DID")
        document = (resolver or did_resolver.resolve)(did)
    except Exception:
        return finish(IdentityReason.DID_RESOLUTION_FAILED)
    checks["DID_resolved"] = True
    # Lines 5-8: verify the DID document and the key it binds to the identifier.
    if not did_resolver.verify_document(did, document):
        return finish(IdentityReason.DID_DOCUMENT_INVALID)
    checks["DID_document_valid"] = True
    evidence.update(did_method=did.split(":")[1], verification_method=document["authentication"][0],
                    key_address=did_resolver.ethereum_address(document))
    # Lines 9-12: retrieve the credential associated with u.
    try:
        cred = credential if credential is not None else get_credential(did)
    except Exception:                                         # a credential store that cannot be read holds no credential
        cred = None
    if cred is None:
        return finish(IdentityReason.CREDENTIAL_NOT_FOUND)
    checks["VC_found"] = True
    # Lines 13-16: verify the credential on its four conditions, signature, issuer, subject and validity time.
    vc = check_credential(did, role=None, credential=cred, now=now)
    evidence.update(credential_id=vc["credential_id"], issuer=vc["issuer"])
    for name, reason in (("Issuer_valid", IdentityReason.CREDENTIAL_ISSUER_UNTRUSTED),
                         ("Sig_VC", IdentityReason.CREDENTIAL_SIGNATURE_INVALID),
                         ("Subject_match", IdentityReason.CREDENTIAL_SUBJECT_MISMATCH),
                         ("Time_valid", IdentityReason.CREDENTIAL_TIME_INVALID)):
        if not vc[name]:
            return finish(reason)
        checks[name] = True
    # Line 13 also checks the credential status: the issuer's signed status list must show it is not revoked.
    try:
        status = credential_status.check_status(cred)
    except Exception:
        return finish(IdentityReason.CREDENTIAL_STATUS_UNAVAILABLE)
    evidence.update(status_list=status["status_list"], status_index=status["index"], status_sequence=status["sequence"])
    if status["revoked"]:
        return finish(IdentityReason.CREDENTIAL_REVOKED)
    checks["Status_valid"] = True
    # Lines 17-20: extract the role and authority claims and match them to the authority the step requires.
    subject = cred["credentialSubject"]
    claims.update(role=subject.get("role"), organisation=subject.get("organisation"))
    if role is not None and claims["role"] != role:
        return finish(IdentityReason.AUTHORITY_MISMATCH)
    checks["Role_match"] = True
    # Line 21: record the identity and authority verification evidence.
    result = finish(IdentityReason.OK)
    if record is not None:
        try:
            record(dict(evidence))
        except Exception:
            return finish(IdentityReason.EVIDENCE_NOT_RECORDED)
    # Line 22: return VALID.
    return result


def record_identity_evidence(evidence, consent_id=None, patient_did=None, actor_role=None):
    """Write the evidence of one verification to the audit ledger (Algorithm 5.1, line 21). Pass it, or a
    functools.partial of it that names the consent, as the `record` argument of verify_identity."""
    from database import audit_db                            # imported here: the checks themselves need no database
    role = actor_role or str(evidence.get("required_role") or "participant").capitalize()
    return audit_db.log(actor_did=evidence.get("did"), actor_role=role, action="IDENTITY_VERIFICATION",
                        patient_did=patient_did, consent_id=consent_id, result=evidence.get("result"), metadata=evidence)
