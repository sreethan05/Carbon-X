import React, { useState, useEffect } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { ArrowRight, CheckCircle2, AlertTriangle, ShieldCheck, Compass, Info, Check, Edit3, X } from 'lucide-react';
import VerificationBadge from '../components/VerificationBadge';
import LeafletMap from '../components/LeafletMap';
import { useAuth } from '../context/AuthContext';

export default function FarmMapRegistration() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();

  // Received state from land-verification step
  const navState = location.state || {};
  const surveyNumber = navState.surveyNumber || '124/A';
  const ownerName = navState.ownerName || user?.name || 'K. Ramesh';
  const village = navState.village || 'Pochampally';
  const registryAreaHa = navState.areaHa || 1.20;
  const tierCode = navState.tierCode || (surveyNumber === '124/A' ? '1A' : surveyNumber === '124/B' ? '1B' : '2');
  const initialBadge = navState.tier || (tierCode === '1A' ? 'REGISTRY' : tierCode === '1B' ? 'REGISTRY_DOC' : 'DOCUMENT');
  const isReadOnly = tierCode === '1A';

  // Live calculated state from map drawing
  const [drawnAreaHa, setDrawnAreaHa] = useState(registryAreaHa);
  const [assignedBadge, setAssignedBadge] = useState(initialBadge);
  const [showConfirmationModal, setShowConfirmationModal] = useState(false);
  const [showAdvisory, setShowAdvisory] = useState(true);

  // Compute variance & tolerance
  const areaDiffHa = Math.abs(drawnAreaHa - registryAreaHa);
  const variancePercent = registryAreaHa > 0 ? (areaDiffHa / registryAreaHa) * 100 : 0;
  const isWithinTolerance = variancePercent <= 20;

  useEffect(() => {
    // If mismatch is outside 20% tolerance, flag as advisory FPO review (without hard-blocking)
    if (!isWithinTolerance && tierCode !== '1A') {
      setAssignedBadge('PENDING');
    } else {
      setAssignedBadge(initialBadge);
    }
  }, [drawnAreaHa, registryAreaHa, isWithinTolerance, tierCode, initialBadge]);

  const [parcelGeojson, setParcelGeojson] = useState(null);

  const handleAreaCalculated = (res) => {
    if (res && res.area > 0) {
      setDrawnAreaHa(res.area);
    }
  };

  const handleFinalSubmit = () => {
    const parcel = {
      surveyNumber,
      ownerName,
      village,
      areaHa: drawnAreaHa,
      badge: assignedBadge,
      tierCode,
      flaggedForFpo: !isWithinTolerance,
      geojson: parcelGeojson,
    };
    try {
      localStorage.setItem('carbonx_farm_parcel', JSON.stringify(parcel));
    } catch (err) {
      console.warn('Could not persist parcel', err);
    }
    navigate('/farm-details', { state: parcel });
  };

  return (
    <div className="min-h-screen bg-surface font-inter text-agriText-main flex flex-col">

      {/* Top Header Bar */}
      <div className="bg-white border-b border-forest-100 px-4 md:px-8 py-3.5 shadow-xs flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold text-primary uppercase tracking-wider bg-surface-sage border border-forest-200 px-2.5 py-0.5 rounded-full">
              Tier {tierCode} Mapping Verification
            </span>
            <VerificationBadge badge={assignedBadge} showTier size="sm" />
          </div>
          <h1 className="text-lg font-extrabold text-carbon-900 font-manrope mt-1">
            Parcel Geometry: Survey {surveyNumber} ({village})
          </h1>
        </div>

        {/* Live Area Cross-Verification Display Bar */}
        <div className="bg-surface-sage/60 border border-forest-200 rounded-xl px-4 py-2.5 text-xs flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div>
              <span className="text-[10px] text-agriText-subtle font-semibold block uppercase tracking-wider">Registry/OCR Area</span>
              <span className="font-mono font-bold text-carbon-900">{registryAreaHa} ha</span>
            </div>
            <div className="h-6 border-r border-forest-200" />
            <div>
              <span className="text-[10px] text-agriText-subtle font-semibold block uppercase tracking-wider">Drawn Area</span>
              <span className="font-mono font-bold text-primary">{drawnAreaHa} ha</span>
            </div>
          </div>

          <div>
            {isWithinTolerance ? (
              <span className="text-emerald-800 font-bold bg-emerald-50 border border-emerald-200 px-3 py-1 rounded-full flex items-center gap-1.5">
                <Check className="w-3.5 h-3.5 text-emerald-700" />
                <span>Within tolerance ✓</span>
              </span>
            ) : (
              <span className="text-amber-800 font-bold bg-amber-50 border border-amber-200 px-3 py-1 rounded-full flex items-center gap-1.5">
                <AlertTriangle className="w-3.5 h-3.5 text-amber-700" />
                <span>Area mismatch — FPO review required</span>
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Main Map Workspace */}
      <div className="flex-1 p-4 md:p-6 space-y-4 max-w-6xl mx-auto w-full">

        {/* Mismatch Advisory Warning (Dismissible & Non-Blocking!) */}
        {!isWithinTolerance && showAdvisory && (
          <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 text-xs text-amber-900 flex items-start justify-between gap-3 shadow-xs">
            <div className="flex items-start gap-3">
              <AlertTriangle className="w-5 h-5 text-amber-700 shrink-0 mt-0.5" />
              <div className="flex-1">
                <h3 className="font-bold text-amber-900">Area Mismatch Advisory (&gt;20% Variance Detected)</h3>
                <p className="text-[11px] text-amber-800 mt-0.5">
                  Drawn area (<code className="font-mono font-bold">{drawnAreaHa} ha</code>) differs from record area (<code className="font-mono font-bold">{registryAreaHa} ha</code>) by {Math.round(variancePercent)}%. You can still submit; your farm will be queued for FPO review.
                </p>
              </div>
            </div>
            <button
              onClick={() => setShowAdvisory(false)}
              className="p-1 hover:bg-amber-100 rounded-lg text-amber-800 transition-colors"
              title="Dismiss Advisory"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* Interactive Leaflet Map Container */}
        <div className="z-0 relative h-[520px] rounded-2xl overflow-hidden shadow-card border border-forest-100">
          <LeafletMap
            readOnly={isReadOnly}
            onGeojsonDrawn={setParcelGeojson}
            onAreaCalculated={handleAreaCalculated}
            showHeatmapToggle={true}
            height="100%"
          />
        </div>

        {/* Action Bar */}
        <div className="bg-white border border-forest-100 rounded-2xl p-4 flex flex-col sm:flex-row justify-between items-center gap-4 shadow-card">
          <div className="text-xs text-agriText-muted">
            {isReadOnly ? (
              <span className="flex items-center gap-1.5 text-emerald-800 font-semibold">
                <ShieldCheck className="w-4 h-4 text-primary" />
                Cadastral geometry verified from Telangana Dharani Portal (Tier 1A).
              </span>
            ) : (
              <span>
                Draw polygon vertices on map to align with physical field bunds.
              </span>
            )}
          </div>

          <button
            onClick={() => setShowConfirmationModal(true)}
            className="w-full sm:w-auto px-6 py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl shadow-sm flex items-center justify-center gap-2 transition-all"
          >
            <span>Confirm Boundary & Proceed</span>
            <ArrowRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Confirmation Modal Overlay */}
      {showConfirmationModal && (
        <div className="fixed inset-0 z-50 bg-[#1B4332]/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white border border-forest-100 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl animate-in fade-in zoom-in duration-150">
            <div className="flex justify-between items-center border-b border-forest-100 pb-3">
              <div className="flex items-center gap-2">
                <ShieldCheck className="w-5 h-5 text-primary" />
                <h3 className="text-sm font-extrabold text-carbon-900 font-manrope">
                  Is this your land? Survey {surveyNumber}, {Math.round(drawnAreaHa * 2.471 * 10) / 10} acres, {village}
                </h3>
              </div>
              <button
                onClick={() => setShowConfirmationModal(false)}
                className="p-1 text-agriText-subtle hover:text-carbon-900 rounded-lg hover:bg-surface-sage"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="bg-surface-sage/50 border border-forest-200 rounded-xl p-4 space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-agriText-subtle font-semibold">Pattadar Owner:</span>
                <span className="font-bold text-carbon-900">{ownerName}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-agriText-subtle font-semibold">Survey Number:</span>
                <span className="font-mono font-bold text-primary">{surveyNumber}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-agriText-subtle font-semibold">Village / Mandal:</span>
                <span className="font-bold text-carbon-900">{village}</span>
              </div>
              <div className="flex justify-between border-t border-forest-200 pt-2">
                <span className="text-agriText-subtle font-semibold">Verified Area:</span>
                <span className="font-mono font-bold text-primary">{drawnAreaHa} ha ({Math.round(drawnAreaHa * 2.471 * 100) / 100} acres)</span>
              </div>
              <div className="flex justify-between items-center border-t border-forest-200 pt-2">
                <span className="text-agriText-subtle font-semibold">Assigned Tier Badge:</span>
                <VerificationBadge badge={assignedBadge} showTier size="sm" />
              </div>
            </div>

            {!isWithinTolerance && (
              <div className="bg-amber-50 border border-amber-200 rounded-xl p-3 text-[11px] text-amber-900">
                ⚠️ Notice: Area variance is outside ±20%. Your submission will be routed to your FPO coordinator for verification review.
              </div>
            )}

            <div className="flex gap-2">
              <button
                onClick={() => setShowConfirmationModal(false)}
                className="flex-1 py-2.5 bg-surface-sage border border-forest-200 text-carbon-800 text-xs font-bold rounded-xl hover:bg-forest-100 transition-all flex items-center justify-center gap-1.5"
              >
                <Edit3 className="w-3.5 h-3.5" />
                <span>Edit Polygon</span>
              </button>
              <button
                onClick={handleFinalSubmit}
                className="flex-1 py-2.5 bg-primary hover:bg-primary-hover text-white text-xs font-bold rounded-xl shadow-sm transition-all flex items-center justify-center gap-1.5"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Confirm & Submit</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
