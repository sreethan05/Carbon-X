import json
import logging
import os
import re
import time
import uuid
from collections import defaultdict, deque
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import supabase_db as db
from app.security import require_role
from app.services.geocoding_service import geocode_village

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])
logger = logging.getLogger("carbonx.voice")

SYSTEM_PROMPT = (
    "You are the CarbonX Farmer Assistant. Help only the authenticated user with their own account. "
    "Support Telugu, Hindi, English, and mixed speech. Use backend tools for account data. Never invent "
    "values or reveal another user's data, PII, documents, phone, Aadhaar, bank, UPI, tokens, passwords, "
    "or internal IDs. Phone OTP confirms phone control only; it is not Aadhaar eKYC. Never approve land, "
    "issue credits, approve payments, change payout details, or change benefit-sharing. Ask confirmation "
    "before saving form values. Use only authorized tools and backend results."
)

ALLOWED_TOOLS = {
    "get_my_plots",
    "get_my_document_status",
    "get_my_score",
    "get_my_credits",
    "get_my_earnings",
    "get_my_payout_status",
    "search_location",
    "explain_land_onboarding",
    "navigate_to",
    "propose_safe_form_update",
}

SAFE_FORM_FIELDS = {
    "name",
    "village",
    "district",
    "state",
    "mandal",
    "survey number",
    "survey_number",
    "khata number",
    "khata_number",
    "crop type",
    "crop_type",
    "land type",
    "land_type",
    "document type",
    "document_type",
    "preferred language",
    "preferred_language",
}

ALLOWED_ACTIONS = {
    "NAVIGATE",
    "OPEN_MAP",
    "START_BOUNDARY_DRAWING",
    "FOCUS_FIELD",
    "SHOW_SCORE",
    "SHOW_EARNINGS",
    "SHOW_DOCUMENT_STATUS",
}

FIELD_ALIASES = {
    "name": "name",
    "full name": "name",
    "village": "village",
    "gramam": "village",
    "gaon": "village",
    "district": "district",
    "jilla": "district",
    "zilla": "district",
    "state": "state",
    "mandal": "mandal",
    "survey": "survey number",
    "survey no": "survey number",
    "survey number": "survey number",
    "khata": "khata number",
    "khata number": "khata number",
    "crop": "crop type",
    "crop type": "crop type",
    "land": "land type",
    "land type": "land type",
    "document": "document type",
    "document type": "document type",
    "preferred language": "preferred language",
    "language": "preferred language",
}

NAVIGATION_TARGETS = {
    "dashboard": "/dashboard",
    "plots": "/farm-analytics",
    "farms": "/farm-analytics",
    "documents": "/farm-verification",
    "kyc": "/farm-verification",
    "score": "/farm-analytics",
    "credits": "/wallet",
    "earnings": "/wallet",
    "payouts": "/wallet",
    "wallet": "/wallet",
    "map": "/farm-map",
    "boundary": "/farm-map",
    "onboarding": "/onboarding",
    "marketplace": "/marketplace",
    "support": "/support",
}

SENSITIVE_KEYS = {
    "aadhaar",
    "aadhaar_last4",
    "otp",
    "upi",
    "bank",
    "account",
    "ifsc",
    "token",
    "password",
    "secret",
    "key",
    "geojson",
    "coordinates",
    "document_content_base64",
    "document_sha256",
    "perceptual_hash",
    "phone",
    "owner_phone",
    "farmer_phone",
}

_rate_windows: dict[str, deque[float]] = defaultdict(deque)
_voice_sessions: dict[str, dict[str, Any]] = {}


class TextVoiceQuery(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    language_code: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[dict[str, Any]] = None


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _sarvam_headers() -> dict[str, str]:
    key = os.getenv("SARVAM_API_KEY", "").strip()
    if not key:
        raise RuntimeError("Sarvam API key is not configured")
    return {"api-subscription-key": key}


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS or any(part in key.lower() for part in ("aadhaar", "otp", "password", "token", "secret")):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive(item)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"\b\d{12}\b", "[REDACTED_AADHAAR]", value)
        value = re.sub(r"\b\d{6}\b", "[REDACTED_OTP]", value)
        value = re.sub(r"\b\d{8,11}\b", "[REDACTED_ID]", value)
        value = re.sub(r"Bearer\s+[A-Za-z0-9._-]+", "Bearer [REDACTED_TOKEN]", value)
    return value


def _log_event(event: str, payload: dict[str, Any]) -> None:
    logger.info("%s %s", event, json.dumps(redact_sensitive(payload), ensure_ascii=False))


def _rate_limit(current_user: dict) -> None:
    limit = _env_int("VOICE_RATE_LIMIT_PER_MINUTE", 10)
    now = time.time()
    key = current_user.get("phone", "unknown")
    window = _rate_windows[key]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(status_code=429, detail="Voice assistant rate limit exceeded")
    window.append(now)


def _voice_session(current_user: dict, session_id: Optional[str]) -> str:
    ttl = _env_int("VOICE_SESSION_TTL_SECONDS", 900)
    now = time.time()
    for sid, row in list(_voice_sessions.items()):
        if now - row["created_at"] > ttl:
            _voice_sessions.pop(sid, None)
    phone = current_user.get("phone")
    if session_id:
        row = _voice_sessions.get(session_id)
        if not row or row.get("phone") != phone or now - row["created_at"] > ttl:
            raise HTTPException(status_code=403, detail="Voice session is invalid or expired")
        return session_id
    new_id = uuid.uuid4().hex
    _voice_sessions[new_id] = {"phone": phone, "created_at": now}
    return new_id


def _language_code(language_code: Optional[str]) -> str:
    allowed = {"te-IN", "hi-IN", "en-IN"}
    value = language_code or os.getenv("SARVAM_DEFAULT_LANGUAGE", "te-IN")
    return value if value in allowed else os.getenv("SARVAM_DEFAULT_LANGUAGE", "te-IN")


async def _sarvam_stt(audio: bytes, filename: str, content_type: str, language_code: str) -> dict[str, Any]:
    model = os.getenv("SARVAM_STT_MODEL", "saaras:v3")
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(
            "https://api.sarvam.ai/speech-to-text",
            headers=_sarvam_headers(),
            data={"model": model, "mode": "codemix", "language_code": language_code},
            files={"file": (filename or "voice.webm", audio, content_type or "audio/webm")},
        )
        res.raise_for_status()
        return res.json()


def _transcript_from_stt(stt: dict[str, Any]) -> str:
    for key in ("transcript", "text", "transcribed_text"):
        value = stt.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    data = stt.get("data")
    if isinstance(data, dict):
        return _transcript_from_stt(data)
    return ""


async def _sarvam_tts(text: str, language_code: str) -> Optional[str]:
    if not os.getenv("SARVAM_API_KEY", "").strip():
        return None
    model = os.getenv("SARVAM_TTS_MODEL", "bulbul:v3")
    safe_text = text[:2400]
    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post(
            "https://api.sarvam.ai/text-to-speech",
            headers={**_sarvam_headers(), "Content-Type": "application/json"},
            json={
                "text": safe_text,
                "language_code": language_code,
                "model": model,
                "speaker": "shubh",
                "pace": 0.95,
                "speech_sample_rate": 24000,
                "output_audio_codec": "wav",
            },
        )
        res.raise_for_status()
        audios = res.json().get("audios") or []
        return "".join(audios) if audios else None


def _tool_schema() -> list[dict[str, Any]]:
    def fn(name: str, description: str, properties: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties or {},
                    "additionalProperties": False,
                },
            },
        }

    return [
        fn("get_my_plots", "Return the authenticated farmer's plot summary only."),
        fn("get_my_document_status", "Return the authenticated farmer's land document verification status."),
        fn("get_my_score", "Return the authenticated farmer's carbon and biodiversity score summary."),
        fn("get_my_credits", "Return the authenticated farmer's credit totals."),
        fn("get_my_earnings", "Return the authenticated farmer's earning summary."),
        fn("get_my_payout_status", "Return payout status without bank, UPI, or beneficiary details."),
        fn("search_location", "Search a village or location in India.", {"query": {"type": "string", "maxLength": 120}}),
        fn("explain_land_onboarding", "Explain CarbonX land onboarding steps."),
        fn("navigate_to", "Navigate to a safe CarbonX page.", {"target": {"type": "string", "maxLength": 40}}),
        fn(
            "propose_safe_form_update",
            "Propose safe form values that require farmer confirmation before saving.",
            {"fields": {"type": "object", "additionalProperties": {"type": "string", "maxLength": 120}}},
        ),
    ]


def _sanitize_farm(farm: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": farm.get("name") or "My Farm",
        "crop_type": farm.get("crop_type") or "",
        "area_hectares": farm.get("area_hectares") or 0,
        "status": farm.get("status") or "",
        "ndvi": farm.get("ndvi") or 0,
        "carbon_tonnes": farm.get("carbon_tonnes") or 0,
        "biodiversity_score": farm.get("biodiversity_score") or 0,
        "total_credits": farm.get("total_credits") or 0,
    }


def _my_farms(phone: str) -> list[dict[str, Any]]:
    return [_sanitize_farm(farm) for farm in db.get_farms(phone)]


def _my_listings(phone: str) -> list[dict[str, Any]]:
    return [row for row in db.get_listings(None) if row.get("farmer_phone") == phone]


def _totals(farms: list[dict[str, Any]]) -> dict[str, float]:
    return {
        "carbon_tonnes": round(sum(float(f.get("carbon_tonnes") or 0) for f in farms), 2),
        "total_credits": round(sum(float(f.get("total_credits") or 0) for f in farms), 2),
        "biodiversity_score": round(sum(float(f.get("biodiversity_score") or 0) for f in farms) / max(len(farms), 1), 1),
    }


def _safe_action(action_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    if action_type not in ALLOWED_ACTIONS:
        raise HTTPException(status_code=400, detail="Invalid voice action")
    if action_type == "NAVIGATE":
        path = payload.get("path")
        if path not in NAVIGATION_TARGETS.values():
            raise HTTPException(status_code=400, detail="Unsafe navigation target")
    return {"type": action_type, "payload": payload}


def execute_voice_tool(name: str, args: dict[str, Any], current_user: dict) -> dict[str, Any]:
    if name not in ALLOWED_TOOLS:
        raise HTTPException(status_code=400, detail="Invalid voice tool")
    phone = current_user.get("phone")
    role = current_user.get("role", "farmer")
    if role != "farmer":
        raise HTTPException(status_code=403, detail="Voice assistant is available to farmers only")

    if name == "get_my_plots":
        farms = _my_farms(phone)
        return {"plots": farms, "count": len(farms), "actions": [_safe_action("SHOW_SCORE", {})]}
    if name == "get_my_document_status":
        record = db.get_kyc_status(phone)
        status = record.get("status") if record else "PENDING"
        reasons = record.get("reasons") if record else []
        return {"status": status, "reasons": reasons[:3] if isinstance(reasons, list) else [], "actions": [_safe_action("SHOW_DOCUMENT_STATUS", {})]}
    if name == "get_my_score":
        farms = _my_farms(phone)
        return {"scores": _totals(farms), "plots_count": len(farms), "actions": [_safe_action("SHOW_SCORE", {})]}
    if name == "get_my_credits":
        farms = _my_farms(phone)
        listings = _my_listings(phone)
        return {"credits": _totals(farms), "active_listings": len([l for l in listings if l.get("status") == "Active"])}
    if name == "get_my_earnings":
        listings = _my_listings(phone)
        estimated = round(sum(float(l.get("current_bid") or 0) for l in listings), 2)
        return {"estimated_earnings": estimated, "currency": "INR", "actions": [_safe_action("SHOW_EARNINGS", {})]}
    if name == "get_my_payout_status":
        return {"status": "Payout details are available in your wallet after approved credit sales.", "bank_or_upi": "[REDACTED]"}
    if name == "search_location":
        query = (args.get("query") or "")[:120]
        result = geocode_village(query)
        return {"query": query, "result": result, "actions": [_safe_action("OPEN_MAP", {})] if result else []}
    if name == "explain_land_onboarding":
        return {"steps": ["Verify land document", "Draw farm boundary", "Review satellite score", "Save farm", "List approved credits when eligible"]}
    if name == "navigate_to":
        target = str(args.get("target") or "").lower().strip()
        path = NAVIGATION_TARGETS.get(target)
        if not path:
            raise HTTPException(status_code=400, detail="Unsafe navigation target")
        return {"actions": [_safe_action("NAVIGATE", {"path": path})]}
    if name == "propose_safe_form_update":
        proposed = {}
        for key, value in (args.get("fields") or {}).items():
            normalized = key.lower().strip().replace("_", " ")
            if normalized in SAFE_FORM_FIELDS:
                proposed[normalized] = str(value)[:120]
        return {"requires_confirmation": True, "proposed_fields": proposed, "actions": [_safe_action("FOCUS_FIELD", {"fields": list(proposed.keys())})]}
    raise HTTPException(status_code=400, detail="Invalid voice tool")


def _fallback_tool_for_text(text: str) -> tuple[str, dict[str, Any]]:
    lowered = text.lower()
    if any(word in lowered for word in ("form", "survey", "crop", "mandal", "khata", "fill", "set my", "change my", "update my", "document type", "land type", "name", "language", "upi")):
        fields = _extract_safe_fields(text)
        return "propose_safe_form_update", {"fields": fields or {"crop type": text[:120]}}
    if any(word in lowered for word in ("document", "kyc", "patta", "పత్ర", "दस्तावेज")):
        return "get_my_document_status", {}
    if any(word in lowered for word in ("earning", "payout", "payment", "income", "డబ్బు", "कमाई")):
        return "get_my_earnings", {}
    if any(word in lowered for word in ("credit", "carbon", "score", "biodiversity", "ndvi")):
        return "get_my_score", {}
    if any(word in lowered for word in ("map", "boundary", "draw", "select land", "land area", "mark land", "outline", "నక्श", "सीमा")):
        return "navigate_to", {"target": "map"}
    if any(word in lowered for word in ("village", "location", "search", "గ్రామ", "गांव")):
        return "search_location", {"query": text[:120]}
    return "get_my_plots", {}


def _extract_safe_fields(text: str) -> dict[str, str]:
    fields = {}
    cleaned = re.sub(r"\s+", " ", text).strip()
    patterns = [
        (r"\b(?:my\s+)?name\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "name"),
        (r"\bvillage\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "village"),
        (r"\bdistrict\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "district"),
        (r"\bstate\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "state"),
        (r"\bmandal\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "mandal"),
        (r"\bsurvey(?:\s+number|\s+no)?\s+(?:is|as|to)?\s*([A-Za-z0-9/-]{1,40})", "survey number"),
        (r"\bkhata(?:\s+number)?\s+(?:is|as|to)?\s*([A-Za-z0-9/-]{1,40})", "khata number"),
        (r"\bcrop(?:\s+type)?\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "crop type"),
        (r"\bland(?:\s+type)?\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "land type"),
        (r"\bdocument(?:\s+type)?\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "document type"),
        (r"\b(?:preferred\s+)?language\s+(?:is|as|to)?\s*([A-Za-z][A-Za-z .'-]{1,60})", "preferred language"),
    ]
    for pattern, field in patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            value = re.split(r"\b(?:and|also|then|please)\b", match.group(1), flags=re.IGNORECASE)[0].strip(" .,")
            if value:
                fields[field] = value[:120]
    return fields


def _fallback_answer(text: str, tool_result: dict[str, Any], language_code: str) -> str:
    if language_code == "hi-IN":
        return "मैंने आपके CarbonX खाते से सुरक्षित जानकारी देखी है. कोई निजी जानकारी साझा नहीं की गई."
    if language_code == "te-IN":
        return "మీ CarbonX ఖాతాలోని సురక్షిత వివరాలు చూశాను. వ్యక్తిగత సమాచారం చూపించలేదు."
    return "I checked your CarbonX account safely. No private details were shared."


async def _sarvam_chat(text: str, language_code: str, current_user: dict) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    if not os.getenv("SARVAM_API_KEY", "").strip():
        tool_name, args = _fallback_tool_for_text(text)
        tool_result = execute_voice_tool(tool_name, args, current_user)
        return _fallback_answer(text, tool_result, language_code), tool_result.get("actions", []), tool_result

    model = os.getenv("SARVAM_CHAT_MODEL", "sarvam-105b-conversations")
    safe_text = str(redact_sensitive(text))[:1000]
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": safe_text},
    ]
    async with httpx.AsyncClient(timeout=20.0) as client:
        first = await client.post(
            "https://api.sarvam.ai/v1/chat/completions",
            headers={**_sarvam_headers(), "Content-Type": "application/json"},
            json={"model": model, "messages": messages, "tools": _tool_schema(), "tool_choice": "auto"},
        )
        first.raise_for_status()
        choice = first.json()["choices"][0]
        message = choice.get("message") or {}
        actions: list[dict[str, Any]] = []
        tool_result: dict[str, Any] = {}
        if choice.get("finish_reason") == "tool_calls" and message.get("tool_calls"):
            messages.append(message)
            for call in message["tool_calls"][:2]:
                fn = call.get("function", {})
                name = fn.get("name")
                if name not in ALLOWED_TOOLS:
                    raise HTTPException(status_code=400, detail="Invalid voice tool")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                tool_result = execute_voice_tool(name, args, current_user)
                actions.extend(tool_result.get("actions") or [])
                messages.append({"role": "tool", "tool_call_id": call.get("id"), "content": json.dumps(redact_sensitive(tool_result), ensure_ascii=False)})
            final = await client.post(
                "https://api.sarvam.ai/v1/chat/completions",
                headers={**_sarvam_headers(), "Content-Type": "application/json"},
                json={"model": model, "messages": messages},
            )
            final.raise_for_status()
            content = final.json()["choices"][0]["message"].get("content") or _fallback_answer(text, tool_result, language_code)
            return content[:1200], actions, tool_result
        return (message.get("content") or _fallback_answer(text, {}, language_code))[:1200], actions, tool_result


async def _handle_text_query(text: str, language_code: str, session_id: Optional[str], current_user: dict, count_rate: bool = True) -> dict[str, Any]:
    if count_rate:
        _rate_limit(current_user)
    sid = _voice_session(current_user, session_id)
    _log_event("voice_query", {"phone": current_user.get("phone"), "role": current_user.get("role"), "text": text})
    try:
        answer, actions, tool_result = await _sarvam_chat(text, language_code, current_user)
    except HTTPException:
        raise
    except Exception:
        tool_name, args = _fallback_tool_for_text(text)
        tool_result = execute_voice_tool(tool_name, args, current_user)
        answer = _fallback_answer(text, tool_result, language_code)
        actions = tool_result.get("actions", [])
    try:
        audio = await _sarvam_tts(answer, language_code)
    except Exception:
        audio = None
    return {
        "success": True,
        "session_id": sid,
        "transcript": redact_sensitive(text),
        "language_code": language_code,
        "response_text": answer,
        "audio_base64": audio,
        "audio_mime_type": "audio/wav" if audio else None,
        "actions": actions,
        "confirmation": tool_result if tool_result.get("requires_confirmation") else None,
        "tool_result": redact_sensitive(tool_result),
    }


@router.post("/text-query")
async def text_query(data: TextVoiceQuery, current_user: dict = Depends(require_role("farmer"))):
    language_code = _language_code(data.language_code)
    return await _handle_text_query(data.text.strip(), language_code, data.session_id, current_user)


@router.post("/query")
async def voice_query(
    file: UploadFile = File(...),
    language_code: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    current_user: dict = Depends(require_role("farmer")),
):
    _rate_limit(current_user)
    max_bytes = _env_int("VOICE_MAX_AUDIO_SECONDS", 30) * 64_000
    audio = await file.read(max_bytes + 1)
    if len(audio) > max_bytes:
        raise HTTPException(status_code=413, detail="Audio is too long")
    lang = _language_code(language_code)
    try:
        stt = await _sarvam_stt(audio, file.filename or "voice.webm", file.content_type or "audio/webm", lang)
        transcript = (stt.get("transcript") or "").strip()
        lang = _language_code(stt.get("language_code") or lang)
    except Exception:
        transcript = ""
    if not transcript:
        sid = _voice_session(current_user, session_id)
        answer = "I could not hear that clearly. Please try again."
        audio_response = None
        try:
            audio_response = await _sarvam_tts(answer, lang)
        except Exception:
            pass
        return {
            "success": True,
            "session_id": sid,
            "transcript": "",
            "language_code": lang,
            "response_text": answer,
            "audio_base64": audio_response,
            "audio_mime_type": "audio/wav" if audio_response else None,
            "actions": [],
            "confirmation": None,
            "tool_result": {},
        }
    return await _handle_text_query(transcript, lang, session_id, current_user, count_rate=False)
