"""Comprehensive unit tests for security.py and supabase_db.py hardening."""
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
from fastapi import HTTPException

from app import security
from app import supabase_db as db


class SecurityHardeningTests(unittest.TestCase):
    def test_create_and_decode_token_with_iat(self):
        payload = {"phone": "9999999999", "role": "farmer"}
        token = security.create_access_token(payload, expires_delta=timedelta(hours=1))
        self.assertIsInstance(token, str)

        decoded = security.decode_token(token)
        self.assertIsNotNone(decoded)
        self.assertEqual(decoded["phone"], "9999999999")
        self.assertEqual(decoded["role"], "farmer")
        self.assertIn("iat", decoded)
        self.assertIn("exp", decoded)

    def test_decode_token_invalid_inputs(self):
        self.assertIsNone(security.decode_token(None))
        self.assertIsNone(security.decode_token(""))
        self.assertIsNone(security.decode_token("not-a-valid-jwt-token"))
        self.assertIsNone(security.decode_token("header.payload"))

    def test_get_current_user_bearer_parsing(self):
        token = security.create_access_token({"phone": "9999999999", "role": "farmer"})

        # Standard header
        user = security.get_current_user(f"Bearer {token}")
        self.assertEqual(user["phone"], "9999999999")

        # Lowercase bearer
        user_lower = security.get_current_user(f"bearer {token}")
        self.assertEqual(user_lower["phone"], "9999999999")

        # Multiple spaces
        user_spaces = security.get_current_user(f"Bearer   {token}")
        self.assertEqual(user_spaces["phone"], "9999999999")

    def test_get_current_user_unauthenticated(self):
        with self.assertRaises(HTTPException) as ctx:
            security.get_current_user(None)
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Not authenticated")

        with self.assertRaises(HTTPException) as ctx:
            security.get_current_user("Basic abc123xyz")
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Not authenticated")

        with self.assertRaises(HTTPException) as ctx:
            security.get_current_user("Bearer ")
        self.assertEqual(ctx.exception.status_code, 401)

        with self.assertRaises(HTTPException) as ctx:
            security.get_current_user("Bearer invalid.token.payload")
        self.assertEqual(ctx.exception.status_code, 401)
        self.assertEqual(ctx.exception.detail, "Invalid token")

    def test_get_current_user_optional(self):
        token = security.create_access_token({"phone": "9999999999", "role": "buyer"})

        self.assertIsNone(security.get_current_user_optional(None))
        self.assertIsNone(security.get_current_user_optional(""))
        self.assertIsNone(security.get_current_user_optional("Basic xyz"))
        self.assertIsNone(security.get_current_user_optional("Bearer bad-token"))

        user = security.get_current_user_optional(f"Bearer {token}")
        self.assertIsNotNone(user)
        self.assertEqual(user["phone"], "9999999999")

        user_lower = security.get_current_user_optional(f"bearer {token}")
        self.assertIsNotNone(user_lower)
        self.assertEqual(user_lower["role"], "buyer")

    def test_require_role(self):
        checker = security.require_role("farmer", "fpo")

        # Matching role
        user = checker({"phone": "111", "role": "farmer"})
        self.assertEqual(user["role"], "farmer")

        # Mixed casing
        user_caps = checker({"phone": "111", "role": "Farmer"})
        self.assertEqual(user_caps["role"], "Farmer")

        # Forbidden role
        with self.assertRaises(HTTPException) as ctx:
            checker({"phone": "111", "role": "buyer"})
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("Access denied", ctx.exception.detail)

    def test_password_hashing_and_verification(self):
        hashed = security.hash_password("SuperSecret123!")
        self.assertIsInstance(hashed, str)
        self.assertTrue(security.verify_password("SuperSecret123!", hashed))
        self.assertFalse(security.verify_password("WrongPassword", hashed))

        # None / empty checks should never raise or evaluate "None" as matching
        self.assertFalse(security.verify_password(None, hashed))
        self.assertFalse(security.verify_password("", hashed))
        self.assertFalse(security.verify_password("SuperSecret123!", None))
        self.assertFalse(security.verify_password("SuperSecret123!", ""))
        self.assertFalse(security.verify_password(None, None))

        with self.assertRaises(ValueError):
            security.hash_password("")


class SupabaseDbHardeningTests(unittest.TestCase):
    def test_verify_otp_naive_and_aware_datetime(self):
        mock_sb = MagicMock()
        future_iso_naive = (datetime.now() + timedelta(minutes=5)).isoformat()

        # Mock select returning naive datetime
        mock_select = MagicMock()
        mock_select.select.return_value.eq.return_value.limit.return_value.execute.return_value.data = [
            {"phone": "9999999999", "otp": "123456", "expires_at": future_iso_naive}
        ]
        mock_sb.table.return_value = mock_select

        with patch.object(db, "_client", return_value=mock_sb):
            # Naive timestamp should not raise TypeError
            result = db.verify_otp_db("9999999999", "123456")
            self.assertTrue(result)

    def test_get_land_registry_none_survey_number(self):
        self.assertIsNone(db.get_land_registry(None))
        self.assertIsNone(db.get_land_registry(""))

    def test_mutations_do_not_modify_caller_dict(self):
        original_profile = {"phone": "9000000000", "name": "Farmer Test"}
        mock_sb = MagicMock()
        with patch.object(db, "_client", return_value=mock_sb):
            db.upsert_profile(original_profile)
            self.assertNotIn("updated_at", original_profile)

        original_fields = {"crop_type": "Wheat"}
        with patch.object(db, "_client", return_value=mock_sb):
            db.update_farm("farm-123", original_fields)
            self.assertNotIn("updated_at", original_fields)

    def test_get_listings_filtered_clamping_and_search_sanitization(self):
        mock_sb = MagicMock()
        mock_q = MagicMock()
        mock_sb.table.return_value.select.return_value = mock_q
        mock_q.eq.return_value = mock_q
        mock_q.ilike.return_value = mock_q
        mock_q.or_.return_value = mock_q
        mock_q.gte.return_value = mock_q
        mock_q.lte.return_value = mock_q
        mock_q.order.return_value.range.return_value.execute.return_value.count = 0
        mock_q.order.return_value.range.return_value.execute.return_value.data = []

        with patch.object(db, "_client", return_value=mock_sb):
            # Negative offset should be clamped to 0
            res = db.get_listings_filtered(offset=-10, limit=20, search="Dr. Reddy (Paddy)")
            self.assertEqual(res["total"], 0)
            self.assertEqual(res["listings"], [])

            # Check that search sanitized dots/parentheses
            or_call_args = mock_q.or_.call_args[0][0]
            self.assertNotIn("(", or_call_args)
            self.assertNotIn(")", or_call_args)
            self.assertNotIn("Dr.", or_call_args)
            self.assertIn("*Dr  Reddy  Paddy*", or_call_args)

    def test_exception_handling_in_query_helpers(self):
        mock_sb = MagicMock()
        mock_sb.table.side_effect = RuntimeError("PostgREST connection reset")

        with patch.object(db, "_client", return_value=mock_sb):
            self.assertIsNone(db.get_profile("123"))
            self.assertFalse(db.upsert_profile({"phone": "123"}))
            self.assertIsNone(db.update_profile("123", {"name": "Test"}))
            self.assertEqual(db.get_document_hashes(), [])
            self.assertIsNone(db.insert_kyc_verification({"doc": "123"}))
            self.assertIsNone(db.get_kyc_status("123"))
            self.assertFalse(db.store_otp("123", "000000", datetime.now(timezone.utc)))
            self.assertFalse(db.verify_otp_db("123", "000000"))
            self.assertFalse(db.clear_otp("123"))
            self.assertEqual(db.get_farms("123"), [])
            self.assertIsNone(db.insert_farm({"name": "Test Farm"}))
            self.assertIsNone(db.update_farm("f1", {"name": "Test Farm"}))
            self.assertEqual(db.get_listings(), [])
            self.assertEqual(db.get_listings_filtered(), {"total": 0, "listings": []})
            self.assertIsNone(db.insert_listing({"credits": 10}))
            self.assertIsNone(db.get_farm("f1"))
            self.assertEqual(db.list_farms_by_status("Active"), [])
            self.assertEqual(db.list_profiles_by_fpo("fpo-1"), [])
            self.assertEqual(db.farm_geojsons_except("123"), [])


if __name__ == "__main__":
    unittest.main()
