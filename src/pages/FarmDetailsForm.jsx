import React, { useState, useMemo } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, Info, Sprout, AlertTriangle, MapPin, Loader2 } from 'lucide-react';

// Values match credit_engine._CROP_FACTORS keys: a label the engine does
// not recognise falls back to generic mixed-cropping factor, so this picker
// strictly mirrors the engine's canonical crop factor set.
const CROPS = ['Rice', 'Paddy', 'Cotton', 'Maize', 'Millets', 'Turmeric', 'Sugarcane', 'Chilli'];
const IRRIGATION_SYSTEMS = ['Drip Irrigation', 'Sprinkler System', 'Rain-fed', 'Canal Flood'];

export default function FarmDetailsForm() {
  const navigate = useNavigate();
  const location = useLocation();

  const parcel = useMemo(() => {
    if (location.state && typeof location.state === 'object') return location.state;
    try {
      return JSON.parse(localStorage.getItem('carbonx_farm_parcel') || '{}');
    } catch {
      return {};
    }
  }, [location.state]);

  const savedDetails = useMemo(() => {
    try {
      return JSON.parse(localStorage.getItem('carbonx_farm_details') || '{}');
    } catch {
      return {};
    }
  }, []);

  // Match OCR-extracted crop or previously stored details to canonical list
  const initialCrop = () => {
    const candidate = parcel.crop || savedDetails.crop;
    if (candidate) {
      const match = CROPS.find(c => c.toLowerCase() === candidate.toLowerCase());
      if (match) return match;
    }
    return 'Cotton';
  };

  const initialIrrigation = () => {
    const candidate = parcel.irrigation || savedDetails.irrigation;
    if (candidate) {
      if (/drip/i.test(candidate)) return 'Drip Irrigation';
      if (/sprinkler/i.test(candidate)) return 'Sprinkler System';
      if (/rain/i.test(candidate)) return 'Rain-fed';
      if (/canal|flood|bore/i.test(candidate)) return 'Canal Flood';
    }
    return 'Drip Irrigation';
  };

  const [crop, setCrop] = useState(initialCrop);
  const [irrigation, setIrrigation] = useState(initialIrrigation);
  const [validationError, setValidationError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const hasParcel = Boolean(parcel && (parcel.geojson || parcel.surveyNumber));

  const handleSubmit = (e) => {
    e.preventDefault();
    if (isSubmitting) return;

    if (!hasParcel) {
      setValidationError('No farm parcel boundary found. Please draw or verify your farm boundary on the map first.');
      return;
    }
    if (parcel?.areaHa != null && (typeof parcel.areaHa !== 'number' || isNaN(parcel.areaHa) || parcel.areaHa <= 0)) {
      setValidationError('Farm area must be a valid positive number greater than 0 ha.');
      return;
    }
    if (!crop || !CROPS.includes(crop)) {
      setValidationError('Please select a valid primary crop type.');
      return;
    }
    if (!irrigation || !IRRIGATION_SYSTEMS.includes(irrigation)) {
      setValidationError('Please select a valid irrigation system.');
      return;
    }

    setValidationError('');
    setIsSubmitting(true);

    try {
      // Store fields consumed by the satellite scan and farm persistence pipeline
      localStorage.setItem('carbonx_farm_details', JSON.stringify({ crop, irrigation }));
    } catch (err) {
      console.warn('Could not persist farm details to localStorage', err);
    }
    navigate('/satellite-preview');
  };

  return (
    <div className="min-h-screen bg-slate-50 font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-2xl mx-auto space-y-6">

        {/* Page Title */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex justify-between items-center">
          <div>
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full inline-block mb-1">
              Agronomic Metadata
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Crop &amp; Irrigation Profile</h1>
            <p className="text-xs text-slate-500 mt-0.5">These two fields feed the Sentinel-2 scan and your farm's MRV record.</p>
          </div>
          <Sprout className="w-10 h-10 text-emerald-700" />
        </div>

        {/* Linked Parcel Summary Card */}
        {hasParcel ? (
          <div className="bg-white border border-emerald-200/80 rounded-xl p-4 shadow-xs flex items-center justify-between text-xs">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 bg-emerald-50 border border-emerald-200 rounded-lg flex items-center justify-center text-emerald-700">
                <MapPin className="w-4 h-4" />
              </div>
              <div>
                <p className="font-bold text-slate-900">
                  Survey {parcel.surveyNumber || '—'} ({parcel.village || 'Registered Village'})
                </p>
                <p className="text-[11px] text-slate-500">
                  Cadastral Plot · {typeof parcel?.areaHa === 'number' && !isNaN(parcel.areaHa) && parcel.areaHa > 0
                    ? `${parcel.areaHa} ha (${Math.round(parcel.areaHa * 2.471 * 10) / 10} acres)`
                    : 'Area mapped'}
                  {parcel?.tierCode ? ` · Tier ${parcel.tierCode}` : ''}
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => navigate('/farm-map', { state: parcel })}
              className="text-xs font-bold text-emerald-700 hover:text-emerald-800 underline"
            >
              Adjust Map
            </button>
          </div>
        ) : (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 text-xs text-amber-900 flex items-start justify-between gap-3 shadow-xs">
            <div className="flex items-start gap-2.5">
              <AlertTriangle className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
              <div>
                <p className="font-bold">No farm boundary on record</p>
                <p className="text-[11px] text-amber-800 mt-0.5">
                  Draw your farm parcel on the satellite map first so the engine can scan the correct plot.
                </p>
              </div>
            </div>
            <button
              type="button"
              onClick={() => navigate('/farm-map')}
              className="px-3 py-1.5 bg-amber-700 text-white rounded-lg font-bold text-xs hover:bg-amber-800 shrink-0"
            >
              Draw Boundary
            </button>
          </div>
        )}

        {/* Validation Error Banner */}
        {validationError && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-3.5 text-xs font-semibold flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{validationError}</span>
          </div>
        )}

        {/* Honest method note — no bonus math happens on this screen */}
        <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-5 flex items-start gap-3">
          <Info className="w-5 h-5 text-emerald-700 shrink-0 mt-0.5" />
          <div className="text-xs text-emerald-900 space-y-1">
            <p className="font-bold">How your estimate is built</p>
            <p className="leading-relaxed">
              After you continue, the Sentinel-2 scan measures your plot's NDVI. The credit engine combines a
              crop-calibrated biomass factor and an IPCC-style soil factor with that satellite signal, then applies a
              conservative 10–30% uncertainty deduction based on evidence quality. The full step-by-step math is shown
              with the scan result and in your Carbon Passport.
            </p>
          </div>
        </div>

        {/* Crop & Irrigation Form */}
        <form onSubmit={handleSubmit} className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-5">
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Primary Crop Type</label>
            <select
              value={crop}
              onChange={e => setCrop(e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-emerald-600"
            >
              {CROPS.map(c => <option key={c} value={c}>{c}</option>)}
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Irrigation System</label>
            <select
              value={irrigation}
              onChange={e => setIrrigation(e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-emerald-600"
            >
              <option value="Drip Irrigation">Drip Irrigation</option>
              <option value="Sprinkler System">Sprinkler System</option>
              <option value="Rain-fed">Rain-fed</option>
              <option value="Canal Flood">Canal Flood</option>
            </select>
          </div>

          <button
            type="submit"
            disabled={!hasParcel || isSubmitting}
            className="w-full py-3 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 mt-4"
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>Routing to Satellite Processing…</span>
              </>
            ) : (
              <>
                <span>Proceed to Earth Engine Satellite Processing</span>
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>

          <p className="text-[11px] text-slate-500 text-center">
            Practice-specific factor tables (zero-till, AWD rice, cover crops) are on the MRV roadmap; today the engine
            credits satellite-measured vegetation improvement plus a crop-calibrated soil factor.
          </p>
        </form>

      </div>
    </div>
  );
}
