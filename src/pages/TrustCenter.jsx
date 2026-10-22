import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle, CheckCircle2, Download, FileCheck2, Fingerprint,
  Loader2, LockKeyhole, RefreshCw, ShieldCheck, Trash2, XCircle,
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import {
  deleteMyAccount,
  getDeletionCheck,
  getPrivacyConsent,
  getPrivacyExport,
  getPrivacyPolicy,
  getPrivacyRequests,
  getValidationClaims,
  getValidationStatus,
  setPrivacyConsent,
  submitPrivacyCorrection,
} from '../services/api';

const STATUS_STYLES = {
  proxy_unvalidated: 'bg-amber-50 text-amber-900 border-amber-200',
  proxy_insufficient_data: 'bg-sky-50 text-sky-900 border-sky-200',
  field_validated_limited: 'bg-emerald-50 text-emerald-900 border-emerald-200',
  field_validation_failed: 'bg-rose-50 text-rose-900 border-rose-200',
};

const CORRECTION_FIELDS = ['name', 'village', 'district', 'state', 'upi', 'preferred_language'];

function Section({ icon: Icon, title, children, description }) {
  return (
    <section className="bg-white border border-forest-100 rounded-2xl p-5 sm:p-6 space-y-4 shadow-sm">
      <div className="flex items-start gap-3">
        <div className="w-9 h-9 rounded-xl bg-forest-50 border border-forest-100 grid place-items-center shrink-0">
          <Icon className="w-4.5 h-4.5 text-forest-700" size={18} />
        </div>
        <div>
          <h2 className="text-sm font-bold text-carbon-900">{title}</h2>
          {description && <p className="text-xs text-agriText-muted mt-0.5">{description}</p>}
        </div>
      </div>
      {children}
    </section>
  );
}

export default function TrustCenter() {
  const navigate = useNavigate();
  const { isAuthenticated, user, logout } = useAuth();
  const [policy, setPolicy] = useState(null);
  const [validation, setValidation] = useState(null);
  const [claims, setClaims] = useState(null);
  const [consent, setConsent] = useState(null);
  const [requests, setRequests] = useState([]);
  const [deletion, setDeletion] = useState(null);
  const [selectedConsent, setSelectedConsent] = useState({});
  const [correction, setCorrection] = useState({ field: 'village', current_value: '', requested_value: '', reason: '' });
  const [deleteReason, setDeleteReason] = useState('');
  const [deleteConfirm, setDeleteConfirm] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    const [p, v, c] = await Promise.all([
      getPrivacyPolicy(),
      getValidationStatus(),
      getValidationClaims(),
    ]);
    if (p.success) setPolicy(p);
    if (v.success) setValidation(v);
    if (c.success) setClaims(c);
    if (isAuthenticated) {
      const [consentRes, reqRes, deletionRes] = await Promise.all([
        getPrivacyConsent(),
        getPrivacyRequests(),
        getDeletionCheck(),
      ]);
      if (consentRes.success) {
        setConsent(consentRes);
        const next = {};
        Object.entries(consentRes.current || {}).forEach(([purpose, row]) => {
          next[purpose] = Boolean(row?.granted);
        });
        setSelectedConsent(next);
      }
      if (reqRes.success) setRequests(reqRes.requests || []);
      if (deletionRes.success) setDeletion(deletionRes);
    }
    setLoading(false);
  }, [isAuthenticated]);

  useEffect(() => { refresh(); }, [refresh]);

  const purposes = policy?.purposes || {};
  const status = validation?.status || 'proxy_unvalidated';
  const counts = validation?.counts || {};
  const metrics = validation?.metrics || {};
  const thresholds = validation?.thresholds || {};

  const statusLabel = useMemo(() => {
    if (status === 'field_validated_limited') return 'Field validated (limited scope)';
    if (status === 'field_validation_failed') return 'Field validation failed';
    if (status === 'proxy_insufficient_data') return 'Proxy estimate — collecting field data';
    return 'Proxy estimate — not field-validated';
  }, [status]);

  const saveConsent = async () => {
    setBusy('consent');
    setNotice(null);
    const res = await setPrivacyConsent(selectedConsent);
    if (res.success) {
      setNotice({ type: 'ok', message: 'Consent choices recorded with a timestamp and policy version.' });
      setConsent((prev) => ({ ...(prev || {}), current: res.current }));
    } else {
      setNotice({ type: 'error', message: res.message || 'Could not record consent.' });
    }
    setBusy('');
  };

  const downloadArchive = async () => {
    setBusy('export');
    const res = await getPrivacyExport();
    setBusy('');
    if (!res.success) {
      setNotice({ type: 'error', message: res.message || 'Export failed.' });
      return;
    }
    const blob = new Blob([JSON.stringify(res.archive, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `carbonx-data-export-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
    setNotice({ type: 'ok', message: 'Your data archive was generated and downloaded.' });
  };

  const requestCorrection = async (event) => {
    event.preventDefault();
    setBusy('correction');
    const res = await submitPrivacyCorrection(correction);
    setBusy('');
    if (res.success) {
      setNotice({ type: 'ok', message: 'Correction request submitted for staff review. It is not applied automatically.' });
      setCorrection({ field: 'village', current_value: '', requested_value: '', reason: '' });
      const req = await getPrivacyRequests();
      if (req.success) setRequests(req.requests || []);
    } else {
      setNotice({ type: 'error', message: res.message || 'Correction request failed.' });
    }
  };

  const requestDeletion = async () => {
    setBusy('delete');
    const res = await deleteMyAccount(deleteReason);
    setBusy('');
    if (res.success) {
      setNotice({ type: 'ok', message: res.message || 'Account erasure recorded.' });
      setTimeout(() => { logout(); }, 1200);
    } else {
      setNotice({
        type: 'error',
        message: res.blockers?.length
          ? `Cannot delete yet: ${res.blockers.map((b) => b.type || b).join(', ')}`
          : (res.message || 'Deletion failed.'),
      });
    }
  };

  return (
    <div className="max-w-5xl mx-auto px-4 py-6 space-y-5">
      <header className="bg-gradient-to-br from-forest-900 to-carbon-900 text-white rounded-3xl p-6 sm:p-8 space-y-3">
        <div className="flex items-center gap-2 text-emerald-200 text-xs font-bold uppercase tracking-wider">
          <ShieldCheck size={16} /> Trust, evidence & data rights
        </div>
        <h1 className="text-2xl sm:text-3xl font-extrabold font-manrope">What CarbonX can prove — and what it cannot yet</h1>
        <p className="text-sm text-emerald-50/90 max-w-3xl">
          Carbon figures are currently proxy estimates from satellite and soil factors. They stay labelled as proxies
          until independent field samples meet the published validation thresholds. External methodology review,
          privacy-counsel review and the first live pilot are still pending — this page does not claim otherwise.
        </p>
        <button
          onClick={() => navigate('/')}
          className="text-[11px] font-bold text-emerald-200 underline underline-offset-2 hover:text-white"
        >
          Back to home
        </button>
      </header>

      {notice && (
        <div className={`rounded-xl border px-4 py-3 text-xs font-semibold flex items-start gap-2 ${
          notice.type === 'ok'
            ? 'bg-emerald-50 border-emerald-200 text-emerald-900'
            : 'bg-rose-50 border-rose-200 text-rose-900'
        }`}>
          {notice.type === 'ok' ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
          <span>{notice.message}</span>
        </div>
      )}

      {loading ? (
        <div className="bg-white border border-forest-100 rounded-2xl p-10 text-center text-xs text-agriText-muted">
          <Loader2 className="w-5 h-5 animate-spin mx-auto mb-2" /> Loading evidence state…
        </div>
      ) : (
        <>
          <Section
            icon={Fingerprint}
            title="Estimate validation status"
            description="The threshold is set before data collection, not after. A failed validation is published as failed."
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className={`text-[11px] font-bold px-3 py-1.5 rounded-full border uppercase tracking-wide ${STATUS_STYLES[status] || STATUS_STYLES.proxy_unvalidated}`}>
                {statusLabel}
              </span>
              <button onClick={refresh} className="ml-auto text-[11px] font-bold text-forest-800 hover:text-forest-900 inline-flex items-center gap-1">
                <RefreshCw size={12} /> Refresh
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="rounded-xl bg-surface-sage/60 border border-forest-100 p-3">
                <span className="text-[10px] uppercase tracking-wide text-agriText-muted font-bold">Verified rate samples</span>
                <p className="text-xl font-extrabold text-carbon-900">{counts.verified_rate_samples ?? 0}</p>
                <p className="text-[10px] text-agriText-muted">minimum {thresholds.min_verified_samples ?? 30}</p>
              </div>
              <div className="rounded-xl bg-surface-sage/60 border border-forest-100 p-3">
                <span className="text-[10px] uppercase tracking-wide text-agriText-muted font-bold">MAPE</span>
                <p className="text-xl font-extrabold text-carbon-900">{metrics.mape_pct == null ? '—' : `${metrics.mape_pct}%`}</p>
                <p className="text-[10px] text-agriText-muted">limit {thresholds.max_mape_pct ?? 30}%</p>
              </div>
              <div className="rounded-xl bg-surface-sage/60 border border-forest-100 p-3">
                <span className="text-[10px] uppercase tracking-wide text-agriText-muted font-bold">Absolute bias</span>
                <p className="text-xl font-extrabold text-carbon-900">{metrics.bias_pct == null ? '—' : `${metrics.bias_pct}%`}</p>
                <p className="text-[10px] text-agriText-muted">limit {thresholds.max_abs_bias_pct ?? 20}%</p>
              </div>
              <div className="rounded-xl bg-surface-sage/60 border border-forest-100 p-3">
                <span className="text-[10px] uppercase tracking-wide text-agriText-muted font-bold">CI90 coverage</span>
                <p className="text-xl font-extrabold text-carbon-900">{metrics.ci90_coverage_pct == null ? '—' : `${metrics.ci90_coverage_pct}%`}</p>
                <p className="text-[10px] text-agriText-muted">minimum {thresholds.min_ci90_coverage_pct ?? 50}%</p>
              </div>
            </div>

            <div className="grid md:grid-cols-2 gap-3">
              <div className="rounded-xl border border-emerald-200 bg-emerald-50/60 p-4">
                <h3 className="text-[11px] font-bold uppercase tracking-wide text-emerald-900 flex items-center gap-1.5">
                  <CheckCircle2 size={14} /> Claims we stand behind
                </h3>
                <ul className="mt-2 space-y-1.5 text-xs text-emerald-950/90">
                  {(claims?.supported_claims || validation?.supported_claims || []).map((claim) => (
                    <li key={claim}>• {claim}</li>
                  ))}
                </ul>
              </div>
              <div className="rounded-xl border border-amber-200 bg-amber-50/70 p-4">
                <h3 className="text-[11px] font-bold uppercase tracking-wide text-amber-950 flex items-center gap-1.5">
                  <XCircle size={14} /> Claims we do not make
                </h3>
                <ul className="mt-2 space-y-1.5 text-xs text-amber-950/90">
                  {(claims?.unsupported_claims || validation?.unsupported_claims || []).map((claim) => (
                    <li key={claim}>• {claim}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-xs text-slate-700 space-y-1">
              <p className="font-bold text-slate-900">Still pending — not completed</p>
              <p>Qualified independent MRV/agronomy review · first live pilot with consent and field sampling · qualified privacy-counsel review of Aadhaar/document handling.</p>
              <p className="text-[11px] text-slate-500">See docs/VALIDATION_PROTOCOL.md, docs/PILOT_PROTOCOL.md and docs/PRIVACY_DPIA.md for the review checklists and status.</p>
            </div>
          </Section>

          <Section
            icon={LockKeyhole}
            title="Public access rules"
            description="Open transparency does not mean publishing farmers' identities, rupees, exact fields or private evidence."
          >
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wide text-agriText-muted border-b border-forest-100">
                    <th className="py-2 pr-3">Record</th>
                    <th className="py-2 pr-3">Public</th>
                    <th className="py-2">Owner / buyer / staff</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-forest-50 text-carbon-700">
                  {[
                    ['Carbon passport', 'Passport id, crop, district, proxy credits, validation status, redacted ledger', 'Farm name, owner identity, village, projected income, full ledger'],
                    ['Certificate', 'Retired certificates only; no names, phone, rupee value or split', 'Held/refunded/disputed records for the farmer, buyer of record or staff'],
                    ['Ledger', 'Event type, sequence, time, hash and credit quantity', 'Buyer identity, gross rupees, split amounts and reasons'],
                    ['Evidence', 'Counts, verification booleans and public-consent photos without EXIF GPS', 'Exact coordinates, creator phone, private photos and metadata'],
                    ['Marketplace listing', 'Crop, district, credits, price and validation label; no phone/name/village', 'Farmer sees own contact and village-level location'],
                  ].map(([record, pub, priv]) => (
                    <tr key={record}>
                      <td className="py-2.5 pr-3 font-bold text-carbon-900 whitespace-nowrap">{record}</td>
                      <td className="py-2.5 pr-3">{pub}</td>
                      <td className="py-2.5">{priv}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          {isAuthenticated ? (
            <>
              <Section
                icon={FileCheck2}
                title="Consent"
                description="Optional purposes can be withdrawn. Required service consent is closed only by deleting the account."
              >
                <div className="space-y-2">
                  {Object.entries(purposes).map(([purpose, meta]) => {
                    const checked = Boolean(selectedConsent[purpose]);
                    return (
                      <label key={purpose} className="flex items-start gap-3 rounded-xl border border-forest-100 p-3 hover:bg-forest-50/40 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={checked}
                          disabled={Boolean(meta.required) || busy === 'consent'}
                          onChange={(e) => setSelectedConsent((prev) => ({ ...prev, [purpose]: e.target.checked }))}
                          className="mt-0.5 h-4 w-4 accent-emerald-600"
                        />
                        <span className="min-w-0">
                          <span className="block text-xs font-bold text-carbon-900">
                            {meta.label} {meta.required && <span className="text-[10px] font-semibold text-amber-700">(required)</span>}
                          </span>
                          <span className="block text-[11px] text-agriText-muted">{meta.description}</span>
                          {consent?.current?.[purpose]?.captured_at && (
                            <span className="block text-[10px] text-agriText-muted mt-1">
                              Last updated {String(consent.current[purpose].captured_at).slice(0, 10)}
                            </span>
                          )}
                        </span>
                      </label>
                    );
                  })}
                </div>
                <button
                  onClick={saveConsent}
                  disabled={busy === 'consent'}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-forest-800 text-white text-xs font-bold hover:bg-forest-900 disabled:opacity-60"
                >
                  {busy === 'consent' && <Loader2 size={14} className="animate-spin" />} Save consent choices
                </button>
              </Section>

              <Section icon={Download} title="Access & portability" description="Download a JSON archive of your profile, farms, listings, evidence metadata, consent history and ledger records.">
                <button
                  onClick={downloadArchive}
                  disabled={busy === 'export'}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl border border-forest-200 bg-white text-forest-900 text-xs font-bold hover:bg-forest-50 disabled:opacity-60"
                >
                  {busy === 'export' ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Download my data
                </button>
              </Section>

              <Section icon={RefreshCw} title="Correction request" description="Corrections are reviewed before they change a record. Financial corrections use refund + reissue, never a silent edit.">
                <form onSubmit={requestCorrection} className="grid sm:grid-cols-2 gap-3">
                  <label className="text-[11px] font-bold text-carbon-800">
                    Field
                    <select
                      value={correction.field}
                      onChange={(e) => setCorrection({ ...correction, field: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-forest-200 px-3 py-2 text-xs font-normal"
                    >
                      {CORRECTION_FIELDS.map((field) => <option key={field} value={field}>{field}</option>)}
                    </select>
                  </label>
                  <label className="text-[11px] font-bold text-carbon-800">
                    Current value
                    <input
                      value={correction.current_value}
                      onChange={(e) => setCorrection({ ...correction, current_value: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-forest-200 px-3 py-2 text-xs font-normal"
                      placeholder="What the record says now"
                    />
                  </label>
                  <label className="text-[11px] font-bold text-carbon-800">
                    Correct value
                    <input
                      required
                      value={correction.requested_value}
                      onChange={(e) => setCorrection({ ...correction, requested_value: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-forest-200 px-3 py-2 text-xs font-normal"
                      placeholder="What it should say"
                    />
                  </label>
                  <label className="text-[11px] font-bold text-carbon-800">
                    Reason
                    <input
                      value={correction.reason}
                      onChange={(e) => setCorrection({ ...correction, reason: e.target.value })}
                      className="mt-1 w-full rounded-xl border border-forest-200 px-3 py-2 text-xs font-normal"
                      placeholder="e.g. revenue record updated"
                    />
                  </label>
                  <button
                    type="submit"
                    disabled={busy === 'correction'}
                    className="sm:col-span-2 justify-self-start inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-forest-800 text-white text-xs font-bold hover:bg-forest-900 disabled:opacity-60"
                  >
                    {busy === 'correction' && <Loader2 size={14} className="animate-spin" />} Submit for review
                  </button>
                </form>
                {requests.length > 0 && (
                  <div className="rounded-xl border border-forest-100 overflow-hidden">
                    <table className="w-full text-left text-[11px]">
                      <thead className="bg-surface-sage/60 text-agriText-muted uppercase text-[9px] tracking-wide">
                        <tr><th className="p-2">Type</th><th className="p-2">Status</th><th className="p-2">Created</th></tr>
                      </thead>
                      <tbody className="divide-y divide-forest-50">
                        {requests.slice(0, 8).map((request) => (
                          <tr key={request.id}>
                            <td className="p-2 font-semibold text-carbon-800">{request.request_type}</td>
                            <td className="p-2">{request.status}</td>
                            <td className="p-2 text-agriText-muted">{String(request.created_at || '').slice(0, 10)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Section>

              <Section
                icon={Trash2}
                title="Account deletion"
                description="The profile is scrubbed to an inactive tombstone. Phone is retained only as an account-lock/FK anchor; name, UPI, Aadhaar suffix, wallet, village and farm boundaries are erased."
              >
                {deletion && !deletion.can_delete && (
                  <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-950">
                    <p className="font-bold mb-1">Deletion is blocked while balances or disputes are open.</p>
                    <ul className="space-y-1">
                      {(deletion.blockers || []).map((blocker, index) => (
                        <li key={index}>• {blocker.type || 'blocker'}{blocker.listing_id ? ` (${blocker.listing_id})` : ''}</li>
                      ))}
                    </ul>
                  </div>
                )}
                <div className="grid sm:grid-cols-2 gap-3">
                  <label className="text-[11px] font-bold text-carbon-800">
                    Reason (optional)
                    <input
                      value={deleteReason}
                      onChange={(e) => setDeleteReason(e.target.value)}
                      className="mt-1 w-full rounded-xl border border-forest-200 px-3 py-2 text-xs font-normal"
                    />
                  </label>
                  <label className="text-[11px] font-bold text-carbon-800">
                    Type DELETE to confirm
                    <input
                      value={deleteConfirm}
                      onChange={(e) => setDeleteConfirm(e.target.value)}
                      className="mt-1 w-full rounded-xl border border-rose-200 px-3 py-2 text-xs font-normal"
                      placeholder="DELETE"
                    />
                  </label>
                </div>
                <button
                  onClick={requestDeletion}
                  disabled={deleteConfirm.trim().toUpperCase() !== 'DELETE' || busy === 'delete' || (deletion && deletion.can_delete === false)}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-rose-700 text-white text-xs font-bold hover:bg-rose-800 disabled:opacity-50"
                >
                  {busy === 'delete' ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />} Permanently delete account
                </button>
              </Section>
            </>
          ) : (
            <div className="rounded-2xl border border-forest-100 bg-white p-5 text-xs text-agriText-muted">
              Sign in as a farmer to manage consent, download your data, request a correction or delete your account.
              <span className="block mt-1 text-carbon-700 font-semibold">Signed in as {user?.name || 'a guest'}.</span>
            </div>
          )}

          <Section icon={ShieldCheck} title="Contact & grievance" description={policy?.legal_note}>
            <div className="grid sm:grid-cols-2 gap-3 text-xs text-carbon-700">
              <p><span className="font-bold text-carbon-900">Policy version:</span> {policy?.policy_version || '—'}</p>
              <p><span className="font-bold text-carbon-900">Controller:</span> {policy?.controller || 'CarbonX'}</p>
              <p><span className="font-bold text-carbon-900">Privacy contact:</span> {policy?.contact || 'privacy@carbonx.example'}</p>
              <p><span className="font-bold text-carbon-900">Aadhaar:</span> {policy?.aadhaar?.stored || 'Last 4 digits only'}</p>
            </div>
            <div className="grid sm:grid-cols-2 gap-3">
              {Object.entries(policy?.retention || {}).map(([key, value]) => (
                <div key={key} className="rounded-xl border border-forest-100 p-3 text-[11px]">
                  <p className="font-bold text-carbon-900 capitalize">{key.replaceAll('_', ' ')}</p>
                  <p className="text-agriText-muted mt-0.5">{typeof value === 'string' ? value : JSON.stringify(value)}</p>
                </div>
              ))}
            </div>
          </Section>
        </>
      )}
    </div>
  );
}
