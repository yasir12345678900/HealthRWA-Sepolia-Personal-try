// SPDX-License-Identifier: MIT
/*
Consent SBT for HALAH — v2 hardened
History Access Link for Authorised Healthcare
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh

v1 (ConsentSBT.sol) blocks transferFrom only, so the token remains
transferable through both safeTransferFrom overloads. v2 closes that
gap with a _beforeTokenTransfer guard: only mint (from == 0) and
burn (to == 0) are permitted, which is the standard soulbound pattern.
Built against @openzeppelin/contracts@4.9.x.
*/

pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract ConsentSBTv2 is ERC721, Ownable {
    uint256 private tokenCounter;

    struct Consent {
        address patient;
        address requester;
        string purpose;
        uint256 expiry;
        bool revoked;
    }

    mapping(uint256 => Consent) public consents;

    constructor() ERC721("MedicalConsent", "CONSENT") {}

    function mintConsent(
        address patient,
        address requester,
        string memory purpose,
        uint256 expiry
    ) public onlyOwner returns (uint256) {
        tokenCounter++;
        uint256 tokenId = tokenCounter;
        _safeMint(patient, tokenId);
        consents[tokenId] = Consent(patient, requester, purpose, expiry, false);
        return tokenId;
    }

    /// Soulbound guard: forbid every transfer except mint and burn.
    function _beforeTokenTransfer(
        address from,
        address to,
        uint256 firstTokenId,
        uint256 batchSize
    ) internal override {
        require(from == address(0) || to == address(0), "Soulbound Token");
        super._beforeTokenTransfer(from, to, firstTokenId, batchSize);
    }

    function revoke(uint256 tokenId) public onlyOwner {
        consents[tokenId].revoked = true;
    }

    function checkValid(uint256 tokenId) public view returns (bool) {
        Consent memory c = consents[tokenId];
        if (c.revoked) return false;
        if (block.timestamp > c.expiry) return false;
        return true;
    }
}
