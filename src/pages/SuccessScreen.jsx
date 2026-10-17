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
              Your farmland parcel has been saved to the CarbonX farm registry with its verification status attached.
            </p>
          </div>

          {/* Next Steps Breakdown */}
          <div className="space-y-3 pt-2 text-left">
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Next Step Schedule</h3>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 flex items-start gap-3">
              <Calendar className="w-4 h-4 text-emerald-700 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-slate-900">Continuous Satellite Monitoring</p>
                <p className="text-[11px] text-slate-600">The 5-day NDVI monitoring cycle re-checks your parcel after each Sentinel-2 revisit; any at-risk drop routes straight to FPO review.</p>
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 flex items-start gap-3">
              <Users className="w-4 h-4 text-amber-700 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-slate-900">Cooperative Credit Pooling</p>
                <p className="text-[11px] text-slate-600">When your farm is linked to an FPO, credits can be pooled and listed together by the FPO desk.</p>
              </div>
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 flex items-start gap-3">
              <Wallet className="w-4 h-4 text-sky-700 shrink-0 mt-0.5" />
              <div>
                <p className="text-xs font-bold text-slate-900">Transparent Payout Split</p>
                <p className="text-[11px] text-slate-600">Purchases settle through escrow with the 70% farmer floor split. UPI payout rails are simulated in this build and labelled as such.</p>
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
