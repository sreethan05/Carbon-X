import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, CheckCircle2, Sparkles, AlertTriangle } from 'lucide-react';
import BadgePill from '../components/BadgePill';
import { useAuth } from '../context/AuthContext';
import { createMarketplaceListing } from '../services/api';

export default function CreateListing() {
  const navigate = useNavigate();
  const { farms, refreshUser } = useAuth();

  const [volume, setVolume] = useState(1);
  const [unitPrice, setUnitPrice] = useState(340);
  const [assignedBadge, setAssignedBadge] = useState('DOCUMENT');
  const [selectedFarmId, setSelectedFarmId] = useState('');
  const [isPublishing, setIsPublishing] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const getBadgeBenchmark = (badge) => {
    switch (badge) {
      case 'REGISTRY': return 340;
      case 'REGISTRY_DOC': return 320;
      case 'FPO': return 300;
      default: return 310;
    }
  };

  // Pick verified farms with available credits
  const sellableFarms = (farms || []).filter((f) => (parseFloat(f.total_credits) || 0) > 0);

  useEffect(() => {
    refreshUser();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (sellableFarms.length > 0 && !selectedFarmId) {
      setSelectedFarmId(sellableFarms[0].id);
    }
  }, [sellableFarms.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const selectedFarm = sellableFarms.find((f) => f.id === selectedFarmId) || sellableFarms[0] || null;
  const rawAvail = parseFloat(selectedFarm?.total_credits);
  const maxVolume = selectedFarm && Number.isFinite(rawAvail) ? Math.max(0, rawAvail) : 0;
  const minVolume = maxVolume > 0 ? (maxVolume < 0.5 ? 0.1 : 0.5) : 0;

  useEffect(() => {
    if (selectedFarm) {
      const raw = parseFloat(selectedFarm.total_credits);
      const avail = Number.isFinite(raw) ? Math.max(0, raw) : 0;
      const minV = avail > 0 ? (avail < 0.5 ? 0.1 : 0.5) : 0;
      setVolume(avail > 0 ? Math.min(avail, Math.max(minV, 1)) : 0);
      const badge = selectedFarm.badge || 'DOCUMENT';
      setAssignedBadge(badge);
      setUnitPrice(selectedFarm.benchmark || getBadgeBenchmark(badge));
    }
  }, [selectedFarmId, selectedFarm]); // eslint-disable-line react-hooks/exhaustive-deps

  // Live revenue calculations (mirrors backend services/split_engine.py:
  // farmer 70% floor, FPO 5% only when involvement is proven, platform
  // keeps the remainder — 25% with FPO / 30% without).
  const effectivePrice = Number.isFinite(parseFloat(unitPrice)) ? Math.max(0, parseFloat(unitPrice)) : 0;
  const effectiveVolume = Number.isFinite(parseFloat(volume)) ? Math.max(0, parseFloat(volume)) : 0;
  const grossValue = effectiveVolume * effectivePrice;
  const hasFpoInvolvement = Boolean(selectedFarm?.fpo_id);
  const farmerShare = grossValue * 0.70;
  const fpoShare = hasFpoInvolvement ? grossValue * 0.05 : 0;
  const platformShare = grossValue - farmerShare - fpoShare;

  const handleSubmitListing = async (e) => {
    e.preventDefault();
    setError('');
    if (!selectedFarm) {
      setError('No verified farm with credits found. Enroll and scan a parcel first.');
      return;
    }
    if (maxVolume <= 0) {
      setError('This parcel has 0 available credits remaining to list.');
      return;
    }
    if (effectiveVolume <= 0) {
      setError('Listing volume must be greater than zero.');
      return;
    }
    if (effectiveVolume > maxVolume) {
      setError(`Listing volume (${effectiveVolume} MT) cannot exceed available credits (${maxVolume} MT).`);
      return;
    }
    if (effectivePrice <= 0) {
      setError('Benchmark price must be greater than zero.');
      return;
    }
    setIsPublishing(true);
    try {
      const res = await createMarketplaceListing({
        credits: effectiveVolume,
        price_per_credit: effectivePrice,
        farm_id: selectedFarm.id,
        crop: selectedFarm.crop_type || 'Mixed Crop',
      });
      if (res && res.success) {
        setSuccess(true);
        refreshUser();
        setTimeout(() => navigate('/marketplace'), 1200);
      } else {
        setError((res && res.message) || 'Failed to publish listing');
      }
    } catch {
      setError('Marketplace service unreachable. Is the backend running?');
    } finally {
      setIsPublishing(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Header */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex justify-between items-center">
          <div>
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full inline-block mb-1">
              Credit Yield Configuration
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Create Marketplace Credit Listing</h1>
            <p className="text-xs text-slate-500 mt-0.5">Publish verified carbon credits onto the corporate trading floor.</p>
          </div>

          <button
            onClick={() => navigate('/farmer/dashboard')}
            className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-lg text-xs font-bold transition-all flex items-center gap-1.5"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Dashboard</span>
          </button>
        </div>

        {error && (
          <p className="text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg leading-relaxed flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" /> {error}
          </p>
        )}

        {success && (
          <p className="text-xs text-emerald-800 font-bold bg-emerald-50 border border-emerald-200 p-2.5 rounded-lg flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 shrink-0" /> Listing published! Redirecting to the marketplace…
          </p>
        )}

        {/* Configuration Panel */}
        <form onSubmit={handleSubmitListing} className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-6">
          <div className="flex items-center justify-between bg-slate-50 border border-slate-200 p-4 rounded-xl">
            <div>
              <p className="text-xs font-bold text-slate-900">Verified Parcel Footprint</p>
              {selectedFarm ? (
                <p className="text-[11px] text-slate-500">
                  {selectedFarm.name} · {selectedFarm.area_hectares} ha · {selectedFarm.total_credits} credits available
                </p>
              ) : (
                <p className="text-[11px] text-rose-700 font-semibold">No sellable farm found — enroll a parcel first</p>
              )}
            </div>
            <BadgePill badge={assignedBadge} size="sm" />
          </div>

          {sellableFarms.length > 1 && (
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">Choose Farm</label>
              <select
                value={selectedFarmId}
                onChange={(e) => setSelectedFarmId(e.target.value)}
                className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold text-slate-900 focus:outline-none focus:border-emerald-600"
              >
                {sellableFarms.map((f) => (
                  <option key={f.id} value={f.id}>{f.name} — {f.total_credits} credits</option>
                ))}
              </select>
            </div>
          )}

          {/* Interactive Volume Controls */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs font-bold">
              <label className="text-slate-700 uppercase tracking-wider">Volume to List (MT CO2e)</label>
              <div className="flex items-center gap-1.5">
                <input
                  type="number"
                  min={minVolume}
                  max={maxVolume}
                  step="0.1"
                  value={volume}
                  onChange={(e) => {
                    const val = parseFloat(e.target.value);
                    if (isNaN(val)) {
                      setVolume('');
                    } else {
                      setVolume(Math.max(0, Math.min(maxVolume, val)));
                    }
                  }}
                  disabled={maxVolume <= 0}
                  className="w-20 px-2 py-0.5 text-right font-mono font-bold text-emerald-800 bg-slate-50 border border-slate-200 rounded text-sm focus:outline-none focus:border-emerald-600 disabled:opacity-50"
                />
                <span className="text-slate-600 text-xs font-semibold">MT</span>
              </div>
            </div>
            <input
              type="range"
              min={minVolume}
              max={Math.max(minVolume, maxVolume)}
              step={maxVolume > 20 ? "1" : "0.1"}
              value={Number(volume) || 0}
              onChange={(e) => setVolume(parseFloat(e.target.value) || 0)}
              disabled={maxVolume <= 0}
              className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-700 disabled:opacity-40"
            />
            <div className="flex justify-between text-[10px] text-slate-400">
              <span>Min: {minVolume} MT</span>
              <span>Available: {maxVolume} MT</span>
            </div>
          </div>

          {/* Unit Benchmark Price Input */}
          <div>
            <div className="flex justify-between items-center mb-1">
              <label className="text-xs font-bold text-slate-700 uppercase tracking-wider">
                Benchmark Price per Credit (INR)
              </label>
              <button
                type="button"
                onClick={() => setUnitPrice(getBadgeBenchmark(assignedBadge))}
                className="text-[10px] font-bold text-emerald-700 hover:underline"
              >
                Reset to Benchmark (₹{getBadgeBenchmark(assignedBadge)})
              </button>
            </div>
            <input
              type="number"
              min="1"
              max="10000"
              value={unitPrice}
              onChange={(e) => {
                const val = parseFloat(e.target.value);
                setUnitPrice(isNaN(val) ? '' : Math.max(0, val));
              }}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold text-slate-900 focus:outline-none focus:border-emerald-600"
            />
            <p className="text-[10px] text-slate-500 mt-1">
              Recommended benchmark for {assignedBadge} badge: INR {getBadgeBenchmark(assignedBadge)} / Credit
            </p>
          </div>

          {/* Live Revenue Projection Box */}
          <div className="bg-[#0D2F1D] text-white border border-emerald-800 rounded-xl p-5 space-y-3">
            <div className="flex justify-between items-center border-b border-emerald-800/80 pb-3">
              <span className="text-xs font-bold text-emerald-300 uppercase tracking-wider">Gross Carbon Value</span>
              <span className="text-base font-bold text-white font-mono">INR {grossValue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-300">Farmer payout (70% floor)</span>
              <span className="text-emerald-400 font-mono font-semibold">INR {farmerShare.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-300">
                {hasFpoInvolvement ? 'FPO share (5% — involvement proven)' : 'FPO share (none — no FPO on this farm)'}
              </span>
              <span className="text-emerald-300 font-mono font-semibold">INR {fpoShare.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>

            <div className="flex justify-between items-center text-xs">
              <span className="text-slate-300">Platform & monitoring share ({hasFpoInvolvement ? '25' : '30'}%)</span>
              <span className="text-slate-300 font-mono font-semibold">INR {platformShare.toLocaleString('en-IN', { minimumFractionDigits: 2 })}</span>
            </div>

            <div className="flex justify-between items-center text-xs pt-1 border-t border-emerald-800/80">
              <span className="text-emerald-300 font-bold uppercase tracking-wider">Estimated Farmer Payout</span>
              <span className="text-xl font-extrabold text-emerald-400 font-manrope font-mono">
                INR {farmerShare.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </span>
            </div>
            <p className="text-[10px] text-slate-400">
              Splits are computed per sale by the backend split engine at the actual sale price; the farmer's 70% floor is guaranteed.
            </p>
          </div>

          <button
            type="submit"
            disabled={isPublishing || !selectedFarm || maxVolume <= 0 || effectiveVolume <= 0 || effectiveVolume > maxVolume || effectivePrice <= 0}
            className="w-full py-3 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
          >
            <Sparkles className="w-4 h-4" />
            <span>{isPublishing ? 'Publishing…' : 'Publish Listing to Public Marketplace'}</span>
          </button>
        </form>

      </div>
    </div>
  );
}
