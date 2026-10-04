const express = require('express');
const router = express.Router();
const blockchain = require('../services/blockchain');

function chainError(res, error, fallback) {
  const msg = error.message || fallback;
  const status = msg.includes('not configured') ? 503 : 500;
  console.error(fallback, error);
  return res.status(status).json({ error: msg });
}

router.post('/mint', async (req, res) => {
  try {
    const { farmerAddress, farmCoordinatesHash, carbonAmount, ndviMean, verificationProof, uri } = req.body;
    if (!farmCoordinatesHash || carbonAmount == null || ndviMean == null || !verificationProof || !uri) {
      return res.status(400).json({ error: 'Missing required fields' });
    }
    const result = await blockchain.mintCarbonCredit(
      farmerAddress || null,
      farmCoordinatesHash,
      carbonAmount,
      ndviMean,
      verificationProof,
      uri
    );
    res.status(201).json({
      message: 'Carbon credit minted successfully',
      tokenId: result.tokenId,
      txHash: result.txHash,
      owner: result.owner,
    });
  } catch (error) {
    return chainError(res, error, 'Minting error');
  }
});

router.post('/list', async (req, res) => {
  try {
    const { tokenId, price, sellerPrivateKey } = req.body;
    if (tokenId === undefined || !price) {
      return res.status(400).json({ error: 'Missing tokenId or price' });
    }
    const result = await blockchain.listCreditOnMarketplace(tokenId, price, sellerPrivateKey || null);
    res.status(200).json({
      message: 'Carbon credit listed on chain',
      tokenId: result.tokenId,
      price: result.price,
      txHash: result.txHash,
    });
  } catch (error) {
    return chainError(res, error, 'Listing error');
  }
});

router.post('/buy', async (req, res) => {
  try {
    const { tokenId, price, buyerPrivateKey } = req.body;
    if (tokenId === undefined || !price) {
      return res.status(400).json({ error: 'Missing tokenId or price' });
    }
    const result = await blockchain.purchaseCredit(tokenId, price, buyerPrivateKey || null);
    res.status(200).json({
      message: 'Carbon credit purchased successfully',
      tokenId: result.tokenId,
      txHash: result.txHash,
    });
  } catch (error) {
    return chainError(res, error, 'Purchase error');
  }
});

router.post('/retire', async (req, res) => {
  try {
    const { tokenId, ownerPrivateKey } = req.body;
    if (tokenId === undefined) {
      return res.status(400).json({ error: 'Missing tokenId' });
    }
    const result = await blockchain.retireCredit(tokenId, ownerPrivateKey || null);
    res.status(200).json({
      message: 'Carbon credit retired successfully',
      tokenId: result.tokenId,
      txHash: result.txHash,
    });
  } catch (error) {
    return chainError(res, error, 'Retirement error');
  }
});

router.get('/:tokenId', async (req, res) => {
  try {
    const data = await blockchain.getCreditData(req.params.tokenId);
    res.status(200).json(data);
  } catch (error) {
    return chainError(res, error, 'Fetch credit error');
  }
});

module.exports = router;
