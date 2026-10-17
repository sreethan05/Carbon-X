import React, { useEffect, useState } from 'react';
import { ShieldCheck, RefreshCw, AlertTriangle, Check, X } from 'lucide-react';
import { getOpsSummary, getFpoPending, getFpoFlagged, fpoConfirmFarm, fpoReviewFarm } from '../services/api';

export default function AdminDashboard() {
  const [summary, setSummary] = useState(null);
  const [pendingQueue, setPendingQueue] = useState([]);
  const [flaggedQueue, setFlaggedQueue] = useState([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [actionError, setActionError] = useState('');
  const [busyId, setBusyId] = useState(null);

  const loadAll = async () => {
    setIsLoading(true);
    setLoadError('');
    const [sumRes, pendingRes, flaggedRes] = await Promise.all([
      getOpsSummary(), getFpoPending(), getFpoFlagged(),
    ]);
    if (sumRes && sumRes.success) {
      setSummary(sumRes);
    } else {
      setSummary(null);
      setLoadError((sumRes && sumRes.message) || 'Ops summary unavailable');
    }
    setPendingQueue((pendingRes && pendingRes.pending) || []);
    setFlaggedQueue((flaggedRes && flaggedRes.flagged) || []);
    setIsLoading(false);
  };

  useEffect(() => { loadAll(); }, []);

  const runAction = async (farmId, action) => {
    setBusyId(farmId);
    setActionError('');
    const res = action === 'approve'
      ? await fpoConfirmFarm(farmId)
      : await fpoReviewFarm(farmId, { action: 'reject' });
    if (!res || !res.success) {
      setActionError((res && res.message) || `Could not ${action} the farm.`);
    }
    setBusyId(null);
    await loadAll();
  };

  // Real queue rows: flagged farms first, then pending enrollments.
  const queueRows = [
    ...flaggedQueue.map((f) => ({
      key: `flagged-${f.id}`,
      id: f.id,
      stage: 'FLAGGED',
      farmer: f.farmer_name || 'Unknown Farmer',
      farmName: f.farm_name,
      village: f.village,
      areaHa: f.area_hectares,
      detail: f.issue || 'Flagged for review',
      date: f.date,
    })),
    ...pendingQueue.map((p) => ({
      key: `pending-${p.id}`,
      id: p.id,
      stage: 'PENDING',
      farmer: p.name || 'Unknown Farmer',
      farmName: p.farm_name,
      village: p.village,
      areaHa: p.area_hectares,
      detail: `${p.crop || 'Crop not set'} — new enrollment awaiting verification`,
      date: p.date,
    })),
  ];

  const metric = (value) => (value === null || value === undefined ? '—' : Number(value).toLocaleString('en-IN'));

  return (
    <div className="min-h-screen bg-slate-50 font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Header */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex justify-between items-center">
          <div>
            <span className="text-xs font-semibold text-rose-800 uppercase tracking-wider bg-rose-50 border border-rose-200 px-2.5 py-0.5 rounded-full inline-block mb-1">
              Integrity Oversight
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Platform Compliance & Audit Desk</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Live operational counts and the real verification review queue — approvals/rejections write to the farm record and the KYC audit log.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={loadAll}
              disabled={isLoading}
              className="px-3 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg text-xs font-bold flex items-center gap-1.5 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              <span>Refresh</span>
            </button>
            <ShieldCheck className="w-10 h-10 text-slate-800" />
          </div>
        </div>

        {loadError && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-700 mt-0.5 shrink-0" />
            <div className="text-xs text-amber-900">
              <p className="font-bold">Live metrics unavailable</p>
              <p className="mt-0.5">{loadError} — this desk reads from the live database.</p>
            </div>
          </div>
        )}

        {/* System-wide metrics from GET /ops/summary */}
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Registered Profiles</p>
            <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">{metric(summary && summary.profiles)}</p>
            <p className="text-xs text-slate-500 mt-1">KYC records: {metric(summary && summary.kyc_verifications)}</p>
          </div>

          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Active Credit Listings</p>
            <p className="text-2xl font-extrabold text-slate-900 font-manrope mt-1">{metric(summary && summary.listings_active)}</p>
            <p className="text-xs text-slate-500 mt-1">Retired: {metric(summary && summary.listings_retired)}</p>
          </div>

          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Farms Flagged (at risk)</p>
            <p className="text-2xl font-extrabold text-rose-800 font-manrope mt-1">{metric(summary && summary.farms_flagged_at_risk)}</p>
            <p className="text-xs text-rose-700 font-medium mt-1">Routed to FPO review</p>
          </div>

          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Pending Review</p>
            <p className="text-2xl font-extrabold text-amber-800 font-manrope mt-1">{metric(summary && summary.farms_pending_review)}</p>
            <p className="text-xs text-amber-700 font-medium mt-1">Credits blocked until verified</p>
          </div>
        </div>

        {/* Ledger & calibration strip */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-5 flex flex-wrap gap-x-8 gap-y-2">
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Ledger events: <span className="text-slate-900 font-mono">{metric(summary && summary.ledger_events)}</span></span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Ground-truth samples: <span className="text-slate-900 font-mono">{metric(summary && summary.ground_truth_samples)}</span></span>
          <span className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Farms total: <span className="text-slate-900 font-mono">{metric(summary && summary.farms_total)}</span></span>
        </div>

        {/* Verification review queue */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-4">
          <div>
            <h2 className="text-base font-bold text-slate-900">Verification Review Queue</h2>
            <p className="text-xs text-slate-500 mt-0.5">Real pending and flagged farm records. Approve certifies the farm (FPO-attested badge); reject keeps it flagged with credits blocked.</p>
          </div>

          {actionError && (
            <p className="text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg">{actionError}</p>
          )}

          {queueRows.length === 0 && !isLoading ? (
            <div className="border border-dashed border-slate-200 rounded-xl p-8 text-center">
              <ShieldCheck className="w-8 h-8 text-slate-300 mx-auto mb-2" />
              <p className="text-sm font-bold text-slate-700">No farms awaiting review</p>
              <p className="text-xs text-slate-500 mt-1">Pending enrollments and monitoring flags will appear here as they are raised.</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-slate-600 font-semibold uppercase tracking-wider">
                    <th className="py-3 px-4">Stage</th>
                    <th className="py-3 px-4">Farm & Farmer</th>
                    <th className="py-3 px-4">Village</th>
                    <th className="py-3 px-4">Area (ha)</th>
                    <th className="py-3 px-4">Detail</th>
                    <th className="py-3 px-4">Raised</th>
                    <th className="py-3 px-4">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {queueRows.map((row) => (
                    <tr key={row.key} className="hover:bg-slate-50 transition-colors">
                      <td className="py-3 px-4">
                        <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold border ${
                          row.stage === 'FLAGGED'
                            ? 'bg-rose-50 text-rose-800 border-rose-200'
                            : 'bg-amber-50 text-amber-800 border-amber-200'
                        }`}>
                          {row.stage}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <p className="font-bold text-slate-900">{row.farmName || '—'}</p>
                        <p className="text-slate-500">{row.farmer}{row.village ? ` · ${row.village}` : ''}</p>
                      </td>
                      <td className="py-3 px-4 text-slate-700">{row.village || '—'}</td>
                      <td className="py-3 px-4 text-slate-900 font-mono">{row.areaHa ?? row.area ?? '—'}</td>
                      <td className="py-3 px-4 text-slate-700">{row.detail}</td>
                      <td className="py-3 px-4 text-slate-500 font-mono">{row.date || '—'}</td>
                      <td className="py-3 px-4">
                        <div className="flex gap-2">
                          <button
                            onClick={() => runAction(row.id, 'approve')}
                            disabled={busyId === row.id}
                            className="px-2.5 py-1 bg-emerald-700 hover:bg-emerald-600 text-white rounded text-[10px] font-bold flex items-center gap-1 disabled:opacity-50"
                          >
                            <Check className="w-3 h-3" />
                            <span>Approve</span>
                          </button>
                          <button
                            onClick={() => runAction(row.id, 'reject')}
                            disabled={busyId === row.id}
                            className="px-2.5 py-1 bg-rose-800 hover:bg-rose-700 text-white rounded text-[10px] font-bold flex items-center gap-1 disabled:opacity-50"
                          >
                            <X className="w-3 h-3" />
                            <span>Reject</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

      </div>
    </div>
  );
}
