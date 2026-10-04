import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Layers, ArrowRight, CheckCircle2, Building, Loader2, AlertTriangle } from 'lucide-react';
import BadgePill from '../components/BadgePill';
import { useAuth } from '../context/AuthContext';
import { autoMatchCredits, buyCredits } from '../services/api';

export default function CorporateCreditAnalysis() {
  const navigate = useNavigate();
  const { user } = useAuth();

  // Bulk Auto-Match Engine State
  const [targetVolume, setTargetVolume] = useState(100);
  const [priority, setPriority] = useState('lowest_price'); // nearest, highest_ndvi, lowest_price
  const [showCheckoutModal, setShowCheckoutModal] = useState(false);
  const [paymentDone, setPaymentDone] = useState(false);
  const [isMatching, setIsMatching] = useState(false);
  const [isPaying, setIsPaying] = useState(false);
  const [matchError, setMatchError] = useState('');
  const [payError, setPayError] = useState('');
  const [lastCertId, setLastCertId] = useState(null);

  // Greedy fill matched parcels from the live auto-match API
  const [matchedParcels, setMatchedParcels] = useState([]);
  const [lastProof, setLastProof] = useState(null);

  const runAutoMatch = async () => {
    setIsMatching(true);
    setMatchError('');
    try {
      const data = await autoMatchCredits(targetVolume, priority);
      if (data && data.success) {
        setMatchedParcels(data.matched_farms || []);
      } else {
        setMatchError((data && data.message) || 'Auto-match failed');
        setMatchedParcels([]);
      }
    } catch {
      setMatchError('Auto-match service unreachable. Is the backend running?');
      setMatchedParcels([]);
    } finally {
      setIsMatching(false);
    }
  };

  useEffect(() => { runAutoMatch(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const grossValue = matchedParcels.reduce((acc, item) => acc + (item.credits || 0) * (item.rate || 0), 0);
  const farmerTotal = matchedParcels.reduce((acc, item) => acc + (item.farmer_share_inr || 0), 0);
  const fpoPlatformTotal = grossValue - farmerTotal;

  const handleExecutePayment = async () => {
    setIsPaying(true);
    setPayError('');
    try {
      // Execute real escrow purchases for each allocated parcel
      let lastCert = null;
      let proof = null;
      for (const parcel of matchedParcels) {
        if (!parcel.listing_id || (parcel.credits || 0) <= 0) continue;
        const res = await buyCredits({
          listing_id: parcel.listing_id,
          credits: parcel.credits,
          unit_price: parcel.rate,
          buyer_name: user?.name || 'Corporate Buyer',
        });
        if (res && res.certificate_id) {
          lastCert = res.certificate_id;
          proof = res;
        } else if (res && res.message) {
          console.warn(`Purchase skipped for ${parcel.farm}: ${res.message}`);
        }
      }
      if (lastCert) {
        setLastCertId(lastCert);
        setLastProof(proof);
        setPaymentDone(true);
      } else {
        setPayError('No purchases completed — the matched parcels may no longer be available. Re-run the auto-match.');
        setIsPaying(false);
      }
    } catch {
      setPayError('Payment execution failed. Please try again.');
      setIsPaying(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Header */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex justify-between items-center">
          <div>
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full inline-block mb-1">
              Corporate Bulk Procurement & Checkout
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Parcel Diligence & Auto-Match Engine</h1>
            <p className="text-xs text-slate-500 mt-0.5">Greedy fill allocation matching enterprise volume targets with verified Telangana parcels.</p>
          </div>
          <Sparkles className="w-10 h-10 text-emerald-700" />
        </div>

        {/* Bulk Procurement Matrix */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-6">
          <h2 className="text-base font-bold text-slate-900">Bulk Auto-Match Configuration</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Target Volume Slider */}
            <div className="space-y-2">
              <div className="flex justify-between items-center text-xs font-bold">
                <label className="text-slate-700 uppercase tracking-wider">Target Offset Volume (MT CO2e)</label>
                <span className="text-emerald-800 font-mono text-base">{targetVolume} MT</span>
              </div>
              <input
                type="range"
                min="50"
                max="1000"
                step="25"
                value={targetVolume}
                onChange={e => setTargetVolume(parseFloat(e.target.value))}
                className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-700"
              />
              <p className="text-[10px] text-slate-500">Range: 50 to 1,000 Metric Tonnes</p>
            </div>

            {/* Preference Priorities Selector */}
            <div>
              <label className="block text-xs font-bold text-slate-700 uppercase tracking-wider mb-2">
                Allocation Preference Priority
              </label>
              <select
                value={priority}
                onChange={e => setPriority(e.target.value)}
                className="w-full px-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-semibold text-slate-900 focus:outline-none"
              >
                <option value="lowest_price">Lowest Unit Price (Greedy Cost Minimization)</option>
                <option value="highest_ndvi">Highest Sentinel-2 NDVI Biomass Density</option>
                <option value="nearest">Nearest Spatial Centroid (Telangana Mandals)</option>
              </select>
              <button
                onClick={runAutoMatch}
                disabled={isMatching}
                className="mt-3 w-full py-2.5 bg-[#0C2A18] hover:bg-[#15803D] disabled:opacity-60 text-white rounded-lg text-xs font-bold transition-all flex items-center justify-center gap-2"
              >
                {isMatching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Sparkles className="w-4 h-4 text-emerald-300" />}
                <span>{isMatching ? 'Matching Live Listings…' : 'Run Auto-Match on Live Marketplace'}</span>
              </button>
            </div>
          </div>

          {matchError && (
            <p className="text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 shrink-0" /> {matchError}
            </p>
          )}

          {/* Matched Farm Parcels Summary Table */}
          <div className="space-y-3 pt-4 border-t border-slate-100">
            <h3 className="text-xs font-bold text-slate-900 uppercase tracking-wider">Real-Time Parcel Allocation Table</h3>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-slate-200 bg-slate-50 text-slate-600 font-semibold uppercase tracking-wider">
                    <th className="py-2.5 px-4">Matched Farm Parcel</th>
                    <th className="py-2.5 px-4">Farmer</th>
                    <th className="py-2.5 px-4">Location</th>
                    <th className="py-2.5 px-4">Badge</th>
                    <th className="py-2.5 px-4">Allocated Volume</th>
                    <th className="py-2.5 px-4">Unit Rate</th>
                    <th className="py-2.5 px-4">Farmer Keeps (70%)</th>
                    <th className="py-2.5 px-4">Subtotal</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 font-medium">
                  {matchedParcels.length === 0 ? (
                    <tr>
                      <td colSpan="8" className="py-6 px-4 text-center text-slate-500">
                        {isMatching ? 'Matching live listings…' : 'No active listings matched this target. Lower the volume or check back later.'}
                      </td>
                    </tr>
                  ) : (
                    matchedParcels.map((item, idx) => (
                      <tr key={item.listing_id || idx} className="hover:bg-slate-50 transition-colors">
                        <td className="py-2.5 px-4 font-bold text-slate-900">{item.farm}</td>
                        <td className="py-2.5 px-4 text-slate-700">{item.farmer}</td>
                        <td className="py-2.5 px-4 font-mono text-slate-600">{item.survey || '—'}</td>
                        <td className="py-2.5 px-4">
                          <BadgePill badge={item.badge} size="sm" />
                        </td>
                        <td className="py-2.5 px-4 font-bold text-emerald-800">{item.credits} MT</td>
                        <td className="py-2.5 px-4 text-slate-900">INR {item.rate}</td>
                        <td className="py-2.5 px-4 text-emerald-700 font-semibold">
                          INR {Number(item.farmer_share_inr || 0).toLocaleString('en-IN')}
                        </td>
                        <td className="py-2.5 px-4 font-extrabold text-slate-900">
                          INR {((item.credits || 0) * (item.rate || 0)).toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Escrow Financial Ledger Breakdown */}
        <div className="bg-[#0C2A18] text-white border border-emerald-900 shadow-sm rounded-xl p-6 space-y-4">
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <Layers className="w-5 h-5 text-emerald-400" />
            <span>Escrow Financial Ledger Breakdown</span>
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-2 border-t border-emerald-800/80">
            <div>
              <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Total Carbon Credit Value</p>
              <p className="text-2xl font-extrabold font-manrope text-white mt-1">
                INR {grossValue.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div>
              <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">Farmer Payouts (70% floor)</p>
              <p className="text-2xl font-extrabold font-manrope text-emerald-400 mt-1">
                INR {farmerTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </p>
            </div>

            <div>
              <p className="text-xs font-semibold text-slate-300 uppercase tracking-wider">FPO + Platform Share</p>
              <p className="text-2xl font-extrabold font-manrope text-amber-300 mt-1">
                INR {fpoPlatformTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </p>
            </div>
          </div>
          <p className="text-[11px] text-slate-300">
            Every farmer keeps a guaranteed 70% of their parcel value; the FPO earns 5% only where its verification
            involvement is proven — the remainder funds platform operations and satellite monitoring.
          </p>

          <button
            onClick={() => setShowCheckoutModal(true)}
            disabled={matchedParcels.length === 0 || isMatching}
            className="w-full py-3 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow-md flex items-center justify-center gap-2 mt-4"
          >
            <span>Proceed to Payment Gateway Simulation</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>

        {/* Payment Gateway Modal */}
        {showCheckoutModal && (
          <div className="fixed inset-0 z-50 bg-[#0C2A18]/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white border border-slate-200 shadow-xl rounded-xl p-6 max-w-md w-full space-y-4">
              <div className="flex justify-between items-center border-b border-slate-100 pb-3">
                <div className="flex items-center gap-2">
                  <Building className="w-5 h-5 text-emerald-700" />
                  <h3 className="text-sm font-bold text-slate-900">Corporate Payment Gateway (UPI / RTGS)</h3>
                </div>
              </div>

              {paymentDone ? (
                <div className="space-y-3">
                  <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 p-4 rounded-xl text-center space-y-1">
                    <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto" />
                    <p className="font-bold text-sm">Escrow settlement executed — credits retired</p>
                    <p className="text-xs text-slate-600 font-mono">Certificate: {lastCertId}</p>
                    {lastProof?.escrow_ref && (
                      <p className="text-[11px] text-slate-500 font-mono">Escrow {lastProof.escrow_ref}</p>
                    )}
                  </div>

                  {lastProof?.split && (
                    <div className="border border-slate-200 rounded-lg p-3 space-y-1 text-xs">
                      <p className="font-bold text-slate-700 text-[11px] uppercase tracking-wide">
                        Payout split executed ({lastProof.split.model})
                      </p>
                      {lastProof.split.lines.map(line => (
                        <div key={line.recipient} className="flex justify-between">
                          <span className="text-slate-600 font-semibold">{line.recipient} · {line.share_pct}%</span>
                          <span className="font-mono font-bold text-slate-900">INR {Number(line.amount_inr).toLocaleString('en-IN')}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {lastProof?.batch_hash && (
                    <div className="bg-slate-50 border border-slate-200 rounded-lg p-3">
                      <p className="text-[11px] font-bold text-slate-700 uppercase tracking-wide">Tamper-evident record</p>
                      <p className="font-mono text-[10px] text-slate-600 break-all mt-0.5">sha256:{lastProof.batch_hash}</p>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => { setShowCheckoutModal(false); setPaymentDone(false); runAutoMatch(); }}
                      className="flex-1 py-2.5 bg-slate-100 text-slate-700 rounded-lg text-xs font-bold hover:bg-slate-200"
                    >
                      Close
                    </button>
                    <button
                      type="button"
                      onClick={() => navigate(`/buyer/certificates/${lastCertId}`)}
                      className="flex-1 py-2.5 bg-emerald-700 text-white rounded-lg text-xs font-bold hover:bg-emerald-600 flex items-center justify-center gap-1"
                    >
                      <span>View Certificate</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1 text-xs">
                    <p className="font-semibold text-slate-700">Gross Procurement Amount: <strong className="text-slate-900">INR {grossValue.toLocaleString()}</strong></p>
                    <p className="text-[11px] text-slate-500">
                      Executes {matchedParcels.length} real escrow purchase{matchedParcels.length === 1 ? '' : 's'} against live listings.
                    </p>
                  </div>

                  {payError && (
                    <p className="text-xs text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg">{payError}</p>
                  )}

                  <div className="flex gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowCheckoutModal(false)}
                      className="flex-1 py-2.5 bg-slate-100 text-slate-700 rounded-lg text-xs font-bold hover:bg-slate-200"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleExecutePayment}
                      disabled={isPaying}
                      className="flex-1 py-2.5 bg-emerald-700 text-white rounded-lg text-xs font-bold hover:bg-emerald-600 disabled:opacity-60 flex items-center justify-center gap-1"
                    >
                      {isPaying ? <Loader2 className="w-4 h-4 animate-spin" /> : <span>Execute Escrow Purchase</span>}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
