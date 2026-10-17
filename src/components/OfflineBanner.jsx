import React, { useState, useEffect } from 'react';
import { WifiOff, RefreshCw, CheckCircle2 } from 'lucide-react';

export default function OfflineBanner() {
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [showReconnected, setShowReconnected] = useState(false);

  useEffect(() => {
    const handleOnline = () => {
      setIsOffline(false);
      setShowReconnected(true);
      const timer = setTimeout(() => setShowReconnected(false), 4000);
      return () => clearTimeout(timer);
    };
    const handleOffline = () => {
      setIsOffline(true);
      setShowReconnected(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  if (showReconnected) {
    return (
      <aside
        aria-live="polite"
        className="bg-emerald-600 text-white text-xs font-medium py-2 px-4 flex items-center justify-center gap-2 shadow-sm border-b border-emerald-700 transition-all z-50 animate-fade-in"
      >
        <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-200" />
        <span>Internet connection restored — live MRV and market data active</span>
      </aside>
    );
  }

  if (!isOffline) return null;

  return (
    <aside
      role="status"
      aria-live="polite"
      className="bg-amber-600 text-white text-xs font-medium py-2 px-4 flex items-center justify-between shadow-sm border-b border-amber-700 transition-all z-50"
    >
      <div className="flex items-center gap-2">
        <WifiOff className="w-4 h-4 shrink-0 text-amber-200" />
        <span>You're offline — live market and MRV data are paused; cached app shell is active</span>
        <span className="hidden sm:inline-block bg-amber-800/60 px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-semibold">
          Offline Mode
        </span>
      </div>
      <button
        type="button"
        onClick={() => window.location.reload()}
        className="flex items-center gap-1 bg-amber-700/90 hover:bg-amber-800 text-white px-2.5 py-1 rounded text-xs font-semibold transition-colors focus:ring-2 focus:ring-amber-300 outline-none"
        title="Retry connection"
      >
        <RefreshCw className="w-3 h-3" />
        <span>Retry</span>
      </button>
    </aside>
  );
}
