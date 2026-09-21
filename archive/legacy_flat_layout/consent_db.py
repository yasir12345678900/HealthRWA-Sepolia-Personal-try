CONSENTS={}

def save(consent):
    CONSENTS[consent.consent_id]=consent

def get(consent_id):
    return CONSENTS.get(consent_id)


def update(consent):
    CONSENTS[consent.consent_id]=consent

def revoke(consent_id):
    consent=get(consent_id)

    if consent:
        consent.revoked=True
        update(consent)


def get_patient_consent(patient):
    return [
        c
        for c in CONSENTS.values()
        if c.patient_did==patient
    ]


# CONSENTS={}
# def save(consent):
#     CONSENTS[
#         consent.consent_id
#     ]=consent

# def get(consent_id):
#     return CONSENTS.get(
#         consent_id
#     )

# def get_patient_consent(patient):
#     return [
#         c for c in CONSENTS.values()
#         if c.patient_did==patient
#     ]
