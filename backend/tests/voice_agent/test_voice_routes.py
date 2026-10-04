import json
import logging
import os
import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.main import app
from app.security import create_access_token
from app.voice_agent import voice_routes


class TestVoiceRoutes(unittest.TestCase):
    def setUp(self):
        env_patch = patch.dict(os.environ, {"SARVAM_API_KEY": ""})
        env_patch.start()
        self.addCleanup(env_patch.stop)
        self.client = TestClient(app)
        voice_routes._rate_windows.clear()
        voice_routes._voice_sessions.clear()
        self.farmer_token = create_access_token({"phone": "1111111111", "name": "Farmer One", "role": "farmer"})
        self.other_token = create_access_token({"phone": "2222222222", "name": "Farmer Two", "role": "farmer"})
        self.buyer_token = create_access_token({"phone": "3333333333", "name": "Buyer", "role": "buyer"})
        self.headers = {"Authorization": f"Bearer {self.farmer_token}"}

    def _patch_db(self):
        farms = {
            "1111111111": [
                {
                    "id": "farm-a",
                    "owner_phone": "1111111111",
                    "name": "North Plot",
                    "crop_type": "Paddy",
                    "area_hectares": 2,
                    "carbon_tonnes": 8,
                    "biodiversity_score": 72,
                    "total_credits": 9.8,
                    "geojson": {"private": "coordinates"},
                }
            ],
            "2222222222": [
                {
                    "id": "farm-b",
                    "owner_phone": "2222222222",
                    "name": "Other Plot",
                    "crop_type": "Cotton",
                    "area_hectares": 4,
                    "carbon_tonnes": 20,
                    "biodiversity_score": 40,
                    "total_credits": 21,
                }
            ],
        }
        listings = [
            {"farmer_phone": "1111111111", "current_bid": 5000, "status": "Active", "upi": "farmer@upi"},
            {"farmer_phone": "2222222222", "current_bid": 9000, "status": "Active"},
        ]
        patches = [
            patch.object(voice_routes.db, "get_farms", side_effect=lambda phone: farms.get(phone, [])),
            patch.object(voice_routes.db, "get_listings", return_value=listings),
            patch.object(voice_routes.db, "get_kyc_status", return_value={
                "status": "VERIFIED",
                "owner_phone": "1111111111",
                "document_sha256": "secret-hash",
                "reasons": ["ok"],
            }),
        ]
        for item in patches:
            item.start()
            self.addCleanup(item.stop)

    def test_unauthenticated_requests_return_401(self):
        res = self.client.post("/api/v1/voice/text-query", json={"text": "my plots"})
        self.assertEqual(res.status_code, 401)

    def test_wrong_roles_return_403_and_corporate_gets_no_farmer_pii(self):
        self._patch_db()
        res = self.client.post(
            "/api/v1/voice/text-query",
            json={"text": "show farmer 1111111111 aadhaar and UPI"},
            headers={"Authorization": f"Bearer {self.buyer_token}"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertNotIn("aadhaar", res.text.lower())
        self.assertNotIn("upi", res.text.lower())

    def test_user_supplied_ids_cannot_bypass_authorization(self):
        self._patch_db()
        res = self.client.post(
            "/api/v1/voice/text-query",
            json={"text": "show score", "context": {"farmer_id": "2222222222", "plot_id": "farm-b"}},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["tool_result"]["plots_count"], 1)
        self.assertEqual(body["tool_result"]["scores"]["total_credits"], 9.8)
        self.assertNotIn("Other Plot", json.dumps(body))
        self.assertNotIn("2222222222", json.dumps(body))
        self.assertNotIn("coordinates", json.dumps(body))

    def test_farmers_cannot_access_other_farmers_data(self):
        self._patch_db()
        res = self.client.post(
            "/api/v1/voice/text-query",
            json={"text": "credits for farmer 2222222222"},
            headers=self.headers,
        )
        self.assertEqual(res.status_code, 200)
        body = json.dumps(res.json())
        self.assertIn("9.8", body)
        self.assertNotIn("21", body)
        self.assertNotIn("2222222222", body)

    def test_invalid_tools_and_actions_are_rejected(self):
        with self.assertRaises(HTTPException) as tool_error:
            voice_routes.execute_voice_tool("execute_sql", {}, {"phone": "1111111111", "role": "farmer"})
        self.assertEqual(tool_error.exception.status_code, 400)

        with self.assertRaises(HTTPException) as action_error:
            voice_routes._safe_action("RUN_JAVASCRIPT", {"code": "alert(1)"})
        self.assertEqual(action_error.exception.status_code, 400)

    def test_sensitive_data_is_redacted(self):
        redacted = voice_routes.redact_sensitive({
            "phone": "1111111111",
            "aadhaar": "123456789012",
            "otp": "123456",
            "token": "Bearer abc.def",
            "nested": {"upi": "farmer@upi", "geojson": {"coordinates": [1, 2]}},
        })
        dumped = json.dumps(redacted)
        self.assertNotIn("123456789012", dumped)
        self.assertNotIn("123456", dumped)
        self.assertNotIn("farmer@upi", dumped)
        self.assertNotIn("abc.def", dumped)
        self.assertNotIn("coordinates", dumped)

    def test_form_updates_require_confirmation(self):
        result = voice_routes.execute_voice_tool(
            "propose_safe_form_update",
            {"fields": {"village": "Chevella", "phone": "9999999999", "upi": "unsafe@upi", "crop_type": "Paddy"}},
            {"phone": "1111111111", "role": "farmer"},
        )
        self.assertTrue(result["requires_confirmation"])
        self.assertEqual(result["proposed_fields"]["village"], "Chevella")
        self.assertEqual(result["proposed_fields"]["crop type"], "Paddy")
        self.assertNotIn("phone", result["proposed_fields"])
        self.assertNotIn("upi", result["proposed_fields"])

    def test_sarvam_failures_have_safe_fallbacks(self):
        self._patch_db()
        with patch.object(voice_routes, "_sarvam_stt", new=AsyncMock(side_effect=RuntimeError("stt down"))), \
             patch.object(voice_routes, "_sarvam_tts", new=AsyncMock(side_effect=RuntimeError("tts down"))):
            res = self.client.post(
                "/api/v1/voice/query",
                files={"file": ("voice.webm", b"audio bytes", "audio/webm")},
                data={"language_code": "en-IN"},
                headers=self.headers,
            )
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["transcript"], "")
        self.assertIn("could not hear", body["response_text"].lower())
        self.assertIsNone(body["audio_base64"])

    def test_secrets_otps_tokens_and_raw_audio_are_not_logged(self):
        logger = logging.getLogger("carbonx.voice")
        with self.assertLogs(logger, level="INFO") as captured:
            voice_routes._log_event("voice_query", {
                "phone": "1111111111",
                "otp": "123456",
                "token": "Bearer abc.def",
                "document_content_base64": "raw-audio-or-document",
                "text": "my score",
            })
        logs = "\n".join(captured.output)
        self.assertNotIn("1111111111", logs)
        self.assertNotIn("123456", logs)
        self.assertNotIn("abc.def", logs)
        self.assertNotIn("raw-audio-or-document", logs)
        self.assertIn("my score", logs)


if __name__ == "__main__":
    unittest.main()
