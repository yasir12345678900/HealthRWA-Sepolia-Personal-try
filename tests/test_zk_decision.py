"""Commitment, the two trees and the decision proof (Chapter 7, Algorithms 7.1 and 7.2).
The tests of the commitment, the trees and the predicate set need Python only. The tests that compare with
circomlibjs need zk/node_modules, and the tests that prove need the built circuit (bash zk/build_decision.sh):
they are skipped when these are absent, as tests/test_zk.py does. No test uses the network or the clock."""
import copy
import json
import os
import shutil
import subprocess
from datetime import datetime

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZK = os.path.join(ROOT, "zk")
T0 = 1_800_000_000                 # start of the consent window of the tests, in Unix seconds
DAY = 86400
BLINDING = 0x1234567890ABCDEF1234567890ABCDEF
NONCE = 0xFEDCBA0987654321
DOCTOR = "did:hospital:001"
# Known answers of circomlibjs 0.1.7 (buildPoseidon). The first is the published circomlib test vector.
POSEIDON_1_2 = 0x115cc0f5e7d690413df64c6b9662e9cf2a3617f2743245519e19607a4417189a
POSEIDON_1_TO_10 = 3657500514307717306974218405144578736633140001277925127187636780142269815841
EMPTY_ROOT_16 = 0x2a7c7c9b6ce5880b9f6f228d72bf6a575a526f29c66ecceef8b753d38bba7323   # the constant of the consent contract
ROOT_OF_1_2_3 = 11397113127042759377329521018964827364778122266531915391172612913853570517131


def _iso(seconds):
    return datetime.fromtimestamp(seconds).isoformat()


def _consent(consent_id="zk-d-1", days=30, **changes):
    from models.consent import Consent
    fields = dict(consent_id=consent_id, patient_did="did:patient:layan", requester_did=DOCTOR,
                  guardian_dids=["did:parent:A", "did:parent:B"], purpose="Treatment", scope=["Observation", "Medication"],
                  threshold=2, signatures=[], start_date=_iso(T0), expiry_date=_iso(T0 + days * DAY))
    fields.update(changes)
    return Consent(**fields)


def _issued(consent=None, before=3, after=2):
    """A committed consent inside a consent tree that holds other consents before and after it, and a
    revocation tree in which one of the others is revoked. Returns (consent, consent tree, revocation tree)."""
    from services import commitment_service as cs, merkle_service as ms
    consent = consent or _consent()
    cs.commit_consent(consent, blinding=BLINDING)
    tree = ms.ConsentTree([cs.poseidon([7, i]) for i in range(before)])
    tree.append(consent.commitment)
    for i in range(after):
        tree.append(cs.poseidon([8, i]))
    return consent, tree, ms.RevocationTree([1])


def _js_available():
    return shutil.which("node") is not None and os.path.exists(os.path.join(ZK, "node_modules", "circomlibjs", "package.json"))


def _js(request):
    r = subprocess.run(["node", os.path.join(ZK, "poseidon_cli.js"), json.dumps(request)], capture_output=True, text=True, cwd=ZK, timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["out"]


def _need_circuit():
    from services import zk_decision_service as zd
    if not zd.decision_available():
        pytest.skip("run zk/build_decision.sh")
    return zd


# ---- field encoding and Poseidon -----------------------------------------------------------------

def test_poseidon_reproduces_the_circomlib_known_answers():
    from services import commitment_service as cs
    assert cs.poseidon([1, 2]) == POSEIDON_1_2                          # state width 3: tree nodes and the tag
    assert cs.poseidon(list(range(1, 11))) == POSEIDON_1_TO_10          # state width 11: the commitment
    assert cs.poseidon(["1", "0x2"]) == POSEIDON_1_2                    # decimal and 0x strings are accepted
    for bad in ([], [cs.FIELD], [-1], [True], list(range(17))):
        with pytest.raises(ValueError):
            cs.poseidon(bad)


def test_string_becomes_a_248_bit_field_element():
    from eth_utils import keccak
    from services import commitment_service as cs
    for text in ("did:patient:layan", DOCTOR, "did:key:z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK", "Ünïcode"):
        assert cs.to_field(text) == int.from_bytes(keccak(text=text)[1:], "big")       # keccak256 with the top byte cleared
        assert 0 < cs.to_field(text) < 2 ** 248 < cs.FIELD
    assert cs.to_field("did:parent:A") != cs.to_field("did:parent:B")
    for bad in ("", None, 5):
        with pytest.raises(ValueError):
            cs.to_field(bad)


def test_policy_terms_have_the_codes_of_the_specification():
    from services import commitment_service as cs
    assert cs.role_code("doctor") == 1
    assert [cs.purpose_code(p) for p in ("Treatment", "Research", "Emergency")] == [1, 2, 3]
    assert cs.context_code("AU") == 0x4155 and cs.context_code("") == 0 and cs.context_code(None) == 0
    assert [cs.scope_mask([m]) for m in ("Observation", "Medication", "Condition", "Procedure")] == [1, 2, 4, 8]
    assert cs.scope_mask(["Procedure", "Observation", "Observation"]) == 9 and cs.scope_mask([]) == 0
    assert cs.scope_modules(6) == ["Medication", "Condition"]
    for encode, bad in ((cs.role_code, "nurse"), (cs.purpose_code, "Marketing"), (cs.context_code, "AUS"),
                        (cs.context_code, "é1"), (cs.scope_mask, ["Imaging"]), (cs.scope_mask, 16)):
        with pytest.raises(ValueError):
            encode(bad)


def test_window_is_taken_in_whole_seconds_and_never_grows():
    from services import commitment_service as cs
    assert cs.unix_seconds(_iso(T0)) == T0 and cs.unix_seconds(datetime.fromtimestamp(T0)) == T0 and cs.unix_seconds(T0) == T0
    assert cs.unix_seconds(T0 + 0.25, round_up=True) == T0 + 1 and cs.unix_seconds(T0 + 0.75) == T0
    consent = _consent(start_date=_iso(T0 + 0.5), expiry_date=_iso(T0 + DAY + 0.5))
    opening = cs.compute_commitment(consent, blinding=BLINDING)[1]
    assert (int(opening["notBefore"]), int(opening["expiry"])) == (T0 + 1, T0 + DAY)
    with pytest.raises(ValueError):
        cs.unix_seconds(-1)


# ---- commitment ----------------------------------------------------------------------------------

def test_commitment_is_poseidon_of_the_ten_opening_values():
    from services import commitment_service as cs
    consent = _consent()
    commitment, opening = cs.compute_commitment(consent, blinding=BLINDING)
    assert list(opening) == list(cs.OPENING_FIELDS) and all(isinstance(v, str) and v.isdigit() for v in opening.values())
    assert opening == {"patient": str(cs.to_field("did:patient:layan")),
                       "guardiansDigest": str(cs.guardians_digest(["did:parent:A", "did:parent:B"], 2)),
                       "requester": str(cs.to_field(DOCTOR)), "role": "1", "purpose": "1", "context": str(0x4155),
                       "scopeMask": "3", "notBefore": str(T0), "expiry": str(T0 + 30 * DAY), "blinding": str(BLINDING)}
    assert commitment.startswith("0x") and len(commitment) == 66 and 0 < int(commitment, 16) < cs.FIELD
    assert int(commitment, 16) == cs.poseidon([int(opening[name]) for name in cs.OPENING_FIELDS]) == cs.open_commitment(opening)
    assert cs.compute_commitment(consent, blinding=BLINDING) == (commitment, opening)        # same blinding, same commitment
    assert consent.commitment is None and consent.commitment_opening is None               # compute does not change the consent


def test_commitment_is_hiding_through_a_fresh_blinding_value():
    from services import commitment_service as cs
    consent = _consent()
    first, second = cs.compute_commitment(consent), cs.compute_commitment(consent)
    assert first[0] != second[0] and first[1]["blinding"] != second[1]["blinding"]            # same consent, unlinkable commitments
    assert {k: v for k, v in first[1].items() if k != "blinding"} == {k: v for k, v in second[1].items() if k != "blinding"}
    assert 0 <= int(first[1]["blinding"]) < 2 ** 248
    assert cs.verify_opening(*first) and cs.verify_opening(*second) and not cs.verify_opening(first[0], second[1])
    with pytest.raises(ValueError):
        cs.compute_commitment(consent, blinding=2 ** 248)


def test_commitment_binds_every_committed_field():
    from services import commitment_service as cs
    base = cs.compute_commitment(_consent(), blinding=BLINDING)[0]
    changed = [dict(patient_did="did:patient:other"), dict(guardian_dids=["did:parent:A", "did:parent:C"]),
               dict(guardian_dids=["did:parent:A", "did:parent:B", "did:parent:C"]), dict(threshold=1),
               dict(requester_did="did:hospital:002"), dict(purpose="Research"), dict(jurisdiction="US"),
               dict(scope=["Observation"]), dict(start_date=_iso(T0 + 1)), dict(expiry_date=_iso(T0 + 30 * DAY + 1))]
    seen = {base}
    for change in changed:
        seen.add(cs.compute_commitment(_consent(**change), blinding=BLINDING)[0])
    seen.add(cs.compute_commitment(_consent(), blinding=BLINDING + 1)[0])
    seen.add(cs.compute_commitment(_consent(), blinding=BLINDING, role=2)[0])
    assert len(seen) == len(changed) + 3                                                     # every change gives another commitment
    # an opening with one value changed no longer opens the commitment
    opening = cs.compute_commitment(_consent(), blinding=BLINDING)[1]
    for name in cs.OPENING_FIELDS:
        forged = dict(opening, **{name: str(int(opening[name]) + 1)})
        assert not cs.verify_opening(base, forged)
    assert not cs.verify_opening(base, {k: v for k, v in opening.items() if k != "blinding"})
    assert not cs.verify_opening(base, None)


def test_guardians_digest_folds_the_sorted_guardians_and_the_threshold():
    from services import commitment_service as cs
    a, b, c = sorted(cs.to_field(d) for d in ("did:parent:A", "did:parent:B", "did:parent:C"))
    assert cs.guardians_digest(["did:parent:A"], 1) == cs.poseidon([cs.to_field("did:parent:A"), 1])
    assert cs.guardians_digest(["did:parent:A", "did:parent:B", "did:parent:C"], 2) == cs.poseidon([cs.poseidon([cs.poseidon([a, b]), c]), 2])
    assert cs.guardians_digest(["did:parent:C", "did:parent:A", "did:parent:B"], 2) == cs.guardians_digest(["did:parent:A", "did:parent:B", "did:parent:C"], 2)
    assert cs.guardians_digest(["did:parent:A", "did:parent:B"], 1) != cs.guardians_digest(["did:parent:A", "did:parent:B"], 2)
    for guardians, threshold in (([], 1), (["did:parent:A", "did:parent:A"], 1), (["did:parent:A"], 0), (["did:parent:A"], 2)):
        with pytest.raises(ValueError):
            cs.guardians_digest(guardians, threshold)


def test_commit_consent_keeps_commitment_and_opening_with_the_record():
    from services import commitment_service as cs
    consent = _consent()
    commitment, opening = cs.commit_consent(consent, blinding=BLINDING)
    assert (consent.commitment, consent.commitment_opening) == (commitment, opening)
    assert cs.verify_opening(consent.commitment, consent.commitment_opening) and cs.opening_matches_consent(consent, opening)
    consent.expiry_date = _iso(T0 + 365 * DAY)                           # the record is changed after the commitment
    assert not cs.opening_matches_consent(consent, opening)


# ---- request tag ---------------------------------------------------------------------------------

def test_request_tag_opens_to_its_requester_and_two_tags_are_unlinkable():
    from services import commitment_service as cs
    tag, nonce = cs.request_tag(DOCTOR, NONCE)
    assert nonce == NONCE and tag == cs.poseidon([cs.to_field(DOCTOR), NONCE])
    assert cs.open_tag(tag, DOCTOR, NONCE) and cs.open_tag(str(tag), DOCTOR, str(NONCE))        # the auditor with the ledger
    assert not cs.open_tag(tag, "did:hospital:002", NONCE) and not cs.open_tag(tag, DOCTOR, NONCE + 1)
    first, second = cs.request_tag(DOCTOR), cs.request_tag(DOCTOR)                              # fresh nonce for each request
    assert first[0] != second[0] and first[1] != second[1] and 0 <= first[1] < 2 ** 248
    assert cs.open_tag(first[0], DOCTOR, first[1]) and cs.open_tag(second[0], DOCTOR, second[1])


# ---- the two trees -------------------------------------------------------------------------------

def test_empty_trees_have_the_root_of_the_contract():
    from services import commitment_service as cs, merkle_service as ms
    zeros = ms.empty_roots()
    assert len(zeros) == 17 and zeros[0] == 0 and zeros[1] == cs.poseidon([0, 0]) and zeros[16] == EMPTY_ROOT_16
    assert all(zeros[h + 1] == cs.poseidon([zeros[h], zeros[h]]) for h in range(16))
    assert ms.ConsentTree().root == ms.RevocationTree().root == ms.MerkleTree().root == EMPTY_ROOT_16
    assert ms.ConsentTree().capacity == 2 ** 16 and ms.ConsentTree().count == 0


def test_consent_tree_gives_every_issued_commitment_a_path_to_the_root():
    from services import commitment_service as cs, merkle_service as ms
    tree = ms.ConsentTree()
    assert [tree.append(leaf) for leaf in (1, 2, 3)] == [0, 1, 2] and tree.root == ROOT_OF_1_2_3      # value of circomlibjs
    leaves = [cs.poseidon([5, i]) for i in range(11)]
    tree = ms.ConsentTree()
    roots = set()
    for i, leaf in enumerate(leaves):
        assert tree.append(leaf) == i and tree.count == i + 1
        roots.add(tree.root)
    assert len(roots) == len(leaves)                                      # every mint changes the root
    assert tree.commitments() == leaves
    for i, leaf in enumerate(leaves):
        path = tree.path(i)
        assert tree.index_of(leaf) == i == path["index"] and path["leaf"] == leaf and len(path["siblings"]) == 16
        assert path["bits"] == [(i >> h) & 1 for h in range(16)] and path["root"] == tree.root
        assert ms.root_from_path(leaf, i, path["siblings"]) == tree.root
        assert ms.root_from_path(leaf + 1, i, path["siblings"]) != tree.root          # another leaf
        assert ms.root_from_path(leaf, i ^ 1, path["siblings"]) != tree.root          # another place
    assert tree.index_of(12345) is None and tree.index_of("not a number") is None
    assert tree.index_of(hex(leaves[4])) == 4 and tree.index_of(str(leaves[4])) == 4
    assert ms.root_from_path(0, 11, tree.path(11)["siblings"]) == tree.root           # the next free leaf is empty
    for bad in (leaves[0], 0, cs.FIELD):                                               # issued twice, empty, outside the field
        with pytest.raises(ValueError):
            tree.append(bad)
    with pytest.raises(IndexError):
        tree.path(2 ** 16)


def test_consent_tree_keeps_the_current_root_and_the_last_eight():
    from services import merkle_service as ms
    tree = ms.ConsentTree()
    history = [tree.root]
    for leaf in range(1, 13):
        tree.append(leaf)
        history.append(tree.root)
    assert tree.recent_roots() == history[::-1][:9] and tree.recent_roots()[0] == tree.root
    assert all(tree.is_known_root(root) for root in history[-9:])        # a mint during proving does not void a proof
    assert not any(tree.is_known_root(root) for root in history[:-9])    # the ninth root back is no longer accepted
    assert tree.is_known_root(str(tree.root)) and not tree.is_known_root(0)
    # a tree loaded from the list of issued commitments is the tree of the same mints one by one
    loaded = ms.ConsentTree(list(range(1, 13)))
    assert loaded.root == tree.root and loaded.recent_roots() == tree.recent_roots() and loaded.count == 12
    assert loaded.path(5) == tree.path(5) and loaded.index_of(12) == 11
    with pytest.raises(ValueError):
        ms.ConsentTree([5, 6, 5] + list(range(10, 30)))


def test_small_tree_fills_up_and_refuses_another_consent():
    from services import merkle_service as ms
    tree = ms.ConsentTree(depth=2)
    for leaf in (1, 2, 3, 4):
        tree.append(leaf)
    assert ms.root_from_path(4, 3, tree.path(3)["siblings"]) == tree.root and len(tree.path(3)["siblings"]) == 2
    with pytest.raises(ValueError):
        tree.append(5)


def test_revocation_tree_opens_to_zero_until_the_consent_is_revoked():
    from services import merkle_service as ms
    tree = ms.RevocationTree()
    before = tree.root
    path = tree.path(3)
    assert path["leaf"] == 0 and ms.root_from_path(0, 3, path["siblings"]) == before and not tree.is_revoked(3)
    after = tree.revoke(3)
    assert after == tree.root != before and tree.is_revoked(3) and tree.leaf(3) == 1 and tree.revoked() == [3]
    path = tree.path(3)
    assert ms.root_from_path(1, 3, path["siblings"]) == after             # the leaf now opens to 1
    assert ms.root_from_path(0, 3, path["siblings"]) != after             # and no longer to 0
    for other in (0, 2, 4, 65535):                                        # the other consents still open to 0
        assert ms.root_from_path(0, other, tree.path(other)["siblings"]) == after and not tree.is_revoked(other)
    assert tree.revoke(3) == after                                        # revoking again changes nothing
    assert not any(hasattr(tree, name) for name in ("unrevoke", "restore", "clear", "set_leaf"))     # no way back
    assert ms.RevocationTree([3]).root == after and ms.RevocationTree([5, 3]).root == ms.RevocationTree([3, 5]).root


def test_off_chain_trees_follow_the_vectors_of_the_consent_contract():
    """The contract package stores a sequence of mints and revocations with the roots after each step. When that
    file is present, the off-chain trees must reach the same roots."""
    from services import merkle_service as ms
    vectors = os.path.join(ROOT, "blockchain", "abi", "ConsentTreeVectors.json")
    if not os.path.exists(vectors):
        pytest.skip("blockchain/abi/ConsentTreeVectors.json is not in this checkout")
    with open(vectors) as f:
        data = json.load(f)
    steps = data.get("sequence") or []
    if "zeros" not in data or not steps or not all({"op", "tokenId", "consentRoot", "revocationRoot"} <= set(step) for step in steps):
        pytest.skip("the vector file has another layout")
    assert [str(z) for z in ms.empty_roots(int(data.get("depth", 16)))] == data["zeros"]
    consents, revocations = ms.ConsentTree(), ms.RevocationTree()
    for step in steps:
        if step["op"] == "mint":
            assert consents.append(step["commitment"]) == step["tokenId"] - 1          # token n holds leaf n - 1
        else:
            revocations.revoke(step["tokenId"] - 1)
        assert (str(consents.root), str(revocations.root)) == (step["consentRoot"], step["revocationRoot"])


# ---- Python against circomlibjs -------------------------------------------------------------------

def test_python_values_equal_the_circomlibjs_values():
    """The Python services, the JavaScript helper and therefore the circuit and the Poseidon contract agree."""
    if not _js_available():
        pytest.skip("zk/node_modules with circomlibjs is not installed")
    from services import commitment_service as cs, merkle_service as ms
    inputs = [[0, 0], [1, 2], [cs.FIELD - 1, cs.FIELD - 1], [BLINDING, NONCE], list(range(1, 11)),
              [cs.FIELD - 1 - i for i in range(10)], [5], [1, 2, 3], list(range(1, 17))]
    assert _js({"op": "hash", "inputs": [[str(x) for x in xs] for xs in inputs]}) == [str(cs.poseidon(xs)) for xs in inputs]
    texts = ["did:patient:layan", DOCTOR, "did:parent:A", "Ünïcode", "x"]
    assert _js({"op": "field", "texts": texts}) == [str(cs.to_field(text)) for text in texts]
    guardians = ["did:parent:C", "did:parent:A", "did:parent:B"]
    assert _js({"op": "guardians", "dids": guardians, "threshold": 2}) == str(cs.guardians_digest(guardians, 2))
    commitment, opening = cs.compute_commitment(_consent(), blinding=BLINDING)
    assert _js({"op": "commitment", "opening": opening}) == str(int(commitment, 16))
    assert _js({"op": "tag", "requester": DOCTOR, "nonce": str(NONCE)}) == str(cs.request_tag(DOCTOR, NONCE)[0])
    leaves = [cs.poseidon([9, i]) for i in range(5)]
    assert _js({"op": "root", "depth": 16, "leaves": [str(x) for x in leaves]}) == str(ms.ConsentTree(leaves).root)
    assert _js({"op": "root", "depth": 16, "leaves": []}) == str(EMPTY_ROOT_16)


# ---- Algorithm 7.1: the predicate set and the two input vectors -------------------------------------

def test_statement_assigns_the_consent_to_the_witness_and_keeps_seven_public_inputs():
    from services import commitment_service as cs, zk_decision_service as zd
    consent, tree, revocations = _issued()
    reads = []

    def read_roots():                                                    # stands for the read from the consent contract
        reads.append(1)
        return tree.root, revocations.root

    s = zd.build_statement(consent, read_roots, requester_did=DOCTOR, role="doctor", purpose="Treatment", context="AU",
                           scope=["Observation"], now_ts=T0 + 100, nonce=NONCE)
    assert len(reads) == 1
    assert list(s["public"]) == ["t", "role", "purpose", "context", "tag", "consentRoot", "revocationRoot"] == list(zd.PUBLIC_SIGNALS)
    assert s["publicSignals"] == [str(T0 + 100), "1", "1", str(0x4155), str(cs.request_tag(DOCTOR, NONCE)[0]), str(tree.root), str(revocations.root)]
    opening = consent.commitment_opening
    assert s["private"] == {"patient": opening["patient"], "guardiansDigest": opening["guardiansDigest"], "requester": opening["requester"],
                            "committedRole": "1", "committedPurpose": "1", "committedContext": str(0x4155), "scopeMask": "3",
                            "notBefore": str(T0), "expiry": str(T0 + 30 * DAY), "blinding": str(BLINDING),
                            "requestedScope": "1", "nonce": str(NONCE)}
    assert s["predicates"] == dict.fromkeys(("OPENING", "WINDOW", "ROLE", "PURPOSE", "CONTEXT", "SCOPE", "REQUESTER"), True)
    assert s["audit"] == {"requester_did": DOCTOR, "nonce": str(NONCE), "tag": s["public"]["tag"]}
    # nothing that identifies the consent, a party, the scope or the window is among the public inputs
    hidden = {opening[name] for name in ("patient", "guardiansDigest", "requester", "scopeMask", "notBefore", "expiry", "blinding")}
    hidden |= {str(int(consent.commitment, 16)), str(NONCE), str(tree.index_of(consent.commitment))}
    assert not hidden & set(s["publicSignals"])
    # a request that names nothing takes the terms of the consent, and a fresh nonce is drawn for every request
    first, second = (zd.build_statement(consent, zd.tree_roots(tree, revocations), now_ts=T0 + 100) for _ in range(2))
    assert first["public"]["tag"] != second["public"]["tag"] and first["private"]["requestedScope"] == "3"
    assert {k: v for k, v in first["public"].items() if k != "tag"} == {k: v for k, v in second["public"].items() if k != "tag"}
    assert cs.open_tag(first["public"]["tag"], DOCTOR, first["audit"]["nonce"])
    # the roots may arrive from the contract client as numbers or as decimal or 0x strings
    as_text = zd.build_statement(consent, lambda: (hex(tree.root), str(revocations.root)), now_ts=T0 + 100)
    assert as_text["publicSignals"][5:] == [str(tree.root), str(revocations.root)]
    with pytest.raises(ValueError):
        zd.build_statement(consent, lambda: (cs.FIELD, 0), now_ts=T0 + 100)
    # a reading that carries the time of its block gives the proof that time, unless the caller gives one
    reading = {"consent_root": tree.root, "revocation_root": revocations.root, "block_timestamp": T0 + 777, "block_number": 9}
    assert zd.build_statement(consent, lambda: reading)["public"]["t"] == str(T0 + 777)
    assert zd.build_statement(consent, lambda: reading, now_ts=T0 + 5)["public"]["t"] == str(T0 + 5)
    assert zd.build_statement(consent, lambda: reading)["publicSignals"][5:] == [str(tree.root), str(revocations.root)]


def test_witness_holds_both_merkle_paths_at_the_leaf_of_the_consent():
    from services import merkle_service as ms, zk_decision_service as zd
    consent, tree, revocations = _issued()
    s = zd.build_statement(consent, zd.tree_roots(tree, revocations), scope=["Medication"], now_ts=T0 + 100, nonce=NONCE)
    inputs, predicates = zd.assemble_witness(s, tree, revocations)
    assert all(predicates[name] for name in zd.PREDICATES) and list(predicates) == list(zd.PREDICATES)
    assert inputs["leafIndex"] == "3" and len(inputs["consentPath"]) == len(inputs["revocationPath"]) == 16
    assert ms.root_from_path(int(consent.commitment, 16), 3, inputs["consentPath"]) == int(inputs["consentRoot"])
    assert ms.root_from_path(0, 3, inputs["revocationPath"]) == int(inputs["revocationRoot"])
    assert set(inputs) == set(zd.PUBLIC_SIGNALS) | set(s["private"]) | {"leafIndex", "consentPath", "revocationPath"}
    # roots read from a chain that the off-chain trees do not follow: the paths do not lead to them
    stale = zd.build_statement(consent, lambda: (tree.root + 1, revocations.root + 1), now_ts=T0 + 100, nonce=NONCE)
    predicates = zd.assemble_witness(stale, tree, revocations)[1]
    assert (predicates["ISSUED"], predicates["NOT_REVOKED"]) == (False, False)
    with pytest.raises(ValueError):
        zd.assemble_witness(s, tree, ms.RevocationTree(depth=8))


# The requests that must not be provable: the change to the valid request, the predicate that fails, and the
# constraint of zk/halah_decision.circom that refuses the witness.
REFUSED = [
    ("expired consent", dict(now_ts=T0 + 30 * DAY + 1), "WINDOW", "notExpired.out === 1"),
    ("request before the window", dict(now_ts=T0 - 1), "WINDOW", "started.out === 1"),
    ("scope outside the consent", dict(scope=["Observation", "Condition"]), "SCOPE", "want.out[i] * (1 - have.out[i]) === 0"),
    ("empty scope", dict(scope=[]), "SCOPE", "empty.out === 0"),
    ("different purpose", dict(purpose="Research"), "PURPOSE", "purpose === committedPurpose"),
    ("different role", dict(role=2), "ROLE", "role === committedRole"),
    ("different context", dict(context="US"), "CONTEXT", "context === committedContext"),
    ("another requester", dict(requester_did="did:hospital:002"), "REQUESTER", "tag === opened.out"),
]


def _request(**changes):
    request = dict(requester_did=DOCTOR, role="doctor", purpose="Treatment", context="AU", scope=["Observation"],
                   now_ts=T0 + 100, nonce=NONCE)
    request.update(changes)
    return request


@pytest.mark.parametrize("case,change,predicate,constraint", REFUSED, ids=[r[0] for r in REFUSED])
def test_request_outside_the_consent_is_refused_before_the_prover(case, change, predicate, constraint):
    from services import zk_decision_service as zd
    consent, tree, revocations = _issued()
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.generate_decision_proof(consent, tree, revocations, **_request(**change))
    assert refused.value.failed == [predicate] and isinstance(refused.value, RuntimeError)


def test_unknown_policy_terms_and_modules_are_refused():
    from services import zk_decision_service as zd
    consent, tree, revocations = _issued()
    for change, predicate in ((dict(role="nurse"), "ROLE"), (dict(purpose="Marketing"), "PURPOSE"),
                              (dict(context="Australia"), "CONTEXT"), (dict(scope=["Imaging"]), "SCOPE")):
        with pytest.raises(zd.DecisionProofError) as refused:
            zd.generate_decision_proof(consent, tree, revocations, **_request(**change))
        assert refused.value.failed == [predicate]


def test_consent_without_a_context_permits_every_context():
    from services import zk_decision_service as zd
    consent, tree, revocations = _issued(_consent(jurisdiction=""))
    s = zd.build_statement(consent, zd.tree_roots(tree, revocations), **_request(context="US"))
    assert s["public"]["context"] == "0" and s["predicates"]["CONTEXT"] is True


def test_revoked_or_never_issued_consent_is_refused_before_the_prover():
    from services import merkle_service as ms, zk_decision_service as zd
    consent, tree, revocations = _issued()
    revocations.revoke(tree.index_of(consent.commitment))
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.generate_decision_proof(consent, tree, revocations, **_request())
    assert refused.value.failed == ["NOT_REVOKED"]
    never_issued, _, _ = _issued(_consent("zk-d-2", patient_did="did:patient:other"))
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.generate_decision_proof(never_issued, tree, ms.RevocationTree(), **_request())
    assert refused.value.failed == ["ISSUED"]


def test_changed_or_deleted_opening_is_refused():
    from services import zk_decision_service as zd
    consent, tree, revocations = _issued()
    consent.expiry_date = _iso(T0 + 365 * DAY)                           # the record no longer says what was committed
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.generate_decision_proof(consent, tree, revocations, **_request())
    assert refused.value.failed == ["OPENING"]
    consent, tree, revocations = _issued()
    consent.commitment_opening["scopeMask"] = "15"                       # an opening that claims a wider scope
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.generate_decision_proof(consent, tree, revocations, **_request(scope=["Procedure"]))
    assert refused.value.failed == ["OPENING", "ISSUED"]
    for broken in (None, {}, dict(_issued()[0].commitment_opening, blinding="not a number")):
        consent, tree, revocations = _issued()
        consent.commitment_opening = broken                              # deleted at revocation (Algorithm 6.4), or unusable
        with pytest.raises(zd.DecisionProofError) as refused:
            zd.generate_decision_proof(consent, tree, revocations, **_request())
        assert refused.value.failed == ["OPENING"]


def test_without_the_built_circuit_there_is_no_proof_and_no_placeholder(monkeypatch):
    from services import zk_decision_service as zd
    monkeypatch.setattr(zd, "decision_available", lambda depth=16: False)
    consent, tree, revocations = _issued()
    with pytest.raises(zd.ProofUnavailable):
        zd.generate_decision_proof(consent, tree, revocations, **_request())
    fake = {"mode": "groth16", "circuit": "halah_decision", "proof": {"pi_a": []}, "publicSignals": ["0"] * 7}
    assert zd.verify_decision_proof(fake) is False


def test_verification_refuses_what_is_not_a_decision_proof():
    from services import zk_decision_service as zd
    for bad in (None, "", "a" * 64, {}, {"mode": "placeholder", "digest": "ab"}, {"mode": "groth16"},
                {"mode": "groth16", "proof": {}, "publicSignals": ["1"] * 6},
                {"mode": "groth16", "proof": {}, "publicSignals": ["1"] * 7, "circuit": "../consent_validity"}):
        assert zd.verify_decision_proof(bad) is False


# ---- Algorithm 7.2 with the built circuit ----------------------------------------------------------

def test_circuit_source_constrains_every_assignment_and_declares_the_seven_public_inputs():
    """Every signal of the circuit is assigned with <== and every check is written with ===, so whatever the
    witness generator refuses is a constraint of the proof as well. (The library templates are not judged here.)"""
    with open(os.path.join(ZK, "halah_decision.circom")) as f:
        source = f.read()
    code = source.split("*/", 1)[1]                                      # the text after the header comment
    assert "<--" not in code and "-->" not in code
    assert "component main {public [t, role, purpose, context, tag, consentRoot, revocationRoot]} = HalahDecision(16, 4);" in code
    declared = [line.split()[2].rstrip(";") for line in code.splitlines() if line.strip().startswith("signal input")]
    assert declared[3:10] == ["t", "role", "purpose", "context", "tag", "consentRoot", "revocationRoot"]      # after MerkleRoot's three
    assert "signal output" not in code.split("template HalahDecision", 1)[1]        # an output would become a public signal


def test_built_keys_have_seven_public_inputs():
    _need_circuit()
    with open(os.path.join(ZK, "build", "halah_decision_verification_key.json")) as f:
        key = json.load(f)
    assert (key["protocol"], key["curve"], key["nPublic"], len(key["IC"])) == ("groth16", "bn128", 7, 8)
    exported = os.path.join(ROOT, "contracts", "HalahDecisionVerifier.sol")
    if os.path.exists(exported):
        with open(exported) as f:
            text = f.read()
        assert "contract Groth16Verifier" in text and "uint[7] calldata _pubSignals" in text

@pytest.fixture(scope="module")
def proved():
    """One valid request, proved once for the tests below: (service, consent, trees, proof)."""
    zd = _need_circuit()
    consent, tree, revocations = _issued()
    proof = zd.generate_decision_proof(consent, tree, revocations, **_request())
    return zd, consent, tree, revocations, proof


def test_valid_request_proves_and_verifies(proved):
    from services import commitment_service as cs
    zd, consent, tree, revocations, proof = proved
    assert proof["mode"] == "groth16" and proof["circuit"] == "halah_decision" and "Groth16" in proof["scheme"]
    assert proof["tag"] == proof["public"]["tag"] == proof["publicSignals"][4]
    assert zd.verify_decision_proof(proof) is True
    assert proof["publicSignals"] == [str(T0 + 100), "1", "1", str(0x4155), str(cs.request_tag(DOCTOR, NONCE)[0]),
                                      str(tree.root), str(revocations.root)]
    assert zd.public_inputs(proof) == {"t": T0 + 100, "role": 1, "purpose": 1, "context": 0x4155, "tag": cs.request_tag(DOCTOR, NONCE)[0],
                                       "consentRoot": tree.root, "revocationRoot": revocations.root}
    assert set(proof["proof"]) >= {"pi_a", "pi_b", "pi_c"} and proof["proof"]["protocol"] == "groth16"
    # the auditor opens the tag with the nonce of the audit ledger, and nobody else's identifier opens it
    assert cs.open_tag(proof["public"]["tag"], proof["audit"]["requester_did"], proof["audit"]["nonce"])
    assert not cs.open_tag(proof["public"]["tag"], "did:hospital:002", proof["audit"]["nonce"])
    # what may be published carries no consent data
    published = json.dumps({"proof": proof["proof"], "publicSignals": proof["publicSignals"]})
    opening = consent.commitment_opening
    for secret in (opening["patient"], opening["guardiansDigest"], opening["requester"], opening["blinding"],
                   str(int(consent.commitment, 16)), str(NONCE), "did:"):
        assert secret not in published


def test_every_scope_inside_the_consent_and_both_ends_of_the_window_prove(proved):
    zd, consent, tree, revocations, _ = proved
    for change in (dict(scope=["Medication"], now_ts=T0), dict(scope=["Observation", "Medication"], now_ts=T0 + 30 * DAY)):
        proof = zd.generate_decision_proof(consent, tree, revocations, **_request(nonce=None, **change))
        assert zd.verify_decision_proof(proof) is True and proof["public"]["t"] == str(change["now_ts"])


def test_two_proofs_for_the_same_clinician_carry_unlinkable_tags(proved):
    zd, consent, tree, revocations, first = proved
    second = zd.generate_decision_proof(consent, tree, revocations, **_request(nonce=None))
    assert zd.verify_decision_proof(second) is True
    assert second["public"]["tag"] != first["public"]["tag"] and second["proof"] != first["proof"]
    assert {k: v for k, v in second["public"].items() if k != "tag"} == {k: v for k, v in first["public"].items() if k != "tag"}


def _circuit_line(error):
    """The source line of zk/halah_decision.circom that the witness generator names in its refusal."""
    number = int(error.detail.rsplit("line:", 1)[1].strip())
    with open(os.path.join(ZK, "halah_decision.circom")) as f:
        return f.read().splitlines()[number - 1].strip()


@pytest.mark.parametrize("case,change,predicate,constraint", REFUSED, ids=[r[0] for r in REFUSED])
def test_circuit_gives_no_proof_for_a_request_outside_the_consent(case, change, predicate, constraint):
    """The honest prover runs on the witness as it is, and the circuit refuses it at the constraint of its family."""
    zd = _need_circuit()
    consent, tree, revocations = _issued()
    statement = zd.build_statement(consent, zd.tree_roots(tree, revocations), **_request(**change))
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.prove_decision(statement, tree, revocations, check=False)
    assert refused.value.failed == [predicate] and "PROVE_FAILED" in refused.value.detail
    assert _circuit_line(refused.value) == constraint + ";"


def test_circuit_gives_no_proof_for_a_revoked_consent(proved):
    from services import merkle_service as ms
    zd, consent, tree, _, earlier = proved
    revocations = ms.RevocationTree([1])                                 # the revocation tree of the valid request
    before = revocations.root
    revocations.revoke(tree.index_of(consent.commitment))
    statement = zd.build_statement(consent, zd.tree_roots(tree, revocations), **_request())
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.prove_decision(statement, tree, revocations, check=False)
    assert refused.value.failed == ["NOT_REVOKED"] and _circuit_line(refused.value) == "revocationRoot === live.root;"
    # The proof made before the revocation stays a valid proof of the earlier state. Its public revocation root is
    # the one from before the revocation, which the verifier contract refuses because it is no longer current.
    assert zd.verify_decision_proof(earlier) is True
    assert zd.public_inputs(earlier)["revocationRoot"] == before != revocations.root


def test_circuit_gives_no_proof_for_a_consent_that_was_never_issued():
    zd = _need_circuit()
    _, tree, revocations = _issued()
    forged = _issued(_consent("zk-d-3", scope=["Observation", "Medication", "Condition", "Procedure"]))[0]    # committed, never minted
    statement = zd.build_statement(forged, zd.tree_roots(tree, revocations), **_request(scope=["Procedure"]))
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.prove_decision(statement, tree, revocations, check=False)
    assert refused.value.failed == ["ISSUED"] and _circuit_line(refused.value) == "consentRoot === issued.root;"


def test_circuit_gives_no_proof_for_an_opening_with_a_widened_scope():
    zd = _need_circuit()
    consent, tree, revocations = _issued()
    consent.commitment_opening["scopeMask"] = "15"                       # the opening no longer hashes to the leaf
    statement = zd.build_statement(consent, zd.tree_roots(tree, revocations), **_request(scope=["Procedure"]))
    with pytest.raises(zd.DecisionProofError) as refused:
        zd.prove_decision(statement, tree, revocations, check=False)
    assert _circuit_line(refused.value) == "consentRoot === issued.root;"


def test_tampered_public_input_or_proof_is_rejected(proved):
    from services import commitment_service as cs
    zd, _, _, _, proof = proved
    for position, name in enumerate(zd.PUBLIC_SIGNALS):                  # each of the seven public inputs
        bad = copy.deepcopy(proof)
        bad["publicSignals"][position] = str(int(bad["publicSignals"][position]) + 1)
        assert zd.verify_decision_proof(bad) is False, name
    alias = copy.deepcopy(proof)
    alias["publicSignals"][4] = str(int(alias["publicSignals"][4]) + cs.FIELD)       # the same tag written outside the field
    assert zd.verify_decision_proof(alias) is False
    short = copy.deepcopy(proof)
    short["publicSignals"] = short["publicSignals"][:6]
    assert zd.verify_decision_proof(short) is False
    forged = copy.deepcopy(proof)
    forged["proof"]["pi_a"][0] = str(int(forged["proof"]["pi_a"][0]) + 1)
    assert zd.verify_decision_proof(forged) is False
    swapped = copy.deepcopy(proof)
    swapped["proof"]["pi_c"] = proof["proof"]["pi_a"]
    assert zd.verify_decision_proof(swapped) is False
    assert zd.verify_decision_proof(proof) is True                       # the untouched proof still verifies


def test_proof_survives_later_mints_through_the_recent_roots(proved):
    zd, _, tree, _, proof = proved
    later = copy.deepcopy(tree)
    root = zd.public_inputs(proof)["consentRoot"]
    for leaf in range(100, 108):
        later.append(leaf)
    assert later.is_known_root(root) and later.root != root              # eight mints later the root is still accepted
    later.append(108)
    assert not later.is_known_root(root)                                 # the ninth mint retires it


def test_exported_solidity_verifier_accepts_the_proof_on_the_in_memory_chain(proved):
    """contracts/HalahDecisionVerifier.sol, compiled with solc and deployed on the in-memory chain, accepts the
    proof of the valid request and rejects it for a changed public input."""
    zd, _, _, _, proof = proved
    source = os.path.join(ROOT, "contracts", "HalahDecisionVerifier.sol")
    if not os.path.exists(os.path.join(ZK, "node_modules", "solc", "package.json")) or not os.path.exists(source):
        pytest.skip("solc or the exported verifier is not present")
    pytest.importorskip("eth_tester")
    with open(os.path.join(ZK, "build", "halah_decision_verification_key.json")) as f:
        key = json.load(f)
    with open(source) as f:
        text = f.read()
    if key["vk_alpha_1"][0] not in text or key["IC"][7][0] not in text:
        pytest.skip("the verifier contract was exported from another setup: run zk/build_decision.sh")
    script = ('const solc=require("solc"),fs=require("fs");const out=JSON.parse(solc.compile(JSON.stringify({language:"Solidity",'
              'sources:{"V.sol":{content:fs.readFileSync(process.argv[1],"utf8")}},settings:{optimizer:{enabled:true,runs:200},'
              'outputSelection:{"*":{"*":["abi","evm.bytecode.object"]}}}})));const c=out.contracts["V.sol"].Groth16Verifier;'
              'console.log(JSON.stringify({abi:c.abi,bytecode:"0x"+c.evm.bytecode.object}))')
    r = subprocess.run(["node", "-e", script, source], capture_output=True, text=True, cwd=ZK, timeout=300)
    assert r.returncode == 0, r.stderr
    artefact = json.loads(r.stdout)
    from web3 import Web3
    from web3.providers.eth_tester import EthereumTesterProvider
    w3 = Web3(EthereumTesterProvider())
    sender = w3.eth.accounts[0]
    receipt = w3.eth.wait_for_transaction_receipt(
        w3.eth.contract(abi=artefact["abi"], bytecode=artefact["bytecode"]).constructor().transact({"from": sender}))
    verifier = w3.eth.contract(address=receipt["contractAddress"], abi=artefact["abi"])
    a, b, c, signals = zd.solidity_calldata(proof)
    assert len(signals) == 7 and verifier.functions.verifyProof(a, b, c, signals).call() is True
    for position in range(7):
        changed = list(signals)
        changed[position] += 1
        assert verifier.functions.verifyProof(a, b, c, changed).call() is False
    assert verifier.functions.verifyProof(c, b, a, signals).call() is False


def test_tree_of_another_depth_uses_the_circuit_built_for_that_depth():
    from services import commitment_service as cs, merkle_service as ms, zk_decision_service as zd
    assert zd.circuit_name() == zd.circuit_name(16) == "halah_decision" and zd.circuit_name(8) == "halah_decision_d8"
    if not zd.decision_available(8):
        pytest.skip("run DEPTH=8 bash zk/build_decision.sh")
    consent = _consent()
    cs.commit_consent(consent, blinding=BLINDING)
    tree, revocations = ms.ConsentTree([11, 12], depth=8), ms.RevocationTree(depth=8)
    tree.append(consent.commitment)
    proof = zd.generate_decision_proof(consent, tree, revocations, **_request())
    assert proof["circuit"] == "halah_decision_d8" and zd.verify_decision_proof(proof) is True
    assert zd.verify_decision_proof(dict(proof, circuit="halah_decision")) is False      # not a proof of the depth-16 circuit
