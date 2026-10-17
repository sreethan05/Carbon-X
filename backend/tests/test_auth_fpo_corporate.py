import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

os.environ["CARBONX_ALLOW_DEV_OTP"] = "1"

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402
from app import supabase_db as _db  # noqa: E402
from app.security import create_access_token  # noqa: E402

client = TestClient(app)


class AuthRouterTests(unittest.TestCase):
    def test_send_otp_normalizes_phone(self):
        # 10 digits
        r1 = client.post("/send-otp", json={"phone": "9876500001"})
        self.assertTrue(r1.json().get("success"), r1.json())
        self.assertIn("dev_otp", r1.json())

        # With +91 and spaces
        r2 = client.post("/send-otp", json={"phone": "+91 98765 00002"})
        self.assertTrue(r2.json().get("success"), r2.json())

        # With leading 0 and hyphens
        r3 = client.post("/send-otp", json={"phone": "098765-00003"})
        self.assertTrue(r3.json().get("success"), r3.json())

        # Invalid short phone
        r4 = client.post("/send-otp", json={"phone": "12345"})
        self.assertFalse(r4.json().get("success"))
        self.assertIn("10-digit", r4.json().get("message", ""))

    def test_send_otp_extra_fields_forbidden(self):
        r = client.post("/send-otp", json={"phone": "9876500004", "hack": "forbidden"})
        self.assertEqual(r.status_code, 422)

    def test_registration_otp_verify_and_flow(self):
        otp_res = client.post("/send-otp", json={"phone": "9876500005"}).json()
        otp = otp_res.get("dev_otp")

        # Verify OTP step 1
        verify_res = client.post("/register/verify-otp", json={"phone": "+91 9876500005", "otp": otp}).json()
        self.assertTrue(verify_res.get("success"), verify_res)
        token = verify_res.get("verification_token")
        self.assertTrue(token)

        # Extra fields forbidden on verify-otp
        bad_verify = client.post("/register/verify-otp", json={"phone": "9876500005", "otp": otp, "extra": "data"})
        self.assertEqual(bad_verify.status_code, 422)

    def test_demo_login_endpoint(self):
        with patch.object(_db, "is_ready", return_value=False):
            r = client.post("/demo/login", json={"phone": "9000000001"})
            self.assertEqual(r.status_code, 200)
            data = r.json()
            self.assertTrue(data.get("success"), data)
            self.assertTrue(data.get("demo_mode"))
            self.assertTrue(data.get("token"))
            self.assertEqual(data.get("user", {}).get("phone"), "9000000001")

            # Demo login with extra fields forbidden
            r_extra = client.post("/demo/login", json={"phone": "9000000001", "unwanted": "field"})
            self.assertEqual(r_extra.status_code, 422)

    def test_get_me_corporate_buyer(self):
        token = create_access_token({"c_id": 42, "name": "Global Green Corp", "role": "buyer"})
        res = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("user", {}).get("name"), "Global Green Corp")
        self.assertEqual(data.get("user", {}).get("role"), "buyer")
        self.assertEqual(data.get("user", {}).get("c_id"), 42)

    def test_get_me_demo_session(self):
        token = create_access_token({"phone": "9000000001", "name": "Venkat Rao", "role": "farmer", "demo": True})
        res = client.get("/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertEqual(data.get("user", {}).get("phone"), "9000000001")
        self.assertTrue(data.get("user", {}).get("demo"))

    def test_update_profile_extra_fields_forbidden(self):
        token = create_access_token({"phone": "9000000001", "name": "Venkat Rao", "role": "farmer"})
        res = client.patch(
            "/profile",
            json={"village": "Bonakal", "role": "admin"},  # role is forbidden as extra field
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(res.status_code, 422)

    def test_fpo_login_endpoint_in_auth_router(self):
        with patch.object(_db, "_client", return_value=None):
            # Demo mode FPO lookup
            res = client.post("/fpo/login", json={"registration_no": "FPO-TG-001"})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("success"), data)
            self.assertIn("Khammam Farmer Producer Org", data.get("fpo_name", ""))
            self.assertTrue(data.get("officer_phone_masked"))

            # Accepts legacy password field without breaking
            res_legacy = client.post("/fpo/login", json={"registration_no": "FPO-TG-001", "password": "any"})
            self.assertTrue(res_legacy.json().get("success"))


class CorporateRouterTests(unittest.TestCase):
    def test_corporate_login_demo_fallback(self):
        with patch.object(_db, "_client", return_value=None):
            res = client.post(
                "/corporate/login",
                json={"name": "Telangana Sustainable Agro Pvt Ltd", "password": "Corporate@2026"},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data.get("success"), data)
            self.assertTrue(data.get("token"))
            self.assertEqual(data.get("user", {}).get("role"), "buyer")
            self.assertEqual(data.get("user", {}).get("name"), "Telangana Sustainable Agro Pvt Ltd")

    def test_corporate_login_invalid_credentials(self):
        with patch.object(_db, "_client", return_value=None):
            res = client.post(
                "/corporate/login",
                json={"name": "Telangana Sustainable Agro Pvt Ltd", "password": "WrongPassword"},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertFalse(data.get("success"))

    def test_corporate_login_extra_fields_forbidden(self):
        res = client.post(
            "/corporate/login",
            json={"name": "Telangana Sustainable Agro Pvt Ltd", "password": "Corporate@2026", "inject": "data"},
        )
        self.assertEqual(res.status_code, 422)


class FpoRouterTests(unittest.TestCase):
    def test_fpo_routes_require_privileged_role(self):
        farmer_token = create_access_token({"phone": "9876543210", "role": "farmer"})
        res = client.get("/fpo/farmers", headers={"Authorization": f"Bearer {farmer_token}"})
        self.assertEqual(res.status_code, 403)

        fpo_token = create_access_token({"phone": "9000000001", "role": "fpo"})
        with patch.object(_db, "is_ready", return_value=False):
            # Without DB, returns 503 instead of 403 Forbidden
            res_fpo = client.get("/fpo/farmers", headers={"Authorization": f"Bearer {fpo_token}"})
            self.assertEqual(res_fpo.status_code, 503)

    def test_fpo_pending_unlinked_officer(self):
        fpo_token = create_access_token({"phone": "9000000001", "role": "fpo"})
        with patch.object(_db, "_client", return_value=None):
            res = client.get("/fpo/pending", headers={"Authorization": f"Bearer {fpo_token}"})
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertFalse(data.get("success"))
            self.assertIn("Database", data.get("message", ""))

    def test_fpo_onboard_validation(self):
        fpo_token = create_access_token({"phone": "9000000001", "role": "fpo"})
        # Extra fields forbidden on onboarding model
        res = client.post(
            "/fpo/onboard",
            json={
                "name": "Ramu", "phone": "9876543210", "survey_number": "100/A",
                "acreage": 2.5, "mandal": "Khammam", "village": "Bonakal",
                "extra": "attack",
            },
            headers={"Authorization": f"Bearer {fpo_token}"},
        )
        self.assertEqual(res.status_code, 422)

    def test_fpo_review_action_validation(self):
        fpo_token = create_access_token({"phone": "9000000001", "role": "fpo"})
        res = client.post(
            "/fpo/review/farm_123",
            json={"action": "invalid_action", "notes": "test"},
            headers={"Authorization": f"Bearer {fpo_token}"},
        )
        # Farm not found (404) or bad request (400)
        self.assertIn(res.status_code, [400, 404, 503])


if __name__ == "__main__":
    unittest.main()
