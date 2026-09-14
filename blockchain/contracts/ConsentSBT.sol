// SPDX-License-Identifier: MIT
/*
Consent SBT for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-06-3
*/

pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

contract ConsentSBT is ERC721, Ownable {
    uint256 private tokenCounter;
    struct Consent {
        address patient;
        address requester;
        string purpose;
        uint256 expiry;
        bool revoked;
    }

    mapping(
        uint256 => Consent
    )
    public consents;

    constructor()
    ERC721(
        "MedicalConsent",
        "CONSENT"
    )
    {}

    function mintConsent(
        address patient,
        address requester,
        string memory purpose,
        uint256 expiry
    )

    public onlyOwner
    returns(uint256){
        tokenCounter++;
        uint256 tokenId =
            tokenCounter;
        _safeMint(
            patient,
            tokenId
        );

        consents[tokenId]=Consent(
            patient,
            requester,
            purpose,
            expiry,
            false
        );
        return tokenId;
    }



    /*
    Soulbound: disable transfer
    */

    function transferFrom(
        address,
        address,
        uint256
    )

    public override
    {
        revert("Soulbound Token");
    }

    function revoke(uint256 tokenId)

    public onlyOwner{
        consents[tokenId]
        .revoked=true;
    }


    function checkValid(uint256 tokenId)

    public view returns(bool){
        Consent memory c = consents[tokenId];

        if(c.revoked)
            return false;


        if(block.timestamp > c.expiry)
            return false;
        return true;
    }
}