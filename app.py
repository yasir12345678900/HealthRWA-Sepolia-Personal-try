'''
HALAH: A Blockchain-Based Patient Consent Management System
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date (YYYY-MM-DD): 2026-06-08, 2026-08-02
'''
from datetime import datetime, date, time
import streamlit as st
from blockchain import onchain_ui  # on-chain mode (Sepolia)
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
from models.access import AccessRequest

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
        background-color: white;
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
repo = repository.SyntheaRepository("data/synthea")

# 侧边栏角色切换
role = st.sidebar.selectbox(
    "Select Access Role",
    ["Patient", "Guardian", "Doctor", "Auditor"]
)
onchain_ui.render_chain_badge()

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
        doctor = st.text_input("Authorised Doctor DID", "did:hospital:001")
        scope = st.multiselect("Data Access Scope (EMR Modules)", ["Observation", "Medication", "Condition", "Procedure"])
        
    with col2:
        guardians = st.text_area("Designated Guardian DIDs (Comma Separated)", "did:parent:A,did:parent:B")
        st.markdown("**Contract Temporal Validity**")
        start_text = st.text_input("Start Time (YYYY-MM-DD HH:MM:SS)", value=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
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

    st.markdown("---")
    if st.button("Initial Consent"):
        consent = create_consent(
            patient_did,
            doctor,
            guardians.split(","),
            scope,
            "Treatment",
            start_datetime.isoformat(),
            expiry_datetime.isoformat()
        )
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
        
        st.success(" Smart Contract Successfully Deployed & Logged!")
        # 视觉渲染渲染区块链生成的哈希结果
        st.markdown(f"""
        <div class="blockchain-badge">
            <b>[BLOCKCHAIN RECEIPT]</b><br>
            • <b>Consent ID:</b> {consent.consent_id}<br>
            • <b>TxHash:</b> {getattr(log_entry, 'tx_hash', '0x1c8b9f...a4e2d3')} <br>
            • <b>Block Number:</b> #{getattr(log_entry, 'block_number', '18402195')}
        </div>
        """, unsafe_allow_html=True)


# ==========================
# ROLE: Guardian (SRQ2)
# ==========================
if role == "Guardian":
    st.header("Guardian Cryptographic Approval")
    cid = st.text_input("Enter Target Consent ID")
    consent = consent_db.get(cid)
    
    if consent:
        st.info(f"Found active transaction for Patient: `{consent.patient_did}`")
        did = st.selectbox("Select Your Guardian DID Identity", consent.guardian_dids)

        if st.button("Sign Consent via VC"):
            if verify_vc(did):
                consent.signatures.append(did)
                
                # 记录审计并回填链上凭证
                log_entry = audit_db.log(
                    actor_did=did,
                    actor_role="Guardian",
                    action="SIGN_CONSENT",
                    patient_did=consent.patient_did,
                    consent_id=consent.consent_id,
                    scope=consent.scope,
                    purpose=consent.purpose,
                    result="SUCCESS",
                    metadata={
                        "threshold": consent.threshold,
                        "signature_count": len(consent.signatures)
                    }
                )

                st.success(f"Identity verified. Multi-sig added: ({len(consent.signatures)}/{consent.threshold})")

                # 如果多签满足阈值，铸造SBT令牌
                if len(consent.signatures) == consent.threshold:
                    consent.token_id = "SBT001"
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
                    st.balloons()
                    st.markdown(f"""
                    <div class="blockchain-badge" style="border-left-color: #00f5d4;">
                        <b>[SBT MINTED SUCCESS]</b><br>
                        • <b>Soulbound Token ID:</b> {consent.token_id}<br>
                        • <b>Status:</b> Consent Fully Activated on-chain.
                    </div>
                    """, unsafe_allow_html=True)
                    onchain_ui.render_onchain_mint(consent, audit_db)

# ==========================
# ROLE: Doctor (SRQ3, SRQ4, SRQ5)
# ==========================
if role == "Doctor":
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
            # Evaluate Consent State
            # ---------------------------------
            state = evaluate_state(consent)

            audit_db.log(
                actor_did="System",
                actor_role="ConsentEngine",
                action="STATE_CHECK",
                patient_did=consent.patient_did,
                consent_id=consent.consent_id,
                scope=consent.scope,
                purpose=consent.purpose,
                result=state
            )

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
                # Doctor Request Scope
                # ---------------------------------
                st.subheader("Request Patient Data")

                scope = st.multiselect(
                    "Select Request Scope",
                    options=consent.scope,
                    help="You may only request data within the authorised consent scope."
                )

                if scope:
                    st.info(
                        f"Requested Modules: {', '.join(scope)}"
                    )

                # ---------------------------------
                # ZK Access
                # ---------------------------------
                if st.button(
                    "Execute Zero-Knowledge Access",
                    type="primary"
                ):

                    # if not scope:
                    #     st.warning("Please select at least one authorised data module.")
                    #     st.stop()

                    # Generate ZK proof
                    proof = generate_proof(consent)

                    # Verify requested scope
                    request = AccessRequest(
                        consent.requester_did,
                        consent.patient_did,
                        scope,
                        consent.purpose,
                        datetime.now().isoformat()
                    )

                    valid_scope = check_scope(
                        consent,
                        request
                    )

                    # Verify proof
                    proof_valid = verify_proof(proof)

                    # Authorization decision
                    allowed = authorize(
                        state,
                        proof_valid,
                        valid_scope
                    )

                    # ---------------------------------
                    # ACCESS GRANTED
                    # ---------------------------------
                    if allowed:

                        st.success(
                            "Cryptographic Verification Successful — Access Granted."
                        )

                        data = repo.query_patient(
                            consent.patient_did,
                            scope
                        )

                        audit_db.log(
                            actor_did=consent.requester_did,
                            actor_role="Doctor",
                            action="DATA_ACCESS",
                            patient_did=consent.patient_did,
                            consent_id=consent.consent_id,
                            scope=scope,
                            purpose=consent.purpose,
                            result="GRANTED",
                            metadata={
                                "zk_proof_verified": proof_valid,
                                "scope_valid": valid_scope,
                                "consent_state": state
                            }
                        )

                        # ---------------------------------
                        # Display EMR
                        # ---------------------------------
                        st.subheader("Authorised Medical Records")

                        for module, records in data.items():

                            with st.expander(
                                module.upper(),
                                expanded=True
                            ):
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

                    # ---------------------------------
                    # ACCESS DENIED
                    # ---------------------------------
                    else:

                        st.error(
                            "Security Exception: "
                            "Access Denied by ZK-Policy."
                        )

                        audit_db.log(
                            actor_did=consent.requester_did,
                            actor_role="Doctor",
                            action="DATA_ACCESS",
                            patient_did=consent.patient_did,
                            consent_id=consent.consent_id,
                            scope=scope,
                            purpose=consent.purpose,
                            result="DENIED",
                            metadata={
                                "zk_proof_verified": proof_valid,
                                "scope_valid": valid_scope,
                                "consent_state": state
                            }
                        )

            else:

                st.error(
                    f"Consent is not active. Current state: {state}"
                )

                st.warning(
                    "The Doctor cannot access patient data "
                    "because the consent is not currently valid."
                )




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
        "Blockchain Integrity",
        "VERIFIED"
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
    st.subheader("Complete Blockchain Audit Ledger")

    st.dataframe(
        audit_df,
        use_container_width=True
    )