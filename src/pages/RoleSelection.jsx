import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Users, Building2, Globe, ArrowRight, ArrowLeft } from 'lucide-react';

export default function RoleSelection() {
  const navigate = useNavigate();

  const roleCards = [
    {
      id: 'farmer',
      title: 'Farmer & Land Owner',
      desc: 'Register farm parcels via Telugu/English voice input, upload land deeds for AI verification, and receive direct UPI carbon credit payouts.',
      scope: 'Permission Scope: Land Deed Upload, Satellite Boundary Mapping, Carbon Passport, Wallet Payouts',
      icon: Users,
      badgeColor: 'bg-emerald-50 text-emerald-800 border-emerald-200',
      route: '/farmer/register'
    },
    {
      id: 'fpo',
      title: 'FPO / Cooperative Officer',
      desc: 'Manage member farmers, perform bulk direct onboarding, inspect flagged ground-truth records, and execute cooperative credit pooling.',
      scope: 'Permission Scope: Member Roster, Bulk Onboarding, Ground-Truth Overlap Inspector, Cooperative Pooling',
      icon: Building2,
      badgeColor: 'bg-amber-50 text-amber-800 border-amber-200',
      route: '/fpo/login'
    },
    {
      id: 'buyer',
      title: 'Corporate Buyer & ESG Officer',
      desc: 'Browse verified carbon credit listings, run bulk auto-match allocation algorithms, and manage Scope 1-3 retirement certificates.',
      scope: 'Permission Scope: Multi-Tier Badge Trading, Bulk Auto-Match Engine, BRSR Audit Export, Certificate Retirement',
      icon: Globe,
      badgeColor: 'bg-sky-50 text-sky-800 border-sky-200',
      route: '/corporate/login'
    }
  ];

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-10 px-4 md:px-10 flex flex-col items-center">
      <div className="max-w-4xl w-full space-y-6">

        {/* Navigation Back */}
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-1.5 text-xs font-bold text-slate-600 hover:text-slate-900 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Gateway</span>
        </button>

        {/* Title Header */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 text-center space-y-2">
          <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full inline-block">
            Role-Based Access Portal
          </span>
          <h1 className="text-3xl font-extrabold text-slate-900 font-manrope">Select Ecosystem Role</h1>
          <p className="text-xs text-slate-500 max-w-xl mx-auto">
            Choose your role to access customized dashboards, verification workflows, and marketplace portals.
          </p>
        </div>

        {/* 3 Primary Role Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {roleCards.map((r) => {
            const Icon = r.icon;
            return (
              <div
                key={r.id}
                onClick={() => navigate(r.route)}
                className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex flex-col justify-between hover:border-emerald-600 transition-all cursor-pointer space-y-4"
              >
                <div className="space-y-3">
                  <div className={`w-12 h-12 rounded-xl flex items-center justify-center border ${r.badgeColor}`}>
                    <Icon className="w-6 h-6" />
                  </div>
                  <h2 className="text-lg font-bold text-slate-900">{r.title}</h2>
                  <p className="text-xs text-slate-600 leading-relaxed">{r.desc}</p>
                </div>

                <div className="space-y-3 pt-2 border-t border-slate-100">
                  <p className="text-[10px] font-mono text-slate-500">{r.scope}</p>
                  <button
                    type="button"
                    className="w-full py-2.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-1.5"
                  >
                    <span>Enter Portal</span>
                    <ArrowRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

      </div>
    </div>
  );
}
