const { expect } = require("chai");
const { ethers } = require("hardhat");

describe("Carbon Credit Trading System", function () {
  let CarbonCredit;
  let carbonCredit;
  let CarbonMarketplace;
  let carbonMarketplace;
  
  let owner;
  let farmer;
  let buyer;
  let otherAccount;

  beforeEach(async function () {
    [owner, farmer, buyer, otherAccount] = await ethers.getSigners();

    // Deploy CarbonCredit
    CarbonCredit = await ethers.getContractFactory("CarbonCredit");
    carbonCredit = await CarbonCredit.deploy(owner.address, owner.address); // owner is admin and minter
    await carbonCredit.waitForDeployment();

    // Deploy CarbonMarketplace
    CarbonMarketplace = await ethers.getContractFactory("CarbonMarketplace");
    carbonMarketplace = await CarbonMarketplace.deploy(await carbonCredit.getAddress());
    await carbonMarketplace.waitForDeployment();
  });

  describe("Minting", function () {
    it("Should allow the minter to mint a carbon credit NFT", async function () {
      const farmHash = ethers.keccak256(ethers.toUtf8Bytes("farm_coordinates"));
      const carbonAmount = ethers.parseEther("10.5"); // 10.5 tCO2e
      const ndviMean = 4500; // NDVI 0.45 * 10^4
      const proof = "ipfs://QmVerificationProofHash";
      const uri = "https://example.com/credit/0";

      await expect(
        carbonCredit.connect(owner).mint(farmer.address, farmHash, carbonAmount, ndviMean, proof, uri)
      ).to.emit(carbonCredit, "CarbonCreditMinted");

      expect(await carbonCredit.ownerOf(0)).to.equal(farmer.address);

      const data = await carbonCredit.getCreditData(0);
      expect(data.farmCoordinatesHash).to.equal(farmHash);
      expect(data.carbonAmount).to.equal(carbonAmount);
      expect(data.ndviMean).to.equal(ndviMean);
      expect(data.verificationProof).to.equal(proof);
      expect(data.retired).to.be.false;
    });

    it("Should reject minting from unauthorized accounts", async function () {
      const farmHash = ethers.keccak256(ethers.toUtf8Bytes("farm_coordinates"));
      const carbonAmount = ethers.parseEther("1.0");
      const ndviMean = 5000;
      const proof = "ipfs://proof";
      const uri = "https://example.com/1";

      await expect(
        carbonCredit.connect(farmer).mint(farmer.address, farmHash, carbonAmount, ndviMean, proof, uri)
      ).to.be.revertedWithCustomError(carbonCredit, "AccessControlUnauthorizedAccount");
    });
  });

  describe("Marketplace Trading", function () {
    let tokenId = 0;
    const price = ethers.parseEther("0.1"); // 0.1 ETH/MATIC

    beforeEach(async function () {
      const farmHash = ethers.keccak256(ethers.toUtf8Bytes("farm_coordinates"));
      const carbonAmount = ethers.parseEther("10");
      const ndviMean = 4000;
      const proof = "ipfs://proof";
      const uri = "https://example.com/0";

      // Mint token to farmer
      await carbonCredit.connect(owner).mint(farmer.address, farmHash, carbonAmount, ndviMean, proof, uri);
    });

    it("Should list credit on the marketplace", async function () {
      // Approve marketplace to transfer token
      await carbonCredit.connect(farmer).approve(await carbonMarketplace.getAddress(), tokenId);

      await expect(
        carbonMarketplace.connect(farmer).listCredit(tokenId, price)
      )
        .to.emit(carbonMarketplace, "CreditListed")
        .withArgs(tokenId, farmer.address, price);

      // Marketplace should hold the NFT now
      expect(await carbonCredit.ownerOf(tokenId)).to.equal(await carbonMarketplace.getAddress());

      const listing = await carbonMarketplace.getListing(tokenId);
      expect(listing.seller).to.equal(farmer.address);
      expect(listing.price).to.equal(price);
      expect(listing.active).to.be.true;
    });

    it("Should allow purchase of a listed credit", async function () {
      await carbonCredit.connect(farmer).approve(await carbonMarketplace.getAddress(), tokenId);
      await carbonMarketplace.connect(farmer).listCredit(tokenId, price);

      // Farmer balance before
      const initialFarmerBalance = await ethers.provider.getBalance(farmer.address);

      // Buy credit
      await expect(
        carbonMarketplace.connect(buyer).buyCredit(tokenId, { value: price })
      )
        .to.emit(carbonMarketplace, "CreditSold")
        .withArgs(tokenId, buyer.address, farmer.address, price);

      // Buyer should now own the NFT
      expect(await carbonCredit.ownerOf(tokenId)).to.equal(buyer.address);

      // Seller should have received the funds
      const finalFarmerBalance = await ethers.provider.getBalance(farmer.address);
      expect(finalFarmerBalance - initialFarmerBalance).to.equal(price);

      // Listing should be inactive
      const listing = await carbonMarketplace.getListing(tokenId);
      expect(listing.active).to.be.false;
    });

    it("Should allow cancelling a listing", async function () {
      await carbonCredit.connect(farmer).approve(await carbonMarketplace.getAddress(), tokenId);
      await carbonMarketplace.connect(farmer).listCredit(tokenId, price);

      await expect(
        carbonMarketplace.connect(farmer).cancelListing(tokenId)
      )
        .to.emit(carbonMarketplace, "ListingCancelled")
        .withArgs(tokenId, farmer.address);

      // Farmer should own the NFT again
      expect(await carbonCredit.ownerOf(tokenId)).to.equal(farmer.address);

      // Listing should be inactive
      const listing = await carbonMarketplace.getListing(tokenId);
      expect(listing.active).to.be.false;
    });
  });

  describe("Retirement", function () {
    let tokenId = 0;

    beforeEach(async function () {
      const farmHash = ethers.keccak256(ethers.toUtf8Bytes("farm"));
      const carbonAmount = ethers.parseEther("5");
      const ndviMean = 3500;
      const proof = "ipfs://proof";
      const uri = "https://example.com/0";

      await carbonCredit.connect(owner).mint(buyer.address, farmHash, carbonAmount, ndviMean, proof, uri);
    });

    it("Should allow owner to retire the credit", async function () {
      await expect(carbonCredit.connect(buyer).retire(tokenId))
        .to.emit(carbonCredit, "CarbonCreditRetired")
        .withArgs(tokenId, buyer.address);

      const data = await carbonCredit.getCreditData(tokenId);
      expect(data.retired).to.be.true;
      expect(data.retiredBy).to.equal(buyer.address);
    });

    it("Should block transfers of retired credits", async function () {
      await carbonCredit.connect(buyer).retire(tokenId);

      await expect(
        carbonCredit.connect(buyer).transferFrom(buyer.address, otherAccount.address, tokenId)
      ).to.be.revertedWith("CarbonCredit: Credit is retired and cannot be transferred");
    });
  });
});
