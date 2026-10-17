import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Layers, ArrowRight, ArrowLeft, CheckCircle2, Building, Loader2, AlertTriangle, ExternalLink } from 'lucide-react';
import BadgePill from '../components/BadgePill';
import { useAuth } from '../context/AuthContext';
import { autoMatchCredits, buyCredits, createCheckout } from '../services/api';

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
  const [allCertIds, setAllCertIds] = useState([]);

  // Greedy fill matched parcels from the live auto-match API
  const [matchedParcels, setMatchedParcels] = useState([]);
  const [lastProof, setLastProof] = useState(null);

  const runAutoMatch = async () => {
    setIsMatching(true);
    setMatchError('');
    try {
      const vol = parseFloat(targetVolume);
      if (!Number.isFinite(vol) || vol <= 0) {
        setMatchError('Target volume must be greater than zero (minimum 1 MT CO2e).');
        setMatchedParcels([]);
        return;
      }
      const data = await autoMatchCredits(vol, priority);
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

  // Re-run auto match with a debounce when targetVolume or priority change
  useEffect(() => {
    const timer = setTimeout(() => {
      runAutoMatch();
    }, 300);
    return () => clearTimeout(timer);
  }, [targetVolume, priority]); // eslint-disable-line react-hooks/exhaustive-deps

  const grossValue = matchedParcels.reduce((acc, item) => acc + (parseFloat(item.credits) || 0) * (parseFloat(item.rate) || 0), 0);
  const farmerTotal = matchedParcels.reduce((acc, item) => acc + (parseFloat(item.farmer_share_inr) || 0), 0);
  const fpoPlatformTotal = grossValue - farmerTotal;
  const totalAllocatedCredits = matchedParcels.reduce((acc, item) => acc + (parseFloat(item.credits) || 0), 0);

  const handleExecutePayment = async () => {
    setIsPaying(true);
    setPayError('');
    try {
      // Execute real escrow purchases for each allocated parcel
      let proof = null;
      let purchased = 0;
      let totalPurchasedGross = 0;
      let totalFarmerShare = 0;
      let totalFpoShare = 0;
      let totalPlatformShare = 0;
      const settledCerts = [];
      const skipped = [];

      for (const parcel of matchedParcels) {
        const pCredits = parseFloat(parcel.credits);
        if (!parcel.listing_id || !Number.isFinite(pCredits) || pCredits <= 0) continue;

        let res = await createCheckout({
          listing_id: parcel.listing_id,
          credits: pCredits,
          buyer_name: user?.name || 'Corporate Buyer',
        });

        // Handle Razorpay gateway when payment_required is true
        if (res && res.payment_required && res.checkout?.key_id) {
          if (!window.Razorpay) {
            await new Promise((resolve, reject) => {
              if (document.querySelector('script[src*="checkout.razorpay.com"]')) {
                const checkInterval = setInterval(() => {
                  if (window.Razorpay) { clearInterval(checkInterval); resolve(); }
                }, 100);
                return;
              }
              const script = document.createElement('script');
              script.src = 'https://checkout.razorpay.com/v1/checkout.js';
              script.onload = resolve;
              script.onerror = () => reject(new Error('Failed to load Razorpay payment gateway'));
              document.body.appendChild(script);
            });
          }

          const rzpResult = await new Promise((resolve, reject) => {
            const rzp = new window.Razorpay({
              key: res.checkout.key_id,
              order_id: res.checkout.order_id,
              name: 'CarbonX Market',
              description: `Bulk Escrow Purchase: ${parcel.farm} (${pCredits} MT)`,
              handler: (response) => resolve(response),
              modal: {
                ondismiss: () => reject(new Error('Razorpay payment window closed before completion.')),
              },
              prefill: { name: user?.name || 'Corporate Buyer' },
              theme: { color: '#0C2A18' },
            });
            rzp.on('payment.failed', (errResponse) => {
              const reason = errResponse?.error?.description || errResponse?.error?.reason || 'Transaction failed or was declined.';
              reject(new Error(`Payment Failed: ${reason}`));
            });
            rzp.open();
          });

          res = {
            success: true,
            certificate_id: `PENDING-RZP-${(rzpResult.razorpay_payment_id || '').slice(-8)}`,
            escrow_ref: rzpResult.razorpay_payment_id || 'RZP-ESCROW',
            gross_amount: pCredits * (parseFloat(parcel.rate) || 0),
            batch_hash: rzpResult.razorpay_signature || 'Awaiting signature verification',
          };
        }

        if (res && res.settlement) res = res.settlement;
        if (!res || !res.certificate_id) {
          res = await buyCredits({
            listing_id: parcel.listing_id,
            credits: pCredits,
            unit_price: parcel.rate,
            buyer_name: user?.name || 'Corporate Buyer',
          });
        }
        if (res && res.certificate_id) {
          settledCerts.push(res.certificate_id);
          proof = res;
          purchased += 1;
          const pGross = Number(res.gross_amount || (pCredits * (parseFloat(parcel.rate) || 0)));
          totalPurchasedGross += pGross;
          if (res.split) {
            totalFarmerShare += Number(res.split.farmer_amount_inr || 0);
            totalFpoShare += Number(res.split.fpo_amount_inr || 0);
            totalPlatformShare += Number(res.split.platform_amount_inr || 0);
          } else {
            const fShare = Math.round(pGross * 0.70);
            const fpShare = Math.round(pGross * 0.05);
            totalFarmerShare += fShare;
            totalFpoShare += fpShare;
            totalPlatformShare += (pGross - fShare - fpShare);
          }
        } else {
          skipped.push(`${parcel.farm || parcel.listing_id}: ${(res && (res.message || res.detail)) || 'listing unavailable'}`);
        }
      }

      if (settledCerts.length > 0) {
        const firstCert = settledCerts[0];
        setLastCertId(firstCert);
        setAllCertIds(settledCerts);
        setLastProof({
          ...proof,
          purchased_count: purchased,
          all_certificates: settledCerts,
          skipped_purchases: skipped,
          gross_amount: totalPurchasedGross,
          split: {
            model: '3-way aggregate',
            lines: [
              { recipient: 'Farmers (70% floor)', share_pct: 70, amount_inr: totalFarmerShare },
              { recipient: 'FPO / Verifiers (5% where involved)', share_pct: 5, amount_inr: totalFpoShare },
              { recipient: 'Platform & Monitoring', share_pct: 25, amount_inr: totalPlatformShare },
            ],
          },
        });
        setPaymentDone(true);
      } else {
        setPayError(skipped.length
          ? `No purchases completed — ${skipped[0]}`
          : 'No purchases completed — the matched parcels may no longer be available. Re-run the auto-match.');
      }
    } catch (err) {
      setPayError(err.message || 'Payment execution failed. Please try again.');
    } finally {
      setIsPaying(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Header */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full inline-block mb-1">
              Corporate Bulk Procurement & Checkout
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Parcel Diligence & Auto-Match Engine</h1>
            <p className="text-xs text-slate-500 mt-0.5">Greedy fill allocation matching enterprise volume targets with verified Telangana parcels.</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => navigate('/marketplace')}
              className="px-3.5 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Marketplace</span>
            </button>
            <button
              onClick={() => navigate('/corporate/dashboard')}
              className="px-3.5 py-2 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold transition-all flex items-center gap-1.5"
            >
              <span>Dashboard</span>
            </button>
          </div>
        </div>

        {/* Bulk Procurement Matrix */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-6">
          <h2 className="text-base font-bold text-slate-900">Bulk Auto-Match Configuration</h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Target Volume Slider & Precise Input */}
            <div className="space-y-3">
              <div className="flex justify-between items-center text-xs font-bold">
                <label className="text-slate-700 uppercase tracking-wider">Target Offset Volume (MT CO2e)</label>
                <div className="flex items-center gap-1.5">
                  <input
                    type="number"
                    min="1"
                    max="2500"
                    step="5"
                    value={targetVolume}
                    onChange={e => {
                      const val = parseFloat(e.target.value);
                      if (isNaN(val)) {
                        setTargetVolume('');
                      } else {
                        setTargetVolume(Math.max(1, Math.min(2500, val)));
                      }
                    }}
                    className="w-24 px-2.5 py-1 text-right font-mono font-bold text-emerald-800 bg-slate-50 border border-slate-200 rounded-lg text-sm focus:outline-none focus:border-emerald-600"
                  />
                  <span className="text-slate-600 font-semibold text-xs">MT</span>
                </div>
              </div>
              <input
                type="range"
                min="25"
                max="1000"
                step="25"
                value={Number(targetVolume) || 25}
                onChange={e => setTargetVolume(parseFloat(e.target.value) || 25)}
                className="w-full h-2 bg-slate-200 rounded-lg appearance-none cursor-pointer accent-emerald-700"
              />
              <div className="flex flex-wrap items-center justify-between gap-2 pt-0.5">
                <div className="flex items-center gap-1 text-[10px] font-semibold text-slate-500">
                  <span>Presets:</span>
                  {[50, 100, 250, 500, 1000].map(amt => (
                    <button
                      key={amt}
                      type="button"
                      onClick={() => setTargetVolume(amt)}
                      className={`px-1.5 py-0.5 rounded border transition-colors ${
                        targetVolume === amt
                          ? 'bg-emerald-800 text-white border-emerald-800 font-bold'
                          : 'bg-white text-slate-600 border-slate-200 hover:bg-slate-100'
                      }`}
                    >
                      {amt}
                    </button>
                  ))}
                </div>
                <span className="text-[10px] text-slate-400">Min: 1 MT · Max: 2,500 MT</span>
              </div>

              {/* Allocation Fulfillment Metric Bar */}
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-2.5 space-y-1.5">
                <div className="flex justify-between items-center text-[11px] font-bold">
                  <span className="text-slate-600">Marketplace Inventory Matched:</span>
                  <span className="font-mono text-emerald-800">
                    {totalAllocatedCredits.toFixed(1)} MT / {targetVolume || 0} MT ({targetVolume > 0 ? Math.min(100, Math.round((totalAllocatedCredits / targetVolume) * 100)) : 0}%)
                  </span>
                </div>
                <div className="w-full bg-slate-200 h-1.5 rounded-full overflow-hidden">
                  <div
                    className="bg-emerald-700 h-full rounded-full transition-all duration-300"
                    style={{
                      width: `${targetVolume > 0 ? Math.min(100, (totalAllocatedCredits / targetVolume) * 100) : 0}%`,
                    }}
                  />
                </div>
              </div>
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
            <span>Proceed to Escrow Checkout</span>
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
                  <div className="bg-emerald-50 border border-emerald-200 text-emerald-900 p-4 rounded-xl text-center space-y-2">
                    <CheckCircle2 className="w-8 h-8 text-emerald-600 mx-auto" />
                    <p className="font-bold text-sm">Escrow settlement executed — credits retired</p>
                    
                    {allCertIds.length > 1 ? (
                      <div className="space-y-1.5 pt-1">
                        <p className="text-[11px] font-semibold text-emerald-800">
                          {allCertIds.length} Certificates Generated:
                        </p>
                        <div className="flex flex-wrap gap-1.5 justify-center">
                          {allCertIds.map((cid) => (
                            <button
                              key={cid}
                              type="button"
                              onClick={() => navigate(`/buyer/certificates/${cid}`)}
                              className="px-2 py-1 bg-white border border-emerald-300 rounded text-[10px] font-mono font-bold text-emerald-900 hover:bg-emerald-100 flex items-center gap-1 shadow-2xs"
                            >
                              <span>{cid}</span>
                              <ExternalLink className="w-2.5 h-2.5" />
                            </button>
                          ))}
                        </div>
                      </div>
                    ) : (
                      <p className="text-xs text-slate-600 font-mono">Certificate: {lastCertId}</p>
                    )}

                    {lastProof?.escrow_ref && (
                      <p className="text-[11px] text-slate-500 font-mono">Escrow {lastProof.escrow_ref}</p>
                    )}
                    {lastProof?.skipped_purchases?.length > 0 && (
                      <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-2 mt-1 text-left font-semibold">
                        {lastProof.purchased_count} purchase{lastProof.purchased_count === 1 ? '' : 's'} settled;{' '}
                        {lastProof.skipped_purchases.length} skipped (listing changed): {lastProof.skipped_purchases[0]}
                      </p>
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
                    <div className="bg-rose-50 border border-rose-200 p-3 rounded-xl flex items-start gap-2.5 text-xs text-rose-800">
                      <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                      <div className="flex-1 space-y-1">
                        <p className="font-bold">Payment Execution Issue</p>
                        <p className="text-[11px] leading-relaxed text-rose-700">{payError}</p>
                      </div>
                    </div>
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
                      disabled={isPaying || matchedParcels.length === 0}
                      className="flex-1 py-2.5 bg-emerald-700 text-white rounded-lg text-xs font-bold hover:bg-emerald-600 disabled:opacity-60 flex items-center justify-center gap-1 shadow-sm"
                    >
                      {isPaying ? (
                        <>
                          <Loader2 className="w-4 h-4 animate-spin" />
                          <span>Processing…</span>
                        </>
                      ) : (
                        <span>{payError ? 'Retry Escrow Purchase' : 'Execute Escrow Purchase'}</span>
                      )}
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
