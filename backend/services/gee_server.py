#!/usr/bin/env python3
"""
GEE Microservice - Your teammate's Python file integrated as a service
Run this to enable real GEE analysis: python gee_server.py

Project: carbonsetu-496709
"""

import ee
import json
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# Initialize GEE with your project
ee.Initialize(project="carbonsetu-496709")

def get_satellite_features(longitude, latitude):
    """Your teammate's original function - gets NDVI from Sentinel-2"""
    point = ee.Geometry.Point([longitude, latitude])

    image = (
        ee.ImageCollection("COPERNICUS/S2_SR")
        .filterBounds(point)
        .filterDate("2024-01-01", "2024-12-31")
        .sort("CLOUDY_PIXEL_PERCENTAGE")
        .first()
    )

    ndvi = image.normalizedDifference(["B8", "B4"])

    ndvi_value = ndvi.reduceRegion(
        reducer=ee.Reducer.mean(),
        geometry=point,
        scale=10
    ).getInfo()

    nd = ndvi_value.get("nd", 0.3)

    features = [
        nd,
        nd * 0.9,
        nd * 1.1,
        0.8,
        0.4,
        0.3,
        0.9,
        0.2
    ]

    return {
        "nd": nd,
        "ndMin": nd * 0.9,
        "ndMax": nd * 1.1,
        "features": features,
        "timestamp": str(ee.Date())
    }

def analyze_polygon(coordinates):
    """Analyze a polygon - get centroid and run analysis"""
    if len(coordinates) < 3:
        return {"error": "Need at least 3 coordinates"}
    
    # Calculate centroid
    lats = [c[1] for c in coordinates]
    lngs = [c[0] for c in coordinates]
    centroid_lat = sum(lats) / len(lats)
    centroid_lng = sum(lngs) / len(lngs)
    
    # Run GEE analysis
    result = get_satellite_features(centroid_lng, centroid_lat)
    result["centroid"] = {"lat": centroid_lat, "lng": centroid_lng}
    result["coordinates_count"] = len(coordinates)
    
    return result

class GEEHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        data = json.loads(body)
        
        if self.path == '/analyze/point':
            lat = data.get('latitude')
            lng = data.get('longitude')
            result = get_satellite_features(lng, lat)
            self.send_json(result)
            
        elif self.path == '/analyze/polygon':
            coords = data.get('coordinates', [])
            result = analyze_polygon(coords)
            self.send_json(result)
            
        else:
            self.send_error(404, "Endpoint not found")
    
    def do_GET(self):
        if self.path == '/health':
            self.send_json({"status": "ok", "gee": "connected"})
        else:
            self.send_error(404)
    
    def send_json(self, data):
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def log_message(self, format, *args):
        print(f"[GEE] {format % args}")

if __name__ == '__main__':
    port = 5001
    server = HTTPServer(('localhost', port), GEEHandler)
    print(f"🌍 GEE Microservice running on http://localhost:{port}")
    print(f"   POST /analyze/point - Analyze single point")
    print(f"   POST /analyze/polygon - Analyze polygon centroid")
    print(f"   GET /health - Health check")
    server.serve_forever()
