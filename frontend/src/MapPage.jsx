import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import axios from "axios";

import markerIcon2x from "leaflet/dist/images/marker-icon-2x.png";
import markerIcon from "leaflet/dist/images/marker-icon.png";
import markerShadow from "leaflet/dist/images/marker-shadow.png";

// ================= FIX LEAFLET ICONS =================

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow
});

export default function App() {

  const mapRef = useRef(null);

  const drawLayerRef = useRef(null);

  const drawingRef = useRef(false);

  const polygonModeRef = useRef(false);

  const currentPolylineRef = useRef(null);

  const freeDrawPointsRef = useRef([]);

  const polygonPointsRef = useRef([]);

  const [searchText, setSearchText] =
    useState("");

  const [geojson, setGeojson] =
    useState(null);

  const [report, setReport] =
    useState(null);

  // ================= MAP =================

  useEffect(() => {

    if (mapRef.current)
      return;

    const map = L.map("map", {
      center: [20.5937, 78.9629],
      zoom: 5,
      zoomControl: true,
      maxZoom: 22
    });

    mapRef.current = map;

    // ================= SATELLITE MAP =================

    L.tileLayer(
      "https://mt1.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}",
      {
        maxZoom: 22
      }
    ).addTo(map);

    // ================= DRAW LAYER =================

    drawLayerRef.current =
      L.layerGroup().addTo(map);

  }, []);

  // ================= SEARCH =================

  const searchLocation = async () => {

    if (!searchText)
      return;

    try {

      const response =
        await axios.get(
          "https://nominatim.openstreetmap.org/search",
          {
            params: {
              q: searchText,
              format: "json",
              limit: 1
            }
          }
        );

      if (
        response.data.length === 0
      ) {

        alert(
          "Location not found"
        );

        return;

      }

      const result =
        response.data[0];

      const lat =
        parseFloat(result.lat);

      const lon =
        parseFloat(result.lon);

      mapRef.current.flyTo(
        [lat, lon],
        16,
        {
          duration: 2
        }
      );

      L.marker([
        lat,
        lon
      ]).addTo(
        mapRef.current
      );

    } catch (err) {

      console.log(err);

      alert(
        "Search failed"
      );

    }

  };

  // ================= FREE DRAW =================

  const startDrawing =
    () => {

      if (!mapRef.current)
        return;

      const map =
        mapRef.current;

      drawingRef.current =
        true;

      polygonModeRef.current =
        false;

      freeDrawPointsRef.current =
        [];

      map.dragging.disable();

      document
        .getElementById("map")
        .style.cursor =
        "crosshair";

      map.off("mousedown");
      map.off("mousemove");
      map.off("mouseup");

      // START

      map.on("mousedown", (e) => {

        if (
          !drawingRef.current
        )
          return;

        freeDrawPointsRef.current =
          [e.latlng];

        currentPolylineRef.current =
          L.polyline(
            freeDrawPointsRef.current,
            {
              color: "red",
              weight: 4
            }
          ).addTo(
            drawLayerRef.current
          );

      });

      // MOVE

      map.on("mousemove", (e) => {

        if (
          !drawingRef.current
        )
          return;

        freeDrawPointsRef.current.push(
          e.latlng
        );

        currentPolylineRef.current.setLatLngs(
          freeDrawPointsRef.current
        );

      });

      // STOP

      map.on("mouseup", () => {

        if (
          !drawingRef.current
        )
          return;

        drawingRef.current =
          false;

        map.dragging.enable();

        document
          .getElementById("map")
          .style.cursor =
          "grab";

        if (
          freeDrawPointsRef.current.length < 3
        )
          return;

        freeDrawPointsRef.current.push(
          freeDrawPointsRef.current[0]
        );

        drawLayerRef.current.removeLayer(
          currentPolylineRef.current
        );

        const polygon =
          L.polygon(
            freeDrawPointsRef.current,
            {
              color: "red",
              weight: 3,
              fillOpacity: 0.25
            }
          ).addTo(
            drawLayerRef.current
          );

        setGeojson(
          polygon.toGeoJSON()
        );

      });

    };

  // ================= POLYGON MODE =================

  const enablePolygonMode =
    () => {

      if (!mapRef.current)
        return;

      const map =
        mapRef.current;

      polygonModeRef.current =
        true;

      drawingRef.current =
        false;

      polygonPointsRef.current =
        [];

      let tempLine = null;

      map.off("click");

      document
        .getElementById("map")
        .style.cursor =
        "crosshair";

      map.on("click", (e) => {

        if (
          !polygonModeRef.current
        )
          return;

        const latlng =
          e.latlng;

        // FIRST POINT

        if (
          polygonPointsRef.current.length === 0
        ) {

          polygonPointsRef.current.push(
            latlng
          );

          L.circleMarker(
            latlng,
            {
              radius: 8,
              color: "red",
              fillColor: "white",
              fillOpacity: 1,
              weight: 3
            }
          ).addTo(
            drawLayerRef.current
          );

          return;

        }

        // CHECK CLOSE

        const firstPoint =
          polygonPointsRef.current[0];

        const distance =
          map.distance(
            firstPoint,
            latlng
          );

        if (
          distance < 25 &&
          polygonPointsRef.current.length > 2
        ) {

          polygonPointsRef.current.push(
            firstPoint
          );

          if (tempLine) {

            drawLayerRef.current.removeLayer(
              tempLine
            );

          }

          const polygon =
            L.polygon(
              polygonPointsRef.current,
              {
                color: "yellow",
                weight: 3,
                fillOpacity: 0.25
              }
            ).addTo(
              drawLayerRef.current
            );

          setGeojson(
            polygon.toGeoJSON()
          );

          polygonModeRef.current =
            false;

          map.off("click");

          document
            .getElementById("map")
            .style.cursor =
            "grab";

          alert(
            "Polygon completed"
          );

          return;

        }

        // ADD NEW POINT

        polygonPointsRef.current.push(
          latlng
        );

        L.circleMarker(
          latlng,
          {
            radius: 5,
            color: "yellow",
            fillColor: "white",
            fillOpacity: 1,
            weight: 2
          }
        ).addTo(
          drawLayerRef.current
        );

        if (tempLine) {

          drawLayerRef.current.removeLayer(
            tempLine
          );

        }

        tempLine =
          L.polyline(
            polygonPointsRef.current,
            {
              color: "yellow",
              weight: 4
            }
          ).addTo(
            drawLayerRef.current
          );

      });

    };

  // ================= CLEAR =================

  const clearAll =
    () => {

      setGeojson(null);

      setReport(null);

      drawLayerRef.current.clearLayers();

    };

  // ================= ANALYZE =================

  const analyze = async () => {

    if (!geojson) {

      alert(
        "Please draw farm area first"
      );

      return;

    }

    try {

      const response =
        await axios.post(
          "http://127.0.0.1:5000/analyze",
          {
            geojson
          }
        );

      if (
        !response.data.success
      ) {

        alert(
          response.data.error
        );

        return;

      }

      setReport(
        response.data
      );

    } catch (err) {

      console.log(err);

      alert(
        "Backend connection failed"
      );

    }

  };

  return (

    <div
      style={{
        width: "100vw",
        height: "100vh"
      }}
    >

      {/* TITLE */}

      <div
        style={{
          position: "absolute",
          top: 10,
          width: "100%",
          textAlign: "center",
          zIndex: 5000,
          color: "white",
          fontSize: "48px",
          fontWeight: "bold",
          textShadow:
            "2px 2px 12px black"
        }}
      >
        CarbonSetu
      </div>

      {/* SEARCH */}

      <div
        style={{
          position: "absolute",
          top: 90,
          left: "50%",
          transform:
            "translateX(-50%)",
          display: "flex",
          gap: 12,
          zIndex: 5000
        }}
      >

        <input
          value={searchText}
          onChange={(e) =>
            setSearchText(
              e.target.value
            )
          }
          placeholder="Search location..."
          style={{
            width: 520,
            padding: 16,
            borderRadius: 16,
            border: "none",
            fontSize: 18
          }}
        />

        <button
          onClick={searchLocation}
          style={greenBtn}
        >
          Search
        </button>

      </div>

      {/* LEFT TOOL */}

      <div
        style={{
          position: "absolute",
          left: 20,
          top: 220,
          zIndex: 5000
        }}
      >

        <button
          onClick={enablePolygonMode}
          style={toolBtn}
        >
          ⬠
        </button>

      </div>

      {/* BOTTOM BUTTONS */}

      <div
        style={{
          position: "absolute",
          bottom:
            report ? 340 : 30,
          width: "100%",
          display: "flex",
          justifyContent: "center",
          gap: 16,
          zIndex: 5000
        }}
      >

        <button
          style={blueBtn}
          onClick={startDrawing}
        >
          Start Drawing
        </button>

        <button
          style={grayBtn}
          onClick={clearAll}
        >
          Clear
        </button>

        <button
          style={greenBtn}
          onClick={analyze}
        >
          Analyze
        </button>

      </div>

      {/* REPORT */}

      {report && (

        <div
          style={{
            position: "absolute",
            bottom: 10,
            left: "50%",
            transform:
              "translateX(-50%)",
            width: "94%",
            maxWidth: 1200,
            background:
              "rgba(255,255,255,0.97)",
            borderRadius: 24,
            padding: 24,
            zIndex: 6000
          }}
        >

          {/* HEADER */}

          <div
            style={{
              display: "flex",
              justifyContent:
                "space-between",
              alignItems: "center",
              marginBottom: 24
            }}
          >

            <h1
              style={{
                margin: 0,
                fontSize: 42
              }}
            >
              Carbon Analysis Report
            </h1>

            <button
              onClick={() => {

                setReport(null);

                drawLayerRef.current.clearLayers();

                setGeojson(null);

              }}
              style={{
                background: "#f39c12",
                color: "white",
                border: "none",
                borderRadius: 16,
                padding: "14px 24px",
                fontSize: 18,
                fontWeight: "bold",
                cursor: "pointer"
              }}
            >
              New Analysis
            </button>

          </div>

          {/* REPORT GRID */}

          <div
            style={{
              display: "grid",
              gridTemplateColumns:
                "repeat(auto-fit,minmax(220px,1fr))",
              gap: 20
            }}
          >

            <div style={reportCard}>
              <h3>NDVI</h3>
              <p>{report.ndvi}</p>
            </div>

            <div style={reportCard}>
              <h3>EVI</h3>
              <p>{report.evi}</p>
            </div>

            <div style={reportCard}>
              <h3>Tree Cover</h3>
              <p>
                {report.tree_cover_percent}%
              </p>
            </div>

            <div style={reportCard}>
              <h3>Soil Moisture</h3>
              <p>
                {report.soil_moisture_percent}%
              </p>
            </div>

            <div style={reportCard}>
              <h3>Carbon Tonnes</h3>
              <p>
                {report.carbon_tonnes}
              </p>
            </div>

            <div style={reportCard}>
              <h3>Area</h3>
              <p>
                {report.area_hectares} ha
              </p>
            </div>

            <div style={reportCard}>
              <h3>Vegetation Health</h3>
              <p>
                {report.vegetation_health}
              </p>
            </div>

          </div>

        </div>

      )}

      {/* MAP */}

      <div
        id="map"
        style={{
          width: "100vw",
          height: "100vh"
        }}
      />

    </div>

  );

}

// ================= STYLES =================

const toolBtn = {

  width: 60,
  height: 60,
  borderRadius: 18,
  border: "none",
  background: "white",
  fontSize: 26,
  cursor: "pointer",
  boxShadow:
    "0 3px 10px rgba(0,0,0,0.25)"

};

const blueBtn = {

  background: "#2980b9",
  color: "white",
  border: "none",
  borderRadius: 16,
  padding: "14px 26px",
  fontSize: 16,
  fontWeight: "bold",
  cursor: "pointer"

};

const grayBtn = {

  background: "#7f8c8d",
  color: "white",
  border: "none",
  borderRadius: 16,
  padding: "14px 26px",
  fontSize: 16,
  fontWeight: "bold",
  cursor: "pointer"

};

const greenBtn = {

  background: "#27ae60",
  color: "white",
  border: "none",
  borderRadius: 16,
  padding: "14px 26px",
  fontSize: 16,
  fontWeight: "bold",
  cursor: "pointer"

};

const reportCard = {

  background: "#f4f6f7",
  borderRadius: 18,
  padding: 20,
  textAlign: "center",
  boxShadow:
    "0 3px 10px rgba(0,0,0,0.08)"

};