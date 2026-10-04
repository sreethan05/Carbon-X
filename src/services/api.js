const PY = '/py-api';
const BC = '/bc-api';

function authHeaders() {
  const token = localStorage.getItem('carbonx_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function post(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function patch(url, body) {
  const res = await fetch(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
  return res.json();
}

async function get(url) {
  const res = await fetch(url, { headers: authHeaders() });
  return res.json();
}

// ── Auth ──

export async function sendOtp(phone) {
  return post(`${PY}/send-otp`, { phone });
}

export async function verifyRegistrationOtp(phone, otp) {
  return post(`${PY}/register/verify-otp`, { phone, otp });
}

export async function sendLoginOtp(phone) {
  return post(`${PY}/login/send-otp`, { phone });
}

export async function registerUser(payload) {
  return post(`${PY}/register`, payload);
}

export async function loginUser(phone, otp) {
  return post(`${PY}/login`, { phone, otp });
}

export async function getMe() {
  return get(`${PY}/me`);
}

export async function updateProfile(fields) {
  return patch(`${PY}/profile`, fields);
}

// Voice assistant

export async function sendVoiceTextQuery(payload) {
  return post(`${PY}/api/v1/voice/text-query`, payload);
}

export async function sendVoiceAudioQuery({ file, language_code, session_id }) {
  const form = new FormData();
  form.append('file', file);
  if (language_code) form.append('language_code', language_code);
  if (session_id) form.append('session_id', session_id);
  const res = await fetch(`${PY}/api/v1/voice/query`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  return res.json();
}

// ── KYC ──

export async function verifyAadhaar(payload) {
  return post(`${PY}/verify-aadhaar`, payload);
}

export async function verifyLandDocument(payload) {
  return post(`${PY}/verify-land`, payload);
}

export async function getKycStatus(phone) {
  return get(`${PY}/kyc/status/${phone}`);
}

// ── Farms & satellite (GEE + ML) ──

export async function analyzeFarm(geojson, farmName, cropType, irrigation) {
  return post(`${PY}/analyze`, {
    geojson,
    farm_name: farmName,
    crop_type: cropType,
    irrigation,
  });
}

export async function saveFarm(farm) {
  return post(`${PY}/save-farm`, { farm });
}

export async function predictBiodiversity(longitude, latitude) {
  const res = await fetch(
    `${PY}/predict?longitude=${longitude}&latitude=${latitude}`,
    { headers: authHeaders() }
  );
  return res.json();
}

// ── Marketplace ──

// params: { status, crop, location, farmer_phone, farm_id, listing_model,
//           min_price, max_price, min_credits, max_credits, search,
//           sort, order, limit, offset }  (empty/null/undefined values are dropped)
export async function getMarketplaceListings(params = {}) {
  const qs = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString();
  return get(`${PY}/marketplace/listings${qs ? `?${qs}` : ''}`);
}

export async function createMarketplaceListing(payload) {
  return post(`${PY}/marketplace/listings`, payload);
}

export async function placeListingBid(listingId, bidAmount, bidderName) {
  return post(`${PY}/marketplace/listings/${listingId}/bid`, { bid_amount: bidAmount, bidder_name: bidderName });
}

export async function buyCredits(payload) {
  return post(`${PY}/marketplace/buy`, payload);
}

export async function autoMatchCredits(targetVolume, priority = 'lowest_price') {
  return post(`${PY}/marketplace/auto-match`, { target_volume: targetVolume, priority });
}

// ── Certificates & wallet ──

export async function getWallet() {
  return get(`${PY}/wallet`);
}

export async function getCertificates() {
  return get(`${PY}/certificates`);
}

export async function retireCertificate(certId, scope) {
  const qs = scope ? `?scope=${encodeURIComponent(scope)}` : '';
  return post(`${PY}/certificates/${certId}/retire${qs}`, {});
}

// ── Farm passport & history ──

export async function getFarmPassport(farmId) {
  return get(`${PY}/passport/${farmId}`);
}

export async function getNdviHistory(farmId) {
  return get(`${PY}/farm/${farmId}/ndvi-history`);
}

// ── FPO ──

export async function fpoLogin(registrationNo, password) {
  return post(`${PY}/fpo/login`, { registration_no: registrationNo, password });
}

export async function getFpos() {
  return get(`${PY}/fpos`);
}

export async function getFpoFarmers() {
  return get(`${PY}/fpo/farmers`);
}

export async function getFpoPending() {
  return get(`${PY}/fpo/pending`);
}

export async function getFpoFlagged() {
  return get(`${PY}/fpo/flagged`);
}

export async function fpoOnboardFarmer(payload) {
  return post(`${PY}/fpo/onboard`, payload);
}

export async function fpoConfirmFarm(farmId) {
  return post(`${PY}/fpo/confirm/${farmId}`, {});
}

export async function fpoReviewFarm(farmId, payload) {
  return post(`${PY}/fpo/review/${farmId}`, payload);
}

// ── Corporate ──

export async function corporateLogin(name, password) {
  return post(`${PY}/corporate/login`, { name, password });
}

// ── Documents ──

export async function parsePahaniDocument(file) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${PY}/documents/parse-pahani`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  return res.json();
}

// ── Blockchain ──

export async function mintCredit(payload) {
  return post(`${BC}/api/credits/mint`, payload);
}

export async function listCredit(tokenId, price) {
  return post(`${BC}/api/credits/list`, { tokenId, price });
}

export async function buyCredit(tokenId, price, buyerPrivateKey) {
  return post(`${BC}/api/credits/buy`, { tokenId, price, buyerPrivateKey });
}

export async function retireCredit(tokenId, ownerPrivateKey) {
  return post(`${BC}/api/credits/retire`, { tokenId, ownerPrivateKey });
}

export async function getCreditData(tokenId) {
  return get(`${BC}/api/credits/${tokenId}`);
}

export async function getBlockchainHealth() {
  try {
    const res = await fetch(`${BC}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

/** Combined carbon + biodiversity credits from farm or analysis row */
export function combinedCredits(row) {
  const carbon = parseFloat(row?.carbon_tonnes ?? row?.carbon_credits ?? 0) || 0;
  const bio =
    parseFloat(row?.biodiversity_credits ?? 0) ||
    (parseFloat(row?.biodiversity_score ?? 0) / 40) ||
    0;
  const total = parseFloat(row?.total_credits ?? 0) || carbon + bio;
  return {
    carbon: Math.round(carbon * 100) / 100,
    biodiversity: Math.round(bio * 100) / 100,
    total: Math.round(total * 100) / 100,
  };
}
