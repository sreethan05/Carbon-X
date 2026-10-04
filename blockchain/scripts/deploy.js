const hre = require("hardhat");

async function main() {
  const [deployer] = await hre.ethers.getSigners();
  console.log("Deploying contracts with the account:", deployer.address);

  // Deploy CarbonCredit contract
  // We set deployer as the admin and minter for testing and deployment demonstration
  const CarbonCredit = await hre.ethers.getContractFactory("CarbonCredit");
  const carbonCredit = await CarbonCredit.deploy(deployer.address, deployer.address);
  await carbonCredit.waitForDeployment();
  const carbonCreditAddress = await carbonCredit.getAddress();
  console.log("CarbonCredit deployed to:", carbonCreditAddress);

  // Deploy CarbonMarketplace contract
  const CarbonMarketplace = await hre.ethers.getContractFactory("CarbonMarketplace");
  const carbonMarketplace = await CarbonMarketplace.deploy(carbonCreditAddress);
  await carbonMarketplace.waitForDeployment();
  const carbonMarketplaceAddress = await carbonMarketplace.getAddress();
  console.log("CarbonMarketplace deployed to:", carbonMarketplaceAddress);
  
  console.log("Deployment finished successfully!");
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
