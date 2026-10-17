import React, { useEffect, useState, useCallback, useId } from 'react';
import { Calculator, Sparkles, Loader2, Info } from 'lucide-react';
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
  const [hasPhoto, setHasPhoto] = useState(false);
  const [geotagOk, setGeotagOk] = useState(false);
  const [fpoVerified, setFpoVerified] = useState(false);
  const [result, setResult] = useState(null);
  const [isCalculating, setIsCalculating] = useState(false);
  const [error, setError] = useState('');

  const photoInputId = useId();
  const geotagInputId = useId();
  const fpoInputId = useId();

  useEffect(() => {
    if (farm) {
      const hectares = parseFloat(
        farm.areaHectares || farm.area_hectares || farm.area || (farm.acres ? farm.acres / 2.471 : '')
      );
      if (hectares && !isNaN(hectares)) setArea(hectares.toFixed(2));
      const farmCrop = farm.crop || farm.crop_type;
      if (farmCrop && farmCrop !== '—') {
        const matched = CROPS.find(c => c.toLowerCase() === String(farmCrop).toLowerCase());
        if (matched) setCrop(matched);
      }
      if (farm.ndvi != null && !isNaN(farm.ndvi)) setNdvi(parseFloat(farm.ndvi));
      setFpoVerified(['REGISTRY', 'REGISTRY_DOC', 'FPO'].includes(String(farm.badge || '').toUpperCase()));
    }
  }, [farm]);

  const runEstimate = useCallback(async (customOverrides = {}) => {
    const currentArea = customOverrides.area !== undefined ? customOverrides.area : area;
    const currentCrop = customOverrides.crop !== undefined ? customOverrides.crop : crop;
    const currentNdvi = customOverrides.ndvi !== undefined ? customOverrides.ndvi : ndvi;
    const currentHasPhoto = customOverrides.hasPhoto !== undefined ? customOverrides.hasPhoto : hasPhoto;
    const currentGeotagOk = customOverrides.geotagOk !== undefined ? customOverrides.geotagOk : geotagOk;
    const currentFpoVerified = customOverrides.fpoVerified !== undefined ? customOverrides.fpoVerified : fpoVerified;

    const hectares = parseFloat(currentArea);
    if (!hectares || hectares <= 0) {
      setError('Enter your plot area in hectares');
      return;
    }
    setError('');
    setIsCalculating(true);
    try {
      const badge = farm?.badge || (currentFpoVerified ? 'REGISTRY' : 'DOCUMENT');
      const data = await calculateEarnings({
        area_hectares: hectares,
        crop: currentCrop,
        ndvi: currentNdvi,
        badge,
        has_photo: currentHasPhoto,
        geotag_ok: currentGeotagOk,
        fpo_or_registry: currentFpoVerified,
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
  }, [area, crop, ndvi, hasPhoto, geotagOk, fpoVerified, farm]);

  // Reactive slider and practice flags: debounced recalculation when user tweaks parameters
  useEffect(() => {
    if (!result && !farm) return undefined;
    const hectares = parseFloat(area);
    if (!hectares || hectares <= 0) return undefined;

    const timer = setTimeout(() => {
      runEstimate();
    }, 300);
    return () => clearTimeout(timer);
  }, [ndvi, crop, hasPhoto, geotagOk, fpoVerified, area, farm, result, runEstimate]);

  const getCanopyLabel = (val) => {
    if (val < 0.35) return 'Sparse / Emergence';
    if (val < 0.65) return 'Moderate Vegetative';
    return 'Dense Canopy';
  };

  const cropOptions = CROPS.some(c => c.toLowerCase() === crop.toLowerCase())
    ? CROPS
    : [crop, ...CROPS];

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
            onChange={e => {
              setArea(e.target.value);
              if (error) setError('');
            }}
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
            {cropOptions.map(c => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="md:col-span-2">
          <label className="flex justify-between items-center text-[10px] font-bold text-slate-600 uppercase tracking-wider mb-1">
            <span className="flex items-center gap-1.5">
              <span>Sentinel-2 NDVI</span>
              <span className="text-[10px] font-medium text-emerald-700 bg-emerald-50 px-1.5 py-0.2 rounded border border-emerald-200">
                {getCanopyLabel(ndvi)}
              </span>
            </span>
            <span className="text-emerald-800 font-mono text-xs">{Number(ndvi).toFixed(2)}</span>
          </label>
          <input
            type="range"
            min="0.10"
            max="0.99"
            step="0.01"
            value={ndvi}
            onChange={e => setNdvi(parseFloat(e.target.value))}
            className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-700 mt-2"
          />
        </div>
      </div>

      <div className="flex flex-wrap gap-x-5 gap-y-2 text-xs font-semibold text-slate-700">
        <label htmlFor={photoInputId} className="flex items-center gap-1.5 cursor-pointer">
          <input
            id={photoInputId}
            type="checkbox"
            checked={hasPhoto}
            onChange={e => setHasPhoto(e.target.checked)}
            className="accent-emerald-700"
          />
          Practice photo captured (+0.25)
        </label>
        <label htmlFor={geotagInputId} className="flex items-center gap-1.5 cursor-pointer">
          <input
            id={geotagInputId}
            type="checkbox"
            checked={geotagOk}
            onChange={e => setGeotagOk(e.target.checked)}
            className="accent-emerald-700"
          />
          Geotag inside boundary (+0.25)
        </label>
        <label htmlFor={fpoInputId} className="flex items-center gap-1.5 cursor-pointer">
          <input
            id={fpoInputId}
            type="checkbox"
            checked={fpoVerified}
            onChange={e => setFpoVerified(e.target.checked)}
            className="accent-emerald-700"
          />
          FPO / registry verified (+0.25)
        </label>
      </div>

      <div className="flex items-center gap-3">
        <button
          onClick={() => runEstimate()}
          disabled={isCalculating}
          className="w-full sm:w-auto px-6 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
        >
          {isCalculating ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-emerald-300" />}
          <span>{isCalculating ? 'Calculating…' : result ? 'Recalculate Estimate' : 'Estimate My Earnings'}</span>
        </button>
        {result && (
          <span className="text-[11px] text-slate-400 flex items-center gap-1">
            <Info className="w-3.5 h-3.5 text-slate-400" />
            Adjusting inputs or slider updates dynamically
          </span>
        )}
      </div>

      {error && (
        <p className="text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg">{error}</p>
      )}

      {result && (
        <div className="space-y-4 pt-2 border-t border-slate-100">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Estimated Credits</p>
              <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">
                {result.estimate?.credits_tco2e ?? '—'} <span className="text-xs text-slate-500 font-bold">tCO2e/yr</span>
              </p>
              <p className="text-[11px] text-slate-500">after −{result.estimate?.uncertainty_pct ?? 0}% uncertainty</p>
            </div>
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4">
              <p className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider">Your Expected Income (70% floor)</p>
              <p className="text-2xl font-extrabold text-emerald-900 font-manrope mt-1">
                ₹{Number(result.income?.expected_income_inr || 0).toLocaleString('en-IN')}
                <span className="text-xs text-emerald-700 font-bold"> / yr</span>
              </p>
              <p className="text-[11px] text-emerald-800">
                Sale range ₹{Number(result.income?.range_inr?.min || 0).toLocaleString('en-IN')} – ₹{Number(result.income?.range_inr?.max || 0).toLocaleString('en-IN')}
              </p>
            </div>
            <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4">
              <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Evidence Quality</p>
              <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">
                {Math.round((result.evidence_quality?.score ?? 0) * 100)}%
              </p>
              <p className="text-[11px] text-slate-500">better evidence → smaller deduction</p>
            </div>
          </div>

          {Array.isArray(result.estimate?.steps) && result.estimate.steps.length > 0 && (
            <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4 space-y-1.5">
              <p className="text-[11px] font-bold text-slate-600 uppercase tracking-wider mb-1">How this was calculated</p>
              {result.estimate.steps.map(step => (
                <div key={step.step} className="flex justify-between gap-3 text-[11px]">
                  <span className="text-slate-600 font-semibold shrink-0">{step.step}. {step.name}</span>
                  <span className="text-slate-500 text-right">{step.detail}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
