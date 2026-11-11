pragma circom 2.1.6;
include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";
include "circomlib/circuits/bitify.circom";
/* HALAH decision statement (Groth16, BN254), Chapter 7, Algorithms 7.1 and 7.2:
   "I know a consent whose commitment c is a leaf of the consent tree, whose leaf of the revocation tree is 0,
    whose window holds the time t, whose policy permits the claimed role, purpose and context, whose scope
    covers the requested modules, and whose requester is the one behind the request tag."
   Public, in this order: t, role, purpose, context, tag, consentRoot, revocationRoot
   Private: the opening of c (patient, guardiansDigest, requester, role, purpose, context, scopeMask, notBefore,
            expiry, blinding), the leaf index and the two Merkle paths, the requested scope mask, the nonce of the tag.
   Not proved here, and checked by the server off chain: the guardian threshold (guardiansDigest is only opened),
   the requester's credential for the claimed role, and the SUSPENDED state.
   Constraint families: 1 commitment opening, 2 membership in the consent tree, 3 revocation leaf opens to 0,
   4 window by range checks, 5 role, purpose and context equal the committed ones, 6 requested scope is not
   empty and inside the committed scope, 7 the tag opens to the committed requester.
   Hash: Poseidon of circomlib 2.0.5 over the BN254 scalar field (S-box x^5, 8 full rounds, 57 partial rounds for
   two inputs and 66 for the ten inputs of the commitment). Both trees have depth 16 and the scope mask has 4 bits.
   Size: 8760 constraints after simplification (--O2), 483 for every level of the trees. */

// Root reached from a leaf through its siblings. bits[h] = 1 when the node at height h is a right child.
// The caller constrains every bit to 0 or 1.
template MerkleRoot(depth) {
    signal input leaf;
    signal input bits[depth];
    signal input siblings[depth];
    signal output root;
    signal node[depth + 1];
    signal left[depth];
    component h[depth];
    node[0] <== leaf;
    for (var i = 0; i < depth; i++) {
        left[i] <== node[i] + bits[i] * (siblings[i] - node[i]);
        h[i] = Poseidon(2);
        h[i].inputs[0] <== left[i];
        h[i].inputs[1] <== node[i] + siblings[i] - left[i];
        node[i + 1] <== h[i].out;
    }
    root <== node[depth];
}

template HalahDecision(depth, modules) {
    // public inputs, in the order of the verifier contract
    signal input t;
    signal input role;
    signal input purpose;
    signal input context;
    signal input tag;
    signal input consentRoot;
    signal input revocationRoot;
    // witness: the opening of the commitment
    signal input patient;
    signal input guardiansDigest;
    signal input requester;
    signal input committedRole;
    signal input committedPurpose;
    signal input committedContext;
    signal input scopeMask;
    signal input notBefore;
    signal input expiry;
    signal input blinding;
    // witness: the place of the consent in both trees
    signal input leafIndex;
    signal input consentPath[depth];
    signal input revocationPath[depth];
    // witness: the request
    signal input requestedScope;
    signal input nonce;

    // 1. Commitment opening: c = Poseidon(opening)
    component c = Poseidon(10);
    c.inputs[0] <== patient;
    c.inputs[1] <== guardiansDigest;
    c.inputs[2] <== requester;
    c.inputs[3] <== committedRole;
    c.inputs[4] <== committedPurpose;
    c.inputs[5] <== committedContext;
    c.inputs[6] <== scopeMask;
    c.inputs[7] <== notBefore;
    c.inputs[8] <== expiry;
    c.inputs[9] <== blinding;

    // 2. Membership: c is leaf leafIndex of the consent tree (the consent was issued)
    component index = Num2Bits(depth);
    index.in <== leafIndex;
    component issued = MerkleRoot(depth);
    issued.leaf <== c.out;
    for (var i = 0; i < depth; i++) {
        issued.bits[i] <== index.out[i];
        issued.siblings[i] <== consentPath[i];
    }
    consentRoot === issued.root;

    // 3. Non-revocation: the leaf of the revocation tree at the same index opens to 0
    component live = MerkleRoot(depth);
    live.leaf <== 0;
    for (var i = 0; i < depth; i++) {
        live.bits[i] <== index.out[i];
        live.siblings[i] <== revocationPath[i];
    }
    revocationRoot === live.root;

    // 4. Window: notBefore <= t <= expiry. The three values are range-checked to 64 bits first,
    //    because the comparators are sound only for inputs of that size.
    component tBits = Num2Bits(64);
    tBits.in <== t;
    component fromBits = Num2Bits(64);
    fromBits.in <== notBefore;
    component untilBits = Num2Bits(64);
    untilBits.in <== expiry;
    component started = LessEqThan(64);
    started.in[0] <== notBefore;
    started.in[1] <== t;
    started.out === 1;
    component notExpired = LessEqThan(64);
    notExpired.in[0] <== t;
    notExpired.in[1] <== expiry;
    notExpired.out === 1;

    // 5. Policy: the claimed role, purpose and context are the committed ones
    role === committedRole;
    purpose === committedPurpose;
    context === committedContext;

    // 6. Scope: the requested mask is not empty and has no bit outside the committed mask
    component have = Num2Bits(modules);
    have.in <== scopeMask;
    component want = Num2Bits(modules);
    want.in <== requestedScope;
    for (var i = 0; i < modules; i++) {
        want.out[i] * (1 - have.out[i]) === 0;
    }
    component empty = IsZero();
    empty.in <== requestedScope;
    empty.out === 0;

    // 7. Request tag: tag = Poseidon(requester, nonce) for the requester inside the commitment
    component opened = Poseidon(2);
    opened.inputs[0] <== requester;
    opened.inputs[1] <== nonce;
    tag === opened.out;
}
component main {public [t, role, purpose, context, tag, consentRoot, revocationRoot]} = HalahDecision(16, 4);
