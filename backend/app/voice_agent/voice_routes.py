"""FastAPI routes for CarbonX Farmer Voice Assistant.

Exposes /query (audio multipart) and /text-query endpoints with farmer role authentication,
rate-limiting, session tracking, and seamless delegation to voice_agent core.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app import supabase_db as db
from app.security import require_role
from app.voice_agent.prompt_templates import SYSTEM_PROMPT
from app.voice_agent.voice_agent import (
    ALLOWED_ACTIONS,
    ALLOWED_TOOLS,
    FIELD_ALIASES,
    NAVIGATION_TARGETS,
    SAFE_FORM_FIELDS,
    SENSITIVE_KEYS,
    _env_int,
    _log_event,
    _my_farms,
    _my_listings,
    _rate_windows,
    _safe_action,
    _sanitize_farm,
    _sarvam_chat,
    _sarvam_headers,
    _sarvam_stt,
    _sarvam_tts,
    _totals,
    _voice_sessions,
    execute_voice_tool,
    extract_safe_fields as _extract_safe_fields,
    fallback_answer as _fallback_answer,
    fallback_tool_for_text as _fallback_tool_for_text,
    get_voice_session as _voice_session,
    handle_text_query as _handle_text_query,
    handle_voice_query,
    language_code as _language_code,
    rate_limit as _rate_limit,
    redact_sensitive,
    transcript_from_stt as _transcript_from_stt,
)

router = APIRouter(prefix="/api/v1/voice", tags=["voice"])


class TextVoiceQuery(BaseModel):
    text: str = Field(..., min_length=1, max_length=1000)
    language_code: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[dict[str, Any]] = None


@router.post("/text-query")
async def text_query(data: TextVoiceQuery, current_user: dict = Depends(require_role("farmer"))):
    """Handle text query from farmer with role verification and rate limiting."""
    lang = _language_code(data.language_code)
    return await _handle_text_query(data.text.strip(), lang, data.session_id, current_user)


@router.post("/query")
async def voice_query(
    file: UploadFile = File(...),
    language_code: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
    current_user: dict = Depends(require_role("farmer")),
):
    """Handle voice audio file from farmer (STT -> Intent/LLM -> TTS)."""
    return await handle_voice_query(file, language_code, session_id, current_user)


# Legacy re-exports to guarantee complete backward compatibility with all test suites
__all__ = [
    "router",
    "db",
    "SYSTEM_PROMPT",
    "ALLOWED_TOOLS",
    "SAFE_FORM_FIELDS",
    "ALLOWED_ACTIONS",
    "FIELD_ALIASES",
    "NAVIGATION_TARGETS",
    "SENSITIVE_KEYS",
    "TextVoiceQuery",
    "execute_voice_tool",
    "redact_sensitive",
    "_safe_action",
    "_sarvam_stt",
    "_sarvam_tts",
    "_log_event",
    "_rate_limit",
    "_voice_session",
    "_language_code",
    "_extract_safe_fields",
    "_fallback_tool_for_text",
    "_fallback_answer",
    "_sarvam_chat",
    "_handle_text_query",
    "_rate_windows",
    "_voice_sessions",
    "_transcript_from_stt",
    "text_query",
    "voice_query",
]
