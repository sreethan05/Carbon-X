import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, MapPin, ShoppingCart, CheckCircle2, ChevronRight, PlusCircle, Minus, Plus, X, AlertTriangle } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getMarketplaceListings, buyCredits } from '../services/api';

export default function Marketplace() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [searchQuery, setSearchQuery] = useState('');
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
    const data = await getMarketplaceListings({ limit: 50 });
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

  useEffect(() => { loadListings(); }, []);

  const getQuantity = (id) => quantities[id] || 1;

  const updateQuantity = (id, delta) => {
    const current = getQuantity(id);
    const updated = Math.max(1, current + delta);
    setQuantities({ ...quantities, [id]: updated });
  };

  const filteredListings = listings.filter(item => {
    if (!searchQuery) return true;
    const query = searchQuery.toLowerCase();
    return (
      (item.crop && item.crop.toLowerCase().includes(query)) ||
      (item.farmer && item.farmer.toLowerCase().includes(query)) ||
      (item.location && item.location.toLowerCase().includes(query))
    );
  });

  const handleBuyClick = (item) => {
    setCheckoutModalItem(item);
    setPurchaseProof(null);
    setCheckoutError('');
  };

  const handleConfirmPurchase = async () => {
    setIsProcessing(true);
    setCheckoutError('');
    try {
      const qty = getQuantity(checkoutModalItem.id);
      const price = parseFloat(checkoutModalItem.price);
      const data = await buyCredits({
        listing_id: checkoutModalItem.id,
        credits: qty,
        ...(Number.isFinite(price) ? { unit_price: price } : {}),
        ...(user?.name ? { buyer_name: user.name } : {}),
      });
      if (data && data.certificate_id) {
        setIsProcessing(false);
        setPurchaseProof(data);
        return;
      }
      throw new Error((data && (data.message || data.detail)) || 'Purchase failed');
    } catch (err) {
      // No simulated receipts: either the backend escrow really executed
      // (demo mode included, with real ledger hashes) or the error is shown.
      setCheckoutError(err.message || 'Purchase could not be completed. Please try again.');
      setIsProcessing(false);
    }
  };

  const checkoutQty = checkoutModalItem ? getQuantity(checkoutModalItem.id) : 1;
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
              placeholder="Search by crop or location..."
              value={searchQuery}
              onChange={e => setSearchQuery(e.target.value)}
              className="w-full pl-12 pr-6 py-3.5 bg-white border border-slate-200 rounded-full text-sm text-slate-900 shadow-sm focus:outline-none focus:border-emerald-600 font-medium"
            />
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
            <p className="text-sm font-bold text-slate-700">No listings match your search</p>
            <p className="text-xs text-slate-500 mt-1">Try a different crop or location.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
            {filteredListings.map(item => {
              const qty = getQuantity(item.id);
              const art = cropArt(item.crop);
              return (
                <div key={item.id} className="bg-white border border-slate-200 rounded-2xl shadow-sm hover:shadow-md hover:border-emerald-300 transition-all overflow-hidden flex flex-col">
                  {/* Crop art tile */}
                  <div className={`relative h-28 bg-gradient-to-br ${art.grad} flex items-center justify-center`}>
                    <span className="text-5xl drop-shadow-sm">{art.emoji}</span>
                    <span className="absolute top-3 left-3 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-white/90 text-emerald-900 border border-emerald-200">
                      {item.badge || 'UNRATED'}
                    </span>
                    <span className="absolute top-3 right-3 px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-[#0C2A18] text-emerald-100">
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
                        <button type="button" aria-label="Decrease quantity"
                          onClick={() => updateQuantity(item.id, -1)}
                          className="p-0.5 hover:bg-slate-100 rounded text-slate-600">
                          <Minus className="w-3.5 h-3.5" />
                        </button>
                        <span className="font-mono text-sm font-bold text-slate-900 min-w-[18px] text-center">{qty}</span>
                        <button type="button" aria-label="Increase quantity"
                          onClick={() => updateQuantity(item.id, 1)}
                          className="p-0.5 hover:bg-slate-100 rounded text-slate-600">
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                      <button
                        type="button"
                        onClick={() => handleBuyClick(item)}
                        className="flex-1 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white text-xs font-bold rounded-xl transition-all shadow-sm flex items-center justify-center gap-1"
                      >
                        <span>Buy Credits</span>
                        <ChevronRight className="w-4 h-4" />
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
                    <p className="text-rose-700 font-bold bg-rose-50 border border-rose-200 p-2.5 rounded-lg leading-relaxed">
                      {checkoutError}
                    </p>
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
                    <div className="flex justify-between">
                      <span className="text-slate-500 font-semibold">Selected Volume:</span>
                      <span className="font-mono font-bold text-emerald-800">{checkoutQty} MT</span>
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
                      disabled={isProcessing}
                      className="flex-1 py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-1.5"
                    >
                      <span>{isProcessing ? 'Executing...' : 'Confirm & Lock Escrow'}</span>
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
