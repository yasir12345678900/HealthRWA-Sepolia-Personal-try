'''
Performance Evaluation for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-10, 2026-08-02
'''

# import uuid
# from models.consent import Consent

# def create_consent(
#     patient,
#     doctor,
#     guardians,
#     scope,
#     purpose,
#     start,
#     expiry
# ):
#     return Consent(
#         consent_id=str(uuid.uuid4()),
#         patient_did=patient,
#         requester_did=doctor,
#         guardian_dids=guardians,
#         purpose=purpose,
#         scope=scope,
#         threshold=len(guardians),
#         start_date=start,
#         expiry_date=expiry
#     )


import uuid
from models.consent import Consent


def create_consent(
    patient,
    doctor,
    guardians,
    scope,
    purpose,
    start,
    expiry

):

    return Consent(
        consent_id=str(uuid.uuid4()),
        patient_did=patient,
        requester_did=doctor,
        guardian_dids=guardians,
        purpose=purpose,
        scope=scope,
        threshold=len(guardians),
        start_date=start,
        expiry_date=expiry,
        state="PENDING_SIGNATURE"

    )