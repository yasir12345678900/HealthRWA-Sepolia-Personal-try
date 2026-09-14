# database/did_mapping.py
def create_patient_did(patient_id):
    return (
        "did:patient:"
        +
        patient_id
    )


def resolve_patient_id(did):
    if did.startswith(
        "did:patient:"
    ):
        return did.replace(
            "did:patient:",
            ""
        )

    return None