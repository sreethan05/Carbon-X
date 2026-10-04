# CarbonX

> Satellite-verified carbon credit platform connecting Indian farmers directly to carbon markets

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)
[![Status: MVP](https://img.shields.io/badge/Status-MVP-orange)]()

---

## About

CarbonX enables smallholder farmers in India to monetize their carbon sequestration through automated satellite verification. The platform eliminates documentation barriers, verification delays, and intermediary costs that have traditionally locked farmers out of carbon markets.

**Key Features:**
- GPS-based farm boundary registration
- Automated NDVI calculation using Sentinel-2 satellite imagery
- Real-time carbon sequestration estimates
- Farmer dashboard with earnings projections

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React.js, Tailwind CSS, Leaflet.js |
| Backend | Node.js, Express |
| Database | PostgreSQL, PostGIS |
| Satellite Data | Google Earth Engine / Sentinel Hub |
| Auth | JWT |
| Deployment | Vercel (frontend), Render (backend) |

---

## Architecture

```
┌─────────────────┐
│  React Frontend │
│  + Leaflet Map  │
└────────┬────────┘
         │ REST API
         ▼
┌─────────────────┐
│  Express API    │
│  + JWT Auth     │
└────┬───────┬────┘
     │       │
     │       └──────► Satellite API (GEE/Sentinel Hub)
     │                     │
     │                     ▼
     │              ┌──────────────┐
     │              │  ML Service  │
     │              │  NDVI → tCO2e│
     │              └──────┬───────┘
     │                     │
     │                     ▼
     │              ┌──────────────┐
     │              │  Blockchain  │
     │              │ Smart Contract│
     │              │ Mint Credits │
     │              └──────────────┘
     ▼
┌─────────────┐
│ PostgreSQL  │
│ + PostGIS   │
└─────────────┘
```

**Flow:**
1. Farmer draws boundary → Frontend sends GeoJSON to Backend
2. Backend calls Satellite API → fetches NIR/Red bands
3. ML Service calculates NDVI and carbon estimate
4. Smart contract mints carbon credit with unique ID on blockchain
5. Credit + farm data stored in PostgreSQL
6. Dashboard displays NDVI, tCO2e, and on-chain credit ID

---

## Getting Started

### Prerequisites
- Node.js 18+
- PostgreSQL 14+ with PostGIS extension
- Python 3.9+ (for ML service)
- Google Earth Engine account or Sentinel Hub API key
- Blockchain node access (Polygon/Hyperledger)

### Installation

**Backend:**
```bash
git clone https://github.com/yourusername/carbonx.git
cd carbonx/backend

npm install

# Configure environment variables
cp .env.example .env
# Add: DATABASE_URL, JWT_SECRET, GEE_API_KEY, BLOCKCHAIN_RPC_URL

npm run migrate
npm run dev
```

**ML Service:**
```bash
cd ../ml-service

pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Add: GEE_SERVICE_ACCOUNT, SENTINEL_API_KEY

python app.py
```

**Frontend:**
```bash
cd ../frontend

npm install

# Configure environment variables
cp .env.example .env
# Add: REACT_APP_API_URL

npm start
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/register` | Create farmer account |
| POST | `/api/auth/login` | Login (returns JWT) |
| POST | `/api/farms` | Register farm with GeoJSON boundary |
| GET | `/api/farms` | Get all farms for user |
| GET | `/api/farms/:id` | Get farm details |
| POST | `/api/farms/:id/calculate` | Trigger NDVI calculation + credit minting |
| GET | `/api/credits/:creditId` | Get blockchain credit details |

---

## Carbon Calculation & Credit Minting

**Step 1 — NDVI Calculation:**
```
NDVI = (NIR - Red) / (NIR + Red)
```

**Step 2 — Carbon Estimation:**
```
tCO2e = area_hectares × NDVI_mean × 3.67
```
Where 3.67 is the standard above-ground biomass coefficient.

**Step 3 — Blockchain Minting:**
Smart contract mints a carbon credit token with:
- Unique on-chain ID
- Farm coordinates (hashed for privacy)
- tCO2e amount
- Timestamp
- NDVI verification proof

This creates a permanent, tamper-proof record preventing double-counting.

---

## Project Structure

```
carbonx/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── Map/
│   │   │   ├── Dashboard/
│   │   │   └── Auth/
│   │   ├── pages/
│   │   ├── services/
│   │   └── utils/
│   └── package.json
│
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   │   ├── auth.js
│   │   │   ├── farms.js
│   │   │   └── credits.js
│   │   ├── controllers/
│   │   ├── models/
│   │   ├── services/
│   │   │   ├── blockchain.js
│   │   │   └── ml-client.js
│   │   └── middleware/
│   │       └── auth.js
│   ├── migrations/
│   └── package.json
│
├── ml-service/
│   ├── models/
│   │   └── carbon_estimator.py
│   ├── services/
│   │   ├── satellite.py
│   │   └── ndvi_calculator.py
│   ├── app.py
│   └── requirements.txt
│
├── blockchain/
│   ├── contracts/
│   │   └── CarbonCredit.sol
│   ├── scripts/
│   │   └── deploy.js
│   └── hardhat.config.js
│
└── README.md
```

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) for details.

---
