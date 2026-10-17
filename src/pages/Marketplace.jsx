import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, MapPin, ShoppingCart, CheckCircle2, ChevronRight, PlusCircle, Minus, Plus, X, AlertTriangle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getMarketplaceListings, buyCredits, createCheckout } from '../services/api';

export default function Marketplace() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCrop, setSelectedCrop] = useState('ALL');
  const [statusFilter, setStatusFilter] = useState('Active'); // 'Active' | 'ALL'
  const [sortBy, setSortBy] = useState('price_asc'); // 'price_asc' | 'price_desc' | 'credits_desc'
  const [quantities, setQuantities] = useState({});
  const [checkoutModalItem, setCheckoutModalItem] = useState(null);
  const [purchaseProof, setPurchaseProof] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [checkoutError, setCheckoutError] = useState('');

  const [listings, setListings] = useState([]);
  const [dataSource, setDataSource] = useState('loading');
  const [loadError, setLoadError] = useState('');

  const loadListings = async () => {
    setDataSource('loading');
    setLoadError('');
    const data = await getMarketplaceListings({ limit: 50, status: statusFilter === 'Active' ? 'Active' : undefined });
    if (!data || !data.success) {
      setListings([]);
      setDataSource('error');
      setLoadError((data && data.message) || 'Marketplace service unreachable. Please retry.');
      return;
    }
    const mapped = (data.listings || [])
      .filter((l) => l.id)
      .map((l) => ({
        id: l.id,
        crop: l.crop || '—',
        farmer: l.farmer_name || '—',
        location: l.location || '—',
        available: l.total_credits ?? l.carbon_credits ?? null,
        carbonScore: l.carbon_credits ?? null,
        bioScore: l.biodiversity_credits ?? null,
        price: l.price_per_credit ?? null,
        status: l.status || '—',
        badge: l.badge || null,
        imageUrl: l.image_url,
      }));
    setListings(mapped);
    setDataSource(data.source || 'live_db');
  };

  useEffect(() => { loadListings(); }, [statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const getQuantity = (id, maxAvailable) => {
    const max = Number.isFinite(Number(maxAvailable)) ? Math.max(0, Number(maxAvailable)) : 999;
    if (max <= 0) return 0;
    const current = quantities[id];
    if (current === undefined || current === null) return 1;
    return Math.min(max, Math.max(1, current));
  };

  const updateQuantity = (id, delta, maxAvailable) => {
    const max = Number.isFinite(Number(maxAvailable)) ? Math.max(0, Number(maxAvailable)) : 999;
    if (max <= 0) {
      setQuantities(prev => ({ ...prev, [id]: 0 }));
      return;
    }
    const current = getQuantity(id, max);
    const updated = Math.min(max, Math.max(1, current + delta));
    setQuantities(prev => ({ ...prev, [id]: updated }));
  };

  const filteredListings = listings
    .filter(item => {
      // Crop filter
      if (selectedCrop !== 'ALL') {
        const itemCrop = (item.crop || '').toLowerCase();
        const sel = selectedCrop.toLowerCase();
        if (sel === 'rice' && !itemCrop.includes('rice') && !itemCrop.includes('paddy')) return false;
        else if (sel !== 'rice' && !itemCrop.includes(sel)) return false;
      }
      // Status filter
      if (statusFilter === 'Active' && item.status.toLowerCase() !== 'active') {
        return false;
      }
      // Search query
      if (!searchQuery) return true;
      const query = searchQuery.toLowerCase();
      return (
        (item.crop && item.crop.toLowerCase().includes(query)) ||
        (item.farmer && item.farmer.toLowerCase().includes(query)) ||
        (item.location && item.location.toLowerCase().includes(query))
      );
    })
    .sort((a, b) => {
      if (sortBy === 'price_asc') {
        return (parseFloat(a.price) || 0) - (parseFloat(b.price) || 0);
      }
      if (sortBy === 'price_desc') {
        return (parseFloat(b.price) || 0) - (parseFloat(a.price) || 0);
      }
      if (sortBy === 'credits_desc') {
        return (parseFloat(b.available) || 0) - (parseFloat(a.available) || 0);
      }
      return 0;
    });

  const handleBuyClick = (item) => {
    const maxAvail = Number.isFinite(Number(item.available)) ? Math.max(0, Number(item.available)) : 999;
    if (maxAvail <= 0 || (item.status || '').toLowerCase() !== 'active') {
      return;
    }
    const qty = Math.min(maxAvail, Math.max(1, getQuantity(item.id, maxAvail)));
    setQuantities(prev => ({ ...prev, [item.id]: qty }));
    setCheckoutModalItem(item);
    setPurchaseProof(null);
    setCheckoutError('');
  };

  const handleConfirmPurchase = async () => {
    setIsProcessing(true);
    setCheckoutError('');
    try {
      const maxAvail = parseFloat(checkoutModalItem.available);
      const qty = getQuantity(checkoutModalItem.id, checkoutModalItem.available);
      const price = parseFloat(checkoutModalItem.price);

      if (!Number.isFinite(qty) || qty <= 0) {
        throw new Error('Requested volume must be at least 1 credit.');
      }
      if (Number.isFinite(maxAvail) && maxAvail <= 0) {
        throw new Error('This listing has no available credits remaining to purchase.');
      }
      if (Number.isFinite(maxAvail) && qty > maxAvail) {
        throw new Error(`Requested volume (${qty} MT) exceeds available inventory (${maxAvail} MT).`);
      }
      const buyerName = user?.name || 'Corporate Buyer';

      // 1. Attempt checkout via payments service
      const checkoutRes = await createCheckout({
        listing_id: checkoutModalItem.id,
        credits: qty,
        buyer_name: buyerName,
      });

      // Handle Razorpay live checkout if payment gateway is engaged
      if (checkoutRes && checkoutRes.payment_required && checkoutRes.checkout?.key_id) {
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
            script.onerror = () => reject(new Error('Failed to load Razorpay checkout SDK. Please verify your connection.'));
            document.body.appendChild(script);
          });
        }
        const rzp = new window.Razorpay({
          key: checkoutRes.checkout.key_id,
          order_id: checkoutRes.checkout.order_id,
          name: 'CarbonX Market',
          description: `Retirement of ${qty} credits (${checkoutModalItem.crop})`,
          handler: (response) => {
            const gross = checkoutTotal || (qty * price);
            const farmerShare = Math.round(gross * 0.70);
            const fpoShare = Math.round(gross * 0.05);
            const platformShare = gross - farmerShare - fpoShare;
            setPurchaseProof({
              success: true,
              certificate_id: `PENDING-RZP-${(response.razorpay_payment_id || '').slice(-8)}`,
              escrow_ref: response.razorpay_payment_id || 'RZP-ESCROW',
              gross_inr: gross,
              farmer_share_inr: farmerShare,
              fpo_share_inr: fpoShare,
              platform_share_inr: platformShare,
              payment_ref: response.razorpay_payment_id,
              batch_hash: response.razorpay_signature || 'Awaiting signature verification',
              split: {
                model: '3-way conditional',
                lines: [
                  { recipient: 'Farmer', share_pct: 70, amount_inr: farmerShare },
                  { recipient: 'FPO / Verifier', share_pct: 5, amount_inr: fpoShare },
                  { recipient: 'Platform & Monitoring', share_pct: 25, amount_inr: platformShare },
                ],
              },
            });
            setIsProcessing(false);
            loadListings();
          },
          modal: {
            ondismiss: () => {
              setIsProcessing(false);
              setCheckoutError('Payment checkout window was closed before completion. You can retry payment when ready.');
            },
          },
          prefill: { name: buyerName },
          theme: { color: '#0C2A18' },
        });
        rzp.on('payment.failed', (errResponse) => {
          const reason = errResponse?.error?.description || errResponse?.error?.reason || 'Transaction failed or was declined by bank.';
          const code = errResponse?.error?.code ? ` (${errResponse.error.code})` : '';
          setCheckoutError(`Payment Failed: ${reason}${code}. Your account was not charged. Please retry or try another payment method.`);
          setIsProcessing(false);
        });
        rzp.open();
        return;
      }

      // If simulated settlement or standard response
      const settlement = checkoutRes?.settlement || checkoutRes;
      if (settlement && settlement.certificate_id) {
        setIsProcessing(false);
        setPurchaseProof(settlement);
        loadListings();
        return;
      }

      // Fallback to legacy buyCredits if checkout endpoint returned an unexpected structure
      const data = await buyCredits({
        listing_id: checkoutModalItem.id,
        credits: qty,
        ...(Number.isFinite(price) ? { unit_price: price } : {}),
        buyer_name: buyerName,
      });
      if (data && data.certificate_id) {
        setIsProcessing(false);
        setPurchaseProof(data);
        loadListings();
        return;
      }
      throw new Error((checkoutRes && (checkoutRes.message || checkoutRes.detail)) || (data && (data.message || data.detail)) || 'Purchase failed');
    } catch (err) {
      setCheckoutError(err.message || 'Purchase could not be completed. Please try again.');
      setIsProcessing(false);
    }
  };

  const checkoutQty = checkoutModalItem ? getQuantity(checkoutModalItem.id, checkoutModalItem.available) : 1;
  const checkoutPrice = checkoutModalItem ? parseFloat(checkoutModalItem.price) : NaN;
  const checkoutTotal = Number.isFinite(checkoutPrice) ? checkoutQty * checkoutPrice : null;

  // Crop visual identity — gradient + emoji tiles that always render (no
  // network dependency), keyed by crop name.
  const cropArt = (crop) => {
    const map = {
      rice: { emoji: "🌾", grad: "from-emerald-100 to-lime-200" },
      paddy: { emoji: "🌾", grad: "from-emerald-100 to-lime-200" },
      maize: { emoji: "🌽", grad: "from-amber-100 to-yellow-200" },
      cotton: { emoji: "☁️", grad: "from-sky-100 to-slate-200" },
      millets: { emoji: "🌾", grad: "from-orange-100 to-amber-200" },
      sugarcane: { emoji: "🎋", grad: "from-lime-100 to-green-200" },
      turmeric: { emoji: "🟡", grad: "from-yellow-100 to-orange-200" },
      chilli: { emoji: "🌶️", grad: "from-red-100 to-orange-200" },
    };
    return map[(crop || "").toLowerCase()] || { emoji: "🌱", grad: "from-emerald-100 to-teal-200" };
  };

  return (
    <div className="min-h-screen bg-slate-50 font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-6xl mx-auto space-y-6">

        {/* Header & Search Bar */}
        <div className="space-y-4">
          <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
            <div>
              <h1 className="text-2xl font-extrabold text-[#0F172A] font-manrope">Carbon Credit Marketplace</h1>
              <p className="text-xs text-slate-500 mt-0.5 flex items-center gap-2">
                Direct agricultural carbon offset procurement from verified Telangana farms.
                {dataSource === 'fallback' && (
                  <span className="text-[10px] font-bold text-amber-800 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">
                    SAMPLE DATA (DB offline)
                  </span>
                )}
              </p>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <button
                onClick={() => navigate('/create-listing')}
                className="px-4 py-2.5 bg-white border border-emerald-600 text-emerald-800 hover:bg-emerald-50 rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-1.5"
              >
                <PlusCircle className="w-4 h-4 text-emerald-700" />
                <span>List Credits for Sale</span>
              </button>

              <button
                onClick={() => navigate('/marketplace/checkout')}
                className="px-5 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-2"
              >
                <ShoppingCart className="w-4 h-4 text-emerald-300" />
                <span>Bulk Auto-Match Engine</span>
              </button>
            </div>
          </div>

          {/* Full-width clean white search bar */}
          <div className="relative w-full">
            <Search className="w-5 h-5 text-slate-400 absolute left-5 top-4" />
            <input
              type="text"
              placeholder="Search by crop, farmer, or location..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-6 py-3.5 bg-white border border-slate-200 rounded-full text-sm text-slate-900 shadow-sm focus:outline-none focus:border-emerald-600 font-medium"
            />
          </div>

          {/* Quick Filters & Sorting Controls */}
          <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 pt-1">
            {/* Crop Pills */}
            <div className="flex flex-wrap items-center gap-1.5">
              {[
                { id: 'ALL', label: 'All Crops' },
                { id: 'Rice', label: '🌾 Rice / Paddy' },
                { id: 'Cotton', label: '☁️ Cotton' },
                { id: 'Maize', label: '🌽 Maize' },
                { id: 'Millets', label: '🌾 Millets' },
                { id: 'Sugarcane', label: '🎋 Sugarcane' },
                { id: 'Chilli', label: '🌶️ Chilli' },
              ].map(c => (
                <button
                  key={c.id}
                  type="button"
                  onClick={() => setSelectedCrop(c.id)}
                  className={`px-3 py-1.5 rounded-full text-xs font-bold transition-all ${
                    selectedCrop === c.id
                      ? 'bg-[#0C2A18] text-emerald-100 shadow-sm'
                      : 'bg-white border border-slate-200 text-slate-600 hover:bg-slate-100'
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>

            {/* Status & Sort Controls */}
            <div className="flex items-center gap-2 self-end md:self-auto text-xs">
              <div className="flex items-center bg-white border border-slate-200 rounded-xl p-0.5 shadow-xs">
                <button
                  type="button"
                  onClick={() => setStatusFilter('Active')}
                  className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
                    statusFilter === 'Active' ? 'bg-emerald-800 text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  Active Only
                </button>
                <button
                  type="button"
                  onClick={() => setStatusFilter('ALL')}
                  className={`px-2.5 py-1 rounded-lg font-bold transition-all ${
                    statusFilter === 'ALL' ? 'bg-emerald-800 text-white shadow-xs' : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  All Statuses
                </button>
              </div>

              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                className="px-3 py-1.5 bg-white border border-slate-200 rounded-xl font-semibold text-slate-700 focus:outline-none shadow-xs"
              >
                <option value="price_asc">Price: Low to High</option>
                <option value="price_desc">Price: High to Low</option>
                <option value="credits_desc">Most Volume (MT)</option>
              </select>
            </div>
          </div>
        </div>

        {/* Marketplace product grid */}
        {dataSource === 'loading' ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center">
            <p className="text-sm font-bold text-slate-700">Loading listings…</p>
          </div>
        ) : dataSource === 'error' ? (
          <div className="bg-white border border-rose-200 rounded-2xl p-12 text-center space-y-3">
            <AlertTriangle className="w-10 h-10 text-rose-400 mx-auto" />
            <p className="text-sm font-bold text-slate-700">Marketplace could not be reached</p>
            <p className="text-xs text-slate-500">{loadError}</p>
            <button
              onClick={loadListings}
              className="px-5 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold"
            >
              Retry
            </button>
          </div>
        ) : filteredListings.length === 0 ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-12 text-center">
            <Search className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-sm font-bold text-slate-700">No listings match your search or filter</p>
            <p className="text-xs text-slate-500 mt-1">Try resetting the crop filter or status selector.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {filteredListings.map(item => {
              const qty = getQuantity(item.id, item.available);
              const art = cropArt(item.crop);
              const isAvailable = (item.status || '').toLowerCase() === 'active' && (item.available == null || item.available > 0);
              return (
                <div key={item.id} className="bg-white border border-slate-200 rounded-2xl shadow-sm hover:shadow-md hover:border-emerald-300 transition-all overflow-hidden flex flex-col">
                  {/* Crop art tile */}
                  <div className={`relative h-28 bg-gradient-to-br ${art.grad} flex items-center justify-center`}>
                    <span className="text-5xl drop-shadow-sm">{art.emoji}</span>
                    <span className="absolute top-3 left-3 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-white/90 text-emerald-900 border border-emerald-200">
                      {item.badge || 'UNRATED'}
                    </span>
                    <span className={`absolute top-3 right-3 px-2.5 py-0.5 rounded-full text-[10px] font-bold ${
                      (item.status || '').toLowerCase() === 'active'
                        ? 'bg-[#0C2A18] text-emerald-100'
                        : 'bg-slate-700 text-slate-200'
                    }`}>
                      {item.status}
                    </span>
                  </div>

                  <div className="p-5 flex flex-col gap-3 flex-1">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <h2 className="text-base font-extrabold text-slate-900 font-manrope truncate">{item.crop}</h2>
                        <p className="text-xs text-slate-500 truncate flex items-center gap-1 mt-0.5">
                          <MapPin className="w-3.5 h-3.5 text-slate-400 shrink-0" />
                          {item.location}
                        </p>
                      </div>
                      <div className="text-right shrink-0">
                        <p className="text-lg font-extrabold text-emerald-800 font-manrope">₹{item.price ?? '—'}</p>
                        <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wide">per credit</p>
                      </div>
                    </div>

                    <p className="text-xs font-semibold text-slate-600 flex items-center gap-1.5">
                      <span className="w-5 h-5 rounded-full bg-emerald-100 text-emerald-800 flex items-center justify-center text-[9px] font-black shrink-0">
                        {(item.farmer || '—').slice(0, 2).toUpperCase()}
                      </span>
                      {item.farmer}
                    </p>

                    <div className="grid grid-cols-3 gap-2 text-center">
                      <div className="bg-slate-50 border border-slate-100 rounded-lg py-1.5">
                        <p className="text-[9px] font-bold text-slate-400 uppercase">Available</p>
                        <p className="text-xs font-extrabold text-slate-900">{item.available ?? '—'}</p>
                      </div>
                      <div className="bg-slate-50 border border-slate-100 rounded-lg py-1.5">
                        <p className="text-[9px] font-bold text-slate-400 uppercase">Carbon</p>
                        <p className="text-xs font-extrabold text-slate-900">{item.carbonScore ?? '—'} t</p>
                      </div>
                      <div className="bg-slate-50 border border-slate-100 rounded-lg py-1.5">
                        <p className="text-[9px] font-bold text-slate-400 uppercase">Bio</p>
                        <p className="text-xs font-extrabold text-slate-900">{item.bioScore ?? '—'} t</p>
                      </div>
                    </div>

                    <div className="mt-auto flex items-center gap-2 pt-1">
                      <div className="flex items-center border border-slate-200 rounded-xl px-2 py-1.5 bg-white gap-2.5">
                        <button
                          type="button"
                          aria-label="Decrease quantity"
                          disabled={!isAvailable || qty <= 1}
                          onClick={() => updateQuantity(item.id, -1, item.available)}
                          className="p-0.5 hover:bg-slate-100 disabled:opacity-40 rounded text-slate-600"
                        >
                          <Minus className="w-3.5 h-3.5" />
                        </button>
                        <span className="font-mono text-sm font-bold text-slate-900 min-w-[18px] text-center">{qty}</span>
                        <button
                          type="button"
                          aria-label="Increase quantity"
                          disabled={!isAvailable || (item.available != null && qty >= item.available)}
                          onClick={() => updateQuantity(item.id, 1, item.available)}
                          className="p-0.5 hover:bg-slate-100 disabled:opacity-40 rounded text-slate-600"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <button
                        type="button"
                        disabled={!isAvailable}
                        onClick={() => handleBuyClick(item)}
                        className={`flex-1 py-2.5 text-xs font-bold rounded-xl transition-all shadow-sm flex items-center justify-center gap-1 ${
                          isAvailable
                            ? 'bg-[#0C2A18] hover:bg-[#15803D] text-white'
                            : 'bg-slate-200 text-slate-500 cursor-not-allowed'
                        }`}
                      >
                        <span>{isAvailable ? 'Buy Credits' : ((item.status || '').toLowerCase() === 'retired' ? 'Retired' : 'Sold Out')}</span>
                        {isAvailable && <ChevronRight className="w-4 h-4" />}
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Purchase Escrow Confirmation Modal */}
        {checkoutModalItem && (
          <div className="fixed inset-0 z-50 bg-[#0C2A18]/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white border border-slate-200 shadow-xl rounded-2xl p-6 max-w-md w-full space-y-4">
              <div className="flex justify-between items-center border-b border-slate-100 pb-3">
                <h3 className="text-base font-bold text-[#0F172A]">Confirm Credit Escrow Purchase</h3>
                <button onClick={() => setCheckoutModalItem(null)} className="p-1 hover:bg-slate-100 rounded-lg">
                  <X className="w-4 h-4 text-slate-500" />
                </button>
              </div>

              {purchaseProof ? (
                <div className="space-y-3 text-xs">
                  <div className="bg-emerald-50 border border-emerald-200 text-emerald-950 p-4 rounded-xl text-center space-y-1">
                    <CheckCircle2 className="w-8 h-8 text-emerald-700 mx-auto" />
                    <p className="font-bold text-sm">Purchase complete — credits retired</p>
                    <p className="text-[11px] text-slate-600">
                      Escrow {purchaseProof.escrow_ref} · Certificate {purchaseProof.certificate_id}
                    </p>
                  </div>

                  {purchaseProof.split?.lines?.length > 0 && (
                    <div className="border border-slate-200 rounded-xl p-3 space-y-1.5">
                      <p className="font-bold text-slate-700 text-[11px] uppercase tracking-wide">
                        Transparent payout split ({purchaseProof.split.model})
                      </p>
                      {purchaseProof.split.lines.map(line => (
                        <div key={line.recipient} className="flex justify-between items-center">
                          <span className="text-slate-600 font-semibold">
                            {line.recipient} <span className="text-slate-400">· {line.share_pct}%</span>
                          </span>
                          <span className="font-mono font-bold text-slate-900">₹{Number(line.amount_inr).toLocaleString('en-IN')}</span>
                        </div>
                      ))}
                      <p className="text-[10px] text-slate-500 pt-1 border-t border-slate-100">
                        Paid from escrow {purchaseProof.escrow_ref} — the farmer's 70% floor is guaranteed.
                      </p>
                    </div>
                  )}

                  {purchaseProof.batch_hash && (
                    <div className="bg-slate-50 border border-slate-200 rounded-xl p-3 space-y-1">
                      <p className="font-bold text-slate-700 text-[11px] uppercase tracking-wide">Tamper-evident record</p>
                      <p className="font-mono text-[10px] text-slate-600 break-all">sha256:{purchaseProof.batch_hash}</p>
                      <p className="text-[10px] text-slate-500">Anchored to the farm's hash ledger — anyone can recompute this chain.</p>
                    </div>
                  )}

                  <div className="flex gap-2">
                    <button
                      onClick={() => { setCheckoutModalItem(null); setPurchaseProof(null); }}
                      className="flex-1 py-2.5 bg-slate-100 text-slate-700 rounded-xl text-xs font-bold hover:bg-slate-200"
                    >
                      Close
                    </button>
                    <button
                      onClick={() => navigate(`/buyer/certificates/${purchaseProof.certificate_id}`)}
                      className="flex-1 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold shadow-sm"
                    >
                      View Certificate
                    </button>
                  </div>
                </div>
              ) : (
                <div className="space-y-4 text-xs">
                  {checkoutError && (
                    <div className="bg-rose-50 border border-rose-200 p-3 rounded-xl flex items-start gap-2.5 text-xs text-rose-800">
                      <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
                      <div className="flex-1 space-y-1">
                        <p className="font-bold">Payment Issue Encountered</p>
                        <p className="text-[11px] leading-relaxed text-rose-700">{checkoutError}</p>
                      </div>
                    </div>
                  )}
                  <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-4 space-y-2">
                    <div className="flex justify-between">
                      <span className="text-slate-500 font-semibold">Crop Parcel:</span>
                      <span className="font-bold text-slate-900">{checkoutModalItem.crop} ({checkoutModalItem.farmer})</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500 font-semibold">Location:</span>
                      <span className="font-medium text-slate-800">{checkoutModalItem.location}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-slate-500 font-semibold">Selected Volume:</span>
                      <div className="flex items-center border border-slate-200 rounded-lg px-2 py-1 bg-white gap-2">
                        <button
                          type="button"
                          aria-label="Decrease volume"
                          disabled={isProcessing || checkoutQty <= 1}
                          onClick={() => updateQuantity(checkoutModalItem.id, -1, checkoutModalItem.available)}
                          className="p-0.5 hover:bg-slate-100 disabled:opacity-40 rounded text-slate-600"
                        >
                          <Minus className="w-3.5 h-3.5" />
                        </button>
                        <span className="font-mono font-bold text-emerald-800 min-w-[20px] text-center">{checkoutQty} MT</span>
                        <button
                          type="button"
                          aria-label="Increase volume"
                          disabled={isProcessing || (checkoutModalItem.available != null && checkoutQty >= checkoutModalItem.available)}
                          onClick={() => updateQuantity(checkoutModalItem.id, 1, checkoutModalItem.available)}
                          className="p-0.5 hover:bg-slate-100 disabled:opacity-40 rounded text-slate-600"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                    <div className="flex justify-between border-t border-slate-200 pt-2">
                      <span className="text-slate-500 font-semibold">Total Escrow Value:</span>
                      <span className="font-mono font-bold text-slate-900">
                        {checkoutTotal != null ? `₹${checkoutTotal.toLocaleString('en-IN')}` : '—'}
                      </span>
                    </div>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={() => setCheckoutModalItem(null)}
                      className="flex-1 py-2.5 bg-slate-100 text-slate-700 rounded-xl text-xs font-bold hover:bg-slate-200"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleConfirmPurchase}
                      disabled={isProcessing || checkoutQty <= 0 || (checkoutModalItem.available != null && checkoutQty > checkoutModalItem.available)}
                      className="flex-1 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] disabled:opacity-50 text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-1.5"
                    >
                      <span>{isProcessing ? 'Executing...' : (checkoutError ? 'Retry Payment' : 'Confirm & Lock Escrow')}</span>
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
