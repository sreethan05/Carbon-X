import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Search, ShieldCheck, FileText, CheckCircle2, ArrowRight, Loader2,
  Upload, ScanLine, AlertTriangle
} from 'lucide-react';
import VerificationBadge from '../components/VerificationBadge';
import { useAuth } from '../context/AuthContext';
import { parsePahaniDocument, lookupLandRegistry } from '../services/api';

export default function FarmOwnershipVerification() {
  const navigate = useNavigate();
  const { user } = useAuth();

  const [surveyInput, setSurveyInput] = useState('124/A');
  const [lookupError, setLookupError] = useState('');
  const [isSearching, setIsSearching] = useState(false);
  const [registryResult, setRegistryResult] = useState(null);
  const [searchDone, setSearchDone] = useState(false);
  const [isProceeding, setIsProceeding] = useState(false);

  // File upload state & Trust Engine Stepper
  const [pahaniFile, setPahaniFile] = useState(null);
  const [isProcessingPipeline, setIsProcessingPipeline] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [pipelineDone, setPipelineDone] = useState(false);
  const [parseResult, setParseResult] = useState(null);
  const [parseError, setParseError] = useState('');
  const pipelineTimerRef = useRef(null);

  useEffect(() => {
    return () => {
      if (pipelineTimerRef.current) {
        clearInterval(pipelineTimerRef.current);
      }
    };
  }, []);

  const trustChecklist = [
    { title: '1. OCR Text Extraction', desc: 'Survey Number, Owner Name, Registered Area' },
    { title: '2. EXIF & GPS Metadata Validation', desc: 'Validates camera coordinates against village bounds' },
    { title: '3. SHA-256 Perceptual Hash Check', desc: 'Performs duplicate document hash collision test' },
    { title: '4. Village Geocoding Cross-Check', desc: 'Cross-checks survey village boundaries' },
    { title: '5. Sentinel-2 Farmland Reality Check', desc: 'Confirms vegetation canopy (> 0.3 NDVI, < 0.1 flag)' },
    { title: '6. Fuzzy Profile Name Match', desc: 'Validates name match within 20% area threshold' }
  ];

  const handleRegistryLookup = async (e) => {
    if (e) e.preventDefault();
    if (isSearching) return;
    const survey = surveyInput.trim();
    setLookupError('');
    if (!survey) {
      setLookupError('Please enter a survey number.');
      return;
    }
    const SURVEY_REGEX = /^[a-zA-Z0-9\s/_\-.]+$/;
    if (!SURVEY_REGEX.test(survey)) {
      setLookupError('Enter a valid alphanumeric survey number (e.g. 124/A, 101/1).');
      return;
    }

    setIsSearching(true);
    setSearchDone(false);
    setRegistryResult(null);

    // Honest document-based fallback record (Tier 2) — used only when the
    // registry cannot provide a verdict, never to fake a registry match.
    const documentPath = (registryMessage, unavailable = false) => ({
      found: false,
      surveyNumber: survey,
      ownerName: user?.name || null,
      village: user?.village || null,
      mandal: user?.district || null,
      areaHa: null,
      tier: 'DOCUMENT',
      tierCode: '2',
      hasGeometry: false,
      geojson: null,
      registryMessage,
      unavailable,
    });

    try {
      const data = await lookupLandRegistry(survey);
      if (data && data.success && data.found) {
        const hasGeom = Boolean(data.registry_geometry_available) || Boolean(data.geojson);
        setRegistryResult({
          found: true,
          surveyNumber: data.survey_number || survey,
          ownerName: data.owner_name || user?.name || '—',
          village: data.village || '—',
          mandal: data.mandal || '—',
          areaHa: typeof data.area_ha === 'number' && !isNaN(data.area_ha) && data.area_ha > 0 ? data.area_ha : null,
          tier: hasGeom ? 'REGISTRY' : 'REGISTRY_DOC',
          tierCode: hasGeom ? '1A' : '1B',
          hasGeometry: hasGeom,
          geojson: data.geojson || null,
          registryMessage: null,
          unavailable: false,
        });
      } else if (data && data.success && data.found === false) {
        setRegistryResult(documentPath('Survey number not found in the government registry extract — proceeding with document-based verification (Tier 2).'));
      } else {
        setRegistryResult(documentPath(
          (data && data.message) || 'Registry lookup is currently unavailable — proceeding with document-based verification (Tier 2).',
          true,
        ));
      }
    } catch (err) {
      console.warn('Registry lookup failed', err);
      setRegistryResult(documentPath('Registry service unreachable — proceeding with document-based verification (Tier 2).', true));
    } finally {
      setIsSearching(false);
      setSearchDone(true);
    }
  };

  const handlePahaniUpload = (e) => {
    if (isProcessingPipeline) return;
    const file = e.target.files?.[0];
    if (!file) return;
    setPahaniFile(file);
    runPipeline(file);
  };

  const runPipeline = async (file) => {
    if (isProcessingPipeline) return;
    setIsProcessingPipeline(true);
    setActiveStep(0);
    setPipelineDone(false);
    setParseResult(null);
    setParseError('');

    // Animate the checklist while the real OCR pipeline runs
    if (pipelineTimerRef.current) clearInterval(pipelineTimerRef.current);
    pipelineTimerRef.current = setInterval(() => {
      setActiveStep((prev) => Math.min(prev + 1, trustChecklist.length - 1));
    }, 500);

    try {
      const data = await parsePahaniDocument(file);
      if (pipelineTimerRef.current) {
        clearInterval(pipelineTimerRef.current);
        pipelineTimerRef.current = null;
      }
      setActiveStep(trustChecklist.length - 1);
      setIsProcessingPipeline(false);
      if (data && (data.success || data.extracted_fields || data.fields)) {
        setParseResult(data);
        setPipelineDone(true);

        const fields = data.extracted_fields || data.fields || {};
        if (fields.survey_number && (!surveyInput || surveyInput === '124/A')) {
          setSurveyInput(fields.survey_number);
        }

        // If no registry lookup has been performed yet, initialize metadata display from document fields
        if (!registryResult && (fields.survey_number || fields.pattadar_name || fields.village)) {
          const areaHa = typeof fields.total_extent_hectares === 'number' && !isNaN(fields.total_extent_hectares) && fields.total_extent_hectares > 0
            ? fields.total_extent_hectares
            : typeof fields.total_extent_acres === 'number' && !isNaN(fields.total_extent_acres) && fields.total_extent_acres > 0
              ? Math.round(fields.total_extent_acres * 0.404686 * 100) / 100
              : null;
          setRegistryResult({
            found: false,
            surveyNumber: fields.survey_number || surveyInput || 'Document-Verified',
            ownerName: fields.pattadar_name || user?.name || '—',
            village: fields.village || user?.village || '—',
            mandal: fields.mandal || user?.district || '—',
            areaHa,
            tier: 'DOCUMENT',
            tierCode: '2',
            hasGeometry: false,
            geojson: null,
            registryMessage: 'Extracted from uploaded Telangana Pahani / RoR 1B document (Tier 2 Document-Verified).',
            unavailable: false,
            crop: fields.crop_name || null,
            irrigation: fields.irrigation_source || null,
          });
          setSearchDone(true);
        }
      } else {
        setParseError((data && (data.message || data.detail)) || 'Document parsing failed — verify the file and retry.');
      }
    } catch (err) {
      if (pipelineTimerRef.current) {
        clearInterval(pipelineTimerRef.current);
        pipelineTimerRef.current = null;
      }
      setIsProcessingPipeline(false);
      const msg = err?.status === 401 || err?.message === 'Not authenticated'
        ? 'Please sign in first so your document can be verified against your account.'
        : 'Document service unreachable. You can continue and upload from a stronger network.';
      setParseError(msg);
    }
  };

  const proceedToMapping = () => {
    if (!registryResult || isProceeding) return;
    setIsProceeding(true);

    const fields = parseResult?.extracted_fields || parseResult?.fields || {};
    const statePayload = {
      surveyNumber: registryResult.surveyNumber || surveyInput,
      ownerName: registryResult.ownerName || user?.name || null,
      village: registryResult.village || user?.village || '',
      areaHa: registryResult.areaHa ?? null,
      tierCode: registryResult.tierCode,
      tier: registryResult.tier,
      hasGeometry: registryResult.hasGeometry,
      geojson: registryResult.geojson,
      pahaniUploaded: Boolean(pahaniFile),
      crop: fields.crop_name || registryResult.crop || null,
      irrigation: fields.irrigation_source || registryResult.irrigation || null,
    };

    try {
      localStorage.setItem('carbonx_land_verification', JSON.stringify(statePayload));
    } catch {
      // ignore
    }

    navigate('/farm-map', { state: statePayload });
  };

  return (
    <div className="min-h-screen bg-[#F8FAF8] font-inter text-slate-900 py-8 px-4 md:px-10">
      <div className="max-w-7xl mx-auto space-y-6">

        {/* Page Header */}
        <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 flex flex-col md:flex-row justify-between items-start md:items-center gap-4">
          <div>
            <span className="text-xs font-semibold text-emerald-800 uppercase tracking-wider bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full inline-block mb-1">
              Step 1: Land Verification & Registry Lookup
            </span>
            <h1 className="text-2xl font-extrabold text-slate-900 font-manrope">Farm Ownership & Deed Verification</h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Pilot verification against uploaded Pahani / RoR 1B records and the platform's curated registry extract — not a live government registry lookup.
            </p>
          </div>

          {registryResult && <VerificationBadge badge={registryResult.tier} showTier size="lg" />}
        </div>

        {/* 50/50 Split Desktop Layout */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

          {/* Left Column: Registry Search & Trust Engine Stepper */}
          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-6">
            <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <ShieldCheck className="w-5 h-5 text-emerald-700" />
              <span>1. Survey Number Registry Lookup</span>
            </h2>

            <form onSubmit={handleRegistryLookup} className="space-y-3">
              <label className="block text-xs font-bold text-slate-700">Survey / Passbook Number</label>
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={surveyInput}
                    disabled={isSearching}
                    onChange={e => setSurveyInput(e.target.value)}
                    placeholder="e.g. 124/A, 101/A, 102/B"
                    className="w-full pl-9 pr-3 py-2.5 bg-slate-50 border border-slate-200 rounded-lg text-xs font-mono text-slate-900 focus:outline-none focus:border-emerald-600 disabled:opacity-50"
                    required
                  />
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
                </div>
                <button
                  type="submit"
                  disabled={isSearching}
                  className="px-5 py-2.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs font-bold rounded-lg shadow-sm flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Search className="w-4 h-4" />}
                  <span>{isSearching ? 'Looking up…' : 'Lookup'}</span>
                </button>
              </div>
              {lookupError && (
                <p className="text-[11px] text-rose-700 font-semibold bg-rose-50 border border-rose-200 rounded-lg p-2 flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                  <span>{lookupError}</span>
                </p>
              )}
            </form>

            <hr className="border-slate-100" />

            {/* Document Dropzone & Trust Pipeline */}
            <div className="space-y-4">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-emerald-700" />
                <span>2. Pahani Document Drop-Zone & Verification</span>
              </h2>

              <div className="border-2 border-dashed border-slate-300 rounded-xl p-6 text-center hover:border-emerald-600 bg-[#F8FAF8] transition-colors">
                <input
                  type="file"
                  accept="image/*,.pdf"
                  disabled={isProcessingPipeline}
                  onChange={handlePahaniUpload}
                  id="doc-upload"
                  className="hidden"
                />
                <label
                  htmlFor="doc-upload"
                  className={isProcessingPipeline ? "cursor-not-allowed opacity-60 space-y-2 block" : "cursor-pointer space-y-2 block"}
                >
                  <Upload className="w-8 h-8 text-emerald-700 mx-auto" />
                  <p className="text-xs font-bold text-slate-900">
                    {pahaniFile ? pahaniFile.name : 'Upload Telangana Pahani / RoR 1B Document'}
                  </p>
                  <p className="text-[10px] text-slate-500">
                    {isProcessingPipeline ? 'Processing document…' : 'Click to upload PNG, JPG, or PDF'}
                  </p>
                </label>
              </div>

              {/* Compact Pipeline Status Bar Card */}
              {(isProcessingPipeline || pipelineDone) && (
                <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 space-y-3">
                  <div className="flex justify-between items-center text-xs">
                    <div className="flex items-center gap-2">
                      {pipelineDone ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-700" />
                      ) : (
                        <Loader2 className="w-4 h-4 text-emerald-700 animate-spin" />
                      )}
                      <span className="font-bold text-emerald-950">
                        {pipelineDone ? 'Document OCR Preview Complete' : `Reading document ${activeStep + 1} of ${trustChecklist.length}`}
                      </span>
                    </div>
                    <span className="text-[11px] font-mono font-bold text-emerald-800">
                      {pipelineDone ? '100%' : `${Math.round(((activeStep + 1) / trustChecklist.length) * 100)}%`}
                    </span>
                  </div>

                  {/* Progress Bar */}
                  <div className="w-full bg-emerald-200/60 h-2 rounded-full overflow-hidden">
                    <div
                      className="bg-emerald-600 h-full rounded-full transition-all duration-300"
                      style={{ width: pipelineDone ? '100%' : `${((activeStep + 1) / trustChecklist.length) * 100}%` }}
                    />
                  </div>

                  <p className="text-[11px] text-emerald-800 font-medium">
                    {pipelineDone
                      ? 'Document text was extracted. Full ownership, duplicate, and fraud checks run only when you submit the verification request.'
                      : trustChecklist[Math.min(activeStep, trustChecklist.length - 1)].title}
                  </p>

                  {parseError && (
                    <p className="text-[11px] text-rose-700 font-bold bg-rose-50 border border-rose-200 rounded-lg p-2">
                      {parseError}
                    </p>
                  )}

                  {parseResult && (
                    <div className="bg-white border border-emerald-100 rounded-lg p-3 space-y-1">
                      <p className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">Extracted Document Fields</p>
                      {Object.entries(parseResult.extracted_fields || parseResult.fields || {}).filter(([, v]) => v).slice(0, 8).map(([k, v]) => (
                        <div key={k} className="flex justify-between text-[11px]">
                          <span className="text-slate-500 font-semibold capitalize">{k.replace(/_/g, ' ')}:</span>
                          <span className="font-mono font-bold text-slate-900">{String(v)}</span>
                        </div>
                      ))}
                      {Array.isArray(parseResult.missing_fields) && parseResult.missing_fields.length > 0 && (
                        <p className="text-[10px] text-amber-700 font-semibold pt-1">
                          Not detected: {parseResult.missing_fields.join(', ')}
                        </p>
                      )}
                    </div>
                  )}
                </div>
              )}

              {!isProcessingPipeline && !pipelineDone && (
                <button
                  type="button"
                  onClick={() => {
                    if (pahaniFile) {
                      runPipeline(pahaniFile);
                    } else {
                      setParseError('Upload a Pahani / RoR document first — the Trust Engine reads the actual file.');
                    }
                  }}
                  className="w-full py-2.5 bg-[#0C2A18] hover:bg-[#15803D] text-white rounded-lg text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2"
                >
                  <ScanLine className="w-4 h-4" />
                  <span>Run Automated Trust Engine Check</span>
                </button>
              )}

              {!isProcessingPipeline && !pipelineDone && parseError && (
                <p className="text-[11px] text-rose-700 font-bold bg-rose-50 border border-rose-200 rounded-lg p-2">
                  {parseError}
                </p>
              )}
            </div>
          </div>

          {/* Right Column: Extracted Record Metadata & Forward Action */}
          <div className="bg-white border border-slate-200 shadow-sm rounded-xl p-6 space-y-6 flex flex-col justify-between">
            <div className="space-y-6">
              <h2 className="text-base font-bold text-slate-900 flex items-center gap-2">
                <FileText className="w-5 h-5 text-emerald-700" />
                <span>Extracted Record Metadata</span>
              </h2>

              {searchDone && registryResult ? (
                <div className="space-y-4">
                  {registryResult.registryMessage && (
                    <p className={`text-[11px] font-semibold rounded-lg p-2.5 border leading-relaxed ${
                      registryResult.unavailable ? 'text-rose-800 bg-rose-50 border-rose-200' : 'text-amber-900 bg-amber-50 border-amber-200'
                    }`}>
                      {registryResult.registryMessage}
                    </p>
                  )}
                  <div className="bg-emerald-50 border border-emerald-200 rounded-xl p-4 flex items-center justify-between">
                    <div>
                      <span className="text-[10px] font-bold text-emerald-800 uppercase tracking-wider block mb-1">
                        Assigned Verification Badge
                      </span>
                      <VerificationBadge badge={registryResult.tier} showTier size="lg" />
                    </div>
                    <div className="text-right">
                      <p className="text-[10px] font-semibold text-slate-500">Benchmark Price</p>
                      <p className="text-sm font-bold text-emerald-800">
                        {registryResult.tier === 'REGISTRY' ? 'INR 340 / credit' : registryResult.tier === 'REGISTRY_DOC' ? 'INR 320 / credit' : 'INR 310 / credit'}
                      </p>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4 bg-[#F8FAF8] p-4 rounded-xl border border-slate-200 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-500 font-semibold block">Pattadar Owner</span>
                      <span className="font-bold text-slate-900">{registryResult.ownerName || '—'}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 font-semibold block">Survey Number</span>
                      <span className="font-mono font-bold text-emerald-800">{registryResult.surveyNumber}</span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 font-semibold block">Village & Mandal</span>
                      <span className="font-bold text-slate-900">
                        {[registryResult.village, registryResult.mandal].filter(Boolean).join(', ') || '—'}
                      </span>
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 font-semibold block">Recorded Area</span>
                      <span className="font-bold text-slate-900">
                        {typeof registryResult.areaHa === 'number' && !isNaN(registryResult.areaHa) && registryResult.areaHa > 0
                          ? `${registryResult.areaHa} ha (${Math.round(registryResult.areaHa * 2.471 * 100) / 100} Acres)`
                          : '— (no area on record)'}
                      </span>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="bg-[#F8FAF8] border border-slate-200 rounded-xl p-6 text-center text-xs text-slate-500">
                  Lookup a survey number or upload Pahani document to display extracted metadata.
                </div>
              )}
            </div>

            {searchDone && registryResult && (
              <button
                onClick={proceedToMapping}
                disabled={isProceeding}
                className="w-full py-3 bg-[#0C2A18] hover:bg-[#15803D] disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-xl text-xs font-bold transition-all shadow-sm flex items-center justify-center gap-2 mt-6"
              >
                {isProceeding ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                <span>{isProceeding ? 'Preparing Map Workspace…' : 'Proceed to Satellite Boundary Mapping'}</span>
                {!isProceeding && <ArrowRight className="w-4 h-4" />}
              </button>
            )}
          </div>

        </div>
      </div>
    </div>
  );
}
