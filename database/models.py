# from dataclasses import dataclass

# @dataclass
# class Consent:
#     consent_id:str
#     patient_id:str
#     requester:str
#     purpose:str
#     scope:list
#     threshold:int
#     signatures:list
#     start_date:str
#     expiry_date:str
#     state:str="PENDING"
#     token_id:str=None


from dataclasses import dataclass, field
from typing import List, Optional
from datetime import datetime


@dataclass
class Consent:
    consent_id: str
    patient_did: str
    requester_did: str
    guardian_dids: List[str]
    purpose: str
    scope: List[str]
    threshold: int
    start_date: str
    expiry_date: str
    signatures: List[str] = field(default_factory=list)
    state: str = "DRAFT"
    token_id: Optional[str] = None
    revoked: bool = False
    created_time: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    updated_time: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None