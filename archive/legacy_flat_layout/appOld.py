'''
HALAH: A Blockchain-Based Patient Consent Management System
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date (YYYY-MM-DD): 2026-06-08, 2026-08-02
'''
from datetime import datetime,date,time
import streamlit as st
from services.consent_service import *
from services.identity_service import *
from services.state_service import *
from services.zk_service import *
from services.access_service import *
from database.consent_db import *
import pandas as pd
import database.repository as repository
import database.consent_db as consent_db
import database.audit_db as audit_db

from models.access import AccessRequest
repo=repository.SyntheaRepository("data/synthea")
st.title("Blockchain Patient Consent Management")

role=st.sidebar.selectbox(
"Role",
[
"Patient",
"Guardian",
"Doctor",
"Auditor"
]
)

# ==========================
# SRQ1
# ==========================
if role=="Patient":
    st.header("Create Consent")
    # Read Synthea DID
    patients = repo.get_patient_dids()
    patient_did = st.selectbox("Patient DID",patients["DID"].tolist())
    doctor=st.text_input(
        "Doctor DID",
        "did:hospital:001"
    )


    guardians=st.text_area(
        "Guardian DIDs",
        "did:parent:A,did:parent:B"
    )

    scope=st.multiselect(
        "Data Scope",
        [
            "Observation",
            "Medication",
            "Condition",
            "Procedure"
        ]
    )

    st.subheader("Consent Validity")

    start_text = st.text_input(
        "Start Time (YYYY-MM-DD HH:MM:SS)",
        value=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    )

    expiry_text = st.text_input(
        "Expiry Time (YYYY-MM-DD HH:MM:SS)",
        value="2026-12-31 23:59:59"
    )

    try:
        start_datetime = datetime.strptime(
            start_text,
            "%Y-%m-%d %H:%M:%S"
        )

        expiry_datetime = datetime.strptime(
            expiry_text,
            "%Y-%m-%d %H:%M:%S"
        )

        if expiry_datetime <= start_datetime:
            st.error("Expiry time must be later than start time.")
            st.stop()

    except ValueError:
        st.error(
            "Datetime format must be YYYY-MM-DD HH:MM:SS"
        )
        st.stop()




    ####################################################################

    if st.button("Create"):
        # consent=create_consent(
        #     patient_did,   #
        #     doctor,
        #     guardians.split(","),
        #     scope,
        #     "Treatment",
        #     "2026-01-01",
        #     "2026-12-31"
        # )


        consent=create_consent(
                    patient_did,   #
                    doctor,
                    guardians.split(","),
                    scope,
                    "Treatment",
                    start_datetime.isoformat(),
                    expiry_datetime.isoformat()
                )

        consent_db.save(consent)

        audit_db.log(
            actor_did=patient_did,
            actor_role="Patient",
            action="CREATE_CONSENT",
            patient_did=patient_did,
            consent_id=consent.consent_id,
            scope=scope,
            purpose="Treatment",
            result="SUCCESS"
        )
        st.success(consent.consent_id)



# ==========================
# SRQ2
# ==========================
if role=="Guardian":
    st.header("Guardian Approval")
    cid=st.text_input("Consent ID")
    consent=consent_db.get(cid)
    if consent:
        did=st.selectbox("Guardian",consent.guardian_dids)

        if st.button("Sign"):
            if verify_vc(did):
                consent.signatures.append(did)
                audit_db.log(
                    actor_did=did,
                    actor_role="Guardian",
                    action="SIGN_CONSENT",
                    patient_did=consent.patient_did,
                    consent_id=consent.consent_id,
                    scope=consent.scope,
                    purpose=consent.purpose,
                    result="SUCCESS",
                    metadata={
                        "threshold":consent.threshold,
                        "signature_count":len(consent.signatures)
                    }
                )

                if len(consent.signatures)==consent.threshold:
                    consent.token_id="SBT001"
                    audit_db.log(
                        actor_did="Blockchain",
                        actor_role="SmartContract",
                        action="MINT_SBT",
                        patient_did=consent.patient_did,
                        consent_id=consent.consent_id,
                        scope=consent.scope,
                        purpose=consent.purpose,
                        metadata={
                            "token_id":
                            consent.token_id
                        }
                    )
                st.success("Signed")

# ==========================
# SRQ3,4,5
# ==========================
if role=="Doctor":
    st.header("Request Patient Data")
    cid=st.text_input("Consent ID")
    consent=consent_db.get(cid)
    if consent:
        state=evaluate_state(consent)

        audit_db.log(
            actor_did="System",
            actor_role="ConsentEngine",
            action="STATE_CHECK",
            patient_did=consent.patient_did,
            consent_id=consent.consent_id,
            result=state
        )

        st.write("Consent State:",state)
        scope=st.multiselect(
        "Request Scope",
        consent.scope
        )
        
        st.write("Authorized Scope:",consent.scope)
        st.write("Requested Scope:",scope)

        if st.button("Access"):
            proof=generate_proof(consent)

            valid=check_scope(
                consent,
                AccessRequest(
                consent.requester_did,
                consent.patient_did,
                scope,
                consent.purpose,
                str(datetime.now())
                )
            )

            allowed=authorize(
                state,
                verify_proof(proof),
                valid
            )


            if allowed:
                # ###################
                # st.write(
                #     "DEBUG Requested scope:",
                #     scope
                # )

                # st.write(
                #     "DEBUG Consent scope:",
                #     consent.scope
                # )


                # data=repo.query_patient(
                #     consent.patient_did,
                #     scope
                # )


                # st.write(
                #     "DEBUG Returned keys:",
                #     list(data.keys())
                # )

                ######################

                data=repo.query_patient(consent.patient_did, scope)
                audit_db.log(
                    actor_did=consent.requester_did,
                    actor_role="Doctor",
                    action="DATA_ACCESS",
                    patient_did=consent.patient_did,
                    consent_id=consent.consent_id,
                    scope=scope,
                    purpose=consent.purpose,
                    result="GRANTED"
                )

                st.success("Access Granted")

                for k,v in data.items():
                    st.subheader(k)
                    st.dataframe(v)

            else:
                st.error("Access Denied")
                audit_db.log(
                    actor_did=consent.requester_did,
                    actor_role="Doctor",
                    action="DATA_ACCESS",
                    patient_did=consent.patient_did,
                    consent_id=consent.consent_id,
                    scope=scope,
                    purpose=consent.purpose,
                    result="DENIED",
                    metadata={"reason":state}
                )

# ==========================
# SRQ6
# ==========================
if role=="Auditor":
    st.header("Audit Dashboard")
    st.write(audit_db.get())

    audit=pd.DataFrame(audit_db.get())
    st.dataframe(audit,use_container_width=True)
