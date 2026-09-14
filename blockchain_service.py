
'''
blockchain for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-10
'''


def mint_sbt(consent):
    token_id="SBT-"+consent.consent_id[:8]
    return token_id



from blockchain.contract import ConsentContract
def mint_consent(consent):
    contract=ConsentContract()
    token=contract.mint(
        consent.patient_did,
        consent.requester_did,
        consent.purpose
    )
    return token

# For Upgrading Deployment
# web3.py
# contract.functions.mint()

# from blockchain.contract import ConsentContract
# contract=ConsentContract()
# token_id=contract.mint(
#     patient_wallet,
#     doctor_wallet,
#     "Treatment",
#     expiry_timestamp
# )
