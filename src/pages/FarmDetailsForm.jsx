import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Leaf, Sparkles, Sprout, Droplets, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function FarmDetailsForm() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [crop, setCrop] = useState('Cotton');
  const [irrigation, setIrrigation] = useState('Drip Irrigation');
  const [tillage, setTillage] = useState('Zero-Till');
  const [fertilizer, setFertilizer] = useState('Bio-Fertilizers & Compost');

  // Real-time estimated carbon bonus per practice
  const getBonus = () => {
    let bonus = 0;
    if (tillage === 'Zero-Till') bonus += 0.50;
    if (tillage === 'Reduced-Till') bonus += 0.25;
    if (irrigation === 'Drip Irrigation') bonus += 0.35;
    if (fertilizer.includes('Bio-Fertilizers')) bonus += 0.40;
    return bonus.toFixed(2);
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    localStorage.setItem('carbonx_farm_details', JSON.stringify({ crop, irrigation, tillage, fertilizer, bonus: getBonus() }));
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
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Regenerative Farming Practices</h1>
            <p className="text-xs text-slate-500 mt-0.5">Capture soil management and irrigation practices to calculate yield bonus.</p>
          </div>
          <Sprout className="w-10 h-10 text-emerald-700" />
        </div>

        {/* Real-Time Impact Preview Banner */}
        <div className="bg-[#0D2F1D] text-white border border-emerald-800 shadow-sm rounded-xl p-5 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-emerald-800/80 rounded-xl flex items-center justify-center text-emerald-300">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <p className="text-xs font-bold text-emerald-300 uppercase tracking-wider">Sequestration Bonus Yield</p>
              <p className="text-xl font-extrabold font-manrope text-white mt-0.5">
                +{getBonus()} Credits / Acre / Year
              </p>
            </div>
          </div>
          <span className="text-[11px] bg-emerald-950 border border-emerald-600 text-emerald-300 px-3 py-1 rounded-full font-semibold">
            LSTM Sequestration Boost
          </span>
        </div>

        {/* Practices Form */}
        <form onSubmit={handleSubmit} className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-5">
          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Primary Crop Type</label>
            <select
              value={crop}
              onChange={e => setCrop(e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-emerald-600"
            >
              <option value="Cotton">Cotton</option>
              <option value="Paddy (Rice)">Paddy (Rice)</option>
              <option value="Pulses & Millets">Pulses & Millets</option>
              <option value="Maize">Maize</option>
              <option value="Sugarcane">Sugarcane</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Irrigation System</label>
            <select
              value={irrigation}
              onChange={e => setIrrigation(e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-emerald-600"
            >
              <option value="Drip Irrigation">Drip Irrigation (+0.35 bonus)</option>
              <option value="Sprinkler System">Sprinkler System (+0.20 bonus)</option>
              <option value="Rain-fed">Rain-fed (+0.10 bonus)</option>
              <option value="Canal Flood">Canal Flood (+0.00 bonus)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Tillage Management Practice</label>
            <select
              value={tillage}
              onChange={e => setTillage(e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-emerald-600"
            >
              <option value="Zero-Till">Zero-Till / No-Till Farming (+0.50 bonus)</option>
              <option value="Reduced-Till">Reduced Tillage (+0.25 bonus)</option>
              <option value="Conventional">Conventional Deep Ploughing (+0.00 bonus)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs font-bold text-slate-700 mb-1">Fertilizer & Nutrient Practices</label>
            <select
              value={fertilizer}
              onChange={e => setFertilizer(e.target.value)}
              className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none focus:border-emerald-600"
            >
              <option value="Bio-Fertilizers & Compost">Bio-Fertilizers & Organic Compost (+0.40 bonus)</option>
              <option value="Integrated Nutrient Mgmt">Integrated Nutrient Management (+0.20 bonus)</option>
              <option value="Synthetic NPK">Synthetic Chemical NPK (+0.00 bonus)</option>
            </select>
          </div>

          <button
            type="submit"
            className="w-full py-3 bg-emerald-700 hover:bg-emerald-600 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 mt-4"
          >
            <span>Proceed to Earth Engine Satellite Processing</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </form>

      </div>
    </div>
  );
}
