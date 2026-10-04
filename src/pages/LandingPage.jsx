import React from 'react';
import { useNavigate } from 'react-router-dom';
import { Leaf, ArrowRight, ShieldCheck, Cpu, Globe, Users, Building2, Wallet, CheckCircle2 } from 'lucide-react';
import { useLanguage } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';

export default function LandingPage() {
  const navigate = useNavigate();
  const { currentLang, changeLanguage } = useLanguage();
  const { isAuthenticated, role } = useAuth();

  const handleFpoClick = () => {
    if (isAuthenticated && (role === 'fpo' || role === 'verifier')) {
      navigate('/fpo/dashboard');
    } else {
      navigate('/fpo/login');
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900">
      {/* Full-width Organic Green Header */}
      <header className="sticky top-0 z-50 bg-[#1B4332] border-b border-emerald-900 text-white px-4 md:px-10 py-3.5 shadow-md">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <div className="flex items-center gap-3 cursor-pointer" onClick={() => navigate('/')}>
            <div className="w-10 h-10 bg-[#2D6A4F] border border-emerald-500 rounded-xl flex items-center justify-center text-white shadow-sm">
              <Leaf className="w-5 h-5" />
            </div>
            <div>
              <span className="font-manrope font-extrabold text-xl tracking-tight block leading-tight text-white">CarbonX</span>
              <span className="text-[10px] font-medium text-emerald-200">Enterprise AgTech & Carbon Infrastructure</span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            <div className="flex items-center gap-1.5 bg-[#2D6A4F]/60 border border-emerald-600 rounded-xl px-3 py-1.5 text-xs text-white">
              <Globe className="w-3.5 h-3.5 text-emerald-300" />
              <select
                value={currentLang}
                onChange={(e) => changeLanguage(e.target.value)}
                className="bg-transparent border-none outline-none text-xs font-semibold text-white cursor-pointer"
              >
                <option value="en" className="bg-[#1B4332] text-white">English</option>
                <option value="te" className="bg-[#1B4332] text-white">తెలుగు (Telugu)</option>
              </select>
            </div>

            <button
              onClick={() => navigate(isAuthenticated ? '/dashboard' : '/farmer/login')}
              className="text-xs font-semibold text-emerald-100 hover:text-white px-3 py-2 rounded-xl transition-colors hidden sm:block"
            >
              {isAuthenticated ? 'My Dashboard' : 'Sign In'}
            </button>

            <button
              onClick={() => navigate('/role-selection')}
              className="text-xs font-bold text-white bg-[#2D6A4F] hover:bg-[#40916C] px-4 py-2.5 rounded-xl transition-all shadow-sm flex items-center gap-2 border border-emerald-500"
            >
              <span>Launch Portal</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      {/* Hero Banner with authentic farmland imagery overlay */}
      <section className="relative bg-[#1B4332] text-white py-20 px-4 md:px-10 overflow-hidden">
        <div className="absolute inset-0 z-0 opacity-20 bg-[url('https://images.unsplash.com/photo-1500937386664-56d1dfef3854?auto=format&fit=crop&q=80&w=1600')] bg-cover bg-center" />
        <div className="absolute inset-0 bg-gradient-to-b from-[#1B4332]/85 via-[#1B4332]/95 to-[#1B4332]" />

        <div className="relative z-10 max-w-5xl mx-auto text-center pt-6">
          <div className="inline-flex items-center gap-2 bg-[#2D6A4F]/80 border border-emerald-400/40 px-4 py-1.5 rounded-full text-xs font-semibold text-[#D1FAE5] mb-6 shadow-inner">
            <ShieldCheck className="w-4 h-4 text-emerald-300" />
            <span>Government Land Registry & Sentinel-2 Satellite MRV Protocol</span>
          </div>

          <h1 className="text-4xl md:text-6xl font-extrabold tracking-tight leading-tight mb-6 font-manrope">
            Bridge Farmers to <span className="text-emerald-300">Carbon Markets</span>
          </h1>

          <p className="text-lg md:text-xl text-emerald-100 max-w-3xl mx-auto leading-relaxed mb-10">
            Scientific land verification, automated satellite indexing, and direct wallet settlements.
          </p>

          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <button
              onClick={() => navigate('/farmer/register')}
              className="px-6 py-3.5 bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl font-bold text-sm transition-all shadow-md flex items-center justify-center gap-2"
            >
              <span>Farmer Voice Registration</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              onClick={handleFpoClick}
              className="px-6 py-3.5 bg-[#2D6A4F] hover:bg-[#40916C] text-white border border-emerald-500 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2"
            >
              <span>FPO Command Center</span>
            </button>
            <button
              onClick={() => navigate('/marketplace')}
              className="px-6 py-3.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-[#D1FAE5] border border-emerald-600 rounded-xl font-bold text-sm transition-all flex items-center justify-center gap-2"
            >
              <span>Corporate Marketplace</span>
            </button>
          </div>
        </div>
      </section>

      {/* Live Key Performance Indicators (Bento Grid) */}
      <section className="max-w-7xl mx-auto px-4 md:px-10 -mt-8 relative z-20 mb-16">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 flex items-center gap-4">
            <div className="w-12 h-12 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center text-emerald-800">
              <Leaf className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Total Farmland Enrolled</p>
              <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">14,200 Acres</p>
              <p className="text-xs text-emerald-700 font-medium mt-0.5">Verified across 10 Telangana Mandals</p>
            </div>
          </div>

          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 flex items-center gap-4">
            <div className="w-12 h-12 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center text-emerald-800">
              <Cpu className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Verified CO2 Sequestered</p>
              <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">285.4K Tonnes</p>
              <p className="text-xs text-emerald-700 font-medium mt-0.5">Indexed via Sentinel-2 multi-spectral NDVI</p>
            </div>
          </div>

          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 flex items-center gap-4">
            <div className="w-12 h-12 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center text-emerald-800">
              <Wallet className="w-6 h-6" />
            </div>
            <div>
              <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Net Farmer Disbursements</p>
              <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">INR 12.4 Cr</p>
              <p className="text-xs text-emerald-700 font-medium mt-0.5">Direct UPI payout with 2% escrow fee split</p>
            </div>
          </div>
        </div>
      </section>

      {/* Institutional Trust Ribbon */}
      <section className="bg-[#1B4332] text-emerald-100 py-6 border-y border-emerald-900 mb-16">
        <div className="max-w-7xl mx-auto px-4 md:px-10 flex flex-wrap justify-between items-center gap-6 text-xs font-semibold">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-300" />
            <span>ISRO Bhuvan Compatible</span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-300" />
            <span>Sentinel-2 Multi-Spectral NDVI</span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-300" />
            <span>PostGIS Boundary Verification</span>
          </div>
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-300" />
            <span>Direct UPI Escrow Settlement</span>
          </div>
        </div>
      </section>

      {/* How CarbonX Works — the five-flow trust story */}
      <section className="max-w-7xl mx-auto px-4 md:px-10 mb-20">
        <div className="text-center mb-12">
          <span className="text-[11px] font-bold text-emerald-800 uppercase tracking-widest bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full">
            The Trust Pipeline
          </span>
          <h2 className="text-2xl md:text-3xl font-extrabold text-slate-900 font-manrope mt-4">From field photo to farmer payout — in five verified steps</h2>
          <p className="text-sm text-slate-600 mt-2 max-w-2xl mx-auto">
            Every credit on CarbonX walks the same auditable path. Nothing silently fails, nothing invisibly passes — and the farmer sees every rupee.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {[
            { n: '1', t: 'Register & Validate', d: 'OTP login, OCR of any land document, map-drawn boundary. Failed checks escalate to the FPO queue — never silently dropped.' },
            { n: '2', t: 'Verify (Stage 1)', d: 'Declared crop cross-checked against Sentinel-2 NDVI signatures. Mismatch pauses for human review — satellites check, humans judge.' },
            { n: '3', t: 'Calculate (Stage 2)', d: 'VM0042-style five-step math: additionality, biomass, soil carbon — minus a 10–30% uncertainty deduction. Conservative by design.' },
            { n: '4', t: 'Anchor & Monitor', d: 'Every credit anchors a SHA-256 evidence hash. A 5-day NDVI cycle flags at-risk credits straight to FPO review.' },
            { n: '5', t: 'Sell & Split', d: 'Buyers see the farmer-level breakdown before paying. Escrow splits 70/5/25 or 70/30, purchase = instant retirement, certificate issued.' },
          ].map((s) => (
            <div key={s.n} className="bg-white border border-slate-200 rounded-2xl p-5 shadow-sm hover:shadow-md hover:border-emerald-300 transition-all">
              <div className="w-9 h-9 rounded-full bg-[#1B4332] text-emerald-200 font-extrabold text-sm flex items-center justify-center mb-3 font-manrope">
                {s.n}
              </div>
              <h3 className="text-sm font-extrabold text-slate-900 font-manrope">{s.t}</h3>
              <p className="text-xs text-slate-600 mt-1.5 leading-relaxed">{s.d}</p>
            </div>
          ))}
        </div>

        <div className="mt-6 bg-emerald-50 border border-emerald-200 rounded-2xl p-4 text-center">
          <p className="text-xs text-emerald-900 font-semibold">
            <span className="font-extrabold">The farmer's sale screen:</span> Credit sold · Price ₹1,800 · Your share (70%) ₹1,260 · FPO (5%) ₹90 · Platform (25%) ₹450 · Verified record sha256:3a7f…9e21
          </p>
          <p className="text-[11px] text-emerald-700 mt-1">Every rupee, every recipient, every hash — one screen.</p>
        </div>
      </section>

      {/* Quick Portal Navigation Cards */}
      <section className="max-w-7xl mx-auto px-4 md:px-10 mb-20">
        <div className="text-center mb-12">
          <h2 className="text-2xl md:text-3xl font-extrabold text-slate-900 font-manrope">Ecosystem Access Portals</h2>
          <p className="text-sm text-slate-600 mt-2">Select your role to access dedicated tools and verification workflows.</p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          {/* Farmer Card */}
          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 flex flex-col justify-between hover:border-emerald-500 transition-all">
            <div>
              <div className="w-12 h-12 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center text-emerald-800 mb-4">
                <Users className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-slate-900">Farmer Onboarding & Passport</h3>
              <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                Voice assistance onboarding in Telugu/English, land verification, satellite reality check, and direct UPI payout ledger.
              </p>
            </div>
            <button
              onClick={() => navigate('/farmer/register')}
              className="mt-6 w-full py-2.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2"
            >
              <span>Register / Login as Farmer</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* FPO Card */}
          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 flex flex-col justify-between hover:border-emerald-500 transition-all">
            <div>
              <div className="w-12 h-12 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center text-emerald-800 mb-4">
                <Building2 className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-slate-900">FPO & Cooperative Command Center</h3>
              <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                Bulk member onboarding, flagged record ground-truth inspector, cooperative credit pooling, and certificate management.
              </p>
            </div>
            <button
              onClick={() => navigate('/fpo/dashboard')}
              className="mt-6 w-full py-2.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2"
            >
              <span>Access FPO Desk</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>

          {/* Corporate Card */}
          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 flex flex-col justify-between hover:border-emerald-500 transition-all">
            <div>
              <div className="w-12 h-12 bg-emerald-50 border border-emerald-200 rounded-xl flex items-center justify-center text-emerald-800 mb-4">
                <Globe className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-slate-900">Corporate Buyer Marketplace</h3>
              <p className="text-xs text-slate-600 mt-2 leading-relaxed">
                Filter verified credits by badge tier, run bulk auto-match allocation algorithms, and manage Scope 1-3 retirement certificates.
              </p>
            </div>
            <button
              onClick={() => navigate('/marketplace')}
              className="mt-6 w-full py-2.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2"
            >
              <span>Explore Credit Marketplace</span>
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-[#1B4332] text-emerald-100 py-8 border-t border-emerald-900 text-center text-xs">
        <div className="max-w-7xl mx-auto px-4 md:px-10 flex flex-col sm:flex-row justify-between items-center gap-4">
          <p>CarbonX Platform: Enterprise Institutional AgTech Ecosystem</p>
          <div className="flex gap-4">
            <button onClick={() => navigate('/role-selection')} className="hover:text-white transition-colors">Role Portal</button>
            <button onClick={() => navigate('/marketplace')} className="hover:text-white transition-colors">Marketplace</button>
            <button onClick={() => navigate('/fpo/dashboard')} className="hover:text-white transition-colors">FPO Desk</button>
          </div>
        </div>
      </footer>
    </div>
  );
}
