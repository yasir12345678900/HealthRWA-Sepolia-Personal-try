// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Mock of the Groth16 verifier of the decision circuit. FOR THE TESTS OF ConsentDecisionVerifier ONLY.
/// @notice It proves nothing and is not zero-knowledge. It has the interface of the verifier that snarkjs exports
///         for 7 public signals, and it accepts a "proof" exactly when a[0] is the keccak256 digest of the public
///         signals and of the rest of the proof, reduced to the field. Like a real proof, it is therefore bound to
///         its public signals, so the tests can tell a wrapper that forwards everything unchanged from one that
///         does not. Anyone can compute an accepted "proof", so never deploy it.
contract MockDecisionVerifier {
    uint256 private constant FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617;

    /// The value of a[0] that this mock accepts for the given public signals and the rest of the proof.
    function expectedA0(uint256 a1, uint256[2][2] calldata b, uint256[2] calldata c,
                        uint256[7] calldata publicSignals) public pure returns (uint256) {
        return uint256(keccak256(abi.encode(publicSignals, a1, b, c))) % FIELD;
    }

    function verifyProof(uint256[2] calldata a, uint256[2][2] calldata b, uint256[2] calldata c,
                         uint256[7] calldata publicSignals) external pure returns (bool) {
        return a[0] == expectedA0(a[1], b, c, publicSignals);
    }
}
