# CarbonX — integrated stack (root `src/`, not `frontend/`)

The main app lives at the **repository root** (`npm run dev` → Vite on port **5000**). The `frontend/` folder is the old standalone map UI; the GEE map is now `src/components/GEEMap.jsx`.

## 1. Supabase (CarbonX project)

1. Open [Supabase Dashboard](https://supabase.com/dashboard/project/rbdyzeuucgqkhlikbpnd) → **Settings → API**.
2. Copy **Project URL**, **anon key**, and **service_role key**.

**Root `.env`:**

```env
VITE_SUPABASE_URL=https://rbdyzeuucgqkhlikbpnd.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-or-publishable-key>
```

**`backend/.env`:**

```env
SUPABASE_URL=https://rbdyzeuucgqkhlikbpnd.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
GEE_PROJECT=carbonsetu-496709
```

Schema is already applied (`profiles`, `farms`, `marketplace_listings`, `otp_codes`).

## 2. Python API (GEE + ML + auth + Supabase)

```bash
cd backend
pip install -r requirements.txt
# Earth Engine: earthengine authenticate
uvicorn app.main:app --reload --port 8000
```

## 3. Blockchain API (optional)

```bash
cd backend
npm install
npm run dev   # port 3001
```

Set `RPC_URL`, contract addresses, and `MINTER_PRIVATE_KEY` in `backend/.env` for live chain; otherwise demo minting works.

## 4. Frontend

```bash
npm install
npm run dev   # http://localhost:5000
```

Proxies: `/py-api` → Python :8000, `/bc-api` → Node :3001.

## Flow

1. Register / login (phone OTP; dev OTP printed in API console).
2. **Farm map** — GEE satellite tiles + place search + draw → **Scan AI** (Sentinel-2 via Earth Engine + biodiversity ML).
3. **Dashboard** — combined carbon + biodiversity credits per farm.
4. **Create listing** — mint (blockchain) + save listing (Supabase).
5. **Marketplace** — browse farmers and buy/bid.
# CarbonX — integrated stack (root `src/`, not `frontend/`)

The main app lives at the **repository root** (`npm run dev` → Vite on port **5000**). The `frontend/` folder is the old standalone map UI; the GEE map is now `src/components/GEEMap.jsx`.

## 1. Supabase (CarbonX project)

1. Open [Supabase Dashboard](https://supabase.com/dashboard/project/rbdyzeuucgqkhlikbpnd) → **Settings → API**.
2. Copy **Project URL**, **anon key**, and **service_role key**.

**Root `.env`:**

```env
VITE_SUPABASE_URL=https://rbdyzeuucgqkhlikbpnd.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-or-publishable-key>
```

**`backend/.env`:**

```env
SUPABASE_URL=https://rbdyzeuucgqkhlikbpnd.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
GEE_PROJECT=carbonsetu-496709
```

Schema is already applied (`profiles`, `farms`, `marketplace_listings`, `otp_codes`).

## 2. Python API (GEE + ML + auth + Supabase)

```bash
cd backend
pip install -r requirements.txt
# Earth Engine: earthengine authenticate
uvicorn app.main:app --reload --port 8000
```

## 3. Blockchain API (optional)

```bash
cd backend
npm install
npm run dev   # port 3001
```

Set `RPC_URL`, contract addresses, and `MINTER_PRIVATE_KEY` in `backend/.env` for live chain; otherwise demo minting works.

## 4. Frontend

```bash
npm install
npm run dev   # http://localhost:5000
```

Proxies: `/py-api` → Python :8000, `/bc-api` → Node :3001.

## Flow

1. Register / login (phone OTP; dev OTP printed in API console).
2. **Farm map** — GEE satellite tiles + place search + draw → **Scan AI** (Sentinel-2 via Earth Engine + biodiversity ML).
3. **Dashboard** — combined carbon + biodiversity credits per farm.
4. **Create listing** — mint (blockchain) + save listing (Supabase).
5. **Marketplace** — browse farmers and buy/bid.
# CarbonX — integrated stack (root `src/`, not `frontend/`)

The main app lives at the **repository root** (`npm run dev` → Vite on port **5000**). The `frontend/` folder is the old standalone map UI; the GEE map is now `src/components/GEEMap.jsx`.

## 1. Supabase (CarbonX project)

1. Open [Supabase Dashboard](https://supabase.com/dashboard/project/rbdyzeuucgqkhlikbpnd) → **Settings → API**.
2. Copy **Project URL**, **anon key**, and **service_role key**.

**Root `.env`:**

```env
VITE_SUPABASE_URL=https://rbdyzeuucgqkhlikbpnd.supabase.co
VITE_SUPABASE_ANON_KEY=<anon-or-publishable-key>
```

**`backend/.env`:**

```env
SUPABASE_URL=https://rbdyzeuucgqkhlikbpnd.supabase.co
SUPABASE_ANON_KEY=<anon-key>
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
GEE_PROJECT=carbonsetu-496709
TWILIO_ACCOUNT_SID=<sid>
TWILIO_AUTH_TOKEN=<token>
TWILIO_PHONE_NUMBER=<twilio-number>
```

Schema is already applied (`profiles`, `farms`, `marketplace_listings`, `otp_codes`).

## 2. Python API (GEE + ML + auth + Supabase)

```bash
cd backend
pip install -r requirements.txt
# Earth Engine: earthengine authenticate
uvicorn app.main:app --reload --port 8000
```

## 3. Blockchain API (optional)

```bash
cd backend
npm install
npm run dev   # port 3001
```

Set `RPC_URL`, contract addresses, and `MINTER_PRIVATE_KEY` in `backend/.env` for live chain; otherwise demo minting works.

## 4. Frontend

```bash
npm install
npm run dev   # http://localhost:5000
```

Proxies: `/py-api` → Python :8000, `/bc-api` → Node :3001.

## Flow

1. Register / login (phone OTP delivered through Twilio).
2. **Farm map** — GEE satellite tiles + place search + draw → **Scan AI** (Sentinel-2 via Earth Engine + biodiversity ML).
3. **Dashboard** — combined carbon + biodiversity credits per farm.
4. **Create listing** — mint (blockchain) + save listing (Supabase).
5. **Marketplace** — browse farmers and buy/bid.
