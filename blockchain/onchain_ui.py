'''Streamlit widgets for HALAH on-chain mode (Sepolia) - v3'''
import streamlit as st
from services import blockchain_service as bc


@st.cache_data(ttl=30, show_spinner=False)
def _cached_status():
    return bc.chain_status()


def render_chain_badge():
    s = _cached_status()
    if s.get("mode") == "demo":
        st.sidebar.caption("Chain: Demo mode (local ledger)")
        return
    if "error" in s:
        st.sidebar.warning(f"Sepolia: not reachable - {s['error'][:90]}")
        return
    net = "Sepolia" if s.get("is_sepolia") else f"chain {s.get('chain_id')}"
    st.sidebar.success(f"{net} - block {s['block']:,}\n\nSigner balance: {s['balance_eth']:.4f} ETH")
    if not s.get("contract_has_code"):
        st.sidebar.error("Contract address has no code - check CONTRACT_ADDRESS")
    elif s.get("signer_is_owner") is False:
        st.sidebar.error("Signer is not the contract owner - mint will revert")
    st.sidebar.markdown(f"[View contract on Etherscan]({s['explorer_contract']})")


def render_onchain_mint(consent, audit_db):
    '''Called right after the local SBT mint. Anchors on Sepolia when configured.'''
    if not bc.onchain_enabled():
        st.caption("Demo mode - on-chain anchoring skipped. Set RPC_URL / CONTRACT_ADDRESS / PRIVATE_KEY in .env to mint on Sepolia.")
        return None
    with st.spinner("Anchoring consent SBT on Sepolia - waiting for block confirmation..."):
        try:
            r = bc.mint_consent(consent)
        except Exception as e:
            audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT",
                         patient_did=consent.patient_did, consent_id=consent.consent_id,
                         scope=consent.scope, purpose=consent.purpose, result="FAILED",
                         metadata={"error": str(e)[:300]})
            st.warning(f"On-chain anchoring failed - SBT kept in the local demo ledger. Reason: {e}")
            return None
    consent.tx_hash = r["tx_hash"]
    if r.get("token_id") is not None:
        consent.token_id = f"SBT-{r['token_id']}"
    audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_MINT",
                 patient_did=consent.patient_did, consent_id=consent.consent_id,
                 scope=consent.scope, purpose=consent.purpose, result="SUCCESS",
                 tx_hash=r["tx_hash"], block_number=r["block_number"],
                 metadata={"tx_hash": r["tx_hash"], "token_id": r.get("token_id"),
                           "block": r["block_number"], "gas_used": r["gas_used"],
                           "contract": r["contract"], "explorer": r["explorer_tx"]})
    st.markdown(f"""
    <div class="blockchain-badge">
        <b>[ON-CHAIN ANCHOR - SEPOLIA]</b><br>
        &bull; <b>Tx hash:</b> {r['tx_hash']}<br>
        &bull; <b>Block:</b> {r['block_number']} &nbsp;&bull;&nbsp; <b>Gas used:</b> {r['gas_used']}<br>
        &bull; <b>Token ID:</b> {r.get('token_id')} &nbsp;&bull;&nbsp; <b>Contract:</b> {r['contract']}
    </div>""", unsafe_allow_html=True)
    c1, c2 = st.columns(2)
    with c1:
        st.link_button("View transaction on Etherscan", r["explorer_tx"])
    with c2:
        if r.get("explorer_token"):
            st.link_button("View SBT token on Etherscan", r["explorer_token"])
        else:
            st.link_button("View contract on Etherscan", r["explorer_contract"])
    return r


def render_onchain_anchor_async(consent, audit_db, consent_db):
    from services import anchor_service
    if not bc.onchain_enabled():
        st.caption("Demo mode - on-chain anchoring skipped"); return None
    job = anchor_service.job_status(consent.consent_id)
    if job is None or job.get("status") == "failed":
        job = anchor_service.anchor_async(consent, audit_db, consent_db)
    if job.get("status") == "running":
        st.info("Anchoring on Sepolia in the background (15-30 s). You may navigate away - the result is written to the ledger automatically. Refresh or open Auditor to see it.")
    elif job.get("status") == "done":
        r = job["result"]; st.success(f"On-chain anchor confirmed - token #{r.get('token_id')} - block {r.get('block_number')}")
        st.markdown(f"[View transaction on Etherscan]({r.get('explorer_tx')})")
    elif job.get("status") == "failed":
        st.warning(f"On-chain anchoring failed: {job.get('error')}")
    return job
