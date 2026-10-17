// API bases: Vite dev proxies /py-api and /bc-api; in production set
// VITE_PY_API_BASE / VITE_BC_API_BASE (e.g. https://api.example.com).
export const PY_API_BASE = (import.meta.env.VITE_PY_API_BASE || '/py-api').replace(/\/+$/, '');
const BC = (import.meta.env.VITE_BC_API_BASE || '/bc-api').replace(/\/+$/, '');
const PY = PY_API_BASE;

function authHeaders() {
  try {
    const token = typeof window !== 'undefined' ? localStorage.getItem('carbonx_token') : null;
    if (token && token !== 'null' && token !== 'undefined' && token.trim() !== '') {
      return { Authorization: `Bearer ${token.trim()}` };
    }
  } catch {
    // Storage access might be restricted in some browser privacy modes
  }
  return {};
}

function notifyUnauthorized(status, code, message) {
  if (typeof window !== 'undefined') {
    try {
      const token = localStorage.getItem('carbonx_token');
      // Only dispatch if a session token was present (avoid false triggers on initial unauthenticated calls)
      if (token && token !== 'null' && token !== 'undefined') {
        window.dispatchEvent(
          new CustomEvent('carbonx:unauthorized', {
            detail: { status, code: code || 'UNAUTHORIZED', message },
          })
        );
      }
    } catch {
      /* ignore */
    }
  }
}

function extractErrorMessage(data, status) {
  if (data?.message && typeof data.message === 'string' && data.message.trim() !== '') {
    return data.message;
  }
  if (typeof data?.detail === 'string' && data.detail.trim() !== '') {
    return data.detail;
  }
  if (Array.isArray(data?.detail)) {
    // Format FastAPI 422 validation errors into clean human-readable text
    const parts = data.detail
      .map((item) => {
        if (!item) return '';
        if (typeof item === 'string') return item;
        const loc = Array.isArray(item.loc)
          ? item.loc.filter((x) => x !== 'body' && x !== '__root__').join('.')
          : '';
        const msg = item.msg || item.message || JSON.stringify(item);
        return loc ? `${loc}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (parts.length > 0) return parts.join(', ');
  }
  if (data?.error && typeof data.error === 'string' && data.error.trim() !== '') {
    return data.error;
  }
  if (status === 401) return 'Session expired or unauthorized. Please sign in again.';
  if (status === 403) return 'You do not have permission to perform this action.';
  if (status === 404) return 'The requested resource was not found.';
  if (status === 422) return 'Validation error. Please verify the submitted data.';
  if (status >= 500) return `Server error (HTTP ${status}). Please try again later.`;
  return `Request failed (HTTP ${status})`;
}

function extractErrorCode(data, status) {
  if (data?.code && typeof data.code === 'string' && data.code.trim() !== '') {
    return data.code;
  }
  if (status === 401) return 'UNAUTHORIZED';
  if (status === 403) return 'FORBIDDEN';
  if (status === 404) return 'NOT_FOUND';
  if (status === 422) return 'VALIDATION_ERROR';
  if (status >= 500) return `SERVER_ERROR_${status}`;
  return `HTTP_${status}`;
}

// Normalize every response into a JSON envelope:
//   { success, code?, message?, status?, ...payload }
// Non-JSON bodies (proxy 502 HTML, empty 204) and network failures resolve to
// { success: false, code: 'NETWORK'|'NON_JSON', message } instead of throwing,
// so callers can branch on `success` exactly like for backend envelopes.
async function parseResponse(res) {
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }

  // Handle 401 UNAUTHORIZED globally to notify AuthContext for auto-logout
  if (res.status === 401 || (data && typeof data === 'object' && data.code === 'UNAUTHORIZED')) {
    notifyUnauthorized(res.status, data?.code, extractErrorMessage(data, res.status));
  }

  if (data && typeof data === 'object') {
    // Array response safety
    if (Array.isArray(data)) {
      if (!res.ok) {
        return {
          success: false,
          code: extractErrorCode(null, res.status),
          message: extractErrorMessage(null, res.status),
          data,
          status: res.status,
        };
      }
      return { success: true, data, status: res.status };
    }

    // Error response normalization
    if (!res.ok || data.success === false) {
      const code = extractErrorCode(data, res.status);
      const message = extractErrorMessage(data, res.status);
      return {
        ...data,
        success: false,
        code,
        message,
        status: res.status,
      };
    }

    return {
      success: true,
      ...data,
      status: res.status,
    };
  }

  // Successful empty response (e.g. 204 No Content, 200 with empty body)
  if (res.ok) {
    return {
      success: true,
      status: res.status,
    };
  }

  return {
    success: false,
    code: extractErrorCode(null, res.status),
    message: extractErrorMessage(null, res.status),
    status: res.status,
  };
}

async function request(url, options = {}) {
  let res;
  try {
    res = await fetch(url, options);
  } catch {
    return {
      success: false,
      code: 'NETWORK',
      message: 'Cannot reach the server. Check your connection and try again.',
      status: 0,
    };
  }
  return parseResponse(res);
}

async function post(url, body) {
  return request(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
}

async function patch(url, body) {
  return request(url, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  });
}

async function get(url) {
  return request(url, { headers: authHeaders() });
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
  return request(`${PY}/api/v1/voice/query`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
}

// ── KYC ──

export async function verifyAadhaar(payload) {
  return post(`${PY}/verify-aadhaar`, payload);
}

export async function verifyLandDocument(payload) {
  return post(`${PY}/verify-land`, payload);
}

export async function getKycStatus(phone) {
  return get(`${PY}/kyc/status/${encodeURIComponent(phone)}`);
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
  return get(`${PY}/predict?longitude=${encodeURIComponent(longitude)}&latitude=${encodeURIComponent(latitude)}`);
}

export async function lookupLandRegistry(surveyNumber) {
  return get(`${PY}/land/registry/${encodeURIComponent(surveyNumber)}`);
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
  return post(`${PY}/marketplace/listings/${encodeURIComponent(listingId)}/bid`, { bid_amount: bidAmount, bidder_name: bidderName });
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
  return post(`${PY}/certificates/${encodeURIComponent(certId)}/retire${qs}`, {});
}

// ── Trust & transparency (split engine, hash ledger, earnings calculator) ──

export async function calculateEarnings(payload) {
  return post(`${PY}/farms/earnings-calculator`, payload);
}

export async function getFarmLedger(farmId) {
  return get(`${PY}/ledger/${encodeURIComponent(farmId)}`);
}

export async function demoLogin(phone) {
  return post(`${PY}/demo/login`, { phone });
}

export async function runMonitoring() {
  return post(`${PY}/monitor/run`, {});
}

// ── Farm passport & history ──

export async function getFarmPassport(farmId) {
  return get(`${PY}/passport/${encodeURIComponent(farmId)}`);
}

export async function getNdviHistory(farmId) {
  return get(`${PY}/farm/${encodeURIComponent(farmId)}/ndvi-history`);
}

// ── Evidence capture (practice photos & geotags) ──

export async function uploadEvidencePhoto(farmId, file, { latitude, longitude, capturedAt } = {}) {
  const form = new FormData();
  form.append('file', file);
  if (latitude !== undefined && latitude !== null && latitude !== '') form.append('latitude', latitude.toString());
  if (longitude !== undefined && longitude !== null && longitude !== '') form.append('longitude', longitude.toString());
  if (capturedAt) form.append('captured_at', capturedAt);
  return request(`${PY}/farms/${encodeURIComponent(farmId)}/evidence/photo`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
}

export async function addEvidenceGeotag(farmId, payload) {
  return post(`${PY}/farms/${encodeURIComponent(farmId)}/evidence/geotag`, payload);
}

export async function getFarmEvidence(farmId) {
  return get(`${PY}/farms/${encodeURIComponent(farmId)}/evidence`);
}

export function getEvidencePhotoUrl(farmId, sha256) {
  return `${PY}/farms/${encodeURIComponent(farmId)}/evidence/photo/${encodeURIComponent(sha256)}`;
}

// ── Payments & Checkout ──

export async function getPaymentsConfig() {
  return get(`${PY}/payments/config`);
}

export async function createCheckout(payload) {
  return post(`${PY}/payments/checkout`, payload);
}

// ── FPO ──

export async function fpoLogin(registrationNo) {
  // FPO sign-in is registration_no -> OTP to the linked officer's phone;
  // the password step no longer exists (see POST /fpo/login).
  return post(`${PY}/fpo/login`, { registration_no: registrationNo });
}

export async function getFpos() {
  return get(`${PY}/fpos`);
}

export async function getOpsSummary() {
  return get(`${PY}/ops/summary`);
}

export async function getGroundTruthEval() {
  return get(`${PY}/ops/ground-truth/eval`);
}

export async function getSystemHealth() {
  return get(`${PY}/health`);
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
  return post(`${PY}/fpo/confirm/${encodeURIComponent(farmId)}`, {});
}

export async function fpoReviewFarm(farmId, payload) {
  return post(`${PY}/fpo/review/${encodeURIComponent(farmId)}`, payload);
}

// ── Corporate ──

export async function corporateLogin(name, password) {
  return post(`${PY}/corporate/login`, { name, password });
}

// ── Documents ──

export async function parsePahaniDocument(file) {
  const form = new FormData();
  form.append('file', file);
  return request(`${PY}/documents/parse-pahani`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
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
  return get(`${BC}/api/credits/${encodeURIComponent(tokenId)}`);
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
  const total = parseFloat(row?.total_credits ?? 0) || (carbon + bio);
  return {
    carbon: Number.isFinite(carbon) ? Math.round(carbon * 100) / 100 : 0,
    biodiversity: Number.isFinite(bio) ? Math.round(bio * 100) / 100 : 0,
    total: Number.isFinite(total) ? Math.round(total * 100) / 100 : 0,
  };
}
