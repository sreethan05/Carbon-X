import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Sparkles, Layers, ArrowRight, ArrowLeft, CheckCircle2, Building, Loader2, AlertTriangle, ExternalLink } from 'lucide-react';
import BadgePill from '../components/BadgePill';
import { useAuth } from '../context/AuthContext';
import { autoMatchCredits, createCheckout } from '../services/api';
import { loadRazorpay } from '../services/razorpay';

function openRazorpay(checkout, parcel, buyerName) {
  return new Promise((resolve, reject) => {
    const gateway = new window.Razorpay({
      key: checkout.key_id,
      order_id: checkout.order_id,
      name: 'CarbonX Market',
      description: `Bulk purchase: ${parcel.farm} (${parcel.credits} MT)`,
      handler: resolve,
      modal: {
        ondismiss: () => reject(new Error('The payment window closed before confirmation.')),
      },
      prefill: { name: buyerName },
      theme: { color: '#0C2A18' },
    });
    gateway.on('payment.failed', ({ error } = {}) => {
      reject(new Error(error?.description || error?.reason || 'The payment provider reported a failure.'));
    });
    gateway.open();
  });
}

function sumRecordedSplit(settled) {
  const fields = [
    ['Farmers', 'farmer_amount_inr'],
    ['FPOs', 'fpo_amount_inr'],
    ['Platform & monitoring', 'platform_amount_inr'],
  ];
  if (!settled.length || !settled.every((receipt) =>
    fields.every(([, field]) => Number.isFinite(receipt.split?.[field]))
  )) return [];
  return fields.map(([recipient, field]) => ({
    recipient,
    amount: settled.reduce((paise, receipt) => paise + Math.round(receipt.split[field] * 100), 0) / 100,
  }));
}

export default function CorporateCreditAnalysis() {
  const navigate = useNavigate();
  const { user } = useAuth();

  // Bulk Auto-Match Engine State
  const [targetVolume, setTargetVolume] = useState(100);
  const [priority, setPriority] = useState('lowest_price'); // nearest, highest_ndvi, lowest_price
  const [checkoutParcels, setCheckoutParcels] = useState(null);
  const [checkoutOutcome, setCheckoutOutcome] = useState(null);
  const [isMatching, setIsMatching] = useState(false);
  const [matchedSettings, setMatchedSettings] = useState(null);
  const [isPaying, setIsPaying] = useState(false);
  const [matchError, setMatchError] = useState('');
  const checkoutInFlight = useRef(false);
  const matchRequest = useRef(0);

  // Greedy fill matched parcels from the live auto-match API
  const [matchedParcels, setMatchedParcels] = useState([]);

  const runAutoMatch = async () => {
    const request = ++matchRequest.current;
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
      if (request !== matchRequest.current) return;
      if (data && data.success) {
        setMatchedParcels(data.matched_farms || []);
        setMatchedSettings({ targetVolume, priority });
      } else {
        setMatchError((data && data.message) || 'Auto-match failed');
        setMatchedParcels([]);
      }
    } catch {
      if (request !== matchRequest.current) return;
      setMatchError('Auto-match service unreachable. Is the backend running?');
      setMatchedParcels([]);
    } finally {
      if (request === matchRequest.current) setIsMatching(false);
    }
  };

  // Re-run auto match with a debounce when targetVolume or priority change
  useEffect(() => {
    matchRequest.current++;
    const timer = setTimeout(() => {
      runAutoMatch();
    }, 300);
    return () => clearTimeout(timer);
  }, [targetVolume, priority]); // eslint-disable-line react-hooks/exhaustive-deps

  const grossValue = matchedParcels.reduce((acc, item) => acc + (parseFloat(item.credits) || 0) * (parseFloat(item.rate) || 0), 0);
  const farmerTotal = matchedParcels.reduce((acc, item) => acc + (parseFloat(item.farmer_share_inr) || 0), 0);
  const fpoPlatformTotal = grossValue - farmerTotal;
  const totalAllocatedCredits = matchedParcels.reduce((acc, item) => acc + (parseFloat(item.credits) || 0), 0);
  const hasCurrentMatch = matchedSettings?.targetVolume === targetVolume && matchedSettings?.priority === priority;
  const checkoutValue = (checkoutParcels || []).reduce((acc, item) => acc + (Number(item.credits) || 0) * (Number(item.rate) || 0), 0);
  const needsPaymentReview = Boolean(checkoutOutcome?.pending.length || checkoutOutcome?.unconfirmed);
  const recordedSplit = sumRecordedSplit(checkoutOutcome?.settled || []);

  const openCheckout = () => {
    if (needsPaymentReview) {
      setCheckoutParcels([]);
      return;
    }
    setCheckoutOutcome(null);
    setCheckoutParcels(matchedParcels);
  };

  const closeCheckout = () => {
    setCheckoutParcels(null);
    if (checkoutOutcome && !needsPaymentReview) runAutoMatch();
  };

  const handleExecutePayment = async () => {
    if (checkoutInFlight.current || checkoutOutcome || !checkoutParcels?.length) return;
    checkoutInFlight.current = true;
    setIsPaying(true);
    const outcome = { settled: [], pending: [], issue: '', unconfirmed: false, unattempted: checkoutParcels.length };
    const buyerName = user?.name || 'Corporate Buyer';
    for (const parcel of checkoutParcels) {
      outcome.unattempted -= 1;
      let orderId;
      let paymentWindowOpened = false;
      let awaitingCheckoutResponse = false;
      const parcelName = parcel.farm || parcel.listing_id || 'Matched parcel';
      try {
        const credits = Number(parcel.credits);
        if (!parcel.listing_id || !Number.isFinite(credits) || credits <= 0) {
          throw new Error('The matched listing or volume is invalid.');
        }
        awaitingCheckoutResponse = true;
        const result = await createCheckout({
          listing_id: parcel.listing_id,
          credits,
          buyer_name: buyerName,
        });
        awaitingCheckoutResponse = false;

        if (!result?.success) {
          outcome.unconfirmed = !result?.status || result.status >= 500 || Boolean(result.requires_reconciliation);
          throw new Error(result?.message || 'The checkout request failed.');
        }

        if (result.payment_required) {
          orderId = result.checkout?.order_id;
          if (!orderId || !result.checkout?.key_id) {
            throw new Error('The checkout response is missing payment order details.');
          }
          await loadRazorpay();
          paymentWindowOpened = true;
          const payment = await openRazorpay(result.checkout, parcel, buyerName);
          outcome.pending.push({
            orderId,
            parcelName,
            paymentId: payment?.razorpay_payment_id,
          });
          continue;
        }

        const settlement = result.settlement;
        if (!settlement?.success || !settlement.certificate_id) {
          outcome.unconfirmed = true;
          throw new Error('The server did not return a settlement receipt.');
        }
        outcome.settled.push({ ...settlement, simulated: result.simulated === true });
      } catch (error) {
        outcome.unconfirmed ||= paymentWindowOpened || awaitingCheckoutResponse;
        outcome.issue = `${parcelName}: ${error.message}${orderId ? ` Order ${orderId}.` : ''}`;
        break;
      }
    }
    setCheckoutOutcome(outcome);
    setIsPaying(false);
    checkoutInFlight.current = false;
  };

  return (
    <div className="product-page min-h-screen font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Header */}
        <div className="field-page-head bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
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
                <label htmlFor="bulk-target-volume" className="text-slate-700 uppercase tracking-wider">Target Offset Volume (MT CO2e)</label>
                <div className="flex items-center gap-1.5">
                  <input
                    id="bulk-target-volume"
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
                aria-label="Target offset volume slider"
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
            onClick={openCheckout}
            disabled={!needsPaymentReview && (!hasCurrentMatch || matchedParcels.length === 0 || isMatching)}
            className="w-full py-3 bg-emerald-700 hover:bg-emerald-800 disabled:opacity-50 text-white rounded-xl text-xs font-bold flex items-center justify-center gap-2 mt-4"
          >
            {needsPaymentReview ? 'Review payment status' : 'Proceed to Escrow Checkout'}
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>

        {checkoutParcels && (
          <div className="fixed inset-0 z-50 bg-[#0C2A18]/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div role="dialog" aria-labelledby="bulk-checkout-title" className="bg-white border border-slate-200 shadow-xl rounded-xl p-6 max-w-md max-h-full overflow-y-auto w-full space-y-4">
              <h3 id="bulk-checkout-title" className="text-base font-bold flex items-center gap-2">
                <Building className="w-5 h-5 text-emerald-700" /> Bulk escrow checkout
              </h3>

              {checkoutOutcome ? (
                <div className="space-y-3 text-xs">
                  {checkoutOutcome.settled.length > 0 && (
                    <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 space-y-2">
                      <p className="font-bold flex items-center gap-2 text-emerald-900">
                        <CheckCircle2 className="w-4 h-4" />
                        {checkoutOutcome.settled.length} recorded settlement(s)
                      </p>
                      {checkoutOutcome.settled.every((receipt) => receipt.simulated) && (
                        <p>Simulated escrow. No money moved.</p>
                      )}
                      {checkoutOutcome.settled.map((receipt) => (
                        <button
                          key={receipt.certificate_id}
                          type="button"
                          onClick={() => navigate(`/buyer/certificates/${receipt.certificate_id}`)}
                          className="flex gap-2 items-center text-emerald-900 font-mono underline break-all"
                        >
                          {receipt.certificate_id} <ExternalLink className="w-3 h-3 shrink-0" />
                        </button>
                      ))}
                      {recordedSplit.length > 0 && (
                        <dl className="space-y-1 border-t border-emerald-200 pt-2">
                          {recordedSplit.map(({ recipient, amount }) => (
                            <div key={recipient} className="flex justify-between gap-2">
                              <dt>{recipient}</dt>
                              <dd>₹{amount.toLocaleString('en-IN')}</dd>
                            </div>
                          ))}
                        </dl>
                      )}
                    </div>
                  )}
                  {checkoutOutcome.pending.length > 0 && (
                    <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 space-y-2">
                      <p className="font-bold">Payment authorized. Settlement pending.</p>
                      {checkoutOutcome.pending.map(({ orderId, parcelName, paymentId }) => (
                        <p key={orderId} className="break-words">{parcelName} · {paymentId || orderId}</p>
                      ))}
                      <p>Certificates appear after the provider confirms settlement.</p>
                    </div>
                  )}
                  {checkoutOutcome.issue && (
                    <p role="alert" className="bg-rose-50 border border-rose-200 rounded-xl p-3 text-rose-900 flex gap-2">
                      <AlertTriangle className="w-4 h-4 shrink-0" /> {checkoutOutcome.issue}
                    </p>
                  )}
                  {checkoutOutcome.unattempted > 0 && <p>Parcels left unattempted: {checkoutOutcome.unattempted}</p>}
                  {needsPaymentReview && (
                    <button type="button" onClick={() => navigate('/corporate/dashboard')} className="text-emerald-800 underline font-bold">
                      Check your certificates and payment status before retrying
                    </button>
                  )}
                  <button type="button" onClick={closeCheckout} className="w-full py-2.5 bg-slate-100 text-slate-700 rounded-lg font-bold">
                    Close
                  </button>
                </div>
              ) : (
                <div className="space-y-4 text-xs">
                  <div className="bg-slate-50 border border-slate-200 rounded-lg p-3 space-y-1">
                    <p className="font-semibold">Estimated checkout value: ₹{checkoutValue.toLocaleString('en-IN')}</p>
                    <p>Review and submit checkout for {checkoutParcels.length} matched parcel(s).</p>
                  </div>
                  <div className="flex gap-2">
                    <button type="button" onClick={closeCheckout} disabled={isPaying} className="flex-1 py-2.5 bg-slate-100 rounded-lg font-bold">
                      Cancel
                    </button>
                    <button type="button" onClick={handleExecutePayment} disabled={isPaying} className="flex-1 py-2.5 bg-emerald-700 text-white rounded-lg font-bold flex items-center justify-center gap-1">
                      {isPaying && <Loader2 className="w-4 h-4 animate-spin" />}
                      {isPaying ? 'Processing…' : 'Submit escrow purchases'}
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
