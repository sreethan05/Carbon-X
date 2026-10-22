import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  buyCredits,
  combinedCredits,
  getMarketplaceListings,
  sendOtp,
} from '../../src/services/api';
import { farmToAnalytics, listingToAuction } from '../../src/utils/farmAnalytics';
import { cn } from '../../src/lib/utils';

// ── fetch stub helper ────────────────────────────────────────────────────────
function jsonResponder(payload, status = 200) {
  const ok = status >= 200 && status < 300;
  return {
    ok,
    status,
    json: async () => payload,
  };
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => jsonResponder({ success: true }, 200)));
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

// ── cn (tailwind-merge) ──────────────────────────────────────────────────────
describe('cn()', () => {
  it('keeps the last conflicting tailwind class', () => {
    expect(cn('p-2', 'bg-red-500', 'bg-green-500')).toBe('p-2 bg-green-500');
  });

  it('keeps non-conflicting classes and drops falsy inputs', () => {
    expect(cn('rounded-3xl', null, undefined, '', 'shadow-card')).toBe(
      'rounded-3xl shadow-card'
    );
  });
});

// ── combinedCredits ──────────────────────────────────────────────────────────
describe('combinedCredits()', () => {
  it('prefers total_credits when present', () => {
    expect(combinedCredits({ carbon_tonnes: 12.34, biodiversity_credits: 3.46, total_credits: 20 }).total).toBe(20);
  });

  it('sums carbon + biodiversity when total_credits absent', () => {
    const r = combinedCredits({ carbon_credits: '4', biodiversity_score: 100 });
    expect(r.carbon).toBe(4);
    expect(r.biodiversity).toBe(2.5); // score/40 derivation
    expect(r.total).toBe(6.5);
  });

  it('parses string columns and rounds to 2 decimals', () => {
    const r = combinedCredits({ carbon_tonnes: '12.34', biodiversity_credits: '3.46', total_credits: '10.5' });
    expect(r).toEqual({ carbon: 12.34, biodiversity: 3.46, total: 10.5 });
  });

  it('is zero-safe for empty rows', () => {
    expect(combinedCredits({})).toEqual({ carbon: 0, biodiversity: 0, total: 0 });
    expect(combinedCredits(null)).toEqual({ carbon: 0, biodiversity: 0, total: 0 });
  });
});

// ── marketplace query building ───────────────────────────────────────────────
describe('getMarketplaceListings()', () => {
  it('drops empty/null/undefined params and keeps real ones', async () => {
    await getMarketplaceListings({ status: 'Active', crop: 'rice', min_price: undefined, search: null, limit: '' });
    expect(fetch).toHaveBeenCalledWith(
      expect.stringMatching(/^\/py-api\/marketplace\/listings\?/),
      expect.anything()
    );
    const url = fetch.mock.calls[0][0];
    expect(url).toContain('status=Active');
    expect(url).toContain('crop=rice');
    expect(url).not.toContain('min_price');
    expect(url).not.toContain('search');
    expect(url).not.toContain('limit');
  });

  it('omits the query string entirely when no params given', async () => {
    await getMarketplaceListings();
    expect(fetch.mock.calls[0][0]).toBe('/py-api/marketplace/listings');
  });
});

// ── POST + auth header + buy payload ─────────────────────────────────────────
describe('sendOtp() and buyCredits()', () => {
  it('posts JSON without Authorization when no token stored', async () => {
    await sendOtp('9999999999');
    const [, init] = fetch.mock.calls[0];
    expect(init.method).toBe('POST');
    expect(init.headers['Content-Type']).toBe('application/json');
    expect(init.headers.Authorization).toBeUndefined();
    expect(init.body).toBe(JSON.stringify({ phone: '9999999999' }));
    expect(fetch.mock.calls[0][0]).toBe('/py-api/send-otp');
  });

  it('attaches Bearer token from localStorage', async () => {
    localStorage.setItem('carbonx_token', 'j-w-t');
    await sendOtp('9999999999');
    expect(fetch.mock.calls[0][1].headers.Authorization).toBe('Bearer j-w-t');
  });

  it('normalizes camelCase buy payloads into snake_case', async () => {
    await buyCredits({ listingId: 'L-1', credits: 2.5, buyerName: 'Acme', unitPrice: 520 });
    const [, init] = fetch.mock.calls[0];
    const body = JSON.parse(init.body);
    expect(body).toEqual({
      listing_id: 'L-1',
      credits: 2.5,
      buyer_name: 'Acme',
      unit_price: 520,
    });
    expect(fetch.mock.calls[0][0]).toBe('/py-api/marketplace/buy');
  });
});

// ── error envelope normalization ─────────────────────────────────────────────
describe('error envelopes', () => {
  it('maps 422 FastAPI detail arrays into a readable message', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponder({ detail: [{ loc: ['body', 'polygon'], msg: 'Invalid geometry' }] }, 422)
      )
    );
    const r = await sendOtp('9999999999');
    expect(r.success).toBe(false);
    expect(r.code).toBe('VALIDATION_ERROR');
    expect(r.message).toContain('polygon: Invalid geometry');
  });

  it('propagates backend-classified codes and messages', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponder({ success: false, code: 'FORBIDDEN', message: 'nope' }, 403)
      )
    );
    // sendOtp response has no stored token -> no unauthorized event noise
    const r = await sendOtp('9999999999');
    expect(r.code).toBe('FORBIDDEN');
    expect(r.message).toBe('nope');
  });

  it('survives non-JSON bodies (proxy 502 HTML) with classified codes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, status: 502, json: async () => { throw new Error('not json'); } }))
    );
    const r = await getMarketplaceListings();
    expect(r.success).toBe(false);
    expect(r.code).toBe('SERVER_ERROR_502');
    expect(r.status).toBe(502);
  });

  it('resolves network failures to a NETWORK envelope instead of throwing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('fetch failed'); }));
    const r = await getMarketplaceListings();
    expect(r.success).toBe(false);
    expect(r.code).toBe('NETWORK');
    expect(r.status).toBe(0);
  });

  it('dispatches carbonx:unauthorized on 401 when a session token exists', async () => {
    localStorage.setItem('carbonx_token', 'expired-token');
    const events = [];
    window.addEventListener('carbonx:unauthorized', (e) => events.push(e.detail), { once: true });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        jsonResponder({ success: false, code: 'UNAUTHORIZED', message: 'Session expired' }, 401)
      )
    );
    const r = await getMarketplaceListings();
    expect(events).toHaveLength(1);
    expect(events[0].code).toBe('UNAUTHORIZED');
    expect(r.success).toBe(false);
    expect(r.message).toBe('Session expired');
  });

  it('does NOT dispatch unauthorized on 401 when no token was stored', async () => {
    let fired = 0;
    window.addEventListener('carbonx:unauthorized', () => fired++);
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => jsonResponder({ success: false, code: 'UNAUTHORIZED' }, 401))
    );
    await getMarketplaceListings();
    expect(fired).toBe(0);
    window.removeEventListener('carbonx:unauthorized', () => fired++);
  });
});

// ── farmAnalytics mappers ────────────────────────────────────────────────────
describe('farmToAnalytics()', () => {
  it('maps a populated row with derived display fields', () => {
    const a = farmToAnalytics({
      id: 'f1',
      name: 'Paddy A',
      crop_type: 'rice',
      ndvi: '0.67',
      soil_moisture: '31.5',
      ai_confidence: '88',
      biodiversity_score: 72,
      total_credits: 12,
      vegetation_health: 'Excellent',
      area_hectares: 2.5,
    });
    expect(a).toMatchObject({
      id: 'f1',
      name: 'Paddy A',
      cropType: 'rice',
      ndvi: 0.67,
      vegetationHealth: 'Excellent',
      aiConfidence: '88%',
      soilCarbon: '31.5% SOC',
      carbonPot: '12 t CO2e/yr',
    });
    expect(a.ndviTrend).toHaveLength(12);
  });

  it('degrades gracefully for an empty row', () => {
    const a = farmToAnalytics({});
    expect(a.name).toBe('My Farm');
    expect(a.cropType).toBe('Mixed Crop');
    expect(a.ndvi).toBe(0);
    expect(a.vegetationHealth).toBe('Sparse');
    expect(a.aiConfidence).toBe('Not available');
  });
});

describe('listingToAuction()', () => {
  it('uses total_credits and formats the rupee bid', () => {
    const card = listingToAuction({ id: 'L9', total_credits: '7.44', price_per_credit: '380', crop: 'mango' });
    expect(card.credits).toBe('7.4 tCO2e');
    expect(card.currentBid).toBe('₹380/credit');
    expect(card.crop).toBe('mango');
  });

  it('falls back to carbon+bio sum and the default price', () => {
    const card = listingToAuction({});
    expect(card.crop).toBe('Carbon Credits');
    expect(card.credits).toBe('0.0 tCO2e');
    expect(card.currentBid).toBe('₹520/credit');
  });
});
