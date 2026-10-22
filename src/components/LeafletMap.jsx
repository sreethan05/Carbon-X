import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import { MapContainer, TileLayer, Marker, Popup, Polyline, Polygon, useMapEvents, useMap } from 'react-leaflet';
import 'leaflet/dist/leaflet.css';
import L from 'leaflet';
import * as turf from '@turf/turf';

import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

const TILE_ERROR_FALLBACK = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='256' height='256' fill='%23132017'><rect width='256' height='256' fill='%23132017'/><text x='50%' y='48%' dominant-baseline='middle' text-anchor='middle' fill='%2322c55e' font-size='11' font-family='sans-serif'>🛰️ Satellite imagery</text><text x='50%' y='58%' dominant-baseline='middle' text-anchor='middle' fill='%2386efac' font-size='10' font-family='sans-serif'>unavailable at zoom</text></svg>";

function MapLifecycleHandler({ onMapReady }) {
  const map = useMap();

  useEffect(() => {
    if (onMapReady) onMapReady(map);

    // Initial resize to avoid grey tile bug
    const resizeTimer = setTimeout(() => {
      try {
        map.invalidateSize();
      } catch {
        // ignore
      }
    }, 150);

    const handleWindowResize = () => {
      try {
        map.invalidateSize();
      } catch {
        // ignore
      }
    };
    window.addEventListener('resize', handleWindowResize);

    return () => {
      clearTimeout(resizeTimer);
      window.removeEventListener('resize', handleWindowResize);
      try {
        map.stop();
        const container = map.getContainer();
        if (container && container._leaflet_id) {
          delete container._leaflet_id;
        }
      } catch {
        // ignore
      }
    };
  }, [map, onMapReady]);

  return null;
}

function FlyToLocation({ position }) {
  const map = useMap();
  useEffect(() => {
    if (position) {
      try {
        map.flyTo(position, 16, { duration: 1.5 });
      } catch {
        // ignore
      }
    }
    return () => {
      try {
        map.stop();
      } catch {
        // ignore
      }
    };
  }, [position, map]);
  return null;
}

function AutoFitBounds({ points }) {
  const map = useMap();
  const lastPointsKeyRef = useRef('');

  useEffect(() => {
    if (points && points.length >= 3) {
      const key = points.map(p => `${p[0].toFixed(5)},${p[1].toFixed(5)}`).join(';');
      if (key !== lastPointsKeyRef.current) {
        lastPointsKeyRef.current = key;
        try {
          const bounds = L.latLngBounds(points);
          if (bounds.isValid()) {
            map.fitBounds(bounds, { padding: [40, 40], maxZoom: 18 });
          }
        } catch {
          // ignore
        }
      }
    }
  }, [points, map]);

  return null;
}

function MapClickHandler({ readOnly, polygonMode, polygonPoints, setPolygonPoints, polygonClosed, setPolygonClosed, setPolygonMode, onComplete }) {
  const pointsRef = useRef(polygonPoints);
  pointsRef.current = polygonPoints;

  const modeRef = useRef(polygonMode);
  modeRef.current = polygonMode;

  const closedRef = useRef(polygonClosed);
  closedRef.current = polygonClosed;

  const readOnlyRef = useRef(readOnly);
  readOnlyRef.current = readOnly;

  useMapEvents({
    click(e) {
      if (readOnlyRef.current || !modeRef.current || closedRef.current) return;
      const latlng = [e.latlng.lat, e.latlng.lng];
      const currentPts = pointsRef.current;
      if (currentPts.length >= 3) {
        const first = currentPts[0];
        const dist = Math.sqrt(Math.pow(latlng[0] - first[0], 2) + Math.pow(latlng[1] - first[1], 2));
        if (dist < 0.0005) {
          setPolygonClosed(true);
          setPolygonMode(false);
          if (onComplete) onComplete(currentPts);
          return;
        }
      }
      setPolygonPoints(prev => [...prev, latlng]);
    }
  });
  return null;
}

// Calculate geodesic polygon area using turf or spherical fallback
function calculatePolygonAreaHa(pts) {
  if (!pts || pts.length < 3) return 0;

  try {
    const coords = [...pts.map(p => [p[1], p[0]]), [pts[0][1], pts[0][0]]];
    const poly = {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [coords] }
    };

    if (turf && turf.area) {
      const areaM2 = turf.area(poly);
      return Math.round((areaM2 / 10000) * 100) / 100;
    }
  } catch (err) {
    console.warn('Turf area calculation error, using spherical fallback', err);
  }

  // Spherical Shoelace Formula Fallback
  let areaDeg = 0;
  const n = pts.length;
  for (let i = 0; i < n; i++) {
    const j = (i + 1) % n;
    areaDeg += pts[i][1] * pts[j][0] - pts[j][1] * pts[i][0];
  }
  const areaM2 = Math.abs(areaDeg) / 2 * (111320 ** 2) * Math.cos((pts[0][0] * Math.PI) / 180);
  return Math.round((areaM2 / 10000) * 100) / 100;
}

export default function LeafletMap({
  readOnly = false,
  initialPoints = null,
  onGeojsonDrawn = null,
  onAreaCalculated = null,
  showHeatmapToggle = true,
  height = '60vh',
}) {
  const containerRef = useRef(null);
  const [search, setSearch] = useState('');
  const [flyTo, setFlyTo] = useState(null);
  const [polygonMode, setPolygonMode] = useState(false);
  // Never fabricate a boundary: start empty unless the caller supplies real
  // geometry (e.g., a locked cadastral registry polygon for Tier 1A).
  const [polygonPoints, setPolygonPoints] = useState(initialPoints || []);
  const [polygonClosed, setPolygonClosed] = useState(Boolean(initialPoints && initialPoints.length >= 3));
  // Only emit GeoJSON once the polygon comes from real input (registry
  // geometry or a user-drawn boundary) — a mount with no data must not
  // silently submit a placeholder square as the parcel.
  const [polygonTouched, setPolygonTouched] = useState(Boolean(initialPoints && initialPoints.length >= 3));
  const [status, setStatus] = useState(readOnly ? '🔒 Cadastral Boundary Locked (Tier 1A)' : '');
  const [heatmapActive, setHeatmapActive] = useState(false);

  // Outer container cleanup safeguard on unmount to prevent 'Map container is already initialized' error
  useEffect(() => {
    const container = containerRef.current;
    return () => {
      if (container) {
        const leafletContainer = container.querySelector('.leaflet-container');
        if (leafletContainer && leafletContainer._leaflet_id) {
          delete leafletContainer._leaflet_id;
        }
      }
    };
  }, []);

  useEffect(() => {
    if (initialPoints && initialPoints.length >= 3) {
      setPolygonPoints(initialPoints);
      setPolygonClosed(true);
      setPolygonTouched(true);
    }
  }, [initialPoints]);

  const emitGeojson = useCallback((pts) => {
    if (!pts || pts.length < 3) return;
    const coords = [...pts.map(p => [p[1], p[0]]), [pts[0][1], pts[0][0]]];
    const geojson = {
      type: 'Feature',
      geometry: { type: 'Polygon', coordinates: [coords] }
    };
    const ha = calculatePolygonAreaHa(pts);

    if (onGeojsonDrawn) onGeojsonDrawn(geojson);
    if (onAreaCalculated) onAreaCalculated({ area: ha, acres: Math.round(ha * 2.471 * 100) / 100, score: 84 });
  }, [onGeojsonDrawn, onAreaCalculated]);

  // Debounced area calculation and GeoJSON emission to prevent UI lockup during vertex manipulation
  useEffect(() => {
    if (polygonTouched && polygonClosed && polygonPoints.length >= 3) {
      const timer = setTimeout(() => {
        emitGeojson(polygonPoints);
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [polygonTouched, polygonClosed, polygonPoints, emitGeojson]);

  const startPolygon = () => {
    if (readOnly) return;
    setPolygonMode(true);
    setPolygonTouched(true);
    setPolygonPoints([]);
    setPolygonClosed(false);
    setStatus('Click map to draw farm vertices. Click near start point to close.');
    if (onGeojsonDrawn) onGeojsonDrawn(null);
  };

  const closePolygon = useCallback((pts = polygonPoints) => {
    if (pts.length >= 3) {
      setPolygonClosed(true);
      setPolygonMode(false);
      setStatus('Farm boundary closed!');
      emitGeojson(pts);
    } else {
      setStatus('Add at least 3 points first.');
    }
  }, [polygonPoints, emitGeojson]);

  const clearAll = () => {
    if (readOnly) return;
    setPolygonPoints([]);
    setPolygonClosed(false);
    setPolygonMode(false);
    setStatus('');
    if (onGeojsonDrawn) onGeojsonDrawn(null);
    if (onAreaCalculated) onAreaCalculated({ area: 0, acres: 0, score: 0 });
  };

  const searchLocation = async () => {
    if (!search.trim()) return;
    try {
      const res = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(search)}`);
      if (!res.ok) {
        setStatus('Search service unavailable');
        return;
      }
      const data = await res.json();
      if (Array.isArray(data) && data.length > 0) {
        setFlyTo([parseFloat(data[0].lat), parseFloat(data[0].lon)]);
        setStatus(`Location found: ${data[0].display_name.split(',')[0]}`);
      } else {
        setStatus('Location not found.');
      }
    } catch {
      setStatus('Search failed.');
    }
  };

  const handleMarkerDrag = useCallback((index) => (e) => {
    if (readOnly) return;
    const { lat, lng } = e.target.getLatLng();
    setPolygonPoints(prev => {
      const next = [...prev];
      next[index] = [lat, lng];
      return next;
    });
    setPolygonTouched(true);
    setStatus(`Vertex ${index + 1} adjusted (${lat.toFixed(5)}, ${lng.toFixed(5)})`);
  }, [readOnly]);

  // Memoize area calculation so typing in search does not trigger expensive turf calculations
  const currentAreaHa = useMemo(() => {
    return polygonClosed && polygonPoints.length >= 3 ? calculatePolygonAreaHa(polygonPoints) : 0;
  }, [polygonClosed, polygonPoints]);

  return (
    <div ref={containerRef} className="relative w-full rounded-2xl overflow-hidden border border-forest-100 shadow-card" style={{ height, minHeight: 360 }}>
      <MapContainer
        center={polygonPoints.length > 0 ? polygonPoints[0] : [17.385, 78.4867]}
        zoom={15}
        maxZoom={22}
        style={{ width: '100%', height: '100%' }}
        zoomControl={false}
      >
        <MapLifecycleHandler />
        <TileLayer
          url="https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"
          subdomains={['mt0', 'mt1', 'mt2', 'mt3']}
          maxZoom={22}
          attribution='&copy; <a href="https://www.google.com/maps" target="_blank" rel="noopener noreferrer">Google Maps</a> Satellite'
          errorTileUrl={TILE_ERROR_FALLBACK}
          eventHandlers={{
            tileerror: () => {
              // Gracefully handle tile loading error
            },
          }}
        />
        {flyTo && <FlyToLocation position={flyTo} />}
        {polygonPoints.length >= 3 && <AutoFitBounds points={polygonPoints} />}
        <MapClickHandler
          readOnly={readOnly}
          polygonMode={polygonMode}
          polygonPoints={polygonPoints}
          setPolygonPoints={setPolygonPoints}
          polygonClosed={polygonClosed}
          setPolygonClosed={setPolygonClosed}
          setPolygonMode={setPolygonMode}
          onComplete={closePolygon}
        />

        {polygonPoints.map((pt, i) => (
          <Marker
            key={`vertex-${i}`}
            position={pt}
            draggable={!readOnly}
            eventHandlers={{
              click: () => {
                if (!readOnly && polygonMode && !polygonClosed && polygonPoints.length >= 3 && i === 0) {
                  closePolygon();
                }
              },
              dragend: handleMarkerDrag(i),
            }}
          >
            <Popup>
              <div className="text-xs space-y-1">
                <span className="font-bold text-slate-900">Vertex {i + 1}</span>
                <p className="font-mono text-[11px] text-slate-600">
                  {pt[0].toFixed(5)}, {pt[1].toFixed(5)}
                </p>
                {!readOnly && (
                  <p className="text-[10px] text-emerald-700 font-semibold">
                    Drag pin to fine-tune boundary
                  </p>
                )}
              </div>
            </Popup>
          </Marker>
        ))}

        {polygonPoints.length > 1 && !polygonClosed && (
          <Polyline
            positions={polygonPoints}
            pathOptions={{ color: '#16A34A', weight: 3, dashArray: '6,4' }}
          />
        )}

        {polygonClosed && polygonPoints.length >= 3 && (
          <Polygon
            positions={polygonPoints}
            pathOptions={
              heatmapActive
                ? { color: '#DC2626', fillColor: '#16A34A', fillOpacity: 0.55, weight: 3 }
                : { color: readOnly ? '#14532D' : '#16A34A', fillColor: '#16A34A', fillOpacity: 0.3, weight: readOnly ? 4 : 3 }
            }
          />
        )}
      </MapContainer>

      {/* Top Search bar */}
      <div className="absolute top-3 left-3 z-[1000] flex gap-2 w-[calc(100%-110px)] max-w-xs">
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && searchLocation()}
          placeholder="Search village or Mandal..."
          className="flex-1 bg-white/95 backdrop-blur-sm border border-forest-200 rounded-xl px-3 py-1.5 text-xs text-carbon-900 shadow-sm focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <button
          onClick={searchLocation}
          className="bg-primary hover:bg-primary-hover text-white text-xs font-bold px-3 py-1.5 rounded-xl shadow-sm transition-all shrink-0"
        >
          Go
        </button>
      </div>

      {/* Top Right Controls: NDVI Heatmap Toggle & ReadOnly Badge */}
      <div className="absolute top-3 right-3 z-[1000] flex items-center gap-2">
        {showHeatmapToggle && (
          <button
            onClick={() => setHeatmapActive(!heatmapActive)}
            className={`px-3 py-1.5 rounded-xl text-xs font-bold shadow-sm transition-all border flex items-center gap-1.5 ${
              heatmapActive
                ? 'bg-emerald-700 text-white border-emerald-800'
                : 'bg-white/95 text-carbon-800 border-forest-200 hover:bg-surface-sage'
            }`}
          >
            <span>🌱 Boundary Overlay</span>
            {heatmapActive && <span className="w-2 h-2 rounded-full bg-emerald-300 animate-pulse" />}
          </button>
        )}
      </div>

      {/* Bottom Floating Live Turf Area Display */}
      {polygonClosed && currentAreaHa > 0 && (
        <div className="absolute bottom-16 left-3 z-[1000] bg-white/95 backdrop-blur-md border border-forest-200 rounded-xl px-3 py-2 shadow-sm flex items-center gap-2 text-xs">
          <span className="font-semibold text-agriText-muted">Live Area:</span>
          <span className="font-mono font-bold text-primary">{currentAreaHa} ha</span>
          <span className="text-[10px] text-agriText-subtle">
            ({Math.round(currentAreaHa * 2.471 * 100) / 100} acres)
          </span>
        </div>
      )}

      {/* Drawing Toolbar */}
      <div className="absolute bottom-3 left-1/2 -translate-x-1/2 z-[1000] flex items-center gap-2">
        {!readOnly && !polygonMode && (
          <button
            onClick={startPolygon}
            className="bg-primary hover:bg-primary-hover text-white text-xs font-bold px-4 py-2 rounded-xl shadow-md flex items-center gap-1.5 transition-all"
          >
            <span>⬠ Redraw Boundary</span>
          </button>
        )}

        {!readOnly && polygonMode && polygonPoints.length >= 3 && (
          <button
            onClick={closePolygon}
            className="bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold px-4 py-2 rounded-xl shadow-md transition-all"
          >
            ✓ Close Boundary
          </button>
        )}

        {!readOnly && (polygonPoints.length > 0 || polygonClosed) && (
          <button
            onClick={clearAll}
            className="bg-white/90 hover:bg-white border border-forest-200 text-carbon-800 text-xs font-bold px-3 py-2 rounded-xl shadow-sm transition-all"
          >
            ✕ Clear
          </button>
        )}

        {readOnly && (
          <div className="bg-primary/95 backdrop-blur-md text-white text-xs font-bold px-4 py-2 rounded-xl shadow-md flex items-center gap-1.5">
            <span>🔒 Cadastral Boundary (Tier 1A Read-Only)</span>
          </div>
        )}
      </div>

      {/* Status Pill */}
      {status && (
        <div className="absolute top-12 left-1/2 -translate-x-1/2 z-[1000] bg-carbon-900/80 backdrop-blur-md text-white text-[11px] px-3 py-1 rounded-full shadow-md text-center">
          {status}
        </div>
      )}
    </div>
  );
}
