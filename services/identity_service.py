'''
DID/VC + Threshold Authorization for SRQ2
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-22
'''

def verify_vc(did):
    return did.startswith(
        "did:"
    )

def verify_signature(did):
    return True
