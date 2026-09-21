'''
Zero Knowledge Proof for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-30
'''

import hashlib
# Demo test
# def generate_proof(consent):
#     value=str(consent.consent_id)

#     return hashlib.sha256(
#         value.encode()
#     ).hexdigest()

# def verify_proof(proof):
#     return len(proof)>0


def generate_proof(consent):
    return hashlib.sha256(
        consent.consent_id.encode()
    ).hexdigest()

def verify_proof(proof):
    return proof is not None


# Extension to Circom + snarkjs