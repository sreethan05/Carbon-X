"""Voice agent tests — query routing, tool dispatch, session isolation,
rate limiting, audio size limits, and security constraints.

Hermetic: runs without external Sarvam API calls or live DB access.
Imports and runs the base TestVoiceRoutes suite from tests.voice_agent.test_voice_routes
and extends it with additional edge case coverage (rate limits, 413 audio payload,
session continuity, and language normalization).

Run from backend/: python -m unittest tests.test_voice -v
"""
import os
import sys
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.main import app
from app.security import create_access_token
from app.voice_agent import voice_routes

# Import the core voice routes test suite
from tests.voice_agent.test_voice_routes import TestVoiceRoutes


class TestVoiceAgentExtended(unittest.TestCase):
    def setUp(self):
        env_patch = patch.dict(os.environ, {"SARVAM_API_KEY": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = TestClient(app)
        voice_routes._rate_windows.clear()
        voice_routes._voice_sessions.clear()
        self.farmer_token = create_access_token({"phone": "1111111111", "name": "Farmer One", "role": "farmer"})
        self.headers = {"Authorization": f"Bearer {self.farmer_token}"}

    def test_audio_too_long_returns_413(self):
        max_bytes = voice_routes._env_int("VOICE_MAX_AUDIO_SECONDS", 30) * 64_000
        oversized_audio = b"0" * (max_bytes + 10)
        res = self.client.post(
            "/api/v1/voice/query",
            files={"file": ("voice.webm", oversized_audio, "audio/webm")},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 413)
        self.assertIn("too long", res.text.lower())

    def test_rate_limit_exceeded_returns_429(self):
        limit = voice_routes._env_int("VOICE_RATE_LIMIT_PER_MINUTE", 10)
        # Consume the allowed calls up to limit
        for _ in range(limit):
            voice_routes._rate_limit({"phone": "1111111111"})

        with self.assertRaises(HTTPException) as exc_info:
            voice_routes._rate_limit({"phone": "1111111111"})
        self.assertEqual(exc_info.exception.status_code, 429)
        self.assertIn("rate limit exceeded", exc_info.exception.detail.lower())

    def test_language_code_normalization(self):
        # Allowed language codes pass through
        self.assertEqual(voice_routes._language_code("te-IN"), "te-IN")
        self.assertEqual(voice_routes._language_code("hi-IN"), "hi-IN")
        self.assertEqual(voice_routes._language_code("en-IN"), "en-IN")

        # Unknown or None defaults safely to configured default (default te-IN)
        default_lang = os.getenv("SARVAM_DEFAULT_LANGUAGE", "te-IN")
        self.assertEqual(voice_routes._language_code("fr"), default_lang)
        self.assertEqual(voice_routes._language_code(None), default_lang)
        self.assertEqual(voice_routes._language_code(""), default_lang)

    def test_session_lifecycle_and_continuity(self):
        sid = voice_routes._voice_session({"phone": "1111111111"}, session_id=None)
        self.assertTrue(bool(sid))

        # Re-using the valid session preserves it
        sid2 = voice_routes._voice_session({"phone": "1111111111"}, session_id=sid)
        self.assertEqual(sid, sid2)

        # Another phone cannot reuse or hijack the first user's session (raises 403)
        with self.assertRaises(HTTPException) as ctx:
            voice_routes._voice_session({"phone": "2222222222"}, session_id=sid)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("invalid or expired", ctx.exception.detail.lower())

    def test_disallowed_actions_fail_safely(self):
        with self.assertRaises(HTTPException) as ctx:
            voice_routes._safe_action("DROP_TABLE", {"name": "farms"})
        self.assertEqual(ctx.exception.status_code, 400)

    def test_intent_routing_balance_check(self):
        """Verify balance check intent routes to get_my_earnings across EN, TE, HI."""
        queries = [
            "balance check",
            "check balance",
            "what is my balance",
            "wallet balance",
            "నా బ్యాలెన్స్ ఎంత?",
            "బ్యాలెన్స్ చెక్ చేయండి",
            "ఖాతా నిల్వ",
            "बैलेंस चेक करें",
            "खाता बैलेंस क्या है?",
            "बकाया राशि",
            "शेष राशि",
        ]
        for q in queries:
            tool, _ = voice_routes._fallback_tool_for_text(q)
            self.assertEqual(tool, "get_my_earnings", f"Query '{q}' failed to route to get_my_earnings")

    def test_intent_routing_farm_status(self):
        """Verify farm status intent routes to get_my_plots across EN, TE, HI."""
        queries = [
            "farm status",
            "what is my farm status",
            "plot status",
            "my farms",
            "my plots summary",
            "నా పొలం స్థితి ఏమిటి?",
            "పొలాలు వివరాలు",
            "నా చేను ఎలా ఉంది?",
            "ఖేత్ కి స్థితి క్యా హై?",
            "खेत की स्थिति क्या है?",
            "फार्म स्टेटस दिखाएं",
            "मेरे खेत",
            "प्लॉट विवरण",
        ]
        for q in queries:
            tool, _ = voice_routes._fallback_tool_for_text(q)
            self.assertEqual(tool, "get_my_plots", f"Query '{q}' failed to route to get_my_plots")

    def test_intent_routing_market_prices(self):
        """Verify market prices intent routes to navigate_to marketplace across EN, TE, HI."""
        queries = [
            "what is market price",
            "market prices for carbon credits",
            "current credit price",
            "selling price on marketplace",
            "మార్కెట్ ధరలు ఎంత?",
            "కార్బన్ క్రెడిట్ ధర",
            "మార్కెట్ రేటు",
            "మార్కెట్",
            "मार्केट भाव क्या है?",
            "कार्बन क्रेडिट का बाजार भाव",
            "क्रेडिट की कीमत",
            "मार्केट रेट",
        ]
        for q in queries:
            tool, args = voice_routes._fallback_tool_for_text(q)
            self.assertEqual(tool, "navigate_to", f"Query '{q}' failed to route to navigate_to")
            self.assertEqual(args.get("target"), "marketplace", f"Query '{q}' target should be marketplace")

    def test_intent_routing_help(self):
        """Verify help intent routes to navigate_to support across EN, TE, HI."""
        queries = [
            "help",
            "need assistance",
            "customer support",
            "how can you help me",
            "నాకు సహాయం కావాలి",
            "మద్దతు కేంద్రం",
            "హెల్ప్",
            "సపోర్ట్",
            "मुझे मदद चाहिए",
            "कस्टमर सहायता",
            "सपोर्ट",
            "हेल्प",
        ]
        for q in queries:
            tool, args = voice_routes._fallback_tool_for_text(q)
            self.assertEqual(tool, "navigate_to", f"Query '{q}' failed to route to navigate_to")
            self.assertEqual(args.get("target"), "support", f"Query '{q}' target should be support")

    def test_multilingual_prompt_formatting_and_templates(self):
        """Verify prompt templates and formatters produce correct localized responses in TE, HI, EN."""
        from app.voice_agent.prompt_templates import (
            ENGLISH_INSTRUCTIONS,
            HINDI_INSTRUCTIONS,
            SYSTEM_PROMPT,
            TELUGU_INSTRUCTIONS,
            format_tool_response,
            get_generic_fallback,
            get_unclear_audio_fallback,
        )

        # Instructions content sanity
        self.assertIn("CarbonX", SYSTEM_PROMPT)
        self.assertIn("రైతు", TELUGU_INSTRUCTIONS)
        self.assertIn("किसान", HINDI_INSTRUCTIONS)
        self.assertIn("farmer", ENGLISH_INSTRUCTIONS.lower())

        # navigate_to marketplace
        mkt_result = {"actions": [{"type": "NAVIGATE", "payload": {"path": "/marketplace"}}], "target": "marketplace"}
        mkt_te = format_tool_response("navigate_to", mkt_result, "te-IN")
        self.assertIn("మార్కెట్‌ప్లేస్", mkt_te)
        self.assertIn("₹400", mkt_te)

        mkt_hi = format_tool_response("navigate_to", mkt_result, "hi-IN")
        self.assertIn("मार्केटप्लेस", mkt_hi)
        self.assertIn("₹400", mkt_hi)

        mkt_en = format_tool_response("navigate_to", mkt_result, "en-IN")
        self.assertIn("marketplace", mkt_en.lower())
        self.assertIn("₹400", mkt_en)

        # navigate_to support (help)
        supp_result = {"actions": [{"type": "NAVIGATE", "payload": {"path": "/support"}}], "target": "support"}
        supp_te = format_tool_response("navigate_to", supp_result, "te-IN")
        self.assertIn("సహాయం", supp_te)

        supp_hi = format_tool_response("navigate_to", supp_result, "hi-IN")
        self.assertIn("सहायता", supp_hi)

        supp_en = format_tool_response("navigate_to", supp_result, "en-IN")
        self.assertIn("support", supp_en.lower())

        # Fallbacks
        self.assertIn("సురక్షిత", get_generic_fallback("te-IN"))
        self.assertIn("सुरक्षित", get_generic_fallback("hi-IN"))
        self.assertIn("safely", get_generic_fallback("en-IN"))

        self.assertIn("స్పష్టంగా", get_unclear_audio_fallback("te-IN"))
        self.assertIn("स्पष्ट", get_unclear_audio_fallback("hi-IN"))
        self.assertIn("clearly", get_unclear_audio_fallback("en-IN"))

    def test_graceful_degradation_when_sarvam_not_configured(self):
        """Honest degradation: without SARVAM_API_KEY, queries succeed via local intent & rule engine."""
        with patch.dict(os.environ, {"SARVAM_API_KEY": ""}):
            # Text query for balance check
            res_balance = self.client.post(
                "/api/v1/voice/text-query",
                json={"text": "balance check", "language_code": "te-IN"},
                headers=self.headers,
            )
            self.assertEqual(res_balance.status_code, 200)
            data_balance = res_balance.json()
            self.assertTrue(data_balance["success"])
            self.assertIsNone(data_balance["audio_base64"])
            self.assertEqual(data_balance["language_code"], "te-IN")
            self.assertIn("ఆదాయం", data_balance["response_text"])

            # Text query for market prices
            res_mkt = self.client.post(
                "/api/v1/voice/text-query",
                json={"text": "market prices", "language_code": "en-IN"},
                headers=self.headers,
            )
            self.assertEqual(res_mkt.status_code, 200)
            data_mkt = res_mkt.json()
            self.assertTrue(data_mkt["success"])
            self.assertIn("marketplace", data_mkt["response_text"].lower())
            self.assertTrue(any(a.get("type") == "NAVIGATE" and a.get("payload", {}).get("path") == "/marketplace" for a in data_mkt["actions"]))

            # Text query for help
            res_help = self.client.post(
                "/api/v1/voice/text-query",
                json={"text": "help me", "language_code": "hi-IN"},
                headers=self.headers,
            )
            self.assertEqual(res_help.status_code, 200)
            data_help = res_help.json()
            self.assertTrue(data_help["success"])
            self.assertIn("सहायता", data_help["response_text"])
            self.assertTrue(any(a.get("type") == "NAVIGATE" and a.get("payload", {}).get("path") == "/support" for a in data_help["actions"]))


if __name__ == "__main__":
    unittest.main()
