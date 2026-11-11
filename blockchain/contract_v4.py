'''
Blockchain contract binding for HALAH, thesis design (ConsentSBTv4 and ConsentDecisionVerifier)
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11

Client of the two contracts of the thesis design, in the style of blockchain/contract.py:
build the transaction, sign it locally, send it, wait for the receipt and decode the events.

    ConsentContractV4          the commitment-only Soulbound token (Algorithm 5.3 and the on-chain
                               step of Algorithm 6.4). The mint takes a per-consent address and the
                               commitment and nothing else. The contract keeps the consent tree
                               (current root and the last 8) and the revocation tree root.
    DecisionVerifierContract   the wrapper around the Groth16 verifier of the decision circuit
                               (Algorithm 7.3): checks on the tag, the time and the two roots, then
                               the ConsentVerified event.

Nothing here reads a key or opens a connection at import. Configuration comes from the arguments
or, as in blockchain/contract.py, from the environment:

    RPC_URL               JSON-RPC endpoint (default: public Sepolia node)
    CONTRACT_V4_ADDRESS   deployed ConsentSBTv4 address (0x...)
    VERIFIER_ADDRESS      deployed ConsentDecisionVerifier address (0x...)
    PRIVATE_KEY           hex key of the contract OWNER wallet (test funds only!)

The tests pass an in-memory chain (`w3`), the addresses and a test key, so they need no network.
With `read_only=True` a client needs no key: it reads the chain, as an auditor or a third party does.

Deployment (a real transaction, only when run on purpose). The Poseidon contract exists as bytecode
only, so the three contracts are deployed from here and not from Remix:

    python3 -m blockchain.contract_v4 [address of the Groth16 verifier of the decision circuit]
'''
import json
import logging
import os
import secrets
import sys

from web3 import Web3
from web3.exceptions import ContractLogicError
from web3.logs import DISCARD
from eth_utils import keccak, to_checksum_address

from blockchain.contract import DEFAULT_RPC, SEPOLIA_CHAIN_ID, did_to_address, explorer_address, explorer_token, explorer_tx

try:  # the in-memory chain reports a revert with its own exception type
    from eth_tester.exceptions import TransactionFailed
except Exception:  # eth-tester is a test dependency only
    class TransactionFailed(Exception):
        pass

ABI_DIR = os.path.join(os.path.dirname(__file__), "abi")

# Order of the BN254 scalar field. A commitment, a tag and a root are elements of this field.
FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617
TREE_DEPTH = 16          # depth of the consent tree and of the revocation tree
RECENT_ROOTS = 8         # earlier consent roots that stay acceptable beside the current one
TOLERANCE = 300          # largest accepted age of the proof time t, in seconds

# Public inputs of the decision proof, in the order the circuit and the contract use.
PUBLIC_SIGNALS = ("t", "role", "purpose", "context", "tag", "consentRoot", "revocationRoot")

# Reason of the contract for each rejection of Algorithm 7.3 -> code that the caller records.
REJECTIONS = {
    "public input outside the field": "INPUT_OUTSIDE_FIELD",
    "tag already seen": "TAG_ALREADY_SEEN",
    "time is in the future": "TIME_IN_FUTURE",
    "time is too old": "TIME_TOO_OLD",
    "revocation root is not current": "REVOCATION_ROOT_NOT_CURRENT",
    "consent root is not recent": "CONSENT_ROOT_NOT_RECENT",
    "proof is not valid": "PROOF_NOT_VALID",
}

# The one function of the Groth16 verifier that snarkjs exports for the decision circuit.
PROOF_VERIFIER_ABI = [{"type": "function", "name": "verifyProof", "stateMutability": "view",
                       "inputs": [{"name": "a", "type": "uint256[2]"}, {"name": "b", "type": "uint256[2][2]"},
                                  {"name": "c", "type": "uint256[2]"}, {"name": "publicSignals", "type": "uint256[7]"}],
                       "outputs": [{"name": "", "type": "bool"}]}]

log = logging.getLogger("halah.chain.v4")


def load_artifact(name="ConsentSBTv4"):
    '''ABI and bytecode of a contract, as tools/compile_v4.js stored them.'''
    with open(os.path.join(ABI_DIR, name if name.endswith(".json") else name + ".json")) as f:
        return json.load(f)


def to_field(value):
    '''A commitment, tag or root as an integer of the field. Accepts an int, a decimal or 0x string, or bytes.'''
    if isinstance(value, bool) or value is None:
        raise ValueError("not a field element: %r" % (value,))
    if isinstance(value, (bytes, bytearray)):
        number = int.from_bytes(value, "big")
    elif isinstance(value, str):
        text = value.strip()
        number = int(text, 16) if text.lower().startswith("0x") else int(text)
    else:
        number = int(value)
    if not 0 <= number < FIELD:
        raise ValueError("value is outside the field")
    return number


def derive_consent_address(patient, consent_id, salt=None):
    '''Per-consent address that the token is minted to (Algorithm 5.3).

    The address is keccak256 over the patient's wallet address, the consent identifier and a random
    32-byte salt, so a patient's consents sit at unrelated addresses and the chain does not link them.
    `patient` is a wallet address, or a DID that blockchain.contract.did_to_address maps to one.
    The salt is the off-chain link between the address and the patient: keep it with the opening of
    the commitment, and delete it at revocation. Give the same salt to derive the same address again.
    Nobody holds a key for the address, which a Soulbound token that never moves does not need.
    Returns (checksummed address, salt as 0x hex).
    '''
    wallet = bytes.fromhex(did_to_address(patient)[2:])
    if salt is None:
        salt = secrets.token_bytes(32)
    elif isinstance(salt, str):
        salt = bytes.fromhex(salt[2:] if salt.lower().startswith("0x") else salt)
    elif isinstance(salt, int):
        if not 0 <= salt < 2 ** 256:
            raise ValueError("the salt must be 32 bytes")
        salt = salt.to_bytes(32, "big")
    if len(salt) != 32:
        raise ValueError("the salt must be 32 bytes")
    digest = keccak(b"HALAH consent address v1" + wallet + keccak(text=str(consent_id)) + bytes(salt))
    return to_checksum_address("0x" + digest[-20:].hex()), "0x" + bytes(salt).hex()


def proof_to_calldata(proof):
    '''A Groth16 proof as the three arguments (a, b, c) of the Solidity verifier.

    Accepts the proof object of snarkjs ({"pi_a", "pi_b", "pi_c"}), a result that carries it under
    "proof", or (a, b, c) already in the Solidity layout. snarkjs writes each G2 coordinate as
    (c0, c1) and the verifier contract reads (c1, c0), so the two numbers of each pair of pi_b swap.
    '''
    if isinstance(proof, dict) and "pi_a" not in proof and "proof" in proof:
        proof = proof["proof"]
    if isinstance(proof, dict):
        a = [int(proof["pi_a"][0]), int(proof["pi_a"][1])]
        b = [[int(proof["pi_b"][0][1]), int(proof["pi_b"][0][0])], [int(proof["pi_b"][1][1]), int(proof["pi_b"][1][0])]]
        c = [int(proof["pi_c"][0]), int(proof["pi_c"][1])]
        return a, b, c
    a, b, c = proof
    return [int(x) for x in a], [[int(x) for x in pair] for pair in b], [int(x) for x in c]


def revert_reason(error):
    '''The reason string of a reverted call ("execution reverted: <reason>" on both chains).'''
    text = str(getattr(error, "message", None) or error)
    marker = "execution reverted:"
    return text.split(marker, 1)[1].strip() if marker in text else text.strip()


def _sign_and_send(w3, account, fn, gas=None):
    '''Build, sign locally, send and wait for the receipt. With `gas` the estimate is skipped.'''
    tx = {"from": account.address, "nonce": w3.eth.get_transaction_count(account.address), "chainId": w3.eth.chain_id}
    if gas:
        tx["gas"] = int(gas)
    signed = account.sign_transaction(fn.build_transaction(tx))
    raw = getattr(signed, "raw_transaction", None) or getattr(signed, "rawTransaction")
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=240)
    return Web3.to_hex(tx_hash), receipt


def deploy_contract(w3, private_key, name, *args, gas=None):
    '''Deploy one artefact from the given key and return (address, receipt).'''
    art = load_artifact(name)
    account = w3.eth.account.from_key(private_key)
    factory = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    tx_hash, receipt = _sign_and_send(w3, account, factory.constructor(*args), gas=gas)
    if int(receipt["status"]) != 1:
        raise RuntimeError("deployment of %s reverted (tx %s)" % (name, tx_hash))
    return receipt["contractAddress"], receipt


def deploy_v4(w3, private_key, proof_verifier=None, gas=None):
    '''Deploy the Poseidon contract and ConsentSBTv4, and ConsentDecisionVerifier when the address
    of the Groth16 verifier of the decision circuit (`proof_verifier`) is given.
    The key becomes the owner of the token contract. Returns the addresses and the gas of each deployment.'''
    out = {"poseidon": None, "token": None, "verifier": None, "proof_verifier": proof_verifier, "gas_used": {}}
    out["poseidon"], rc = deploy_contract(w3, private_key, "PoseidonT3", gas=gas)
    out["gas_used"]["PoseidonT3"] = int(rc["gasUsed"])
    out["token"], rc = deploy_contract(w3, private_key, "ConsentSBTv4", out["poseidon"], gas=gas)
    out["gas_used"]["ConsentSBTv4"] = int(rc["gasUsed"])
    if proof_verifier:
        out["verifier"], rc = deploy_contract(w3, private_key, "ConsentDecisionVerifier", to_checksum_address(proof_verifier), out["token"], gas=gas)
        out["gas_used"]["ConsentDecisionVerifier"] = int(rc["gasUsed"])
    return out


class _Client:
    '''What the two clients share: the connection, the signer, the contract and the transaction path.'''
    ARTIFACT = None
    ADDRESS_ENV = None

    def __init__(self, w3=None, address=None, private_key=None, abi=None, gas_limit=None, read_only=False):
        self.rpc = os.environ.get("RPC_URL", DEFAULT_RPC)
        address = address or os.environ.get(self.ADDRESS_ENV, "")
        private_key = None if read_only else (private_key or os.environ.get("PRIVATE_KEY", ""))
        if not address:
            raise RuntimeError("%s is not set - deploy %s and give its address" % (self.ADDRESS_ENV, self.ARTIFACT))
        if not private_key and not read_only:
            raise RuntimeError("PRIVATE_KEY is not set - give the TEST wallet key of the sender (never commit it)")
        self.w3 = w3 or Web3(Web3.HTTPProvider(self.rpc, request_kwargs={"timeout": 30}))
        self.account = self.w3.eth.account.from_key(private_key) if private_key else None   # None: a reader without a key
        self.address = to_checksum_address(address)
        self.abi = abi or load_artifact(self.ARTIFACT)["abi"]
        self.contract = self.w3.eth.contract(address=self.address, abi=self.abi)
        # With a gas limit the estimate is skipped, so a transaction that reverts is still mined (status 0).
        self.gas_limit = gas_limit

    @property
    def signer(self):
        return self.account.address if self.account else None

    def _send(self, fn):
        if self.account is None:
            raise RuntimeError("this client is read-only: it holds no key to sign a transaction")
        return _sign_and_send(self.w3, self.account, fn, gas=self.gas_limit)

    def _logs(self, event, from_block=0):
        try:
            return event().get_logs(from_block=from_block)
        except TypeError:  # older web3 spelling
            return event().get_logs(fromBlock=from_block)


class ConsentContractV4(_Client):
    ARTIFACT = "ConsentSBTv4"
    ADDRESS_ENV = "CONTRACT_V4_ADDRESS"

    # ---- diagnostics ---------------------------------------------------
    def status(self):
        chain_id = self.w3.eth.chain_id
        owner = None
        try:
            owner = self.contract.functions.owner().call()
        except Exception as e:
            log.warning("owner() call failed: %s", e)
        return {
            "chain_id": chain_id,
            "is_sepolia": chain_id == SEPOLIA_CHAIN_ID,
            "block": self.w3.eth.block_number,
            "signer": self.signer,
            "contract": self.address,
            "contract_has_code": len(self.w3.eth.get_code(self.address)) > 0,
            "owner": owner,
            "signer_is_owner": (owner == self.signer) if owner and self.signer else None,
            "consent_count": self.consent_count(),
            "version": 4,
            "explorer_contract": explorer_address(self.address),
        }

    # ---- issuance (Algorithm 5.3) ----------------------------------------
    def mint_consent(self, to_address, commitment):
        '''Mint the token of a consent to its per-consent address, carrying only the commitment.

        Call it once the threshold of approvals is met off chain. The signer must be the owner.
        Returns the receipt fields, the token identifier, the leaf index of the commitment in the
        consent tree (token identifier - 1) and the new consent root.'''
        commitment = to_field(commitment)
        to_address = to_checksum_address(to_address)
        tx_hash, receipt = self._send(self.contract.functions.mintConsent(to_address, commitment))
        token_id = None
        try:
            evs = self.contract.events.ConsentIssued().process_receipt(receipt, errors=DISCARD)
            if evs:
                token_id = int(evs[0]["args"]["tokenId"])
        except Exception as e:
            log.warning("could not decode ConsentIssued for %s: %s", tx_hash, e)
        block = int(receipt["blockNumber"])
        return {"tx_hash": tx_hash, "status": int(receipt["status"]), "block_number": block,
                "gas_used": int(receipt["gasUsed"]), "token_id": token_id,
                "leaf_index": token_id - 1 if token_id is not None else None,
                "commitment": commitment, "token_address": to_address,
                "consent_root": self._root_after(self.consent_root, block) if token_id is not None else None,
                "contract": self.address, "signer": self.signer, "chain_id": self.w3.eth.chain_id,
                "explorer_tx": explorer_tx(tx_hash),
                "explorer_token": explorer_token(self.address, token_id) if token_id is not None else None,
                "version": 4}

    # ---- revocation (Algorithm 6.4, on-chain step) -------------------------
    def revoke(self, token_id):
        '''Revoke a consent on chain: its flag is set for good and its leaf of the revocation tree becomes 1.'''
        tx_hash, receipt = self._send(self.contract.functions.revoke(int(token_id)))
        ok = int(receipt["status"]) == 1
        block = int(receipt["blockNumber"])
        return {"tx_hash": tx_hash, "status": int(receipt["status"]), "block_number": block,
                "gas_used": int(receipt["gasUsed"]), "token_id": int(token_id),
                "revocation_root": self._root_after(self.revocation_root, block) if ok else None,
                "explorer_tx": explorer_tx(tx_hash)}

    def _root_after(self, read, block):
        # The transaction is already mined. A node that cannot serve the read must not turn it into an error.
        try:
            return read(block)
        except Exception as e:
            log.warning("could not read the root at block %s: %s", block, e)
            return None

    # ---- reads -----------------------------------------------------------
    def check_valid(self, token_id):
        '''The revocation state: True for an issued consent that is not revoked.'''
        return bool(self.contract.functions.checkValid(int(token_id)).call())

    def consent_of(self, token_id):
        '''Everything the token stores: the commitment and the revocation state.'''
        commitment, revoked = self.contract.functions.consents(int(token_id)).call()
        return {"commitment": int(commitment), "revoked": bool(revoked)}

    def token_of_commitment(self, commitment):
        '''Token identifier of a commitment, or None when it was not issued.'''
        return int(self.contract.functions.tokenOfCommitment(to_field(commitment)).call()) or None

    def consent_count(self):
        return int(self.contract.functions.consentCount().call())

    def consent_root(self, block="latest"):
        return int(self.contract.functions.consentRoot().call(block_identifier=block))

    def revocation_root(self, block="latest"):
        return int(self.contract.functions.revocationRoot().call(block_identifier=block))

    def recent_roots(self, block="latest"):
        '''The current consent root first, then the earlier roots that are still acceptable.'''
        return [int(r) for r in self.contract.functions.recentRoots().call(block_identifier=block) if r]

    def is_known_consent_root(self, root):
        return bool(self.contract.functions.isKnownConsentRoot(to_field(root)).call())

    def read_roots(self):
        '''The two roots that Algorithm 7.1 reads from the chain, all taken at one block, with its time.'''
        block = self.w3.eth.get_block("latest")
        number = int(block["number"])
        return {"consent_root": self.consent_root(number), "revocation_root": self.revocation_root(number),
                "recent_roots": self.recent_roots(number), "block_number": number,
                "block_timestamp": int(block["timestamp"]), "contract": self.address, "chain_id": self.w3.eth.chain_id}

    def latest_block_time(self):
        '''Timestamp of the latest block: a time that the server does not control.'''
        return int(self.w3.eth.get_block("latest")["timestamp"])

    def issued_commitments(self, from_block=0):
        '''The commitments in leaf order, read from the ConsentIssued events, to rebuild the consent tree off chain.'''
        logs = sorted(self._logs(self.contract.events.ConsentIssued, from_block), key=lambda e: int(e["args"]["tokenId"]))
        return [int(e["args"]["commitment"]) for e in logs]

    def revoked_token_ids(self, from_block=0):
        '''The revoked tokens in the order of their revocation, read from the ConsentRevoked events.'''
        return [int(e["args"]["tokenId"]) for e in self._logs(self.contract.events.ConsentRevoked, from_block)]


class DecisionVerifierContract(_Client):
    ARTIFACT = "ConsentDecisionVerifier"
    ADDRESS_ENV = "VERIFIER_ADDRESS"

    def status(self):
        return {"chain_id": self.w3.eth.chain_id, "block": self.w3.eth.block_number, "signer": self.signer,
                "contract": self.address, "contract_has_code": len(self.w3.eth.get_code(self.address)) > 0,
                "proof_verifier": self.contract.functions.proofVerifier().call(),
                "consent_token": self.contract.functions.consentToken().call(),
                "tolerance": int(self.contract.functions.TOLERANCE().call()),
                "explorer_contract": explorer_address(self.address)}

    def tag_seen(self, tag):
        return bool(self.contract.functions.tagSeen(to_field(tag)).call())

    def verified_at_block(self, tag):
        '''Number of the block in which the proof with this tag was accepted, or None.'''
        return int(self.contract.functions.verifiedAtBlock(to_field(tag)).call()) or None

    def verify_decision(self, proof, public_signals=None, record_rejection=False):
        '''Algorithm 7.3: submit the proof and its public inputs to the verifier contract.

        `public_signals` are [t, role, purpose, context, tag, consentRoot, revocationRoot], or are taken
        from `proof["publicSignals"]`. Take t from latest_block_time() of the token client and the roots
        from read_roots(): a t read from the system clock can be ahead of the block and is then refused.
        The submission is first run as a call against the latest block, so a rejection costs no gas
        and returns its reason. With `record_rejection` the refused transaction is sent all the same (with
        a fixed gas limit) and stays on chain as a failed transaction, as evidence of the refusal.
        Returns `accepted`, the reason code on rejection (see REJECTIONS), the receipt fields, the
        ConsentVerified event and `reference` (the transaction hash) for the audit record.'''
        if self.account is None:
            raise RuntimeError("this client is read-only: use reverify() to check a proof without a transaction")
        a, b, c, signals = self._arguments(proof, public_signals)
        fn = self.contract.functions.verifyDecision(a, b, c, signals)
        out = {"accepted": False, "reason": None, "reason_text": None, "tx_hash": None, "status": None,
               "block_number": None, "gas_used": None, "reference": None, "event": None,
               "public_inputs": dict(zip(PUBLIC_SIGNALS, signals)), "contract": self.address}
        try:
            fn.call({"from": self.account.address})
        except (ContractLogicError, TransactionFailed) as e:
            out["reason_text"] = revert_reason(e)
            out["reason"] = REJECTIONS.get(out["reason_text"], "REJECTED")
            if not record_rejection:
                return out
        gas = self.gas_limit or (600000 if out["reason"] else None)
        tx_hash, receipt = _sign_and_send(self.w3, self.account, fn, gas=gas)
        out.update({"tx_hash": tx_hash, "status": int(receipt["status"]), "block_number": int(receipt["blockNumber"]),
                    "gas_used": int(receipt["gasUsed"]), "explorer_tx": explorer_tx(tx_hash)})
        evs = self.contract.events.ConsentVerified().process_receipt(receipt, errors=DISCARD)
        if out["status"] == 1 and evs:
            out["accepted"] = bool(evs[0]["args"]["result"])
            out["event"] = {k: (int(v) if not isinstance(v, bool) else v) for k, v in dict(evs[0]["args"]).items()}
            out["reference"] = tx_hash
        elif out["reason"] is None:  # the state changed between the call and the transaction
            out["reason"], out["reason_text"] = "REJECTED", "transaction reverted"
        return out

    def _arguments(self, proof, public_signals=None):
        if public_signals is None:
            public_signals = proof["publicSignals"]
        signals = [int(s, 16) if isinstance(s, str) and s.lower().startswith("0x") else int(s) for s in public_signals]
        if len(signals) != len(PUBLIC_SIGNALS):
            raise ValueError("the decision proof has %d public signals" % len(PUBLIC_SIGNALS))
        return (*proof_to_calldata(proof), signals)

    # ---- what a third party can do with the chain alone (no key, no off-chain record) ----
    def submitted_proof(self, tx_hash):
        '''The proof and the public signals of a verification, decoded from the input of its transaction.'''
        _, args = self.contract.decode_function_input(self.w3.eth.get_transaction(tx_hash)["input"])
        return {"proof": ([int(x) for x in args["a"]], [[int(x) for x in pair] for pair in args["b"]], [int(x) for x in args["c"]]),
                "publicSignals": [int(x) for x in args["publicSignals"]]}

    def reverify(self, proof, public_signals=None):
        '''Check a proof against the Groth16 verifier itself, as a call. It answers whether the proof holds for
        these public signals. The tag, the time and the roots were checked once, when the proof was accepted.'''
        a, b, c, signals = self._arguments(proof, public_signals)
        groth16 = self.w3.eth.contract(address=self.contract.functions.proofVerifier().call(), abi=PROOF_VERIFIER_ABI)
        return bool(groth16.functions.verifyProof(a, b, c, signals).call())

    def verifications(self, from_block=0):
        '''The ConsentVerified events, for an auditor who holds only the chain.'''
        return [{"tx_hash": Web3.to_hex(e["transactionHash"]), "block_number": int(e["blockNumber"]),
                 **{k: (int(v) if not isinstance(v, bool) else v) for k, v in dict(e["args"]).items()}}
                for e in self._logs(self.contract.events.ConsentVerified, from_block)]


def main(argv=None, w3=None, private_key=None, gas=None):
    '''Deploy the Poseidon contract and ConsentSBTv4, and the decision verifier when the address of the
    Groth16 verifier is given. The key (PRIVATE_KEY) becomes the owner. Prints the lines for .env.'''
    argv = sys.argv[1:] if argv is None else argv
    w3 = w3 or Web3(Web3.HTTPProvider(os.environ.get("RPC_URL", DEFAULT_RPC), request_kwargs={"timeout": 30}))
    private_key = private_key or os.environ.get("PRIVATE_KEY", "")
    if not private_key:
        raise RuntimeError("PRIVATE_KEY is not set - give the TEST wallet key of the deployer (never commit it)")
    out = deploy_v4(w3, private_key, proof_verifier=argv[0] if argv else None, gas=gas)
    print("chain=%s gas=%s" % (w3.eth.chain_id, out["gas_used"]))
    print("POSEIDON_ADDRESS=" + out["poseidon"])
    print("CONTRACT_V4_ADDRESS=" + out["token"])
    if out["verifier"]:
        print("VERIFIER_ADDRESS=" + out["verifier"])
    return out


if __name__ == "__main__":
    main()
