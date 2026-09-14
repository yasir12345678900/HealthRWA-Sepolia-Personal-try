from web3 import Web3
import json

class ConsentContract:
    def __init__(self):
        self.w3=Web3(
        Web3.HTTPProvider(
        "https://rpc-amoy.polygon.technology"
        )
        )

        abi=json.load(
        open("blockchain/abi/ConsentSBT.json")
        )["abi"]

        self.contract=self.w3.eth.contract(address="CONTRACT_ADDRESS",abi=abi)

    def mint(self,patient,doctor,purpose,expiry):
        tx=self.contract.functions.mintConsent(
            patient,
            doctor,
            purpose,
            expiry
        )
        return tx

    def verify(self,token_id):
        return self.contract.functions.checkValid(token_id).call()

    def revoke(self,token_id):
        return self.contract.functions.revoke(token_id)
