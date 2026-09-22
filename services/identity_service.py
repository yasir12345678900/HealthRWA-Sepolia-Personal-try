"""
DID/VC + EIP-712 guardian approval for SRQ2 (HALAH v1.1)
verify_vc(did) -> DID format check | guardian_address(did) | sign_consent(did, consent_id) -> (sig, addr)
verify_signature(did, consent_id, signature) -> bool  (ecrecover of typed data == guardian address)
DEMO KEY MODEL: guardian key derived from its DID so the prototype can sign without wallets.
In production the guardian's own wallet signs the SAME typed data; only verify_signature() is used.
"""
import os
from eth_account import Account
from eth_account.messages import encode_typed_data
from web3 import Web3

DEMO_KEY_TAG = os.environ.get("HALAH_DEMO_KEY_TAG", "HALAH-DEMO-GUARDIAN-KEY-v1")
CHAIN_ID = int(os.environ.get("CHAIN_ID", "11155111"))
DOMAIN = {"name": "HALAH Consent", "version": "1", "chainId": CHAIN_ID}
TYPES = {"Approval": [{"name": "consentId", "type": "string"}, {"name": "guardian", "type": "string"}, {"name": "action", "type": "string"}]}

def verify_vc(did):
    return isinstance(did, str) and did.startswith("did:") and len(did) > 4

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
