import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Wallet, ArrowRight, CheckCircle2, Building, ArrowLeft, ShieldCheck } from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { getWallet, demoLogin } from '../services/api';

export default function CarbonWallet() {
  const navigate = useNavigate();
  const { user, refreshUser, login, isAuthenticated } = useAuth();

  const [totalEarned, setTotalEarned] = useState(0);
  const [pendingEscrow, setPendingEscrow] = useState(0);
  const [withdrawableUpi, setWithdrawableUpi] = useState(0);
  const [farmerShareTotal, setFarmerShareTotal] = useState(0);
  const [fpoShareTotal, setFpoShareTotal] = useState(0);
  const [platformShareTotal, setPlatformShareTotal] = useState(0);
  const [upiId, setUpiId] = useState(user?.upi || '');
  const [loadError, setLoadError] = useState('');
  const [demoMode, setDemoMode] = useState(false);
  const [isStartingDemo, setIsStartingDemo] = useState(false);

  // Bank Withdrawal Modal State
  const [showWithdrawModal, setShowWithdrawModal] = useState(false);
  const [selectedBank, setSelectedBank] = useState('State Bank of India (SBI)');
  const [upiIdInput, setUpiIdInput] = useState(user?.upi || '');
  const [withdrawAmt, setWithdrawAmt] = useState('1000');
  const [isTransferring, setIsTransferring] = useState(false);
  const [transferSuccess, setTransferSuccess] = useState(false);

  // Itemized transaction ledger from the real wallet API
  const [transactions, setTransactions] = useState([]);

  const loadWallet = async () => {
    setLoadError('');
    try {
      const data = await getWallet();
      if (data && data.success) {
        setTotalEarned(data.total_earned || 0);
        setPendingEscrow(data.escrow_pending || 0);
        setWithdrawableUpi(data.withdrawable_upi || 0);
        setFarmerShareTotal(data.farmer_share_total || 0);
        setFpoShareTotal(data.fpo_share_total || 0);
        setPlatformShareTotal(data.platform_share_total || 0);
        setUpiId(data.upi_id || user?.upi || '');
        setDemoMode(!!data.demo_mode);
        setTransactions((data.transactions || []).map((t) => ({
          date: t.date,
          txId: t.tx_id,
          source: t.source,
          creditsSold: t.credits_sold,
          rate: t.rate,
          gross: t.gross,
          farmerShare: t.farmer_share ?? 0,
          fpoShare: t.fpo_share ?? 0,
          platformShare: t.platform_share ?? 0,
          splitModel: t.split_model || '3-way',
          ledgerHash: t.ledger_hash,
          status: t.status,
        })));
      } else {
        setLoadError((data && (data.message || data.detail)) || 'Could not load wallet data');
      }
    } catch {
      setLoadError('Wallet service unreachable. Please try again.');
    }
  };

  useEffect(() => { loadWallet(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const startDemoSession = async () => {
    setIsStartingDemo(true);
    try {
      const data = await demoLogin();
      if (data && data.success && data.token) {
        await login(data.token, data.user);
        await refreshUser();
        await loadWallet();
      } else {
        setLoadError((data && data.message) || 'Demo session could not be started');
      }
    } catch {
      setLoadError('Demo session could not be started — is the backend running?');
    } finally {
      setIsStartingDemo(false);
    }
  };

  const handleWithdrawSubmit = (e) => {
    e.preventDefault();
    const amt = parseFloat(withdrawAmt) || 0;
    if (amt <= 0 || amt > withdrawableUpi) return;

    setIsTransferring(true);
    // Demo UPI payout simulation — no payments provider is wired in this build
    setTimeout(() => {
      setIsTransferring(false);
      setTransferSuccess(true);
      setWithdrawableUpi((prev) => prev - amt);

      const newTx = {
        date: new Date().toISOString().split('T')[0],
        txId: `UPI-DEMO-${Math.floor(10000 + Math.random() * 90000)}`,
        source: `Simulated UPI Transfer (${selectedBank}) — demo only`,
        gross: amt,
        farmerShare: amt,
        fpoShare: 0,
        platformShare: 0,
        splitModel: 'UPI payout',
        ledgerHash: null,
        status: 'DEMO'
      };

      setTransactions([newTx, ...transactions]);

      setTimeout(() => {
        setTransferSuccess(false);
        setShowWithdrawModal(false);
        refreshUser();
      }, 1800);
    }, 1200);
  };

  return (
    <div className="min-h-screen bg-surface font-inter text-agriText-main py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Header */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] font-bold text-primary uppercase tracking-wider bg-surface-sage border border-forest-200 px-2.5 py-0.5 rounded-full">
                Financial Summary Ledger
              </span>
              <span className="text-[10px] font-semibold text-agriText-subtle bg-warm-cream px-2 py-0.5 rounded">
                Simulated UPI Rails
              </span>
            </div>
            <h1 className="text-2xl font-extrabold text-carbon-900 font-manrope">Farmer Carbon Wallet</h1>
            <p className="text-xs text-agriText-muted mt-0.5">
              Conditional payout splits — your 70% floor is guaranteed, FPO 5% only when involved.
              {demoMode && <span className="ml-2 text-[10px] font-bold text-amber-800 bg-amber-50 border border-amber-200 px-1.5 py-0.5 rounded">DEMO SESSION</span>}
            </p>
          </div>

          <button
            onClick={() => navigate('/farmer/dashboard')}
            className="px-4 py-2.5 bg-surface-sage hover:bg-forest-100 border border-forest-200 text-carbon-800 rounded-xl text-xs font-bold transition-all flex items-center gap-2"
          >
            <ArrowLeft className="w-4 h-4" />
            <span>Back to Dashboard</span>
          </button>
        </div>

        {/* Auth / error prompt */}
        {loadError && (
          <div className="bg-amber-50 border border-amber-200 rounded-2xl p-5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
            <div>
              <p className="text-sm font-bold text-amber-900">Wallet could not load</p>
              <p className="text-xs text-amber-800 mt-0.5">{loadError}</p>
              {!isAuthenticated && (
                <p className="text-xs text-amber-700 mt-1">No database configured? Start a demo farmer session to explore the wallet with sample data.</p>
              )}
            </div>
            {!isAuthenticated && (
              <button
                onClick={startDemoSession}
                disabled={isStartingDemo}
                className="px-4 py-2.5 bg-[#1B4332] hover:bg-[#2D6A4F] text-white rounded-xl text-xs font-bold shadow-sm whitespace-nowrap"
              >
                {isStartingDemo ? 'Starting...' : 'Start Demo Farmer Session'}
              </button>
            )}
          </div>
        )}

        {/* Financial Summary Banner */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div className="bg-surface-sage border border-forest-200 text-carbon-900 shadow-card rounded-2xl p-6 flex flex-col justify-between">
            <div>
              <p className="text-[11px] font-semibold text-agriText-subtle uppercase tracking-wider">Total Lifetime Earned</p>
              <p className="text-3xl font-extrabold font-manrope text-primary mt-2">
                ₹{totalEarned.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </p>
            </div>
            <p className="text-[11px] text-agriText-muted mt-4">Settled into linked bank account via simulated UPI</p>
          </div>

          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 flex flex-col justify-between">
            <div>
              <p className="text-[11px] font-semibold text-agriText-subtle uppercase tracking-wider">Pending Escrow Balance</p>
              <p className="text-3xl font-extrabold text-amber-700 font-manrope mt-2">
                ₹{pendingEscrow.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </p>
            </div>
            <p className="text-xs text-agriText-muted mt-4">Held in smart escrow until corporate purchase execution</p>
          </div>

          <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 flex flex-col justify-between">
            <div>
              <p className="text-[11px] font-semibold text-agriText-subtle uppercase tracking-wider">Your Share (70% floor)</p>
              <p className="text-3xl font-extrabold text-carbon-900 font-manrope mt-2">
                ₹{farmerShareTotal.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </p>
            </div>

            <button
              onClick={() => setShowWithdrawModal(true)}
              className="mt-4 w-full py-2.5 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
            >
              <Wallet className="w-4 h-4" />
              <span>Simulate Instant UPI Payout</span>
            </button>
          </div>
        </div>

        {/* Split composition strip */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-5 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-primary" />
            <p className="text-xs font-bold text-carbon-900">Conditional split across all settled sales</p>
          </div>
          <div className="flex flex-wrap gap-4 text-xs font-semibold">
            <span className="text-primary">Farmer: ₹{farmerShareTotal.toLocaleString('en-IN')}</span>
            <span className="text-emerald-700">FPO (5% when involved): ₹{fpoShareTotal.toLocaleString('en-IN')}</span>
            <span className="text-slate-500">Platform: ₹{platformShareTotal.toLocaleString('en-IN')}</span>
          </div>
        </div>

        {/* Itemized Transaction Ledger */}
        <div className="bg-white border border-forest-100 shadow-card rounded-2xl p-6 space-y-6">
          <div className="flex justify-between items-center">
            <div>
              <h2 className="text-base font-bold text-carbon-900">Itemized Transaction Ledger</h2>
              <p className="text-xs text-agriText-muted">Every payout line, anchored to the tamper-evident hash ledger.</p>
            </div>

            <span className="text-xs font-mono font-semibold text-primary bg-surface-sage border border-forest-200 px-3 py-1 rounded-full">
              UPI VPA: {upiIdInput}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-forest-100 bg-surface-sage/40 text-agriText-muted font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Date</th>
                  <th className="py-3 px-4">Transaction ID</th>
                  <th className="py-3 px-4">Source / Buyer</th>
                  <th className="py-3 px-4">Gross</th>
                  <th className="py-3 px-4">Your Share</th>
                  <th className="py-3 px-4">FPO / Platform</th>
                  <th className="py-3 px-4">Ledger Proof</th>
                  <th className="py-3 px-4">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-forest-50 font-medium">
                {transactions.map((tx) => (
                  <tr key={tx.txId} className="hover:bg-surface-sage/30 transition-colors">
                    <td className="py-3 px-4 text-agriText-muted">{tx.date}</td>
                    <td className="py-3 px-4 font-mono text-carbon-900">{tx.txId}</td>
                    <td className="py-3 px-4 font-bold text-carbon-900">
                      {tx.source}
                      <span className="ml-2 text-[10px] font-semibold text-agriText-subtle">({tx.splitModel} split)</span>
                    </td>
                    <td className="py-3 px-4 text-carbon-800">₹{Number(tx.gross || 0).toLocaleString('en-IN')}</td>
                    <td className="py-3 px-4 font-extrabold text-primary">₹{Number(tx.farmerShare || 0).toLocaleString('en-IN')}</td>
                    <td className="py-3 px-4 text-carbon-700">
                      ₹{Number(tx.fpoShare || 0).toLocaleString('en-IN')} / ₹{Number(tx.platformShare || 0).toLocaleString('en-IN')}
                    </td>
                    <td className="py-3 px-4">
                      {tx.ledgerHash ? (
                        <span className="font-mono text-[10px] text-agriText-muted" title={`sha256:${tx.ledgerHash}`}>
                          sha256:{String(tx.ledgerHash).slice(0, 10)}…
                        </span>
                      ) : (
                        <span className="text-agriText-subtle">—</span>
                      )}
                    </td>
                    <td className="py-3 px-4">
                      <span className="bg-surface-sage text-primary border border-forest-200 px-2.5 py-0.5 rounded-full text-[10px] font-bold">
                        {tx.status}
                      </span>
                    </td>
                  </tr>
                ))}
                {transactions.length === 0 && !loadError && (
                  <tr>
                    <td colSpan={8} className="py-6 px-4 text-center text-agriText-muted">
                      No settled sales yet — list credits on the marketplace to see conditional splits here.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Instant UPI Withdrawal Modal */}
        {showWithdrawModal && (
          <div className="fixed inset-0 z-50 bg-carbon-900/40 backdrop-blur-xs flex items-center justify-center p-4">
            <div className="bg-white border border-forest-100 shadow-2xl rounded-2xl p-6 max-w-md w-full space-y-4">
              <div className="flex justify-between items-center border-b border-forest-100 pb-3">
                <div className="flex items-center gap-2">
                  <Building className="w-5 h-5 text-primary" />
                  <h3 className="text-sm font-bold text-carbon-900">Simulated UPI Bank Payout</h3>
                </div>
                <span className="text-[10px] font-bold text-agriText-subtle bg-warm-cream px-2 py-0.5 rounded">
                  Demo Mode
                </span>
              </div>

              {transferSuccess ? (
                <div className="bg-surface-sage border border-forest-200 text-carbon-900 p-4 rounded-xl text-center space-y-2">
                  <CheckCircle2 className="w-8 h-8 text-primary mx-auto" />
                  <p className="font-bold text-sm">Demo UPI Payout Dispatched!</p>
                  <p className="text-xs text-agriText-muted">Simulated transfer completed to {selectedBank}.</p>
                </div>
              ) : (
                <form onSubmit={handleWithdrawSubmit} className="space-y-4">
                  <div>
                    <label className="block text-xs font-bold text-carbon-800 mb-1">Destination Bank Account</label>
                    <select
                      value={selectedBank}
                      onChange={e => setSelectedBank(e.target.value)}
                      className="w-full px-3 py-2 bg-surface-sage/40 border border-forest-200 rounded-xl text-xs font-semibold text-carbon-900 focus:outline-none"
                    >
                      <option value="State Bank of India (SBI)">State Bank of India (SBI)</option>
                      <option value="HDFC Bank">HDFC Bank</option>
                      <option value="Telangana Grameena Bank">Telangana Grameena Bank</option>
                      <option value="ICICI Bank">ICICI Bank</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-carbon-800 mb-1">UPI VPA Handle</label>
                    <input
                      type="text"
                      required
                      value={upiIdInput}
                      onChange={e => setUpiIdInput(e.target.value)}
                      className="w-full px-3 py-2 bg-surface-sage/40 border border-forest-200 rounded-xl text-xs font-mono text-carbon-900 focus:outline-none"
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold text-carbon-800 mb-1">Withdrawal Amount (₹)</label>
                    <input
                      type="number"
                      max={withdrawableUpi}
                      min="100"
                      required
                      value={withdrawAmt}
                      onChange={e => setWithdrawAmt(e.target.value)}
                      className="w-full px-3 py-2 bg-surface-sage/40 border border-forest-200 rounded-xl text-sm font-bold text-carbon-900 focus:outline-none"
                    />
                    <p className="text-[10px] text-agriText-subtle mt-1">Available balance: ₹{withdrawableUpi.toFixed(2)}</p>
                  </div>

                  <div className="flex gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowWithdrawModal(false)}
                      className="flex-1 py-2.5 bg-surface-sage border border-forest-200 text-carbon-800 rounded-xl text-xs font-bold hover:bg-forest-100"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={isTransferring}
                      className="flex-1 py-2.5 bg-primary text-white rounded-xl text-xs font-bold hover:bg-primary-hover flex items-center justify-center gap-1 shadow-sm"
                    >
                      <span>{isTransferring ? 'Processing...' : 'Confirm Demo Transfer'}</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </form>
              )}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
