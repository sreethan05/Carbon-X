import { useEffect, useRef, useState, useCallback } from 'react';
import L from 'leaflet';
import 'leaflet/dist/leaflet.css';

import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png';
import markerIcon from 'leaflet/dist/images/marker-icon.png';
import markerShadow from 'leaflet/dist/images/marker-shadow.png';

delete L.Icon.Default.prototype._getIconUrl;
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
});

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
  const mapRef = useRef(null);
  const drawLayerRef = useRef(null);
  const drawingRef = useRef(false);
  const polygonModeRef = useRef(false);
  const currentPolylineRef = useRef(null);
  const freeDrawPointsRef = useRef([]);
  const polygonPointsRef = useRef([]);

  const [searchText, setSearchText] = useState('');
  const [status, setStatus] = useState('');
  const [placeName, setPlaceName] = useState('');

  const emitGeojson = useCallback((geojson) => {
    if (!geojson) {
      if (onGeojsonDrawn) onGeojsonDrawn(null);
      if (onAreaCalculated) onAreaCalculated({ area: 0, score: 0, ndvi: 0 });
      return;
    }
    if (onGeojsonDrawn) onGeojsonDrawn(geojson);
    if (onAreaCalculated && geojson.geometry?.coordinates?.[0]) {
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
      onAreaCalculated({ area: Math.round((Math.abs(areaM2) / 20000) * 100) / 100, score: 0, ndvi: 0 });
    }
  }, [onGeojsonDrawn, onAreaCalculated]);

  useEffect(() => {
    if (mapRef.current) return;

    const map = L.map('gee-map', {
      center: [20.5937, 78.9629],
      zoom: 5,
      zoomControl: true,
      maxZoom: 22,
    });
    mapRef.current = map;

    L.tileLayer('https://mt1.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}', {
      maxZoom: 22,
      attribution: '© Google · GEE analysis layer',
    }).addTo(map);

    drawLayerRef.current = L.layerGroup().addTo(map);

    return () => {
      map.remove();
      mapRef.current = null;
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
      const data = await res.json();
      if (!data.length) {
        setStatus('Location not found');
        return;
      }
      const place = data[0];
      const lat = parseFloat(place.lat);
      const lon = parseFloat(place.lon);
      const label = place.display_name?.split(',').slice(0, 3).join(', ') || searchText;
      setPlaceName(label);
      mapRef.current.flyTo([lat, lon], 16, { duration: 1.5 });
      L.marker([lat, lon]).addTo(drawLayerRef.current).bindPopup(label);
      setStatus(label);
    } catch {
      setStatus('Search failed');
    }
  };

  const clearAll = () => {
    drawLayerRef.current?.clearLayers();
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
    const el = document.getElementById('gee-map');
    if (el) el.style.cursor = 'crosshair';

    map.off('mousedown mousemove mouseup');
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
      freeDrawPointsRef.current.push(e.latlng);
      currentPolylineRef.current.setLatLngs(freeDrawPointsRef.current);
    });
    map.on('mouseup', () => {
      if (!drawingRef.current) return;
      drawingRef.current = false;
      map.dragging.enable();
      if (el) el.style.cursor = 'grab';
      if (freeDrawPointsRef.current.length < 3) return;
      freeDrawPointsRef.current.push(freeDrawPointsRef.current[0]);
      drawLayerRef.current.removeLayer(currentPolylineRef.current);
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
    let tempLine = null;
    const el = document.getElementById('gee-map');
    if (el) el.style.cursor = 'crosshair';
    map.off('click');

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
        polygonPointsRef.current.push(first);
        if (tempLine) drawLayerRef.current.removeLayer(tempLine);
        const polygon = L.polygon(polygonPointsRef.current, {
          color: '#eab308',
          weight: 3,
          fillOpacity: 0.25,
        }).addTo(drawLayerRef.current);
        const gj = polygon.toGeoJSON();
        polygonModeRef.current = false;
        map.off('click');
        if (el) el.style.cursor = 'grab';
        setStatus('Polygon complete');
        emitGeojson(gj);
        return;
      }
      polygonPointsRef.current.push(latlng);
      L.circleMarker(latlng, { radius: 5, color: '#eab308', fillColor: 'white', fillOpacity: 1, weight: 2 })
        .addTo(drawLayerRef.current);
      if (tempLine) drawLayerRef.current.removeLayer(tempLine);
      tempLine = L.polyline(polygonPointsRef.current, { color: '#eab308', weight: 4 }).addTo(drawLayerRef.current);
    });
    setStatus('Tap corners — click near the first point to close');
  };

  return (
    <div
      className="relative w-full rounded-2xl overflow-hidden border border-forest-100 shadow-lg"
      style={{ height, minHeight }}
    >
      <div id="gee-map" className="w-full h-full" />

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
