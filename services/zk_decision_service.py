'''
Zero-knowledge proof of the consent decision for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11

The Verification Module, off-chain side (Chapter 7). For one request it proves that the decision rule held,
without naming the consent, the patient, the guardians, the requester or the policy terms:

    a consent exists whose commitment is in the consent tree (it was issued), whose leaf of the
    revocation tree is 0 (it is not revoked), whose window holds the time t, whose policy permits the
    claimed role, purpose and context, whose scope covers the requested modules, and whose requester
    is the one behind the request tag.

Public inputs, in this order: t, role, purpose, context, tag, consentRoot, revocationRoot.
Everything else is the witness and stays on the server.

The proof does NOT establish that the guardian threshold was met, that the requester holds the credential
for the claimed role, or that the consent is not SUSPENDED. The server checks these off chain (Chapters 5
and 6) and the proof relies on those checks. The proof is evidence that the rule held, not a decision:
the Enforcement Module decides first, and Algorithm 6.5 releases data only when both agree. The privacy
is against the chain, the auditor and third parties. The server holds the witness and learns everything.

build_statement(consent, read_roots, ...)            Algorithm 7.1: the predicate set, the public inputs and
                                                     the private inputs of one request, with a fresh request tag
assemble_witness(statement, consent_tree, revocation_tree)
                                                     the circuit inputs with the two Merkle paths
prove_decision(statement, consent_tree, revocation_tree)
                                                     Algorithm 7.2: assemble the witness, run the prover,
                                                     return the proof and the public inputs
generate_decision_proof(consent, consent_tree, revocation_tree, ...)   Algorithms 7.1 and 7.2 in one call
verify_decision_proof(proof)                         local verification with the verification key
solidity_calldata(proof)                             (a, b, c, public signals) for the verifier contract

The circuit is zk/halah_decision.circom (Groth16 over BN254, circom and snarkjs). Build it once with
`bash zk/build_decision.sh`. Without the build no proof can be made: decision_available() is False,
prove_decision raises ProofUnavailable and verify_decision_proof returns False. There is no placeholder.
'''
import json
import os
import re
import shutil
import subprocess
import time

from services.commitment_service import (CONSENT_ROLE, OPENING_FIELDS, context_code, field_element,
                                         open_commitment, opening_matches_consent, purpose_code, request_tag,
                                         role_code, scope_mask, to_field, unix_seconds, verify_opening)
from services.merkle_service import TREE_DEPTH, root_from_path

ZK_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "zk")
_BUILD = os.path.join(ZK_DIR, "build")

# Public inputs of the decision proof, in the order the circuit and the verifier contract use.
PUBLIC_SIGNALS = ("t", "role", "purpose", "context", "tag", "consentRoot", "revocationRoot")
# The predicate set of the statement. The first seven are fixed by Algorithm 7.1, the last two by the
# Merkle paths that Algorithm 7.2 adds.
PREDICATES = ("OPENING", "WINDOW", "ROLE", "PURPOSE", "CONTEXT", "SCOPE", "REQUESTER", "ISSUED", "NOT_REVOKED")
SCHEME = "Groth16/BN254 (circom+snarkjs), decision circuit"

# Name of each opening value as a signal of the circuit.
_WITNESS_NAME = {"role": "committedRole", "purpose": "committedPurpose", "context": "committedContext"}


class DecisionProofError(RuntimeError):
    '''No proof was produced. `failed` lists the predicates of the statement that do not hold.'''

    def __init__(self, failed, detail=""):
        self.failed = list(failed)
        self.detail = detail
        message = "no proof: " + (", ".join(self.failed) if self.failed else "the prover refused the witness")
        super().__init__(message + ((" (" + detail + ")") if detail else ""))


class ProofUnavailable(RuntimeError):
    '''The circuit is not built on this machine, so no proof can be made or verified.'''


def circuit_name(depth=TREE_DEPTH):
    '''Name of the circuit build for a tree depth. The deployed depth is 16.'''
    return "halah_decision" if int(depth) == TREE_DEPTH else "halah_decision_d%d" % int(depth)


def decision_available(depth=TREE_DEPTH):
    '''True when Node and the built circuit of this tree depth are present.'''
    name = circuit_name(depth)
    return shutil.which("node") is not None and all(os.path.exists(os.path.join(_BUILD, part)) for part in (
        os.path.join(name + "_js", name + ".wasm"), name + ".zkey", name + "_verification_key.json"))


def _node(script, arg, name, timeout=120):
    r = subprocess.run(["node", os.path.join(ZK_DIR, script), arg, name], capture_output=True, text=True,
                       timeout=timeout, cwd=ZK_DIR)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or "node failed")
    return r.stdout.strip()


def _encoded(encode, value):
    '''(code, True) for a value the commitment has a code for, (0, False) for any other value.'''
    try:
        return encode(value), True
    except (TypeError, ValueError):
        return 0, False


def _roots(reading):
    '''(consent root, revocation root, block time or None) from what read_roots returned.'''
    if isinstance(reading, dict):
        return (field_element(reading["consent_root"]), field_element(reading["revocation_root"]),
                reading.get("block_timestamp"))
    consent_root, revocation_root = reading
    return field_element(consent_root), field_element(revocation_root), None


# ---- Algorithm 7.1: predicate set construction ---------------------------------------------------

def build_statement(consent, read_roots, requester_did=None, role=CONSENT_ROLE, purpose=None, context=None,
                    scope=None, now_ts=None, nonce=None):
    '''Algorithm 7.1. From one request and the consent, construct the predicate set and the two input
    vectors of the proof.

    read_roots()   returns the two roots as read from the consent contract at proof time: the pair
                   (consentRoot, revocationRoot), or a dict with consent_root and revocation_root and,
                   when it has one, the block_timestamp of the block they were read at.
                   The tests and offline tools pass the roots of the off-chain trees.
    requester_did, purpose, context, scope
                   the request. A value left as None is taken from the consent, as evaluate_allow does.
    role           the role the requester claims (the credential for it is checked off chain).
    now_ts         the time t of the request in Unix seconds. The verifier contract accepts t only if
                   it is not later than the block and at most 300 seconds older. Without now_ts the
                   block_timestamp of the roots is used, and the system clock when there is none.
    nonce          the random value of the request tag. Leave it as None: a fresh one is drawn.

    Each element of the consent goes to the witness, and only t, the claimed role, purpose and context,
    the request tag and the two roots are public. The result holds
      public, publicSignals   the public inputs by name and in order (decimal strings)
      private                 the opening of the commitment, the requested scope mask and the nonce
      predicates              which predicates of the statement hold for this request
      audit                   the requester and the nonce, for the audit ledger only: with them an
                              auditor opens the tag. They must never be published with the proof.
    '''
    requester_did = consent.requester_did if requester_did is None else requester_did
    purpose = consent.purpose if purpose is None else purpose
    context = (getattr(consent, "jurisdiction", "") or "") if context is None else context
    scope = consent.scope if scope is None else scope
    consent_root, revocation_root, block_time = _roots(read_roots())
    if now_ts is None:
        now_ts = time.time() if block_time is None else block_time
    t = unix_seconds(now_ts)

    role_n, role_known = _encoded(role_code, role)
    purpose_n, purpose_known = _encoded(purpose_code, purpose)
    context_n, context_known = _encoded(context_code, context)
    requested, scope_known = _encoded(scope_mask, scope)
    tag, nonce = request_tag(requester_did, nonce)

    opening = getattr(consent, "commitment_opening", None)
    commitment = getattr(consent, "commitment", None)
    predicates = dict.fromkeys(PREDICATES[:7], False)
    private = None
    try:
        o = {name: field_element(opening[name]) for name in OPENING_FIELDS}
    except (KeyError, TypeError, ValueError):
        o = None                         # no usable opening (never committed, or deleted at revocation)
    if o is not None:
        if o["context"] == 0:            # a consent without a context permits every context
            context_n, context_known = 0, True
        predicates = {
            # the record holds a commitment, the opening hashes to it, and the record was not changed since
            "OPENING": bool(commitment) and verify_opening(commitment, opening) and opening_matches_consent(consent, opening),
            "WINDOW": o["notBefore"] <= t <= o["expiry"],
            "ROLE": role_known and role_n == o["role"],
            "PURPOSE": purpose_known and purpose_n == o["purpose"],
            "CONTEXT": context_known and context_n == o["context"],
            "SCOPE": scope_known and requested != 0 and requested & ~o["scopeMask"] == 0,
            "REQUESTER": to_field(requester_did) == o["requester"],
        }
        private = {_WITNESS_NAME.get(name, name): str(o[name]) for name in OPENING_FIELDS}
        private.update({"requestedScope": str(requested), "nonce": str(nonce)})

    public = dict(zip(PUBLIC_SIGNALS, (str(v) for v in (t, role_n, purpose_n, context_n, tag, consent_root, revocation_root))))
    return {"public": public, "publicSignals": [public[name] for name in PUBLIC_SIGNALS], "private": private,
            "predicates": predicates,
            "audit": {"requester_did": requester_did, "nonce": str(nonce), "tag": str(tag)}}


def tree_roots(consent_tree, revocation_tree):
    '''A read_roots callable over the off-chain trees, for tests and offline tools.'''
    return lambda: (consent_tree.root, revocation_tree.root)


# ---- Algorithm 7.2: witness and proof ------------------------------------------------------------

def assemble_witness(statement, consent_tree, revocation_tree):
    '''First part of Algorithm 7.2. Add to the statement the place of the consent in the two trees:
    the leaf index, the Merkle path of the commitment in the consent tree (membership) and the path
    of the revocation leaf at the same index, which must open to 0 (non-revocation).
    Returns (circuit inputs, predicates), where the predicates now include ISSUED and NOT_REVOKED.
    Both are judged against the roots of the statement, so a tree that is out of step with the
    chain fails here, as its proof would fail on chain.'''
    if statement.get("private") is None:
        raise DecisionProofError(["OPENING"], "the consent record holds no opening of a commitment")
    if consent_tree.depth != revocation_tree.depth:
        raise ValueError("the two trees must have the same depth")
    private, public = statement["private"], statement["public"]
    commitment = open_commitment({name: private[_WITNESS_NAME.get(name, name)] for name in OPENING_FIELDS})
    index = consent_tree.index_of(commitment)
    issued = index is not None
    if not issued:
        # A consent that was never issued has no leaf. The witness then points at the first free leaf,
        # and the membership constraint of the circuit refuses it.
        index = consent_tree.count % consent_tree.capacity
    membership = consent_tree.path(index)
    revocation = revocation_tree.path(index)
    predicates = dict(statement["predicates"])
    predicates["ISSUED"] = issued and root_from_path(commitment, index, membership["siblings"]) == int(public["consentRoot"])
    predicates["NOT_REVOKED"] = (revocation["leaf"] == 0
                                 and root_from_path(0, index, revocation["siblings"]) == int(public["revocationRoot"]))
    inputs = dict(public)
    inputs.update(private)
    inputs.update({"leafIndex": str(index), "consentPath": [str(node) for node in membership["siblings"]],
                   "revocationPath": [str(node) for node in revocation["siblings"]]})
    return inputs, predicates


def prove_decision(statement, consent_tree, revocation_tree, check=True):
    '''Algorithm 7.2. Assemble the witness, run the Groth16 prover and return the proof with its
    public inputs.

    With check (the default) a statement with a predicate that does not hold is refused here, with the
    names of the failed predicates, and the prover is not started. With check=False the witness goes to
    the prover as it is, and the circuit refuses it: that is the evidence that no proof can be
    made for such a request, and the tests use it. In both cases DecisionProofError is raised.

    The result holds mode, scheme, circuit, proof, publicSignals, public (the public inputs by name) and
    tag, all of which may be published, and audit (requester and nonce), which goes to the audit ledger only.'''
    inputs, predicates = assemble_witness(statement, consent_tree, revocation_tree)
    failed = [name for name in PREDICATES if not predicates[name]]
    if check and failed:
        raise DecisionProofError(failed)
    name = circuit_name(consent_tree.depth)
    if not decision_available(consent_tree.depth):
        raise ProofUnavailable("the decision circuit %s is not built: run zk/build_decision.sh" % name)
    try:
        out = json.loads(_node("prove_decision.js", json.dumps(inputs), name))
    except RuntimeError as error:
        raise DecisionProofError(failed, str(error).splitlines()[-1]) from None
    return {"mode": "groth16", "scheme": "%s, tree depth %d" % (SCHEME, consent_tree.depth), "circuit": name,
            "proof": out["proof"], "publicSignals": out["publicSignals"],
            "public": dict(zip(PUBLIC_SIGNALS, out["publicSignals"])), "tag": out["publicSignals"][4],
            "audit": dict(statement["audit"])}


def generate_decision_proof(consent, consent_tree, revocation_tree, requester_did=None, role=CONSENT_ROLE,
                            purpose=None, context=None, scope=None, now_ts=None, nonce=None, read_roots=None):
    '''Algorithms 7.1 and 7.2 for one request. read_roots reads the two roots from the consent contract.
    Without it the roots of the off-chain trees are used. Raises DecisionProofError when the statement does
    not hold for this request, and ProofUnavailable when the circuit is not built.'''
    statement = build_statement(consent, read_roots or tree_roots(consent_tree, revocation_tree),
                                requester_did=requester_did, role=role, purpose=purpose, context=context,
                                scope=scope, now_ts=now_ts, nonce=nonce)
    return prove_decision(statement, consent_tree, revocation_tree)


# ---- verification --------------------------------------------------------------------------------

def verify_decision_proof(proof):
    '''Local verification of a decision proof against the verification key of its circuit. It needs the
    proof and the seven public inputs only. It does not make the checks of the verifier contract on the
    tag, the time and the two roots (Algorithm 7.3): compare public_inputs(proof) with the chain for those.'''
    if not isinstance(proof, dict) or proof.get("mode") != "groth16":
        return False
    signals, name = proof.get("publicSignals"), proof.get("circuit", circuit_name())
    if not isinstance(signals, list) or len(signals) != len(PUBLIC_SIGNALS) or not isinstance(proof.get("proof"), dict):
        return False
    try:                                 # a value of the field has one representation only
        signals = [str(field_element(signal)) for signal in signals]
    except (TypeError, ValueError):
        return False
    match = re.fullmatch(r"halah_decision(?:_d(\d+))?", str(name))
    if not match or not decision_available(int(match.group(1) or TREE_DEPTH)):
        return False
    try:
        return _node("verify_decision.js", json.dumps({"proof": proof["proof"], "publicSignals": signals}), name) == "true"
    except (RuntimeError, subprocess.TimeoutExpired):
        return False


def public_inputs(proof):
    '''The public inputs of a proof by name, as integers.'''
    return {name: int(value) for name, value in zip(PUBLIC_SIGNALS, proof["publicSignals"])}


def solidity_calldata(proof):
    '''A proof as the arguments (a, b, c, public signals) of verifyProof in contracts/HalahDecisionVerifier.sol.
    snarkjs writes each G2 coordinate as (c0, c1) and the contract reads (c1, c0), so each pair of pi_b swaps.'''
    p = proof["proof"]
    a = [int(p["pi_a"][0]), int(p["pi_a"][1])]
    b = [[int(p["pi_b"][0][1]), int(p["pi_b"][0][0])], [int(p["pi_b"][1][1]), int(p["pi_b"][1][0])]]
    c = [int(p["pi_c"][0]), int(p["pi_c"][1])]
    return a, b, c, [int(value) for value in proof["publicSignals"]]
