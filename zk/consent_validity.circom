pragma circom 2.1.6;
include "circomlib/circuits/poseidon.circom";
include "circomlib/circuits/comparators.circom";
/* HALAH limited-scope ZK statement (Groth16, BN254):
   "I know (secret, expiry) such that Poseidon(secret, expiry) == commitment  AND  now <= expiry"
   Public: commitment, now   Private: secret, expiry */
template ConsentValidity() {
    signal input secret;
    signal input expiry;
    signal input commitment;
    signal input now;
    signal output ok;
    component h = Poseidon(2);
    h.inputs[0] <== secret;
    h.inputs[1] <== expiry;
    commitment === h.out;
    component le = LessEqThan(64);
    le.in[0] <== now;
    le.in[1] <== expiry;
    le.out === 1;
    ok <== 1;
}
component main {public [commitment, now]} = ConsentValidity();
