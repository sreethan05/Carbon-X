import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Download, FileText, Sparkles, ArrowRight, ShieldCheck, Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getCertificates } from '../services/api';

export default function CorporateDashboard() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const companyName = user?.name || 'Corporate Buyer';
  const targetKey = `cx_corp_target_${companyName}`;

  const [certs, setCerts] = useState([]);
  const [loadingCerts, setLoadingCerts] = useState(true);
  const [purchasedOffsets, setPurchasedOffsets] = useState(0.0);
  const [isExporting, setIsExporting] = useState(false);
  // Self-declared decarbonization target — stored locally per corporate account
  // (the platform has no per-corporate target field server-side yet).
  const [targetOffsets, setTargetOffsets] = useState(() => {
    const saved = parseFloat(localStorage.getItem(targetKey));
    return Number.isFinite(saved) && saved > 0 ? saved : 1000.0;
  });
  const [targetInput, setTargetInput] = useState(() => {
    const saved = parseFloat(localStorage.getItem(targetKey));
    return Number.isFinite(saved) && saved > 0 ? String(saved) : '1000';
  });

  const handleTargetChange = (val) => {
    setTargetInput(val);
    const num = parseFloat(val);
    if (Number.isFinite(num) && num > 0) {
      setTargetOffsets(num);
      localStorage.setItem(targetKey, String(num));
    }
  };

  useEffect(() => {
    (async () => {
      try {
        const data = await getCertificates();
        const list = (data && data.success && Array.isArray(data.certificates)) ? data.certificates : [];
        setCerts(list);
        setPurchasedOffsets(list.reduce((sum, c) => sum + (parseFloat(c.volume_mt) || 0), 0));
      } catch (e) {
        console.warn('Could not load certificates', e);
      } finally {
        setLoadingCerts(false);
      }
    })();
  }, []);

  const safeTarget = Number.isFinite(targetOffsets) && targetOffsets > 0 ? targetOffsets : 1.0;
  const progressPercent = Math.min(((purchasedOffsets / safeTarget) * 100), 100).toFixed(1);

  // Portfolio Scope Target Distributions
  const retiredOffsets = certs.filter(c => c.status === 'RETIRED').reduce((sum, c) => sum + (parseFloat(c.volume_mt) || 0), 0);
  const escrowOffsets = certs.filter(c => c.status !== 'RETIRED').reduce((sum, c) => sum + (parseFloat(c.volume_mt) || 0), 0);

  const scope1Target = Math.round(targetOffsets * 0.20);
  const scope2Target = Math.round(targetOffsets * 0.30);
  const scope3Target = Math.round(targetOffsets * 0.50);

  const scope1Purchased = Math.min(purchasedOffsets, scope1Target);
  const scope2Purchased = Math.min(Math.max(purchasedOffsets - scope1Target, 0), scope2Target);
  const scope3Purchased = Math.max(purchasedOffsets - scope1Target - scope2Target, 0);

  const handleExportBRSR = () => {
    setIsExporting(true);
    const lines = [
      'CarbonX — BRSR & Scope 1-3 Audit Export',
      '=======================================',
      `Reporting entity: ${companyName}`,
      `Reporting period: ${new Date().getFullYear()}`,
      `Target offset volume: ${targetOffsets} MT CO2e`,
      `Purchased (escrow + retired): ${purchasedOffsets.toFixed(2)} MT CO2e`,
      `  - Permanently Retired: ${retiredOffsets.toFixed(2)} MT CO2e`,
      `  - Held in Escrow: ${escrowOffsets.toFixed(2)} MT CO2e`,
      `Progress: ${progressPercent}%`,
      '',
      'OFFSET PORTFOLIO BREAKDOWN',
      '--------------------------',
      `Scope 1 (Direct Operations): ${scope1Purchased.toFixed(2)} / ${scope1Target} MT`,
      `Scope 2 (Electricity & Power): ${scope2Purchased.toFixed(2)} / ${scope2Target} MT`,
      `Scope 3 (Agri Supply Chain): ${scope3Purchased.toFixed(2)} / ${scope3Target} MT`,
      '',
      'CERTIFICATE LEDGER',
      '------------------',
      ...(certs.length
        ? certs.flatMap((c) => [
            `${c.id} | ${c.volume_mt} MT | ${c.status} | issued ${c.issued_date} | ref ${c.tx_hash || '—'}`,
            `   source: ${(c.source_parcels || []).join(', ')}`,
          ])
        : ['(no certificates yet — purchase credits on the marketplace)']),
      '',
      `Generated: ${new Date().toISOString()}`,
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `brsr_report_${new Date().toISOString().slice(0, 10)}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    setIsExporting(false);
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Corporate Profile Header */}
        <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
              Enterprise ESG Desk
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">{companyName}</h1>
            <p className="text-xs text-slate-500 mt-0.5">Corporate Net-Zero Carbon Neutrality & BRSR Reporting.</p>
          </div>

          <div className="flex gap-3">
            <button
              onClick={() => navigate('/marketplace')}
              className="px-4 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-2"
            >
              <Sparkles className="w-4 h-4 text-emerald-300" />
              <span>Browse Marketplace</span>
            </button>
          </div>
        </div>

        {/* Net-Zero Progress Bar */}
        <div className="bg-[#0C2A18] text-white border border-emerald-900 shadow-sm rounded-xl p-6 space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div>
              <p className="text-xs font-bold text-emerald-300 uppercase tracking-wider">Corporate Decarbonization Progress</p>
              <h2 className="text-2xl sm:text-3xl font-extrabold font-manrope text-white mt-1">
                {purchasedOffsets.toFixed(2)} / {targetOffsets} MT CO2e
              </h2>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <label className="text-[10px] font-bold text-emerald-300 uppercase tracking-wider flex items-center gap-1.5">
                Your target (MT)
                <input
                  type="number"
                  min="1"
                  value={targetInput}
                  onChange={(e) => handleTargetChange(e.target.value)}
                  className="w-24 px-2 py-1 bg-emerald-950 border border-emerald-800 rounded-lg text-xs font-mono text-white focus:outline-none focus:border-emerald-400"
                />
              </label>
              <span className="text-lg sm:text-xl font-extrabold font-mono text-[#D1FAE5]">{progressPercent}% Achieved</span>
            </div>
          </div>

          <div className="w-full bg-emerald-950 border border-emerald-800 h-3.5 rounded-full overflow-hidden">
            <div
              className="bg-emerald-400 h-full rounded-full transition-all duration-1000"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
        </div>

        {/* Offset Portfolio Targets Breakdown */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
            <div>
              <h2 className="text-base font-bold text-slate-900 font-manrope">Corporate Offset Portfolio Targets</h2>
              <p className="text-xs text-slate-500">Decarbonization target breakdown across GHG Protocol Scope 1, 2, and 3 tiers.</p>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full">
                {retiredOffsets.toFixed(1)} MT Retired · {escrowOffsets.toFixed(1)} MT in Escrow
              </span>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-slate-700">Scope 1 (Direct)</span>
                <span className="text-[10px] font-bold text-slate-500 bg-slate-200/60 px-2 py-0.5 rounded">20% Weight</span>
              </div>
              <p className="text-xl font-bold font-manrope text-slate-900">
                {scope1Purchased.toFixed(1)} / {scope1Target} MT
              </p>
              <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
                <div
                  className="bg-emerald-600 h-full rounded-full transition-all duration-700"
                  style={{ width: `${Math.min((scope1Purchased / Math.max(scope1Target, 1)) * 100, 100)}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-500">Fuel combustion, on-site fleet emissions.</p>
            </div>

            <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-slate-700">Scope 2 (Electricity)</span>
                <span className="text-[10px] font-bold text-slate-500 bg-slate-200/60 px-2 py-0.5 rounded">30% Weight</span>
              </div>
              <p className="text-xl font-bold font-manrope text-slate-900">
                {scope2Purchased.toFixed(1)} / {scope2Target} MT
              </p>
              <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
                <div
                  className="bg-emerald-600 h-full rounded-full transition-all duration-700"
                  style={{ width: `${Math.min((scope2Purchased / Math.max(scope2Target, 1)) * 100, 100)}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-500">Purchased electricity & facility cooling.</p>
            </div>

            <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4 space-y-2">
              <div className="flex justify-between items-center">
                <span className="text-xs font-bold text-slate-700">Scope 3 (Agri Supply Chain)</span>
                <span className="text-[10px] font-bold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded">50% Weight</span>
              </div>
              <p className="text-xl font-bold font-manrope text-slate-900">
                {scope3Purchased.toFixed(1)} / {scope3Target} MT
              </p>
              <div className="w-full bg-slate-200 h-2 rounded-full overflow-hidden">
                <div
                  className="bg-emerald-600 h-full rounded-full transition-all duration-700"
                  style={{ width: `${Math.min((scope3Purchased / Math.max(scope3Target, 1)) * 100, 100)}%` }}
                />
              </div>
              <p className="text-[10px] text-slate-500">Agricultural procurement & smallholder farm sourcing.</p>
            </div>
          </div>
        </div>

        {/* BRSR Export Card & Procurement Certificates */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">

          {/* BRSR Export Card */}
          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-emerald-50 text-emerald-800 rounded-xl flex items-center justify-center">
                <FileText className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">BRSR & Scope 1-3 Audit Export</h3>
                <p className="text-xs text-slate-500">Business Responsibility and Sustainability Reporting.</p>
              </div>
            </div>

            <p className="text-xs text-slate-600 leading-relaxed">
              Export an audit report containing your escrow certificate ledger, source parcels, and escrow references for regulatory compliance.
            </p>

            <button
              onClick={handleExportBRSR}
              disabled={isExporting}
              className="w-full py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
            >
              <Download className="w-4 h-4" />
              <span>{isExporting ? 'Generating Report...' : 'Download BRSR Report'}</span>
            </button>
          </div>

          {/* Procurement Certificates */}
          <div className="bg-white border border-slate-200 border-l-4 border-l-emerald-600 shadow-sm rounded-xl p-6 space-y-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-emerald-50 text-emerald-800 rounded-xl flex items-center justify-center">
                <ShieldCheck className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-base font-bold text-slate-900">Historical Procurement Certificates</h3>
                <p className="text-xs text-slate-500">Review active certificates held in escrow or retired.</p>
              </div>
            </div>

            <div className="space-y-2">
              {loadingCerts ? (
                <div className="flex items-center gap-2 text-xs text-slate-500 p-3">
                  <Loader2 className="w-4 h-4 animate-spin" /> Loading certificate ledger…
                </div>
              ) : certs.length === 0 ? (
                <div className="bg-[#F8FAF8] border border-slate-200 rounded-lg p-4 text-xs text-slate-500 text-center space-y-2">
                  <p>No certificates yet.</p>
                  <button
                    onClick={() => navigate('/marketplace')}
                    className="px-3 py-1.5 bg-[#0C2A18] text-white rounded-lg font-bold hover:bg-[#15803D]"
                  >
                    Purchase credits on the marketplace
                  </button>
                </div>
              ) : (
                certs.map((c) => (
                  <div
                    key={c.id}
                    onClick={() => navigate(`/buyer/certificates/${c.id}`)}
                    className="bg-[#F8FAF8] border border-slate-200 rounded-lg p-3 flex justify-between items-center hover:border-emerald-600 cursor-pointer transition-all"
                  >
                    <div>
                      <p className="text-xs font-mono font-bold text-slate-900">{c.id}</p>
                      <p className="text-[10px] text-slate-500">
                        {c.volume_mt} MT CO2e : {c.status === 'RETIRED' ? 'Permanently Retired' : 'Held in Escrow'}
                        {c.crop ? ` · ${c.crop}` : ''}
                      </p>
                    </div>
                    <ArrowRight className="w-4 h-4 text-emerald-700" />
                  </div>
                ))
              )}
            </div>
          </div>

        </div>

      </div>
    </div>
  );
}
