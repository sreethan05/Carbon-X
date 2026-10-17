import React, { useState, useEffect } from 'react';
import { Download, X, Smartphone, ShieldCheck } from 'lucide-react';

export default function InstallPrompt() {
  const [deferredPrompt, setDeferredPrompt] = useState(null);
  const [showPrompt, setShowPrompt] = useState(false);

  useEffect(() => {
    // Check if app is already running in standalone PWA mode
    const isStandalone =
      window.matchMedia('(display-mode: standalone)').matches ||
      window.navigator.standalone === true;

    if (isStandalone) return;

    // Check if dismissed recently (within 7 days)
    const dismissedTime = localStorage.getItem('carbonx_install_dismissed');
    if (dismissedTime && Date.now() - parseInt(dismissedTime, 10) < 7 * 24 * 60 * 60 * 1000) {
      return;
    }

    const handleBeforeInstallPrompt = (e) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setShowPrompt(true);
    };

    const handleAppInstalled = () => {
      setShowPrompt(false);
      setDeferredPrompt(null);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
    window.addEventListener('appinstalled', handleAppInstalled);

    return () => {
      window.removeEventListener('beforeinstallprompt', handleBeforeInstallPrompt);
      window.removeEventListener('appinstalled', handleAppInstalled);
    };
  }, []);

  const handleInstall = async () => {
    if (!deferredPrompt) return;
    deferredPrompt.prompt();
    try {
      const choice = await deferredPrompt.userChoice;
      if (choice.outcome === 'accepted') {
        setShowPrompt(false);
        setDeferredPrompt(null);
      }
    } catch {
      setShowPrompt(false);
    }
  };

  const handleDismiss = () => {
    setShowPrompt(false);
    try {
      localStorage.setItem('carbonx_install_dismissed', Date.now().toString());
    } catch {
      /* ignore storage access restrictions */
    }
  };

  if (!showPrompt) return null;

  return (
    <div
      role="dialog"
      aria-labelledby="pwa-install-title"
      aria-describedby="pwa-install-desc"
      className="fixed bottom-16 md:bottom-4 right-4 left-4 sm:left-auto sm:w-96 z-50 bg-forest-900 text-white rounded-2xl shadow-2xl border border-forest-700/60 p-4 transition-all animate-in fade-in slide-in-from-bottom-4"
    >
      <div className="flex items-start gap-3">
        <div className="w-10 h-10 rounded-xl bg-forest-800 flex items-center justify-center shrink-0 border border-forest-600/40">
          <Smartphone className="w-5 h-5 text-emerald-400" />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between gap-2">
            <h4 id="pwa-install-title" className="text-sm font-bold text-white flex items-center gap-1.5">
              Install CarbonX App
              <span className="inline-flex items-center gap-0.5 text-[10px] font-medium text-emerald-300 bg-emerald-950 px-1.5 py-0.5 rounded border border-emerald-800">
                <ShieldCheck className="w-2.5 h-2.5" /> MRV
              </span>
            </h4>
            <button
              type="button"
              onClick={handleDismiss}
              className="text-forest-400 hover:text-white p-1 rounded-lg transition-colors"
              aria-label="Dismiss install prompt"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <p id="pwa-install-desc" className="text-xs text-forest-200 mt-1 leading-relaxed">
            Install on your phone or desktop for one-tap field mapping, offline verification, and live credit updates.
          </p>

          <div className="mt-3 flex items-center gap-2">
            <button
              type="button"
              onClick={handleInstall}
              className="flex-1 inline-flex items-center justify-center gap-1.5 bg-emerald-500 hover:bg-emerald-400 text-forest-950 font-bold text-xs py-2 px-3 rounded-xl shadow transition-all active:scale-95"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Install App</span>
            </button>
            <button
              type="button"
              onClick={handleDismiss}
              className="text-xs font-semibold text-forest-300 hover:text-white px-3 py-2 rounded-xl transition-colors"
            >
              Not now
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
