import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { ShieldCheck, Download, Lock, ArrowLeft, Loader2, AlertTriangle, FileDown } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import {
  getCertificates,
  getCertificate,
  getCertificatePdfUrl,
  getCertificateLifecycle,
  openCertificateDispute,
  retireCertificate,
} from '../services/api';

export default function CertificateRetirementPage() {
  const { certId } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const [cert, setCert] = useState(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [isRetiring, setIsRetiring] = useState(false);
  const [isDownloadingPdf, setIsDownloadingPdf] = useState(false);
  const [retireError, setRetireError] = useState('');
  const [pdfError, setPdfError] = useState('');
  const [selectedScope, setSelectedScope] = useState('Scope 1 Neutrality');
  const [retireTimestamp, setRetireTimestamp] = useState(null);
  const [lifecycle, setLifecycle] = useState(null);
  const [disputeReason, setDisputeReason] = useState('');
  const [disputeError, setDisputeError] = useState('');
  const [disputeNotice, setDisputeNotice] = useState('');
  const [isDisputing, setIsDisputing] = useState(false);

  useEffect(() => {
    (async () => {
      try {
        let found = null;
        const singleRes = await getCertificate(certId).catch(() => null);
        if (singleRes && singleRes.success && singleRes.certificate) {
          found = singleRes.certificate;
        } else {
          const data = await getCertificates();
          const list = (data && data.success && Array.isArray(data.certificates)) ? data.certificates : [];
          found = list.find((c) => c.id?.toLowerCase() === certId?.toLowerCase());
        }
        if (found) {
          setCert(found);
          if (found.status === 'RETIRED') setRetireTimestamp(found.retired_at || found.retired_timestamp || null);
          const lifecycleRes = await getCertificateLifecycle(certId).catch(() => null);
          if (lifecycleRes?.success) setLifecycle(lifecycleRes);
        } else if (certId && certId.toUpperCase().startsWith('PENDING-RZP-')) {
          // A browser payment callback is not a certificate. The verified
          // webhook issues the real, unique certificate id after settlement.
          setLoadError('Payment is authorized, but the certificate has not been issued yet. CarbonX is waiting for the verified payment webhook — refresh in a moment.');
        } else {
          setLoadError(`Certificate ${certId} was not found in the escrow ledger.`);
        }
      } catch {
        setLoadError('Certificate ledger unreachable. Is the backend running?');
      } finally {
        setLoading(false);
      }
    })();
  }, [certId, user?.name]);

  const handlePermanentRetire = async () => {
    setIsRetiring(true);
    setRetireError('');
    try {
      const res = await retireCertificate(certId, selectedScope);
      if (res && res.success) {
        setCert((prev) => ({ ...prev, status: 'RETIRED' }));
        setRetireTimestamp(res.retired_timestamp || new Date().toISOString());
      } else {
        setRetireError((res && res.message) || 'Retirement failed');
      }
    } catch {
      setRetireError('Retirement service unreachable. Please try again.');
    } finally {
      setIsRetiring(false);
    }
  };

  const status = cert?.status || 'HELD_IN_ESCROW';

  const handleOpenDispute = async () => {
    if (!disputeReason.trim()) {
      setDisputeError('Describe the issue before opening a dispute.');
      return;
    }
    setIsDisputing(true);
    setDisputeError('');
    const res = await openCertificateDispute(certId, {
      reason: disputeReason.trim(),
      detail: `Opened from buyer certificate page for ${certId}`,
    });
    setIsDisputing(false);
    if (res?.success) {
      setDisputeNotice(res.message || 'Dispute opened. The listing is frozen for new sales.');
      setDisputeReason('');
      const lifecycleRes = await getCertificateLifecycle(certId).catch(() => null);
      if (lifecycleRes?.success) setLifecycle(lifecycleRes);
    } else {
      setDisputeError(res?.message || 'The dispute could not be opened.');
    }
  };

  const handleDownloadPdf = async () => {
    if (!certId) {
      setPdfError('No certificate identifier found.');
      return;
    }
    setIsDownloadingPdf(true);
    setPdfError('');
    try {
      const token = localStorage.getItem('carbonx_token');
      const res = await fetch(getCertificatePdfUrl(certId), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      const contentType = res.headers.get('content-type') || '';
      if (res.ok && contentType.includes('application/pdf')) {
        const blob = await res.blob();
        if (!blob || blob.size === 0) {
          throw new Error('Server returned an empty PDF document.');
        }
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `CarbonX_Certificate_${certId}.pdf`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else if (res.status === 404) {
        setPdfError('Certificate record is currently pending escrow confirmation. Please export the compliance text record below or retry in a moment.');
      } else {
        const err = await res.json().catch(() => ({}));
        setPdfError(err.message || err.detail || `PDF could not be generated (HTTP ${res.status}). Please retry or export TXT.`);
      }
    } catch (err) {
      setPdfError(err.message || 'Failed to download PDF. Server may be unreachable.');
    } finally {
      setIsDownloadingPdf(false);
    }
  };

  const downloadCertificate = () => {
    const formattedRetireDate = retireTimestamp ? new Date(retireTimestamp).toLocaleDateString() : '—';
    const lines = [
      '==========================================',
      '  OFFICIAL CARBON OFFSET CERTIFICATE',
      '  CarbonX — Enterprise AgTech Registry Standard',
      '==========================================',
      `Certificate ID: ${certId}`,
      `Issued to: ${cert?.issued_to || user?.name || '—'}`,
      `Volume: ${cert?.volume_mt ?? '—'} Metric Tonnes CO2e`,
      `Source parcels: ${(cert?.source_parcels || []).join(', ') || '—'}`,
      `Issued date: ${cert?.issued_date || '—'}`,
      `Escrow reference: ${cert?.tx_hash || '—'}`,
      `Status: ${status}`,
      ...(status === 'RETIRED' ? [`Retired for ${selectedScope} on ${formattedRetireDate}`] : []),
    ];
    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `CarbonX_Certificate_${certId}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="min-h-screen bg-slate-100 font-inter text-slate-900 py-10 px-4 md:px-10 flex flex-col items-center">
      <div className="max-w-4xl w-full space-y-6">

        {/* Header Navigation */}
        <div className="flex justify-between items-center">
          <button
            onClick={() => navigate('/corporate/dashboard')}
            className="px-4 py-2 bg-white border border-slate-200 rounded-xl text-xs font-bold text-slate-800 hover:bg-slate-50 flex items-center gap-1.5 shadow-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Corporate Dashboard</span>
          </button>

          <span className={`px-3 py-1 rounded-full text-xs font-bold font-mono border ${
            status === 'RETIRED' ? 'bg-slate-900 text-white border-slate-900' : 'bg-emerald-50 text-emerald-900 border-emerald-300'
          }`}>
            STATUS: {status}
          </span>
        </div>

        {loading ? (
          <div className="bg-white border border-slate-200 rounded-xl p-10 text-center text-sm text-slate-500 flex items-center justify-center gap-2">
            <Loader2 className="w-5 h-5 animate-spin" /> Loading certificate…
          </div>
        ) : loadError ? (
          <div className="bg-white border border-rose-200 rounded-xl p-6 text-center space-y-3">
            <AlertTriangle className="w-8 h-8 text-rose-600 mx-auto" />
            <p className="text-sm font-bold text-rose-800">{loadError}</p>
            <button
              onClick={() => navigate('/corporate/dashboard')}
              className="px-4 py-2 bg-[#0C2A18] text-white rounded-lg text-xs font-bold"
            >
              Back to dashboard
            </button>
          </div>
        ) : (
          <>
            {/* Official Certificate Layout */}
            <div className="bg-[#F8FAFC] border-4 border-double border-slate-300 shadow-2xl rounded-2xl p-8 md:p-12 text-center space-y-6 relative overflow-hidden">
              {/* Top Stamp / Badge */}
              <div className="flex justify-between items-center border-b border-slate-200 pb-6">
                <div className="text-left">
                  <span className="font-manrope font-extrabold text-xl text-slate-900 tracking-tight block">CarbonX</span>
                  <span className="text-[10px] font-mono text-slate-500">Enterprise AgTech Registry Standard</span>
                </div>

                <div className="w-14 h-14 bg-emerald-50 border border-emerald-300 rounded-full flex items-center justify-center text-emerald-800">
                  <ShieldCheck className="w-8 h-8" />
                </div>
              </div>

              <div className="space-y-2 py-4">
                <p className="text-xs font-bold text-emerald-800 uppercase tracking-widest">CarbonX Retirement Certificate</p>
                <h1 className="text-3xl md:text-4xl font-extrabold font-manrope text-slate-900">Agricultural Carbon Credit Certificate</h1>
                <p className="text-xs font-mono text-slate-500">Certificate ID: {certId}</p>
              </div>

              <div className={`rounded-xl border p-3 text-left text-[11px] space-y-1 ${
                cert.validation_status === 'field_validated_limited'
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-950'
                  : 'bg-amber-50 border-amber-200 text-amber-950'
              }`}>
                <p className="font-bold">
                  {cert.validation_label || 'Proxy estimate — not field-validated'}
                </p>
                <p>
                  This certificate records a retired credit volume. Until independent field samples meet the published
                  validation thresholds, the underlying sequestration volume is a proxy estimate, not a measured removal.
                </p>
              </div>

              <div className="max-w-xl mx-auto space-y-3 text-xs text-slate-700 bg-white border border-slate-200 p-6 rounded-xl shadow-inner">
                <p>This certifies that</p>
                <p className="text-base font-extrabold text-slate-900 font-manrope">{cert.issued_to || user?.name || '—'}</p>
                <p>has acquired and holds</p>
                <p className="text-2xl font-black text-emerald-800 font-manrope">{Number(cert.volume_mt || 0).toFixed(2)} Metric Tonnes CO2e</p>
                <p className="text-[11px] text-slate-500 pt-2 border-t border-slate-100">
                  Sourced from registered agricultural parcel{cert.crop ? '' : 's'}: <strong className="text-slate-800">{(cert.source_parcels || []).join(', ') || 'source record unavailable'}{cert.crop ? ` · ${cert.crop}` : ''}</strong>.
                  Farmer identity and exact field location are withheld from public certificates.
                </p>
              </div>

              {/* Batch hash + escrow reference */}
              <div className="bg-slate-100 border border-slate-200 rounded-xl p-3 text-xs font-mono text-slate-700 space-y-1.5 max-w-xl mx-auto">
                <div className="flex justify-between items-center">
                  <span>Escrow Reference:</span>
                  <span className="font-bold text-slate-900 truncate">{cert.tx_hash || '—'}</span>
                </div>
                {cert.batch_hash && (
                  <div className="flex justify-between items-center border-t border-slate-200 pt-1.5">
                    <span>Batch hash (sha256):</span>
                    <span className="font-bold text-emerald-800 truncate" title={cert.batch_hash}>
                      {String(cert.batch_hash).slice(0, 24)}…
                    </span>
                  </div>
                )}
              </div>

              {status === 'RETIRED' && (
                <div className="bg-[#0C2A18] text-white border border-emerald-800 rounded-xl p-4 max-w-xl mx-auto text-xs space-y-1">
                  <p className="font-bold text-emerald-400">PERMANENTLY RETIRED & LOCKED</p>
                  <p>Retired for {selectedScope}{retireTimestamp ? ` on ${new Date(retireTimestamp).toLocaleDateString()}` : ''}</p>
                </div>
              )}
            </div>

            {lifecycle?.lifecycle && (
              <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-4">
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-base font-bold text-slate-900">Credit lifecycle &amp; dispute record</h2>
                  <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 border border-slate-200 text-slate-700">
                    {lifecycle.lifecycle.lifecycle_state || '—'}
                  </span>
                  <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${
                    lifecycle.lifecycle.dispute_status === 'OPEN'
                      ? 'bg-rose-50 border-rose-200 text-rose-800'
                      : 'bg-emerald-50 border-emerald-200 text-emerald-800'
                  }`}>
                    Dispute: {lifecycle.lifecycle.dispute_status || 'NONE'}
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                  {[
                    ['Issued', lifecycle.lifecycle.credits_issued],
                    ['Sold (net)', lifecycle.lifecycle.credits_sold],
                    ['Refunded', lifecycle.lifecycle.credits_refunded],
                    ['Remaining', lifecycle.lifecycle.credits_remaining],
                  ].map(([label, value]) => (
                    <div key={label} className="rounded-xl bg-slate-50 border border-slate-200 p-3">
                      <p className="text-[10px] uppercase tracking-wide text-slate-500 font-bold">{label}</p>
                      <p className="text-lg font-extrabold text-slate-900">{Number(value ?? 0).toFixed(2)}</p>
                    </div>
                  ))}
                </div>
                {lifecycle.payout && (
                  <p className="text-[11px] text-slate-600">
                    Payout status: <strong>{lifecycle.payout.payout_status || '—'}</strong>
                    {lifecycle.payout.refunded ? ' · refunded from the original SALE/SPLIT record' : ' · farmer floor check passed'}
                  </p>
                )}
                {(lifecycle.audit_events || []).length > 0 && (
                  <div className="rounded-xl border border-slate-200 overflow-hidden">
                    <table className="w-full text-left text-[11px]">
                      <thead className="bg-slate-50 text-[9px] uppercase tracking-wide text-slate-500">
                        <tr><th className="p-2">Event</th><th className="p-2">At</th><th className="p-2">Proof</th></tr>
                      </thead>
                      <tbody className="divide-y divide-slate-100">
                        {(lifecycle.audit_events || []).map((event, index) => (
                          <tr key={`${event.type}-${index}`}>
                            <td className="p-2 font-semibold text-slate-800">{event.type}{event.decision ? ` · ${event.decision}` : ''}</td>
                            <td className="p-2 text-slate-500">{String(event.at || '').slice(0, 19).replace('T', ' ')}</td>
                            <td className="p-2 font-mono text-[9px] text-slate-400">{String(event.hash || '').slice(0, 12)}…</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}

                {lifecycle.lifecycle.dispute_status !== 'OPEN'
                  && status !== 'REFUNDED'
                  && status !== 'FAILED_RECONCILIATION' && (
                  <div className="rounded-xl border border-rose-200 bg-rose-50/50 p-4 space-y-3">
                    <div>
                      <p className="text-xs font-bold text-rose-900">Open a dispute on this sale</p>
                      <p className="text-[11px] text-rose-800 mt-0.5">
                        An open dispute freezes new sales on the listing. It must end in release, rejection or a full refund;
                        credits and money are never edited in place.
                      </p>
                    </div>
                    <textarea
                      value={disputeReason}
                      onChange={(e) => setDisputeReason(e.target.value)}
                      maxLength={1000}
                      rows={2}
                      placeholder="Describe the issue (e.g. wrong volume, parcel mismatch, duplicate certificate)"
                      className="w-full rounded-xl border border-rose-200 bg-white px-3 py-2 text-xs"
                    />
                    {disputeError && <p className="text-[11px] font-semibold text-rose-800">{disputeError}</p>}
                    {disputeNotice && <p className="text-[11px] font-semibold text-emerald-800">{disputeNotice}</p>}
                    <button
                      onClick={handleOpenDispute}
                      disabled={isDisputing}
                      className="px-4 py-2 rounded-xl bg-rose-700 text-white text-xs font-bold hover:bg-rose-800 disabled:opacity-60"
                    >
                      {isDisputing ? 'Opening…' : 'Open dispute'}
                    </button>
                  </div>
                )}
              </div>
            )}

            {/* Permanent Retirement Terminal */}
            <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-4">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <Lock className="w-5 h-5 text-slate-800" />
                <span>Permanent Retirement Terminal</span>
              </h2>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div>
                  <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-1">
                    Scope Neutrality Selection
                  </label>
                  <select
                    value={selectedScope}
                    onChange={e => setSelectedScope(e.target.value)}
                    disabled={status === 'RETIRED'}
                    className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none"
                  >
                    <option value="Scope 1 Neutrality">Scope 1 Neutrality (Direct Emissions)</option>
                    <option value="Scope 2 Neutrality">Scope 2 Neutrality (Purchased Energy)</option>
                    <option value="Scope 3 Neutrality">Scope 3 Neutrality (Supply Chain)</option>
                  </select>
                </div>

                <div className="flex items-end">
                  {status === 'HELD_IN_ESCROW' ? (
                    <button
                      onClick={handlePermanentRetire}
                      disabled={isRetiring}
                      className="w-full py-2.5 bg-rose-800 hover:bg-rose-700 disabled:opacity-60 text-white rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2"
                    >
                      <Lock className="w-4 h-4" />
                      <span>{isRetiring ? 'Retiring…' : 'Permanently Retire Credits'}</span>
                    </button>
                  ) : (
                    <div className="w-full py-2.5 bg-slate-100 text-slate-500 rounded-lg text-xs font-bold text-center">
                      Certificate Locked & Retired
                    </div>
                  )}
                </div>
              </div>

              {retireError && (
                <p className="text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 shrink-0" /> {retireError}
                </p>
              )}

              {pdfError && (
                <div className="bg-rose-50 border border-rose-200 p-3 rounded-xl flex items-start gap-2.5 text-xs text-rose-800 text-left">
                  <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                  <div className="flex-1">
                    <p className="font-bold">PDF Generation Notice</p>
                    <p className="text-[11px] text-rose-700 mt-0.5 leading-relaxed">{pdfError}</p>
                    <p className="text-[10px] text-slate-500 mt-1">You can always use the "Export Compliance Record (TXT)" option below as an instant verifiable text record.</p>
                  </div>
                </div>
              )}

              {/* Export Controls */}
              <div className="flex flex-col sm:flex-row gap-3 pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={handleDownloadPdf}
                  disabled={isDownloadingPdf}
                  className="flex-1 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2"
                >
                  {isDownloadingPdf ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
                  <span>{isDownloadingPdf ? 'Generating PDF…' : 'Download PDF Certificate'}</span>
                </button>

                <button
                  type="button"
                  onClick={downloadCertificate}
                  className="flex-1 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-800 rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2"
                >
                  <Download className="w-4 h-4 text-emerald-700" />
                  <span>Export Compliance Record (TXT)</span>
                </button>
              </div>
            </div>
          </>
        )}

      </div>
    </div>
  );
}
