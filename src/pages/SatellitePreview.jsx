import React, { useState, useEffect, useRef, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Satellite, Lock, AlertTriangle, Activity, Layers, Sprout,
  RotateCcw, ArrowRight, MapPin, ShieldCheck, Eye
} from 'lucide-react';
import { MapContainer, TileLayer, Polygon, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import { analyzeFarm, saveFarm } from '../services/api';
import { useAuth } from '../context/AuthContext';

function geojsonToLatLngs(geojson) {
  try {
    let coords = geojson?.geometry?.coordinates || geojson?.coordinates;
    if (!coords) return null;
    if (geojson?.geometry?.type === 'MultiPolygon' || geojson?.type === 'MultiPolygon') {
      coords = coords[0];
    }
    const ring = coords[0];
    if (!Array.isArray(ring) || ring.length < 3) return null;
    const pts = ring.map(([lng, lat]) => [lat, lng]);
    if (pts.length > 3 && pts[0][0] === pts[pts.length - 1][0] && pts[0][1] === pts[pts.length - 1][1]) {
      pts.pop();
    }
    return pts;
  } catch {
    return null;
  }
}

function FitParcelBounds({ points }) {
  const map = useMap();
  useEffect(() => {
    if (points && points.length >= 3) {
      try {
        const bounds = L.latLngBounds(points);
        if (bounds.isValid()) {
          map.fitBounds(bounds, { padding: [35, 35], maxZoom: 18 });
        }
      } catch {
        // ignore
      }
    }
  }, [points, map]);
  return null;
}

export default function SatellitePreview() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [progress, setProgress] = useState(8);
  const [stage, setStage] = useState('Indexing Surface Rasters...');
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [mrvLocked, setMrvLocked] = useState(false);
  const [activeOverlay, setActiveOverlay] = useState('ndvi'); // 'ndvi' | 'rgb'
  const startedRef = useRef(false);

  const parcel = useMemo(() => {
    try { return JSON.parse(localStorage.getItem('carbonx_farm_parcel') || 'null'); } catch { return null; }
  }, []);

  const details = useMemo(() => {
    try { return JSON.parse(localStorage.getItem('carbonx_farm_details') || '{}'); } catch { return {}; }
  }, []);

  const parcelPoints = useMemo(() => geojsonToLatLngs(parcel?.geojson), [parcel?.geojson]);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    if (!parcel || !parcel.geojson) {
      setError('No farm boundary found. Please draw your parcel on the map first.');
      return;
    }

    const steps = [
      ['Fetching Sentinel-2 rasters...', 30],
      ['Computing NDVI / EVI indices...', 55],
      ['Scoring biodiversity (ML model)...', 78],
      ['Estimating annual sequestration...', 92],
    ];
    let i = 0;
    const timer = setInterval(() => {
      if (i < steps.length) {
        setStage(steps[i][0]);
        setProgress(steps[i][1]);
        i += 1;
      }
    }, 900);

    (async () => {
      try {
        const farmName = `Survey ${parcel.surveyNumber || 'unregistered'} (${parcel.village || 'unknown village'})`;
        const analysis = await analyzeFarm(
          parcel.geojson,
          farmName,
          details.crop || 'Mixed Crop',
          details.irrigation || 'Drip'
        );
        if (!analysis || !analysis.success) {
          throw new Error((analysis && analysis.message) || 'Satellite analysis failed');
        }
        setResult(analysis);

        let savedFarm = null;
        if (isAuthenticated) {
          const flagged = Boolean(parcel.flaggedForFpo) || parcel.badge === 'PENDING';
          try {
            const saved = await saveFarm({
              name: farmName,
              geojson: parcel.geojson,
              crop_type: details.crop || 'Mixed Crop',
              irrigation: details.irrigation || 'Drip',
              ndvi: analysis.ndvi,
              evi: analysis.evi,
              carbon_tonnes: analysis.carbon_tonnes,
              biodiversity_score: analysis.biodiversity_score,
              tree_cover: analysis.tree_cover,
              soil_moisture: analysis.soil_moisture,
              vegetation_health: analysis.vegetation_health,
              ai_confidence: analysis.ai_confidence,
              satellite_source: analysis.satellite_source,
              area_hectares: analysis.area_hectares || parcel.areaHa,
              badge: parcel.badge,
              // Area-variance flagged parcels must not save as "Verified":
              // the backend keeps credits blocked until FPO review passes.
              status: flagged ? 'PENDING' : undefined,
              s2_scene: analysis.s2_scene || null,
              ci90_low: analysis.scan_estimate?.ci90?.low ?? null,
              ci90_high: analysis.scan_estimate?.ci90?.high ?? null,
            });
            if (saved && saved.success) savedFarm = saved.farm;
          } catch (e) {
            console.warn('save-farm failed', e);
          }
        }
        try {
          localStorage.setItem('carbonx_farm_result', JSON.stringify({ analysis, savedFarm, parcel, details }));
        } catch { /* ignore */ }

        setProgress(100);
        setStage('Scan Complete');
        setMrvLocked(true);
      } catch (err) {
        clearInterval(timer);
        setError(err.message || 'Satellite analysis failed. Please retry.');
      }
    })();

    return () => clearInterval(timer);
  }, [isAuthenticated, parcel, details]);

  const retry = () => {
    startedRef.current = false;
    setError('');
    setProgress(8);
    setStage('Indexing Surface Rasters...');
    window.location.reload();
  };

  const handleConfirm = () => {
    navigate('/verification-success');
  };

  // Formats nullable scan metrics without crashing or inventing values
  const fmt = (value, digits = 2, suffix = '') => {
    const n = Number(value);
    return Number.isFinite(n) ? `${n.toFixed(digits)}${suffix}` : '—';
  };

  // Determine vegetation color for NDVI index overlay
  const getNdviOverlayColor = (val) => {
    const ndvi = Number(val);
    if (!Number.isFinite(ndvi)) return { stroke: '#15803D', fill: '#22C55E' };
    if (ndvi >= 0.7) return { stroke: '#065F46', fill: '#10B981', label: 'Very High Biomass' };
    if (ndvi >= 0.5) return { stroke: '#15803D', fill: '#22C55E', label: 'Healthy Canopy' };
    if (ndvi >= 0.3) return { stroke: '#B45309', fill: '#EAB308', label: 'Moderate Canopy' };
    return { stroke: '#B91C1C', fill: '#EF4444', label: 'Sparse / Stressed' };
  };

  const ndviColor = getNdviOverlayColor(result?.ndvi);

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 flex flex-col items-center justify-center p-4 md:p-8">
      <div className="max-w-3xl w-full space-y-6">

        {/* HUD Scanner Box */}
        <div className="bg-[#0C2A18] text-white border border-emerald-900 rounded-2xl p-6 md:p-8 text-center relative overflow-hidden shadow-xl">
          <div className="relative w-20 h-20 mx-auto mb-3">
            <div className={`absolute inset-0 bg-emerald-400/20 rounded-full ${mrvLocked ? '' : 'animate-ping'}`} />
            <div className="absolute inset-0 border-2 border-emerald-400 rounded-full flex items-center justify-center bg-[#0C2A18] shadow-inner">
              <Satellite className="w-9 h-9 text-emerald-300" />
            </div>
          </div>

          <span className="text-[10px] font-bold uppercase tracking-wider bg-[#15803D] text-[#D1FAE5] border border-emerald-500/40 px-3 py-1 rounded-full inline-block mb-2">
            Sentinel-2 Multi-Spectral Scanner
          </span>
          <h1 className="text-2xl font-extrabold font-manrope text-white">Satellite MRV Analysis HUD</h1>
          <p className="text-xs text-emerald-100/80 mt-1 max-w-md mx-auto">
            Processing Band 8 (NIR) & Band 4 (Red) canopy surface rasters for parcel verification.
          </p>

          {error ? (
            <div className="mt-6 max-w-md mx-auto bg-rose-950/60 border border-rose-400/50 text-rose-100 rounded-xl p-4 text-xs font-semibold flex flex-col items-center gap-3">
              <span className="flex items-center gap-2"><AlertTriangle className="w-4 h-4" /> {error}</span>
              <div className="flex gap-2">
                <button onClick={retry} className="px-3 py-1.5 bg-rose-800 hover:bg-rose-700 rounded-lg font-bold flex items-center gap-1.5">
                  <RotateCcw className="w-3.5 h-3.5" /> Retry Scan
                </button>
                <button onClick={() => navigate('/farm-map')} className="px-3 py-1.5 bg-emerald-800 hover:bg-emerald-700 rounded-lg font-bold">
                  Back to Map
                </button>
              </div>
            </div>
          ) : (
            <div className="mt-6 max-w-md mx-auto space-y-2">
              <div className="flex justify-between items-center text-xs font-semibold text-emerald-200">
                <span>{mrvLocked ? 'Analysis Complete · Review & Confirm' : stage}</span>
                <span className="font-mono">{progress}%</span>
              </div>
              <div className="w-full bg-emerald-950/80 border border-emerald-700/50 h-3 rounded-full overflow-hidden">
                <div
                  className="bg-emerald-400 h-full rounded-full transition-all duration-500 ease-out"
                  style={{ width: `${progress}%` }}
                />
              </div>
            </div>
          )}

          {mrvLocked && result?.stage1 && (
            <div className={`mt-5 inline-flex items-center gap-2 px-5 py-2 rounded-full text-xs font-bold font-mono shadow-md border animate-in fade-in zoom-in duration-200 ${
              result.stage1.status === 'MATCH'
                ? 'bg-[#15803D] border-emerald-400 text-[#D1FAE5]'
                : result.stage1.status === 'MISMATCH'
                  ? 'bg-amber-100 border-amber-400 text-amber-900'
                  : 'bg-slate-100 border-slate-300 text-slate-700'
            }`}>
              <Lock className="w-4 h-4" />
              <span>
                {result.stage1.status === 'MATCH' && 'LOCKED : APPROVED MRV RECORD'}
                {result.stage1.status === 'MISMATCH' && `PAUSED : ${result.stage1.reason}`}
                {result.stage1.status === 'UNREVIEWED' && 'LOCKED : NO SIGNATURE CHECK AVAILABLE'}
                {!['MATCH', 'MISMATCH', 'UNREVIEWED'].includes(result.stage1.status) && (result.stage1.reason || `PAUSED : ${result.stage1.status}`)}
              </span>
            </div>
          )}
        </div>

        {/* Interactive Satellite Tile & Vegetation Index Overlay Map */}
        {parcelPoints && parcelPoints.length >= 3 && (
          <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden shadow-sm">
            <div className="px-4 py-3 bg-surface border-b border-slate-200 flex flex-wrap justify-between items-center gap-2 text-xs">
              <div className="flex items-center gap-2">
                <MapPin className="w-4 h-4 text-emerald-700" />
                <span className="font-bold text-slate-900">
                  Cadastral Satellite Overlay: Survey {parcel?.surveyNumber || '—'} ({parcel?.village || '—'})
                </span>
              </div>

              {/* Layer switch buttons */}
              <div className="flex items-center gap-1.5 bg-slate-100 p-1 rounded-xl border border-slate-200">
                <button
                  type="button"
                  onClick={() => setActiveOverlay('ndvi')}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all flex items-center gap-1 ${
                    activeOverlay === 'ndvi'
                      ? 'bg-emerald-700 text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Eye className="w-3.5 h-3.5" />
                  <span>NDVI Heatmap</span>
                </button>
                <button
                  type="button"
                  onClick={() => setActiveOverlay('rgb')}
                  className={`px-2.5 py-1 rounded-lg text-[11px] font-bold transition-all flex items-center gap-1 ${
                    activeOverlay === 'rgb'
                      ? 'bg-emerald-700 text-white shadow-xs'
                      : 'text-slate-600 hover:text-slate-900'
                  }`}
                >
                  <Satellite className="w-3.5 h-3.5" />
                  <span>True Color</span>
                </button>
              </div>
            </div>

            <div className="relative h-[320px] w-full">
              <MapContainer
                center={parcelPoints[0]}
                zoom={16}
                maxZoom={22}
                style={{ width: '100%', height: '100%' }}
                zoomControl={false}
              >
                <TileLayer
                  url="https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
                  subdomains={['mt0', 'mt1', 'mt2', 'mt3']}
                  maxZoom={22}
                  attribution="&copy; Google Satellite · Sentinel-2 SR"
                />
                <FitParcelBounds points={parcelPoints} />

                {activeOverlay === 'ndvi' ? (
                  <Polygon
                    positions={parcelPoints}
                    pathOptions={{
                      color: ndviColor.stroke,
                      fillColor: ndviColor.fill,
                      fillOpacity: 0.55,
                      weight: 3,
                    }}
                  />
                ) : (
                  <Polygon
                    positions={parcelPoints}
                    pathOptions={{
                      color: '#16A34A',
                      fillColor: '#16A34A',
                      fillOpacity: 0.15,
                      weight: 3,
                      dashArray: '6,4',
                    }}
                  />
                )}
              </MapContainer>

              {/* Floating Map Pill */}
              <div className="absolute bottom-3 left-3 z-[1000] bg-white/95 backdrop-blur-sm border border-slate-200 rounded-xl px-3 py-1.5 shadow-sm text-xs flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: activeOverlay === 'ndvi' ? ndviColor.fill : '#16A34A' }} />
                <span className="font-bold text-slate-800">
                  {activeOverlay === 'ndvi' ? `NDVI: ${fmt(result?.ndvi)} (${ndviColor.label})` : 'Natural Color Canopy'}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* 3-Column Real-Time Metric Ribbon */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-1">
            <div className="flex items-center gap-2 text-emerald-700 mb-1">
              <Sprout className="w-4 h-4" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Surface NDVI</span>
            </div>
            <p className="text-2xl font-extrabold text-slate-900 font-mono">{result ? fmt(result.ndvi) : '—'}</p>
            <p className="text-[11px] text-emerald-700 font-semibold">{result ? `${result.vegetation_health || 'Unknown'} Vegetation` : 'Awaiting scan...'}</p>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-1">
            <div className="flex items-center gap-2 text-emerald-700 mb-1">
              <Activity className="w-4 h-4" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Biodiversity Index</span>
            </div>
            <p className="text-2xl font-extrabold text-slate-900 font-mono">
              {result && Number.isFinite(Number(result.biodiversity_score))
                ? `${(Number(result.biodiversity_score) / 10).toFixed(1)} / 10`
                : '—'}
            </p>
            <p className="text-[11px] text-emerald-700 font-semibold">
              {result ? `${result.ml_source || 'ML model'}` : 'Awaiting scan...'}
            </p>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-1">
            <div className="flex items-center gap-2 text-emerald-700 mb-1">
              <Layers className="w-4 h-4" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Annual Sequestration</span>
            </div>
            <p className="text-2xl font-extrabold text-slate-900 font-mono">{result ? `${fmt(result.carbon_tonnes)} MT` : '—'}</p>
            <p className="text-[11px] text-emerald-700 font-semibold">
              {result
                ? (Number.isFinite(Number(result.total_credits)) ? `${result.total_credits} tradeable credits` : '— tradeable credits')
                : 'Awaiting scan...'}
            </p>
          </div>
        </div>

        {result && result.credits_available === false && (
          <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-xl p-4 text-xs font-semibold flex items-start gap-2.5">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>
              {result.message || 'No live satellite data was available for this scan, so no credits are issued.'}
              {' '}The parcel will be saved for FPO review.
            </span>
          </div>
        )}

        {/* Confirmation & Navigation Bar */}
        {mrvLocked && result && (
          <div className="bg-white border border-forest-100 rounded-2xl p-5 shadow-sm flex flex-col sm:flex-row justify-between items-center gap-4">
            <div className="text-xs text-slate-600 space-y-0.5 text-center sm:text-left">
              <p className="font-bold text-slate-900 flex items-center justify-center sm:justify-start gap-1.5">
                <ShieldCheck className="w-4 h-4 text-primary" />
                <span>Verification Scan Ready for Final Ledger Enrollment</span>
              </p>
              <p className="text-[11px] text-slate-500">
                Source: {result.satellite_source || 'Sentinel-2 SR'} · Plot area: {fmt(result.area_hectares)} ha
              </p>
            </div>

            <div className="flex items-center gap-2.5 w-full sm:w-auto">
              <button
                type="button"
                onClick={() => navigate('/farm-map', { state: parcel })}
                className="flex-1 sm:flex-initial px-4 py-2.5 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-xl text-xs font-bold transition-all"
              >
                Adjust Boundary
              </button>
              <button
                type="button"
                onClick={handleConfirm}
                className="flex-1 sm:flex-initial px-6 py-2.5 bg-primary hover:bg-primary-hover text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-1.5"
              >
                <span>Confirm &amp; Finalize</span>
                <ArrowRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}
