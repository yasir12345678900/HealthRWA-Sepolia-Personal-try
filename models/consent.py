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
    revoked:bool=False
    jurisdiction:str="AU"
    zk_secret:str=None
    zk_commitment:str=None
    signature_data:dict=field(default_factory=dict)
    # Fields added for the thesis design. Every one has a default, so a consent created by the
    # earlier code keeps its behaviour.
    commitment:str=None                 # hiding commitment c over the consent fields (hex)
    commitment_opening:dict=None        # blinding value and committed fields, held off chain only
    token_address:str=None              # per-consent address that the token is minted to
    guardian_addresses:dict=field(default_factory=dict)   # wallet-held guardian keys: DID -> address
    triggers:list=field(default_factory=list)             # conditional triggers
    transitions:list=field(default_factory=list)          # capacity transitions
    attestations:list=field(default_factory=list)         # attested events presented for the triggers
    patient_birth_date:str=None
    majority_age:int=18
    predecessor_id:str=None             # consent that this one replaces after a capacity transition
    successor_id:str=None               # consent that replaces this one
    revoked_at:str=None
    revoked_by:str=None
