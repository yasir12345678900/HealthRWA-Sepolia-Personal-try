'''
blockchain for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
v3 (2026-09-20): real on-chain mode through blockchain.contract (Sepolia).
Demo mode (no .env) keeps working exactly as before.
2026-11-17: the thesis design. With CONTRACT_V4_ADDRESS set, the mint goes to ConsentSBTv4 through
blockchain.contract_v4: a per-consent address and the consent commitment, nothing else. The screens call the
functions below and never build a client themselves, so the tests can put a client on an in-memory chain in
their place. Without CONTRACT_V4_ADDRESS the ConsentSBTv3 path of before is used.
The time of a decision is read here as well (chain_time): the timestamp of the latest block when a chain is
configured, and the labelled server clock in demo mode. The decision proof is made against the two trees of the
consent contract (chain_trees, decision_proof) and verified by the verifier contract (verify_decision).
'''
import logging
import os
log = logging.getLogger("halah.service")
from datetime import datetime, timedelta

try:
    from blockchain import contract as chain
except Exception:  # web3 not installed -> demo mode only
    chain = None

try:
    from blockchain import contract_v4 as chain_v4
except Exception:  # web3 not installed -> demo mode only
    chain_v4 = None


def mint_sbt(consent):
    # Demo-mode token id used by the Streamlit prototype (no chain call).
    return "SBT-" + consent.consent_id[:8]


def v4_enabled():
    '''On-chain mode of the thesis design: ConsentSBTv4 is configured (CONTRACT_V4_ADDRESS and PRIVATE_KEY).'''
    return chain_v4 is not None and bool(os.environ.get("CONTRACT_V4_ADDRESS")) and bool(os.environ.get("PRIVATE_KEY"))


def proof_enabled():
    '''The decision verifier is configured as well (VERIFIER_ADDRESS), so a decision proof can be verified on chain.'''
    return v4_enabled() and bool(os.environ.get("VERIFIER_ADDRESS"))


def token_client(read_only=False):
    '''Client of ConsentSBTv4. A read-only client holds no key.'''
    return chain_v4.ConsentContractV4(read_only=read_only)


def verifier_client(read_only=False):
    '''Client of ConsentDecisionVerifier. A read-only client holds no key.'''
    return chain_v4.DecisionVerifierContract(read_only=read_only)


def onchain_enabled():
    return v4_enabled() or (chain is not None and chain.is_configured())


def _is_chain_token(token_id):
    t = str(token_id or "")
    return t.startswith("SBT-") and t[4:].isdigit()


def has_chain_token(consent):
    '''True for a consent whose token is on ConsentSBTv4. Only the ConsentSBTv4 mint records a per-consent
    address, so an older record whose "SBT-<n>" is a ConsentSBTv3 token is not taken for a token of the new
    contract, where the same number belongs to another consent.'''
    return v4_enabled() and _is_chain_token(getattr(consent, "token_id", None)) and bool(getattr(consent, "token_address", None))


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


def mint_consent_v4(consent):
    '''Algorithm 5.3 on ConsentSBTv4: the token goes to a per-consent address and carries the consent commitment.
    No party, purpose, window or context goes on chain, and the opening of the commitment stays in the record.
    On a confirmed mint the per-consent address is kept in consent.token_address. The salt of the address is not
    kept: the record holds the address itself, and a revocation deletes it. Returns the receipt of the client.'''
    if not getattr(consent, "commitment", None):
        raise RuntimeError("the consent has no commitment, so it cannot be minted on ConsentSBTv4")
    address, _salt = chain_v4.derive_consent_address(consent.patient_did, consent.consent_id)
    r = token_client().mint_consent(address, consent.commitment)
    if r.get("status") == 1 and r.get("token_id") is not None:
        consent.token_address = r["token_address"]
    return r


def revoke_onchain(consent):
    '''Revoke the ConsentSBTv4 token of a consent (the on-chain step of Algorithm 6.4). Returns the receipt.'''
    if not has_chain_token(consent):
        raise RuntimeError("the consent has no token on ConsentSBTv4")
    return token_client().revoke(int(str(consent.token_id)[4:]))


def chain_time():
    '''The time t of a decision with its evidence (services/time_source.read_time): time, source, unix,
    block_number, reason and clock_skew_seconds. With a chain configured it is the timestamp of the latest block,
    read through time_source.block_provider, and there is no fall-back: when the chain cannot be read,
    time_source.TimeSourceError is raised and the caller refuses the request. In demo mode it is the server clock,
    labelled "system-clock-fallback".'''
    from services import time_source
    if not onchain_enabled():
        return time_source.read_time(None)

    def latest_block():
        # the connection is made here, so that a chain that cannot be reached is a failed read and nothing else
        client = token_client(read_only=True) if v4_enabled() else chain.ConsentContract()
        return time_source.block_provider(client.w3)()
    return time_source.read_time(latest_block, allow_fallback=False)


def chain_trees():
    '''The consent tree and the revocation tree, built again from the chain: one read of consents(i) for each
    issued token. The prover takes the two Merkle paths of a consent from them (Algorithm 7.2).'''
    from services import merkle_service
    client = token_client(read_only=True)
    leaves = [client.consent_of(i) for i in range(1, client.consent_count() + 1)]
    return (merkle_service.ConsentTree([leaf["commitment"] for leaf in leaves]),
            merkle_service.RevocationTree([i for i, leaf in enumerate(leaves) if leaf["revoked"]]))


def decision_proof(consent, requester_did, purpose, context, scope, now_ts):
    '''Algorithms 7.1 and 7.2 for one request: the statement with the two roots read from the consent contract and
    the time t of the decision (now_ts, the block time in Unix seconds), then the Groth16 proof. Raises
    zk_decision_service.DecisionProofError when the statement does not hold and ProofUnavailable when the circuit
    is not built on this machine.'''
    from services import zk_decision_service
    statement = zk_decision_service.build_statement(consent, token_client(read_only=True).read_roots,
                                                    requester_did=requester_did, purpose=purpose, context=context,
                                                    scope=scope, now_ts=now_ts)
    consent_tree, revocation_tree = chain_trees()
    return zk_decision_service.prove_decision(statement, consent_tree, revocation_tree)


def verify_decision(proof):
    '''Algorithm 7.3: the proof and its public inputs are submitted to ConsentDecisionVerifier, which reads the
    roots from the consent contract. Returns the answer of the client (accepted, reason_text, tx_hash,
    block_number, gas_used, event, contract) with the chain identifier. A refused proof costs no transaction.'''
    client = verifier_client()
    answer = client.verify_decision(proof)
    answer["chain_id"] = client.w3.eth.chain_id
    return answer


def mint_consent(consent):
    """Real Sepolia mint. With ConsentSBTv4 configured: the commitment-only mint of the thesis design.
    Otherwise mintConsentV3 (validity window and jurisdiction) when the deployed contract supports it, else v2."""
    if v4_enabled():
        return mint_consent_v4(consent)
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
        if v4_enabled():
            c = token_client()
            s = c.status()
            s["rpc"] = c.rpc
            s["balance_eth"] = float(c.w3.from_wei(c.w3.eth.get_balance(c.signer), "ether"))
            s["verifier"] = os.environ.get("VERIFIER_ADDRESS") or None
        else:
            s = chain.ConsentContract().status()
        s["mode"] = "onchain"
        return s
    except Exception as e:
        return {"mode": "onchain", "error": str(e)}


def explorer_tx(tx_hash):
    return chain.explorer_tx(tx_hash) if chain else f"https://sepolia.etherscan.io/tx/{tx_hash}"


def revoke(token_id):
    """Revoke an on-chain consent SBT (onlyOwner) on ConsentSBTv3. A token number alone does not say which contract
    it belongs to, so with ConsentSBTv4 configured this call is refused: use revoke_onchain(consent)."""
    if chain is None:
        raise RuntimeError("web3 not available")
    if v4_enabled():
        raise RuntimeError("ConsentSBTv4 is configured: a token is revoked through revoke_onchain(consent)")
    return chain.ConsentContract().revoke(int(token_id))
