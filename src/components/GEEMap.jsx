import { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
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

/**
 * Google Earth Engine–backed farm mapper (satellite + labels, draw + search).
 * Same map stack as the legacy frontend/ MapPage — not the basic Leaflet-only map.
 */
export default function GEEMap({
  onGeojsonDrawn,
  onAreaCalculated,
  height = '65vh',
  minHeight = 340,
}) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const drawLayerRef = useRef(null);
  const drawingRef = useRef(false);
  const polygonModeRef = useRef(false);
  const currentPolylineRef = useRef(null);
  const tempLineRef = useRef(null);
  const searchMarkerRef = useRef(null);
  const freeDrawPointsRef = useRef([]);
  const polygonPointsRef = useRef([]);
  const areaDebounceTimerRef = useRef(null);

  const [searchText, setSearchText] = useState('');
  const [status, setStatus] = useState('');
  const [placeName, setPlaceName] = useState('');

  const emitGeojson = useCallback((geojson) => {
    if (areaDebounceTimerRef.current) {
      clearTimeout(areaDebounceTimerRef.current);
      areaDebounceTimerRef.current = null;
    }

    if (!geojson) {
      if (onGeojsonDrawn) onGeojsonDrawn(null);
      if (onAreaCalculated) onAreaCalculated({ area: 0, score: 0, ndvi: 0 });
      return;
    }
    if (onGeojsonDrawn) onGeojsonDrawn(geojson);

    // Debounce area calculation to avoid jank during high-frequency drawing / point additions
    areaDebounceTimerRef.current = setTimeout(() => {
      let areaHa = 0;
      try {
        if (turf && turf.area) {
          const areaM2 = turf.area(geojson);
          areaHa = Math.round((areaM2 / 10000) * 100) / 100;
        }
      } catch {
        areaHa = 0;
      }

      if (areaHa <= 0 && geojson.geometry?.coordinates?.[0]) {
        const ring = geojson.geometry.coordinates[0];
        const closedRing = ring[0]?.[0] === ring[ring.length - 1]?.[0] && ring[0]?.[1] === ring[ring.length - 1]?.[1]
          ? ring
          : [...ring, ring[0]];
        const latMid = closedRing
          .slice(0, -1)
          .reduce((sum, [, lat]) => sum + lat, 0) / Math.max(closedRing.length - 1, 1);
        const metersPerLngDegree = 111320 * Math.cos((latMid * Math.PI) / 180);
        const metersPerLatDegree = 110540;
        const projected = closedRing.map(([lng, lat]) => [lng * metersPerLngDegree, lat * metersPerLatDegree]);
        let areaM2 = 0;
        for (let i = 0; i < projected.length - 1; i++) {
          areaM2 += projected[i][0] * projected[i + 1][1] - projected[i + 1][0] * projected[i][1];
        }
        areaHa = Math.round((Math.abs(areaM2) / 20000) * 100) / 100;
      }

      if (onAreaCalculated) {
        onAreaCalculated({ area: areaHa, score: 0, ndvi: 0 });
      }
    }, 150);
  }, [onGeojsonDrawn, onAreaCalculated]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    // Clean up any stale map instance or container leaflet ID before initializing
    if (mapRef.current) {
      try {
        mapRef.current.remove();
      } catch (err) {
        console.warn('Map cleanup error:', err);
      }
      mapRef.current = null;
    }

    if (container._leaflet_id) {
      delete container._leaflet_id;
    }

    const map = L.map(container, {
      center: [20.5937, 78.9629],
      zoom: 5,
      zoomControl: true,
      maxZoom: 22,
    });
    mapRef.current = map;

    const tileLayer = L.tileLayer('https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}', {
      subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
      maxZoom: 22,
      attribution: '© <a href="https://www.google.com/maps" target="_blank" rel="noopener noreferrer">Google Maps</a> · GEE analysis layer',
      errorTileUrl: TILE_ERROR_FALLBACK,
    });
    tileLayer.on('tileerror', () => {
      // Gracefully handle tile loading error without breaking map controls
    });
    tileLayer.addTo(map);

    drawLayerRef.current = L.layerGroup().addTo(map);

    // Initial resize to avoid grey tile bug
    const resizeTimer = setTimeout(() => {
      try {
        map.invalidateSize();
      } catch {
        // ignore
      }
    }, 150);

    const handleResize = () => {
      try {
        map.invalidateSize();
      } catch {
        // ignore
      }
    };
    window.addEventListener('resize', handleResize);

    return () => {
      clearTimeout(resizeTimer);
      window.removeEventListener('resize', handleResize);
      if (areaDebounceTimerRef.current) {
        clearTimeout(areaDebounceTimerRef.current);
      }
      if (mapRef.current) {
        try {
          mapRef.current.stop();
          mapRef.current.remove();
        } catch (err) {
          console.warn('Error removing map instance:', err);
        }
        mapRef.current = null;
      }
      if (container) {
        delete container._leaflet_id;
      }
    };
  }, []);

  const searchLocation = async () => {
    if (!searchText.trim() || !mapRef.current) return;
    setStatus('Searching…');
    try {
      const params = new URLSearchParams({
        q: searchText,
        format: 'json',
        limit: '1',
        addressdetails: '1',
      });
      const res = await fetch(`https://nominatim.openstreetmap.org/search?${params}`);
      if (!res.ok) {
        setStatus('Search service unavailable');
        return;
      }
      const data = await res.json();
      if (!Array.isArray(data) || !data.length) {
        setStatus('Location not found');
        return;
      }
      const place = data[0];
      const lat = parseFloat(place.lat);
      const lon = parseFloat(place.lon);
      const label = place.display_name?.split(',').slice(0, 3).join(', ') || searchText;
      setPlaceName(label);
      mapRef.current.flyTo([lat, lon], 16, { duration: 1.5 });

      if (searchMarkerRef.current && drawLayerRef.current) {
        drawLayerRef.current.removeLayer(searchMarkerRef.current);
      }
      searchMarkerRef.current = L.marker([lat, lon]).addTo(drawLayerRef.current).bindPopup(label);
      setStatus(label);
    } catch {
      setStatus('Search failed');
    }
  };

  const clearAll = () => {
    const map = mapRef.current;
    if (map) {
      map.off('mousedown mousemove mouseup click');
      map.dragging.enable();
    }
    if (containerRef.current) containerRef.current.style.cursor = 'grab';
    drawLayerRef.current?.clearLayers();
    tempLineRef.current = null;
    currentPolylineRef.current = null;
    searchMarkerRef.current = null;
    polygonPointsRef.current = [];
    freeDrawPointsRef.current = [];
    drawingRef.current = false;
    polygonModeRef.current = false;
    setPlaceName('');
    setStatus('');
    emitGeojson(null);
  };

  const startDrawing = () => {
    const map = mapRef.current;
    if (!map) return;
    drawingRef.current = true;
    polygonModeRef.current = false;
    freeDrawPointsRef.current = [];
    map.dragging.disable();
    if (containerRef.current) containerRef.current.style.cursor = 'crosshair';

    map.off('mousedown mousemove mouseup click');
    map.on('mousedown', (e) => {
      if (!drawingRef.current) return;
      freeDrawPointsRef.current = [e.latlng];
      currentPolylineRef.current = L.polyline(freeDrawPointsRef.current, {
        color: '#16a34a',
        weight: 4,
      }).addTo(drawLayerRef.current);
    });
    map.on('mousemove', (e) => {
      if (!drawingRef.current || !currentPolylineRef.current) return;
      const pts = freeDrawPointsRef.current;
      const lastPt = pts[pts.length - 1];
      if (lastPt) {
        const d = map.distance(lastPt, e.latlng);
        // Throttle points closer than 2 meters to avoid creating overly dense polygons
        if (d < 2) return;
      }
      pts.push(e.latlng);
      currentPolylineRef.current.setLatLngs(pts);
    });
    map.on('mouseup', () => {
      if (!drawingRef.current) return;
      drawingRef.current = false;
      map.dragging.enable();
      if (containerRef.current) containerRef.current.style.cursor = 'grab';
      map.off('mousedown mousemove mouseup');
      if (freeDrawPointsRef.current.length < 3) return;
      if (currentPolylineRef.current && drawLayerRef.current) {
        drawLayerRef.current.removeLayer(currentPolylineRef.current);
        currentPolylineRef.current = null;
      }
      const polygon = L.polygon(freeDrawPointsRef.current, {
        color: '#16a34a',
        weight: 3,
        fillOpacity: 0.25,
      }).addTo(drawLayerRef.current);
      const gj = polygon.toGeoJSON();
      setStatus('Boundary drawn — run satellite scan');
      emitGeojson(gj);
    });
  };

  const enablePolygonMode = () => {
    const map = mapRef.current;
    if (!map) return;
    polygonModeRef.current = true;
    drawingRef.current = false;
    polygonPointsRef.current = [];
    if (tempLineRef.current && drawLayerRef.current) {
      drawLayerRef.current.removeLayer(tempLineRef.current);
      tempLineRef.current = null;
    }
    if (containerRef.current) containerRef.current.style.cursor = 'crosshair';
    map.off('mousedown mousemove mouseup click');

    map.on('click', (e) => {
      if (!polygonModeRef.current) return;
      const latlng = e.latlng;
      if (polygonPointsRef.current.length === 0) {
        polygonPointsRef.current.push(latlng);
        L.circleMarker(latlng, {
          radius: 8,
          color: '#15803d',
          fillColor: 'white',
          fillOpacity: 1,
          weight: 3,
        }).addTo(drawLayerRef.current);
        return;
      }
      const first = polygonPointsRef.current[0];
      const distance = map.distance(first, latlng);
      if (distance < 25 && polygonPointsRef.current.length > 2) {
        if (tempLineRef.current && drawLayerRef.current) {
          drawLayerRef.current.removeLayer(tempLineRef.current);
          tempLineRef.current = null;
        }
        const polygon = L.polygon(polygonPointsRef.current, {
          color: '#eab308',
          weight: 3,
          fillOpacity: 0.25,
        }).addTo(drawLayerRef.current);
        const gj = polygon.toGeoJSON();
        polygonModeRef.current = false;
        map.off('click');
        if (containerRef.current) containerRef.current.style.cursor = 'grab';
        setStatus('Polygon complete');
        emitGeojson(gj);
        return;
      }
      polygonPointsRef.current.push(latlng);
      L.circleMarker(latlng, { radius: 5, color: '#eab308', fillColor: 'white', fillOpacity: 1, weight: 2 })
        .addTo(drawLayerRef.current);
      if (tempLineRef.current && drawLayerRef.current) {
        drawLayerRef.current.removeLayer(tempLineRef.current);
      }
      tempLineRef.current = L.polyline(polygonPointsRef.current, { color: '#eab308', weight: 4 }).addTo(drawLayerRef.current);
    });
    setStatus('Tap corners — click near the first point to close');
  };

  return (
    <div
      className="relative w-full rounded-2xl overflow-hidden border border-forest-100 shadow-lg"
      style={{ height, minHeight }}
    >
      <div ref={containerRef} className="w-full h-full" />

      <div className="absolute top-3 left-1/2 -translate-x-1/2 z-[5000] flex gap-2 w-[92%] max-w-md">
        <input
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && searchLocation()}
          placeholder="Search village, district, landmark…"
          className="flex-1 bg-white/95 backdrop-blur-sm border border-forest-100 rounded-xl px-3 py-2.5 text-xs text-carbon-800 shadow-md focus:outline-none focus:ring-1 focus:ring-forest-400"
        />
        <button
          type="button"
          onClick={searchLocation}
          className="bg-forest-800 hover:bg-forest-900 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-md"
        >
          Search
        </button>
      </div>

      {placeName && (
        <div className="absolute top-14 left-3 z-[5000] bg-black/70 text-white text-[10px] px-3 py-1 rounded-lg max-w-[240px]">
          📍 {placeName}
        </div>
      )}

      <div className="absolute left-3 top-24 z-[5000]">
        <button
          type="button"
          onClick={enablePolygonMode}
          className="w-11 h-11 rounded-xl bg-white shadow-md text-lg border border-forest-100"
          title="Polygon mode"
        >
          ⬠
        </button>
      </div>

      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-[5000] flex flex-wrap justify-center gap-2 px-2">
        <button type="button" onClick={startDrawing}
          className="bg-sky-700 hover:bg-sky-800 text-white text-xs font-bold px-4 py-2.5 rounded-xl shadow-lg">
          Free Draw
        </button>
        <button type="button" onClick={clearAll}
          className="bg-white/95 border border-forest-100 text-carbon-700 text-xs font-bold px-4 py-2.5 rounded-xl shadow-md">
          Clear
        </button>
      </div>

      {status && (
        <div className="absolute bottom-16 left-1/2 -translate-x-1/2 z-[5000] bg-emerald-900/85 text-white text-[10px] px-3 py-1.5 rounded-full max-w-[90%] text-center">
          {status}
        </div>
      )}

      <div className="absolute bottom-3 right-3 z-[5000]">
        <span className="bg-black/65 text-white text-[9px] px-2 py-1 rounded-lg font-mono">
          🛰️ GEE · Google Satellite + labels
        </span>
      </div>
    </div>
  );
}
