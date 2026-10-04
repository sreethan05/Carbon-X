import React from 'react';
import { useNavigate } from 'react-router-dom';
import { CheckCircle2, ArrowRight, Calendar, Users, Wallet } from 'lucide-react';

export default function SuccessScreen() {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-slate-50 font-inter text-slate-900 py-10 px-4 flex items-center justify-center">
      <div className="max-w-lg w-full space-y-6">

        {/* Enrollment Summary Card */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 text-center space-y-4">
          <div className="w-14 h-14 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center text-emerald-700 mx-auto">
            <CheckCircle2 className="w-8 h-8" />
          </div>

          <div>
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
              Farm Enrollment Confirmed
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope mt-2">
              Welcome to CarbonX Network
            </h1>
            <p className="text-xs text-slate-500 mt-1">
              Your farmland parcel has been officially cataloged in the Telangana Carbon Sequestration Registry.
            </p>
          </div>

          {/* Next Steps Breakdown */}
          <div className="space-y-3 pt-2 text-left">
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Next Step Schedule</h3>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 flex items-start gap-3">
              <Calendar className="w-4 h-4 text-emerald-700 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-slate-900">Seasonal Satellite Re-Scan Date</p>
                <p className="text-[11px] text-slate-600">October 15, 2026 : Post-Kharif Sentinel-2 biomass sweep.</p>
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 flex items-start gap-3">
              <Users className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-slate-900">Cooperative Credit Pooling Window</p>
                <p className="text-[11px] text-slate-600">Yaadadri Laxmi Narsimha FPC bulk order matching active.</p>
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 flex items-start gap-3">
              <Wallet className="w-4 h-4 text-sky-700 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-slate-900">Direct UPI Payout Ledger</p>
                <p className="text-[11px] text-slate-600">Automated settlement triggered upon corporate buyer execution.</p>
              </div>
            </div>
          </div>

          <button
            onClick={() => navigate('/farmer/dashboard')}
            className="w-full py-3 bg-emerald-700 hover:bg-emerald-600 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 mt-4"
          >
            <span>Access Farmer Command Center</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>

      </div>
    </div>
  );
}
