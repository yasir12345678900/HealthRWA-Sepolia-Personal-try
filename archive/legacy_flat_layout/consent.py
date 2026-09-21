'''
Consent Models for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-03
'''

from dataclasses import dataclass,field

@dataclass
class Consent:
    consent_id:str
    patient_did:str
    requester_did:str
    guardian_dids:list
    purpose:str
    scope:list
    threshold:int
    signatures:list=field(default_factory=list)
    start_date:str=None
    expiry_date:str=None
    state:str="CREATED"
    token_id:str=None
