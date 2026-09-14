'''
Access Models for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-3
'''


from dataclasses import dataclass
@dataclass
class AccessRequest:
    doctor_did:str
    patient_did:str
    scope:list
    purpose:str
    request_time:str


