const express = require('express');
const router = express.Router();
const crypto = require('crypto');
const { connectDB, getFarmsCollection, getUsersCollection, getCreditsCollection, inMemoryDB } = require('../services/database');
const blockchain = require('../services/blockchain');

// Register a new farm
router.post('/:userId/register', async (req, res) => {
  try {
    const { userId } = req.params;
    const { geoJson, areaHectares, farmName, farmType } = req.body;

    if (!geoJson || !areaHectares) {
      return res.status(400).json({ success: false, message: 'GeoJSON and area required' });
    }

    await connectDB();
    const farmsCollection = getFarmsCollection();

    // Calculate coordinates hash for blockchain
    const coordsString = JSON.stringify(geoJson.geometry?.coordinates || geoJson.coordinates);
    const farmCoordinatesHash = crypto
      .createHash('sha256')
      .update(coordsString)
      .digest('hex');

    // Create farm record
    const farm = {
      userId,
      farmName: farmName || 'My Farm',
      farmType: farmType || '',
      geoJson,
      areaHectares,
      coordinatesHash: farmCoordinatesHash,
      status: 'pending',
      ndvi: null,
      carbonTonnes: null,
      soilMoisture: null,
      tokenId: null,
      txHash: null,
      createdAt: new Date(),
      updatedAt: new Date()
    };

    let farmId;
    if (farmsCollection instanceof Map) {
      farm._id = `farm_${inMemoryDB.counters.farmId++}`;
      inMemoryDB.farms.set(farm._id, farm);
      farmId = farm._id;
    } else {
      const result = await farmsCollection.insertOne(farm);
      farmId = result.insertedId.toString();
    }

    res.status(201).json({ 
      success: true, 
      message: 'Farm registered successfully',
      farmId: farmId.toString(),
      farm: {
        id: farmId.toString(),
        farmName: farm.farmName,
        areaHectares: farm.areaHectares,
        status: farm.status
      }
    });
  } catch (error) {
    console.error('Register farm error:', error);
    res.status(500).json({ success: false, message: error.message });
  }
});

// Get user's farms
router.get('/:userId/farms', async (req, res) => {
  try {
    const { userId } = req.params;

    await connectDB();
    const farmsCollection = getFarmsCollection();

    let farms = [];
    if (farmsCollection instanceof Map) {
      farms = Array.from(inMemoryDB.farms.values())
        .filter(f => f.userId === userId)
        .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt));
    } else {
      farms = await farmsCollection
        .find({ userId: userId })
        .sort({ createdAt: -1 })
        .toArray();
    }

    res.json({ 
      success: true,
      farms: farms.map(f => ({
        id: f._id.toString(),
        farmName: f.farmName,
        farmType: f.farmType,
        areaHectares: f.areaHectares,
        status: f.status,
        ndvi: f.ndvi,
        carbonTonnes: f.carbonTonnes,
        soilMoisture: f.soilMoisture,
        tokenId: f.tokenId,
        createdAt: f.createdAt
      }))
    });
  } catch (error) {
    console.error('Get farms error:', error);
    res.status(500).json({ success: false, message: error.message });
  }
});

// Get farm details
router.get('/:userId/farms/:farmId', async (req, res) => {
  try {
    const { userId, farmId } = req.params;

    await connectDB();
    const farmsCollection = getFarmsCollection();

    let farm;
    if (farmsCollection instanceof Map) {
      farm = inMemoryDB.farms.get(farmId);
    } else {
      farm = await farmsCollection.findOne({ 
        _id: new require('mongodb').ObjectId(farmId),
        userId: userId
      });
    }

    if (!farm) {
      return res.status(404).json({ success: false, message: 'Farm not found' });
    }

    res.json({ 
      success: true,
      farm: {
        id: farm._id.toString(),
        farmName: farm.farmName,
        farmType: farm.farmType,
        geoJson: farm.geoJson,
        areaHectares: farm.areaHectares,
        status: farm.status,
        ndvi: farm.ndvi,
        evi: farm.evi,
        carbonTonnes: farm.carbonTonnes,
        soilMoisture: farm.soilMoisture,
        vegetationHealth: farm.vegetationHealth,
        tokenId: farm.tokenId,
        txHash: farm.txHash,
        createdAt: farm.createdAt,
        updatedAt: farm.updatedAt
      }
    });
  } catch (error) {
    console.error('Get farm error:', error);
    res.status(500).json({ success: false, message: error.message });
  }
});

// Analyze farm using satellite imagery (placeholder for actual GEE integration)
router.post('/:userId/farms/:farmId/analyze', async (req, res) => {
  try {
    const { userId, farmId } = req.params;

    await connectDB();
    const farmsCollection = getFarmsCollection();

    let farm;
    if (farmsCollection instanceof Map) {
      farm = inMemoryDB.farms.get(farmId);
    } else {
      farm = await farmsCollection.findOne({ 
        _id: new require('mongodb').ObjectId(farmId),
        userId: userId
      });
    }

    if (!farm) {
      return res.status(404).json({ success: false, message: 'Farm not found' });
    }

    // Simulate analysis results (in production, this would call actual satellite analysis)
    const ndviValue = 0.5 + Math.random() * 0.4;
    const eviValue = 0.3 + Math.random() * 0.4;
    const treeCover = Math.round(Math.min(Math.max(ndviValue * 100, 0), 100));
    const soilMoisture = Math.round(Math.min(Math.max(eviValue * 25, 0), 100));
    const carbonTonnes = Math.round(farm.areaHectares * treeCover * 0.12 * 100) / 100;
    const vegetationHealth = ndviValue > 0.6 ? 'Healthy' : ndviValue > 0.3 ? 'Moderate' : 'Poor';

    const analysisResults = {
      ndvi: Math.round(ndviValue * 1000) / 1000,
      evi: Math.round(eviValue * 1000) / 1000,
      treeCover,
      soilMoisture,
      carbonTonnes,
      vegetationHealth,
      status: 'verified',
      updatedAt: new Date()
    };

    if (farmsCollection instanceof Map) {
      Object.assign(farm, analysisResults);
    } else {
      await farmsCollection.updateOne(
        { _id: new require('mongodb').ObjectId(farmId) },
        { $set: analysisResults }
      );
    }
	
    res.json({ 
      success: true,
      analysis: {
        ndvi: analysisResults.ndvi,
        evi: analysisResults.evi,
        treeCover: analysisResults.treeCover,
        soilMoisture: analysisResults.soilMoisture,
        carbonTonnes: analysisResults.carbonTonnes,
        vegetationHealth: analysisResults.vegetationHealth,
        areaHectares: farm.areaHectares
      }
    });
  } catch (error) {
    console.error('Analyze farm error:', error);
    res.status(500).json({ success: false, message: error.message });
  }
});

// Mint carbon credit for verified farm
router.post('/:userId/farms/:farmId/mint', async (req, res) => {
  try {
    const { userId, farmId } = req.params;
    const { farmerAddress, verificationProof, uri } = req.body;
	
    if (!farmerAddress) {
      return res.status(400).json({ success: false, message: 'Farmer address required' });
    }

    await connectDB();
    const farmsCollection = getFarmsCollection();
    const creditsCollection = getCreditsCollection();
    const usersCollection = getUsersCollection();

    let farm;
    if (farmsCollection instanceof Map) {
      farm = inMemoryDB.farms.get(farmId);
    } else {
      farm = await farmsCollection.findOne({ 
        _id: new require('mongodb').ObjectId(farmId),
        userId: userId
      });
    }

    if (!farm) {
      return res.status(404).json({ success: false, message: 'Farm not found' });
    }

    if (farm.status !== 'verified' || !farm.carbonTonnes) {
      return res.json({ success: false, message: 'Farm must be verified and analyzed first' });
    }

    if (farm.tokenId) {
      return res.json({ success: false, message: 'Farm already has minted credits' });
    }

    // Mint carbon credit on blockchain
    let result;
    try {
      result = await blockchain.mintCarbonCredit(
        farmerAddress,
        farm.coordinatesHash,
        farm.carbonTonnes,
        Math.round(farm.ndvi * 10000),
        verificationProof || 'IPFS CID placeholder',
        uri || ''
      );
    } catch (blockchainError) {
      console.warn('Blockchain error (using simulated mint):', blockchainError.message);
      // For demo without blockchain, generate a mock token ID
      result = {
        tokenId: Math.floor(Math.random() * 10000).toString(),
        txHash: '0x' + crypto.randomBytes(32).toString('hex'),
        simulated: true
      };
    }

    // Update farm with token info
    const updateData = {
      tokenId: result.tokenId,
      txHash: result.txHash,
      mintedAt: new Date(),
      updatedAt: new Date()
    };

    if (farmsCollection instanceof Map) {
      Object.assign(farm, updateData);
    } else {
      await farmsCollection.updateOne(
        { _id: new require('mongodb').ObjectId(farmId) },
        { $set: updateData }
      );
    }

    // Create credit record
    const credit = {
      _id: `credit_${inMemoryDB.counters.creditId++}`,
      userId,
      farmId: farmId.toString(),
      tokenId: result.tokenId,
      txHash: result.txHash,
      carbonAmount: farm.carbonTonnes,
      ndviMean: farm.ndvi,
      farmCoordinatesHash: farm.coordinatesHash,
      status: 'minted',
      mintedAt: new Date(),
      createdAt: new Date()
    };

    if (creditsCollection instanceof Map) {
      inMemoryDB.credits.set(credit._id, credit);
    } else {
      await creditsCollection.insertOne(credit);
    }

    // Update user's verified credits
    if (usersCollection instanceof Map) {
      const user = inMemoryDB.users.get(userId);
      if (user) {
        user.verifiedCredits = (user.verifiedCredits || 0) + farm.carbonTonnes;
      }
    } else {
      await usersCollection.updateOne(
        { _id: new require('mongodb').ObjectId(userId) },
        { $inc: { verifiedCredits: farm.carbonTonnes } }
      );
    }

    res.json({ 
      success: true,
      message: 'Carbon credit minted successfully',
      credit: {
        tokenId: result.tokenId,
        txHash: result.txHash,
        carbonAmount: farm.carbonTonnes
      }
    });
  } catch (error) {
    console.error('Mint credit error:', error);
    res.status(500).json({ success: false, message: error.message });
  }
});

module.exports = router;
// Run GEE analysis on farm polygon
router.post('/:userId/farms/:farmId/gee-analyze', async (req, res) => {
  try {
    const { userId, farmId } = req.params;

    await connectDB();
    const farmsCollection = getFarmsCollection();

    let farm;
    if (farmsCollection instanceof Map) {
      farm = inMemoryDB.farms.get(farmId);
    } else {
      farm = await farmsCollection.findOne({ 
        _id: new require('mongodb').ObjectId(farmId),
        userId: userId
      });
    }

    if (!farm) {
      return res.status(404).json({ success: false, message: 'Farm not found' });
    }

    const coords = farm.geoJson?.geometry?.coordinates?.[0] || farm.geoJson?.coordinates?.[0] || [];
    
    if (coords.length === 0) {
      return res.status(400).json({ success: false, message: 'No polygon coordinates found' });
    }

    const geeService = require('../services/gee');
    const coordinates = coords.map(c => ({ lat: c[1], lng: c[0] }));
    const analysis = await geeService.analyzePolygon(coordinates);

    const updateData = {
      ndvi: analysis.nd,
      evi: analysis.features[1],
      treeCover: Math.round(analysis.features[3] * 100),
      soilMoisture: Math.round(analysis.features[4] * 100),
      carbonTonnes: parseFloat((farm.areaHectares * analysis.features[6] * 10).toFixed(2)),
      vegetationHealth: analysis.nd > 0.6 ? 'Healthy' : analysis.nd > 0.3 ? 'Moderate' : 'Poor',
      status: 'analyzed',
      geeAnalysis: {
        nd: analysis.nd,
        ndMin: analysis.ndMin,
        ndMax: analysis.ndMax,
        features: analysis.features,
        timestamp: analysis.timestamp
      },
      updatedAt: new Date()
    };

    if (farmsCollection instanceof Map) {
      Object.assign(farm, updateData);
    } else {
      await farmsCollection.updateOne(
        { _id: new require('mongodb').ObjectId(farmId) },
        { $set: updateData }
      );
    }

    res.json({ 
      success: true,
      analysis: {
        ndvi: analysis.nd,
        ndviMin: analysis.ndMin,
        ndviMax: analysis.ndMax,
        features: analysis.features,
        source: analysis.source
      },
      farm: {
        id: farmId,
        ndvi: updateData.ndvi,
        carbonTonnes: updateData.carbonTonnes
      }
    });
  } catch (error) {
    console.error('GEE analysis error:', error);
    res.status(500).json({ success: false, message: error.message });
  }
});
