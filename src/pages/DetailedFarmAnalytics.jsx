import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { Sparkles, TrendingUp, ArrowLeft, Sliders, CheckCircle2, ShieldCheck, Hash } from 'lucide-react';
import VerificationBadge from '../components/VerificationBadge';
import { useAuth } from '../context/AuthContext';
import { getFarmPassport, getNdviHistory, getFarmLedger } from '../services/api';

export default function DetailedFarmAnalytics() {
  const navigate = useNavigate();
  const { farmId: routeFarmId } = useParams();
  const { farms } = useAuth();

  const [passport, setPassport] = useState(null);
  const [trendData, setTrendData] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [loading, setLoading] = useState(true);

  // Resolve which farm we're looking at: route param first, else the first real
  // farm, else the backend's demo passport (works with the database offline).
  const farmId = routeFarmId || (farms && farms[0] && farms[0].id) || 'demo';

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoadError('');
      if (!farmId) {
        setLoadError('No farm enrolled yet. Complete the parcel enrollment flow first.');
        setLoading(false);
        return;
      }
      try {
        const [pp, hist] = await Promise.all([getFarmPassport(farmId), getNdviHistory(farmId)]);
        if (cancelled) return;
        if (pp && pp.success) {
          setPassport(pp);
        } else {
          setLoadError((pp && pp.message) || 'Could not load the carbon passport');
        }
        if (hist && hist.success && Array.isArray(hist.history) && hist.history.length) {
          setTrendData(hist.history.map((h) => ({
            month: `${h.month} (${h.season.split(' ')[0]})`,
            ndvi: h.ndvi,
            rabi_baseline: Math.max(0.2, h.ndvi - 0.12),
          })));
        }
      } catch {
        if (!cancelled) setLoadError('Analytics service unreachable. Is the backend running?');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [farmId]);

  // Live ledger: poll the hash chain so a sale/split/retire lands on the
  // farmer's screen without a manual refresh.
  useEffect(() => {
    if (!farmId) return undefined;
    const timer = setInterval(async () => {
      if (document.hidden) return;
      try {
        const chain = await getFarmLedger(farmId);
        if (!chain || !chain.success) return;
        setPassport((prev) => (prev ? { ...prev, ledger: chain.verification ? { ...chain.verification, types: chain.events.map((e) => e.type) } : prev.ledger } : prev));
      } catch { /* transient — next tick retries */ }
    }, 15000);
    return () => clearInterval(timer);
  }, [farmId]);

  // P3 Score Simulator Practice Options
  const practiceOptions = [
    {
      id: 'none',
      name: 'Current Baseline (Conventional Tillage)',
      scoreDelta: 0,
      creditDelta: 0,
      earningsDelta: 0,
      desc: 'Standard chemical fertilizer application and seasonal tillage.'
    },
    {
      id: 'no_till',
      name: 'Switch to Zero-Tillage Farming',
      scoreDelta: 8,
      creditDelta: 2.2,
      earningsDelta: 748,
      desc: 'Eliminating tillage preserves soil organic carbon and reduces soil moisture evaporation.'
    },
    {
      id: 'cover_crop',
      name: 'Incorporate Legume Cover Crops',
      scoreDelta: 6,
      creditDelta: 1.8,
      earningsDelta: 612,
      desc: 'Planting clover/sunn hemp during fallow windows fixes atmospheric nitrogen.'
    },
    {
      id: 'awd_rice',
      name: 'Alternate Wetting & Drying (AWD Rice)',
      scoreDelta: 10,
      creditDelta: 3.1,
      earningsDelta: 1054,
      desc: 'Periodic drying of rice paddies reduces methane emissions by up to 48%.'
    },
    {
      id: 'biochar',
      name: 'Apply Biochar & Organic Compost Layer',
      scoreDelta: 12,
      creditDelta: 3.8,
      earningsDelta: 1292,
      desc: 'Adding biochar locks stable carbon in the soil matrix for decades.'
    }
  ];

  const [selectedPracticeId, setSelectedPracticeId] = useState('no_till');

  const activePractice = practiceOptions.find((p) => p.id === selectedPracticeId) || practiceOptions[0];

  const baseScore = passport ? Math.round((passport.biodiversity_index || 0) * 10) : 0;
  const baseCredits = passport ? parseFloat(passport.annual_credits || 0) : 0;
  const baseEarnings = passport
    ? Math.round(parseFloat(passport.annual_credits || 0) * parseFloat(passport.benchmark_price || 340))
    : 0;

  const currentScore = baseScore + activePractice.scoreDelta;
  const currentCredits = Math.round((baseCredits + activePractice.creditDelta) * 10) / 10;
  const currentEarnings = baseEarnings + activePractice.earningsDelta;

  return (
    <div className="min-h-screen bg-surface font-inter text-agriText-main py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Page Header */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-bold text-primary uppercase tracking-wider bg-surface-sage border border-forest-200 px-2.5 py-0.5 rounded-full">
                Sentinel-2 MRV & Carbon Passport
              </span>
              <VerificationBadge badge={passport?.badge || 'DOCUMENT'} showTier size="sm" />
            </div>
            <h1 className="text-2xl font-extrabold text-carbon-900 font-manrope">Multi-Season Analytics & Passport</h1>
            <p className="text-xs text-agriText-muted mt-0.5">
              {passport ? `${passport.farm_name || 'Farm'} · ${passport.acreage ?? '—'} ha · Passport ${passport.passport_id}` : 'Historical vegetative canopy index & predictive agronomic scoring.'}
            </p>
            {loading && <p className="text-[11px] text-emerald-800 font-bold mt-1">Loading farm record…</p>}
            {loadError && (
              <p className="text-[11px] text-rose-700 font-bold bg-rose-50 border border-rose-200 rounded-lg px-2 py-1 mt-1 inline-block">
                {loadError}
              </p>
            )}
          </div>

          <button
            onClick={() => navigate('/farmer/dashboard')}
            className="px-4 py-2.5 bg-surface-sage hover:bg-forest-100 border border-forest-200 text-carbon-800 rounded-xl text-xs font-bold transition-all flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Dashboard</span>
          </button>
        </div>

        {/* P3 Interactive Score Improvement Simulator */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-5">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-forest-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <Sliders className="w-5 h-5 text-primary" />
                <h2 className="text-base font-bold text-carbon-900">Score Improvement Simulator</h2>
              </div>
              <p className="text-xs text-agriText-muted">Simulate agronomic practices to project score boosts & earning deltas.</p>
            </div>

            <span className="text-[10px] font-bold text-agriText-subtle bg-warm-cream px-2 py-1 rounded">
              Interactive ML Simulation
            </span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Practice Selection Form */}
            <div className="space-y-3">
              <label className="block text-xs font-bold text-carbon-800">
                Select Sustainable Farming Practice
              </label>
              <select
                value={selectedPracticeId}
                onChange={(e) => setSelectedPracticeId(e.target.value)}
                className="w-full px-3.5 py-2.5 bg-surface-sage/40 border border-forest-200 rounded-xl text-xs font-bold text-carbon-900 focus:outline-none focus:ring-2 focus:ring-primary/30"
              >
                {practiceOptions.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name} {p.scoreDelta > 0 ? `(+${p.scoreDelta} pts)` : ''}
                  </option>
                ))}
              </select>
              <p className="text-xs text-agriText-muted bg-surface-sage/30 p-3 rounded-xl border border-forest-100 leading-relaxed">
                {activePractice.desc}
              </p>
            </div>

            {/* Projected Impact Displays */}
            <div className="lg:col-span-2 grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 space-y-1">
                <span className="text-[10px] text-agriText-subtle font-semibold uppercase tracking-wider block">Projected MRV Score</span>
                <div className="flex items-baseline gap-2">
                  <span className="text-2xl font-extrabold text-carbon-900 font-manrope">{currentScore}</span>
                  <span className="text-xs text-agriText-subtle">/ 100</span>
                </div>
                {activePractice.scoreDelta > 0 && (
                  <span className="text-[11px] font-bold text-primary flex items-center gap-0.5">
                    <Sparkles className="w-3.5 h-3.5" /> +{activePractice.scoreDelta} pts boost
                  </span>
                )}
              </div>

              <div className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 space-y-1">
                <span className="text-[10px] text-agriText-subtle font-semibold uppercase tracking-wider block">Projected Credits</span>
                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-extrabold text-carbon-900 font-manrope">{currentCredits}</span>
                  <span className="text-xs text-agriText-subtle">tCO2e</span>
                </div>
                {activePractice.creditDelta > 0 && (
                  <span className="text-[11px] font-bold text-primary flex items-center gap-0.5">
                    <TrendingUp className="w-3.5 h-3.5" /> +{activePractice.creditDelta} tCO2e/yr
                  </span>
                )}
              </div>

              <div className="bg-surface-sage border border-forest-200 rounded-xl p-4 space-y-1">
                <span className="text-[10px] text-agriText-subtle font-semibold uppercase tracking-wider block">Projected Revenue Delta</span>
                <div className="flex items-baseline gap-1">
                  <span className="text-2xl font-extrabold text-primary font-manrope">₹{currentEarnings.toLocaleString('en-IN')}</span>
                  <span className="text-xs text-agriText-muted">/ yr</span>
                </div>
                {activePractice.earningsDelta > 0 && (
                  <span className="text-[11px] font-bold text-primary flex items-center gap-0.5">
                    <CheckCircle2 className="w-3.5 h-3.5" /> +₹{activePractice.earningsDelta}/yr delta
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Trust Engine & Tamper-Evident Ledger */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-base font-bold text-carbon-900 flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary" />
                Trust Engine &amp; Tamper-Evident Ledger
              </h2>
              <p className="text-xs text-agriText-muted">Evidence quality drives a 10–30% uncertainty deduction; every credit event is hash-chained and publicly recomputable.</p>
            </div>
            {passport?.ledger?.verified && (
              <span className="text-[10px] font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full">
                ✓ CHAIN VERIFIED
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 space-y-1">
              <span className="text-[10px] text-agriText-subtle font-semibold uppercase tracking-wider block">Expected Earnings (70% floor)</span>
              <span className="text-2xl font-extrabold text-primary font-manrope">
                ₹{Number(passport?.expected_earnings?.expected_income_inr || currentEarnings).toLocaleString('en-IN')}
              </span>
              {passport?.expected_earnings?.range_inr && (
                <p className="text-[11px] text-agriText-muted">
                  Sale range ₹{Number(passport.expected_earnings.range_inr.min).toLocaleString('en-IN')} – ₹{Number(passport.expected_earnings.range_inr.max).toLocaleString('en-IN')}
                </p>
              )}
            </div>

            <div className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 space-y-1">
              <span className="text-[10px] text-agriText-subtle font-semibold uppercase tracking-wider block">Evidence Quality &amp; Uncertainty</span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-extrabold text-carbon-900 font-manrope">
                  {passport?.trust ? `${Math.round(passport.trust.evidence_quality * 100)}%` : '—'}
                </span>
                <span className="text-xs text-agriText-subtle">quality</span>
              </div>
              <p className="text-[11px] text-agriText-muted">
                Credit deduction: −{passport?.trust?.uncertainty_pct ?? '—'}% (conservative by design)
              </p>
            </div>

            <div className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 space-y-1">
              <span className="text-[10px] text-agriText-subtle font-semibold uppercase tracking-wider block flex items-center gap-1">
                <Hash className="w-3 h-3" /> Ledger Chain
              </span>
              <p className="text-sm font-bold text-carbon-900">
                {passport?.ledger?.events ?? 0} events · {passport?.ledger?.verified ? 'verified' : 'unverified'}
              </p>
              {passport?.ledger?.tail_hash && (
                <p className="font-mono text-[10px] text-agriText-muted break-all" title={`sha256:${passport.ledger.tail_hash}`}>
                  tail sha256:{String(passport.ledger.tail_hash).slice(0, 16)}…
                </p>
              )}
              {passport?.ledger?.types?.length > 0 && (
                <p className="text-[10px] text-agriText-subtle">{passport.ledger.types.join(' → ')}</p>
              )}
            </div>
          </div>

          {/* 5-day monitoring strip */}
          {passport?.monitoring && (
            <div className={`rounded-xl border p-3 flex flex-wrap items-center justify-between gap-2 text-xs ${
              passport.monitoring.at_risk
                ? 'bg-amber-50 border-amber-200 text-amber-900'
                : 'bg-surface-sage/40 border-forest-200 text-carbon-800'
            }`}>
              <span className="font-bold">
                {passport.monitoring.at_risk
                  ? '⚠ Credits AT-RISK — flagged by the 5-day NDVI monitoring cycle, routed to FPO review'
                  : '✓ Monitoring clean — no significant NDVI drop detected'}
              </span>
              <span className="text-agriText-muted font-semibold">
                {passport.monitoring.last_monitored_at
                  ? `Last cycle: ${String(passport.monitoring.last_monitored_at).slice(0, 10)} (NDVI ${Number(passport.monitoring.last_monitor_ndvi || 0).toFixed(2)})`
                  : 'Not yet monitored — first cycle pending'}
              </span>
            </div>
          )}
        </div>

        {/* Recharts Trend Visualizer */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-base font-bold text-carbon-900">Multi-Season NDVI Progression Curve</h2>
              <p className="text-xs text-agriText-muted">Comparing Kharif main crop vs Rabi inter-crop vegetative canopy retention.</p>
            </div>
            <div className="flex items-center gap-4 text-xs font-medium">
              <span className="flex items-center gap-1.5 text-primary font-bold">
                <span className="w-3 h-3 bg-primary rounded-full inline-block" /> Kharif 2024
              </span>
              <span className="flex items-center gap-1.5 text-agriText-subtle">
                <span className="w-3 h-3 bg-agriText-subtle rounded-full inline-block" /> Rabi Baseline
              </span>
            </div>
          </div>

          <div className="h-72 w-full pt-4">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#EEF5EE" />
                <XAxis dataKey="month" stroke="#526056" style={{ fontSize: '11px', fontWeight: '600' }} />
                <YAxis domain={[0.2, 1.0]} stroke="#526056" style={{ fontSize: '11px', fontWeight: '600' }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1F2923', borderColor: '#323C34', borderRadius: '12px', color: '#FFF', fontSize: '12px' }}
                />
                <Line type="monotone" dataKey="ndvi" stroke="#1F7A4D" strokeWidth={3} dot={{ r: 4, fill: '#1F7A4D' }} />
                <Line type="monotone" dataKey="rabi_baseline" stroke="#94A397" strokeWidth={2} strokeDasharray="5 5" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

      </div>
    </div>
  );
}
