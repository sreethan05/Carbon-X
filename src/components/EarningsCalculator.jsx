import React, { useEffect, useState } from 'react';
import { Calculator, Sparkles, Loader2 } from 'lucide-react';
import { calculateEarnings } from '../services/api';

const CROPS = ['Rice', 'Maize', 'Millets', 'Turmeric', 'Cotton', 'Sugarcane', 'Chilli'];

/**
 * Pre-signup earnings estimate (Trust Engine Stage 2, simplified VM0042):
 * shows the farmer expected rupees — with the uncertainty deduction applied —
 * before enrolling. Open endpoint, works even with the database offline.
 */
export default function EarningsCalculator({ farm }) {
  const [area, setArea] = useState('');
  const [crop, setCrop] = useState('Rice');
  const [ndvi, setNdvi] = useState(0.7);
  const [hasPhoto, setHasPhoto] = useState(true);
  const [geotagOk, setGeotagOk] = useState(true);
  const [fpoVerified, setFpoVerified] = useState(false);
  const [result, setResult] = useState(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (farm) {
      const hectares = parseFloat(farm.areaHectares || farm.area_hectares || (farm.acres ? farm.acres / 2.471 : ''));
      if (hectares) setArea(hectares.toFixed(2));
      if (farm.crop) setCrop(farm.crop);
      if (farm.ndvi) setNdvi(parseFloat(farm.ndvi));
      if (farm.badge && farm.badge !== 'DOCUMENT') setFpoVerified(true);
    }
  }, [farm]);

  const runEstimate = async () => {
    const hectares = parseFloat(area);
    if (!hectares || hectares <= 0) {
      setError('Enter your plot area in hectares');
      return;
    }
    setError('');
    setIsCalculating(true);
    try {
      const data = await calculateEarnings({
        area_hectares: hectares,
        crop,
        ndvi,
        has_photo: hasPhoto,
        geotag_ok: geotagOk,
        fpo_or_registry: fpoVerified,
      });
      if (data && data.success) {
        setResult(data);
      } else {
        setError((data && data.message) || 'Could not calculate — is the backend running?');
      }
    } catch {
      setError('Calculator service unreachable. Please try again.');
    } finally {
      setIsCalculating(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 shadow-sm rounded-2xl p-6 space-y-4">
      <div className="flex justify-between items-start gap-3">
        <div>
          <h2 className="text-base font-bold text-[#0F172A] flex items-center gap-2">
            <Calculator className="w-5 h-5 text-emerald-700" />
            Earnings Calculator
          </h2>
          <p className="text-xs text-slate-500 mt-0.5">
            See expected rupees before you enroll — a VM0042-style estimate with an honesty-first uncertainty deduction.
          </p>
        </div>
        <span className="text-[10px] font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded shrink-0">
          NO SIGN-UP NEEDED
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div>
          <label className="block text-[10px] font-bold text-slate-600 uppercase tracking-wider mb-1">Plot area (ha)</label>
          <input
            type="number"
            step="0.1"
            min="0.1"
            value={area}
            onChange={e => setArea(e.target.value)}
            placeholder="e.g. 2.0"
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-bold text-slate-900 focus:outline-none focus:border-emerald-600"
          />
        </div>
        <div>
          <label className="block text-[10px] font-bold text-slate-600 uppercase tracking-wider mb-1">Crop / practice</label>
          <select
            value={crop}
            onChange={e => setCrop(e.target.value)}
            className="w-full px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-sm font-semibold text-slate-900 focus:outline-none"
          >
            {CROPS.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="flex justify-between text-[10px] font-bold text-slate-600 uppercase tracking-wider mb-1">
            <span>Sentinel-2 NDVI</span>
            <span className="text-emerald-800 font-mono">{Number(ndvi).toFixed(2)}</span>
          </label>
          <input
            type="range"
            min="0.2"
            max="0.95"
            step="0.01"
            value={ndvi}
            onChange={e => setNdvi(parseFloat(e.target.value))}
            className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-700 mt-2"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs font-semibold text-slate-700">
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" checked={hasPhoto} onChange={e => setHasPhoto(e.target.checked)} className="accent-emerald-700" />
          Practice photo captured
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" checked={geotagOk} onChange={e => setGeotagOk(e.target.checked)} className="accent-emerald-700" />
          Geotag inside boundary
        </label>
        <label className="flex items-center gap-1.5 cursor-pointer">
          <input type="checkbox" checked={fpoVerified} onChange={e => setFpoVerified(e.target.checked)} className="accent-emerald-700" />
          FPO / registry verified
        </label>
      </div>

      <button
        onClick={runEstimate}
        disabled={isCalculating}
        className="w-full sm:w-auto px-6 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
      >
        {isCalculating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-emerald-300" />}
        <span>{isCalculating ? 'Calculating…' : 'Estimate My Earnings'}</span>
      </button>

      {error && (
        <p className="text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg">{error}</p>
      )}

      {result && (
        <div className="space-y-4 pt-2 border-t border-slate-100">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Estimated Credits</p>
              <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">
                {result.estimate.credits_tco2e} <span className="text-xs text-slate-500 font-bold">tCO2e/yr</span>
              </p>
              <p className="text-[11px] text-slate-500">after −{result.estimate.uncertainty_pct}% uncertainty</p>
            </div>
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
              <p className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider">Your Expected Income (70% floor)</p>
              <p className="text-2xl font-extrabold text-emerald-900 font-manrope mt-1">
                ₹{Number(result.income.expected_income_inr).toLocaleString('en-IN')}
                <span className="text-xs text-emerald-700 font-bold"> / yr</span>
              </p>
              <p className="text-[11px] text-emerald-800">
                Sale range ₹{Number(result.income.range_inr.min).toLocaleString('en-IN')} – ₹{Number(result.income.range_inr.max).toLocaleString('en-IN')}
              </p>
            </div>
            <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Evidence Quality</p>
              <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">
                {Math.round(result.evidence_quality.score * 100)}%
              </p>
              <p className="text-[11px] text-slate-500">better evidence → smaller deduction</p>
            </div>
          </div>

          <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4 space-y-1.5">
            <p className="text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1">How this was calculated</p>
            {result.estimate.steps.map(step => (
              <div key={step.step} className="flex justify-between gap-3 text-[11px]">
                <span className="text-slate-600 font-semibold shrink-0">{step.step}. {step.name}</span>
                <span className="text-slate-500 text-right">{step.detail}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
