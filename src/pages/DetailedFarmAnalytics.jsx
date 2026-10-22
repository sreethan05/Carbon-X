import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
import {
  ArrowLeft,
  ShieldCheck,
  Hash,
  Download,
  Camera,
  Upload,
  MapPin,
  CheckCircle2,
  AlertCircle,
  Loader2,
  RefreshCw,
  FileText,
} from 'lucide-react';
import VerificationBadge from '../components/VerificationBadge';
import { useAuth } from '../context/AuthContext';
import {
  getFarmPassport,
  getNdviHistory,
  getFarmLedger,
  uploadEvidencePhoto,
  addEvidenceGeotag,
  getFarmEvidence,
  getEvidencePhotoUrl,
  PY_API_BASE,
} from '../services/api';

export default function DetailedFarmAnalytics() {
  const navigate = useNavigate();
  const { farmId: routeFarmId } = useParams();
  const { farms } = useAuth();

  const [passport, setPassport] = useState(null);
  const [trendData, setTrendData] = useState([]);
  const [loadError, setLoadError] = useState('');
  const [loading, setLoading] = useState(true);

  // Evidence capture state
  const [evidenceData, setEvidenceData] = useState(null);
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [useDeviceLocation, setUseDeviceLocation] = useState(true);
  const [photoStatus, setPhotoStatus] = useState(null);
  const [uploadingPhoto, setUploadingPhoto] = useState(false);

  const [geotagLat, setGeotagLat] = useState('');
  const [geotagLon, setGeotagLon] = useState('');
  const [submittingGeotag, setSubmittingGeotag] = useState(false);
  const [geotagStatus, setGeotagStatus] = useState(null);
  const [fetchingGps, setFetchingGps] = useState(false);

  // Resolve which farm we're looking at: route param first, else the first real
  // farm, else the backend's demo passport (works with the database offline).
  const farmId = routeFarmId || (farms && farms[0] && farms[0].id) || 'demo';

  const reloadEvidenceAndPassport = async () => {
    if (!farmId) return;
    try {
      const [pp, ev] = await Promise.all([getFarmPassport(farmId), getFarmEvidence(farmId)]);
      if (pp && pp.success) setPassport(pp);
      if (ev && ev.success) setEvidenceData(ev);
    } catch { /* ignore */ }
  };

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
        const [pp, hist, ev] = await Promise.all([
          getFarmPassport(farmId),
          getNdviHistory(farmId),
          getFarmEvidence(farmId),
        ]);
        if (cancelled) return;
        if (pp && pp.success) {
          setPassport(pp);
        } else {
          setLoadError((pp && pp.message) || 'Could not load the carbon passport');
        }
        if (ev && ev.success) {
          setEvidenceData(ev);
        }
        if (hist && hist.success && Array.isArray(hist.history) && hist.history.length) {
          setTrendData(hist.history.map((h) => ({
            month: h.date ? `${h.month} (${h.date})` : h.month,
            ndvi: h.ndvi,
          })));
        } else if (pp && pp.success && pp.sentinel_ndvi != null) {
          setTrendData([{
            month: 'Baseline / Latest Scan',
            ndvi: parseFloat(pp.sentinel_ndvi),
          }]);
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
      setPassport((prev) => {
        if (!prev) return prev;
        const currentEvents = prev.ledger?.events;
        const eventCount = typeof payload.events === 'number'
          ? payload.events
          : Array.isArray(payload.events)
          ? payload.events.length
          : typeof currentEvents === 'number'
          ? currentEvents
          : 0;

        return {
          ...prev,
          ledger: {
            events: eventCount,
            verified: payload.verified ?? prev.ledger?.verified ?? false,
            tail_hash: payload.tail_hash ?? prev.ledger?.tail_hash,
            types: payload.types ?? prev.ledger?.types ?? [],
          },
        };
      });
    };

    const refresh = async () => {
      if (document.hidden) return;
      try {
        const chain = await getFarmLedger(farmId);
        if (!chain || !chain.success) return;
        mergeChain({
          events: chain.verification?.length ?? chain.events?.length ?? 0,
          verified: chain.verification?.valid,
          tail_hash: chain.verification?.tail_hash,
          types: (chain.events || []).map((e) => e.type),
        });
      } catch { /* transient — next tick retries */ }
    };

    try {
      let wsUrl = '';
      if (PY_API_BASE && (PY_API_BASE.startsWith('http://') || PY_API_BASE.startsWith('https://'))) {
        const wsProto = PY_API_BASE.startsWith('https') ? 'wss:' : 'ws:';
        wsUrl = `${wsProto}//${PY_API_BASE.replace(/^https?:\/\//, '')}/ws/ledger/${farmId}`;
      } else {
        const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        wsUrl = `${wsProto}//${window.location.host}${PY_API_BASE || '/py-api'}/ws/ledger/${farmId}`;
      }

      const token = window.localStorage.getItem('carbonx_token');
      if (!token) throw new Error('Authentication required for live ledger updates');
      ws = new WebSocket(`${wsUrl}?token=${encodeURIComponent(token)}`);
      ws.onopen = () => {
        refresh();
      };
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (data.type === 'snapshot') {
            const eventList = Array.isArray(data.events) ? data.events : [];
            mergeChain({
              events: eventList.length,
              verified: data.verified ?? (eventList.length > 0),
              tail_hash: data.tail_hash || (eventList.length ? eventList[eventList.length - 1]?.hash : undefined),
              types: data.types || eventList.map((e) => e.type),
            });
            refresh();
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
      ["phone", pp.phone],
      ["village", pp.village],
      ["district", pp.district],
      ["crop", pp.crop],
      ["acreage_ha", pp.acreage],
      ["badge", pp.badge],
      ["sentinel_ndvi", pp.sentinel_ndvi],
      ["evi", pp.evi],
      ["carbon_tonnes", pp.carbon_tonnes],
      ["annual_credits", pp.annual_credits],
      ["credits_ci90_low", pp.credits_ci90?.low],
      ["credits_ci90_high", pp.credits_ci90?.high],
      ["formula_version", pp.formula_version],
      ["s2_scene", pp.s2_scene],
      ["status", pp.status],
      ["verification_hash", pp.verification_hash],
      ["expected_income_inr", pp.expected_earnings?.expected_income_inr],
      ["income_low_inr", pp.expected_earnings?.range_inr?.min],
      ["income_high_inr", pp.expected_earnings?.range_inr?.max],
      ["evidence_quality", pp.trust?.evidence_quality],
      ["uncertainty_pct", pp.trust?.uncertainty_pct],
      ["practice_photo_verified", pp.trust?.components?.practice_photo?.passed ?? evidenceData?.components?.practice_photo ?? false],
      ["geotag_inside_boundary", pp.trust?.components?.geotag_inside_boundary?.passed ?? evidenceData?.components?.geotag_inside_boundary ?? false],
      ["photo_count", evidenceData?.photo_count ?? 0],
      ["geotag_count", evidenceData?.geotag_count ?? 0],
      ["ledger_events", pp.ledger?.events ?? 0],
      ["ledger_verified", pp.ledger?.verified],
      ["ledger_tail_hash", pp.ledger?.tail_hash],
      ["last_monitored_at", pp.monitoring?.last_monitored_at],
      ["at_risk", pp.monitoring?.at_risk],
    ];
    summary.forEach(([k, v]) => rows.push(["passport", k, v ?? ""]));
    trendData.forEach((d) => rows.push(["ndvi_history", d.month, d.ndvi]));
    (evidenceData?.geotags || []).forEach((g, idx) => {
      rows.push(["geotag", `geotag_${idx + 1}`, `${g.latitude},${g.longitude} (inside: ${g.inside_boundary})`]);
    });
    (evidenceData?.photos || []).forEach((p, idx) => {
      rows.push(["photo", `photo_${idx + 1}`, `${p.sha256} (inside: ${p.inside_boundary})`]);
    });
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
  const COMPONENT_META = [
    ['practice_photo', 'Practice photo captured', '0.25', 'Ground photo verifying regenerative practices.'],
    ['geotag_inside_boundary', 'Geotag inside boundary', '0.25', 'GPS-stamped coordinate verified within parcel polygon.'],
    ['fpo_or_registry_verified', 'FPO / registry verified', '0.25', 'Granted by REGISTRY, REGISTRY_DOC or FPO badges.'],
    ['current_satellite_ndvi', 'Current satellite NDVI', '0.15', 'Passes when the farm has a stored Sentinel-2 NDVI.'],
    ['baseline_established', 'Baseline established', '0.10', 'Needs a stored pre-enrollment baseline series (roadmap).'],
  ];
  const trustComponents = passport?.trust?.components || null;

  const handlePhotoUpload = async (e) => {
    e.preventDefault();
    if (!photoFile) return;
    setUploadingPhoto(true);
    setPhotoStatus(null);
    try {
      let lat = null;
      let lon = null;
      if (useDeviceLocation && navigator.geolocation) {
        try {
          const pos = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, { timeout: 6000 });
          });
          lat = pos.coords.latitude;
          lon = pos.coords.longitude;
        } catch {
          // GPS read failed or denied — upload proceeds without explicit coords
        }
      }
      const res = await uploadEvidencePhoto(farmId, photoFile, {
        latitude: lat,
        longitude: lon,
        capturedAt: new Date().toISOString(),
      });
      if (res && res.success) {
        const geotag = res.photo?.geotag;
        const inside = geotag?.inside_boundary;
        setPhotoStatus({
          type: 'success',
          message: inside
            ? '✓ Photo accepted! GPS confirmed inside farm boundary.'
            : '✓ Photo stored! ' + (geotag ? '(Geotag was outside boundary)' : '(No GPS in EXIF; consider enabling device GPS)'),
        });
        if (photoPreview) URL.revokeObjectURL(photoPreview);
        setPhotoFile(null);
        setPhotoPreview(null);
        await reloadEvidenceAndPassport();
      } else {
        setPhotoStatus({
          type: 'error',
          message: res?.message || 'Could not upload photo.',
        });
      }
    } catch (err) {
      setPhotoStatus({ type: 'error', message: err.message || 'Photo upload failed.' });
    } finally {
      setUploadingPhoto(false);
    }
  };

  const handleFetchGps = () => {
    if (!navigator.geolocation) {
      setGeotagStatus({ type: 'error', message: 'Geolocation is not supported by your browser.' });
      return;
    }
    setFetchingGps(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeotagLat(pos.coords.latitude.toFixed(6));
        setGeotagLon(pos.coords.longitude.toFixed(6));
        setFetchingGps(false);
        setGeotagStatus({ type: 'success', message: 'Current location fetched successfully.' });
      },
      (err) => {
        setFetchingGps(false);
        setGeotagStatus({ type: 'error', message: `Could not fetch GPS: ${err.message}` });
      },
      { timeout: 8000 }
    );
  };

  const handleGeotagSubmit = async (e) => {
    e.preventDefault();
    const lat = parseFloat(geotagLat);
    const lon = parseFloat(geotagLon);
    if (!Number.isFinite(lat) || lat < -90 || lat > 90 || !Number.isFinite(lon) || lon < -180 || lon > 180) {
      setGeotagStatus({ type: 'error', message: 'Please enter valid coordinates (-90 to 90 lat, -180 to 180 lon).' });
      return;
    }
    setSubmittingGeotag(true);
    setGeotagStatus(null);
    try {
      const res = await addEvidenceGeotag(farmId, {
        latitude: lat,
        longitude: lon,
        captured_at: new Date().toISOString(),
      });
      if (res && res.success) {
        const inside = res.geotag?.inside_boundary;
        setGeotagStatus({
          type: 'success',
          message: inside
            ? '✓ Geotag verified inside farm boundary!'
            : `⚠️ Recorded point: ${res.geotag?.reason || 'outside boundary'}`,
        });
        setGeotagLat('');
        setGeotagLon('');
        await reloadEvidenceAndPassport();
      } else {
        setGeotagStatus({ type: 'error', message: res?.message || 'Could not record geotag.' });
      }
    } catch (err) {
      setGeotagStatus({ type: 'error', message: err.message || 'Geotag submission failed.' });
    } finally {
      setSubmittingGeotag(false);
    }
  };

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

        {!loading && !passport && (
          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-10 text-center space-y-4">
            <div className="w-16 h-16 bg-surface-sage border border-forest-200 rounded-full flex items-center justify-center mx-auto text-primary">
              <MapPin className="w-8 h-8" />
            </div>
            <h2 className="text-xl font-bold text-carbon-900">No Farm Parcel Found</h2>
            <p className="text-sm text-agriText-muted max-w-md mx-auto">
              {loadError || "You don't have a farm enrolled under this identifier yet. Complete satellite parcel enrollment to generate your MRV passport and live ledger."}
            </p>
            <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
              <button
                onClick={() => navigate('/farmer/land-verification')}
                className="px-5 py-2.5 bg-primary text-white font-bold text-xs rounded-xl hover:bg-forest-800 transition-all shadow-sm"
              >
                Enroll New Parcel
              </button>
              <button
                onClick={() => navigate('/farmer/dashboard')}
                className="px-5 py-2.5 bg-surface-sage border border-forest-200 text-carbon-800 font-bold text-xs rounded-xl hover:bg-forest-100 transition-all"
              >
                Back to Dashboard
              </button>
            </div>
          </div>
        )}

        {passport && (
          <>
            {/* Carbon Passport Overview Card */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-forest-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-primary" />
                <h2 className="text-base font-bold text-carbon-900">Carbon Passport &amp; MRV Record</h2>
              </div>
              <p className="text-xs text-agriText-muted mt-0.5">
                Official registry passport linking satellite verification, uncertainty intervals, and cryptographic identity.
              </p>
            </div>
            {passport && (
              <span className={`text-[10px] font-bold px-2.5 py-1 rounded-full uppercase tracking-wider ${
                passport.status === 'APPROVED MRV RECORD'
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                  : 'bg-amber-100 text-amber-900 border border-amber-200'
              }`}>
                {passport.status || 'PENDING MRV REVIEW'}
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-surface-sage/30 border border-forest-100 rounded-xl p-4 space-y-1">
              <span className="text-[10px] text-agriText-subtle font-bold uppercase tracking-wider block">Annual Carbon Credits</span>
              <p className="text-2xl font-extrabold text-carbon-900 font-manrope">
                {passport?.annual_credits ?? '—'} <span className="text-xs text-agriText-muted font-bold">tCO2e/yr</span>
              </p>
              <p className="text-[11px] text-agriText-muted">
                {passport?.carbon_tonnes ? `${passport.carbon_tonnes} tonnes soil/biomass` : 'Estimate pending'}
              </p>
              {passport?.credits_ci90 && (passport.credits_ci90.low != null || passport.credits_ci90.high != null) && (
                <p className="text-[10px] text-emerald-800 font-mono font-semibold">
                  CI90: {passport.credits_ci90.low ?? '—'} – {passport.credits_ci90.high ?? '—'} tCO2e
                </p>
              )}
            </div>

            <div className="bg-surface-sage/30 border border-forest-100 rounded-xl p-4 space-y-1">
              <span className="text-[10px] text-agriText-subtle font-bold uppercase tracking-wider block">Satellite Vegetative Scan</span>
              <div className="flex items-baseline gap-2">
                <span className="text-2xl font-extrabold text-primary font-manrope">
                  {passport?.sentinel_ndvi != null ? Number(passport.sentinel_ndvi).toFixed(2) : '—'}
                </span>
                <span className="text-xs text-agriText-muted font-medium">NDVI</span>
                {passport?.evi != null && (
                  <span className="text-xs text-agriText-muted font-mono">({Number(passport.evi).toFixed(2)} EVI)</span>
                )}
              </div>
              <p className="text-[11px] text-agriText-muted truncate" title={passport?.s2_scene || 'Copernicus Sentinel-2'}>
                {passport?.satellite_source || 'Sentinel-2 Harmonized'}
              </p>
            </div>

            <div className="bg-surface-sage/30 border border-forest-100 rounded-xl p-4 space-y-1">
              <span className="text-[10px] text-agriText-subtle font-bold uppercase tracking-wider block">Biodiversity &amp; Soil</span>
              <p className="text-2xl font-extrabold text-carbon-900 font-manrope">
                {passport?.biodiversity_index != null ? `${passport.biodiversity_index}` : '—'}
                <span className="text-xs text-agriText-muted font-medium"> / 100</span>
              </p>
              <p className="text-[11px] text-agriText-muted">
                Crop: <span className="font-semibold text-carbon-900">{passport?.crop || 'Not recorded'}</span>
                {passport?.irrigation ? ` · ${passport.irrigation}` : ''}
              </p>
            </div>

            <div className="bg-surface-sage/30 border border-forest-100 rounded-xl p-4 space-y-1">
              <span className="text-[10px] text-agriText-subtle font-bold uppercase tracking-wider block">MRV Passport Anchor</span>
              <p className="text-xs font-mono font-bold text-carbon-900 truncate" title={passport?.passport_id}>
                {passport?.passport_id || 'CX-FARM-DEMO'}
              </p>
              {passport?.verification_hash && (
                <p className="text-[10px] font-mono text-agriText-muted break-all" title={`hash:${passport.verification_hash}`}>
                  hash:{passport.verification_hash.slice(0, 16)}…
                </p>
              )}
              <p className="text-[10px] text-agriText-subtle">
                Methodology: <span className="font-semibold">{passport?.formula_version || 'VM0042-r2'}</span>
              </p>
            </div>
          </div>
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

        {/* Practice Evidence & Ground Verification Panel */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-6">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 border-b border-forest-100 pb-4">
            <div>
              <div className="flex items-center gap-2">
                <Camera className="w-5 h-5 text-primary" />
                <h2 className="text-base font-bold text-carbon-900">Ground Evidence &amp; Practice Verification</h2>
              </div>
              <p className="text-xs text-agriText-muted mt-0.5">
                Upload real photos of regenerative practices or record boundary-verified geotags. Each verified component increases evidence quality and lowers uncertainty deductions.
              </p>
            </div>
            {evidenceData && (
              <div className="flex items-center gap-2 shrink-0">
                <span className="text-[11px] font-bold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2.5 py-1 rounded-full">
                  {evidenceData.photo_count || 0} Photos · {evidenceData.geotag_count || 0} Geotags
                </span>
                <button
                  type="button"
                  onClick={reloadEvidenceAndPassport}
                  title="Refresh evidence"
                  className="p-1 text-agriText-muted hover:text-carbon-900 transition-colors"
                >
                  <RefreshCw className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* 1. Upload Practice Photo */}
            <form onSubmit={handlePhotoUpload} className="bg-surface-sage/30 border border-forest-100 rounded-xl p-4 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-carbon-900 flex items-center gap-1.5">
                  <Upload className="w-4 h-4 text-primary" /> Upload Practice Photo
                </span>
                <span className="text-[10px] text-agriText-muted font-mono">+0.25 weight</span>
              </div>
              <p className="text-[11px] text-agriText-muted">
                Accepts JPEG, PNG or WebP up to 8 MB. EXIF GPS coordinates are automatically extracted and verified against your farm boundary.
              </p>

              <div>
                <input
                  type="file"
                  id="evidence-photo-input"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) {
                      if (photoPreview) URL.revokeObjectURL(photoPreview);
                      setPhotoFile(file);
                      setPhotoPreview(URL.createObjectURL(file));
                      setPhotoStatus(null);
                    }
                    e.target.value = '';
                  }}
                />
                <label
                  htmlFor="evidence-photo-input"
                  className="border-2 border-dashed border-forest-200 hover:border-primary bg-white rounded-xl p-4 flex flex-col items-center justify-center gap-2 cursor-pointer transition-colors"
                >
                  {photoPreview ? (
                    <div className="space-y-2 text-center">
                      <img src={photoPreview} alt="Preview" className="w-32 h-24 object-cover rounded-lg mx-auto border border-forest-100" />
                      <span className="text-[11px] text-emerald-800 font-bold block">{photoFile?.name}</span>
                    </div>
                  ) : (
                    <>
                      <Camera className="w-6 h-6 text-primary" />
                      <span className="text-xs font-bold text-carbon-800">Tap to select or take photo</span>
                      <span className="text-[10px] text-agriText-muted">JPEG / PNG / WebP</span>
                    </>
                  )}
                </label>
              </div>

              <div className="flex items-center justify-between text-xs">
                <label className="flex items-center gap-2 text-agriText-muted cursor-pointer text-[11px]">
                  <input
                    type="checkbox"
                    checked={useDeviceLocation}
                    onChange={(e) => setUseDeviceLocation(e.target.checked)}
                    className="rounded text-primary focus:ring-primary h-3.5 w-3.5"
                  />
                  <span>Attach device GPS if EXIF is missing</span>
                </label>
              </div>

              <button
                type="submit"
                disabled={!photoFile || uploadingPhoto}
                className="w-full py-2.5 px-4 bg-primary text-white rounded-xl text-xs font-bold hover:bg-forest-800 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {uploadingPhoto ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" /> Uploading &amp; Verifying…
                  </>
                ) : (
                  <>
                    <Upload className="w-4 h-4" /> Submit Practice Photo
                  </>
                )}
              </button>

              {photoStatus && (
                <div
                  className={`p-2.5 rounded-lg text-xs font-medium border flex items-start gap-2 ${
                    photoStatus.type === 'success'
                      ? 'bg-emerald-50 text-emerald-900 border-emerald-200'
                      : 'bg-rose-50 text-rose-900 border-rose-200'
                  }`}
                >
                  {photoStatus.type === 'success' ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  )}
                  <span>{photoStatus.message}</span>
                </div>
              )}
            </form>

            {/* 2. Record Farm Geotag */}
            <form onSubmit={handleGeotagSubmit} className="bg-surface-sage/30 border border-forest-100 rounded-xl p-4 space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs font-bold text-carbon-900 flex items-center gap-1.5">
                  <MapPin className="w-4 h-4 text-primary" /> Record Parcel Geotag
                </span>
                <span className="text-[10px] text-agriText-muted font-mono">+0.25 weight</span>
              </div>
              <p className="text-[11px] text-agriText-muted">
                Record GPS coordinates from your field. Ray-casting verification validates containment inside your registered boundary.
              </p>

              <div className="flex justify-end">
                <button
                  type="button"
                  onClick={handleFetchGps}
                  disabled={fetchingGps}
                  className="px-2.5 py-1 bg-white border border-forest-200 text-carbon-800 hover:bg-forest-100 rounded-lg text-[11px] font-bold flex items-center gap-1 transition-colors"
                >
                  {fetchingGps ? <Loader2 className="w-3 h-3 animate-spin" /> : <MapPin className="w-3 h-3 text-primary" />}
                  <span>Use Device GPS</span>
                </button>
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[10px] font-bold text-agriText-subtle uppercase mb-1">Latitude</label>
                  <input
                    type="number"
                    step="any"
                    placeholder="e.g. 17.385044"
                    value={geotagLat}
                    onChange={(e) => setGeotagLat(e.target.value)}
                    className="w-full px-3 py-2 bg-white border border-forest-200 rounded-lg text-xs font-mono focus:outline-none focus:border-primary"
                  />
                </div>
                <div>
                  <label className="block text-[10px] font-bold text-agriText-subtle uppercase mb-1">Longitude</label>
                  <input
                    type="number"
                    step="any"
                    placeholder="e.g. 78.486671"
                    value={geotagLon}
                    onChange={(e) => setGeotagLon(e.target.value)}
                    className="w-full px-3 py-2 bg-white border border-forest-200 rounded-lg text-xs font-mono focus:outline-none focus:border-primary"
                  />
                </div>
              </div>

              <button
                type="submit"
                disabled={!geotagLat || !geotagLon || submittingGeotag}
                className="w-full py-2.5 px-4 bg-primary text-white rounded-xl text-xs font-bold hover:bg-forest-800 disabled:opacity-50 transition-colors flex items-center justify-center gap-2"
              >
                {submittingGeotag ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" /> Verifying Geotag…
                  </>
                ) : (
                  <>
                    <MapPin className="w-4 h-4" /> Verify &amp; Record Geotag
                  </>
                )}
              </button>

              {geotagStatus && (
                <div
                  className={`p-2.5 rounded-lg text-xs font-medium border flex items-start gap-2 ${
                    geotagStatus.type === 'success'
                      ? 'bg-emerald-50 text-emerald-900 border-emerald-200'
                      : 'bg-rose-50 text-rose-900 border-rose-200'
                  }`}
                >
                  {geotagStatus.type === 'success' ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  )}
                  <span>{geotagStatus.message}</span>
                </div>
              )}
            </form>
          </div>

          {/* 3. Submitted Evidence Records Gallery */}
          {((evidenceData?.photos && evidenceData.photos.length > 0) || (evidenceData?.geotags && evidenceData.geotags.length > 0)) ? (
            <div className="border-t border-forest-100 pt-4 space-y-3">
              <h3 className="text-xs font-bold text-carbon-900 uppercase tracking-wider">Submitted Ground Records</h3>
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
                {(evidenceData.photos || []).map((p, idx) => (
                  <div key={p.id || p.sha256 || idx} className="bg-white border border-forest-100 rounded-xl p-3 flex gap-3 items-center">
                    <img
                      src={getEvidencePhotoUrl(farmId, p.sha256)}
                      alt="Practice photo"
                      className="w-14 h-14 object-cover rounded-lg border border-forest-100 shrink-0 bg-surface-sage"
                      onError={(e) => {
                        e.target.onerror = null;
                        e.target.src = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='56' height='56' viewBox='0 0 24 24' fill='none' stroke='%23059669' stroke-width='2' stroke-linecap='round' stroke-linejoin='round'><path d='M14.5 4h-5L7 7H4a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2h-3l-2.5-3z'/><circle cx='12' cy='13' r='3'/></svg>";
                      }}
                    />
                    <div className="min-w-0 space-y-0.5">
                      <span className="text-[10px] font-mono font-bold text-agriText-muted block truncate">
                        {p.sha256 ? `${p.sha256.slice(0, 8)}…` : 'Photo'}
                      </span>
                      <span className="text-[10px] text-agriText-muted block">
                        {p.captured_at ? new Date(p.captured_at).toLocaleDateString() : p.created_at ? new Date(p.created_at).toLocaleDateString() : 'Recorded'}
                      </span>
                      <span
                        className={`text-[9px] font-bold px-1.5 py-0.5 rounded inline-block ${
                          p.inside_boundary
                            ? 'bg-emerald-100 text-emerald-800'
                            : 'bg-amber-100 text-amber-800'
                        }`}
                      >
                        {p.inside_boundary ? '✓ Inside boundary' : 'Geotag pending'}
                      </span>
                    </div>
                  </div>
                ))}
                {(evidenceData.geotags || []).map((g, idx) => (
                  <div key={g.id || idx} className="bg-white border border-forest-100 rounded-xl p-3 flex items-center justify-between">
                    <div className="space-y-0.5">
                      <span className="text-xs font-mono font-bold text-carbon-900 block">
                        {Number(g.latitude).toFixed(4)}, {Number(g.longitude).toFixed(4)}
                      </span>
                      <span className="text-[10px] text-agriText-muted block">
                        {g.captured_at ? new Date(g.captured_at).toLocaleDateString() : 'Geotag'}
                      </span>
                    </div>
                    <span
                      className={`text-[9px] font-bold px-2 py-0.5 rounded-full ${
                        g.inside_boundary
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-amber-100 text-amber-800'
                      }`}
                    >
                      {g.inside_boundary ? '✓ In boundary' : 'Outside'}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="border-t border-forest-100 pt-4 text-center py-6 bg-surface-sage/20 rounded-xl border border-dashed border-forest-200">
              <Camera className="w-8 h-8 text-forest-300 mx-auto mb-1.5" />
              <p className="text-xs font-bold text-carbon-800">No Ground Records Submitted Yet</p>
              <p className="text-[11px] text-agriText-muted max-w-sm mx-auto mt-0.5">
                Upload practice photos or record parcel geotags above to satisfy MRV criteria and minimize uncertainty deductions.
              </p>
            </div>
          )}
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
                  <YAxis domain={[0, 1.0]} stroke="#526056" style={{ fontSize: '11px', fontWeight: '600' }} />
                  <Tooltip
                    contentStyle={{ backgroundColor: '#1F2923', borderColor: '#323C34', borderRadius: '12px', color: '#FFF', fontSize: '12px' }}
                  />
                  <Line type="monotone" dataKey="ndvi" stroke="#16A34A" strokeWidth={3} dot={{ r: 4, fill: '#16A34A' }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
        </>
        )}

      </div>
    </div>
  );
}
