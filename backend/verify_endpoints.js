const { ethers } = require('ethers');

const API_BASE = 'http://localhost:5000/api/credits';

const FARMER_ADDRESS = '0x70997970C51812dc3A010C7d01b50e0d17dc79C8';
const FARMER_KEY = '0x59c6995e998f97a5a0044966f0945389dc9e86dae88c7a8412f4603b6b78690d';

const BUYER_ADDRESS = '0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC';
const BUYER_KEY = '0x5de4111afa1a4b94908f83103eb1f1706367c2e68ca870fc3fb9a804cdab365a';

async function run() {
  console.log("=== Starting CarbonX Backend API Verification ===");

  // 1. Health check
  try {
    const healthRes = await fetch('http://localhost:5000/health');
    const healthData = await healthRes.json();
    console.log("✔ Backend Health:", healthData.status);
  } catch (err) {
    console.error("❌ Backend is not running or unreachable:", err.message);
    process.exit(1);
  }

  // 2. Mint Credit
  console.log("\n--- Step 1: Minting Carbon Credit ---");
  const farmCoordinatesHash = ethers.keccak256(ethers.toUtf8Bytes("farm_coordinates_test_1"));
  const mintPayload = {
    farmerAddress: FARMER_ADDRESS,
    farmCoordinatesHash,
    carbonAmount: "25.5",
    ndviMean: 5200,
    verificationProof: "ipfs://QmSatelliteVerificationDataProof",
    uri: "https://example.com/credits/0"
  };

  const mintRes = await fetch(`${API_BASE}/mint`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(mintPayload)
  });
  
  if (!mintRes.ok) {
    const err = await mintRes.json();
    console.error("❌ Minting failed:", err);
    process.exit(1);
  }
  const mintData = await mintRes.json();
  console.log("✔ Credit Minted successfully. Token ID:", mintData.tokenId);
  console.log("Transaction Hash:", mintData.txHash);
  const tokenId = mintData.tokenId;

  // 3. Get Credit Details
  console.log("\n--- Step 2: Fetching Minted Credit Details ---");
  const getRes = await fetch(`${API_BASE}/${tokenId}`);
  const getVal = await getRes.json();
  console.log("✔ Fetched Credit Data:");
  console.log(`  - Carbon Amount: ${getVal.carbonAmount} tCO2e`);
  console.log(`  - NDVI Mean: ${getVal.ndviMean}`);
  console.log(`  - Retired: ${getVal.retired}`);

  // 4. List Credit on Marketplace
  console.log("\n--- Step 3: Listing Credit on Marketplace ---");
  const listPayload = {
    tokenId,
    price: "0.05",
    sellerPrivateKey: FARMER_KEY
  };
  const listRes = await fetch(`${API_BASE}/list`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(listPayload)
  });
  
  if (!listRes.ok) {
    const err = await listRes.json();
    console.error("❌ Listing failed:", err);
    process.exit(1);
  }
  const listData = await listRes.json();
  console.log("✔ Credit Listed successfully. Price:", listData.price, "ETH");

  // 5. Get Listing Details
  console.log("\n--- Step 4: Fetching Listing Details ---");
  const getListRes = await fetch(`${API_BASE}/${tokenId}/listing`);
  const listDetails = await getListRes.json();
  console.log("✔ Listing Details:");
  console.log(`  - Seller: ${listDetails.seller}`);
  console.log(`  - Price: ${listDetails.price} ETH`);
  console.log(`  - Active: ${listDetails.active}`);

  // 6. Purchase Credit
  console.log("\n--- Step 5: Purchasing Credit from Marketplace ---");
  const buyPayload = {
    tokenId,
    price: "0.05",
    buyerPrivateKey: BUYER_KEY
  };
  const buyRes = await fetch(`${API_BASE}/buy`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(buyPayload)
  });

  if (!buyRes.ok) {
    const err = await buyRes.json();
    console.error("❌ Purchase failed:", err);
    process.exit(1);
  }
  const buyData = await buyRes.json();
  console.log("✔ Credit Purchased successfully!");
  console.log("Transaction Hash:", buyData.txHash);

  // 7. Verify Ownership change
  console.log("\n--- Step 6: Verifying New Ownership ---");
  const postBuyRes = await fetch(`${API_BASE}/${tokenId}`);
  const postBuyVal = await postBuyRes.json();
  console.log("✔ Fetched Credit Data after Purchase:");
  console.log(`  - Retired: ${postBuyVal.retired}`);

  // 8. Retire Credit
  console.log("\n--- Step 7: Retiring Credit ---");
  const retirePayload = {
    tokenId,
    ownerPrivateKey: BUYER_KEY
  };
  // Wait briefly to ensure previous transaction is mined
  await new Promise(res => setTimeout(res, 2000));
  const retireRes = await fetch(`${API_BASE}/retire`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(retirePayload)
  });

  if (!retireRes.ok) {
    const err = await retireRes.json();
    console.error("❌ Retirement failed:", err);
    process.exit(1);
  }
  const retireData = await retireRes.json();
  console.log("✔ Credit Retired successfully!");
  console.log("Transaction Hash:", retireData.txHash);

  // 9. Fetch final credit state
  console.log("\n--- Step 8: Fetching Final Credit Details ---");
  const finalRes = await fetch(`${API_BASE}/${tokenId}`);
  const finalVal = await finalRes.json();
  console.log("✔ Final Credit Details:");
  console.log(`  - Retired: ${finalVal.retired}`);
  console.log(`  - Retired By: ${finalVal.retiredBy}`);

  console.log("\n=== API Verification Completed Successfully! ===");
}

run().catch(console.error);
