import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Globe, ShieldCheck, ArrowRight, Layers, Sparkles, Building2 } from 'lucide-react';
import BadgePill from '../components/BadgePill';

export default function CorporateWelcome() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Hero */}
        <div className="bg-[#1B4332] text-white border border-emerald-900 shadow-sm rounded-xl p-8 relative overflow-hidden">
          <div className="max-w-3xl relative z-10 space-y-4">
            <span className="text-xs font-semibold text-emerald-300 uppercase tracking-wider bg-emerald-950 border border-emerald-700 px-3 py-1 rounded-full">
              Enterprise Buyer Portal Gateway
            </span>
            <h1 className="text-3xl md:text-4xl font-extrabold font-manrope text-white">
              High-Integrity Agricultural Carbon Offsets
            </h1>
            <p className="text-xs md:text-sm text-slate-300 leading-relaxed">
              Procure verified carbon credits directly from Indian farmers. Built for BRSR reporting, Scope 1-3 neutrality compliance, and satellite-verified MRV auditability.
            </p>

            <div className="flex flex-wrap gap-4 pt-2">
              <button
                onClick={() => navigate('/marketplace')}
                className="px-6 py-3 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl text-xs font-bold transition-all shadow-md flex items-center gap-2"
              >
                <span>Explore Trading Marketplace</span>
                <ArrowRight className="w-4 h-4" />
              </button>

              <button
                onClick={() => navigate('/marketplace/checkout')}
                className="px-6 py-3 bg-[#2D6A4F] hover:bg-[#40916C] text-[#D1FAE5] border border-emerald-500 rounded-xl text-xs font-bold transition-all flex items-center gap-2"
              >
                <Sparkles className="w-4 h-4 text-emerald-300" />
                <span>Run Bulk Auto-Match Engine</span>
              </button>
            </div>
          </div>
        </div>

        {/* Verification Badge Tiers Explanation */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-6">
          <h2 className="text-lg font-bold text-slate-900">Institutional Verification Badge Hierarchy</h2>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 space-y-2">
              <BadgePill badge="REGISTRY" size="sm" />
              <p className="text-xs font-bold text-slate-900 mt-2">Tier 1A: Cadastral Match</p>
              <p className="text-[11px] text-slate-600">Locked registry boundary match. Trading benchmark: INR 340 / credit.</p>
            </div>

            <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-4 space-y-2">
              <BadgePill badge="REGISTRY_DOC" size="sm" />
              <p className="text-xs font-bold text-slate-900 mt-2">Tier 1B: Pahani Record</p>
              <p className="text-[11px] text-slate-600">Pahani deed with verified survey bounds. Benchmark: INR 320 / credit.</p>
            </div>

            <div className="bg-sky-50 border border-sky-200 rounded-xl p-4 space-y-2">
              <BadgePill badge="DOCUMENT" size="sm" />
              <p className="text-xs font-bold text-slate-900 mt-2">Tier 2: OCR Validated</p>
              <p className="text-[11px] text-slate-600">RoR 1B document with OCR validation. Benchmark: INR 310 / credit.</p>
            </div>

            <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-2">
              <BadgePill badge="FPO" size="sm" />
              <p className="text-xs font-bold text-slate-900 mt-2">Tier 3: FPO Attestation</p>
              <p className="text-[11px] text-slate-600">Attested by recognized FPO cooperative. Benchmark: INR 300 / credit.</p>
            </div>
          </div>
        </div>

      </div>
    </div>
  );
}
