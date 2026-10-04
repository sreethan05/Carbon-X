import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Building2, Users, FileText, AlertTriangle, CheckCircle2, Search,
  PlusCircle, ExternalLink, Shield, Check, X, Loader2, RefreshCw
} from 'lucide-react';
import VerificationBadge from '../components/VerificationBadge';
import { useAuth } from '../context/AuthContext';
import {
  getFpoFarmers, getFpoPending, getFpoFlagged, getCertificates,
  fpoOnboardFarmer, fpoConfirmFarm, fpoReviewFarm,
} from '../services/api';

export default function FPODashboard() {
  const navigate = useNavigate();
  const { user, refreshUser } = useAuth();
  const [activeTab, setActiveTab] = useState('farmers');

  // Search & Filter for Tab 1
  const [searchTerm, setSearchTerm] = useState('');
  const [badgeFilter, setBadgeFilter] = useState('ALL');

  // Real data
  const [farmersList, setFarmersList] = useState([]);
  const [pendingQueue, setPendingQueue] = useState([]);
  const [flaggedList, setFlaggedList] = useState([]);
  const [certificates, setCertificates] = useState([]);
  const [stats, setStats] = useState({ totalFarmers: 0, totalAcreageHa: 0, pooledCredits: 0 });
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  // Tab 2: Onboarding Form State
  const [onboardData, setOnboardData] = useState({
    name: '', phone: '', survey_number: '', acreage: '', mandal: 'Pochampally', village: 'Pochampally',
  });
  const [onboardSuccess, setOnboardSuccess] = useState(false);
  const [onboardError, setOnboardError] = useState('');
  const [isOnboarding, setIsOnboarding] = useState(false);

  // Tab 4: Flagged Audit State
  const [auditNotes, setAuditNotes] = useState('');
  const [auditActionDone, setAuditActionDone] = useState(null);
  const [auditBusyId, setAuditBusyId] = useState(null);

  const loadAll = async () => {
    setLoading(true);
    setLoadError('');
    try {
      const [farmersRes, pendingRes, flaggedRes, certsRes] = await Promise.all([
        getFpoFarmers(), getFpoPending(), getFpoFlagged(), getCertificates(),
      ]);
      setFarmersList((farmersRes && farmersRes.farmers) || []);
      setStats({
        totalFarmers: (farmersRes && farmersRes.total_farmers) || 0,
        totalAcreageHa: (farmersRes && farmersRes.total_acreage) || 0,
        pooledCredits: (farmersRes && farmersRes.pooled_credits) || 0,
      });
      setPendingQueue((pendingRes && pendingRes.pending) || []);
      setFlaggedList((flaggedRes && flaggedRes.flagged) || []);
      setCertificates((certsRes && certsRes.success && certsRes.certificates) || []);
    } catch (e) {
      setLoadError('FPO services unreachable. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleOnboardSubmit = async (e) => {
    e.preventDefault();
    if (!onboardData.name || !onboardData.phone || !onboardData.survey_number) return;
    setIsOnboarding(true);
    setOnboardError('');
    try {
      const res = await fpoOnboardFarmer({
        name: onboardData.name,
        phone: onboardData.phone,
        survey_number: onboardData.survey_number,
        acreage: parseFloat(onboardData.acreage) || 2.0,
        mandal: onboardData.mandal,
        village: onboardData.village,
      });
      if (res && res.success) {
        setOnboardSuccess(true);
        setOnboardData({ name: '', phone: '', survey_number: '', acreage: '', mandal: 'Pochampally', village: 'Pochampally' });
        await loadAll();
        setTimeout(() => setOnboardSuccess(false), 4000);
      } else {
        setOnboardError((res && res.message) || 'Onboarding failed');
      }
    } catch (err) {
      setOnboardError('Onboarding service unreachable. Is the backend running?');
    } finally {
      setIsOnboarding(false);
    }
  };

  const handleApprovePending = async (farmId) => {
    setAuditBusyId(farmId);
    try {
      const res = await fpoConfirmFarm(farmId);
      if (res && res.success) {
        await loadAll();
        refreshUser();
      } else {
        alert((res && res.message) || 'Could not confirm farm');
      }
    } finally {
      setAuditBusyId(null);
    }
  };

  const handleReviewFlagged = async (farmId, action) => {
    setAuditBusyId(farmId);
    try {
      const res = await fpoReviewFarm(farmId, { action, notes: auditNotes });
      if (res && (res.success || res.ok)) {
        setAuditActionDone(action === 'approve' ? 'APPROVED_FPO' : 'REJECTED');
        setAuditNotes('');
        await loadAll();
      } else {
        alert((res && (res.message || res.detail)) || 'Review action failed');
      }
    } catch (err) {
      alert('Review service unreachable. Are you signed in as an FPO officer?');
    } finally {
      setAuditBusyId(null);
    }
  };

  const filteredFarmers = farmersList.filter(f => {
    const term = searchTerm.toLowerCase();
    const matchesSearch = !term
      || (f.name || '').toLowerCase().includes(term)
      || (f.phone || '').includes(term)
      || String(f.surveyNumber || '').toLowerCase().includes(term);
    const matchesBadge = badgeFilter === 'ALL' || f.badge === badgeFilter;
    return matchesSearch && matchesBadge;
  });

  const flaggedCount = flaggedList.length;

  return (
    <div className="min-h-screen bg-surface font-inter py-8 px-4 md:px-10 text-agriText-main">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Institutional Header */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-6">
          <div className="flex items-center gap-4">
            <div className="w-14 h-14 bg-surface-sage border border-forest-200 rounded-2xl flex items-center justify-center text-primary shadow-xs">
              <Building2 className="w-7 h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-bold text-primary uppercase tracking-wider bg-surface-sage border border-forest-200 px-2.5 py-0.5 rounded-full">
                  FPO Command Desk
                </span>
              </div>
              <h1 className="text-2xl font-extrabold text-carbon-900 font-manrope">{user?.name || 'FPO Cooperative'}</h1>
              <p className="text-xs text-agriText-muted mt-0.5">Officer: {user?.phone || '—'} | District: Yadadri Bhuvanagiri</p>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-4 w-full md:w-auto">
            <div className="bg-surface-sage/50 border border-forest-200 border-l-4 border-l-emerald-600 rounded-xl p-3 text-center">
              <p className="text-[10px] font-semibold text-agriText-subtle uppercase">Members</p>
              <p className="text-xl font-bold text-carbon-900 mt-0.5">{stats.totalFarmers}</p>
            </div>
            <div className="bg-surface-sage/50 border border-forest-200 border-l-4 border-l-emerald-600 rounded-xl p-3 text-center">
              <p className="text-[10px] font-semibold text-agriText-subtle uppercase">Total Acreage</p>
              <p className="text-xl font-bold text-carbon-900 mt-0.5">{stats.totalAcreageHa} ha</p>
            </div>
            <div className="bg-surface-sage/50 border border-forest-200 border-l-4 border-l-emerald-600 rounded-xl p-3 text-center">
              <p className="text-[10px] font-semibold text-agriText-subtle uppercase">Pooled Credits</p>
              <p className="text-xl font-bold text-primary mt-0.5">{stats.pooledCredits} MT</p>
            </div>
          </div>
        </div>

        {loadError && (
          <div className="bg-rose-50 border border-rose-200 text-rose-800 rounded-xl p-4 text-xs font-bold flex items-center justify-between">
            <span>{loadError}</span>
            <button onClick={loadAll} className="px-3 py-1.5 bg-rose-700 text-white rounded-lg flex items-center gap-1.5">
              <RefreshCw className="w-3.5 h-3.5" /> Retry
            </button>
          </div>
        )}

        {/* 5 Tab Navigation Ribbon */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-2 flex flex-wrap gap-2">
          {[
            { id: 'farmers', label: 'My Farmers', icon: Users, count: farmersList.length },
            { id: 'onboard', label: 'Bulk Member Onboarding', icon: PlusCircle },
            { id: 'pending', label: 'Pending Queue', icon: FileText, count: pendingQueue.length },
            { id: 'audit', label: `Flagged Reviews (${flaggedCount})`, icon: AlertTriangle, count: flaggedCount, highlight: flaggedCount > 0 },
            { id: 'certificates', label: 'FPO Certificates', icon: Shield, count: certificates.length }
          ].map(tab => {
            const Icon = tab.icon;
            const active = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold transition-all ${
                  active
                    ? 'bg-[#1B4332] text-white shadow-xs'
                    : tab.highlight
                    ? 'bg-amber-50 text-amber-900 hover:bg-amber-100 border border-amber-200'
                    : 'text-carbon-800 hover:bg-surface-sage'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
                {tab.count !== undefined && (
                  <span className={`px-2 py-0.5 rounded-full text-[10px] ${active ? 'bg-[#2D6A4F] text-white' : 'bg-surface-sage text-carbon-800'}`}>
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </div>

        {loading && (
          <div className="flex items-center gap-2 text-xs text-slate-500 px-2">
            <Loader2 className="w-4 h-4 animate-spin" /> Loading live FPO data…
          </div>
        )}

        {/* TAB 1: MY FARMERS */}
        {activeTab === 'farmers' && (
          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <h2 className="text-lg font-bold text-carbon-900">Registered Cooperative Members</h2>
                <p className="text-xs text-agriText-muted">Inspect member verification status, survey details, and carbon credits.</p>
              </div>

              <div className="flex items-center gap-3 w-full sm:w-auto">
                <div className="relative flex-1 sm:w-64">
                  <Search className="w-4 h-4 text-agriText-subtle absolute left-3 top-2.5" />
                  <input
                    type="text"
                    placeholder="Search name or phone..."
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                    className="w-full pl-9 pr-3 py-2 bg-surface-sage/40 border border-forest-200 rounded-xl text-xs text-carbon-900 focus:outline-none"
                  />
                </div>

                <select
                  value={badgeFilter}
                  onChange={e => setBadgeFilter(e.target.value)}
                  className="bg-surface-sage/40 border border-forest-200 rounded-xl text-xs text-carbon-900 px-3 py-2 font-medium focus:outline-none"
                >
                  <option value="ALL">All Badges</option>
                  <option value="REGISTRY">REGISTRY</option>
                  <option value="REGISTRY_DOC">REGISTRY_DOC</option>
                  <option value="DOCUMENT">DOCUMENT</option>
                  <option value="FPO">FPO</option>
                  <option value="PENDING">PENDING</option>
                  <option value="NONE">NONE</option>
                </select>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-forest-100 bg-[#F8FAF8] text-agriText-muted font-semibold uppercase tracking-wider">
                    <th className="py-3 px-4">Farmer</th>
                    <th className="py-3 px-4">Phone (+91)</th>
                    <th className="py-3 px-4">Village</th>
                    <th className="py-3 px-4">Farms</th>
                    <th className="py-3 px-4">Acreage</th>
                    <th className="py-3 px-4">Badge</th>
                    <th className="py-3 px-4">Credits</th>
                    <th className="py-3 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-forest-50">
                  {filteredFarmers.length === 0 ? (
                    <tr>
                      <td colSpan="8" className="py-8 px-4 text-center text-agriText-muted">
                        {loading ? 'Loading…' : 'No members found. Onboard farmers from the onboarding tab.'}
                      </td>
                    </tr>
                  ) : (
                    filteredFarmers.map((f) => (
                      <tr key={f.id} className="even:bg-[#F9FAF9] odd:bg-white hover:bg-emerald-50/60 transition-colors">
                        <td className="py-3 px-4 font-bold text-carbon-900">{f.name}</td>
                        <td className="py-3 px-4 font-mono text-agriText-muted">{f.phone || '—'}</td>
                        <td className="py-3 px-4 font-medium text-carbon-800">{f.village || '—'}</td>
                        <td className="py-3 px-4 font-semibold text-carbon-900">{f.farm_count}</td>
                        <td className="py-3 px-4 font-semibold text-carbon-900">{f.acres} ha</td>
                        <td className="py-3 px-4">
                          <VerificationBadge badge={f.badge || 'NONE'} size="sm" />
                        </td>
                        <td className="py-3 px-4 font-bold text-primary">{f.credits} MT</td>
                        <td className="py-3 px-4">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            f.status === 'FLAGGED' ? 'bg-red-50 text-red-700 border border-red-200' :
                            f.status === 'VERIFIED' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' :
                            'bg-amber-50 text-amber-800 border border-amber-200'
                          }`}>
                            {f.status}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* TAB 2: BULK ONBOARDING */}
        {activeTab === 'onboard' && (
          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-6">
            <div>
              <h2 className="text-lg font-bold text-carbon-900">Direct FPO Member Onboarding</h2>
              <p className="text-xs text-agriText-muted">Register cooperative farmers directly to assign FPO Badge (₹300 benchmark price).</p>
            </div>

            {onboardSuccess && (
              <div className="bg-surface-sage border border-forest-200 text-primary p-4 rounded-xl text-xs flex items-center gap-3 font-semibold">
                <CheckCircle2 className="w-5 h-5 text-primary" />
                <span>Farmer successfully onboarded under FPO Attestation with FPO Verification Badge.</span>
              </div>
            )}

            {onboardError && (
              <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl text-xs font-bold">
                {onboardError}
              </div>
            )}

            <form onSubmit={handleOnboardSubmit} className="grid grid-cols-1 md:grid-cols-2 gap-6 max-w-4xl">
              <div>
                <label className="block text-xs font-bold text-carbon-800 mb-1">Legal Full Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. K. Venu Gopal"
                  value={onboardData.name}
                  onChange={e => setOnboardData({ ...onboardData, name: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-sage/40 border border-forest-200 rounded-xl text-xs text-carbon-900 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-carbon-800 mb-1">Mobile Phone (+91)</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. 9876543217"
                  value={onboardData.phone}
                  onChange={e => setOnboardData({ ...onboardData, phone: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-sage/40 border border-forest-200 rounded-xl text-xs text-carbon-900 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-carbon-800 mb-1">Survey Parcel Number</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. 155/A"
                  value={onboardData.survey_number}
                  onChange={e => setOnboardData({ ...onboardData, survey_number: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-sage/40 border border-forest-200 rounded-xl text-xs text-carbon-900 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-bold text-carbon-800 mb-1">Parcel Acreage</label>
                <input
                  type="number"
                  step="0.1"
                  required
                  placeholder="e.g. 2.50"
                  value={onboardData.acreage}
                  onChange={e => setOnboardData({ ...onboardData, acreage: e.target.value })}
                  className="w-full px-3 py-2 bg-surface-sage/40 border border-forest-200 rounded-xl text-xs text-carbon-900 focus:outline-none"
                />
              </div>

              <div className="md:col-span-2 pt-2">
                <button
                  type="submit"
                  disabled={isOnboarding}
                  className="px-6 py-2.5 bg-primary hover:bg-primary-hover disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-2"
                >
                  {isOnboarding ? <Loader2 className="w-4 h-4 animate-spin" /> : <PlusCircle className="w-4 h-4" />}
                  <span>{isOnboarding ? 'Onboarding…' : 'Onboard Member & Issue FPO Badge'}</span>
                </button>
              </div>
            </form>
          </div>
        )}

        {/* TAB 3: PENDING QUEUE */}
        {activeTab === 'pending' && (
          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-6">
            <div>
              <h2 className="text-lg font-bold text-carbon-900">Pending Verification Queue</h2>
              <p className="text-xs text-agriText-muted">Confirm parcels awaiting FPO cooperative verification.</p>
            </div>

            {pendingQueue.length === 0 ? (
              <div className="text-center py-12 border-2 border-dashed border-forest-200 rounded-2xl">
                <CheckCircle2 className="w-10 h-10 text-primary mx-auto mb-2" />
                <p className="text-sm font-bold text-carbon-900">Queue Cleared</p>
                <p className="text-xs text-agriText-muted">No pending parcels awaiting review.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {pendingQueue.map(p => (
                  <div key={p.id} className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                    <div>
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono font-bold text-agriText-subtle">{(p.id || '').slice(0, 8)}</span>
                        <h3 className="text-sm font-bold text-carbon-900">{p.name}</h3>
                        <VerificationBadge badge="PENDING" size="sm" />
                      </div>
                      <p className="text-xs text-agriText-muted mt-1">
                        Phone: {p.phone || '—'} | Village: {p.village || '—'} | Farm: {p.farm_name || '—'} | Area: {p.acres} ha
                      </p>
                    </div>

                    <div className="flex items-center gap-2 w-full md:w-auto">
                      <button
                        onClick={() => handleApprovePending(p.id)}
                        disabled={auditBusyId === p.id}
                        className="flex-1 md:flex-none px-4 py-2 bg-primary hover:bg-primary-hover disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 shadow-xs"
                      >
                        {auditBusyId === p.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                        <span>Confirm under FPO Badge</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 4: FLAGGED REVIEWS */}
        {activeTab === 'audit' && (
          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-6">
            <div className="flex justify-between items-start">
              <div>
                <span className="text-[10px] font-bold text-amber-900 bg-amber-50 border border-amber-200 px-2.5 py-0.5 rounded-full uppercase tracking-wider">
                  Ground-Truth Audit Inspector
                </span>
                <h2 className="text-lg font-bold text-carbon-900 mt-1">Flagged Farm Reviews</h2>
                <p className="text-xs text-agriText-muted">Farms blocked by the fraud engine — approve under FPO badge or keep blocked.</p>
              </div>
            </div>

            {auditActionDone && (
              <div className={`p-4 rounded-xl border text-xs flex items-center gap-3 ${
                auditActionDone === 'APPROVED_FPO' ? 'bg-surface-sage border-forest-200 text-primary' : 'bg-red-50 border-red-200 text-red-900'
              }`}>
                <CheckCircle2 className="w-5 h-5" />
                <span className="font-semibold">
                  {auditActionDone === 'APPROVED_FPO'
                    ? 'Audit Action: Approved under FPO Attestation Badge (₹300 benchmark rate).'
                    : 'Audit Action: Farm kept flagged & blocked from credit earning.'}
                </span>
              </div>
            )}

            {flaggedList.length === 0 ? (
              <div className="text-center py-12 border-2 border-dashed border-forest-200 rounded-2xl">
                <CheckCircle2 className="w-10 h-10 text-primary mx-auto mb-2" />
                <p className="text-sm font-bold text-carbon-900">No flagged farms</p>
                <p className="text-xs text-agriText-muted">The fraud engine has not flagged any parcels.</p>
              </div>
            ) : (
              <div className="space-y-4">
                {flaggedList.map(fl => (
                  <div key={fl.id} className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 space-y-4">
                    <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                      <div>
                        <div className="flex items-center gap-3">
                          <h3 className="text-sm font-bold text-carbon-900">{fl.farmer_name}</h3>
                          <span className="text-xs font-mono text-agriText-subtle">{fl.farm_name || '—'}</span>
                        </div>
                        <p className="text-xs text-agriText-muted mt-1">
                          Village: {fl.village || '—'} | Area: {fl.claimed_acres} ha | Flagged: {fl.date}
                        </p>
                        <p className="text-xs text-amber-800 font-semibold mt-1">{fl.issue}</p>
                      </div>
                    </div>

                    <div className="bg-white border border-forest-200 rounded-xl p-3 space-y-3">
                      <textarea
                        rows={2}
                        placeholder="Enter physical field inspection notes..."
                        value={auditNotes}
                        onChange={e => setAuditNotes(e.target.value)}
                        className="w-full px-3 py-2 bg-white border border-forest-200 rounded-xl text-xs text-carbon-900 focus:outline-none"
                      />
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => handleReviewFlagged(fl.id, 'approve')}
                          disabled={auditBusyId === fl.id}
                          className="px-5 py-2.5 bg-primary hover:bg-primary-hover disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-2 shadow-xs"
                        >
                          {auditBusyId === fl.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                          <span>Approve under FPO Badge (₹300)</span>
                        </button>

                        <button
                          onClick={() => handleReviewFlagged(fl.id, 'reject')}
                          disabled={auditBusyId === fl.id}
                          className="px-5 py-2.5 bg-red-700 hover:bg-red-800 disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all flex items-center gap-2 shadow-xs"
                        >
                          <X className="w-4 h-4" />
                          <span>Reject & Keep Blocked</span>
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* TAB 5: FPO CERTIFICATES */}
        {activeTab === 'certificates' && (
          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-6">
            <div>
              <h2 className="text-lg font-bold text-carbon-900">Pool Procurement Certificates</h2>
              <p className="text-xs text-agriText-muted">Certificates generated from member credit sales on the marketplace.</p>
            </div>

            {certificates.length === 0 ? (
              <div className="text-center py-12 border-2 border-dashed border-forest-200 rounded-2xl">
                <Shield className="w-10 h-10 text-primary mx-auto mb-2" />
                <p className="text-sm font-bold text-carbon-900">No certificates yet</p>
                <p className="text-xs text-agriText-muted">When corporate buyers purchase member credits, pooled certificates appear here.</p>
              </div>
            ) : (
              <div className="space-y-2">
                {certificates.map(c => (
                  <div
                    key={c.id}
                    onClick={() => navigate(`/buyer/certificates/${c.id}`)}
                    className="bg-surface-sage/40 border border-forest-200 rounded-xl p-4 flex justify-between items-center hover:border-primary cursor-pointer transition-all"
                  >
                    <div>
                      <p className="text-xs font-mono font-bold text-carbon-900">{c.id}</p>
                      <p className="text-[11px] text-agriText-muted mt-0.5">
                        {c.volume_mt} MT CO2e · {c.crop || 'Mixed Crop'} · {c.farmer_name || 'Pool'} · {c.status === 'RETIRED' ? 'Retired' : 'Held in Escrow'}
                      </p>
                    </div>
                    <ExternalLink className="w-4 h-4 text-primary" />
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

      </div>
    </div>
  );
}
