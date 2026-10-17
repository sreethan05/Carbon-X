import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Info, Sprout } from 'lucide-react';

// Values must match credit_engine._CROP_FACTORS keys exactly: a label the
// engine does not recognise silently falls back to the generic mixed-cropping
// factor, so this picker mirrors the engine's canonical crop set.
const CROPS = ['Rice', 'Maize', 'Millets', 'Turmeric', 'Cotton', 'Sugarcane', 'Chilli'];

export default function FarmDetailsForm() {
  const navigate = useNavigate();

  const [crop, setCrop] = useState('Cotton');
  const [irrigation, setIrrigation] = useState('Drip Irrigation');

  const handleSubmit = (e) => {
    e.preventDefault();
    // Only the fields the pipeline actually consumes are stored: crop_type
    // selects the engine's factors, irrigation is saved on the farm record.
    localStorage.setItem('carbonx_farm_details', JSON.stringify({ crop, irrigation }));
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
            className="w-full py-3 bg-emerald-700 hover:bg-emerald-600 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 mt-4"
          >
            <span>Proceed to Earth Engine Satellite Processing</span>
            <ArrowRight className="w-4 h-4" />
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
