'''
Consent Creation for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-10, 2026-08-02, 2026-11-11
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
from datetime import date, datetime
from models.consent import Consent


def create_consent(
    patient,
    doctor,
    guardians,
    scope,
    purpose,
    start,
    expiry,
    threshold=None,
    context=None,
    patient_birth_date=None

):
    """Algorithm 4.1, construction of the consent object in the PENDING state, with the authorisation
    requirement A = (G, N) of the thesis design.
    threshold: the patient-defined threshold N of a k-of-n consent, 1 <= N <= |G|. None keeps the N-of-N rule
    of the report, N = |G|.
    context: the policy context of the consent (the two-letter jurisdiction code). None keeps the default of
    the consent model.
    patient_birth_date: date of birth (ISO string or date), from which the capacity transition at the age of
    majority is scheduled. It is stored as YYYY-MM-DD.
    Raises ValueError for an empty guardian set, a guardian named twice, or a threshold outside the range."""
    if not isinstance(guardians, (list, tuple)) or len(guardians) == 0:
        raise ValueError("the guardian set G must name at least one guardian")
    if len(set(guardians)) != len(guardians):
        raise ValueError("each guardian may appear only once in the guardian set G")
    n = len(guardians)
    if threshold is None:
        threshold = n
    elif isinstance(threshold, bool) or not isinstance(threshold, int) or not 1 <= threshold <= n:
        raise ValueError(f"the threshold N must be a whole number with 1 <= N <= {n}, the size of G")

    consent = Consent(
        consent_id=str(uuid.uuid4()),
        patient_did=patient,
        requester_did=doctor,
        guardian_dids=list(guardians),
        purpose=purpose,
        scope=scope,
        threshold=threshold,
        start_date=start,
        expiry_date=expiry,
        state="PENDING_SIGNATURE"

    )
    if context is not None:
        if not (isinstance(context, str) and len(context) == 2 and context.isascii() and context.isalpha()
                and context.isupper()):
            raise ValueError("the context must be a two-letter code in capitals, for example AU")
        consent.jurisdiction = context
    if patient_birth_date is not None:
        # stored as the ISO date YYYY-MM-DD, the form from which the capacity transition is scheduled
        try:
            if isinstance(patient_birth_date, datetime):
                born = patient_birth_date.date()
            elif isinstance(patient_birth_date, date):
                born = patient_birth_date
            elif isinstance(patient_birth_date, str):
                born = datetime.fromisoformat(patient_birth_date).date()
            else:
                raise ValueError
        except ValueError:
            raise ValueError("the date of birth must be an ISO date, for example 2008-11-20") from None
        consent.patient_birth_date = born.isoformat()
    return consent
