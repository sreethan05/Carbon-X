// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC721/IERC721.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

contract CarbonMarketplace is ReentrancyGuard {
    IERC721 public immutable carbonCreditContract;

    struct Listing {
        address seller;
        uint256 price; // Price in native currency (Wei)
        bool active;
    }

    // Mapping from tokenId to Listing
    mapping(uint256 => Listing) private _listings;

    event CreditListed(uint256 indexed tokenId, address indexed seller, uint256 price);
    event CreditSold(uint256 indexed tokenId, address indexed buyer, address indexed seller, uint256 price);
    event ListingCancelled(uint256 indexed tokenId, address indexed seller);
    event ListingPriceUpdated(uint256 indexed tokenId, address indexed seller, uint256 newPrice);

    constructor(address carbonCreditAddress) {
        require(carbonCreditAddress != address(0), "CarbonMarketplace: Invalid contract address");
        carbonCreditContract = IERC721(carbonCreditAddress);
    }

    function listCredit(uint256 tokenId, uint256 price) external nonReentrant {
        require(price > 0, "CarbonMarketplace: Price must be greater than zero");
        require(
            carbonCreditContract.ownerOf(tokenId) == msg.sender,
            "CarbonMarketplace: Only the owner of the credit can list it"
        );

        // Escrow the NFT by transferring it to the marketplace contract
        carbonCreditContract.transferFrom(msg.sender, address(this), tokenId);

        _listings[tokenId] = Listing({
            seller: msg.sender,
            price: price,
            active: true
        });

        emit CreditListed(tokenId, msg.sender, price);
    }

    function buyCredit(uint256 tokenId) external payable nonReentrant {
        Listing storage listing = _listings[tokenId];
        require(listing.active, "CarbonMarketplace: Credit is not listed for sale");
        require(msg.value >= listing.price, "CarbonMarketplace: Insufficient payment");

        address seller = listing.seller;
        uint256 price = listing.price;

        // Mark listing inactive before transferring to prevent reentrancy issues
        listing.active = false;

        // Transfer funds to the seller
        (bool success, ) = payable(seller).call{value: price}("");
        require(success, "CarbonMarketplace: Failed to send funds to seller");

        // Transfer credit NFT to buyer
        carbonCreditContract.transferFrom(address(this), msg.sender, tokenId);

        // Refund excess payment
        if (msg.value > price) {
            (bool refundSuccess, ) = payable(msg.sender).call{value: msg.value - price}("");
            require(refundSuccess, "CarbonMarketplace: Failed to refund excess payment");
        }

        emit CreditSold(tokenId, msg.sender, seller, price);
    }

    function cancelListing(uint256 tokenId) external nonReentrant {
        Listing storage listing = _listings[tokenId];
        require(listing.active, "CarbonMarketplace: Credit is not listed for sale");
        require(listing.seller == msg.sender, "CarbonMarketplace: Only the listing seller can cancel");

        listing.active = false;

        // Return NFT to the seller
        carbonCreditContract.transferFrom(address(this), msg.sender, tokenId);

        emit ListingCancelled(tokenId, msg.sender);
    }

    function updateListingPrice(uint256 tokenId, uint256 newPrice) external nonReentrant {
        require(newPrice > 0, "CarbonMarketplace: Price must be greater than zero");
        Listing storage listing = _listings[tokenId];
        require(listing.active, "CarbonMarketplace: Credit is not listed for sale");
        require(listing.seller == msg.sender, "CarbonMarketplace: Only the listing seller can update price");

        listing.price = newPrice;

        emit ListingPriceUpdated(tokenId, msg.sender, newPrice);
    }

    function getListing(uint256 tokenId) external view returns (Listing memory) {
        return _listings[tokenId];
    }
}
