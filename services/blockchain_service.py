'''
blockchain for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
v3 (2026-09-20): real on-chain mode through blockchain.contract (Sepolia).
Demo mode (no .env) keeps working exactly as before.
'''
import logging
log = logging.getLogger("halah.service")
from datetime import datetime, timedelta

try:
    from blockchain import contract as chain
except Exception:  # web3 not installed -> demo mode only
    chain = None


def mint_sbt(consent):
    # Demo-mode token id used by the Streamlit prototype (no chain call).
    return "SBT-" + consent.consent_id[:8]


def onchain_enabled():
    return chain is not None and chain.is_configured()


def _expiry_ts(consent):
    raw = getattr(consent, "expiry_date", None)
    if raw:
        try:
            return int(datetime.fromisoformat(str(raw)).timestamp())
        except ValueError:
            log.warning("bad expiry_date %r - falling back to +365d", raw)
    return int((datetime.now() + timedelta(days=365)).timestamp())


def _not_before_ts(consent):
    raw = getattr(consent, "start_date", None)
    if raw:
        try:
            return int(datetime.fromisoformat(str(raw)).timestamp())
        except ValueError:
            pass
    return int(datetime.now().timestamp())


def mint_consent(consent):
    """Real Sepolia mint. Uses mintConsentV3 (VT/VL) when the deployed contract supports it, else v2."""
    c = chain.ConsentContract()
    if getattr(c, "has_v3", lambda: False)():
        return c.mint_consent_v3(consent.patient_did, consent.requester_did, consent.purpose,
                                 _not_before_ts(consent), _expiry_ts(consent),
                                 getattr(consent, "jurisdiction", "AU") or "AU", burn_auth=2)
    return _mint_consent_v2(consent)


def _mint_consent_v2(consent):
    '''On-chain mode: mint the consent SBT on Sepolia and return the receipt dict.'''
    if chain is None:
        raise RuntimeError("web3 is not installed - run: pip install web3 python-dotenv")
    c = chain.ConsentContract()
    return c.mint_consent(consent.patient_did, consent.requester_did, consent.purpose, _expiry_ts(consent))


def chain_status():
    if not onchain_enabled():
        return {"mode": "demo"}
    try:
        s = chain.ConsentContract().status()
        s["mode"] = "onchain"
        return s
    except Exception as e:
        return {"mode": "onchain", "error": str(e)}


def explorer_tx(tx_hash):
    return chain.explorer_tx(tx_hash) if chain else f"https://sepolia.etherscan.io/tx/{tx_hash}"


def revoke(token_id):
    """Revoke an on-chain consent SBT (onlyOwner)."""
    if chain is None:
        raise RuntimeError("web3 not available")
    return chain.ConsentContract().revoke(int(token_id))
