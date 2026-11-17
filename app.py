'''
HALAH: A Blockchain-Based Patient Consent Management System
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date (YYYY-MM-DD): 2026-06-08, 2026-08-02, 2026-11-17
'''
from datetime import datetime, date, time
import functools
import streamlit as st
from blockchain import onchain_ui  # on-chain mode (Sepolia)
from services import blockchain_service as bc
import pandas as pd
from services.consent_service import *
from services.identity_service import *
from services.state_service import *
from services.zk_service import *
from services.access_service import *
from database.consent_db import *
import database.repository as repository
import database.consent_db as consent_db
import database.audit_db as audit_db
from services import capacity_service, trigger_service, time_source
from services import commitment_service, identity_service
from services import data_vault, request_service
from services import notification_service, revocation_service

# ==========================================
# MEDICAL & BLOCKCHAIN THEME CSS INJECTION
# ==========================================
st.set_page_config(page_title="HALAH Consent Management", page_icon="", layout="wide")
import halah_theme
halah_theme.apply_theme()

st.markdown("""
<style>
    /* 全局背景与字体优化 */
    .stApp {
        background-color: #f8f9fa;
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    /* 标题样式设计 */
    .main-title {
        color: #0b2545;
        font-size: 2.5rem !important;
        font-weight: 800;
        margin-bottom: 5px;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.05);
    }
    .subtitle {
        color: #00b4d8;
        font-size: 1.1rem;
        font-weight: 600;
        margin-bottom: 25px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    
    /* 项目学术信息面板 */
    .info-panel {
        background: linear-gradient(135deg, #0b2545 0%, #134074 100%);
        color: white;
        padding: 20px;
        border-radius: 12px;
        margin-bottom: 30px;
        box-shadow: 0 4px 15px rgba(11, 37, 69, 0.2);
    }
    .info-panel p { margin: 4px 0; font-size: 0.9rem; opacity: 0.9; }
    .info-panel .authors { font-style: italic; color: #8ecae6; }
    
    /* 侧边栏美化 */
    [data-testid="stSidebar"] {
        background-color: #134074 !important;
        color: white !important;
    }
    [data-testid="stSidebar"] .stSelectbox label {
        color: #8ecae6 !important;
        font-weight: 600;
    }
    
    /* 表单与卡片容器 */
    div.stButton > button {
        background: linear-gradient(90deg, #00b4d8 0%, #0077b6 100%) !important;
        color: white !important;
        font-weight: 600 !important;
        border: none !important;
        padding: 10px 25px !important;
        border-radius: 8px !important;
        box-shadow: 0 4px 10px rgba(0, 180, 216, 0.3) !important;
        transition: all 0.3s ease !important;
        width: 100%;
    }
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 6px 15px rgba(0, 180, 216, 0.4) !important;
    }
    
    /* 区块链凭证状态徽章样式 */
    .blockchain-badge {
        background-color: #212529;
        color: #00f5d4;
        padding: 12px 18px;
        border-radius: 6px;
        font-family: 'Courier New', monospace;
        font-size: 0.95rem;
        border-left: 4px solid #00b4d8;
        margin-top: 10px;
        word-break: break-all;
    }
    
    /* 下拉框与输入框聚焦美化 */
    .stSelectbox, .stTextInput, .stTextArea {
        border-radius: 8px;
    }
    
    /* 状态显示框增强 */
    .stAlert {
        border-radius: 8px !important;
    }
</style>
""", unsafe_allow_html=True)

# ==========================================
# HEADER & SYSTEM INFO
# ==========================================
st.markdown('<h1 class="main-title">HALAH System</h1>', unsafe_allow_html=True)
st.markdown('<div class="subtitle">Patient Consent Management Platform</div>', unsafe_allow_html=True)

# 用优雅的面板展示学术元数据
st.markdown("""
<div class="info-panel">
    <strong>History Access Link for Authorised Healthcare (Version 1)</strong>
</div>
""", unsafe_allow_html=True)

# 初始化数据仓库
@st.cache_resource(show_spinner="Loading Synthea EMR data...")
def _load_repo():
    return repository.SyntheaRepository("data/synthea")


repo = _load_repo()

# 侧边栏角色切换
role = st.sidebar.selectbox(
    "Select Access Role",
    ["Patient", "Guardian", "Clinician", "Auditor"]
)
onchain_ui.render_chain_badge()

# ==========================
# Revocation (Algorithm 6.4) and capacity transition (Algorithm 6.3), as the Patient and Guardian screens call them
# ==========================
def _show_notes(_key):
    """A message that follows a click which ends in a rerun is kept in the session and shown once after it."""
    for _kind, _text in st.session_state.pop(_key, []):
        getattr(st, _kind)(_text)


def _revoke_not_possible(_why):
    """An on-chain revoke that cannot be submitted now. The step fails with its reason, so the revocation records it
    as pending and keeps the link to the token until it is done."""
    def _refuse(_old):
        raise RuntimeError(_why)
    return _refuse


def _onchain_revoke(_c):
    """The on-chain step of a revocation for one consent: the ConsentSBTv4 revoke for a token of that contract, the
    ConsentSBTv3 revoke for a token of the older contract, and no chain step for a token of the local ledger.
    With ConsentSBTv4 configured, a consent that still holds its local token may have a mint under way. The chain is
    asked for the token of its commitment: a token that is found is recorded and revoked, and while the anchoring
    job runs without a confirmed mint the on-chain step stays pending."""
    if bc.has_chain_token(_c):
        return bc.revoke_onchain
    _t = str(_c.token_id or "")
    if bc.v4_enabled() and _t.startswith("SBT-LOCAL-"):
        from services import anchor_service
        _running = (anchor_service.job_status(_c.consent_id) or {}).get("status") == "running"
        try:
            _found = anchor_service.find_onchain_token_v4(_c)
        except Exception as _e:
            return _revoke_not_possible(f"the chain could not be asked for the token of this consent ({str(_e)[:120]})")
        if _found and _running:
            # the anchoring job records the mint itself when its receipt arrives
            _c.token_id, _c.token_address = f"SBT-{_found[0]}", _found[1]
            consent_db.update(_c)
        elif _found:
            anchor_service.reconcile(_c, audit_db, consent_db)       # a mint that no job recorded is recorded now
        if bc.has_chain_token(_c):
            return bc.revoke_onchain
        if _running:
            return _revoke_not_possible("the mint of this consent is not confirmed on chain yet")
    if bc.onchain_enabled() and not bc.v4_enabled() and _t.startswith("SBT-") and _t[4:].isdigit():
        return lambda _old: bc.revoke(int(str(_old.token_id)[4:]))
    return revocation_service.NO_CHAIN


def _revoke(_c, _did, _t):
    """One click of Revoke (Algorithm 6.4). The requested transition to REVOKED is checked against the transition
    policy and recorded first (Algorithm 6.2, lines 16 to 20). The revoker signs the request, and the service checks
    the authority of the revoker, submits the on-chain revoke, deletes the consent-bound copy, destroys its keys,
    deletes the link to the token and notifies every requester who received data. `_t` is the trusted time."""
    request_service.lifecycle_check(_c, _t, target="REVOKED", requested_by=_did)
    _sig, _addr = revocation_service.sign_revocation(_did, _c.consent_id)
    _how = _onchain_revoke(_c)
    if _how == revocation_service.NO_CHAIN:
        return revocation_service.revoke(_c, _did, signature=_sig, now=_t["time"], time_label=_t["source"], onchain_revoke=_how)
    with st.spinner(f"Revoking on {onchain_ui.network_label()} - waiting for block confirmation..."):
        return revocation_service.revoke(_c, _did, signature=_sig, now=_t["time"], time_label=_t["source"], onchain_revoke=_how)


def _revocation_notes(_r):
    """What a revocation did, as the lines a screen shows: the on-chain revoke, the deletion of the consent-bound
    copy and its keys, the recipients who were notified, and the steps that are still pending."""
    _oc, _sh, _notes = _r["onchain"], _r["shredded"], []
    if _oc["status"] == "SUCCESS":
        _notes.append(("success", f"Revoked on-chain. Tx: {_oc['tx_hash']}"))
        _notes.append(("caption", f"Block {_oc['block_number']} - gas used {_oc['gas_used']}"
                                  + (" - revocation root updated." if _oc.get("revocation_root") is not None else ".")))
        if onchain_ui.has_explorer():
            _notes.append(("markdown", f"[View revoke transaction on Etherscan]({bc.explorer_tx(_oc['tx_hash'])})"))
    elif _oc["status"] in ("FAILED", "NOT_SUBMITTED"):
        _notes.append(("warning", f"Local revoke recorded; on-chain revoke failed: {_oc.get('error')}"))
    elif _oc["status"] == "NOT_APPLICABLE" and _r.get("result") == "REVOKED":
        _notes.append(("success", "Consent revoked (local ledger)."))
    _notes.append(("info", f"Consent-bound copy deleted: {', '.join(_sh['modules_deleted']) or 'no copy was held'}. "
                           f"Keys destroyed: {_sh['keys_destroyed']}. "
                           f"Recipients notified: {', '.join(_r['recipients']) or 'none'}."))
    if _r["pending"]:
        _notes.append(("caption", f"Still pending: {revocation_service.pending_words(_r['pending'])}."))
    return _notes


def _take_over(_c, _patient, _t):
    """One click of the take-over at majority (Algorithm 6.3). The retirement of the old consent is a requested
    transition to REVOKED, checked and recorded first (Algorithm 6.2, lines 16 to 20). The re-issued consent has the
    patient as its sole guardian and a threshold of one. It is committed like every consent, the patient signs over
    its commitment, and with ConsentSBTv4 configured it is minted on chain and the old token is revoked on chain."""
    _now = _t["time"]
    if bc.v4_enabled() and str(_c.token_id or "").startswith("SBT-LOCAL-") and not getattr(_c, "successor_id", None):
        # the mint of the old consent may still arrive, and its token would then stay valid on chain
        return {"status": capacity_service.REFUSED, "reason": capacity_service.TOKEN_PENDING}
    request_service.lifecycle_check(_c, _t, target="REVOKED", requested_by=_patient)

    def _mint(_new):
        if bc.v4_enabled():
            return bc.mint_consent_v4(_new)
        # the local ledger token of the re-issued consent. execute_transition records the mint.
        _new.token_id = f"SBT-LOCAL-{_new.consent_id[:8]}"
        return _new.token_id

    def _revoke_old(_old):
        _how = _onchain_revoke(_old)
        return {"token_id": _old.token_id, "status": 1} if _how == revocation_service.NO_CHAIN else _how(_old)

    _prepared = {}
    if not getattr(_c, "successor_id", None):
        try:
            _new = capacity_service.prepare_successor(_c, _now)
            commitment_service.commit_consent(_new)
            _prepared = {"successor": _new, "verify_sig": identity_service.approval_verifier(_new),
                         "sign": lambda _d, _i: identity_service.sign_consent_v2(_d, _i, _new.commitment)}
        except ValueError:
            pass                                   # no transition is due, or a record that cannot be committed
    if bc.v4_enabled():
        with st.spinner(f"Re-issuing on {onchain_ui.network_label()} - waiting for block confirmation (mint, then revoke)..."):
            _tr = capacity_service.execute_transition(_c, _mint, _revoke_old, now=_now, **_prepared)
    else:
        _tr = capacity_service.execute_transition(_c, _mint, _revoke_old, now=_now, **_prepared)
    _new = _tr.get("successor")
    if _prepared and _new is not None and _patient in (_new.signature_data or {}):
        _new.signature_data[_patient]["version"] = 2          # signed over the commitment, like every approval
        consent_db.update(_new)
    return _tr


def _transition_notes(_tr):
    """The outcome of a take-over as the lines the Patient screen shows."""
    if _tr["status"] != capacity_service.COMPLETED:
        return [("warning", capacity_service.outcome_words(_tr))]
    _notes = [("success", f"Consent re-issued to the patient: {_tr['successor_id']} (guardian set: the patient, threshold 1).")]
    _mint, _rev = _tr.get("mint"), _tr.get("revoke")
    _mint = _mint if isinstance(_mint, dict) and _mint.get("tx_hash") else None
    _rev = _rev if isinstance(_rev, dict) and _rev.get("tx_hash") else None
    _parts = ([f"New token #{_mint.get('token_id')} minted in block {_mint.get('block_number')} (tx {_mint['tx_hash']})."] if _mint else []) \
        + ([f"Old token revoked in block {_rev.get('block_number')} (tx {_rev['tx_hash']})."] if _rev else [])
    if _parts:
        _notes.append(("caption", " ".join(_parts)))
    if onchain_ui.has_explorer():
        if _mint:
            _notes.append(("markdown", f"[View mint transaction on Etherscan]({bc.explorer_tx(_mint['tx_hash'])})"))
        if _rev:
            _notes.append(("markdown", f"[View revoke transaction on Etherscan]({bc.explorer_tx(_rev['tx_hash'])})"))
    return _notes


# ==========================
# ROLE: Patient (SRQ1)
# ==========================
if role == "Patient":
    st.header("Create Smart Consent Contract")
    
    # 使用两列布局提高表单表单美观度
    col1, col2 = st.columns(2)
    with col1:
        patients = repo.get_patient_dids()
        patient_did = st.selectbox("Patient DID (Identity Pointer)", patients["DID"].tolist())
        clinician = st.text_input("Authorised Clinician DID", "did:hospital:001")
        # the context of the consent, which VP compares with the context of a request
        jurisdiction = st.selectbox("Consent Context (jurisdiction code)", ["AU", "SA", "GB", "US"], index=0)
        scope = st.multiselect("Data Access Scope (EMR Modules)", ["Observation", "Medication", "Condition", "Procedure"])
        birth_text = st.text_input("Patient Date of Birth (YYYY-MM-DD, optional)", value="",
                                   help="When given, the consent passes to the patient's own authority at the age of majority.")
        trigger_event = st.text_input("Conditional Trigger Event (optional)", value="",
                                      help="An event that a clinician must attest before the consent becomes active.")
        
    with col2:
        guardians = st.text_area("Designated Guardian DIDs (Comma Separated)", "did:parent:A,did:parent:B")
        _g_count = len({g.strip() for g in guardians.split(",") if g.strip()}) or 1
        # Patient-defined threshold N with 1 <= N <= |G| (thesis Section 3.2.4). The default N = |G| is the N-of-N rule.
        threshold_n = st.number_input("Approval Threshold N (guardians who must approve)", min_value=1,
                                      max_value=_g_count, value=_g_count, step=1)
        st.markdown("**Contract Temporal Validity**")
        # The default start is the time at which this session opened the form, and it is kept for the session. A
        # default that changed with every run of the page would replace a start time that the patient typed.
        if "start_default" not in st.session_state:
            st.session_state["start_default"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        start_text = st.text_input("Start Time (YYYY-MM-DD HH:MM:SS)", value=st.session_state["start_default"])
        expiry_text = st.text_input("Expiry Time (YYYY-MM-DD HH:MM:SS)", value="2026-12-31 23:59:59")

    # 时间合法性检查
    try:
        start_datetime = datetime.strptime(start_text, "%Y-%m-%d %H:%M:%S")
        expiry_datetime = datetime.strptime(expiry_text, "%Y-%m-%d %H:%M:%S")
        if expiry_datetime <= start_datetime:
            st.error("Expiry time must be later than start time.")
            st.stop()
    except ValueError:
        st.error("Datetime format must be YYYY-MM-DD HH:MM:SS")
        st.stop()

    guardian_list = [g.strip() for g in guardians.split(",") if g.strip()]
    birth_date = None
    if birth_text.strip():
        try:
            birth_date = datetime.strptime(birth_text.strip(), "%Y-%m-%d").date()
        except ValueError:
            st.error("Date of birth format must be YYYY-MM-DD")
            st.stop()

    st.markdown("---")
    if st.button("Initial Consent"):
        if not scope:
            st.error("Select at least one EMR module for the data access scope.")
            st.stop()
        # The time of the checks below: the block timestamp when a chain is configured, the server clock in demo
        # mode. With a chain configured there is no fall-back to the server clock: the creation is refused.
        _ct, _ct_error = request_service.decision_time()
        if _ct is None:
            st.error(f"The time of the chain could not be read ({_ct_error}). "
                     "In on-chain mode the server clock is not used, so the consent cannot be created now.")
            st.stop()
        # Validate the authorised clinician D and the guardian set G (Algorithm 1, lines 5-6) with Algorithm 5.1:
        # the identifier resolved, the credential verified with its status, the role matched.
        if not identity_service.verify_identity(clinician.strip(), role="doctor", now=_ct["time"]):
            st.error("The authorised clinician must be one valid DID that holds a valid clinician credential.")
            st.stop()
        if not guardian_list or not all(identity_service.verify_identity(g, role="guardian", now=_ct["time"]) for g in guardian_list):
            st.error("Enter at least one guardian DID; each must be a valid DID that holds a valid guardian credential.")
            st.stop()
        if len(set(guardian_list)) != len(guardian_list):
            st.error("Each guardian DID may appear only once.")
            st.stop()
        try:
            consent = create_consent(
                patient_did,
                clinician.strip(),
                guardian_list,
                scope,
                "Treatment",
                start_datetime.isoformat(),
                expiry_datetime.isoformat(),
                threshold=int(threshold_n),
                context=jurisdiction,
                patient_birth_date=birth_date
            )
            # The consent commitment c (Section 7.2.3): the value the guardians sign and the token carries.
            # Its opening stays in the record, off chain.
            commitment_service.commit_consent(consent)
        except ValueError as _e:
            st.error(f"Consent specification rejected: {_e}")
            st.stop()
        consent_db.save(consent)

        # 触发审计日志并捕获返回值记录虚拟交易
        log_entry = audit_db.log(
            actor_did=patient_did,
            actor_role="Patient",
            action="CREATE_CONSENT",
            patient_did=patient_did,
            consent_id=consent.consent_id,
            scope=scope,
            purpose="Treatment",
            result="SUCCESS"
        )
        # Algorithm 6.3: the capacity transition at the age of majority and the conditional trigger are
        # recorded with the consent, and a consent that waits on either of them is SUSPENDED.
        if birth_date is not None:
            # The trusted time says whether the patient has reached majority already.
            capacity_service.schedule_majority_transition(consent, _ct["time"])
        if trigger_event.strip():
            trigger_service.add_trigger(consent, trigger_event.strip(), attester_role="doctor",
                                        actor_did=patient_did, actor_role="Patient")
        
        st.success("Consent contract created and logged (off-chain).")
        # 视觉渲染渲染区块链生成的哈希结果
        st.markdown(f"""
        <div class="blockchain-badge">
            <b>[CONSENT CREATED - OFF-CHAIN]</b><br>
            • <b>Consent ID:</b> {consent.consent_id}<br>
            • <b>Commitment:</b> {consent.commitment[:18]}... (its opening stays off chain)<br>
            • <b>TxHash:</b> OFF-CHAIN - anchoring happens after {consent.threshold} of {len(consent.guardian_dids)} guardian approvals <br>
            • <b>Block Number:</b> pending
        </div>
        """, unsafe_allow_html=True)


    # ---- My Consents / Revoke (additive) ----
    st.markdown("---")
    st.subheader("My Consents")
    _show_notes("consent_notes")
    _mine = consent_db.get_patient_consent(patient_did)
    if not _mine:
        st.caption("No consents yet for this patient DID.")
    # The time of the states, of a revocation and of a take-over: the block timestamp when a chain is configured,
    # the server clock in demo mode. With a chain configured there is no fall-back to the server clock.
    _pt, _pt_error = request_service.decision_time() if _mine else (None, None)
    if _mine and _pt is None:
        st.error(f"The time of the chain could not be read ({_pt_error}). In on-chain mode the server clock is not used, "
                 "so no consent can be revoked or taken over until the chain can be read.")
    for _c in _mine:
        # the state at the trusted time. lifecycle_state changes nothing in the record
        _state = lifecycle_state(_c, _pt["time"]) if _pt else (_c.state or "not derived")
        _cols = st.columns([3, 2, 3, 2])
        _cols[0].markdown(f"`{_c.consent_id[:8]}...` -> {_c.requester_did}")
        _cols[1].markdown(f"**{_state}**")
        _cols[2].markdown(f"{len(guardian_approvals(_c))}/{_c.threshold} sigs - token: {_c.token_id or '-'}")
        _replaced = getattr(_c, "successor_id", None)
        _due = bool(_pt) and bool(capacity_service.pending_transitions(_c, _pt["time"]))
        if getattr(_c, "revoked", False) or _state == "REVOKED":
            _cols[3].markdown(f"RE-ISSUED as `{_replaced[:8]}...`" if _replaced else "REVOKED")
            if _pt is None:
                continue
            if _replaced and _due:
                # re-issued, and the revocation of the old token on chain failed: the same click submits it again
                if st.button("Take over this consent (age of majority)", key=f"tr_{_c.consent_id}"):
                    st.session_state["consent_notes"] = _transition_notes(_take_over(_c, patient_did, _pt))
                    st.rerun()
            elif not _replaced and revocation_service.pending_steps(_c.consent_id):
                # a step of Algorithm 6.4 failed (for example the on-chain revoke): it is finished here
                if _cols[3].button("Complete Revocation", key=f"cr_{_c.consent_id}"):
                    with st.spinner(f"Completing the revocation on {onchain_ui.network_label()}..."):
                        _r = revocation_service.complete_revocation(_c, onchain_revoke=_onchain_revoke(_c),
                                                                    now=_pt["time"], time_label=_pt["source"])
                    st.session_state["consent_notes"] = ([("success", "Revocation completed.")] if _r["complete"] else []) \
                        + _revocation_notes(_r)
                    st.rerun()
            continue
        if _pt is None:
            continue
        if _due:
            st.caption(f"`{_c.consent_id[:8]}...`: the patient has reached the age of majority. "
                       "The consent is suspended until the patient takes it over.")
            if st.button("Take over this consent (age of majority)", key=f"tr_{_c.consent_id}"):
                st.session_state["consent_notes"] = _transition_notes(_take_over(_c, patient_did, _pt))
                st.rerun()
        if _cols[3].button("Revoke", key=f"rv_{_c.consent_id}"):
            _r = _revoke(_c, patient_did, _pt)
            if _r["result"] == "DENIED":
                st.session_state["consent_notes"] = [("error", f"Revocation refused: {revocation_service.refusal_words(_r['reason'])}. "
                                                               "The refused request is recorded in the audit ledger.")]
            else:
                st.session_state["consent_notes"] = _revocation_notes(_r)
            st.rerun()


# ==========================
# ROLE: Guardian (SRQ2)
# ==========================
if role == "Guardian":
    st.header("Guardian Cryptographic Approval")
    cid = st.text_input("Enter Target Consent ID")
    consent = consent_db.get(cid)
    
    if consent:
        # The lifecycle state at the trusted time: the block timestamp when a chain is configured.
        _gt, _gt_error = request_service.decision_time()
        # The line stands in one place of the page. It is drawn here, and drawn again after an accepted approval,
        # so that the page of a click shows the state that the click left.
        _state_line = st.empty()

        def _draw_state():
            try:
                _gstate = lifecycle_state(consent, _gt["time"]) if _gt else "not derived, the time of the chain could not be read"
            except Exception:
                _gstate = "not derived, the record cannot be read"
            _state_line.info(f"Found consent for Patient: `{consent.patient_did}` (state: {_gstate})")
        _draw_state()
        _tid = str(consent.token_id or "")
        _anchored = _tid.startswith("SBT-") and _tid[4:].isdigit()
        if _anchored:
            st.success(f"Already anchored on {onchain_ui.network_label()} - token #{_tid[4:]}")
            if consent.token_address:
                st.caption("The token carries the commitment and the revocation state only. "
                           f"Per-consent address: {consent.token_address}.")
            # the transaction of the mint, from its record in the audit ledger
            _mint = next((e for e in reversed(audit_db.get()) if e.get("consent_id") == consent.consent_id
                          and e.get("action") == "ONCHAIN_MINT" and e.get("result") == "SUCCESS" and e.get("tx_hash")), None)
            if _mint:
                _gas = (_mint.get("metadata") or {}).get("gas_used")
                st.caption(f"Minted in block {_mint.get('block_number')} (tx {_mint['tx_hash']})"
                           + (f" - gas used {_gas}." if _gas else "."))
                if onchain_ui.has_explorer():
                    st.markdown(f"[View mint transaction on Etherscan]({bc.explorer_tx(_mint['tx_hash'])})")
        elif len(guardian_approvals(consent)) >= consent.threshold and not getattr(consent, "revoked", False):
            # (a revoked consent is not anchored again: its revocation deleted the link to the token)
            st.warning(f"Threshold {len(guardian_approvals(consent))}/{consent.threshold} reached but NOT anchored on {onchain_ui.network_label()} yet (token: {consent.token_id or '-'}). "
                       "Click below and wait ~30 s without touching anything.")
            _c1, _c2 = st.columns(2)
            if _c1.button(f"Sync from {onchain_ui.network_label()} (find existing mint)", key=f"sync_{consent.consent_id}"):
                from services import anchor_service
                try:
                    _res = anchor_service.reconcile(consent, audit_db, consent_db)
                    if _res["status"] == "reconciled":
                        st.success(f"Found on-chain: token #{_res['token_id']} block {_res['block_number']} - ledger updated ({_res['duplicates']} duplicate mint(s))")
                        if onchain_ui.has_explorer() and _res.get("tx_hash"):
                            st.markdown(f"[View transaction on Etherscan]({bc.explorer_tx(_res['tx_hash'])})")
                    elif _res["status"] == "none":
                        st.info("No matching mint found on-chain for this consent.")
                except Exception as _e:
                    st.warning(f"Sync failed: {_e}")
            if _c2.button(f"Anchor on {onchain_ui.network_label()} now (background)", type="primary", key=f"anchor_{consent.consent_id}"):
                onchain_ui.render_onchain_anchor_async(consent, audit_db, consent_db)
            from services import anchor_service as _as
            _j = _as.job_status(consent.consent_id)
            if _j and _j.get("status") == "done":
                st.success(f"Anchored - token #{_j['result'].get('token_id')} block {_j['result'].get('block_number')}")
            elif _j and _j.get("status") == "running":
                st.info("Anchoring in progress - refresh in ~30 s.")
        did = st.selectbox("Select Your Guardian DID Identity", consent.guardian_dids)

        if st.button("Sign Consent via VC"):
            if did in consent.signatures:
                st.warning("This guardian has already signed this consent (one signature per guardian).")
                st.stop()
            # With a chain configured there is no fall-back to the server clock: nothing is signed or recorded.
            if _gt is None:
                st.error(f"The time of the chain could not be read ({_gt_error}). "
                         "In on-chain mode the server clock is not used, so the approval cannot be accepted now.")
                st.stop()
            # An approval is not added to a revoked consent: nothing is signed, committed or recorded.
            if getattr(consent, "revoked", False) or lifecycle_state(consent, _gt["time"]) == "REVOKED":
                st.warning("This consent is revoked: an approval cannot be added.")
                st.stop()
            # Algorithm 5.1: the guardian's identifier is resolved, the credential is verified with its status and
            # the role is matched before the approval is accepted. A valid verification is recorded (line 21).
            _id = identity_service.verify_identity(did, role="guardian", now=_gt["time"], record=functools.partial(
                identity_service.record_identity_evidence, consent_id=consent.consent_id,
                patient_did=consent.patient_did, actor_role="Guardian"))
            if not _id.valid:
                audit_db.log(actor_did=did, actor_role="Guardian", action="SIGN_CONSENT",
                             patient_did=consent.patient_did, consent_id=consent.consent_id,
                             scope=consent.scope, purpose=consent.purpose, result="REJECTED",
                             metadata={"reason": _id.reason, "credential_checks": dict(_id.checks),
                                       "time_source": _gt["source"]})
                st.error(f"Guardian credential is not valid ({identity_service.refusal_words(_id)}) - approval rejected.")
                st.stop()
            # Algorithm 5.2: the approval is an EIP-712 signature over the consent commitment c. A record made
            # before the commitment existed is committed at its first approval. A record that already carries
            # approvals over the consent identifier keeps that form, so that old records still open.
            if not consent.commitment and not consent.signatures:
                try:
                    commitment_service.commit_consent(consent)
                except ValueError:
                    pass
            try:
                if consent.commitment:
                    _sig, _addr = identity_service.sign_consent_v2(did, consent.consent_id, consent.commitment)
                    _signed = identity_service.verify_signature_v2(did, consent.consent_id, consent.commitment, _sig,
                                                                   address=(consent.guardian_addresses or {}).get(did))
                    _approval = {"scheme": "EIP-712", "version": 2, "signer": _addr, "signature": _sig}
                else:
                    _sig, _addr = sign_consent(did, consent.consent_id)
                    _signed = verify_signature(did, consent.consent_id, _sig)
                    _approval = {"scheme": "EIP-712", "signer": _addr, "signature": _sig}
            except ValueError:
                _signed = False
            if not _signed:
                st.error("EIP-712 signature verification failed - approval rejected.")
                st.stop()
            if not hasattr(consent, "signature_data") or consent.signature_data is None:
                consent.signature_data = {}
            consent.signature_data[did] = _approval
            consent.signatures.append(did)
            consent_db.update(consent)
            _draw_state()

            # 记录审计并回填链上凭证
            _meta = {
                "threshold": consent.threshold,
                "signature_count": len(guardian_approvals(consent)),
                "scheme": "EIP-712",
                "guardian_address": _addr,
                "signature": _sig,
                "credential_id": _id.evidence["credential_id"],
                "credential_issuer": _id.evidence["issuer"],
                "time_source": _gt["source"]
            }
            if _approval.get("version"):
                _meta["version"] = _approval["version"]
            log_entry = audit_db.log(
                actor_did=did,
                actor_role="Guardian",
                action="SIGN_CONSENT",
                patient_did=consent.patient_did,
                consent_id=consent.consent_id,
                scope=consent.scope,
                purpose=consent.purpose,
                result="SUCCESS",
                metadata=_meta
            )

            _over = " over the consent commitment" if _approval.get("version") else ""
            st.success(f"Guardian identity and credential verified; EIP-712 signature{_over} verified (signer {_addr[:10]}...). Multi-sig: {len(guardian_approvals(consent))}/{consent.threshold}")

            # 如果多签满足阈值，铸造SBT令牌
            # The threshold N decides activation (Algorithm 5.2): the N-th distinct valid approval from a member
            # of G issues the consent. A later approval is recorded and mints nothing, and a revoked consent is
            # not issued.
            if threshold_met(consent) and not consent.token_id and lifecycle_state(consent) != "REVOKED":
                consent.token_id = f"SBT-LOCAL-{consent.consent_id[:8]}"
                consent_db.update(consent)
                _draw_state()                              # the state that the approval and the token leave
                mint_log = audit_db.log(
                    actor_did="Blockchain",
                    actor_role="SmartContract",
                    action="MINT_SBT",
                    patient_did=consent.patient_did,
                    consent_id=consent.consent_id,
                    scope=consent.scope,
                    purpose=consent.purpose,
                    metadata={"token_id": consent.token_id}
                )
                # Algorithm 6.5 releases from the consent-bound encrypted copy. The consented modules are sealed
                # now, each under its own key (one key per consent and module). A consent that has no copy yet
                # is sealed at its first use.
                try:
                    data_vault.default_vault().seal_from_source(consent, repo.query_patient)
                except Exception:
                    pass
                st.balloons()
                st.markdown(f"""
                <div class="blockchain-badge" style="border-left-color: #00f5d4;">
                    <b>[SBT MINTED - LOCAL LEDGER]</b><br>
                    • <b>Soulbound Token ID:</b> {consent.token_id}<br>
                    • <b>Status:</b> {len(guardian_approvals(consent))}/{consent.threshold} guardian approval reached - on-chain anchoring result shown below.
                </div>
                """, unsafe_allow_html=True)
                onchain_ui.render_onchain_anchor_async(consent, audit_db, consent_db)
            elif len(guardian_approvals(consent)) > consent.threshold:
                st.caption("The threshold was reached before this approval: it is recorded, and no new token is minted.")

        # ---- Revocation by a guardian (Algorithm 6.4) ----
        # The control is offered for every consent that is found, also a revoked or a re-issued one, so that a
        # refused request is answered and recorded. The guardian is the one chosen in the selector above.
        st.markdown("---")
        st.caption("Revocation: before the patient's majority any one guardian may revoke alone. "
                   "After it only the patient may revoke.")
        if _gt is None:
            st.caption("The time of the chain could not be read, so a revocation cannot be requested now.")
        elif st.button("Revoke Consent (as guardian)", key=f"grv_{consent.consent_id}"):
            _r = _revoke(consent, did, _gt)
            if _r["result"] == "DENIED":
                st.session_state["guardian_notes"] = [("error", f"Revocation refused: {revocation_service.refusal_words(_r['reason'])}. "
                                                                "The refused request is recorded in the audit ledger.")]
            elif _r["result"] == "ALREADY_REVOKED":
                # a step of the earlier revocation that this request carried out on chain, or tried to, is shown
                st.session_state["guardian_notes"] = [("info", "This consent is already revoked.")] + (
                    _revocation_notes(_r) if _r["onchain"]["status"] in ("SUCCESS", "FAILED") else [])
            elif _r["revoker_role"] == "Patient":
                # the patient is the sole guardian of a re-issued consent, so the selector offers the patient
                st.session_state["guardian_notes"] = [("success", f"Consent revoked by the patient {did}.")] + _revocation_notes(_r)
            else:
                st.session_state["guardian_notes"] = [("success", f"Consent revoked by guardian {did}. One guardian may revoke "
                                                                  "alone before the patient's majority.")] + _revocation_notes(_r)
            st.rerun()
        _show_notes("guardian_notes")

# ==========================
# ROLE: Clinician (SRQ3, SRQ4, SRQ5)
# ==========================
def _show_request_outcome(_out, _empty_scope=False):
    """The answer to one submitted request (Algorithm 6.5): the released modules, or one line that names the
    failed checks and, when one of the nine of Section 6.3.1 applies, the deny code."""
    if _out["outcome"] == request_service.GRANTED:
        st.success("Cryptographic Verification Successful — Access Granted.")
        _ref = _out.get("proof_reference") or {}
        _v = _out.get("verification")
        if _v:
            # The proof of the decision rule was accepted by the verifier contract before anything was decrypted.
            st.markdown(f"""
            <div class="blockchain-badge" style="border-left-color: #00f5d4;">
                <b>[DECISION PROOF VERIFIED ON CHAIN]</b><br>
                • <b>Tx hash:</b> {_v['tx_hash']}<br>
                • <b>Block:</b> {_v['block_number']} • <b>Gas used:</b> {_v['gas_used']}<br>
                • <b>Request tag:</b> {_ref.get('tag')}
            </div>
            """, unsafe_allow_html=True)
            if onchain_ui.has_explorer():
                st.markdown(f"[View verification transaction on Etherscan]({_v['explorer_tx']})")
        else:
            st.caption(f"Proof mode: {_ref.get('mode')} (demo mode: checked locally, not on chain)")
        _when = _out["time"]
        _src = (f"block timestamp, block {_when['block_number']}" if _when["source"] == time_source.SOURCE_BLOCK
                else "server clock, demo mode")
        st.caption(f"Decision time {_when['time']:%Y-%m-%d %H:%M:%S} ({_src}). "
                   f"Released from the consent-bound encrypted copy: {', '.join(_out['modules'])}.")

        # ---------------------------------
        # Display EMR
        # ---------------------------------
        st.subheader("Authorised Medical Records")
        for module, records in _out["data"].items():
            with st.expander(module.upper(), expanded=True):
                if records.empty:
                    st.warning("No records found for this patient in this module.")
                else:
                    st.dataframe(records, use_container_width=True)
                    st.download_button(
                        "Download CSV",
                        records.to_csv(index=False).encode("utf-8"),
                        file_name=f"{module.lower()}_records.csv",
                        mime="text/csv",
                        key=f"download_{module.lower()}",
                    )
        return

    _line = "Access Denied. Failed checks: " + ", ".join(_out["failed_checks"]) + "."
    if _out["deny_code"]:
        _line += f" Deny code: {_out['deny_code']}."
    if (_out.get("decision") or {}).get("VI") and _out.get("state") not in (None, "ACTIVE"):
        _line += f" Consent state: {_out['state']}."
    st.error(_line + " The denied request is recorded in the audit ledger.")
    if _empty_scope:
        st.warning("Please select at least one data module.")
    if request_service.CHECK_PROOF in _out["failed_checks"]:
        _refused = (_out.get("verification") or {}).get("reason_text")
        if _out.get("proof_error"):
            _again = (" Repeat the request when the anchoring is confirmed."
                      if _out["proof_error"] == request_service.TOKEN_NOT_CONFIRMED else "")
            st.caption(f"No proof could be made: {_out['proof_error']}.{_again}")
        elif _refused:
            st.caption(f"The verifier contract did not accept the proof: {_refused}. Repeat the request.")


if role == "Clinician":
    st.header("Secure Patient Data Access")

    cid = st.text_input(
        "Enter Authorised Consent ID",
        placeholder="e.g. CONSENT-001"
    )

    if cid:
        consent = consent_db.get(cid)

        if consent is None:
            st.error("Consent record not found.")

        else:
            # ---------------------------------
            # Consent Information
            # ---------------------------------
            st.subheader("Consent Information")

            c1, c2, c3 = st.columns(3)

            with c1:
                st.metric(
                    "Patient",
                    consent.patient_did
                )

            with c2:
                st.metric(
                    "Consent ID",
                    consent.consent_id
                )

            with c3:
                st.metric(
                    "Purpose",
                    consent.purpose
                )

            # ---------------------------------
            # Requester identity and credential (VI)
            # ---------------------------------
            requester = st.text_input("Your Clinician DID (requester)", key="requester_did").strip()
            if not requester:
                st.info("Enter your clinician DID. Your DID and credential are checked as part of VI.")
                st.stop()

            # The time t of the decision: the block timestamp when a chain is configured, the server clock in demo
            # mode. With a chain configured there is no fall-back to the server clock: a request is refused.
            _t, _t_error = request_service.decision_time()
            if _t is None:
                st.error(f"The time of the chain could not be read ({_t_error}). "
                         "In on-chain mode the server clock is not used, so the request is refused.")
                if st.button("Request Data Access", type="primary", key="request_no_time"):
                    _show_request_outcome(request_service.submit_request(consent, requester, [], "", None))
                st.stop()
            _now = _t["time"]

            # Algorithm 5.1 for the requester: the identifier resolved, the credential verified with its status,
            # the role matched. The evidence is recorded when the request is submitted.
            _rid = identity_service.verify_identity(requester, role="doctor", now=_now)
            if _rid.valid:
                st.caption(f"Clinician credential verified: {_rid.evidence['credential_id']} (issuer {_rid.evidence['issuer']}).")
            else:
                st.warning(f"No valid clinician credential for this DID ({identity_service.refusal_words(_rid)}).")
            if requester != consent.requester_did:
                st.warning("This DID is not the clinician authorised by this consent.")

            # The notices of withdrawal sent to this clinician (Algorithm 6.4, the notification step), read from E.
            _notices = notification_service.inbox(requester) if _rid.valid else []
            if _notices:
                with st.expander(f"Withdrawal notices for this clinician ({len(_notices)})"):
                    for _n in _notices:
                        st.write(f"Consent `{_n.get('consent_id')}` - withdrawn at {str(_n.get('withdrawn_at'))[:19].replace('T', ' ')} - "
                                 f"modules received: {', '.join(_n.get('modules') or [])} - releases: {_n.get('releases')}")
                        st.caption(_n.get("message"))

            if _t["source"] == time_source.SOURCE_BLOCK:
                st.caption(f"Decision time: {_now:%Y-%m-%d %H:%M:%S} - source: block timestamp (block {_t['block_number']})")
            else:
                st.caption(f"Decision time: {_now:%Y-%m-%d %H:%M:%S} - source: server clock (demo mode)")

            # ---------------------------------
            # Conditional triggers (Algorithm 6.3)
            # ---------------------------------
            # The answer to an attestation is kept for the run that follows it, which draws the page again.
            _note = st.session_state.pop("attestation_note", None)
            if _note:
                (st.success if _note[0] else st.error)(_note[1])
            _waiting = trigger_service.waiting_triggers(consent)
            if _waiting and _rid.valid:
                with st.expander(f"Conditional triggers waiting for an attestation ({len(_waiting)})", expanded=True):
                    for _tr in _waiting:
                        _tev = _tr.get("event") if isinstance(_tr, dict) else str(_tr)
                        _trole = _tr.get("attester_role", "doctor") if isinstance(_tr, dict) else "doctor"
                        st.write(f"Event: **{_tev}** (attester role: {'clinician' if _trole == 'doctor' else _trole})")
                        if st.button(f"Attest this event as {requester}", key=f"att_{_tr.get('id') if isinstance(_tr, dict) else _tev}"):
                            # the attestation is signed and presented at the trusted time
                            _att = trigger_service.sign_attestation(requester, consent, _tev, signed_at=_now)
                            _pr = trigger_service.present_attestation(consent, _att, trigger_id=_tr.get("id"), now=_now,
                                                                      verify_did=identity_service.verify_identity)
                            if _pr["VALID"]:
                                st.session_state["attestation_note"] = (True, "Attestation verified and recorded. The trigger is satisfied.")
                            else:
                                st.session_state["attestation_note"] = (False, f"Attestation refused: {trigger_service.refusal_words(_pr['reason'])}.")
                            st.rerun()
            # Algorithm 6.3: triggers and capacity transitions are evaluated before the decision.
            capacity_service.evaluate_conditions(consent, _now)
            state = evaluate_state(consent, _now)

            # ---------------------------------
            # The request as the clinician declares it
            # ---------------------------------
            # The context, the purpose and the scope of the request. VP compares the three with the consent. The
            # selector offers every record module, so a request outside the consented scope can be made: it is
            # refused and recorded.
            st.subheader("Request Patient Data")
            _req_jur = st.selectbox("Request Context (jurisdiction code)", ["AU", "SA", "GB", "US"], index=0, key="req_jur")
            _purposes = sorted(ALLOWED_PURPOSES)
            _req_purpose = st.selectbox("Purpose of this request", _purposes,
                                        index=_purposes.index("Treatment") if "Treatment" in _purposes else 0, key="req_purpose")
            scope = st.multiselect(
                "Select Request Scope",
                options=["Observation", "Medication", "Condition", "Procedure"],
                help="Select the EMR modules you request. A request outside the consented scope is refused and recorded."
            )
            if scope:
                st.info(
                    f"Requested Modules: {', '.join(scope)}"
                )

            # ---------------------------------
            # Decision matrix (Algorithm 6.1)
            # ---------------------------------
            # The matrix of the request as declared so far. VA counts the approvals alone, and the token and
            # revocation conditions are reported by VL. The scope is compared once a module is chosen.
            _full = request_service.decide(consent, requester, scope or None, _req_purpose, _req_jur, _now)
            _m = {k: _full[k] for k in MATRIX_KEYS}
            st.markdown("**Decision matrix - ALLOW = VI AND VA AND VP AND VT AND VL**")
            # The table and its caption stand in one place of the page. Before a click they show the request as
            # declared so far. After a click they are drawn again from the decision of the submitted request.
            _matrix_place = st.empty()

            def _draw_matrix(_decision, _failed_checks, _deny_code):
                with _matrix_place.container():
                    st.table(pd.DataFrame([{k: ("PASS" if _decision[k] else "FAIL") for k in MATRIX_KEYS}]))
                    if _failed_checks:
                        st.caption("Failed checks: " + ", ".join(_failed_checks)
                                   + (f" | Deny code: {_deny_code}" if _deny_code else ""))
            # A deny code is shown only when it is one of the nine of Section 6.3.1. Any other failure is named.
            _failed = request_service.failed_checks(_full)
            _code = request_service.shown_code(_full)
            _draw_matrix(_full, _failed, _code)

            def _request():
                # One click: the request path runs once, from the lifecycle check (STATE_CHECK) to the release by
                # Algorithm 6.5 (DATA_ACCESS). On ALLOW the proof is verified before anything is decrypted.
                _out = request_service.submit_request(consent, requester, scope, _req_purpose, _req_jur,
                                                      source=repo.query_patient, time=_t)
                if _out.get("decision"):
                    _draw_matrix(_out["decision"], _out["failed_checks"], _out["deny_code"])
                _show_request_outcome(_out, _empty_scope=not scope)

            # A requester who fails VI is refused before any consent detail or data is shown (Algorithm 4).
            if not _m["VI"]:
                st.error("Identity and authority check (VI) failed: this requester cannot access this consent.")
                if st.button("Request Data Access", type="primary", key="request_vi_fail"):
                    _request()
                st.stop()

            if state.upper() in ["ACTIVE", "SUCCESS"]:

                st.success(
                    f"🟢 Consent State: {state}"
                )

                # ---------------------------------
                # Authorized Scope
                # ---------------------------------
                st.subheader("Authorised Data Scope")

                st.write(
                    "The following EMR modules are authorised "
                    "under the patient's consent:"
                )

                st.write(consent.scope)

                # ---------------------------------
                # Access with the proof of the decision
                # ---------------------------------
                if bc.v4_enabled():
                    _label = "Request Data Access (decision proof, verified on chain)"
                else:
                    _label = ("Request Data Access (Groth16 ZK proof)" if zk_available()
                              else "Request Data Access (integrity proof - ZK placeholder)")
                if st.button(_label, type="primary"):
                    _request()

            else:

                st.error(
                    f"Consent is not active. Current state: {state}"
                    + (f" (deny code: {_code})" if _code else "")
                )

                st.warning(
                    "The Clinician cannot access patient data "
                    "because the consent is not currently valid."
                )

                # A request on a consent that is not ACTIVE is denied and recorded,
                # like every other denied request (lifecycle-based denial).
                if st.button("Request Data Access", type="primary", key="request_inactive"):
                    _request()




# ==========================
# ROLE: Auditor (SRQ6)
# ==========================
if role == "Auditor":

    st.header("Blockchain Audit & Consent Lifecycle")

    raw_audit_data = audit_db.get()

    if not raw_audit_data:
        st.info("No audit records found.")
        st.stop()

    audit_df = pd.DataFrame(raw_audit_data)
    # dict/list cells (metadata, scope) have mixed shapes -> render as JSON text so Arrow can serialise them
    import json as _json
    for _col in ("metadata", "scope"):
        if _col in audit_df.columns:
            audit_df[_col] = audit_df[_col].apply(lambda v: None if v is None else _json.dumps(v, default=str))
    # The role of the clinician is stored under the key "Doctor", which the earlier records carry. It is shown as Clinician.
    if "actor_role" in audit_df.columns:
        audit_df["actor_role"] = audit_df["actor_role"].replace("Doctor", "Clinician")
    _first_cols = [c for c in ["timestamp", "action", "actor_role", "onchain", "tx_hash", "block_number", "consent_id", "result"] if c in audit_df.columns]
    if _first_cols:
        audit_df = audit_df[_first_cols + [c for c in audit_df.columns if c not in _first_cols]]

    # ---------------------------------
    # Dashboard Metrics
    # ---------------------------------
    m1, m2, m3, m4 = st.columns(4)

    m1.metric(
        "Total Events",
        len(audit_df)
    )

    m2.metric(
        "Consent Events",
        audit_df["action"].eq("CREATE_CONSENT").sum()
        if "action" in audit_df.columns else 0
    )

    m3.metric(
        "Access Requests",
        audit_df["action"].eq("DATA_ACCESS").sum()
        if "action" in audit_df.columns else 0
    )

    m4.metric(
        "On-chain Anchors",
        int(audit_df["onchain"].fillna(False).sum()) if "onchain" in audit_df.columns else 0
    )

    # ---------------------------------
    # Select Consent
    # ---------------------------------
    if "consent_id" in audit_df.columns:

        consent_ids = (
            audit_df["consent_id"]
            .dropna()
            .astype(str)
            .unique()
            .tolist()
        )

        selected_cid = st.selectbox(
            "Select Consent to Audit",
            consent_ids
        )

        consent_events = audit_df[
            audit_df["consent_id"].astype(str)
            == selected_cid
        ].copy()

        # ---------------------------------
        # Consent Lifecycle
        # ---------------------------------
        st.subheader("🔗 Consent Lifecycle")

        for _, event in consent_events.iterrows():

            actor = event.get(
                "actor_did",
                "Unknown"
            )

            role_name = event.get(
                "actor_role",
                "Unknown"
            )

            action = event.get(
                "action",
                "Unknown"
            )

            result = event.get(
                "result",
                "Unknown"
            )

            timestamp = event.get(
                "timestamp",
                "Unknown"
            )

            st.markdown(
                f"""
                **{timestamp}**

                Actor: `{actor}`  
                Role: `{role_name}`  
                Action: `{action}`  
                Result: `{result}`
                """
            )

            st.divider()

        # ---------------------------------
        # Detailed Event Records
        # ---------------------------------
        st.subheader("Detailed Audit Records")

        st.dataframe(
            consent_events,
            use_container_width=True
        )

    # ---------------------------------
    # Complete Ledger
    # ---------------------------------
    st.subheader("Audit Ledger - local events (tx_hash = None) + on-chain anchors (onchain = True)")

    st.dataframe(
        audit_df,
        use_container_width=True
    )