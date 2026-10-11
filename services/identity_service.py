"""
DID/VC + EIP-712 guardian approval for SRQ2 (HALAH v1.3)
is_valid_did(did)                      -> DID syntax check (W3C DID Core: did:<method>:<method-specific-id>)
verify_vc(did, role=None, credential=None, now=None)
                                       -> the participant's verifiable credential is valid (original report, RO2 Step 4):
                                          VC_valid = Sig_VC AND Issuer_valid AND Subject_match AND Time_valid,
                                          and its role claim matches the role the step requires (RO2 Steps 5-6)
check_credential(...)                  -> the same checks, one by one, for the screens and the audit evidence
guardian_address(did) | sign_consent(did, consent_id) -> (sig, addr)
verify_signature(did, consent_id, signature) -> bool  (ecrecover of typed data == guardian address)
DEMO KEY MODEL: the guardian key is derived from its DID so the prototype can sign without wallets.
In production the guardian's own wallet signs the SAME typed data; only verify_signature() is used.
DEMO ISSUER MODEL: the credentials in data/credentials/demo_credentials.json are signed by one demo issuer whose key is
derived from a fixed tag (tools/issue_demo_credentials.py). In production the issuer signs with its own key and the
verifier only needs the issuer's registered address (TRUSTED_ISSUERS). Like the guardian demo keys, the demo issuer
key can be reproduced from the source, so the credential check demonstrates the verification, not the secrecy of the
issuer key. Full DID resolution, and proof that a user controls the DID they enter (holder binding), are not
implemented yet.
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


def _cred_signable(cred):
    return encode_typed_data(domain_data=CRED_DOMAIN, message_types=CRED_TYPES, message_data=_cred_message(cred))


def issue_credential(subject_did, role, organisation="", valid_from="2026-01-01T00:00:00",
                     valid_until="2030-12-31T23:59:59", issuer_did=ISSUER_DID, signer=None):
    """Issue a role credential for subject_did. `signer` (an eth_account LocalAccount) defaults to the demo issuer key;
    tests pass another key to forge a credential."""
    cred = {"@context": ["https://www.w3.org/ns/credentials/v2"],
            "id": f"urn:halah:vc:{role}:{subject_did}",
            "type": ["VerifiableCredential", "HALAHRoleCredential"],
            "issuer": issuer_did, "validFrom": valid_from, "validUntil": valid_until,
            "credentialSubject": {"id": subject_did, "role": role, "organisation": organisation}}
    acct = signer or _issuer_account(issuer_did)
    sig = acct.sign_message(_cred_signable(cred)).signature.hex()
    cred["proof"] = {"type": "EthereumEip712Signature2021", "proofPurpose": "assertionMethod",
                     "verificationMethod": f"{issuer_did}#key-1", "proofValue": sig if sig.startswith("0x") else "0x" + sig}
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
    verification) are reduced to a DID syntax check in this stage. Sig_VC is checked against the registered key of the
    trusted issuer, so an untrusted issuer fails both Sig_VC and Issuer_valid. Any malformed field fails the check."""
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
