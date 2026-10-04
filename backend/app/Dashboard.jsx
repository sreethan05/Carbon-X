import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  Polyline,
  Polygon,
  useMapEvents
} from "react-leaflet";

import "leaflet/dist/leaflet.css";

import L from "leaflet";

import { useState } from "react";

import axios from "axios";

delete L.Icon.Default.prototype._getIconUrl;

L.Icon.Default.mergeOptions({

  iconRetinaUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",

  iconUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",

  shadowUrl:
    "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png"

});

function MapClickHandler({

  drawing,

  polygonMode,

  polygonPoints,

  setPolygonPoints,

  polygonClosed,

  setPolygonClosed,

  setDrawing,

  setPolygonMode

}) {

  useMapEvents({

    click(e) {

      if (
        !drawing &&
        !polygonMode
      ) return;

      if (
        polygonClosed
      ) return;

      const latlng = [

        e.latlng.lat,

        e.latlng.lng

      ];

      // FREE DRAW MODE

      if (drawing) {

        setPolygonPoints(prev => [
          ...prev,
          latlng
        ]);

        return;
      }

      // POLYGON MODE

      if (
        polygonPoints.length === 0
      ) {

        setPolygonPoints([
          latlng
        ]);

        return;
      }

      const first =
        polygonPoints[0];

      const distance =
        Math.sqrt(

          Math.pow(
            latlng[0] - first[0],
            2
          ) +

          Math.pow(
            latlng[1] - first[1],
            2
          )

        );

      // CLOSE POLYGON

      if (

        distance < 0.0005 &&

        polygonPoints.length >= 3

      ) {

        setPolygonClosed(true);

        setPolygonMode(false);

        return;

      }

      // ADD POINT

      setPolygonPoints([

        ...polygonPoints,

        latlng

      ]);

    }

  });

  return null;
}

export default function Dashboard() {

  const [search, setSearch] =
    useState("");

  const [position, setPosition] =
    useState([
      17.385,
      78.4867
    ]);

  const [drawing, setDrawing] =
    useState(false);

  const [polygonMode, setPolygonMode] =
    useState(false);

  const [polygonPoints, setPolygonPoints] =
    useState([]);

  const [polygonClosed, setPolygonClosed] =
    useState(false);

  const [analysis, setAnalysis] =
    useState(null);

  // ================= SEARCH =================

  const searchLocation =
    async () => {

      if (!search) return;

      try {

        const response =
          await axios.get(

            `https://nominatim.openstreetmap.org/search?format=json&q=${search}`

          );

        if (
          response.data.length > 0
        ) {

          const place =
            response.data[0];

          setPosition([

            parseFloat(place.lat),

            parseFloat(place.lon)

          ]);

        }

      } catch {

        alert(
          "Search failed"
        );

      }

    };

  // ================= START FREE DRAW =================

  const startDrawing = () => {

    setDrawing(true);

    setPolygonMode(false);

    setPolygonPoints([]);

    setPolygonClosed(false);

    setAnalysis(null);

  };

  // ================= START POLYGON =================

  const startPolygonMode = () => {

    setPolygonMode(true);

    setDrawing(false);

    setPolygonPoints([]);

    setPolygonClosed(false);

    setAnalysis(null);

  };

  // ================= STOP =================

  const stopDrawing = () => {

    setDrawing(false);

    setPolygonMode(false);

    if (
      polygonPoints.length >= 3
    ) {

      setPolygonClosed(true);

    }

  };

  // ================= CLEAR =================

  const clearPolygon = () => {

    setPolygonPoints([]);

    setPolygonClosed(false);

    setDrawing(false);

    setPolygonMode(false);

    setAnalysis(null);

  };

  // ================= ANALYZE =================

  const analyzeArea =
    async () => {

      try {

        if (
          polygonPoints.length < 3
        ) {

          alert(
            "Draw area first"
          );

          return;

        }

        const geojson = {

          type: "Feature",

          geometry: {

            type: "Polygon",

            coordinates: [[

              ...polygonPoints.map(
                (p) => [
                  p[1],
                  p[0]
                ]
              ),

              [
                polygonPoints[0][1],
                polygonPoints[0][0]
              ]

            ]]

          }

        };

        const response =
          await axios.post(

            "http://127.0.0.1:5000/analyze",

            {
              geojson
            }

          );

        if (
          response.data.success
        ) {

          setAnalysis(
            response.data
          );

        } else {

          alert(
            response.data.message
          );

        }

      } catch {

        alert(
          "Backend connection failed"
        );

      }

    };

  return (

    <div

      style={{

        width: "100vw",

        height: "100vh",

        overflow: "hidden",

        position: "relative"

      }}

    >

      {/* ================= MAP ================= */}

      <MapContainer

        center={position}

        zoom={18}

        maxZoom={22}

        style={{

          width: "100%",

          height: "100%"

        }}

      >

        <TileLayer

          url="https://{s}.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"

          subdomains={[
            "mt0",
            "mt1",
            "mt2",
            "mt3"
          ]}

          maxZoom={22}

        />

        <MapClickHandler

          drawing={drawing}

          polygonMode={polygonMode}

          polygonPoints={polygonPoints}

          setPolygonPoints={setPolygonPoints}

          polygonClosed={polygonClosed}

          setPolygonClosed={setPolygonClosed}

          setDrawing={setDrawing}

          setPolygonMode={setPolygonMode}

        />

        {/* ================= POINTS ================= */}

        {

          polygonPoints.map(
            (point, index) => (

              <Marker

                key={index}

                position={point}

              >

                <Popup>
                  Point {index + 1}
                </Popup>

              </Marker>

            )
          )

        }

        {/* ================= LINE ================= */}

        {

          polygonPoints.length > 1 && (

            <Polyline

              positions={polygonPoints}

              pathOptions={{

                color: drawing
                  ? "red"
                  : "yellow",

                weight: 4

              }}

            />

          )

        }

        {/* ================= POLYGON ================= */}

        {

          polygonClosed && (

            <Polygon

              positions={polygonPoints}

              pathOptions={{

                color: "yellow",

                fillColor: "yellow",

                fillOpacity: 0.3

              }}

            />

          )

        }

      </MapContainer>

      {/* ================= TITLE ================= */}

      <div

        style={{

          position: "absolute",

          top: 20,

          width: "100%",

          display: "flex",

          flexDirection: "column",

          alignItems: "center",

          zIndex: 1000

        }}

      >

        <h1

          style={{

            color: "white",

            fontSize: 70,

            fontWeight: "bold",

            marginBottom: 20

          }}

        >

          CarbonSetu

        </h1>

        {/* ================= SEARCH ================= */}

        <div

          style={{

            display: "flex",

            gap: 10

          }}

        >

          <input

            placeholder="Search location..."

            value={search}

            onChange={(e) =>
              setSearch(
                e.target.value
              )
            }

            style={{

              width: 800,

              padding: 25,

              borderRadius: 20,

              border: "none",

              fontSize: 22

            }}

          />

          <button

            onClick={
              searchLocation
            }

            style={{

              background:
                "#27ae60",

              color: "white",

              border: "none",

              borderRadius: 20,

              padding:
                "20px 40px",

              fontSize: 20,

              fontWeight: "bold",

              cursor: "pointer"

            }}

          >

            Search

          </button>

        </div>

      </div>

      {/* ================= LEFT TOOLBAR ================= */}

      <div

        style={{

          position: "absolute",

          left: 20,

          top: "50%",

          transform:
            "translateY(-50%)",

          zIndex: 2000,

          display: "flex",

          flexDirection: "column",

          gap: 15

        }}

      >

        {/* POLYGON TOOL */}

        {/* ================= LEFT POLYGON TOOL ================= */}

<div
  style={{
    position: "absolute",
    left: 20,
    top: 320,
    zIndex: 99999,
  }}
>

  <button

    onClick={startPolygonMode}

    title="Polygon Tool"

    style={{

      width: 90,

      height: 90,

      borderRadius: "50%",

      border: "4px solid white",

      background: "white",

      color: "black",

      fontSize: 40,

      fontWeight: "bold",

      cursor: "pointer",

      display: "flex",

      alignItems: "center",

      justifyContent: "center",

      boxShadow:
        "0 4px 20px rgba(0,0,0,0.5)"

    }}

  >

    ⬠

  </button>

</div>
      {/* ================= BOTTOM BUTTONS ================= */}

      <div

        style={{

          position: "absolute",

          bottom: 80,

          width: "100%",

          display: "flex",

          justifyContent:
            "center",

          gap: 25,

          zIndex: 1000

        }}

      >

        <button

          onClick={
            startDrawing
          }

          style={buttonBlue}

        >

          Start Drawing

        </button>

        <button

          onClick={
            stopDrawing
          }

          style={buttonGray}

        >

          Stop Drawing

        </button>

        <button

          onClick={
            clearPolygon
          }

          style={buttonGray}

        >

          Clear

        </button>

        <button

          onClick={
            analyzeArea
          }

          style={buttonGreen}

        >

          Analyze

        </button>

      </div>

      {/* ================= ANALYSIS ================= */}

      {

        analysis && (

          <div

            style={{

              position: "absolute",

              right: 20,

              top: 180,

              width: 320,

              background: "white",

              padding: 25,

              borderRadius: 20,

              zIndex: 1000,

              boxShadow:
                "0 5px 20px rgba(0,0,0,0.3)"

            }}

          >

            <h2>
              Analysis
            </h2>

            <p>
              NDVI:
              {" "}
              {analysis.ndvi}
            </p>

            <p>
              EVI:
              {" "}
              {analysis.evi}
            </p>

            <p>
              Tree Cover:
              {" "}
              {analysis.tree_cover}%
            </p>

            <p>
              Soil Moisture:
              {" "}
              {analysis.soil_moisture}%
            </p>

            <p>
              Carbon Tonnes:
              {" "}
              {analysis.carbon_tonnes}
            </p>

            <p>
              Area:
              {" "}
              {analysis.area_hectares} ha
            </p>

            <button

              onClick={
                clearPolygon
              }

              style={{

                marginTop: 20,

                width: "100%",

                padding: 14,

                background:
                  "#27ae60",

                color: "white",

                border: "none",

                borderRadius: 12,

                cursor: "pointer",

                fontWeight:
                  "bold"

              }}

            >

              New Analysis

            </button>

          </div>

        )

      }

    </div>

  );

}

const buttonBlue = {

  background: "#3498db",

  color: "white",

  border: "none",

  borderRadius: 20,

  padding: "22px 42px",

  fontSize: 20,

  fontWeight: "bold",

  cursor: "pointer"

};

const buttonGray = {

  background: "#95a5a6",

  color: "white",

  border: "none",

  borderRadius: 20,

  padding: "22px 42px",

  fontSize: 20,

  fontWeight: "bold",

  cursor: "pointer"

};

const buttonGreen = {

  background: "#27ae60",

  color: "white",

  border: "none",

  borderRadius: 20,

  padding: "22px 42px",

  fontSize: 20,

  fontWeight: "bold",

  cursor: "pointer"

};