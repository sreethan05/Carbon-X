// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/ERC721.sol";
import "@openzeppelin/contracts/token/ERC721/extensions/ERC721URIStorage.sol";
import "@openzeppelin/contracts/access/AccessControl.sol";

contract CarbonCredit is ERC721, ERC721URIStorage, AccessControl {
    bytes32 public constant MINTER_ROLE = keccak256("MINTER_ROLE");

    struct CreditData {
        bytes32 farmCoordinatesHash;
        uint256 carbonAmount; // in tCO2e (18 decimals)
        uint256 ndviMean;     // NDVI mean scaled by 10^4
        uint256 timestamp;    // Verification timestamp
        string verificationProof; // IPFS CID or URL
        bool retired;
        address retiredBy;
    }

    uint256 private _nextTokenId;
    mapping(uint256 => CreditData) private _credits;

    event CarbonCreditMinted(
        uint256 indexed tokenId,
        address indexed farmer,
        bytes32 farmCoordinatesHash,
        uint256 carbonAmount,
        uint256 ndviMean,
        uint256 timestamp,
        string verificationProof
    );

    event CarbonCreditRetired(
        uint256 indexed tokenId,
        address indexed retiredBy
    );

    constructor(address defaultAdmin, address minter) ERC721("CarbonX Credit", "CCX") {
        _grantRole(DEFAULT_ADMIN_ROLE, defaultAdmin);
        _grantRole(MINTER_ROLE, minter);
    }

    function mint(
        address to,
        bytes32 farmCoordinatesHash,
        uint256 carbonAmount,
        uint256 ndviMean,
        string memory verificationProof,
        string memory uri
    ) public onlyRole(MINTER_ROLE) returns (uint256) {
        uint256 tokenId = _nextTokenId++;
        _safeMint(to, tokenId);
        _setTokenURI(tokenId, uri);

        _credits[tokenId] = CreditData({
            farmCoordinatesHash: farmCoordinatesHash,
            carbonAmount: carbonAmount,
            ndviMean: ndviMean,
            timestamp: block.timestamp,
            verificationProof: verificationProof,
            retired: false,
            retiredBy: address(0)
        });

        emit CarbonCreditMinted(
            tokenId,
            to,
            farmCoordinatesHash,
            carbonAmount,
            ndviMean,
            block.timestamp,
            verificationProof
        );

        return tokenId;
    }

    function retire(uint256 tokenId) public {
        require(ownerOf(tokenId) == msg.sender, "CarbonCredit: Only owner can retire credit");
        CreditData storage credit = _credits[tokenId];
        require(!credit.retired, "CarbonCredit: Credit is already retired");

        credit.retired = true;
        credit.retiredBy = msg.sender;

        emit CarbonCreditRetired(tokenId, msg.sender);
    }

    function getCreditData(uint256 tokenId) public view returns (CreditData memory) {
        _requireOwned(tokenId);
        return _credits[tokenId];
    }

    // Overrides required by Solidity

    function tokenURI(uint256 tokenId)
        public
        view
        override(ERC721, ERC721URIStorage)
        returns (string memory)
    {
        return super.tokenURI(tokenId);
    }

    function supportsInterface(bytes4 interfaceId)
        public
        view
        override(ERC721, ERC721URIStorage, AccessControl)
        returns (bool)
    {
        return super.supportsInterface(interfaceId);
    }

    function _update(
        address to,
        uint256 tokenId,
        address auth
    ) internal override(ERC721) returns (address) {
        require(!_credits[tokenId].retired, "CarbonCredit: Credit is retired and cannot be transferred");
        return super._update(to, tokenId, auth);
    }
}
