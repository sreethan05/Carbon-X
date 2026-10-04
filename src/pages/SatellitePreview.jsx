import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Satellite, Lock, AlertTriangle, Activity, Layers, Sprout, RotateCcw } from 'lucide-react';
import { analyzeFarm, saveFarm } from '../services/api';
import { useAuth } from '../context/AuthContext';

export default function SatellitePreview() {
  const navigate = useNavigate();
  const { isAuthenticated } = useAuth();
  const [progress, setProgress] = useState(8);
  const [stage, setStage] = useState('Indexing Surface Rasters...');
  const [error, setError] = useState('');
  const [result, setResult] = useState(null);
  const [mrvLocked, setMrvLocked] = useState(false);
  const startedRef = useRef(false);

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;

    let parcel = null;
    let details = {};
    try { parcel = JSON.parse(localStorage.getItem('carbonx_farm_parcel') || 'null'); } catch { /* ignore */ }
    try { details = JSON.parse(localStorage.getItem('carbonx_farm_details') || '{}'); } catch { /* ignore */ }
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
        const farmName = `Survey ${parcel.surveyNumber} (${parcel.village})`;
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
        setTimeout(() => navigate('/verification-success'), 1600);
      } catch (err) {
        clearInterval(timer);
        setError(err.message || 'Satellite analysis failed. Please retry.');
      }
    })();

    return () => clearInterval(timer);
  }, [navigate, isAuthenticated]);

  const retry = () => {
    startedRef.current = false;
    setError('');
    setProgress(8);
    setStage('Indexing Surface Rasters...');
    // re-run by remounting via key trick: simplest is window reload of state
    window.location.reload();
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 flex flex-col items-center justify-center p-4 md:p-8">
      <div className="max-w-2xl w-full space-y-6">

        {/* HUD Scanner Box */}
        <div className="bg-[#1B4332] text-white border border-emerald-900 rounded-2xl p-8 text-center relative overflow-hidden shadow-xl">
          <div className="relative w-24 h-24 mx-auto mb-4">
            <div className="absolute inset-0 bg-emerald-400/20 rounded-full animate-ping" />
            <div className="absolute inset-0 border-2 border-emerald-400 rounded-full flex items-center justify-center bg-[#1B4332] shadow-inner">
              <Satellite className="w-10 h-10 text-emerald-300" />
            </div>
          </div>

          <span className="text-[10px] font-bold uppercase tracking-wider bg-[#2D6A4F] text-[#D1FAE5] border border-emerald-500/40 px-3 py-1 rounded-full inline-block mb-2">
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
                <span>{mrvLocked ? 'Scan Complete' : stage}</span>
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
            <div className={`mt-6 inline-flex items-center gap-2 px-5 py-2 rounded-full text-xs font-bold font-mono shadow-md border animate-in fade-in zoom-in duration-200 ${
              result.stage1.status === 'MATCH'
                ? 'bg-[#2D6A4F] border-emerald-400 text-[#D1FAE5]'
                : result.stage1.status === 'MISMATCH'
                  ? 'bg-amber-100 border-amber-400 text-amber-900'
                  : 'bg-slate-100 border-slate-300 text-slate-700'
            }`}>
              <Lock className="w-4 h-4" />
              <span>
                {result.stage1.status === 'MATCH' && 'LOCKED : APPROVED MRV RECORD'}
                {result.stage1.status === 'MISMATCH' && `PAUSED : ${result.stage1.reason}`}
                {result.stage1.status === 'UNREVIEWED' && 'LOCKED : NO SIGNATURE CHECK AVAILABLE'}
              </span>
            </div>
          )}
        </div>

        {/* 3-Column Real-Time Metric Ribbon */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-1">
            <div className="flex items-center gap-2 text-emerald-700 mb-1">
              <Sprout className="w-4 h-4" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Surface NDVI</span>
            </div>
            <p className="text-2xl font-extrabold text-slate-900 font-mono">{result ? result.ndvi.toFixed(2) : '—'}</p>
            <p className="text-[11px] text-emerald-700 font-semibold">{result ? `${result.vegetation_health} Vegetation` : 'Awaiting scan...'}</p>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-1">
            <div className="flex items-center gap-2 text-emerald-700 mb-1">
              <Activity className="w-4 h-4" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Biodiversity Index</span>
            </div>
            <p className="text-2xl font-extrabold text-slate-900 font-mono">{result ? `${(result.biodiversity_score / 10).toFixed(1)} / 10` : '—'}</p>
            <p className="text-[11px] text-emerald-700 font-semibold">{result ? `Score ${result.biodiversity_score} · ML Model` : 'Awaiting scan...'}</p>
          </div>

          <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-1">
            <div className="flex items-center gap-2 text-emerald-700 mb-1">
              <Layers className="w-4 h-4" />
              <span className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Annual Sequestration</span>
            </div>
            <p className="text-2xl font-extrabold text-slate-900 font-mono">{result ? `${result.carbon_tonnes.toFixed(2)} MT` : '—'}</p>
            <p className="text-[11px] text-emerald-700 font-semibold">{result ? `${result.total_credits} tradeable credits` : 'Awaiting scan...'}</p>
          </div>
        </div>

        {result && (
          <p className="text-center text-[11px] text-slate-500 font-semibold">
            Data source: {result.satellite_source} · Parcel area {result.area_hectares} ha
          </p>
        )}

      </div>
    </div>
  );
}
