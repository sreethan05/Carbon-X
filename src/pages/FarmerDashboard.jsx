import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  MapPin,
  ShieldCheck,
  Wallet,
  AlertTriangle,
  PlusCircle,
  ShoppingCart,
  TrendingUp,
  BookOpen,
  AlertCircle,
} from 'lucide-react';
import VerificationBadge from '../components/VerificationBadge';
import EarningsCalculator from '../components/EarningsCalculator';
import { useAuth } from '../context/AuthContext';
import { getMarketplaceListings } from '../services/api';

export default function FarmerDashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, farms: realFarms, refreshUser } = useAuth();

  useEffect(() => {
    refreshUser();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const navState = location.state || {};

  // Real listing prices for this farmer's farms (used for the revenue estimate
  // — no fixed benchmark price is fabricated when no listing exists).
  const [listingPrices, setListingPrices] = useState({});

  const targetPhone = navState.farmerPhone || user?.phone;

  useEffect(() => {
    let cancelled = false;
    async function loadPrices() {
      if (!targetPhone) return;
      const res = await getMarketplaceListings({ farmer_phone: targetPhone, status: 'all', limit: 200 });
      if (cancelled || !res || !res.success) return;
      const prices = {};
      (res.listings || []).forEach((l) => {
        if (l.farm_id && l.price_per_credit != null) prices[l.farm_id] = l.price_per_credit;
      });
      setListingPrices(prices);
    }
    loadPrices();
    return () => {
      cancelled = true;
    };
  }, [targetPhone]);

  // Real farms from GET /me (Supabase), mapped to the dashboard's display shape
  const farms = (realFarms || []).map((f, idx) => {
    const status = String(f.status || 'PENDING').toLowerCase();
    const flagged = status === 'flagged';
    const pending = flagged || status === 'pending' || !f.badge;
    return {
      id: f.id,
      surveyNumber: (f.name || `FARM-${idx + 1}`).replace(/^Survey /, ''),
      areaHectares: f.area_hectares ?? null,
      crop: f.crop_type || '—',
      badge: f.badge || 'PENDING',
      credits: f.total_credits || 0,
      ndvi: f.ndvi ?? null,
      bioScore: f.biodiversity_score ? (f.biodiversity_score / 10).toFixed(1) : null,
      status: status.toUpperCase(),
      flagged,
      isPending: pending,
    };
  });

  const [selectedFarmIndex, setSelectedFarmIndex] = useState(0);

  // Synchronize selected farm with route navigation state if explicit farmId or surveyNumber was passed
  useEffect(() => {
    if (farms.length > 0 && (navState.surveyNumber || navState.farmId)) {
      const cleanNavSurvey = navState.surveyNumber
        ? String(navState.surveyNumber).replace(/^Survey /, '').trim()
        : '';
      const matchIdx = farms.findIndex((f) => {
        if (navState.farmId && f.id === navState.farmId) return true;
        if (
          cleanNavSurvey &&
          (f.surveyNumber === cleanNavSurvey || f.surveyNumber.toLowerCase() === cleanNavSurvey.toLowerCase())
        ) {
          return true;
        }
        return false;
      });
      if (matchIdx !== -1) {
        setSelectedFarmIndex(matchIdx);
      }
    }
  }, [navState.surveyNumber, navState.farmId, farms.length]); // eslint-disable-line react-hooks/exhaustive-deps

  // Bound index safely
  const activeIndex = selectedFarmIndex >= 0 && selectedFarmIndex < farms.length ? selectedFarmIndex : 0;

  // If navigated with explicit farmer details state (e.g. from FPO Dashboard)
  const farmerName = navState.farmerName || user?.name || 'Farmer';
  const village = navState.village || user?.village || 'Your village';
  const district = navState.district || user?.district || 'Telangana';

  const currentFarm = farms[activeIndex] || {
    id: null,
    surveyNumber: '—',
    areaHectares: null,
    crop: '—',
    badge: 'PENDING',
    credits: 0,
    ndvi: null,
    bioScore: null,
    status: 'PENDING',
    flagged: false,
    isPending: true,
  };

  const isPending = currentFarm.isPending || currentFarm.badge === 'PENDING';
  const currentPrice = currentFarm.id ? listingPrices[currentFarm.id] : null;
  const currentEarnings =
    currentPrice != null && currentFarm.credits > 0 ? Math.round(currentFarm.credits * currentPrice) : null;

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Top Profile Bar */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-1.5">
              <VerificationBadge badge={currentFarm.badge} showTier size="sm" />
              {currentFarm.flagged && (
                <span className="text-[10px] font-bold text-amber-800 uppercase tracking-wider bg-amber-100 border border-amber-300 px-2 py-0.5 rounded flex items-center gap-1">
                  <AlertCircle className="w-3 h-3 text-amber-700" />
                  Monitoring Flagged
                </span>
              )}
              {navState.farmerName && (
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider bg-slate-100 border border-slate-200 px-2 py-0.5 rounded">
                  FPO Inspected Record
                </span>
              )}
            </div>
            <h1 className="text-2xl font-extrabold text-[#0F172A] font-manrope tracking-tight">{farmerName}</h1>
            <p className="text-xs text-slate-500 mt-1 flex items-center gap-1.5 font-medium">
              <MapPin className="w-3.5 h-3.5 text-emerald-700 shrink-0" />
              <span>
                {village}, {district} | Selected Land Parcel: Survey {currentFarm.surveyNumber} (
                {currentFarm.areaHectares ?? '—'} ha)
              </span>
            </p>
          </div>

          {/* Right-Aligned Horizontal Pill Selector (only if multiple farms exist) */}
          {farms.length > 1 && !navState.surveyNumber && (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs font-bold text-slate-500 mr-1">Switch Farm:</span>
              {farms.map((f, idx) => (
                <button
                  key={f.id || idx}
                  onClick={() => setSelectedFarmIndex(idx)}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all border ${
                    activeIndex === idx
                      ? 'bg-[#0C2A18] text-white border-[#0C2A18] shadow-xs'
                      : 'bg-[#F8FAF8] text-slate-700 border-slate-200 hover:bg-emerald-50'
                  }`}
                >
                  Survey {f.surveyNumber} ({f.badge})
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Empty State Banner if no farms exist */}
        {farms.length === 0 && (
          <div className="bg-white border border-emerald-200 rounded-2xl p-8 text-center space-y-3 shadow-sm">
            <MapPin className="w-10 h-10 text-emerald-700 mx-auto" />
            <h2 className="text-lg font-extrabold text-slate-900 font-manrope">No farms enrolled yet</h2>
            <p className="text-xs text-slate-500 max-w-md mx-auto">
              Verify your land ownership, draw your parcel boundary, and run the satellite scan to mint your first carbon credits.
            </p>
            <button
              onClick={() => navigate('/farmer/land-verification')}
              className="px-5 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white font-bold text-xs rounded-xl transition-all shadow-sm inline-flex items-center gap-2"
            >
              <ShieldCheck className="w-4 h-4" />
              <span>Enroll Your First Parcel</span>
            </button>
          </div>
        )}

        {/* Earnings Calculator — pre-signup estimate, Trust Engine Stage 2 */}
        <EarningsCalculator
          farm={{
            areaHectares: currentFarm.areaHectares,
            crop: currentFarm.crop !== '—' ? currentFarm.crop : undefined,
            ndvi: currentFarm.ndvi,
            badge: currentFarm.badge,
          }}
        />

        {/* Highlighted Revenue Card (Only rendered when at least 1 farm exists) */}
        {farms.length > 0 && (
          isPending ? (
            <div className="bg-amber-50 border border-amber-200 text-amber-950 rounded-2xl p-6 shadow-xs relative overflow-hidden space-y-3">
              <div className="flex items-start gap-3">
                <AlertTriangle className="w-6 h-6 text-amber-700 shrink-0 mt-1" />
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-amber-900 uppercase tracking-wider bg-amber-200 px-2.5 py-0.5 rounded-full">
                      {currentFarm.flagged ? 'Monitoring Flagged' : 'Verification Incomplete'}
                    </span>
                  </div>
                  <h2 className="text-xl font-extrabold font-manrope text-amber-950">
                    {currentFarm.flagged
                      ? 'Action needed: Farm flagged by 5-day monitoring'
                      : 'Complete verification to earn carbon credits'}
                  </h2>
                  <p className="text-xs text-amber-800 max-w-2xl leading-relaxed">
                    This farmland parcel (<code className="font-mono font-bold">Survey {currentFarm.surveyNumber}</code>) has a{' '}
                    <strong>{currentFarm.status}</strong> badge status. Credit minting and UPI earnings are strictly locked
                    until verification or FPO attestation is complete.
                  </p>
                </div>
              </div>

              <div className="pt-2 flex flex-wrap gap-3">
                <button
                  onClick={() => navigate('/farmer/land-verification')}
                  className="px-5 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white font-bold text-xs rounded-xl transition-all shadow-xs flex items-center gap-2"
                >
                  <ShieldCheck className="w-4 h-4" />
                  <span>Complete Verification Flow</span>
                </button>
              </div>
            </div>
          ) : (
            <div className="bg-[#F0FDF4] border border-[#BBF7D0] text-slate-900 rounded-2xl p-6 shadow-sm relative overflow-hidden">
              <div className="relative z-10 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider bg-white border border-emerald-200 px-2.5 py-0.5 rounded-full">
                      ESTIMATED ANNUAL CARBON REVENUE
                    </span>
                    <span className="text-[10px] font-semibold text-slate-500 bg-white/80 px-2 py-0.5 rounded border border-slate-200">
                      {currentEarnings != null ? 'Your latest listing price' : 'No listing yet'}
                    </span>
                  </div>
                  <h2 className="text-3xl md:text-4xl font-extrabold font-manrope text-[#0C2A18] mt-2">
                    {currentEarnings != null ? (
                      <>
                        ₹{currentEarnings.toLocaleString('en-IN')}{' '}
                        <span className="text-sm font-normal text-slate-600">/ year</span>
                      </>
                    ) : (
                      <span className="text-2xl text-slate-500">—</span>
                    )}
                  </h2>
                  <p className="text-xs text-slate-600 mt-1 max-w-xl font-medium">
                    {currentEarnings != null
                      ? `${currentFarm.areaHectares ?? '—'} ha ${currentFarm.crop} = ${currentFarm.credits} credits/year, priced at ₹${currentPrice}/credit from your own marketplace listing.`
                      : `${currentFarm.areaHectares ?? '—'} ha ${currentFarm.crop} = ${currentFarm.credits} credits/year. Publish a listing to see revenue at real market prices.`}
                  </p>
                </div>

                <button
                  onClick={() => navigate('/farmer/wallet')}
                  className="px-6 py-3 bg-[#0C2A18] hover:bg-[#15803D] text-white font-bold text-xs rounded-xl transition-all shadow-sm flex items-center gap-2 shrink-0"
                >
                  <Wallet className="w-4 h-4 text-emerald-300" />
                  <span>Open Wallet & UPI Ledger</span>
                </button>
              </div>
            </div>
          )
        )}

        {/* 3-Column Core Metric Row */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-2xl p-6 space-y-1">
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">NDVI Vegetation Index</p>
            <p className="text-3xl font-extrabold text-[#0C2A18] font-manrope">
              {currentFarm.ndvi != null ? `${currentFarm.ndvi} Index` : '—'}
            </p>
            <p className="text-xs text-slate-500 font-medium pt-1">Sentinel-2 Multi-Spectral Active Vegetation Canopy</p>
          </div>

          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-2xl p-6 space-y-1">
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Active Carbon Credits</p>
            {currentFarm.flagged ? (
              <div>
                <p className="text-2xl font-extrabold text-amber-700 font-manrope">0.00 MT CO2e</p>
                <p className="text-xs text-amber-800 font-semibold mt-1">Paused (5-Day Monitoring Alert)</p>
              </div>
            ) : isPending ? (
              <div>
                <p className="text-2xl font-extrabold text-rose-700 font-manrope">0.00 MT CO2e</p>
                <p className="text-xs text-rose-700 font-semibold mt-1">Blocked (PENDING Status)</p>
              </div>
            ) : (
              <div>
                <p className="text-3xl font-extrabold text-slate-900 font-manrope">
                  {Number(currentFarm.credits).toLocaleString('en-IN')} tCO2e
                </p>
                <p className="text-xs text-emerald-800 font-semibold mt-1">Minted & Verified ({currentFarm.badge})</p>
              </div>
            )}
          </div>

          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-2xl p-6 space-y-1">
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Soil Biodiversity Index</p>
            <p className="text-3xl font-extrabold text-amber-700 font-manrope">
              {currentFarm.bioScore ? `${currentFarm.bioScore} / 10` : '—'}
            </p>
            <p className="text-xs text-slate-500 font-medium pt-1">Ecosystem Richness Score</p>
          </div>
        </div>

        {/* Quick Action Navigation Grid */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 shadow-sm space-y-4">
          <div>
            <h2 className="text-base font-bold text-slate-900 font-manrope">Farm Management & Marketplace Actions</h2>
            <p className="text-xs text-slate-500">
              Quickly navigate to land registration, passport analytics, tutorial walkthroughs, or marketplace trading.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
            <button
              onClick={() => navigate('/farmer/land-verification')}
              className="p-4 bg-slate-50 hover:bg-emerald-50 border border-slate-200 hover:border-emerald-300 rounded-xl transition-all text-left space-y-2 group"
            >
              <div className="w-10 h-10 bg-emerald-100 text-emerald-800 rounded-lg flex items-center justify-center group-hover:scale-105 transition-transform">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <p className="text-xs font-bold text-slate-900">Enroll New Parcel</p>
              <p className="text-[11px] text-slate-500">Verify land deeds & registry</p>
            </button>

            <button
              onClick={() => navigate('/create-listing', { state: { farmId: currentFarm.id } })}
              className="p-4 bg-slate-50 hover:bg-emerald-50 border border-slate-200 hover:border-emerald-300 rounded-xl transition-all text-left space-y-2 group"
            >
              <div className="w-10 h-10 bg-emerald-100 text-emerald-800 rounded-lg flex items-center justify-center group-hover:scale-105 transition-transform">
                <PlusCircle className="w-5 h-5" />
              </div>
              <p className="text-xs font-bold text-slate-900">List Credits for Sale</p>
              <p className="text-[11px] text-slate-500">Publish to corporate buyers</p>
            </button>

            <button
              onClick={() => navigate(currentFarm.id ? `/farmer/passport/${currentFarm.id}` : '/farm-analytics')}
              className="p-4 bg-slate-50 hover:bg-emerald-50 border border-slate-200 hover:border-emerald-300 rounded-xl transition-all text-left space-y-2 group"
            >
              <div className="w-10 h-10 bg-emerald-100 text-emerald-800 rounded-lg flex items-center justify-center group-hover:scale-105 transition-transform">
                <TrendingUp className="w-5 h-5" />
              </div>
              <p className="text-xs font-bold text-slate-900">Carbon Passport</p>
              <p className="text-[11px] text-slate-500">NDVI biomass & P3 score</p>
            </button>

            <button
              onClick={() => navigate('/marketplace')}
              className="p-4 bg-slate-50 hover:bg-emerald-50 border border-slate-200 hover:border-emerald-300 rounded-xl transition-all text-left space-y-2 group"
            >
              <div className="w-10 h-10 bg-emerald-100 text-emerald-800 rounded-lg flex items-center justify-center group-hover:scale-105 transition-transform">
                <ShoppingCart className="w-5 h-5" />
              </div>
              <p className="text-xs font-bold text-slate-900">Open Marketplace</p>
              <p className="text-[11px] text-slate-500">Browse live carbon listings</p>
            </button>

            <button
              onClick={() => navigate('/onboarding')}
              className="p-4 bg-slate-50 hover:bg-emerald-50 border border-slate-200 hover:border-emerald-300 rounded-xl transition-all text-left space-y-2 group"
            >
              <div className="w-10 h-10 bg-emerald-100 text-emerald-800 rounded-lg flex items-center justify-center group-hover:scale-105 transition-transform">
                <BookOpen className="w-5 h-5" />
              </div>
              <p className="text-xs font-bold text-slate-900">Walkthrough Guide</p>
              <p className="text-[11px] text-slate-500">Learn how CarbonX works</p>
            </button>
          </div>
        </div>

      </div>
    </div>
  );
}
