import React, { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import {
  ShieldCheck, Search, Leaf, Car, TreePine, Globe, Loader2,
  AlertTriangle, Copy, CheckCircle2, ExternalLink,
} from "lucide-react";
import { getPublicVerification } from "../services/api";

/** Public certificate verification — trust as marketing. No auth needed. */
export default function VerifyPage() {
  const { certId } = useParams();
  const navigate = useNavigate();
  const [searchId, setSearchId] = useState(certId || "");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(!!certId);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const load = async (id) => {
    if (!id) return;
    setLoading(true);
    setError("");
    try {
      const data = await getPublicVerification(id);
      if (data && data.success) {
        setResult(data);
      } else {
        setResult(null);
        setError((data && data.message) || "Certificate not found");
      }
    } catch {
      setError("Verification service unreachable. Is the backend running?");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { if (certId) load(certId); // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [certId]);

  const submit = (e) => {
    e.preventDefault();
    const id = searchId.trim();
    if (id) navigate(`/verify/${encodeURIComponent(id)}`);
  };

  const copyLink = () => {
    navigator.clipboard.writeText(window.location.href).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div className="min-h-screen bg-[#F6F5EE] font-inter text-slate-900">
      {/* Header */}
      <div className="bg-[#0C2A18] text-white py-10 px-4 md:px-10">
        <div className="max-w-5xl mx-auto">
          <button onClick={() => navigate("/")} className="text-xs font-semibold text-emerald-200 hover:text-white transition flex items-center gap-1.5 mb-4">
            ← CarbonX
          </button>
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-9 h-9 text-emerald-300" />
            <div>
              <h1 className="font-display text-3xl font-extrabold">Public Credit Verification</h1>
              <p className="text-sm text-emerald-100/80 mt-0.5">Anyone can verify any retirement against the tamper-evident ledger — no account needed.</p>
            </div>
          </div>

          <form onSubmit={submit} className="mt-6 flex flex-col sm:flex-row gap-3 max-w-2xl">
            <input
              type="text"
              value={searchId}
              onChange={(e) => setSearchId(e.target.value)}
              placeholder="Enter certificate ID — e.g. CX-2026-CERT-7D39E1F7"
              className="flex-1 px-4 py-3 rounded-xl bg-white/10 border border-white/20 text-white placeholder-emerald-200/50 text-sm font-mono focus:outline-none focus:border-emerald-300"
            />
            <button type="submit" className="px-6 py-3 bg-emerald-500 hover:bg-emerald-400 text-emerald-950 font-bold text-sm rounded-xl transition flex items-center justify-center gap-2">
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
              Verify
            </button>
          </form>
        </div>
      </div>

      <div className="max-w-5xl mx-auto px-4 md:px-10 py-10 space-y-6">
        {error && (
          <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center">
            <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto mb-3" />
            <p className="font-bold text-slate-800">{error}</p>
            <p className="text-xs text-slate-500 mt-2">Certificate IDs look like <span className="font-mono">CX-2026-CERT-XXXXXXXX</span> — printed on every PDF certificate.</p>
          </div>
        )}

        {loading && !result && (
          <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center">
            <Loader2 className="w-8 h-8 text-emerald-600 animate-spin mx-auto" />
            <p className="text-sm text-slate-500 mt-3 font-semibold">Recomputing the ledger chain…</p>
          </div>
        )}

        {result && (
          <>
            {/* Status banner */}
            <div className={`rounded-2xl p-6 border ${result.status === "RETIRED" ? "bg-emerald-50 border-emerald-300" : "bg-amber-50 border-amber-300"}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  {result.status === "RETIRED"
                    ? <CheckCircle2 className="w-10 h-10 text-emerald-600" />
                    : <Loader2 className="w-10 h-10 text-amber-500" />}
                  <div>
                    <p className="font-display font-extrabold text-lg text-slate-900">
                      {result.status === "RETIRED" ? "Verified — permanently retired" : "Held in escrow"}
                    </p>
                    <p className="text-xs text-slate-600 font-mono">{result.certificate_id}</p>
                  </div>
                </div>
                <button onClick={copyLink} className="px-4 py-2 bg-white border border-slate-300 rounded-xl text-xs font-bold text-slate-700 hover:bg-slate-50 flex items-center gap-1.5">
                  {copied ? <CheckCircle2 className="w-4 h-4 text-emerald-600" /> : <Copy className="w-4 h-4" />}
                  {copied ? "Link copied" : "Share verification"}
                </button>
              </div>
            </div>

            {/* Impact equivalents */}
            {result.impact_equivalents && Object.keys(result.impact_equivalents).length > 0 && (
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <div className="bg-white border border-slate-200 rounded-2xl p-5 text-center">
                  <Car className="w-6 h-6 text-emerald-600 mx-auto" />
                  <p className="font-display text-2xl font-extrabold text-slate-900 mt-2">
                    {result.impact_equivalents.cars_off_road_one_year}
                  </p>
                  <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide">cars off the road for a year</p>
                </div>
                <div className="bg-white border border-slate-200 rounded-2xl p-5 text-center">
                  <TreePine className="w-6 h-6 text-emerald-600 mx-auto" />
                  <p className="font-display text-2xl font-extrabold text-slate-900 mt-2">
                    {result.impact_equivalents.tree_seedlings_10_years}
                  </p>
                  <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide">tree-seedlings grown 10 years</p>
                </div>
                <div className="bg-white border border-slate-200 rounded-2xl p-5 text-center">
                  <Globe className="w-6 h-6 text-emerald-600 mx-auto" />
                  <p className="font-display text-2xl font-extrabold text-slate-900 mt-2">
                    {Number(result.impact_equivalents.miles_driven).toLocaleString("en-IN")}
                  </p>
                  <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wide">miles driven avoided</p>
                </div>
              </div>
            )}

            <div className="grid md:grid-cols-2 gap-6">
              {/* Batch details */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 space-y-3">
                <h2 className="font-display font-extrabold flex items-center gap-2"><Leaf className="w-5 h-5 text-emerald-600" /> Batch details</h2>
                <div className="text-xs space-y-2 text-slate-600">
                  <div className="flex justify-between"><span>Volume retired</span><span className="font-bold text-slate-900">{result.credits_tco2e} tCO₂e</span></div>
                  <div className="flex justify-between"><span>Crop / practice</span><span className="font-bold text-slate-900">{result.crop || "Mixed"}</span></div>
                  <div className="flex justify-between"><span>Region</span><span className="font-bold text-slate-900">{result.region}</span></div>
                  <div className="flex justify-between"><span>Verified on</span><span className="font-bold text-slate-900">{result.verified_at}</span></div>
                  <div className="flex justify-between"><span>Escrow reference</span><span className="font-mono font-bold text-slate-900">{result.escrow_ref || "—"}</span></div>
                </div>
                <div className="bg-slate-50 border border-slate-100 rounded-xl p-3.5 text-[11px] text-slate-600">
                  <p className="font-bold text-slate-700">{result.farmer?.display_name}</p>
                  <p className="mt-0.5">{result.farmer?.note}</p>
                </div>
              </div>

              {/* Methodology + ledger */}
              <div className="bg-white border border-slate-200 rounded-2xl p-6 space-y-4">
                <h2 className="font-display font-extrabold">Methodology</h2>
                <div className="text-xs space-y-2 text-slate-600">
                  <div className="flex justify-between"><span>Standard</span><span className="font-bold text-slate-900 text-right">{result.methodology?.standard}</span></div>
                  <div className="flex justify-between"><span>Formula version</span><span className="font-mono font-bold text-slate-900">{result.methodology?.formula_version}</span></div>
                  <div className="flex justify-between"><span>MRV cycle</span><span className="font-bold text-slate-900 text-right">{result.methodology?.mrv_cycle}</span></div>
                  <div className="flex justify-between"><span>Uncertainty</span><span className="font-bold text-slate-900 text-right">{result.methodology?.uncertainty}</span></div>
                </div>
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-slate-400 mb-2">Ledger chain — {result.ledger?.events?.length || 0} events</p>
                  <div className="font-mono text-[10px] space-y-1.5 max-h-48 overflow-y-auto">
                    {(result.ledger?.events || []).map((e) => (
                      <div key={e.seq} className="flex items-center gap-2 justify-between bg-slate-50 rounded-lg px-3 py-1.5">
                        <span className="font-bold text-emerald-700">{e.type}</span>
                        <span className="text-slate-400 truncate" title={e.hash}>sha {String(e.hash).slice(0, 14)}…</span>
                        <span className="text-emerald-600">✓</span>
                      </div>
                    ))}
                  </div>
                  <p className={`text-[11px] font-bold mt-2 ${result.ledger?.verified ? "text-emerald-600" : "text-rose-600"}`}>
                    {result.ledger?.verified ? "✓ Chain verified — recompute it yourself: " : "✗ Chain INVALID"}
                    {result.ledger?.verified && (
                      <span className="font-mono text-slate-500">{result.ledger?.public_recompute}</span>
                    )}
                  </p>
                </div>
                <a
                  href={`/py-api/verify/${result.certificate_id}`}
                  target="_blank" rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-[11px] font-bold text-emerald-700 hover:text-emerald-800"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> View raw JSON (public API)
                </a>
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
