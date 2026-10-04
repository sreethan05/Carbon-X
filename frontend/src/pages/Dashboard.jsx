import { useEffect, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import axios from "axios";

export default function Dashboard() {

  const mapRef = useRef(null);

  const polygonLayerRef = useRef(null);

  const drawingRef = useRef(false);

  const pointsRef = useRef([]);

  const lineRef = useRef(null);

  const [searchText, setSearchText] =
    useState("");

  const [report, setReport] =
    useState(null);

  // ================= MAP =================

  useEffect(() => {

    if (mapRef.current)
      return;

    const map = L.map("map", {
      center: [20.5937, 78.9629],
      zoom: 5,
      maxZoom: 22
    });

    mapRef.current = map;

    L.tileLayer(
      "https://{s}.google.com/vt/lyrs=s,h&x={x}&y={y}&z={z}",
      {
        subdomains: [
          "mt0",
          "mt1",
          "mt2",
          "mt3"
        ],
        maxZoom: 22
      }
    ).addTo(map);

    polygonLayerRef.current =
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

      const place =
        response.data[0];

      const lat =
        parseFloat(place.lat);

      const lon =
        parseFloat(place.lon);

      mapRef.current.flyTo(
        [lat, lon],
        18
      );

    } catch (err) {

      console.log(err);

      alert(
        "Search failed"
      );

    }

  };

  // ================= START DRAW =================

  const startDrawing = () => {

    const map = mapRef.current;

    drawingRef.current = false;

    pointsRef.current = [];

    if (lineRef.current) {

      polygonLayerRef.current.removeLayer(
        lineRef.current
      );

    }

    map.off("click");
    map.off("mousemove");

    map.dragging.disable();

    document.getElementById(
      "map"
    ).style.cursor = "crosshair";

    let started = false;

    // START ON FIRST CLICK

    map.on("click", (e) => {

      // FIRST CLICK

      if (!started) {

        started = true;

        drawingRef.current = true;

        pointsRef.current.push(
          e.latlng
        );

        lineRef.current =
          L.polyline(
            pointsRef.current,
            {
              color: "red",
              weight: 4
            }
          ).addTo(
            polygonLayerRef.current
          );

        return;

      }

      // CHECK CLOSE

      const firstPoint =
        pointsRef.current[0];

      const distance =
        map.distance(
          firstPoint,
          e.latlng
        );

      // USER MANUALLY CLOSES

      if (
        distance < 20 &&
        pointsRef.current.length > 10
      ) {

        finishDrawing();

      }

    });

    // DRAW ON MOVE

    map.on("mousemove", (e) => {

      if (!drawingRef.current)
        return;

      pointsRef.current.push(
        e.latlng
      );

      lineRef.current.setLatLngs(
        pointsRef.current
      );

    });

  };

  // ================= FINISH DRAW =================

  const finishDrawing = () => {

    if (!drawingRef.current)
      return;

    drawingRef.current = false;

    const map = mapRef.current;

    map.dragging.enable();

    document.getElementById(
      "map"
    ).style.cursor = "grab";

    map.off("mousemove");

    if (
      pointsRef.current.length < 3
    ) {

      alert(
        "Draw proper area"
      );

      return;

    }

    pointsRef.current.push(
      pointsRef.current[0]
    );

    if (lineRef.current) {

      polygonLayerRef.current.removeLayer(
        lineRef.current
      );

    }

    const polygon =
      L.polygon(
        pointsRef.current,
        {
          color: "yellow",
          fillColor: "yellow",
          fillOpacity: 0.3,
          weight: 3
        }
      ).addTo(
        polygonLayerRef.current
      );

    // SAVE GEOJSON

    const geojson =
      polygon.toGeoJSON();

    polygonLayerRef.current.geojson =
      geojson;

  };

  // ================= STOP DRAW =================

  const stopDrawing = () => {

    finishDrawing();

  };

  // ================= ANALYZE =================

  const analyze = async () => {

    try {

      const geojson =
        polygonLayerRef.current.geojson;

      if (!geojson) {

        alert(
          "Please draw area first"
        );

        return;

      }

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

  // ================= CLEAR =================

  const clearMap = () => {

    polygonLayerRef.current.clearLayers();

    polygonLayerRef.current.geojson =
      null;

    setReport(null);

  };

  return (

    <div
      style={{
        width: "100vw",
        height: "100vh"
      }}
    >

      {/* MAP */}

      <div
        id="map"
        style={{
          width: "100%",
          height: "100%"
        }}
      />

      {/* TITLE */}

      <div
        style={{
          position: "absolute",
          top: 10,
          width: "100%",
          textAlign: "center",
          fontSize: 60,
          fontWeight: "bold",
          color: "white",
          zIndex: 5000,
          textShadow:
            "2px 2px 10px black"
        }}
      >
        CarbonSetu
      </div>

      {/* SEARCH */}

      <div
        style={{
          position: "absolute",
          top: 130,
          width: "100%",
          display: "flex",
          justifyContent: "center",
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
            width: 700,
            padding: 20,
            borderRadius: 20,
            border: "none",
            fontSize: 20
          }}
        />

        <button
          onClick={searchLocation}
          style={greenBtn}
        >
          Search
        </button>

      </div>

      {/* BUTTONS */}

      <div
        style={{
          position: "absolute",
          bottom: 40,
          width: "100%",
          display: "flex",
          justifyContent: "center",
          gap: 20,
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
          onClick={stopDrawing}
        >
          Stop Drawing
        </button>

        <button
          style={grayBtn}
          onClick={clearMap}
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

      {

        report && (

          <div
            style={{
              position: "absolute",
              bottom: 140,
              left: "50%",
              transform:
                "translateX(-50%)",
              background: "white",
              padding: 24,
              borderRadius: 24,
              zIndex: 7000,
              width: 900,
              display: "grid",
              gridTemplateColumns:
                "repeat(3,1fr)",
              gap: 20,
              boxShadow:
                "0 4px 25px rgba(0,0,0,0.25)"
            }}
          >

            <ReportCard
              title="NDVI"
              value={report.ndvi}
            />

            <ReportCard
              title="EVI"
              value={report.evi}
            />

            <ReportCard
              title="Tree Cover"
              value={`${report.tree_cover}%`}
            />

            <ReportCard
              title="Soil Moisture"
              value={`${report.soil_moisture}%`}
            />

            <ReportCard
              title="Carbon Tonnes"
              value={report.carbon_tonnes}
            />

            <ReportCard
              title="Area"
              value={`${report.area_hectares} ha`}
            />

          </div>

        )

      }

    </div>

  );

}

// ================= REPORT CARD =================

function ReportCard({

  title,
  value

}) {

  return (

    <div
      style={{
        background: "#f5f5f5",
        borderRadius: 18,
        padding: 20,
        textAlign: "center"
      }}
    >

      <h2>{title}</h2>

      <p
        style={{
          fontSize: 26,
          fontWeight: "bold",
          color: "#27ae60"
        }}
      >
        {value}
      </p>

    </div>

  );

}

// ================= BUTTONS =================

const blueBtn = {

  background: "#2980b9",
  color: "white",
  border: "none",
  padding: "18px 34px",
  borderRadius: 18,
  fontSize: 18,
  fontWeight: "bold",
  cursor: "pointer"

};

const grayBtn = {

  background: "#7f8c8d",
  color: "white",
  border: "none",
  padding: "18px 34px",
  borderRadius: 18,
  fontSize: 18,
  fontWeight: "bold",
  cursor: "pointer"

};

const greenBtn = {

  background: "#27ae60",
  color: "white",
  border: "none",
  padding: "18px 34px",
  borderRadius: 18,
  fontSize: 18,
  fontWeight: "bold",
  cursor: "pointer"

};