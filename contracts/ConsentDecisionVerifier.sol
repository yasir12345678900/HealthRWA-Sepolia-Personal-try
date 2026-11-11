// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/// @title Groth16 verifier of the decision circuit, in the form snarkjs exports it for 7 public signals.
interface IDecisionProofVerifier {
    function verifyProof(uint256[2] calldata a, uint256[2][2] calldata b, uint256[2] calldata c,
                         uint256[7] calldata publicSignals) external view returns (bool);
}

/// @title The roots that the consent token (ConsentSBTv4) keeps and updates at every mint and revoke.
interface IConsentRoots {
    function revocationRoot() external view returns (uint256);
    function isKnownConsentRoot(uint256 root) external view returns (bool);
}

/// @title HALAH decision verifier - on-chain verification of the decision proof (Algorithm 7.3).
/// @notice Wraps the Groth16 verifier of the decision circuit and applies the checks that the proof cannot make
///         for itself. The public signals are, in this order, [t, role, purpose, context, tag, consentRoot,
///         revocationRoot]. A submission is refused (the transaction reverts and nothing is recorded) when
///         - the request tag was already seen, so a replayed proof fails;
///         - t is later than the block timestamp, or older than it by more than TOLERANCE, so a back-dated or
///           post-dated proof fails;
///         - the revocation root is not the current one, so a proof built before a revocation fails;
///         - the consent root is neither the current one nor among the last 8;
///         - the Groth16 verifier does not accept the proof for these public signals.
///         An accepted proof records its tag and emits ConsentVerified with the public signals and nothing else.
///         Because t may be up to TOLERANCE seconds old, a consent can be used for up to TOLERANCE seconds after it expires.
contract ConsentDecisionVerifier {
    /// Largest accepted age of t, in seconds.
    uint256 public constant TOLERANCE = 300;
    /// Order of the BN254 scalar field. Every public signal is an element of this field.
    uint256 public constant FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617;

    IDecisionProofVerifier public immutable proofVerifier;
    IConsentRoots public immutable consentToken;

    /// tag => number of the block in which its proof was accepted (0 = the tag was never seen).
    mapping(uint256 => uint256) public verifiedAtBlock;

    event ConsentVerified(uint256 indexed tag, uint256 t, uint256 role, uint256 purpose, uint256 context,
                          uint256 consentRoot, uint256 revocationRoot, bool result);

    constructor(address proofVerifier_, address consentToken_) {
        require(proofVerifier_.code.length > 0 && consentToken_.code.length > 0, "not a contract");
        proofVerifier = IDecisionProofVerifier(proofVerifier_);
        consentToken = IConsentRoots(consentToken_);
    }

    /// True when a proof with this request tag was already accepted.
    function tagSeen(uint256 tag) public view returns (bool) {
        return verifiedAtBlock[tag] != 0;
    }

    /// Verify the decision proof of one request. Returns true and emits ConsentVerified on acceptance, and
    /// reverts with the reason on every rejection, so that a refused submission does not use up its tag.
    function verifyDecision(uint256[2] calldata a, uint256[2][2] calldata b, uint256[2] calldata c,
                            uint256[7] calldata publicSignals) external returns (bool) {
        // a value of the field has one representation only, so a tag cannot be replayed as tag + FIELD
        for (uint256 i = 0; i < 7; i++) {
            require(publicSignals[i] < FIELD, "public input outside the field");
        }
        uint256 t = publicSignals[0];
        uint256 tag = publicSignals[4];

        require(!tagSeen(tag), "tag already seen");
        require(t <= block.timestamp, "time is in the future");
        require(block.timestamp - t <= TOLERANCE, "time is too old");
        require(publicSignals[6] == consentToken.revocationRoot(), "revocation root is not current");
        require(consentToken.isKnownConsentRoot(publicSignals[5]), "consent root is not recent");
        require(proofVerifier.verifyProof(a, b, c, publicSignals), "proof is not valid");

        verifiedAtBlock[tag] = block.number;
        emit ConsentVerified(tag, t, publicSignals[1], publicSignals[2], publicSignals[3],
                             publicSignals[5], publicSignals[6], true);
        return true;
    }
}
