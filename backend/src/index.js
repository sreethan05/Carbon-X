const express = require('express');
const cors = require('cors');
require('dotenv').config();

const creditsRouter = require('./routes/credits');

const app = express();
const PORT = process.env.PORT || 3001;

app.use(cors());
app.use(express.json());

app.use('/api/credits', creditsRouter);

const blockchain = require('./services/blockchain');

app.get('/health', (req, res) => {
  res.status(200).json({
    status: 'UP',
    blockchain: blockchain.BLOCKCHAIN_READY,
    timestamp: new Date(),
  });
});

app.listen(PORT, 'localhost', () => {
  console.log(`CarbonX blockchain backend running on port ${PORT}`);
});
