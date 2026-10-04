// Google Earth Engine Integration Service
// Connects to your teammate's Python GEE microservice or uses simulated data

const GEE_PROJECT = process.env.GEE_PROJECT || 'carbonsetu-496709';
const GEE_MICROSERVICE_URL = process.env.GEE_MICROSERVICE_URL || 'http://localhost:5001';

// Call Python GEE microservice
async function callGEEMicroservice(endpoint, data) {
  const response = await fetch(`${GEE_MICROSERVICE_URL}${endpoint}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  });
  
  if (!response.ok) {
    throw new Error(`GEE microservice error: ${response.status}`);
  }
  
  return response.json();
}

// Get satellite features for a single point
async function getSatelliteFeatures(latitude, longitude) {
  console.log(`[GEE] Analyzing point: ${latitude}, ${longitude}`);
  console.log(`[GEE] Project: ${GEE_PROJECT}`);
  
  try {
    // Try to call Python microservice
    const result = await callGEEMicroservice('/analyze/point', {
      latitude,
      longitude
    });
    
    return {
      nd: result.nd,
      ndMin: result.ndMin,
      ndMax: result.ndMax,
      features: result.features,
      coordinates: { lat: latitude, lng: longitude },
      timestamp: result.timestamp || new Date().toISOString(),
      source: 'GEE Sentinel-2 (carbonsetu-496709)',
      realData: true
    };
  } catch (error) {
    console.warn('[GEE] Microservice not available, using simulated data');
    // Fallback to simulated data
    const baseNdvi = 0.3 + Math.random() * 0.5;
    return {
      nd: parseFloat(baseNdvi.toFixed(3)),
      ndMin: parseFloat((baseNdvi * 0.9).toFixed(3)),
      ndMax: parseFloat((baseNdvi * 1.1).toFixed(3)),
      features: [
        parseFloat(baseNdvi.toFixed(3)),
        parseFloat((baseNdvi * 0.9).toFixed(3)),
        parseFloat((baseNdvi * 1.1).toFixed(3)),
        0.8, 0.4, 0.3, 0.9, 0.2
      ],
      coordinates: { lat: latitude, lng: longitude },
      timestamp: new Date().toISOString(),
      source: 'Simulated (Run python backend/services/gee_server.py for real data)',
      realData: false
    };
  }
}

// Analyze polygon - get centroid and run analysis
async function analyzePolygon(coordinates) {
  console.log(`[GEE] Analyzing polygon with ${coordinates.length} vertices`);
  
  // Calculate centroid
  const centroid = coordinates.reduce((acc, coord) => ({
    lat: acc.lat + coord.lat / coordinates.length,
    lng: acc.lng + coord.lng / coordinates.length
  }), { lat: 0, lng: 0 });
  
  try {
    // Try Python microservice with polygon
    const coordsForAPI = coordinates.map(c => [c.lng, c.lat]);
    const result = await callGEEMicroservice('/analyze/polygon', {
      coordinates: coordsForAPI
    });
    
    return {
      nd: result.nd,
      ndMin: result.ndMin,
      ndMax: result.ndMax,
      features: result.features,
      centroid: result.centroid || centroid,
      vertexCount: coordinates.length,
      timestamp: result.timestamp || new Date().toISOString(),
      source: 'GEE Sentinel-2 (carbonsetu-496709)',
      realData: true
    };
  } catch (error) {
    console.warn('[GEE] Polygon analysis using centroid method');
    // Fallback: analyze centroid only
    const features = await getSatelliteFeatures(centroid.lat, centroid.lng);
    return {
      ...features,
      centroid,
      vertexCount: coordinates.length,
      realData: false
    };
  }
}

module.exports = {
  getSatelliteFeatures,
  analyzePolygon,
  GEE_PROJECT
};