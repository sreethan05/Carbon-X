from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
ROOT_DIR = BACKEND_DIR.parent

load_dotenv(ROOT_DIR / ".env", override=True)
load_dotenv(BACKEND_DIR / ".env", override=True)

from fastapi import FastAPI, WebSocket, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, field_validator
from typing import Literal, Optional
import json
import uuid
from datetime import datetime, timedelta, timezone
import os
import math
import time

from app.security import (
    create_access_token,
    decode_token,
    get_current_user,
    get_current_user_optional,
    require_role,
    verify_password,
)
from app.phone_service import generate_otp, send_phone_otp
from app import supabase_db as db
from app import redis_store
from app import config as app_config
from app.services import credit_engine, ledger, market_store, split_engine
from app.services.kyc_service import analyse_document, validate_aadhaar


def _sample_data():
    """Lazy sample_data access — the fallback dataset is only imported
    when a demo/fallback path actually needs it."""
    from app import sample_data as _sd
    return _sd


app = FastAPI(
    title="CarbonX API",
    version="1.0.0",
    description="Satellite-verified carbon + biodiversity credits for Indian smallholder farmers. "
                "Trust pipeline: register -> verify (Stage 1) -> calculate (Stage 2) -> anchor -> "
                "monitor -> sell/split/retire. See docs/MRV_METHODOLOGY.md for the equations.",
    openapi_tags=[
        {"name": "auth", "description": "Phone-OTP registration/login, JWT sessions"},
        {"name": "farms", "description": "Boundary registration, satellite analysis, Trust Engine"},
        {"name": "marketplace", "description": "Listings, matching, escrow purchases, conditional splits"},
        {"name": "trust", "description": "Hash ledger, certificates, monitoring, ground-truth calibration"},
        {"name": "ops", "description": "Operational snapshots and calibration tooling (no PII)"},
        {"name": "fpo", "description": "FPO desk: pending/flagged farms, farmer roster, credit pooling"},
        {"name": "corporate", "description": "Corporate buyer authentication"},
    ],
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_config.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Security headers + request-ID + version header ──
from app.logging_setup import request_id_var

@app.middleware("http")
async def security_and_trace_headers(request, call_next):
    import uuid as _uuid
    request_id = request.headers.get("X-Request-ID") or _uuid.uuid4().hex[:16]
    request_id_var.set(request_id)
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-API-Version"] = "1.0.0"
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; img-src 'self' data: https:; script-src 'self'; style-src 'self' 'unsafe-inline'",
    )
    if app_config.FORCE_HTTPS:
        response.headers.setdefault("Strict-Transport-Security", "max-age=63072000; includeSubDomains")
    return response


# ── Structured logging ──
from app.logging_setup import setup_logging
setup_logging()


# ── Prometheus metrics ──
try:
    from prometheus_fastapi_instrumentator import Instrumentator
    Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)
except Exception as _e:  # pragma: no cover
    print(f"metrics disabled: {_e}")


# ── Uniform error envelope: every failure returns {success:false,message,code} ──
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

@app.exception_handler(RequestValidationError)
async def validation_exception_envelope(request, exc):
    msgs = []
    for err in exc.errors():
        loc = ".".join(str(x) for x in err.get("loc", []) if x != "body")
        msgs.append(f"{loc}: {err.get('msg', 'invalid')}" if loc else str(err.get("msg", "invalid")))
    return JSONResponse(status_code=422, content={"success": False, "message": "; ".join(msgs)})

_HTTP_ERROR_CODES = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT", 429: "RATE_LIMITED"}

@app.exception_handler(StarletteHTTPException)
async def http_exception_envelope(request, exc):
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    if isinstance(detail, list):
        detail = "; ".join(d.get("msg", str(d)) for d in detail if isinstance(d, dict))
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "message": detail,
                 "code": _HTTP_ERROR_CODES.get(exc.status_code, f"HTTP_{exc.status_code}")},
    )

@app.exception_handler(Exception)
async def unhandled_exception_envelope(request, exc):
    print(f"[unhandled] {request.method} {request.url.path}: {exc}")
    return JSONResponse(status_code=500, content={"success": False, "message": "Internal server error"})


# ── Earth Engine ───
earth_engine_ready = False
try:
    import ee
    ee.Initialize(project=app_config.GEE_PROJECT)
    earth_engine_ready = True
    print("Earth Engine initialized")
except Exception as e:
    print(f"Earth Engine not available: {e}")


# ── /analyze cache ──
_analyze_cache: dict = {}
_ANALYZE_CACHE_TTL = app_config.ANALYZE_CACHE_TTL_SECONDS


# ── /predict endpoint (core endpoint at root level) ───
@app.get("/predict")
def predict(longitude: float, latitude: float):
    try:
        from app.services.ml_service import predict_biodiversity

        ndvi = None
        ndvi_source = "unavailable (no live satellite data)"
        if earth_engine_ready:
            try:
                from app.services.gee_service import get_ndvi_at_point

                sat = get_ndvi_at_point(latitude, longitude)
                if sat.get("live_satellite"):
                    ndvi = float(sat.get("ndvi"))
                    ndvi_source = str(sat.get("source"))
            except Exception as exc:
                print(f"/predict GEE point query failed: {exc}")
        if ndvi is None:
            # No live satellite data: NEVER fabricate an NDVI. A made-up index
            # would flow into the biodiversity score and read as evidence.
            # Report honestly instead (ml_source stays present for clients).
            return {
                "success": True,
                "location": {"longitude": longitude, "latitude": latitude},
                "ndvi": None,
                "ndvi_source": ndvi_source,
                "biodiversity_score": None,
                "status": "Unknown",
                "biodiversity_credits": 0.0,
                "total_credits": 0.0,
                "ml_source": None,
                "satellite_live": False,
                "message": "Live satellite data is unavailable — no NDVI estimate or credit issued.",
            }
        result = predict_biodiversity(ndvi=ndvi)
        # /predict is a biodiversity probe only — it does not estimate carbon,
        # so no carbon credit line is invented here (single source of truth).
        credits = credit_engine.credit_split(0, result["biodiversity_score"])
        return {
            "success": True,
            "location": {"longitude": longitude, "latitude": latitude},
            "ndvi": ndvi,
            "ndvi_source": ndvi_source,
            "biodiversity_score": result["biodiversity_score"],
            "status": result["status"],
            "biodiversity_credits": credits["biodiversity_credits"],
            "total_credits": credits["total_credits"],
            "ml_source": result.get("ml_source"),
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


def _with_ee_backoff(fn, *, attempts=3, base_delay=1.5):
    """Earth Engine call with exponential backoff — quota blips and
    transient timeouts retry instead of failing the scan."""
    last_err = None
    for attempt in range(attempts):
        try:
            return fn()
        except Exception as e:
            last_err = e
            if attempt < attempts - 1:
                delay = base_delay * (2 ** attempt)
                print(f"[ee] call failed ({type(e).__name__}), retry in {delay}s")
                time.sleep(delay)
    raise last_err


# ── Automatic 5-day monitoring scheduler ──
import asyncio

_MONITOR_INTERVAL_SECONDS = app_config.MONITOR_INTERVAL_SECONDS


async def _monitoring_loop():
    await asyncio.sleep(90)  # let the app finish booting first
    while True:
        try:
            if app_config.AUTO_MONITOR:
                result = run_monitoring_cycle()
                print(f"[monitor] scheduled cycle: checked={result.get('checked')} "
                      f"at_risk={result.get('at_risk_count')}")
        except Exception as e:
            print(f"[monitor] scheduled cycle failed: {e}")
        await asyncio.sleep(_MONITOR_INTERVAL_SECONDS)


@app.on_event("startup")
def _start_monitoring_scheduler():
    from app.services import ledger as _ledger
    _ledger.set_main_loop(asyncio.get_running_loop())
    if db.is_ready():
        asyncio.get_event_loop().create_task(_monitoring_loop())
        print("[monitor] 5-day scheduler armed (first cycle in 90s)")


# ── Health check helpers (used by routers) ──
def _sms_ready() -> bool:
    try:
        from app.phone_service import sms_configured
        return sms_configured()
    except Exception:
        return False


def _twilio_ready() -> bool:
    return _sms_ready()


def _require_database():
    if not db.is_ready():
        raise HTTPException(
            status_code=503,
            detail="Database is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env.",
        )


def _get_user(phone: str):
    _require_database()
    return db.get_profile(phone)


def _save_user(user: dict):
    _require_database()
    db.upsert_profile(user)


def _get_user_farms(phone: str):
    _require_database()
    return db.get_farms(phone)


def _save_farm(farm: dict):
    _require_database()
    return db.insert_farm(farm)


def _store_otp(phone: str, otp: str):
    redis_store.store_otp(phone, otp)


def _verify_otp(phone: str, otp: str) -> bool:
    return redis_store.verify_otp(phone, otp)


def _clear_otp(phone: str):
    redis_store.clear_otp(phone)


# ── Health endpoints ──
@app.get("/")
def root():
    return {
        "message": "CarbonX API running",
        "version": "1.0.0",
        "supabase": db.is_ready(),
        "sms": _sms_ready(),
        "twilio": _twilio_ready(),
        "earth_engine": earth_engine_ready,
    }


@app.get("/health")
def health():
    database = db.health_check()
    return {
        "success": database["ready"],
        "database": database,
        "sms": {"ready": _sms_ready(), "provider": "Textplate"},
        "twilio": {"ready": _twilio_ready(), "provider": "Textplate"},
        "earth_engine": {"ready": earth_engine_ready},
    }


# ── /analyze models ───
class GeoJSONPolygon(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["Feature"] = "Feature"
    geometry: dict

    @field_validator("geometry")
    @classmethod
    def _validate_polygon(cls, geom):
        ok, err = _validate_polygon_geojson({"type": "Feature", "geometry": geom})
        if not ok:
            raise ValueError(err)
        return geom


def _validate_polygon_geojson(geojson: dict) -> tuple[bool, str]:
    if not isinstance(geojson, dict):
        return False, "GeoJSON must be an object"
    geom = geojson.get("geometry") or {}
    if geom.get("type") != "Polygon":
        return False, "GeoJSON geometry type must be Polygon"
    rings = geom.get("coordinates")
    if not isinstance(rings, list) or not rings:
        return False, "Polygon coordinates missing"
    ring = rings[0]
    if not isinstance(ring, list) or len(ring) < 4:
        return False, "Polygon ring needs at least 4 positions"
    for pos in ring:
        if (not isinstance(pos, list) or len(pos) < 2
                or not all(isinstance(c, (int, float)) and math.isfinite(c) for c in pos[:2])):
            return False, "Invalid coordinate in polygon ring"
        lon, lat = pos[0], pos[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            return False, "Coordinate out of WGS84 range"
    if ring[0][:2] != ring[-1][:2]:
        return False, "Polygon ring must be closed (first == last position)"
    lons = [pos[0] for pos in ring]
    lats = [pos[1] for pos in ring]
    if (max(lons) - min(lons)) >= 60 or (max(lats) - min(lats)) >= 60:
        return False, "Polygon too large — exceeds scan limit, draw a single farm plot"
    return True, ""


class AnalyzeModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    geojson: GeoJSONPolygon
    farm_name: Optional[str] = "My Farm"
    crop_type: Optional[str] = "Mixed Crop"
    irrigation: Optional[str] = "Drip"


# ── /analyze endpoint (core endpoint at root level) ───
@app.post("/analyze")
def analyze(data: AnalyzeModel):
    try:
        geojson = data.geojson.model_dump()
        ok, err = _validate_polygon_geojson(geojson)
        if not ok:
            return {"success": False, "message": err}

        import json as _json
        cache_key = _json.dumps([data.geojson, data.crop_type], sort_keys=True, default=str)
        cached = _analyze_cache.get(cache_key)
        if cached and time.time() - cached[0] < _ANALYZE_CACHE_TTL:
            return cached[1]

        ml_result = None
        s2_scene = None
        scan_est = None
        max_area = app_config.ANALYZE_MAX_AREA_HECTARES
        try:
            approx_area = _polygon_area_hectares(geojson)
            if approx_area > max_area:
                return {"success": False,
                        "message": f"Parcel area {approx_area:,.0f} ha exceeds the {max_area:,} ha scan limit — redraw the boundary"}
        except Exception:
            pass
        if earth_engine_ready:
            import ee
            coordinates = geojson["geometry"]["coordinates"]
            polygon = ee.Geometry.Polygon(coordinates)
            collection = (
                ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
                .filterBounds(polygon)
                .filterDate("2024-01-01", "2025-12-31")
                .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 20))
            )
            image = collection.median()
            ndvi = image.normalizedDifference(["B8", "B4"]).rename("NDVI")
            ndvi_value = _with_ee_backoff(lambda: ndvi.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e13,
            ).get("NDVI").getInfo())
            evi = image.expression(
                "2.5 * ((NIR - RED) / (NIR + 6 * RED - 7.5 * BLUE + 1))",
                {"NIR": image.select("B8"), "RED": image.select("B4"), "BLUE": image.select("B2")},
            )
            evi_value = _with_ee_backoff(lambda: evi.reduceRegion(
                reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e13,
            ).values().get(0).getInfo())
            area_hectares = round(_with_ee_backoff(lambda: polygon.area().getInfo()) / 10000, 2)

            try:
                B4, B8, B3, B11 = (image.select("B4"), image.select("B8"),
                                   image.select("B3"), image.select("B11"))
                stack = (ndvi.rename("NDVI")
                         .addBands(image.normalizedDifference(["B3", "B11"]).rename("NDWI"))
                         .addBands(image.expression("((NIR-RED)/(NIR+RED+0.5))*1.5",
                                    {"NIR": B8, "RED": B4}).rename("SAVI"))
                         .addBands(B4.rename("B4"))
                         .addBands(B8.rename("B8"))
                         .addBands(B11.rename("B11"))
                         .addBands(collection.map(lambda i: i.normalizedDifference(["B8", "B4"]))
                                   .reduce(ee.Reducer.stdDev()).rename("NDVI_STD"))
                         .addBands(collection.map(lambda i: i.select("B8"))
                                   .reduce(ee.Reducer.variance()).rename("B8_VAR")))
                feat_values = stack.reduceRegion(
                    reducer=ee.Reducer.mean(), geometry=polygon, scale=10, maxPixels=1e9,
                ).getInfo()
                real_features = {k: feat_values.get(k) for k in
                                 ("NDVI", "NDWI", "SAVI", "NDVI_STD", "B4", "B8", "B11", "B8_VAR")}
                if any(v is None for v in real_features.values()):
                    real_features = None
            except Exception as e:
                print(f"[analyze] real feature extraction failed: {e}")
                real_features = None

            try:
                from app.services.ml_service import predict_biodiversity
                ml_result = predict_biodiversity(ndvi=ndvi_value, evi=evi_value,
                                                 area_ha=area_hectares, features=real_features)
                biodiversity_score = ml_result["biodiversity_score"]
            except Exception:
                biodiversity_score = round(min(max(ndvi_value * 100, 30), 98), 1)
            satellite_source = "Google Earth Engine · Sentinel-2 SR"
            try:
                s2_scene = collection.first().get("system:index").getInfo()
            except Exception:
                s2_scene = None

            scan_est = credit_engine.quick_scan_estimate(area_hectares, data.crop_type, ndvi_value, features=real_features)
            scan_est["formula_version"] = app_config.FORMULA_VERSION
            carbon_tonnes = scan_est["credits_tco2e"]
        else:
            # No live satellite data: NEVER fabricate an NDVI, and never turn a
            # made-up index into a credit. Without imagery there is no evidence,
            # so the scan returns an honest empty result and the record is routed
            # to FPO review instead of inventing a number.
            area_hectares = _polygon_area_hectares(geojson)
            return {
                "success": True,
                "ndvi": None,
                "evi": None,
                "tree_cover": 0.0,
                "soil_moisture": 0.0,
                "carbon_tonnes": 0.0,
                "carbon_credits": 0.0,
                "biodiversity_credits": 0.0,
                "total_credits": 0.0,
                "area_hectares": area_hectares,
                "vegetation_health": "Unknown",
                "biodiversity_score": None,
                "ml_source": None,
                "ai_confidence": None,
                "satellite_source": "unavailable (no live Sentinel-2 data)",
                "satellite_live": False,
                "credits_available": False,
                "s2_scene": None,
                "scan_estimate": None,
                "stage1": None,
                "message": ("Live satellite data is unavailable, so no credit can be issued. "
                            "Retry when Earth Engine is reachable, or route this record to FPO review."),
            }

        tree_cover = round(min(max(ndvi_value * 100, 0), 100), 2)
        soil_moisture = round(min(max(evi_value * 25, 0), 100), 2)
        credits = credit_engine.credit_split(carbon_tonnes, biodiversity_score)
        stage1 = credit_engine.stage1_verification(data.crop_type, ndvi_value)
        veg_health = (
            "Excellent" if ndvi_value >= 0.7 else "Good" if ndvi_value >= 0.5
            else "Moderate" if ndvi_value >= 0.3 else "Low"
        )
        ml_source = ml_result.get("source") if isinstance(ml_result, dict) else None
        response = {
            "success": True,
            "ndvi": round(ndvi_value, 3),
            "evi": round(evi_value, 3),
            "tree_cover": tree_cover,
            "soil_moisture": soil_moisture,
            "carbon_tonnes": carbon_tonnes,
            "carbon_credits": credits["carbon_credits"],
            "biodiversity_credits": credits["biodiversity_credits"],
            "total_credits": credits["total_credits"],
            "area_hectares": area_hectares,
            "vegetation_health": veg_health,
            "biodiversity_score": biodiversity_score,
            "ml_source": ml_source,
            "ai_confidence": round(min(85 + ndvi_value * 20, 99.5), 1),
            "satellite_source": satellite_source,
            "s2_scene": s2_scene,
            "scan_estimate": {
                "method": "credit_engine.quick_scan_estimate (single source of truth)",
                "evidence_quality": scan_est.get("evidence_quality"),
                "ci90": scan_est.get("ci90"),
            },
            "stage1": stage1,
        }
        if len(_analyze_cache) > 256:
            _analyze_cache.clear()
        _analyze_cache[cache_key] = (time.time(), response)
        return response
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Include routers ──
from app.routes.auth_router import router as auth_router
from app.routes.farms_router import router as farms_router
from app.routes.marketplace_router import router as marketplace_router
from app.routes.trust_router import router as trust_router
from app.routes.ops_router import router as ops_router
from app.routes.fpo_router import router as fpo_router
from app.routes.corporate_router import router as corporate_router

app.include_router(auth_router)
app.include_router(auth_router, prefix="/auth")
app.include_router(farms_router)
app.include_router(marketplace_router)
app.include_router(trust_router)
app.include_router(ops_router)
app.include_router(fpo_router)
app.include_router(corporate_router)


# ── Voice agent ──
from app.voice_agent.voice_routes import router as voice_router
app.include_router(voice_router)


# ── WebSocket: live ledger updates ──
_ledger_ws_subscribers: dict[str, set[WebSocket]] = {}


async def _ledger_broadcast(farm_id: str, event: dict):
    subscribers = _ledger_ws_subscribers.get(farm_id)
    if not subscribers:
        return
    import json as _json
    msg = _json.dumps(event, default=str)
    dead = set()
    for ws in subscribers:
        try:
            await ws.send_text(msg)
        except Exception:
            dead.add(ws)
    for ws in dead:
        subscribers.discard(ws)


@app.websocket("/ws/ledger/{farm_id}")
async def websocket_ledger(ws: WebSocket, farm_id: str):
    await ws.accept()
    _ledger_ws_subscribers.setdefault(farm_id, set()).add(ws)
    try:
        chain = ledger.get_chain(farm_id)
        if chain:
            await ws.send_text(json.dumps({
                "type": "snapshot",
                "farm_id": farm_id,
                "events": [{k: v for k, v in e.items() if not k.startswith("_")} for e in chain],
            }, default=str))
        while True:
            await ws.receive_text()
    except Exception:
        _ledger_ws_subscribers.get(farm_id, set()).discard(ws)


# ── Monitoring cycle (used by scheduler and /monitor/run) ──
NDVI_DROP_ALERT = app_config.NDVI_DROP_ALERT


@app.post("/monitor/run")
def run_monitoring_cycle(
    current_user: Optional[dict] = Depends(get_current_user_optional),
    x_monitor_secret: Optional[str] = Header(None),
):
    required_secret = app_config.MONITOR_SECRET
    if required_secret and x_monitor_secret != required_secret:
        if not (current_user and current_user.get("role") in ("fpo", "admin", "verifier")):
            return {"success": False, "message": "Monitoring requires the monitor secret or an FPO/admin session"}
    if not db.is_ready():
        return {"success": False, "message": "Monitoring needs the database (demo mode has no live farms)"}
    try:
        sb = db._client()
        farms = (sb.table("farms").select("id,name,ndvi,status,last_monitor_ndvi,last_monitored_at").execute().data) or []
        checked = 0
        at_risk = []
        healthy = 0
        now_iso = datetime.now(timezone.utc).isoformat()
        for farm in farms:
            if str(farm.get("status") or "").lower() in ("pending",):
                continue
            checked += 1
            current = farm.get("ndvi")
            if current is None:
                continue
            current = float(current)
            last = farm.get("last_monitor_ndvi")
            drop = round(float(last) - current, 3) if last is not None else 0.0
            sb.table("farms").update({
                "last_monitor_ndvi": current,
                "last_monitored_at": now_iso,
            }).eq("id", farm["id"]).execute()
            if last is not None and drop >= NDVI_DROP_ALERT:
                sb.table("farms").update({"status": "Flagged"}).eq("id", farm["id"]).execute()
                ledger.append_event(farm["id"], "MONITOR", {
                    "risk": "ndvi_drop", "drop": drop,
                    "previous_ndvi": float(last), "current_ndvi": current,
                    "note": "Credits at-risk — routed to FPO review (drought/disease/abandonment possible)",
                })
                at_risk.append({
                    "farm_id": farm["id"], "name": farm.get("name"),
                    "drop": drop, "previous_ndvi": float(last), "current_ndvi": current,
                })
            else:
                healthy += 1
        return {
            "success": True, "checked": checked, "healthy": healthy,
            "at_risk_count": len(at_risk), "at_risk": at_risk,
            "alert_threshold": NDVI_DROP_ALERT, "ran_at": now_iso,
        }
    except Exception as e:
        return {"success": False, "message": str(e)}


# ── Demo login (only when DB not configured) ──
@app.post("/demo/login")
def demo_login(data: dict = None):
    if db.is_ready():
        return {"success": False, "message": "Demo login is only available in demo mode (database not configured)"}
    body = data or {}
    phone = str(body.get("phone") or "9000000001")
    farmer = _sample_data().FARMERS.get(phone)
    if not farmer:
        return {"success": False, "message": "Unknown demo farmer"}
    token = create_access_token({"phone": phone, "name": farmer["name"], "role": "farmer", "demo": True})
    return {
        "success": True, "demo_mode": True, "token": token,
        "user": {
            "phone": phone, "name": farmer["name"], "role": "farmer",
            "district": farmer.get("district"), "village": farmer.get("village"),
            "upi": farmer.get("upi"), "demo": True,
        },
        "message": f"Demo session started for {farmer['name']}",
    }