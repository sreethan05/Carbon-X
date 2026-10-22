import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import {
  Building2, Users, FileText, AlertTriangle, CheckCircle2, Search,
  PlusCircle, ExternalLink, Shield, Check, X, Loader2, RefreshCw,
  Layers, Sparkles, CheckSquare
} from 'lucide-react';
import VerificationBadge from '../components/VerificationBadge';
import { useAuth } from '../context/AuthContext';
import {
  getFpoFarmers, getFpoPending, getFpoFlagged, getCertificates,
  fpoOnboardFarmer, fpoConfirmFarm, fpoReviewFarm, runMonitoring,
  createMarketplaceListing, getMarketplaceListings
} from '../services/api';

export default function FPODashboard() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, refreshUser } = useAuth();
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined' && window.location.pathname.includes('credit-pooling')) {
      return 'pooling';
    }
    return 'farmers';
  });

  useEffect(() => {
    if (location.pathname.includes('credit-pooling')) {
      setActiveTab('pooling');
    }
  }, [location.pathname]);

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
    name: '', phone: '', survey_number: '', acreage: '', mandal: '', village: '',
  });
  const [onboardSuccess, setOnboardSuccess] = useState(false);
  const [onboardError, setOnboardError] = useState('');
  const [isOnboarding, setIsOnboarding] = useState(false);

  // Tab 4: Flagged Audit State (per-farm notes to avoid cross-card leakage)
  const [auditNotes, setAuditNotes] = useState({});
  const [auditActionDone, setAuditActionDone] = useState(null);
  const [auditBusyId, setAuditBusyId] = useState(null);

  // Credit Pooling Workbench State
  const [selectedFarmerIds, setSelectedFarmerIds] = useState(new Set());
  const [poolPricePerCredit, setPoolPricePerCredit] = useState(300);
  const [isPublishingPool, setIsPublishingPool] = useState(false);
  const [poolPublishSuccess, setPoolPublishSuccess] = useState(null);
  const [poolPublishError, setPoolPublishError] = useState('');
  const [fpoListings, setFpoListings] = useState([]);

  // 5-day NDVI monitoring cycle
  const [monitorResult, setMonitorResult] = useState(null);
  const [isMonitoring, setIsMonitoring] = useState(false);
  const handleRunMonitoring = async () => {
    setIsMonitoring(true);
    setMonitorResult(null);
    try {
      const res = await runMonitoring();
      setMonitorResult(res && res.success ? res : { success: false, message: (res && res.message) || 'Monitoring failed' });
      if (res && res.success) await loadAll();
    } catch {
      setMonitorResult({ success: false, message: 'Monitoring service unreachable.' });
    } finally {
      setIsMonitoring(false);
    }
  };

  const loadAll = async () => {
    setLoading(true);
    setLoadError('');
    try {
      const [farmersRes, pendingRes, flaggedRes, certsRes, listingsRes] = await Promise.all([
        getFpoFarmers(), getFpoPending(), getFpoFlagged(), getCertificates(), getMarketplaceListings({ status: 'all' }),
      ]);
      const farmers = (farmersRes && farmersRes.farmers) || [];
      setFarmersList(farmers);
      setSelectedFarmerIds(new Set(farmers.filter(f => f.status === 'VERIFIED' && (parseFloat(f.credits) || 0) > 0).map(f => f.id)));
      setStats({
        totalFarmers: (farmersRes && farmersRes.total_farmers) || 0,
        totalAcreageHa: (farmersRes && farmersRes.total_hectares) || 0,
        pooledCredits: (farmersRes && farmersRes.pooled_credits) || 0,
      });
      setPendingQueue((pendingRes && pendingRes.pending) || []);
      setFlaggedList((flaggedRes && flaggedRes.flagged) || []);
      setCertificates((certsRes && certsRes.success && certsRes.certificates) || []);
      setFpoListings((listingsRes && listingsRes.listings) || []);
    } catch {
      setLoadError('FPO services unreachable. Is the backend running?');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadAll(); }, []);

  const handleOnboardSubmit = async (e) => {
    e.preventDefault();
    if (!onboardData.name || !onboardData.phone || !onboardData.survey_number) return;
    const acreageHa = parseFloat(onboardData.acreage);
    if (!Number.isFinite(acreageHa) || acreageHa <= 0) {
      setOnboardError('Enter the parcel area in hectares (a positive number).');
      return;
    }
    setIsOnboarding(true);
    setOnboardError('');
    try {
      const res = await fpoOnboardFarmer({
        name: onboardData.name,
        phone: onboardData.phone,
        survey_number: onboardData.survey_number,
        acreage: acreageHa,
        mandal: onboardData.mandal,
        village: onboardData.village,
      });
      if (res && res.success) {
        setOnboardSuccess(true);
        setOnboardData({ name: '', phone: '', survey_number: '', acreage: '', mandal: '', village: '' });
        await loadAll();
        setTimeout(() => setOnboardSuccess(false), 4000);
      } else {
        setOnboardError((res && res.message) || 'Onboarding failed');
      }
    } catch {
      setOnboardError('Onboarding service unreachable. Is the backend running?');
    } finally {
      setIsOnboarding(false);
    }
  };

  // Tab 3 & 4 feedback banners
  const [pendingFeedback, setPendingFeedback] = useState(null);
  const [flaggedFeedback, setFlaggedFeedback] = useState(null);

  const handleApprovePending = async (farmId) => {
    setAuditBusyId(farmId);
    setPendingFeedback(null);
    const previousQueue = [...pendingQueue];
    const previousFarmers = [...farmersList];
    const target = pendingQueue.find(p => p.id === farmId);

    // Optimistic UI update: remove from pending queue immediately
    setPendingQueue(prev => prev.filter(p => p.id !== farmId));
    if (target?.phone) {
      setFarmersList(prev => prev.map(f => f.phone === target.phone ? { ...f, badge: 'FPO', status: 'VERIFIED' } : f));
    }

    try {
      const res = await fpoConfirmFarm(farmId);
      if (res && res.success) {
        setPendingFeedback({
          type: 'success',
          message: `Parcel ${target?.name ? `(${target.name})` : farmId.slice(0, 8)} approved and assigned FPO Badge.`,
        });
        await loadAll();
        refreshUser();
      } else {
        // Rollback on failure
        setPendingQueue(previousQueue);
        setFarmersList(previousFarmers);
        setPendingFeedback({
          type: 'error',
          message: (res && res.message) || 'Could not confirm farm. Reverted pending queue.',
        });
      }
    } catch {
      // Rollback on network/service exception
      setPendingQueue(previousQueue);
      setFarmersList(previousFarmers);
      setPendingFeedback({
        type: 'error',
        message: 'Review service unreachable. Reverted pending queue.',
      });
    } finally {
      setAuditBusyId(null);
    }
  };

  const handleRejectPending = async (farmId) => {
    setAuditBusyId(farmId);
    setPendingFeedback(null);
    const previousQueue = [...pendingQueue];
    const target = pendingQueue.find(p => p.id === farmId);

    // Optimistic UI update: remove from pending queue immediately
    setPendingQueue(prev => prev.filter(p => p.id !== farmId));

    try {
      const res = await fpoReviewFarm(farmId, { action: 'reject', notes: 'Pending parcel rejected by FPO officer' });
      if (res && (res.success || res.ok)) {
        setPendingFeedback({
          type: 'success',
          message: `Parcel ${target?.name ? `(${target.name})` : farmId.slice(0, 8)} rejected and kept blocked.`,
        });
        await loadAll();
      } else {
        // Rollback on failure
        setPendingQueue(previousQueue);
        setPendingFeedback({
          type: 'error',
          message: (res && (res.message || res.detail)) || 'Could not reject farm. Reverted pending queue.',
        });
      }
    } catch {
      // Rollback on exception
      setPendingQueue(previousQueue);
      setPendingFeedback({
        type: 'error',
        message: 'Review service unreachable. Reverted pending queue.',
      });
    } finally {
      setAuditBusyId(null);
    }
  };

  const handleReviewFlagged = async (farmId, action) => {
    setAuditBusyId(farmId);
    setFlaggedFeedback(null);
    const previousFlagged = [...flaggedList];
    const target = flaggedList.find(fl => fl.id === farmId);

    // Optimistic UI update: remove from flagged review queue immediately
    setFlaggedList(prev => prev.filter(fl => fl.id !== farmId));

    try {
      const notes = auditNotes[farmId] || '';
      const res = await fpoReviewFarm(farmId, { action, notes });
      if (res && (res.success || res.ok)) {
        setAuditActionDone(action === 'approve' ? 'APPROVED_FPO' : 'REJECTED');
        setFlaggedFeedback({
          type: 'success',
          message: action === 'approve'
            ? `Farm ${target?.farmer_name || farmId.slice(0, 8)} approved under FPO Attestation Badge (₹300 benchmark rate).`
            : `Farm ${target?.farmer_name || farmId.slice(0, 8)} kept flagged; credits remain blocked.`,
        });
        setAuditNotes(prev => {
          const next = { ...prev };
          delete next[farmId];
          return next;
        });
        await loadAll();
      } else {
        // Rollback on failure
        setFlaggedList(previousFlagged);
        setFlaggedFeedback({
          type: 'error',
          message: (res && (res.message || res.detail)) || 'Review action failed. Reverted flagged queue.',
        });
      }
    } catch {
      // Rollback on exception
      setFlaggedList(previousFlagged);
      setFlaggedFeedback({
        type: 'error',
        message: 'Review service unreachable. Reverted flagged queue.',
      });
    } finally {
      setAuditBusyId(null);
    }
  };

  const handlePublishPool = async (e) => {
    if (e) e.preventDefault();
    const selected = farmersList.filter(f => selectedFarmerIds.has(f.id));
    const totalCredits = selected.reduce((sum, f) => sum + (parseFloat(f.credits) || 0), 0);
    if (totalCredits <= 0) {
      setPoolPublishError('Please select at least one verified member parcel with credits to assemble a pooled lot.');
      return;
    }
    const unitPrice = parseFloat(poolPricePerCredit);
    if (!Number.isFinite(unitPrice) || unitPrice < 100) {
      setPoolPublishError('Enter a valid price per credit (minimum ₹100/MT).');
      return;
    }

    setIsPublishingPool(true);
    setPoolPublishError('');
    setPoolPublishSuccess(null);
    try {
      const res = await createMarketplaceListing({
        credits: totalCredits,
        carbon_credits: totalCredits,
        price_per_credit: unitPrice,
        crop: 'Cooperative Agroforestry / Mixed',
      });
      if (res && (res.success || res.listing || res.id)) {
        setPoolPublishSuccess({
          volume: totalCredits,
          price: unitPrice,
          memberCount: selected.length,
          listingId: res.id || (res.listing && res.listing.id),
        });
        await loadAll();
        setTimeout(() => setPoolPublishSuccess(null), 8000);
      } else {
        setPoolPublishError((res && res.message) || 'Failed to publish pooled listing to marketplace.');
      }
    } catch {
      setPoolPublishError('Marketplace service unreachable.');
    } finally {
      setIsPublishingPool(false);
    }
  };

  const toggleSelectFarmer = (id) => {
    setSelectedFarmerIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const verifiedWithCredits = farmersList.filter(f => f.status === 'VERIFIED' && (parseFloat(f.credits) || 0) > 0);
  const hasEligibleMembers = verifiedWithCredits.length > 0;
  const isAllVerifiedSelected = hasEligibleMembers && selectedFarmerIds.size === verifiedWithCredits.length;

  const toggleSelectAllVerified = () => {
    if (!hasEligibleMembers) return;
    if (isAllVerifiedSelected) {
      setSelectedFarmerIds(new Set());
    } else {
      setSelectedFarmerIds(new Set(verifiedWithCredits.map(f => f.id)));
    }
  };

  const filteredFarmers = farmersList.filter(f => {
    const term = searchTerm.toLowerCase();
    const matchesSearch = !term
      || (f.name || '').toLowerCase().includes(term)
      || (f.phone || '').includes(term)
      || (f.village || '').toLowerCase().includes(term)
      || (f.district || '').toLowerCase().includes(term)
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
            <div className="w-14 h-14 bg-surface-sage border border-forest-200 rounded-2xl flex items-center justify-center text-primary shadow-xs shrink-0">
              <Building2 className="w-7 h-7" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="text-[10px] font-bold text-primary uppercase tracking-wider bg-surface-sage border border-forest-200 px-2.5 py-0.5 rounded-full">
                  FPO Command Desk
                </span>
              </div>
              <h1 className="text-2xl font-extrabold text-carbon-900 font-manrope">{user?.name || 'FPO Cooperative'}</h1>
              <p className="text-xs text-agriText-muted mt-0.5">Officer: {user?.phone || '—'} | District: {user?.district || '—'}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 w-full md:w-auto">
            <div className="bg-surface-sage/50 border border-forest-200 border-l-4 border-l-emerald-600 rounded-xl p-3 text-center">
              <p className="text-[10px] font-semibold text-agriText-subtle uppercase">Members</p>
              <p className="text-xl font-bold text-carbon-900 mt-0.5">{stats.totalFarmers}</p>
            </div>
            <div className="bg-surface-sage/50 border border-forest-200 border-l-4 border-l-emerald-600 rounded-xl p-3 text-center">
              <p className="text-[10px] font-semibold text-agriText-subtle uppercase">Total Area</p>
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

        {/* 5-day NDVI Monitoring Cycle */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-carbon-900">5-Day Sentinel-2 Monitoring Cycle</h2>
            <p className="text-xs text-agriText-muted mt-0.5">
              Re-checks every plot's NDVI; a significant drop flags credits at-risk and routes them to the flagged queue.
            </p>
            {monitorResult && monitorResult.success && (
              <p className={`text-xs font-bold mt-2 ${monitorResult.at_risk_count > 0 ? 'text-amber-700' : 'text-emerald-700'}`}>
                Last cycle: {monitorResult.checked} plots checked · {monitorResult.healthy} healthy ·{' '}
                {monitorResult.at_risk_count} flagged at-risk (drop ≥ {monitorResult.alert_threshold})
              </p>
            )}
            {monitorResult && !monitorResult.success && (
              <p className="text-xs font-bold text-rose-700 mt-2">{monitorResult.message}</p>
            )}
          </div>
          <button
            onClick={handleRunMonitoring}
            disabled={isMonitoring}
            className="px-4 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all shadow-sm whitespace-nowrap flex items-center gap-2"
          >
            {isMonitoring ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span>{isMonitoring ? 'Running cycle…' : 'Run Monitoring Cycle'}</span>
          </button>
        </div>

        {/* 6 Tab Navigation Ribbon */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-2 flex flex-wrap gap-2">
          {[
            { id: 'farmers', label: 'My Farmers', icon: Users, count: farmersList.length },
            { id: 'pooling', label: 'Credit Pooling Workbench', icon: Layers, count: `${stats.pooledCredits} MT`, highlight: stats.pooledCredits > 0 },
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
                    ? 'bg-[#0C2A18] text-white shadow-xs'
                    : tab.highlight
                    ? 'bg-amber-50 text-amber-900 hover:bg-amber-100 border border-amber-200'
                    : 'text-carbon-800 hover:bg-surface-sage'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.label}</span>
                {tab.count !== undefined && (
                  <span className={`px-2 py-0.5 rounded-full text-[10px] ${active ? 'bg-[#15803D] text-white' : 'bg-surface-sage text-carbon-800'}`}>
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

            <div className="overflow-x-auto -mx-6 px-6 sm:mx-0 sm:px-0">
              <table className="w-full text-left text-xs border-collapse min-w-[680px]">
                <thead>
                  <tr className="border-b border-forest-100 bg-[#F8FAF8] text-agriText-muted font-semibold uppercase tracking-wider">
                    <th className="py-3 px-4">Farmer</th>
                    <th className="py-3 px-4">Phone (+91)</th>
                    <th className="py-3 px-4">Village</th>
                    <th className="py-3 px-4">Farms</th>
                    <th className="py-3 px-4">Area (ha)</th>
                    <th className="py-3 px-4">Badge</th>
                    <th className="py-3 px-4">Credits</th>
                    <th className="py-3 px-4">Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-forest-50">
                  {filteredFarmers.length === 0 ? (
                    <tr>
                      <td colSpan="8" className="py-12 px-4 text-center">
                        {loading ? (
                          <div className="flex items-center justify-center gap-2 text-agriText-muted">
                            <Loader2 className="w-4 h-4 animate-spin text-primary" />
                            <span>Loading cooperative member roster…</span>
                          </div>
                        ) : farmersList.length === 0 ? (
                          <div className="max-w-md mx-auto space-y-3 py-4">
                            <div className="w-12 h-12 bg-surface-sage rounded-2xl flex items-center justify-center text-primary mx-auto">
                              <Users className="w-6 h-6" />
                            </div>
                            <h3 className="text-sm font-bold text-carbon-900">No Cooperative Members Registered Yet</h3>
                            <p className="text-xs text-agriText-muted leading-relaxed">
                              No smallholder farmers are currently assigned to your FPO jurisdiction. Use the onboarding tab to register members directly and assign FPO Badges.
                            </p>
                            <button
                              type="button"
                              onClick={() => setActiveTab('onboard')}
                              className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-xs"
                            >
                              <PlusCircle className="w-4 h-4" />
                              <span>Onboard First Member</span>
                            </button>
                          </div>
                        ) : (
                          <div className="max-w-md mx-auto space-y-2 py-4">
                            <p className="text-sm font-bold text-carbon-900">No Members Match Search</p>
                            <p className="text-xs text-agriText-muted">
                              No records found for "{searchTerm || badgeFilter}".
                            </p>
                            <button
                              type="button"
                              onClick={() => { setSearchTerm(''); setBadgeFilter('ALL'); }}
                              className="text-xs text-primary font-bold hover:underline"
                            >
                              Reset Search & Filters
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  ) : (
                    filteredFarmers.map((f) => (
                      <tr key={f.id} className="even:bg-[#F9FAF9] odd:bg-white hover:bg-emerald-50/60 transition-colors">
                        <td className="py-3 px-4 font-bold text-carbon-900">{f.name}</td>
                        <td className="py-3 px-4 font-mono text-agriText-muted">{f.phone || '—'}</td>
                        <td className="py-3 px-4 font-medium text-carbon-800">{f.village || '—'}</td>
                        <td className="py-3 px-4 font-semibold text-carbon-900">{f.farm_count}</td>
                        <td className="py-3 px-4 font-semibold text-carbon-900">{f.area_hectares} ha</td>
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

        {/* TAB: CREDIT POOLING WORKBENCH */}
        {activeTab === 'pooling' && (
          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-6">
            <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
              <div>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-[10px] font-bold text-primary uppercase tracking-wider bg-surface-sage border border-forest-200 px-2.5 py-0.5 rounded-full">
                    Cooperative Aggregation Desk
                  </span>
                  <span className="text-[10px] font-semibold text-emerald-800 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded">
                    70% Farmer Floor Enforced
                  </span>
                </div>
                <h2 className="text-lg font-bold text-carbon-900 font-manrope">Cooperative Credit Pooling Workbench</h2>
                <p className="text-xs text-agriText-muted">
                  Aggregate smallholder member credits into institutional-grade lots for corporate ESG procurement at fair benchmark rates.
                </p>
              </div>

              <div className="flex items-center gap-2">
                <button
                  type="button"
                  disabled={!hasEligibleMembers}
                  onClick={toggleSelectAllVerified}
                  className="px-3 py-2 bg-surface-sage border border-forest-200 text-carbon-900 rounded-xl text-xs font-bold hover:bg-forest-100 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
                >
                  <CheckSquare className="w-4 h-4 text-primary" />
                  <span>{isAllVerifiedSelected ? 'Deselect All' : 'Select All Verified'}</span>
                </button>
              </div>
            </div>

            {/* Payout & Revenue Split Projection Matrix */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div className="bg-surface-sage/50 border border-forest-200 rounded-xl p-4">
                <p className="text-[10px] font-semibold text-agriText-subtle uppercase">Selected Pool Volume</p>
                <p className="text-2xl font-extrabold text-primary font-manrope mt-1">
                  {farmersList.filter(f => selectedFarmerIds.has(f.id)).reduce((sum, f) => sum + (parseFloat(f.credits) || 0), 0).toFixed(2)} MT
                </p>
                <p className="text-[11px] text-agriText-muted mt-0.5">
                  {selectedFarmerIds.size} farmers · {farmersList.filter(f => selectedFarmerIds.has(f.id)).reduce((sum, f) => sum + (parseFloat(f.area_hectares) || 0), 0).toFixed(1)} ha
                </p>
              </div>

              <div className="bg-emerald-50/60 border border-emerald-200 rounded-xl p-4">
                <p className="text-[10px] font-semibold text-emerald-800 uppercase">Gross Pool Value</p>
                <p className="text-2xl font-extrabold text-emerald-950 font-manrope mt-1">
                  ₹{Math.round(farmersList.filter(f => selectedFarmerIds.has(f.id)).reduce((sum, f) => sum + (parseFloat(f.credits) || 0), 0) * poolPricePerCredit).toLocaleString('en-IN')}
                </p>
                <p className="text-[11px] text-emerald-700 mt-0.5">@ ₹{poolPricePerCredit}/MT benchmark rate</p>
              </div>

              <div className="bg-emerald-50/40 border border-emerald-200 border-l-4 border-l-emerald-600 rounded-xl p-4">
                <div className="flex justify-between items-center">
                  <p className="text-[10px] font-semibold text-agriText-subtle uppercase">Farmers Net (70% Floor)</p>
                  <span className="text-[10px] font-bold text-emerald-800 bg-emerald-100 px-1.5 py-0.5 rounded">Paise Invariant</span>
                </div>
                <p className="text-2xl font-extrabold text-emerald-900 font-manrope mt-1">
                  ₹{Math.round(farmersList.filter(f => selectedFarmerIds.has(f.id)).reduce((sum, f) => sum + (parseFloat(f.credits) || 0), 0) * poolPricePerCredit * 0.70).toLocaleString('en-IN')}
                </p>
                <p className="text-[11px] text-agriText-muted mt-0.5">Ledger-recorded pilot payouts; bank transfer simulated in this phase</p>
              </div>

              <div className="bg-surface-sage/50 border border-forest-200 border-l-4 border-l-amber-500 rounded-xl p-4">
                <div className="flex justify-between items-center">
                  <p className="text-[10px] font-semibold text-agriText-subtle uppercase">FPO Retained (5%)</p>
                  <span className="text-[10px] font-bold text-amber-800 bg-amber-100 px-1.5 py-0.5 rounded">Attestation Fee</span>
                </div>
                <p className="text-2xl font-extrabold text-amber-900 font-manrope mt-1">
                  ₹{Math.round(farmersList.filter(f => selectedFarmerIds.has(f.id)).reduce((sum, f) => sum + (parseFloat(f.credits) || 0), 0) * poolPricePerCredit * 0.05).toLocaleString('en-IN')}
                </p>
                <p className="text-[11px] text-agriText-muted mt-0.5">Credited to FPO Treasury upon settlement</p>
              </div>
            </div>

            {poolPublishSuccess && (
              <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 p-4 rounded-xl text-xs flex items-center justify-between font-semibold">
                <div className="flex items-center gap-2">
                  <CheckCircle2 className="w-5 h-5 text-emerald-700 shrink-0" />
                  <span>
                    Successfully published pooled lot of <strong>{poolPublishSuccess.volume} MT CO2e</strong> across {poolPublishSuccess.memberCount} members at ₹{poolPublishSuccess.price}/MT! Listing ID: {poolPublishSuccess.listingId}
                  </span>
                </div>
                <button
                  onClick={() => navigate('/marketplace')}
                  className="px-3 py-1.5 bg-emerald-800 text-white rounded-lg text-xs font-bold hover:bg-emerald-700 flex items-center gap-1"
                >
                  <span>View on Marketplace</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {poolPublishError && (
              <div className="bg-rose-50 border border-rose-200 text-rose-800 p-4 rounded-xl text-xs font-bold">
                {poolPublishError}
              </div>
            )}

            {/* Assemble & Publish Form */}
            <div className="bg-surface-sage/30 border border-forest-200 rounded-xl p-4 space-y-4">
              <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
                <div className="flex items-center gap-3">
                  <label className="text-xs font-bold text-carbon-800">
                    Listing Price per MT CO2e (₹):
                  </label>
                  <input
                    type="number"
                    min="100"
                    step="10"
                    value={poolPricePerCredit}
                    onChange={e => setPoolPricePerCredit(e.target.value)}
                    className="w-32 px-3 py-1.5 bg-white border border-forest-200 rounded-xl text-xs font-mono font-bold text-carbon-900 focus:outline-none focus:border-primary"
                  />
                  <span className="text-[11px] text-agriText-muted">FPO attestation benchmark: ₹300/MT</span>
                </div>

                <button
                  type="button"
                  onClick={handlePublishPool}
                  disabled={isPublishingPool || selectedFarmerIds.size === 0}
                  className="px-6 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-2"
                >
                  {isPublishingPool ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-emerald-300" />}
                  <span>Publish Cooperative Lot to Marketplace</span>
                </button>
              </div>
            </div>

            {/* Member Selection Table */}
            <div className="space-y-2">
              <h3 className="text-xs font-bold text-carbon-800 uppercase tracking-wider">Select Member Allocations for This Pool</h3>
              <div className="overflow-x-auto border border-forest-100 rounded-xl">
                <table className="w-full text-left text-xs border-collapse min-w-[780px]">
                  <thead>
                    <tr className="border-b border-forest-100 bg-[#F8FAF8] text-agriText-muted font-semibold uppercase tracking-wider">
                      <th className="py-3 px-4 w-10">Pool</th>
                      <th className="py-3 px-4">Farmer</th>
                      <th className="py-3 px-4">Phone</th>
                      <th className="py-3 px-4">Village</th>
                      <th className="py-3 px-4">Area (ha)</th>
                      <th className="py-3 px-4">Badge</th>
                      <th className="py-3 px-4">Verified Credits</th>
                      <th className="py-3 px-4">Farmer 70% Share</th>
                      <th className="py-3 px-4">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-forest-50 bg-white">
                    {farmersList.length === 0 ? (
                      <tr>
                        <td colSpan="9" className="py-10 px-4 text-center text-agriText-muted">
                          <div className="max-w-md mx-auto space-y-2">
                            <Layers className="w-8 h-8 text-agriText-subtle mx-auto mb-1" />
                            <p className="text-sm font-bold text-carbon-900">No Members Available for Pooling</p>
                            <p className="text-xs text-agriText-muted">
                              Onboard cooperative farmers to assemble aggregated credit lots for institutional corporate procurement.
                            </p>
                            <button
                              type="button"
                              onClick={() => setActiveTab('onboard')}
                              className="mt-1 text-xs text-primary font-bold hover:underline inline-flex items-center gap-1"
                            >
                              <span>Go to Member Onboarding</span>
                              <PlusCircle className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </td>
                      </tr>
                    ) : (
                      farmersList.map(f => {
                        const isSelected = selectedFarmerIds.has(f.id);
                        const credits = parseFloat(f.credits) || 0;
                        const farmerShare = Math.round(credits * poolPricePerCredit * 0.70);
                        const isEligible = f.status === 'VERIFIED' && credits > 0;
                        return (
                          <tr
                            key={f.id}
                            onClick={() => isEligible && toggleSelectFarmer(f.id)}
                            className={`transition-colors cursor-pointer ${
                              isSelected ? 'bg-emerald-50/70 font-semibold' : !isEligible ? 'opacity-60 bg-slate-50 cursor-not-allowed' : 'hover:bg-slate-50'
                            }`}
                          >
                            <td className="py-3 px-4 text-center" onClick={e => e.stopPropagation()}>
                              <input
                                type="checkbox"
                                disabled={!isEligible}
                                checked={isSelected}
                                onChange={() => toggleSelectFarmer(f.id)}
                                className="w-4 h-4 text-emerald-700 rounded border-forest-200 focus:ring-emerald-600"
                              />
                            </td>
                            <td className="py-3 px-4 font-bold text-carbon-900">{f.name}</td>
                            <td className="py-3 px-4 font-mono text-agriText-muted">{f.phone || '—'}</td>
                            <td className="py-3 px-4 text-carbon-800">{f.village || '—'}</td>
                            <td className="py-3 px-4 font-semibold text-carbon-900">{f.area_hectares} ha</td>
                            <td className="py-3 px-4">
                              <VerificationBadge badge={f.badge || 'NONE'} size="sm" />
                            </td>
                            <td className="py-3 px-4 font-bold text-primary">{credits} MT</td>
                            <td className="py-3 px-4 font-mono text-emerald-800">₹{farmerShare.toLocaleString('en-IN')}</td>
                            <td className="py-3 px-4">
                              <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                                f.status === 'VERIFIED' ? 'bg-emerald-50 text-emerald-800 border border-emerald-200' :
                                f.status === 'FLAGGED' ? 'bg-red-50 text-red-700 border border-red-200' :
                                'bg-amber-50 text-amber-800 border border-amber-200'
                              }`}>
                                {f.status}
                              </span>
                            </td>
                          </tr>
                        );
                      })
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {fpoListings.length > 0 && (
              <div className="bg-surface-sage/40 border border-forest-200 rounded-xl p-3 flex justify-between items-center text-xs">
                <span className="text-agriText-muted">Total active cooperative market listings: <strong className="text-carbon-900">{fpoListings.length}</strong></span>
                <button
                  type="button"
                  onClick={() => navigate('/marketplace')}
                  className="text-primary font-bold hover:underline flex items-center gap-1"
                >
                  <span>Explore Marketplace</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
              </div>
            )}
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
                <label className="block text-xs font-bold text-carbon-800 mb-1">Parcel Area (hectares)</label>
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

            {pendingFeedback && (
              <div className={`p-4 rounded-xl border text-xs flex items-center gap-2 font-semibold ${
                pendingFeedback.type === 'success'
                  ? 'bg-surface-sage border-forest-200 text-primary'
                  : 'bg-rose-50 border-rose-200 text-rose-800'
              }`}>
                {pendingFeedback.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0 text-primary" /> : <AlertTriangle className="w-4 h-4 shrink-0 text-rose-700" />}
                <span>{pendingFeedback.message}</span>
              </div>
            )}

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
                        Phone: {p.phone || '—'} | Village: {p.village || '—'} | Farm: {p.farm_name || '—'} | Area: {p.area_hectares} ha
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

                      <button
                        onClick={() => handleRejectPending(p.id)}
                        disabled={auditBusyId === p.id}
                        className="px-3 py-2 bg-red-700 hover:bg-red-800 disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-1.5 shadow-xs"
                      >
                        <X className="w-4 h-4" />
                        <span>Reject</span>
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

            {flaggedFeedback && (
              <div className={`p-4 rounded-xl border text-xs flex items-center gap-2 font-semibold ${
                flaggedFeedback.type === 'success'
                  ? 'bg-surface-sage border-forest-200 text-primary'
                  : 'bg-rose-50 border-rose-200 text-rose-800'
              }`}>
                {flaggedFeedback.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0 text-primary" /> : <AlertTriangle className="w-4 h-4 shrink-0 text-rose-700" />}
                <span>{flaggedFeedback.message}</span>
              </div>
            )}

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
                {flaggedList.map(fl => {
                  const dropValue = fl.drop != null ? Number(fl.drop) : (fl.last_monitor_ndvi && fl.ndvi ? Number((fl.last_monitor_ndvi - fl.ndvi).toFixed(2)) : null);
                  const isThresholdExceeded = dropValue != null && dropValue >= 0.15;
                  return (
                    <div key={fl.id} className="bg-surface-sage/40 border border-forest-200 rounded-xl p-5 space-y-4">
                      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
                        <div>
                          <div className="flex items-center gap-3">
                            <h3 className="text-sm font-bold text-carbon-900">{fl.farmer_name}</h3>
                            <span className="text-xs font-mono text-agriText-subtle">{fl.farm_name || '—'}</span>
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-700 border border-rose-200">
                              FLAGGED (CREDITS BLOCKED)
                            </span>
                          </div>
                          <p className="text-xs text-agriText-muted mt-1">
                            Village: {fl.village || '—'} | Area: {fl.area_hectares} ha | Crop: {fl.crop || 'Mixed'} | Flagged Date: {fl.date}
                          </p>
                        </div>

                        <button
                          type="button"
                          onClick={() => navigate(`/passport/${fl.id}`)}
                          className="text-xs text-primary font-bold hover:underline flex items-center gap-1 shrink-0"
                        >
                          <span>View Farm Passport</span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      {/* Sentinel-2 NDVI Drop & Threshold Verification Card */}
                      <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-4 space-y-2">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <div className="flex items-center gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-700 shrink-0" />
                            <span className="text-xs font-bold text-amber-950 uppercase tracking-wider">
                              Sentinel-2 5-Day Monitoring Alert: Canopy Stress / Drop Review
                            </span>
                          </div>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-amber-200/80 text-amber-900 border border-amber-300">
                            Threshold: Δ NDVI ≥ 0.15
                          </span>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-1 text-xs">
                          <div className="bg-white/80 border border-amber-200 rounded-lg p-2.5">
                            <span className="text-[10px] text-agriText-muted block uppercase">Previous Sentinel-2 NDVI</span>
                            <span className="font-mono font-bold text-carbon-900 text-sm">
                              {fl.last_monitor_ndvi != null ? Number(fl.last_monitor_ndvi).toFixed(2) : '0.72 (Baseline)'}
                            </span>
                          </div>
                          <div className="bg-white/80 border border-amber-200 rounded-lg p-2.5">
                            <span className="text-[10px] text-agriText-muted block uppercase">Current Revisit NDVI</span>
                            <span className="font-mono font-bold text-rose-700 text-sm">
                              {fl.ndvi != null ? Number(fl.ndvi).toFixed(2) : '0.54 (Recent scan)'}
                            </span>
                          </div>
                          <div className="bg-white/80 border border-amber-200 rounded-lg p-2.5">
                            <span className="text-[10px] text-agriText-muted block uppercase">Calculated NDVI Drop</span>
                            <span className="font-mono font-bold text-amber-900 text-sm">
                              {dropValue != null ? `-${dropValue.toFixed(2)}` : '-0.18 (Drop ≥ 0.15)'}
                            </span>
                            {isThresholdExceeded && (
                              <span className="text-[10px] text-rose-700 font-semibold ml-1">Threshold exceeded</span>
                            )}
                          </div>
                        </div>

                        <p className="text-[11px] text-amber-900 leading-relaxed mt-1">
                          <strong>Reason:</strong> {fl.issue}. Per platform governance, credit issuance is paused until an FPO officer conducts ground-truth field inspection.
                        </p>
                      </div>

                      <div className="bg-white border border-forest-200 rounded-xl p-3 space-y-3">
                        <label className="block text-xs font-bold text-carbon-800">
                          Physical Field Inspection & Ground-Truth Notes:
                        </label>
                        <textarea
                          rows={2}
                          placeholder="Enter physical field inspection notes (e.g. verified seasonal harvest vs drought/canopy loss)..."
                          value={auditNotes[fl.id] || ''}
                          onChange={e => {
                            const val = e.target.value;
                            setAuditNotes(prev => ({ ...prev, [fl.id]: val }));
                          }}
                          className="w-full px-3 py-2 bg-surface-sage/30 border border-forest-200 rounded-xl text-xs text-carbon-900 focus:outline-none focus:border-primary"
                        />
                        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
                          <button
                            onClick={() => handleReviewFlagged(fl.id, 'approve')}
                            disabled={auditBusyId === fl.id}
                            className="px-5 py-2.5 bg-primary hover:bg-primary-hover disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 shadow-xs"
                          >
                            {auditBusyId === fl.id ? <Loader2 className="w-4 h-4 animate-spin" /> : <Check className="w-4 h-4" />}
                            <span>Approve & Attest under FPO Badge (₹300/MT)</span>
                          </button>

                          <button
                            onClick={() => handleReviewFlagged(fl.id, 'reject')}
                            disabled={auditBusyId === fl.id}
                            className="px-5 py-2.5 bg-red-700 hover:bg-red-800 disabled:opacity-60 text-white rounded-xl text-xs font-bold transition-all flex items-center justify-center gap-2 shadow-xs"
                          >
                            <X className="w-4 h-4" />
                            <span>Reject & Keep Credits Blocked</span>
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
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
