import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Search, MapPin, Calendar, ShoppingCart, CheckCircle2, ChevronRight, PlusCircle, Minus, Plus, X, Loader2 } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getMarketplaceListings, buyCredits } from '../services/api';

export default function Marketplace() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [searchQuery, setSearchQuery] = useState('');
  const [quantities, setQuantities] = useState({});
  const [checkoutModalItem, setCheckoutModalItem] = useState(null);
  const [paymentSuccess, setPaymentSuccess] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [checkoutTxHash, setCheckoutTxHash] = useState(null);
  const [checkoutCertId, setCheckoutCertId] = useState(null);
  const [checkoutError, setCheckoutError] = useState('');

  const defaultListings = [
    {
      id: 'LST-001',
      crop: 'Paddy',
      farmer: 'Marketplace Farmer',
      location: 'Chevella, Rangareddy',
      available: '1.14',
      carbonScore: '0.47',
      bioScore: '0.67',
      price: '550',
      status: 'Active',
      badge: 'REGISTRY'
    },
    {
      id: 'LST-002',
      crop: 'Rice',
      farmer: 'Test Farmer',
      location: 'Moinabad, Rangareddy',
      available: '96',
      carbonScore: '0.82',
      bioScore: '0.75',
      price: '550',
      status: 'Active',
      badge: 'REGISTRY_DOC'
    },
    {
      id: 'LST-003',
      crop: 'Cotton',
      farmer: 'Venkat Rao',
      location: 'Pochampally, Yadadri Bhuvanagiri',
      available: '12.5',
      carbonScore: '0.78',
      bioScore: '0.84',
      price: '340',
      status: 'Active',
      badge: 'REGISTRY'
    },
    {
      id: 'LST-004',
      crop: 'Maize',
      farmer: 'B. Lakshmi',
      location: 'Mothkur, Yadadri Bhuvanagiri',
      available: '58.0',
      carbonScore: '0.71',
      bioScore: '0.72',
      price: '320',
      status: 'Active',
      badge: 'REGISTRY_DOC'
    },
    {
      id: 'LST-005',
      crop: 'Paddy',
      farmer: 'M. Narsimha',
      location: 'Bonakal, Khammam, Telangana',
      available: '38.0',
      carbonScore: '0.65',
      bioScore: '0.68',
      price: '310',
      status: 'Active',
      badge: 'DOCUMENT'
    }
  ];

  const [listings, setListings] = useState(defaultListings);
  const [dataSource, setDataSource] = useState('fallback');

  useEffect(() => {
    async function loadListings() {
      setIsLoading(true);
      try {
        const data = await getMarketplaceListings({ limit: 50 });
        if (data && data.success && Array.isArray(data.listings) && data.listings.length > 0) {
          const mapped = data.listings.map((l, idx) => ({
            id: l.id || `LST-DB-${idx}`,
            crop: l.crop || 'Paddy',
            farmer: l.farmer_name || 'Marketplace Farmer',
            location: l.location || 'Telangana',
            available: (l.total_credits || l.carbon_credits || 1.0).toString(),
            carbonScore: (l.carbon_credits || 0.5).toString(),
            bioScore: (l.biodiversity_credits || 0.5).toString(),
            price: (l.price_per_credit || 340).toString(),
            status: l.status || 'Active',
            badge: l.badge || (l.size_label === 'Large' ? 'REGISTRY' : l.size_label === 'Medium' ? 'REGISTRY_DOC' : 'DOCUMENT'),
            imageUrl: l.image_url
          }));
          setListings(mapped);
          setDataSource(data.source || 'live_db');
          return;
        }
        setDataSource('fallback');
      } catch (err) {
        console.warn('Could not fetch remote listings, using defaults', err);
        setDataSource('fallback');
      } finally {
        setIsLoading(false);
      }
    }
    loadListings();
  }, []);

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
    setPaymentSuccess(false);
    setCheckoutError('');
  };

  const finishPurchase = (certId) => {
    setIsProcessing(false);
    setPaymentSuccess(true);
    setTimeout(() => {
      setCheckoutModalItem(null);
      setPaymentSuccess(false);
      navigate(`/buyer/certificates/${certId}`);
    }, 1500);
  };

  const handleConfirmPurchase = async () => {
    setIsProcessing(true);
    setCheckoutError('');
    try {
      const qty = getQuantity(checkoutModalItem.id);
      const price = parseFloat(checkoutModalItem.price) || 340;
      const data = await buyCredits({
        listing_id: checkoutModalItem.id,
        credits: qty,
        unit_price: price,
        buyer_name: user?.name || 'Corporate Buyer'
      });
      if (data && data.certificate_id) {
        setCheckoutTxHash(data.tx_hash);
        setCheckoutCertId(data.certificate_id);
        finishPurchase(data.certificate_id);
        return;
      }
      throw new Error((data && data.message) || 'Purchase failed');
    } catch (err) {
      console.warn('Purchase API unavailable', err);
      if (import.meta.env.DEV) {
        // Demo mode (dev builds only): simulated checkout
        setCheckoutCertId('CX-2026-CERT-00123');
        finishPurchase('CX-2026-CERT-00123');
        return;
      }
      setCheckoutError(err.message || 'Purchase could not be completed. Please try again.');
      setIsProcessing(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-8 px-4 md:px-10">
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
                className="px-5 py-2.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center gap-2"
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
              className="w-full pl-13 pr-6 py-3.5 bg-white border border-slate-200 rounded-full text-sm text-slate-900 shadow-sm focus:outline-none focus:border-emerald-600 font-medium"
            />
          </div>
        </div>

        {/* Listing Cards Stack */}
        <div className="space-y-4">
          {filteredListings.map(item => {
            const qty = getQuantity(item.id);
            return (
              <div
                key={item.id}
                className="bg-white border border-slate-100 rounded-2xl p-6 shadow-sm hover:border-slate-300 transition-all flex flex-col md:flex-row justify-between items-start md:items-center gap-6"
              >
                {/* Left Data Column */}
                <div className="space-y-3 flex-1 min-w-0">
                  <div>
                    <h2 className="text-lg font-bold text-[#0F172A] font-manrope">{item.crop}</h2>
                    <p className="text-sm font-semibold text-[#4B5563] mt-0.5">{item.farmer}</p>
                  </div>

                  {/* Details Line */}
                  <div className="flex flex-wrap items-center gap-4 text-xs text-slate-500">
                    <div className="flex items-center gap-1.5 font-medium">
                      <MapPin className="w-4 h-4 text-slate-400 shrink-0" />
                      <span>{item.location}</span>
                    </div>

                    <div className="flex items-center gap-1.5 font-medium">
                      <Calendar className="w-4 h-4 text-slate-400 shrink-0" />
                      <span>Available: {item.available}</span>
                    </div>
                  </div>

                  {/* Metric & Status Chips Row */}
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <span className="px-3 py-1 bg-slate-100 text-slate-700 text-xs font-semibold rounded-md border border-slate-200">
                      Carbon: {item.carbonScore}
                    </span>
                    <span className="px-3 py-1 bg-slate-100 text-slate-700 text-xs font-semibold rounded-md border border-slate-200">
                      Bio: {item.bioScore}
                    </span>
                    <span className="px-3 py-1 bg-slate-100 text-slate-800 text-xs font-bold rounded-md border border-slate-200 font-mono">
                      ₹{item.price}/credit
                    </span>
                    <span className="px-2.5 py-1 bg-emerald-50 text-emerald-800 text-xs font-semibold rounded-md border border-emerald-200">
                      {item.status}
                    </span>
                  </div>
                </div>

                {/* Right Stepper & Purchase Column */}
                <div className="flex items-center gap-3 shrink-0 self-end md:self-center">
                  <div className="flex items-center border border-slate-200 rounded-xl px-3 py-1.5 bg-slate-50 gap-3">
                    <button
                      type="button"
                      onClick={() => updateQuantity(item.id, -1)}
                      className="p-1 hover:bg-slate-200 rounded text-slate-700 transition-colors"
                    >
                      <Minus className="w-3.5 h-3.5" />
                    </button>

                    <span className="font-mono text-sm font-bold text-slate-900 min-w-[20px] text-center">
                      {qty}
                    </span>

                    <button
                      type="button"
                      onClick={() => updateQuantity(item.id, 1)}
                      className="p-1 hover:bg-slate-200 rounded text-slate-700 transition-colors"
                    >
                      <Plus className="w-3.5 h-3.5" />
                    </button>
                  </div>

                  <button
                    type="button"
                    onClick={() => handleBuyClick(item)}
                    className="px-5 py-2.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-white text-xs font-bold rounded-xl transition-all shadow-sm flex items-center gap-1.5"
                  >
                    <span>Buy</span>
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>

        {/* Purchase Escrow Confirmation Modal */}
        {checkoutModalItem && (
          <div className="fixed inset-0 z-50 bg-[#1B4332]/60 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white border border-slate-200 shadow-xl rounded-2xl p-6 max-w-md w-full space-y-4">
              <div className="flex justify-between items-center border-b border-slate-100 pb-3">
                <h3 className="text-base font-bold text-[#0F172A]">Confirm Credit Escrow Purchase</h3>
                <button onClick={() => setCheckoutModalItem(null)} className="p-1 hover:bg-slate-100 rounded-lg">
                  <X className="w-4 h-4 text-slate-500" />
                </button>
              </div>

              {paymentSuccess ? (
                <div className="bg-emerald-50 border border-emerald-200 text-emerald-950 p-4 rounded-xl text-center space-y-2">
                  <CheckCircle2 className="w-8 h-8 text-emerald-700 mx-auto" />
                  <p className="font-bold text-sm">Escrow Credit Purchase Complete!</p>
                  <p className="text-xs text-slate-600">Redirecting to official certificate...</p>
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
                      <span className="font-mono font-bold text-emerald-800">{getQuantity(checkoutModalItem.id)} MT</span>
                    </div>
                    <div className="flex justify-between border-t border-slate-200 pt-2">
                      <span className="text-slate-500 font-semibold">Total Escrow Value:</span>
                      <span className="font-mono font-bold text-slate-900">
                        ₹{(getQuantity(checkoutModalItem.id) * parseFloat(checkoutModalItem.price)).toLocaleString('en-IN')}
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
                      className="flex-1 py-2.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-1.5"
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
