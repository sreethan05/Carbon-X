import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import { ArrowLeft, ShieldCheck, Hash, Download } from 'lucide-react';
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
            month: h.date ? `${h.month} (${h.date})` : h.month,
            ndvi: h.ndvi,
          })));
        } else {
          setTrendData([]);
        }
      } catch {
        if (!cancelled) setLoadError('Analytics service unreachable. Is the backend running?');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [farmId]);

  // Live ledger: WebSocket push when available, 15s polling as fallback —
  // a sale/split/retire lands on the farmer's screen without a refresh.
  useEffect(() => {
    if (!farmId) return undefined;
    let ws = null;
    let pollTimer = null;
    let closed = false;

    const mergeChain = (payload) => {
      setPassport((prev) => (prev ? {
        ...prev,
        ledger: {
          events: payload.events ?? prev.ledger?.events ?? 0,
          verified: payload.verified ?? prev.ledger?.verified ?? false,
          tail_hash: payload.tail_hash ?? prev.ledger?.tail_hash,
          types: payload.types ?? prev.ledger?.types ?? [],
        },
      } : prev));
    };

    const refresh = async () => {
      if (document.hidden) return;
      try {
        const chain = await getFarmLedger(farmId);
        if (!chain || !chain.success) return;
        mergeChain({
          events: chain.verification?.length ?? chain.events?.length,
          verified: chain.verification?.valid,
          tail_hash: chain.verification?.tail_hash,
          types: (chain.events || []).map((e) => e.type),
        });
      } catch { /* transient — next tick retries */ }
    };

    try {
      const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      ws = new WebSocket(`${wsProto}//${window.location.host}/py-api/ws/ledger/${farmId}`);
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.type === 'snapshot') {
            mergeChain({ events: data.events, verified: data.verified, tail_hash: data.tail_hash });
          } else {
            refresh(); // pull authoritative state on each pushed event
          }
        } catch { /* ignore malformed frames */ }
      };
      ws.onerror = () => { if (!pollTimer) pollTimer = setInterval(refresh, 15000); };
      ws.onclose = () => { if (!closed && !pollTimer) pollTimer = setInterval(refresh, 15000); };
    } catch {
      pollTimer = setInterval(refresh, 15000);
    }

    return () => {
      closed = true;
      if (ws) { try { ws.close(); } catch { /* noop */ } }
      if (pollTimer) clearInterval(pollTimer);
    };
  }, [farmId]);

  // Farmer-facing analytics export (#34): passport summary + NDVI history as CSV.
  const exportAnalyticsCsv = () => {
    const rows = [["section", "key", "value"]];
    const pp = passport || {};
    const summary = [
      ["passport_id", pp.passport_id],
      ["farm_name", pp.farm_name],
      ["owner_name", pp.owner_name],
      ["crop", pp.crop],
      ["acreage_ha", pp.acreage],
      ["badge", pp.badge],
      ["sentinel_ndvi", pp.sentinel_ndvi],
      ["carbon_tonnes", pp.carbon_tonnes],
      ["annual_credits", pp.annual_credits],
      ["status", pp.status],
      ["expected_income_inr", pp.expected_earnings?.expected_income_inr],
      ["income_low_inr", pp.expected_earnings?.range_inr?.min],
      ["income_high_inr", pp.expected_earnings?.range_inr?.max],
      ["evidence_quality", pp.trust?.evidence_quality],
      ["uncertainty_pct", pp.trust?.uncertainty_pct],
      ["ledger_verified", pp.ledger?.verified],
      ["ledger_tail_hash", pp.ledger?.tail_hash],
      ["last_monitored_at", pp.monitoring?.last_monitored_at],
      ["at_risk", pp.monitoring?.at_risk],
    ];
    summary.forEach(([k, v]) => rows.push(["passport", k, v ?? ""]));
    trendData.forEach((d) => rows.push(["ndvi_history", d.month, d.ndvi]));
    const csv = rows.map((r) => r.map((c) => `"${String(c ?? "").replace(/"/g, '""')}"`).join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `carbonx_passport_${(pp.passport_id || farmId || "farm").replace(/[^\w-]/g, "_")}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Evidence components the credit engine actually implements (docs/MRV_METHODOLOGY.md §6).
  // This card renders the passport's real trust block — no projected practice
  // deltas are invented client-side, because no practice-factor model exists yet.
  const COMPONENT_META = [
    ['practice_photo', 'Practice photo captured', '0.25', 'No photo-capture flow exists in the app yet.'],
    ['geotag_inside_boundary', 'Geotag inside boundary', '0.25', 'A GPS-stamped ground photo — not captured yet.'],
    ['fpo_or_registry_verified', 'FPO / registry verified', '0.25', 'Granted by REGISTRY, REGISTRY_DOC or FPO badges.'],
    ['current_satellite_ndvi', 'Current satellite NDVI', '0.15', 'Passes when the farm has a stored Sentinel-2 NDVI.'],
    ['baseline_established', 'Baseline established', '0.10', 'Needs a stored pre-enrollment baseline series (roadmap).'],
  ];
  const trustComponents = passport?.trust?.components || null;

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

        {/* Evidence Checklist — the real engine components behind the deduction */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-forest-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary" />
                <h2 className="text-base font-bold text-carbon-900">Evidence Checklist — What Drives Your Deduction</h2>
              </div>
              <p className="text-xs text-agriText-muted">
                Deduction = 30% − 20% × evidence quality, floored at 10%. Every component below maps 1:1 to the credit engine.
              </p>
            </div>
            {passport?.trust && (
              <span className="text-[10px] font-bold text-agriText-subtle bg-warm-cream px-2 py-1 rounded shrink-0">
                Current deduction: −{passport.trust.uncertainty_pct}%
              </span>
            )}
          </div>

          {trustComponents ? (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
              {COMPONENT_META.map(([key, label, weight, hint]) => {
                const passed = Boolean(trustComponents[key]?.passed);
                return (
                  <div
                    key={key}
                    className={`rounded-xl border p-3 space-y-1 ${passed ? 'border-emerald-200 bg-emerald-50/50' : 'border-forest-100 bg-surface-sage/30'}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${passed ? 'text-emerald-800' : 'text-agriText-subtle'}`}>
                        {passed ? '✓ passed' : '— not yet'}
                      </span>
                      <span className="text-[10px] font-mono font-bold text-agriText-muted">w {weight}</span>
                    </div>
                    <p className="text-xs font-bold text-carbon-900">{label}</p>
                    <p className="text-[10px] text-agriText-muted leading-relaxed">{hint}</p>
                  </div>
                );
              })}
            </div>
          ) : (
            <p className="text-xs text-agriText-muted">
              Passport trust components are unavailable{loadError ? ` (${loadError})` : ''}.
            </p>
          )}

          <p className="text-[11px] text-agriText-muted bg-surface-sage/30 border border-forest-100 rounded-xl p-3 leading-relaxed">
            Practice-specific factor tables (zero-till, AWD rice, cover crops) are on the MRV roadmap — today the engine
            credits the plot-level NDVI improvement plus a crop-calibrated IPCC-style soil factor. To try different
            assumptions, use the Earnings Calculator on your dashboard; it calls the same engine.
          </p>
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
            <div className="flex items-center gap-2">
              <button
                onClick={exportAnalyticsCsv}
                className="px-3 py-1.5 bg-white border border-forest-200 text-carbon-800 hover:bg-surface-sage rounded-lg text-[11px] font-bold transition-all flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" /> Export CSV
              </button>
              {passport?.ledger?.verified && (
                <span className="text-[10px] font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full">
                  ✓ CHAIN VERIFIED
                </span>
              )}
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 space-y-1">
              <span className="text-[10px] text-agriText-subtle font-semibold uppercase tracking-wider block">Expected Earnings (70% floor)</span>
              <span className="text-2xl font-extrabold text-primary font-manrope">
                {passport?.expected_earnings?.expected_income_inr != null
                  ? `₹${Number(passport.expected_earnings.expected_income_inr).toLocaleString('en-IN')}`
                  : '—'}
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

        {/* Stored NDVI measurements — no interpolated seasons */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-4">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-base font-bold text-carbon-900">Stored NDVI Measurements</h2>
              <p className="text-xs text-agriText-muted">Only real stored readings — a full per-date Sentinel-2 curve needs sequential satellite pulls (MRV roadmap).</p>
            </div>
            {trendData.length > 0 && (
              <div className="flex items-center gap-4 text-xs font-medium">
                <span className="flex items-center gap-1.5 text-primary font-bold">
                  <span className="w-3 h-3 bg-primary rounded-full inline-block" /> Sentinel-2 NDVI
                </span>
              </div>
            )}
          </div>

          {trendData.length === 0 ? (
            <div className="h-40 flex items-center justify-center border border-dashed border-forest-100 rounded-xl">
              <p className="text-xs text-agriText-muted">No stored NDVI readings for this farm yet.</p>
            </div>
          ) : (
            <div className="h-72 w-full pt-4">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trendData}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#EEF5EE" />
                  <XAxis dataKey="month" stroke="#526056" style={{ fontSize: '11px', fontWeight: '600' }} />
                  <YAxis domain={[0.2, 1.0]} stroke="#526056" style={{ fontSize: '11px', fontWeight: '600' }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1F2923', borderColor: '#323C34', borderRadius: '12px', color: '#FFF', fontSize: '12px' }}
                  />
                  <Line type="monotone" dataKey="ndvi" stroke="#16A34A" strokeWidth={3} dot={{ r: 4, fill: '#16A34A' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
