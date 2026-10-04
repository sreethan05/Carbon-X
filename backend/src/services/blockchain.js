const fs = require('fs');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../../.env') });
require('dotenv').config({ path: path.join(__dirname, '../../../.env') });

let ethers = null;
let provider = null;
let BLOCKCHAIN_READY = false;

const RPC_URL = process.env.RPC_URL || '';
const CARBON_CREDIT_ADDRESS = process.env.CARBON_CREDIT_ADDRESS || '';
const MARKETPLACE_ADDRESS = process.env.MARKETPLACE_ADDRESS || '';
const MINTER_PRIVATE_KEY = process.env.MINTER_PRIVATE_KEY || '';
const BUYER_PRIVATE_KEY = process.env.BUYER_PRIVATE_KEY || MINTER_PRIVATE_KEY;

if (RPC_URL && CARBON_CREDIT_ADDRESS && MARKETPLACE_ADDRESS && MINTER_PRIVATE_KEY) {
  try {
    ethers = require('ethers').ethers || require('ethers');
    provider = new ethers.JsonRpcProvider(RPC_URL);
    BLOCKCHAIN_READY = true;
    console.log(`Blockchain connected to ${RPC_URL}`);
  } catch (e) {
    console.warn('Blockchain init failed:', e.message);
  }
} else {
  console.warn('Blockchain env vars not set — mint/buy endpoints will return 503 until configured');
}

let carbonCreditAbi = null;
let marketplaceAbi = null;

if (BLOCKCHAIN_READY) {
  try {
    const ccArtifact = JSON.parse(fs.readFileSync(
      path.join(__dirname, '../../../blockchain/artifacts/contracts/CarbonCredit.sol/CarbonCredit.json'), 'utf8'
    ));
    carbonCreditAbi = ccArtifact.abi;
    const mpArtifact = JSON.parse(fs.readFileSync(
      path.join(__dirname, '../../../blockchain/artifacts/contracts/CarbonMarketplace.sol/CarbonMarketplace.json'), 'utf8'
    ));
    marketplaceAbi = mpArtifact.abi;
  } catch {
    console.warn('Smart contract artifacts not found — run: cd blockchain && npx hardhat compile');
    BLOCKCHAIN_READY = false;
  }
}

function requireChain() {
  if (!BLOCKCHAIN_READY) {
    throw new Error('Blockchain not configured. Set RPC_URL, contract addresses, and MINTER_PRIVATE_KEY in backend/.env');
  }
}

const getMinterWallet = () => {
  requireChain();
  return new ethers.Wallet(MINTER_PRIVATE_KEY, provider);
};

async function mintCarbonCredit(toAddress, farmCoordinatesHash, carbonAmount, ndviMean, verificationProof, uri) {
  requireChain();
  const minter = getMinterWallet();
  const recipient = toAddress || minter.address;
  const contract = new ethers.Contract(CARBON_CREDIT_ADDRESS, carbonCreditAbi, minter);
  const amountWei = ethers.parseEther(String(carbonAmount));
  const nonce = await provider.getTransactionCount(minter.address, 'pending');
  const tx = await contract.mint(recipient, farmCoordinatesHash, amountWei, ndviMean, verificationProof, uri, { nonce });
  const receipt = await tx.wait();
  const log = receipt.logs.find(x => x.fragment && x.fragment.name === 'CarbonCreditMinted');
  return { txHash: tx.hash, tokenId: log ? log.args[0].toString() : null, owner: recipient };
}

async function listCreditOnMarketplace(tokenId, price, sellerPrivateKey) {
  requireChain();
  const sellerKey = sellerPrivateKey || MINTER_PRIVATE_KEY;
  const seller = new ethers.Wallet(sellerKey, provider);
  const creditContract = new ethers.Contract(CARBON_CREDIT_ADDRESS, carbonCreditAbi, seller);
  const mpContract = new ethers.Contract(MARKETPLACE_ADDRESS, marketplaceAbi, seller);
  const priceWei = ethers.parseEther(String(price));
  let nonce = await provider.getTransactionCount(seller.address, 'pending');
  const approveTx = await creditContract.approve(MARKETPLACE_ADDRESS, tokenId, { nonce: nonce++ });
  await approveTx.wait();
  const listTx = await mpContract.listCredit(tokenId, priceWei, { nonce: nonce++ });
  await listTx.wait();
  return { txHash: listTx.hash, tokenId, price };
}

async function purchaseCredit(tokenId, value, buyerPrivateKey) {
  requireChain();
  const buyerKey = buyerPrivateKey || BUYER_PRIVATE_KEY;
  if (!buyerKey) throw new Error('No buyer wallet configured (BUYER_PRIVATE_KEY)');
  const buyer = new ethers.Wallet(buyerKey, provider);
  const mpContract = new ethers.Contract(MARKETPLACE_ADDRESS, marketplaceAbi, buyer);
  const paymentWei = ethers.parseEther(String(value));
  const nonce = await provider.getTransactionCount(buyer.address, 'pending');
  const tx = await mpContract.buyCredit(tokenId, { value: paymentWei, nonce });
  await tx.wait();
  return { txHash: tx.hash, tokenId };
}

async function retireCredit(tokenId, ownerPrivateKey) {
  requireChain();
  const ownerKey = ownerPrivateKey || MINTER_PRIVATE_KEY;
  const owner = new ethers.Wallet(ownerKey, provider);
  const contract = new ethers.Contract(CARBON_CREDIT_ADDRESS, carbonCreditAbi, owner);
  const nonce = await provider.getTransactionCount(owner.address, 'pending');
  const tx = await contract.retire(tokenId, { nonce });
  await tx.wait();
  return { txHash: tx.hash, tokenId };
}

async function getCreditData(tokenId) {
  requireChain();
  const contract = new ethers.Contract(CARBON_CREDIT_ADDRESS, carbonCreditAbi, provider);
  const data = await contract.getCreditData(tokenId);
  return {
    tokenId: tokenId.toString(),
    farmCoordinatesHash: data.farmCoordinatesHash,
    carbonAmount: ethers.formatEther(data.carbonAmount),
    ndviMean: data.ndviMean.toString(),
    timestamp: new Date(Number(data.timestamp) * 1000).toISOString(),
    verificationProof: data.verificationProof,
    retired: data.retired,
    retiredBy: data.retiredBy,
  };
}

module.exports = {
  BLOCKCHAIN_READY,
  mintCarbonCredit,
  listCreditOnMarketplace,
  purchaseCredit,
  retireCredit,
  getCreditData,
};
