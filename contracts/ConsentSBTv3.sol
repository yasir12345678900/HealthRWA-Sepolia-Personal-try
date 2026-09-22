// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/// @title ERC-5484 (Consensual Soulbound Token) interface
interface IERC5484 {
    enum BurnAuth { IssuerOnly, OwnerOnly, Both, Neither }
    event Issued(address indexed from, address indexed to, uint256 indexed tokenId, BurnAuth burnAuth);
    function burnAuth(uint256 tokenId) external view returns (BurnAuth);
}

/// @title HALAH Consent SBT v3 - C = (I, A, P, T, L, E): VT/VL enforced on-chain + ERC-5484 burn. Soulbound.
contract ConsentSBTv3 is ERC721, Ownable, IERC5484 {
    uint256 private _counter;

    struct Consent {
        address patient;      // I (pseudonymous keccak256(DID))
        address requester;    // I
        bytes32 purposeHash;  // P
        uint64  notBefore;    // T
        uint64  expiry;       // T
        bytes2  jurisdiction; // L (ISO-3166-1 alpha-2)
        bool    revoked;      // E
        BurnAuth burnAuth;    // ERC-5484
    }

    mapping(uint256 => Consent) public consents;

    event ConsentMinted(uint256 indexed tokenId, address indexed patient, address indexed requester,
                        bytes32 purposeHash, uint64 notBefore, uint64 expiry, bytes2 jurisdiction);
    event ConsentRevoked(uint256 indexed tokenId, address indexed by);
    event ConsentBurned(uint256 indexed tokenId, address indexed by);

    constructor() ERC721("MedicalConsent", "CONSENT") {}

    function mintConsentV3(address patient, address requester, string calldata purpose,
                           uint64 notBefore, uint64 expiry, bytes2 jurisdiction, BurnAuth auth)
        external onlyOwner returns (uint256 tokenId)
    {
        require(patient != address(0) && requester != address(0), "zero address");
        require(notBefore <= expiry, "notBefore > expiry");
        require(expiry > block.timestamp, "expiry in the past");
        tokenId = ++_counter;
        _safeMint(patient, tokenId);
        consents[tokenId] = Consent(patient, requester, keccak256(bytes(purpose)), notBefore, expiry, jurisdiction, false, auth);
        emit ConsentMinted(tokenId, patient, requester, keccak256(bytes(purpose)), notBefore, expiry, jurisdiction);
        emit Issued(msg.sender, patient, tokenId, auth);
    }

    /// v2-compatible signature (VL unrestricted, notBefore = now, burnAuth = Both)
    function mintConsent(address patient, address requester, string calldata purpose, uint256 expiry)
        external onlyOwner returns (uint256)
    {
        return this.mintConsentV3(patient, requester, purpose, uint64(block.timestamp), uint64(expiry), bytes2(0), BurnAuth.Both);
    }

    function _beforeTokenTransfer(address from, address to, uint256 firstTokenId, uint256 batchSize) internal override {
        require(from == address(0) || to == address(0), "Soulbound Token");
        super._beforeTokenTransfer(from, to, firstTokenId, batchSize);
    }

    function revoke(uint256 tokenId) external onlyOwner {
        require(_exists(tokenId), "no token");
        consents[tokenId].revoked = true;
        emit ConsentRevoked(tokenId, msg.sender);
    }

    function burnAuth(uint256 tokenId) external view override returns (BurnAuth) {
        require(_exists(tokenId), "no token");
        return consents[tokenId].burnAuth;
    }

    function burn(uint256 tokenId) external {
        require(_exists(tokenId), "no token");
        BurnAuth a = consents[tokenId].burnAuth;
        bool isIssuer = msg.sender == owner();
        bool isHolder = msg.sender == ownerOf(tokenId);
        bool ok = (a == BurnAuth.IssuerOnly && isIssuer) || (a == BurnAuth.OwnerOnly && isHolder)
               || (a == BurnAuth.Both && (isIssuer || isHolder));
        require(ok, "burn not authorised");
        _burn(tokenId);
        delete consents[tokenId];
        emit ConsentBurned(tokenId, msg.sender);
    }

    function checkValid(uint256 tokenId) public view returns (bool) {
        if (!_exists(tokenId)) return false;
        Consent memory c = consents[tokenId];
        if (c.revoked) return false;
        if (block.timestamp < c.notBefore) return false;   // VT
        if (block.timestamp > c.expiry) return false;      // VT
        return true;
    }

    /// VT AND VL: valid now AND requester jurisdiction matches (bytes2(0) = unrestricted)
    function checkValidAt(uint256 tokenId, bytes2 jurisdiction) external view returns (bool) {
        if (!checkValid(tokenId)) return false;
        bytes2 j = consents[tokenId].jurisdiction;
        return j == bytes2(0) || j == jurisdiction;
    }

    function supportsInterface(bytes4 interfaceId) public view override returns (bool) {
        return interfaceId == type(IERC5484).interfaceId || super.supportsInterface(interfaceId);
    }
}
