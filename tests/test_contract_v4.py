"""ConsentSBTv4 and ConsentDecisionVerifier: the real bytecode on an in-memory EVM (no network, no Sepolia, no Node).

The artefacts in blockchain/abi/ are built by tools/compile_v4.js (solc 0.8.24). ConsentTreeVectors.json holds Poseidon
values and tree roots that the same script computed OFF CHAIN with circomlibjs, so the tests compare the roots of the
contract with an off-chain computation without needing Node. The Groth16 verifier of the decision circuit is replaced by
MockDecisionVerifier, which proves nothing: these tests cover the token and the checks of the wrapper, not the proof.

Scenario numbers follow the thesis: A11 is a mint or revoke by a non-owner or a token transfer, A9 a tampered proof or
public signal. A transaction that must be refused is checked twice: the call reverts with the stated reason, and the same
transaction, once mined, has failed and emitted nothing."""
import json, os, re
from types import SimpleNamespace
import pytest
from eth_utils import keccak
from web3.logs import DISCARD

ABI_DIR = os.path.join(os.path.dirname(__file__), "..", "blockchain", "abi")
FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617
GAS = 3_000_000          # a fixed gas limit: no estimate, so a refused transaction is still mined (status 0)
TEST_KEY_LABEL = "halah contract v4 test owner"       # the client signs with a key derived from this label (not a secret)


def art(name):
    with open(os.path.join(ABI_DIR, name + ".json")) as f:
        return json.load(f)


VECTORS = art("ConsentTreeVectors")
MINTS = [s for s in VECTORS["sequence"] if s["op"] == "mint"]


# ---- the in-memory chain -------------------------------------------------------------------------------------------

@pytest.fixture(scope="module")
def base():
    """One chain for the module: the Poseidon contract, the token, the mock verifier and the wrapper, owned by `owner`,
    and a second set deployed through the Python client from a locally held test key."""
    pytest.importorskip("eth_tester", reason="eth-tester not installed")
    from web3 import Web3, EthereumTesterProvider
    from blockchain import contract_v4 as v4
    w3 = Web3(EthereumTesterProvider())
    owner, attacker, holder, other = w3.eth.accounts[:4]

    def deploy(name, *args):
        a = art(name)
        tx = w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"]).constructor(*args).transact({"from": owner, "gas": 6_000_000})
        rc = w3.eth.get_transaction_receipt(tx)
        assert rc.status == 1
        return w3.eth.contract(address=rc.contractAddress, abi=a["abi"])

    poseidon = deploy("PoseidonT3")
    token = deploy("ConsentSBTv4", poseidon.address)
    mock = deploy("MockDecisionVerifier")
    verifier = deploy("ConsentDecisionVerifier", mock.address, token.address)

    key = Web3.keccak(text=TEST_KEY_LABEL)
    signer = w3.eth.account.from_key(key).address
    w3.eth.send_transaction({"from": owner, "to": signer, "value": 10 ** 18, "gas": 21000})
    stack = v4.deploy_v4(w3, key, proof_verifier=mock.address, gas=6_000_000)
    return SimpleNamespace(w3=w3, Web3=Web3, v4=v4, tester=w3.provider.ethereum_tester, owner=owner, attacker=attacker,
                           holder=holder, other=other, poseidon=poseidon, token=token, mock=mock, verifier=verifier,
                           key=key, signer=signer, stack=stack)


@pytest.fixture
def chain(base):
    """The deployed contracts in their fresh state: whatever a test does is undone after it."""
    snapshot = base.tester.take_snapshot()
    yield base
    base.tester.revert_to_snapshot(snapshot)


def send(c, fn, sender=None):
    rc = c.w3.eth.get_transaction_receipt(fn.transact({"from": sender or c.owner, "gas": GAS}))
    assert rc.status == 1, "the transaction reverted"
    return rc


def mined(c, fn, sender=None):
    """Mine the transaction whatever its outcome and return the receipt (status 1 accepted, 0 reverted)."""
    return c.w3.eth.get_transaction_receipt(fn.transact({"from": sender or c.owner, "gas": GAS}))


def refused(c, fn, reason, sender=None):
    with pytest.raises(Exception, match=re.escape(reason)):
        fn.call({"from": sender or c.owner})
    rc = mined(c, fn, sender)
    assert rc.status == 0 and len(rc.logs) == 0


def commitment(n):
    return int.from_bytes(keccak(text=f"test commitment {n}"), "big") % FIELD


def consent_address(c, n):
    """A per-consent address: nobody holds its key."""
    return c.Web3.to_checksum_address("0x" + c.Web3.keccak(text=f"test consent address {n}")[-20:].hex())


def mint(c, n, to=None):
    rc = send(c, c.token.functions.mintConsent(to or consent_address(c, n), commitment(n)))
    return c.token.events.ConsentIssued().process_receipt(rc, errors=DISCARD)[0]["args"]["tokenId"], rc


def state(c):
    t = c.token.functions
    return (t.consentCount().call(), t.consentRoot().call(), t.revocationRoot().call())


# ---- the artefacts ---------------------------------------------------------------------------------------------------

def test_artefacts_hold_abi_and_bytecode_from_solc_0_8_24():
    for name in ("ConsentSBTv4", "ConsentDecisionVerifier", "MockDecisionVerifier"):
        a = art(name)
        assert a["contractName"] == name and a["compiler"] == "solc 0.8.24 optimizer 200"
        assert a["abi"] and a["bytecode"].startswith("0x") and len(a["bytecode"]) > 200
    assert len(art("ConsentSBTv4")["bytecode"]) // 2 < 24576                      # under the contract size limit
    assert art("PoseidonT3")["compiler"] == "circomlibjs 0.1.7 poseidonContract.createCode(2)"
    assert VECTORS["source"].startswith("circomlibjs 0.1.7") and VECTORS["depth"] == 16 and int(VECTORS["field"]) == FIELD


def test_token_abi_carries_only_the_commitment_and_the_revocation_state():
    abi = art("ConsentSBTv4")["abi"]
    fn = {x["name"]: x for x in abi if x["type"] == "function" and x["name"] not in ("safeTransferFrom",)}
    ev = {x["name"]: x for x in abi if x["type"] == "event"}
    assert [(i["name"], i["type"]) for i in fn["mintConsent"]["inputs"]] == [("to", "address"), ("commitment", "uint256")]
    assert [(o["name"], o["type"]) for o in fn["consents"]["outputs"]] == [("commitment", "uint256"), ("revoked", "bool")]
    assert [(i["name"], i["type"], i["indexed"]) for i in ev["ConsentIssued"]["inputs"]] == [("tokenId", "uint256", True), ("commitment", "uint256", False)]
    assert [(i["name"], i["type"], i["indexed"]) for i in ev["ConsentRevoked"]["inputs"]] == [("tokenId", "uint256", True)]
    assert [(i["name"], i["type"]) for i in fn["revoke"]["inputs"]] == [("tokenId", "uint256")]
    # nothing of what ConsentSBTv3 put on chain is named anywhere in the interface, and checkValidAt is retired
    names = {x.get("name") for x in abi} | {i["name"] for x in abi for i in x.get("inputs", []) + x.get("outputs", [])}
    v3 = {"patient", "requester", "purpose", "purposeHash", "notBefore", "expiry", "jurisdiction", "checkValidAt", "mintConsentV3", "burn"}
    assert not (names & v3)
    assert v3 <= {x.get("name") for x in art("ConsentSBTv3")["abi"]} | {i["name"] for x in art("ConsentSBTv3")["abi"] for i in x.get("inputs", []) + x.get("outputs", [])}


def test_token_storage_layout_has_no_field_for_parties_purpose_or_window():
    a = art("ConsentSBTv4")
    assert a["structs"] == {"struct ConsentSBTv4.Consent": [{"label": "commitment", "type": "uint256"}, {"label": "revoked", "type": "bool"}]}
    assert [(v["label"], v["type"]) for v in a["storage"]] == [
        ("_name", "string"), ("_symbol", "string"),                                # ERC-721: name and symbol
        ("_owners", "mapping(uint256 => address)"), ("_balances", "mapping(address => uint256)"),   # holder of each token
        ("_tokenApprovals", "mapping(uint256 => address)"), ("_operatorApprovals", "mapping(address => mapping(address => bool))"),
        ("_owner", "address"),                                                      # Ownable: the issuer
        ("consents", "mapping(uint256 => struct ConsentSBTv4.Consent)"),            # the commitment and the revocation state
        ("tokenOfCommitment", "mapping(uint256 => uint256)"),
        ("revocationRoot", "uint256"), ("_count", "uint32"), ("_rootPos", "uint8"),
        ("_roots", "uint256[9]"), ("_frontier", "uint256[16]"),                    # the consent tree: hashes only
        ("_revocationNodes", "mapping(uint256 => mapping(uint256 => uint256))")]   # the revocation tree: hashes only


def test_only_the_expected_functions_can_change_the_token_state():
    """No function could clear a revocation, change a commitment or move a token other than the ones listed here."""
    writers = sorted(x["name"] for x in art("ConsentSBTv4")["abi"] if x["type"] == "function" and x["stateMutability"] not in ("view", "pure"))
    assert writers == ["approve", "mintConsent", "revoke", "safeTransferFrom", "safeTransferFrom", "setApprovalForAll", "transferFrom", "transferOwnership"]
    writers = [x["name"] for x in art("ConsentDecisionVerifier")["abi"] if x["type"] == "function" and x["stateMutability"] not in ("view", "pure")]
    assert writers == ["verifyDecision"]


def test_verifier_abi_has_seven_public_signals_and_the_event_carries_nothing_else():
    abi = art("ConsentDecisionVerifier")["abi"]
    verify = next(x for x in abi if x.get("name") == "verifyDecision")
    assert [i["type"] for i in verify["inputs"]] == ["uint256[2]", "uint256[2][2]", "uint256[2]", "uint256[7]"]
    event = next(x for x in abi if x.get("name") == "ConsentVerified")
    assert [i["name"] for i in event["inputs"]] == ["tag", "t", "role", "purpose", "context", "consentRoot", "revocationRoot", "result"]
    assert not any(i["type"] == "address" for i in event["inputs"])               # no account is named in the event
    # the mock has the interface that the wrapper calls on the generated Groth16 verifier
    mock = next(x for x in art("MockDecisionVerifier")["abi"] if x.get("name") == "verifyProof")
    assert [i["type"] for i in mock["inputs"]] == ["uint256[2]", "uint256[2][2]", "uint256[2]", "uint256[7]"]


# ---- Poseidon on chain ---------------------------------------------------------------------------------------------

def test_poseidon_on_chain_equals_circomlibjs(chain):
    h = chain.poseidon.get_function_by_signature("poseidon(uint256[2])")
    for v in VECTORS["poseidon"]:
        assert h([int(x) for x in v["inputs"]]).call() == int(v["output"])
    zeros = [int(z) for z in VECTORS["zeros"]]
    assert zeros[0] == 0 and len(zeros) == 17
    for height in range(16):                                                      # roots of the empty subtrees
        assert h([zeros[height], zeros[height]]).call() == zeros[height + 1]


def test_empty_trees_have_the_offchain_root(chain):
    t = chain.token.functions
    empty = int(VECTORS["zeros"][16])
    assert t.consentRoot().call() == empty and t.revocationRoot().call() == empty and t.consentCount().call() == 0
    assert t.TREE_DEPTH().call() == 16 and t.RECENT_ROOTS().call() == 8 and t.FIELD().call() == FIELD
    assert t.hasher().call() == chain.poseidon.address
    assert t.recentRoots().call() == [empty] + [0] * 8
    assert t.isKnownConsentRoot(0).call() is False


def test_deployment_refuses_a_hasher_that_is_not_poseidon(chain):
    w3, a = chain.w3, art("ConsentSBTv4")
    factory = w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"])
    # a contract that answers 1 to every call: PUSH1 1, PUSH1 0, MSTORE, PUSH1 32, PUSH1 0, RETURN (behind its 12-byte loader)
    rc = w3.eth.get_transaction_receipt(w3.eth.send_transaction({"from": chain.owner, "data": "0x600a600c600039600a6000f3600160005260206000f3", "gas": 200000}))
    wrong = [rc.contractAddress, chain.mock.address, chain.attacker]              # a wrong hash, no hash function, no code
    with pytest.raises(Exception, match="hasher is not Poseidon"):
        w3.eth.call(factory.constructor(wrong[0]).build_transaction({"from": chain.owner, "gas": 6_000_000}))
    for address in wrong:
        rc = w3.eth.get_transaction_receipt(factory.constructor(address).transact({"from": chain.owner, "gas": 6_000_000}))
        assert rc.status == 0 and (rc.contractAddress is None or len(w3.eth.get_code(rc.contractAddress)) == 0)


# ---- the trees against the off-chain computation ---------------------------------------------------------------

@pytest.fixture(scope="module")
def trace(base):
    """Replay the scripted sequence of the vectors (20 mints and 7 revocations) once and record the chain after each step."""
    c, t = base, base.token.functions
    snapshot = c.tester.take_snapshot()
    steps, empty = [], t.consentRoot().call()
    for i, s in enumerate(VECTORS["sequence"]):
        if s["op"] == "mint":
            rc = send(c, t.mintConsent(consent_address(c, i), int(s["commitment"])))
            assert c.token.events.ConsentIssued().process_receipt(rc, errors=DISCARD)[0]["args"]["tokenId"] == s["tokenId"]
        else:
            rc = send(c, t.revoke(s["tokenId"]))
        steps.append(SimpleNamespace(op=s["op"], token_id=s["tokenId"], gas=rc.gasUsed, consent_root=t.consentRoot().call(),
                                     revocation_root=t.revocationRoot().call(), recent=t.recentRoots().call(),
                                     expected=s))
    roots = [empty] + [s.consent_root for s in steps if s.op == "mint"]           # every consent root in order
    known = [t.isKnownConsentRoot(r).call() for r in roots]
    valid = {n: t.checkValid(n).call() for n in range(0, len(MINTS) + 2)}
    c.tester.revert_to_snapshot(snapshot)
    return SimpleNamespace(steps=steps, roots=roots, known=known, valid=valid)


def test_consent_root_after_every_mint_equals_circomlibjs(trace):
    mints = [s for s in trace.steps if s.op == "mint"]
    assert len(mints) == 20
    for s in mints:
        assert s.consent_root == int(s.expected["consentRoot"])
    assert len(set(trace.roots)) == 21                                            # every mint gave a new root


def test_revocation_root_after_every_revocation_equals_circomlibjs(trace):
    revocations = [s for s in trace.steps if s.op == "revoke"]
    assert len(revocations) == 7
    for s in revocations:
        assert s.revocation_root == int(s.expected["revocationRoot"])
    assert len({s.revocation_root for s in revocations}) == 7                     # every revocation gave a new root


def test_a_mint_leaves_the_revocation_root_and_a_revocation_leaves_the_consent_root(trace):
    before = SimpleNamespace(consent_root=trace.roots[0], revocation_root=int(VECTORS["zeros"][16]))
    for s in trace.steps:
        assert s.consent_root == int(s.expected["consentRoot"]) and s.revocation_root == int(s.expected["revocationRoot"])
        if s.op == "mint":
            assert s.revocation_root == before.revocation_root and s.consent_root != before.consent_root
        else:
            assert s.consent_root == before.consent_root and s.revocation_root != before.revocation_root
        before = s


def test_contract_keeps_the_current_consent_root_and_the_last_eight(trace):
    seen = [trace.roots[0]]
    for s in trace.steps:
        if s.op == "mint":
            seen.append(s.consent_root)
        newest_first = list(reversed(seen))[:9]
        assert s.recent == newest_first + [0] * (9 - len(newest_first))
    # after 20 mints the roots 12 to 20 are acceptable (the current one and the 8 before it), the older ones are not
    assert trace.known == [False] * 12 + [True] * 9


def test_check_valid_reports_the_revocation_state(trace):
    revoked = {s.token_id for s in trace.steps if s.op == "revoke"}
    assert revoked == {1, 2, 4, 9, 16, 17, 20}
    for token_id in range(1, 21):
        assert trace.valid[token_id] is (token_id not in revoked)
    assert trace.valid[0] is False and trace.valid[21] is False                   # tokens that were never issued


def test_gas_of_mint_and_revoke_on_the_in_memory_chain(trace):
    """Sixteen Poseidon hashes dominate both. Measured values are printed with `pytest -s`. The bounds only guard against a regression."""
    mints = [s.gas for s in trace.steps if s.op == "mint"]
    revocations = [s.gas for s in trace.steps if s.op == "revoke"]
    print("\nmint gas:", mints, "\nrevoke gas:", revocations)
    assert all(550_000 < g < 720_000 for g in mints)
    assert all(600_000 < g < 950_000 for g in revocations)


class IncrementalTrees:
    """The two update rules of ConsentSBTv4 (_insertCommitment and _setRevocationLeaf), written out line by line over any hash."""

    def __init__(self, hash2, depth=16, zero=None):
        self.h, self.depth, self.zero = hash2, depth, list(zero or [0])
        for height in range(len(self.zero) - 1, depth):                          # roots of the empty subtrees
            self.zero.append(hash2(self.zero[height], self.zero[height]))
        self.frontier, self.nodes, self.revoked, self.count = [0] * depth, {}, set(), 0
        self.consent_root = self.revocation_root = self.zero[depth]

    def mint(self, leaf):
        node, idx, kept = leaf, self.count, False
        for height in range(self.depth):
            if idx & 1 == 0:
                if not kept:
                    self.frontier[height], kept = node, True
                node = self.h(node, self.zero[height])
            else:
                node = self.h(self.frontier[height], node)
            idx >>= 1
        self.count, self.consent_root = self.count + 1, node

    def revoke(self, token_id):
        index = token_id - 1
        self.revoked.add(index)
        sibling = 1 if (index ^ 1) in self.revoked else 0
        node = self.h(1, sibling) if index & 1 == 0 else self.h(sibling, 1)
        idx = index >> 1
        for height in range(1, self.depth):
            self.nodes[(height, idx)] = node
            sibling = self.nodes.get((height, idx ^ 1), 0) or self.zero[height]
            node = self.h(node, sibling) if idx & 1 == 0 else self.h(sibling, node)
            idx >>= 1
        self.revocation_root = node


def full_root(hash2, zero, leaves, depth=16):
    """Root of the tree over the sparse map index -> leaf, recomputed level by level from the leaves."""
    level = dict(leaves)
    for height in range(depth):
        level = {i: hash2(level.get(2 * i, zero[height]), level.get(2 * i + 1, zero[height])) for i in {k >> 1 for k in level}}
    return level.get(0, zero[depth])


def test_update_rules_equal_a_full_recomputation_far_beyond_the_on_chain_sequence(chain):
    """The on-chain sequence has 20 leaves. The same update rules are followed here over 3,000 leaves, where every level
    of carry up to height 11 occurs. This checks the rules, not the bytecode: the first half ties the rules to the chain."""
    # with the Poseidon contract as the hash, the written-out rules give the roots of the circomlibjs vectors
    # (the first 9 steps: 7 mints and 2 revocations, each hash a call to the contract)
    poseidon = chain.poseidon.get_function_by_signature("poseidon(uint256[2])")
    rules = IncrementalTrees(lambda left, right: poseidon([left, right]).call(), zero=[int(z) for z in VECTORS["zeros"]])
    for s in VECTORS["sequence"][:9]:
        rules.mint(int(s["commitment"])) if s["op"] == "mint" else rules.revoke(s["tokenId"])
        assert (rules.consent_root, rules.revocation_root) == (int(s["consentRoot"]), int(s["revocationRoot"]))
    # with a fast stand-in hash, they equal the full recomputation over many more leaves and revocations
    import hashlib, random
    fast = lambda left, right: int.from_bytes(hashlib.sha256(left.to_bytes(32, "big") + right.to_bytes(32, "big")).digest(), "big") % FIELD
    rules, leaves, rng, revocations = IncrementalTrees(fast), {}, random.Random(5), 0
    for i in range(3000):
        leaves[i] = rng.randrange(1, FIELD)
        rules.mint(leaves[i])
        if i < 260 or i % 97 == 0 or i & (i + 1) == 0 or i & (i - 1) == 0:          # densely at first, then at the carries
            assert rules.consent_root == full_root(fast, rules.zero, leaves)
        target = rng.randrange(i + 1)
        if rng.random() < 0.3 and target not in rules.revoked:
            rules.revoke(target + 1)
            revocations += 1
            if i < 260 or revocations % 20 == 0:
                assert rules.revocation_root == full_root(fast, rules.zero, {k: 1 for k in rules.revoked})
    assert revocations > 500 and rules.consent_root == full_root(fast, rules.zero, leaves)
    assert rules.revocation_root == full_root(fast, rules.zero, {k: 1 for k in rules.revoked})


# ---- the token -------------------------------------------------------------------------------------------------------

def test_mint_stores_only_the_commitment_and_the_revocation_state(chain):
    w3, t = chain.w3, chain.token.functions
    to = consent_address(chain, 1)
    token_id, rc = mint(chain, 1)
    assert token_id == 1 and t.ownerOf(1).call() == to and t.balanceOf(to).call() == 1
    assert t.consents(1).call() == [commitment(1), False] and t.tokenOfCommitment(commitment(1)).call() == 1
    # the transaction input is the selector, the per-consent address and the commitment: 4 + 32 + 32 bytes
    data = bytes(w3.eth.get_transaction(rc.transactionHash)["input"])
    assert len(data) == 68 and data[4:36] == bytes(12) + bytes.fromhex(to[2:]) and int.from_bytes(data[36:], "big") == commitment(1)
    # the record of token 1 is two storage words, the commitment and the flag, and the word after them is empty
    variable = int(next(v for v in art("ConsentSBTv4")["storage"] if v["label"] == "consents")["slot"])
    slot = int.from_bytes(w3.keccak((1).to_bytes(32, "big") + variable.to_bytes(32, "big")), "big")   # where the mapping keeps token 1
    word = lambda n: int.from_bytes(w3.eth.get_storage_at(chain.token.address, n), "big")
    assert [word(slot), word(slot + 1), word(slot + 2)] == [commitment(1), 0, 0]
    send(chain, t.revoke(1))
    assert [word(slot), word(slot + 1), word(slot + 2)] == [commitment(1), 1, 0]
    assert t.consents(1).call() == [commitment(1), True]


def test_events_carry_the_token_identifier_and_the_commitment_and_nothing_else(chain):
    to = consent_address(chain, 1)
    _, rc = mint(chain, 1)
    word = lambda value: (int(value, 16) if isinstance(value, str) else value).to_bytes(32, "big")
    allowed = {word(0), word(chain.owner), word(to), word(1), word(commitment(1)), word(3)}     # 3 is BurnAuth.Neither
    assert len(rc.logs) == 3                                                      # Transfer, ConsentIssued, Issued (ERC-5484)
    for entry in rc.logs:
        data = bytes(entry["data"])
        assert all(bytes(topic) in allowed for topic in entry["topics"][1:])
        assert all(data[i:i + 32] in allowed for i in range(0, len(data), 32))
    issued = chain.token.events.ConsentIssued().process_receipt(rc, errors=DISCARD)[0]["args"]
    assert dict(issued) == {"tokenId": 1, "commitment": commitment(1)}
    erc5484 = chain.token.events.Issued().process_receipt(rc, errors=DISCARD)[0]["args"]
    assert dict(erc5484) == {"from": chain.owner, "to": to, "tokenId": 1, "burnAuth": 3}
    rc = send(chain, chain.token.functions.revoke(1))
    assert len(rc.logs) == 1 and bytes(rc.logs[0]["data"]) == b"" and len(rc.logs[0]["topics"]) == 2
    assert dict(chain.token.events.ConsentRevoked().process_receipt(rc, errors=DISCARD)[0]["args"]) == {"tokenId": 1}


def test_A11_non_owner_cannot_mint(chain):
    before = state(chain)
    for sender in (chain.attacker, chain.holder):
        refused(chain, chain.token.functions.mintConsent(consent_address(chain, 1), commitment(1)), "Ownable: caller is not the owner", sender=sender)
    assert state(chain) == before and chain.token.functions.tokenOfCommitment(commitment(1)).call() == 0
    assert mint(chain, 1)[0] == 1                                                 # positive control: the owner can


def test_A11_non_owner_cannot_revoke(chain):
    token_id, _ = mint(chain, 1, to=chain.holder)
    before = state(chain)
    for sender in (chain.attacker, chain.holder):                                 # not even the holder of the token
        refused(chain, chain.token.functions.revoke(token_id), "Ownable: caller is not the owner", sender=sender)
    assert state(chain) == before and chain.token.functions.checkValid(token_id).call() is True
    send(chain, chain.token.functions.revoke(token_id))                           # positive control: the owner can
    assert chain.token.functions.checkValid(token_id).call() is False


def test_A11_token_cannot_be_transferred(chain):
    t = chain.token.functions
    token_id, _ = mint(chain, 1, to=chain.holder)
    refused(chain, t.transferFrom(chain.holder, chain.other, token_id), "Soulbound Token", sender=chain.holder)
    refused(chain, t.safeTransferFrom(chain.holder, chain.other, token_id), "Soulbound Token", sender=chain.holder)
    refused(chain, t.safeTransferFrom(chain.holder, chain.other, token_id, b""), "Soulbound Token", sender=chain.holder)
    send(chain, t.approve(chain.other, token_id), sender=chain.holder)            # an approval does not help either
    refused(chain, t.transferFrom(chain.holder, chain.other, token_id), "Soulbound Token", sender=chain.other)
    send(chain, t.setApprovalForAll(chain.attacker, True), sender=chain.holder)
    refused(chain, t.transferFrom(chain.holder, chain.attacker, token_id), "Soulbound Token", sender=chain.attacker)
    refused(chain, t.transferFrom(chain.holder, chain.owner, token_id), "caller is not token owner or approved", sender=chain.owner)
    assert t.ownerOf(token_id).call() == chain.holder and t.balanceOf(chain.other).call() == 0
    send(chain, t.revoke(token_id))                                               # a revoked token does not move either
    refused(chain, t.transferFrom(chain.holder, chain.other, token_id), "Soulbound Token", sender=chain.holder)
    assert t.ownerOf(token_id).call() == chain.holder


def test_revocation_is_irreversible(chain):
    t = chain.token.functions
    token_id, _ = mint(chain, 1)
    root_before = t.revocationRoot().call()
    send(chain, t.revoke(token_id))
    root_revoked = t.revocationRoot().call()
    assert root_revoked != root_before and t.checkValid(token_id).call() is False
    refused(chain, t.revoke(token_id), "already revoked")                         # a second revocation changes nothing
    refused(chain, t.mintConsent(consent_address(chain, 2), commitment(1)), "commitment already issued")   # no second token for it
    refused(chain, t.mintConsent(consent_address(chain, 1), commitment(2)), "address already holds a consent")
    mint(chain, 2); mint(chain, 3)                                                # later mints and time do not bring it back
    chain.tester.time_travel(chain.w3.eth.get_block("pending").timestamp + 10 * 365 * 86400)
    send(chain, t.revoke(3))
    assert t.checkValid(token_id).call() is False and t.consents(token_id).call() == [commitment(1), True]
    assert t.checkValid(2).call() is True
    assert t.revocationRoot().call() not in (root_before, root_revoked)
    assert t.ownerOf(token_id).call() == consent_address(chain, 1)                # the token remains as the record


def test_mint_refuses_a_bad_commitment_a_reused_address_and_a_duplicate(chain):
    t = chain.token.functions
    before = state(chain)
    refused(chain, t.mintConsent(consent_address(chain, 1), 0), "commitment outside the field")
    refused(chain, t.mintConsent(consent_address(chain, 1), FIELD), "commitment outside the field")
    refused(chain, t.mintConsent("0x0000000000000000000000000000000000000000", commitment(1)), "address zero")
    assert state(chain) == before
    assert mint(chain, 1)[0] == 1 and t.mintConsent(consent_address(chain, 2), FIELD - 1).call({"from": chain.owner}) == 2
    refused(chain, t.mintConsent(consent_address(chain, 1), commitment(2)), "address already holds a consent")   # one address, one consent
    refused(chain, t.mintConsent(consent_address(chain, 2), commitment(1)), "commitment already issued")
    refused(chain, t.revoke(0), "no token")
    refused(chain, t.revoke(2), "no token")
    assert t.consentCount().call() == 1


def test_check_valid_does_not_depend_on_time(chain):
    """The validity window is inside the commitment and proved in the circuit: the token knows the revocation state only."""
    t = chain.token.functions
    token_id, _ = mint(chain, 1)
    chain.tester.time_travel(chain.w3.eth.get_block("pending").timestamp + 50 * 365 * 86400)
    mint(chain, 2)
    assert t.checkValid(token_id).call() is True and t.checkValid(2).call() is True and t.checkValid(3).call() is False


def test_token_follows_erc5484_and_the_owner_cannot_be_given_up(chain):
    t = chain.token.functions
    token_id, _ = mint(chain, 1)
    assert t.supportsInterface(bytes.fromhex("0489b56f")).call() is True           # ERC-5484
    assert t.supportsInterface(bytes.fromhex("80ac58cd")).call() is True           # ERC-721
    assert t.burnAuth(token_id).call() == 3                                        # Neither: no token is ever burnt
    with pytest.raises(Exception, match="no token"):
        t.burnAuth(2).call()
    assert t.name().call() == "MedicalConsent" and t.symbol().call() == "CONSENT" and t.owner().call() == chain.owner
    with pytest.raises(Exception, match="ownership cannot be renounced"):
        t.renounceOwnership().call({"from": chain.owner})
    with pytest.raises(Exception, match="caller is not the owner"):
        t.renounceOwnership().call({"from": chain.attacker})


# ---- the verifier wrapper (Algorithm 7.3), with the mock verifier -----------------------------------------------

def tag(n):
    return int.from_bytes(keccak(text=f"test request tag {n}"), "big") % FIELD


def chain_time(c):
    """Timestamp of the latest block: the time a prover reads from the chain, and the block time that a call sees."""
    return c.w3.eth.get_block("latest").timestamp


def next_block_time(c):
    """Timestamp of the block that the next transaction is mined in (one second after the latest block here)."""
    return c.w3.eth.get_block("pending").timestamp


def signals(c, n=1, t=None, role=1, purpose=1, context=0x4155, consent_root=None, revocation_root=None):
    """Public signals [t, role, purpose, context, tag, consentRoot, revocationRoot] for request n against the current chain."""
    f = c.token.functions
    return [chain_time(c) if t is None else t, role, purpose, context, tag(n),
            f.consentRoot().call() if consent_root is None else consent_root,
            f.revocationRoot().call() if revocation_root is None else revocation_root]


def mock_proof(pub, a1=11, b=((21, 22), (23, 24)), c=(31, 32)):
    """The only "proof" that MockDecisionVerifier accepts for these public signals. It is not a zero-knowledge proof."""
    from eth_abi import encode
    digest = keccak(encode(["uint256[7]", "uint256", "uint256[2][2]", "uint256[2]"], [pub, a1, b, c]))
    return [int.from_bytes(digest, "big") % FIELD, a1], [list(b[0]), list(b[1])], list(c)


def verify(c, pub, proof=None):
    return c.verifier.functions.verifyDecision(*(proof or mock_proof(pub)), pub)


def test_accepted_proof_emits_consent_verified_with_the_public_inputs(chain):
    v = chain.verifier.functions
    mint(chain, 1)
    pub = signals(chain)
    assert v.TOLERANCE().call() == 300 and v.FIELD().call() == FIELD
    assert v.proofVerifier().call() == chain.mock.address and v.consentToken().call() == chain.token.address
    assert v.tagSeen(pub[4]).call() is False and v.verifiedAtBlock(pub[4]).call() == 0
    assert verify(chain, pub).call() is True
    rc = send(chain, verify(chain, pub), sender=chain.other)                      # anyone may submit: the proof is what counts
    assert len(rc.logs) == 1
    event = dict(chain.verifier.events.ConsentVerified().process_receipt(rc, errors=DISCARD)[0]["args"])
    assert event == {"tag": pub[4], "t": pub[0], "role": 1, "purpose": 1, "context": 0x4155,
                     "consentRoot": pub[5], "revocationRoot": pub[6], "result": True}
    assert v.tagSeen(pub[4]).call() is True and v.verifiedAtBlock(pub[4]).call() == rc.blockNumber
    assert 0 <= chain.w3.eth.get_block(rc.blockNumber).timestamp - pub[0] <= 300


def test_replayed_proof_is_rejected_on_its_tag(chain):
    mint(chain, 1)
    pub = signals(chain)
    proof = mock_proof(pub)
    send(chain, verify(chain, pub, proof))
    refused(chain, verify(chain, pub, proof), "tag already seen")                 # the same proof again
    fresh_time = list(pub); fresh_time[0] = chain_time(chain)                     # the same tag in a new proof
    refused(chain, verify(chain, fresh_time), "tag already seen")
    another = signals(chain, n=2)                                                 # a new request has a new tag and passes
    send(chain, verify(chain, another))
    assert chain.verifier.functions.tagSeen(another[4]).call() is True


def test_tag_cannot_be_replayed_as_another_representation_of_the_same_field_element(chain):
    mint(chain, 1)
    pub = signals(chain)
    send(chain, verify(chain, pub))
    alias = signals(chain); alias[4] = pub[4] + FIELD                             # the same element of the field, another integer
    refused(chain, verify(chain, alias), "public input outside the field")
    for i in range(7):                                                            # the same holds for every public signal
        outside = signals(chain, n=2); outside[i] = outside[i] + FIELD
        refused(chain, verify(chain, outside), "public input outside the field")
    assert chain.verifier.functions.tagSeen(tag(2)).call() is False


def test_proof_with_a_time_after_the_block_is_rejected(chain):
    mint(chain, 1)
    refused(chain, verify(chain, signals(chain, t=next_block_time(chain) + 1)), "time is in the future")
    refused(chain, verify(chain, signals(chain, t=chain_time(chain) + 86400)), "time is in the future")
    # the boundary, on mined transactions: one second after the block time fails, the block time itself passes
    block_time = lambda rc: chain.w3.eth.get_block(rc.blockNumber).timestamp
    pub = signals(chain, t=next_block_time(chain) + 1)
    rc = mined(chain, verify(chain, pub))
    assert rc.status == 0 and pub[0] - block_time(rc) == 1
    pub = signals(chain, t=next_block_time(chain))
    rc = mined(chain, verify(chain, pub))
    assert rc.status == 1 and pub[0] == block_time(rc)


def test_back_dated_proof_is_rejected_on_its_time(chain):
    mint(chain, 1)
    refused(chain, verify(chain, signals(chain, t=chain_time(chain) - 301)), "time is too old")
    refused(chain, verify(chain, signals(chain, t=chain_time(chain) - 86400)), "time is too old")
    refused(chain, verify(chain, signals(chain, t=0)), "time is too old")
    # the boundary, on mined transactions: 301 seconds before the block time fails, exactly TOLERANCE = 300 passes
    block_time = lambda rc: chain.w3.eth.get_block(rc.blockNumber).timestamp
    pub = signals(chain, t=next_block_time(chain) - 301)
    rc = mined(chain, verify(chain, pub))
    assert rc.status == 0 and block_time(rc) - pub[0] == 301
    pub = signals(chain, t=next_block_time(chain) - 300)
    rc = mined(chain, verify(chain, pub))
    assert rc.status == 1 and block_time(rc) - pub[0] == 300
    # a proof that was fresh is too old once the chain has moved on by more than the tolerance
    late = signals(chain, n=2)
    assert verify(chain, late).call() is True
    chain.tester.time_travel(late[0] + 302)
    refused(chain, verify(chain, late), "time is too old")


def test_proof_against_the_revocation_root_from_before_a_revocation_is_rejected(chain):
    t = chain.token.functions
    mint(chain, 1); mint(chain, 2)
    stale = t.revocationRoot().call()
    send(chain, verify(chain, signals(chain, n=1)))                               # accepted while the root is current
    send(chain, t.revoke(1))
    assert t.revocationRoot().call() != stale
    refused(chain, verify(chain, signals(chain, n=2, revocation_root=stale)), "revocation root is not current")
    refused(chain, verify(chain, signals(chain, n=2, revocation_root=0)), "revocation root is not current")
    send(chain, verify(chain, signals(chain, n=2)))                               # only the current root passes
    send(chain, t.revoke(2))                                                      # and it stops passing at the next revocation
    refused(chain, verify(chain, signals(chain, n=3, revocation_root=stale)), "revocation root is not current")


def test_consent_root_must_be_current_or_among_the_last_eight(chain):
    t = chain.token.functions
    mint(chain, 1)
    root = t.consentRoot().call()
    refused(chain, verify(chain, signals(chain, consent_root=12345)), "consent root is not recent")
    refused(chain, verify(chain, signals(chain, consent_root=0)), "consent root is not recent")
    for n in range(2, 10):                                                        # eight mints while the proof is being made
        mint(chain, n)
    assert t.consentRoot().call() != root
    send(chain, verify(chain, signals(chain, n=1, consent_root=root)))            # a mint during proving does not void the proof
    mint(chain, 10)                                                               # the ninth mint pushes the root out
    refused(chain, verify(chain, signals(chain, n=2, consent_root=root)), "consent root is not recent")
    send(chain, verify(chain, signals(chain, n=2)))


def test_A9_tampered_proof_or_public_signal_is_rejected(chain):
    mint(chain, 1)
    pub = signals(chain)
    a, b, c = mock_proof(pub)
    for i, changed in ((1, 2), (2, 3), (3, 0x5553)):                              # another role, purpose or context
        tampered = list(pub); tampered[i] = changed
        refused(chain, verify(chain, tampered, (a, b, c)), "proof is not valid")
    other_tag = list(pub); other_tag[4] = tag(2)                                  # the proof of one request under another tag
    refused(chain, verify(chain, other_tag, (a, b, c)), "proof is not valid")
    refused(chain, verify(chain, pub, ([a[0] + 1, a[1]], b, c)), "proof is not valid")
    refused(chain, verify(chain, pub, ([a[0], a[1] + 1], b, c)), "proof is not valid")
    refused(chain, verify(chain, pub, (a, [b[0], [b[1][1], b[1][0]]], c)), "proof is not valid")
    refused(chain, verify(chain, pub, (a, b, [c[1], c[0]])), "proof is not valid")
    assert chain.verifier.functions.tagSeen(pub[4]).call() is False               # a refusal does not use up the tag
    pub = signals(chain)
    send(chain, verify(chain, pub))                                               # the untouched proof still passes
    assert chain.verifier.functions.tagSeen(pub[4]).call() is True


def test_wrapper_refuses_addresses_without_code(chain):
    a = art("ConsentDecisionVerifier")
    factory = chain.w3.eth.contract(abi=a["abi"], bytecode=a["bytecode"])
    for args in ((chain.attacker, chain.token.address), (chain.mock.address, chain.attacker)):
        with pytest.raises(Exception, match="not a contract"):
            chain.w3.eth.call(factory.constructor(*args).build_transaction({"from": chain.owner, "gas": 2_000_000}))


# ---- the Python client -----------------------------------------------------------------------------------------------

def clients(c, gas_limit=GAS):
    token = c.v4.ConsentContractV4(w3=c.w3, address=c.stack["token"], private_key=c.key, gas_limit=gas_limit)
    verifier = c.v4.DecisionVerifierContract(w3=c.w3, address=c.stack["verifier"], private_key=c.key, gas_limit=gas_limit)
    return token, verifier


def test_client_deploys_mints_and_revokes_with_a_locally_signed_transaction(chain):
    v4 = chain.v4
    token, _ = clients(chain)
    assert set(chain.stack["gas_used"]) == {"PoseidonT3", "ConsentSBTv4", "ConsentDecisionVerifier"}
    s = token.status()
    assert s["signer"] == chain.signer == s["owner"] and s["signer_is_owner"] is True and s["contract_has_code"] is True
    assert s["version"] == 4 and s["consent_count"] == 0 and s["is_sepolia"] is False
    empty = int(VECTORS["zeros"][16])
    assert token.read_roots()["consent_root"] == empty == token.read_roots()["revocation_root"]

    to, salt = v4.derive_consent_address("did:patient:layan", "consent-1")
    r = token.mint_consent(to, hex(int(MINTS[0]["commitment"])))                  # the model keeps the commitment as hex
    assert r["status"] == 1 and r["token_id"] == 1 and r["leaf_index"] == 0 and r["token_address"] == to and r["version"] == 4
    assert r["commitment"] == int(MINTS[0]["commitment"]) and r["consent_root"] == int(MINTS[0]["consentRoot"])
    assert r["gas_used"] > 0 and r["tx_hash"].startswith("0x") and r["explorer_tx"].endswith(r["tx_hash"])
    r2 = token.mint_consent(v4.derive_consent_address("did:patient:layan", "consent-2")[0], MINTS[1]["commitment"])
    assert r2["token_id"] == 2 and r2["consent_root"] == int(MINTS[1]["consentRoot"])
    assert token.consent_of(1) == {"commitment": int(MINTS[0]["commitment"]), "revoked": False}
    assert token.token_of_commitment(MINTS[1]["commitment"]) == 2 and token.token_of_commitment(12345) is None
    assert token.check_valid(1) is True and token.consent_count() == 2 and token.is_known_consent_root(r["consent_root"]) is True
    roots = token.read_roots()
    assert roots["consent_root"] == r2["consent_root"] and roots["recent_roots"] == [r2["consent_root"], r["consent_root"], empty]
    assert roots["block_timestamp"] == token.latest_block_time() == chain.w3.eth.get_block("latest").timestamp

    rv = token.revoke(2)
    assert rv["status"] == 1 and rv["token_id"] == 2 and rv["gas_used"] > 0
    assert rv["revocation_root"] == int(VECTORS["sequence"][5]["revocationRoot"])  # the vector step that revokes token 2
    assert token.check_valid(2) is False and token.check_valid(1) is True and token.consent_of(2)["revoked"] is True
    again = token.revoke(2)                                                       # refused on chain: mined, failed, nothing changed
    assert again["status"] == 0 and again["revocation_root"] is None and token.revocation_root() == rv["revocation_root"]
    dup = token.mint_consent(v4.derive_consent_address("did:patient:layan", "consent-3")[0], MINTS[0]["commitment"])
    assert dup["status"] == 0 and dup["token_id"] is None and dup["consent_root"] is None and token.consent_count() == 2
    # the trees can be rebuilt from the events alone
    assert token.issued_commitments() == [int(MINTS[0]["commitment"]), int(MINTS[1]["commitment"])]
    assert token.revoked_token_ids() == [2]


def test_client_estimates_gas_when_no_limit_is_given(chain):
    """The path used on a public network: the node estimates, and a transaction that would revert is not sent at all."""
    token, _ = clients(chain, gas_limit=None)
    to, _ = chain.v4.derive_consent_address("did:patient:layan", "consent-1")
    r = token.mint_consent(to, MINTS[0]["commitment"])
    assert r["status"] == 1 and r["token_id"] == 1 and r["consent_root"] == int(MINTS[0]["consentRoot"])
    blocks = chain.w3.eth.block_number
    with pytest.raises(Exception, match="commitment already issued"):
        token.mint_consent(chain.v4.derive_consent_address("did:patient:layan", "consent-2")[0], MINTS[0]["commitment"])
    assert chain.w3.eth.block_number == blocks                                    # nothing was mined


def test_client_is_refused_when_its_key_is_not_the_owner(chain):
    intruder = chain.Web3.keccak(text="halah contract v4 test intruder")
    chain.w3.eth.send_transaction({"from": chain.owner, "to": chain.w3.eth.account.from_key(intruder).address, "value": 10 ** 18, "gas": 21000})
    token = chain.v4.ConsentContractV4(w3=chain.w3, address=chain.stack["token"], private_key=intruder, gas_limit=GAS)
    assert token.status()["signer_is_owner"] is False
    r = token.mint_consent(consent_address(chain, 1), commitment(1))
    assert r["status"] == 0 and r["token_id"] is None and token.consent_count() == 0
    owner, _ = clients(chain)
    assert owner.mint_consent(consent_address(chain, 1), commitment(1))["token_id"] == 1
    assert token.revoke(1)["status"] == 0 and owner.check_valid(1) is True


def test_client_verifies_a_decision_and_reports_each_rejection(chain):
    v4 = chain.v4
    token, verifier = clients(chain)
    s = verifier.status()
    assert s["proof_verifier"] == chain.mock.address and s["consent_token"] == chain.stack["token"] and s["tolerance"] == 300 == v4.TOLERANCE
    token.mint_consent(consent_address(chain, 1), commitment(1))
    token.mint_consent(consent_address(chain, 2), commitment(2))
    roots = token.read_roots()
    request = lambda n, **change: [change.get("t", token.latest_block_time()), 1, 1, 0x4155, tag(n),   # t is read from the chain
                                   change.get("consent_root", roots["consent_root"]), change.get("revocation_root", roots["revocation_root"])]
    pub = request(1)
    r = verifier.verify_decision(mock_proof(pub), [str(x) for x in pub])           # snarkjs gives the signals as decimal strings
    assert r["accepted"] is True and r["reason"] is None and r["status"] == 1 and r["reference"] == r["tx_hash"]
    assert r["public_inputs"] == dict(zip(v4.PUBLIC_SIGNALS, pub)) and r["gas_used"] > 0
    assert r["event"] == {"tag": pub[4], "t": pub[0], "role": 1, "purpose": 1, "context": 0x4155,
                          "consentRoot": pub[5], "revocationRoot": pub[6], "result": True}
    assert verifier.tag_seen(pub[4]) is True and verifier.verified_at_block(pub[4]) == r["block_number"]
    assert verifier.tag_seen(tag(99)) is False and verifier.verified_at_block(tag(99)) is None

    blocks = chain.w3.eth.block_number
    replay = verifier.verify_decision(mock_proof(pub), pub)
    assert replay["accepted"] is False and replay["reason"] == "TAG_ALREADY_SEEN" and replay["reason_text"] == "tag already seen"
    assert replay["tx_hash"] is None and replay["reference"] is None and chain.w3.eth.block_number == blocks   # a refusal costs nothing
    cases = {"TIME_IN_FUTURE": request(2, t=token.latest_block_time() + 60), "TIME_TOO_OLD": request(2, t=token.latest_block_time() - 301),
             "REVOCATION_ROOT_NOT_CURRENT": request(2, revocation_root=1), "CONSENT_ROOT_NOT_RECENT": request(2, consent_root=1)}
    for code, bad in cases.items():
        assert verifier.verify_decision(mock_proof(bad), bad)["reason"] == code
    bad = request(2)
    tampered = verifier.verify_decision(mock_proof(bad), bad[:1] + [2] + bad[2:])  # the role is changed after proving
    assert tampered["accepted"] is False and tampered["reason"] == "PROOF_NOT_VALID"
    outside = request(2); outside[4] += FIELD
    assert verifier.verify_decision(mock_proof(outside), outside)["reason"] == "INPUT_OUTSIDE_FIELD"
    assert set(v4.REJECTIONS.values()) == set(cases) | {"TAG_ALREADY_SEEN", "PROOF_NOT_VALID", "INPUT_OUTSIDE_FIELD"}
    assert chain.w3.eth.block_number == blocks and verifier.tag_seen(tag(2)) is False

    # after a revocation the proof built before it is refused, and the refusal can be put on chain as evidence
    stale = request(2)
    token.revoke(1)
    r = verifier.verify_decision(mock_proof(stale), stale, record_rejection=True)
    assert r["accepted"] is False and r["reason"] == "REVOCATION_ROOT_NOT_CURRENT" and r["status"] == 0
    assert r["tx_hash"] is not None and r["reference"] is None and r["event"] is None
    fresh = request(2, revocation_root=token.revocation_root())
    assert verifier.verify_decision({"proof": mock_proof(fresh), "publicSignals": [str(x) for x in fresh]})["accepted"] is True
    seen = verifier.verifications()
    assert [e["tag"] for e in seen] == [tag(1), tag(2)] and all(e["result"] is True for e in seen)
    with pytest.raises(ValueError):
        verifier.verify_decision(mock_proof(fresh), fresh[:6])


def test_third_party_reverifies_from_the_chain_alone(chain):
    """A reader without a key and without the off-chain record finds the verification, takes the proof from the
    transaction input and checks it against the Groth16 verifier (here the mock) by a call."""
    v4 = chain.v4
    token, verifier = clients(chain)
    token.mint_consent(consent_address(chain, 1), commitment(1))
    roots = token.read_roots()
    pub = [roots["block_timestamp"], 1, 1, 0x4155, tag(1), roots["consent_root"], roots["revocation_root"]]
    accepted = verifier.verify_decision(mock_proof(pub), pub)
    assert accepted["accepted"] is True

    reader = v4.DecisionVerifierContract(w3=chain.w3, address=chain.stack["verifier"], read_only=True)
    assert reader.signer is None and reader.status()["signer"] is None
    (event,) = reader.verifications()
    assert event["tx_hash"] == accepted["reference"] and event["tag"] == tag(1) and event["block_number"] == accepted["block_number"]
    found = reader.submitted_proof(event["tx_hash"])
    assert found["publicSignals"] == pub and found["proof"] == tuple(mock_proof(pub))
    assert reader.reverify(found) is True                                         # the proof holds for its public signals
    changed = list(pub); changed[2] = 2
    assert reader.reverify(found["proof"], changed) is False                      # and for no others
    with pytest.raises(RuntimeError, match="read-only"):                          # a reader cannot submit, mint or revoke
        reader.verify_decision(found)
    token_reader = v4.ConsentContractV4(w3=chain.w3, address=chain.stack["token"], read_only=True)
    assert token_reader.status()["signer_is_owner"] is None and token_reader.read_roots()["consent_root"] == roots["consent_root"]
    for write in (lambda: token_reader.mint_consent(consent_address(chain, 2), commitment(2)), lambda: token_reader.revoke(1)):
        with pytest.raises(RuntimeError, match="read-only"):
            write()
    assert token_reader.consent_count() == 1 and token_reader.check_valid(1) is True


def test_deployment_entry_point_deploys_the_three_contracts(chain, capsys, monkeypatch):
    v4 = chain.v4
    out = v4.main([chain.mock.address], w3=chain.w3, private_key=chain.key, gas=6_000_000)
    printed = capsys.readouterr().out
    assert "CONTRACT_V4_ADDRESS=" + out["token"] in printed and "VERIFIER_ADDRESS=" + out["verifier"] in printed
    assert "POSEIDON_ADDRESS=" + out["poseidon"] in printed and out["token"] != chain.stack["token"]
    token = v4.ConsentContractV4(w3=chain.w3, address=out["token"], private_key=chain.key, gas_limit=GAS)
    verifier = v4.DecisionVerifierContract(w3=chain.w3, address=out["verifier"], private_key=chain.key, gas_limit=GAS)
    assert token.status()["signer_is_owner"] is True and verifier.status()["consent_token"] == out["token"]
    assert token.contract.functions.hasher().call() == out["poseidon"]
    only_token = v4.main([], w3=chain.w3, private_key=chain.key, gas=6_000_000)   # without a Groth16 verifier: the token alone
    assert only_token["verifier"] is None and "VERIFIER_ADDRESS" not in capsys.readouterr().out
    monkeypatch.delenv("PRIVATE_KEY", raising=False)
    with pytest.raises(RuntimeError, match="PRIVATE_KEY"):
        v4.main([], w3=chain.w3)


def test_per_consent_address_is_unlinkable_without_its_salt():
    from blockchain import contract_v4 as v4
    from blockchain.contract import did_to_address
    from eth_utils import is_checksum_address
    patient = "did:patient:layan"
    a1, s1 = v4.derive_consent_address(patient, "consent-1")
    a2, s2 = v4.derive_consent_address(patient, "consent-2")
    a3, s3 = v4.derive_consent_address(patient, "consent-1")                       # the same consent, a fresh salt
    assert is_checksum_address(a1) and len({a1, a2, a3, did_to_address(patient)}) == 4 and len({s1, s2, s3}) == 3
    assert len(bytes.fromhex(s1[2:])) == 32
    assert v4.derive_consent_address(patient, "consent-1", salt=s1) == (a1, s1)   # the holder of the salt derives it again
    assert v4.derive_consent_address(patient, "consent-1", salt=bytes.fromhex(s1[2:])) == (a1, s1)
    assert v4.derive_consent_address(did_to_address(patient), "consent-1", salt=s1)[0] == a1   # a DID or its wallet address
    assert v4.derive_consent_address("did:patient:other", "consent-1", salt=s1)[0] != a1
    fixed = v4.derive_consent_address(patient, "consent-1", salt=7)
    assert fixed == (v4.derive_consent_address(patient, "consent-1", salt="0x" + "00" * 31 + "07")[0], "0x" + "00" * 31 + "07")
    for bad in (b"short", 2 ** 256, -1):
        with pytest.raises(ValueError):
            v4.derive_consent_address(patient, "consent-1", salt=bad)


def test_proof_and_field_helpers():
    from blockchain import contract_v4 as v4
    # a proof in the layout of snarkjs: each pair of pi_b is swapped for the Solidity verifier, the third entries are dropped
    proof = {"pi_a": ["1", "2", "1"], "pi_b": [["3", "4"], ["5", "6"], ["1", "0"]], "pi_c": ["7", "8", "1"], "protocol": "groth16", "curve": "bn128"}
    assert v4.proof_to_calldata(proof) == ([1, 2], [[4, 3], [6, 5]], [7, 8])
    assert v4.proof_to_calldata({"proof": proof, "publicSignals": []}) == ([1, 2], [[4, 3], [6, 5]], [7, 8])
    assert v4.proof_to_calldata((["1", 2], [[4, 3], [6, 5]], (7, 8))) == ([1, 2], [[4, 3], [6, 5]], [7, 8])   # already in the Solidity layout
    assert v4.to_field("0x10") == 16 == v4.to_field("16") == v4.to_field(16) == v4.to_field(b"\x10")
    assert v4.to_field(FIELD - 1) == FIELD - 1 and v4.FIELD == FIELD
    for bad in (FIELD, -1, None, True):
        with pytest.raises(ValueError):
            v4.to_field(bad)
    from web3.exceptions import ContractLogicError
    assert v4.revert_reason(Exception("execution reverted: tag already seen")) == "tag already seen"
    assert v4.revert_reason(ContractLogicError("execution reverted: time is too old", "0x08c379a0")) == "time is too old"   # a public node
    assert v4.REJECTIONS[v4.revert_reason(ContractLogicError("execution reverted: proof is not valid"))] == "PROOF_NOT_VALID"
    assert v4.PUBLIC_SIGNALS == ("t", "role", "purpose", "context", "tag", "consentRoot", "revocationRoot")
    assert v4.TREE_DEPTH == 16 and v4.RECENT_ROOTS == 8
    assert v4.load_artifact("ConsentSBTv4")["contractName"] == "ConsentSBTv4" == v4.load_artifact("ConsentSBTv4.json")["contractName"]


def test_client_needs_an_address_and_a_key(monkeypatch):
    from blockchain import contract_v4 as v4
    for name in ("CONTRACT_V4_ADDRESS", "VERIFIER_ADDRESS", "PRIVATE_KEY"):
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(RuntimeError, match="CONTRACT_V4_ADDRESS"):
        v4.ConsentContractV4()
    with pytest.raises(RuntimeError, match="VERIFIER_ADDRESS"):
        v4.DecisionVerifierContract()
    with pytest.raises(RuntimeError, match="PRIVATE_KEY"):
        v4.ConsentContractV4(address="0x" + "11" * 20)
