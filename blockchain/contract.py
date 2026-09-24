'''
Blockchain contract binding for HALAH — on-chain mode (Ethereum Sepolia)
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
v3 (2026-09-20): real transaction path — build, sign locally, send, wait for
the receipt, decode the ERC-721 Transfer event to recover the minted tokenId
and produce Etherscan links. Configuration comes ONLY from the environment
(or a local .env file, which is git-ignored):

    RPC_URL           Sepolia JSON-RPC endpoint (default: public node)
    CONTRACT_ADDRESS  deployed ConsentSBTv2 address (0x...)
    PRIVATE_KEY       hex key of the contract OWNER wallet (test funds only!)

Never commit real keys. mintConsent() is onlyOwner, so the signer must be the
account that deployed the contract.
'''
import logging
import os
import json
from dotenv import load_dotenv
from web3 import Web3
from web3.logs import DISCARD
from eth_utils import keccak, to_checksum_address

load_dotenv()

SEPOLIA_CHAIN_ID = 11155111
DEFAULT_RPC = "https://ethereum-sepolia-rpc.publicnode.com"
EXPLORER = "https://sepolia.etherscan.io"
ABI_DIR = os.path.join(os.path.dirname(__file__), "abi")


CONTRACT_VERSION = int(os.environ.get("CONTRACT_VERSION", "2"))


def load_artifact(name=None):
    name = name or f"ConsentSBTv{CONTRACT_VERSION}.json"
    with open(os.path.join(ABI_DIR, name)) as f:
        return json.load(f)


def did_to_address(did):
    '''Map a DID string to a deterministic, checksummed Ethereum address.

    - If `did` already is an address it is returned checksummed.
    - Otherwise keccak256(did) is taken and its last 20 bytes form the
      address. This anchors the DID pseudonymously on-chain; nobody holds a
      key for that address, which is acceptable for a soulbound token that
      must never move anyway (see ConsentSBTv2._beforeTokenTransfer).
    '''
    if did and Web3.is_address(did):
        return to_checksum_address(did)
    digest = keccak(text=str(did))
    return to_checksum_address("0x" + digest[-20:].hex())


def is_configured():
    return bool(os.environ.get("CONTRACT_ADDRESS")) and bool(os.environ.get("PRIVATE_KEY"))


def explorer_tx(tx_hash):
    return f"{EXPLORER}/tx/{tx_hash}"


def explorer_address(addr):
    return f"{EXPLORER}/address/{addr}"


def explorer_token(contract, token_id):
    return f"{EXPLORER}/nft/{contract}/{token_id}"


log = logging.getLogger("halah.chain")


class ConsentContract:
    def __init__(self, w3=None, address=None, private_key=None, abi=None):
        self.rpc = os.environ.get("RPC_URL", DEFAULT_RPC)
        address = address or os.environ.get("CONTRACT_ADDRESS", "")
        private_key = private_key or os.environ.get("PRIVATE_KEY", "")
        if not address:
            raise RuntimeError("CONTRACT_ADDRESS is not set - deploy ConsentSBTv2 on Sepolia and put its address in .env")
        if not private_key:
            raise RuntimeError("PRIVATE_KEY is not set - put the contract owner's TEST wallet key in .env (never commit it)")
        self.w3 = w3 or Web3(Web3.HTTPProvider(self.rpc, request_kwargs={"timeout": 30}))
        self.account = self.w3.eth.account.from_key(private_key)
        self.address = to_checksum_address(address)
        self.abi = abi or load_artifact()["abi"]
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)

    # ---- diagnostics ---------------------------------------------------
    def status(self):
        chain_id = self.w3.eth.chain_id
        code = self.w3.eth.get_code(self.address)
        bal = self.w3.eth.get_balance(self.account.address)
        owner = None
        try:
            owner = self.contract.functions.owner().call()
        except Exception as e:
            log.warning("owner() call failed: %s", e)
        return {
            "rpc": self.rpc,
            "chain_id": chain_id,
            "is_sepolia": chain_id == SEPOLIA_CHAIN_ID,
            "block": self.w3.eth.block_number,
            "signer": self.account.address,
            "balance_eth": float(self.w3.from_wei(bal, "ether")),
            "contract": self.address,
            "contract_has_code": len(code) > 0,
            "owner": owner,
            "signer_is_owner": (owner == self.account.address) if owner else None,
            "explorer_contract": explorer_address(self.address),
        }

    # ---- transaction plumbing -----------------------------------------
    def _send(self, fn):
        tx = fn.build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "chainId": self.w3.eth.chain_id,
        })
        signed = self.account.sign_transaction(tx)
        raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
        tx_hash = self.w3.eth.send_raw_transaction(raw)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
        return Web3.to_hex(tx_hash), receipt

    def mint_consent(self, patient_did, requester_did, purpose, expiry_ts):
        fn = self.contract.functions.mintConsent(
            did_to_address(patient_did),
            did_to_address(requester_did),
            str(purpose)[:200],
            int(expiry_ts),
        )
        tx_hash, receipt = self._send(fn)
        token_id = None
        try:
            evs = self.contract.events.Transfer().process_receipt(receipt, errors=DISCARD)
            if evs:
                token_id = int(evs[0]["args"]["tokenId"])
        except Exception as e:
            log.warning("could not decode Transfer event for tx %s: %s", tx_hash, e)
        out = {
            "tx_hash": tx_hash,
            "status": int(receipt["status"]),
            "block_number": int(receipt["blockNumber"]),
            "gas_used": int(receipt["gasUsed"]),
            "token_id": token_id,
            "contract": self.address,
            "signer": self.account.address,
            "chain_id": self.w3.eth.chain_id,
            "explorer_tx": explorer_tx(tx_hash),
            "explorer_contract": explorer_address(self.address),
        }
        if token_id is not None:
            out["explorer_token"] = explorer_token(self.address, token_id)
        return out

    def check_valid(self, token_id):
        return bool(self.contract.functions.checkValid(int(token_id)).call())

    def revoke(self, token_id):
        tx_hash, receipt = self._send(self.contract.functions.revoke(int(token_id)))
        return {"tx_hash": tx_hash, "status": int(receipt["status"]), "block_number": int(receipt["blockNumber"]),
                "gas_used": int(receipt["gasUsed"]), "explorer_tx": explorer_tx(tx_hash)}

    # ---- v3 (C = (I,A,P,T,L,E)) ------------------------------------------
    def has_v3(self):
        return any(x.get("name") == "mintConsentV3" for x in self.abi if x.get("type") == "function")

    def mint_consent_v3(self, patient_did, requester_did, purpose, not_before_ts, expiry_ts, jurisdiction="AU", burn_auth=2):
        """VT: notBefore/expiry, VL: 2-letter jurisdiction, ERC-5484 burnAuth (0 Issuer,1 Owner,2 Both,3 Neither)."""
        jur = (jurisdiction or "")[:2].encode("ascii").ljust(2, b"\0") if jurisdiction else b"\0\0"
        fn = self.contract.functions.mintConsentV3(did_to_address(patient_did), did_to_address(requester_did), str(purpose),
                                                   int(not_before_ts), int(expiry_ts), jur, int(burn_auth))
        tx_hash, receipt = self._send(fn)
        token_id = None
        try:
            evs = self.contract.events.ConsentMinted().process_receipt(receipt, errors=DISCARD)
            if evs: token_id = int(evs[0]["args"]["tokenId"])
        except Exception as e:
            log.warning("could not decode ConsentMinted for %s: %s", tx_hash, e)
        return {"tx_hash": tx_hash, "status": int(receipt["status"]), "block_number": int(receipt["blockNumber"]),
                "gas_used": int(receipt["gasUsed"]), "token_id": token_id, "explorer_tx": explorer_tx(tx_hash),
                "explorer_token": explorer_token(self.address, token_id) if token_id is not None else None,
                "contract": self.address, "version": 3}

    def check_valid_at(self, token_id, jurisdiction="AU"):
        jur = jurisdiction.encode("ascii")[:2].ljust(2, b"\0")
        return bool(self.contract.functions.checkValidAt(int(token_id), jur).call())

    def burn(self, token_id):
        tx_hash, receipt = self._send(self.contract.functions.burn(int(token_id)))
        return {"tx_hash": tx_hash, "status": int(receipt["status"]), "block_number": int(receipt["blockNumber"]),
                "explorer_tx": explorer_tx(tx_hash)}
