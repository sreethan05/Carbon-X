import React, { useState, useEffect } from 'react';
import { WifiOff, AlertTriangle } from 'lucide-react';

export default function OfflineBanner() {
  const [isOffline, setIsOffline] = useState(!navigator.onLine);

  useEffect(() => {
    const handleOnline = () => setIsOffline(false);
    const handleOffline = () => setIsOffline(true);
    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);
    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  if (!isOffline) return null;

  return (
    <div className="bg-amber-500/90 text-white text-xs font-medium py-2 px-4 flex items-center justify-center gap-2 shadow-sm border-b border-amber-600 transition-all z-50">
      <WifiOff className="w-4 h-4 shrink-0" />
      <span>You're offline — showing cached demo data</span>
      <span className="bg-amber-700/60 px-2 py-0.5 rounded text-[10px] uppercase tracking-wider font-semibold">
        Offline Mode
      </span>
    </div>
  );
}
