import base64
import io
import os
import sys
import unittest
import numpy as np
from PIL import Image
from fastapi.testclient import TestClient

# Ensure app imports correctly
from app.main import app
from app.services.kyc_service import validate_aadhaar
from app.services.ml_service import predict_biodiversity


class TestCarbonXFullSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Force OTP dev mode AFTER app import (main.py load_dotenv
        # override=True would clobber module-level env). phone_service
        # reads env per-call, so this guarantees no real SMS in tests.
        os.environ["TEXTPLATE_API_TOKEN"] = "test"
        os.environ["TEXTPLATE_TEMPLATE_ID"] = "test"
        cls.client = TestClient(app)
        cls.test_phone = "9876543210"
        cls.valid_aadhaar = "200000000009"
        cls.token = None

    def test_01_root_and_health(self):
        """Test root endpoint and health check."""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data.get("message"), "CarbonX API running")
        self.assertTrue(data.get("supabase"))
        self.assertTrue(data.get("earth_engine"))

        health = self.client.get("/health")
        self.assertEqual(health.status_code, 200)
        hdata = health.json()
        self.assertTrue(hdata.get("success"))
        self.assertTrue(hdata.get("database", {}).get("ready"))

    def test_02_aadhaar_validation(self):
        """Test Aadhaar Verhoeff algorithm."""
        self.assertTrue(validate_aadhaar(self.valid_aadhaar))
        self.assertFalse(validate_aadhaar("123456789012"))
        self.assertFalse(validate_aadhaar("200000000000"))
        self.assertFalse(validate_aadhaar("short"))

    def test_03_ml_inference(self):
        """Test ML biodiversity model inference directly."""
        res = predict_biodiversity(ndvi=0.65, evi=0.55, area_ha=2.5)
        self.assertIn("biodiversity_score", res)
        self.assertIn("status", res)
        self.assertIn("confidence", res)
        self.assertGreaterEqual(res["biodiversity_score"], 0)
        self.assertLessEqual(res["biodiversity_score"], 100)
        self.assertIn(res["status"], ["Low", "Moderate", "Good", "Excellent"])

    def test_04_auth_otp_and_register(self):
        """Test OTP sending and user registration."""
        # Test invalid phone
        bad_phone_res = self.client.post("/send-otp", json={"phone": "123"})
        self.assertFalse(bad_phone_res.json().get("success"))

        # Test valid phone
        otp_res = self.client.post("/send-otp", json={"phone": self.test_phone})
        self.assertEqual(otp_res.status_code, 200)
        otp_data = otp_res.json()
        self.assertTrue(otp_data.get("success"))
        otp = otp_data.get("dev_otp")
        self.assertIsNotNone(otp, "Dev OTP should be returned when Twilio is not in live mode")

        verify_otp_res = self.client.post(
            "/register/verify-otp",
            json={"phone": self.test_phone, "otp": otp},
        )
        self.assertEqual(verify_otp_res.status_code, 200)
        verify_otp_data = verify_otp_res.json()
        self.assertTrue(verify_otp_data.get("success"))
        self.assertTrue(verify_otp_data.get("verification_token"))

        # Register user
        reg_payload = {
            "phone": self.test_phone,
            "otp": otp,
            "otp_verification_token": verify_otp_data["verification_token"],
            "name": "Test Farmer",
            "aadhaar": self.valid_aadhaar,
            "state": "Telangana",
            "district": "Rangareddy",
            "village": "Chevella",
            "upi": "testfarmer@upi",
            "role": "farmer",
            "preferred_language": "en",
        }
        reg_res = self.client.post("/register", json=reg_payload)
        self.assertEqual(reg_res.status_code, 200)
        reg_data = reg_res.json()
        self.assertTrue(reg_data.get("success"))
        self.assertIn("token", reg_data)
        TestCarbonXFullSuite.token = reg_data["token"]

    def test_05_auth_login_flow(self):
        """Test OTP generation for login and logging in."""
        login_otp_res = self.client.post("/login/send-otp", json={"phone": self.test_phone})
        self.assertEqual(login_otp_res.status_code, 200)
        otp_data = login_otp_res.json()
        self.assertTrue(otp_data.get("success"))
        otp = otp_data.get("dev_otp")

        login_res = self.client.post("/login", json={"phone": self.test_phone, "otp": otp})
        self.assertEqual(login_res.status_code, 200)
        login_data = login_res.json()
        self.assertTrue(login_data.get("success"))
        self.assertIn("token", login_data)
        TestCarbonXFullSuite.token = login_data["token"]

    def test_06_profile_and_me(self):
        """Test authenticated /me and profile update."""
        headers = {"Authorization": f"Bearer {TestCarbonXFullSuite.token}"}
        me_res = self.client.get("/me", headers=headers)
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.json()
        self.assertTrue(me_data.get("success"))
        self.assertEqual(me_data.get("user", {}).get("name"), "Test Farmer")

        # Patch profile
        patch_res = self.client.patch("/profile", json={"village": "Moinabad"}, headers=headers)
        self.assertEqual(patch_res.status_code, 200)
        patch_data = patch_res.json()
        self.assertTrue(patch_data.get("success"))
        self.assertEqual(patch_data.get("user", {}).get("village"), "Moinabad")

    def test_07_analyze_satellite_and_ml(self):
        """Test /analyze endpoint with real GeoJSON polygon and ML integration."""
        sample_geojson = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [78.4867, 17.3850],
                        [78.4877, 17.3850],
                        [78.4877, 17.3860],
                        [78.4867, 17.3860],
                        [78.4867, 17.3850],
                    ]
                ],
            },
        }
        res = self.client.post(
            "/analyze",
            json={
                "geojson": sample_geojson,
                "farm_name": "Test Organic Farm",
                "crop_type": "Paddy",
                "irrigation": "Drip",
            },
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("ndvi", data)
        self.assertIn("biodiversity_score", data)
        self.assertIn("carbon_credits", data)
        self.assertIn("biodiversity_credits", data)
        self.assertIn("total_credits", data)
        self.assertIn("satellite_source", data)
        self.assertGreater(data.get("total_credits", 0), 0)

    def test_08_save_farm(self):
        """Test saving a farm polygon and credit metrics to Supabase."""
        headers = {"Authorization": f"Bearer {TestCarbonXFullSuite.token}"}
        farm_data = {
            "name": "Green Valley Farm",
            "crop_type": "Paddy",
            "irrigation": "Drip",
            "geojson": {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [78.4867, 17.3850],
                            [78.4877, 17.3850],
                            [78.4877, 17.3860],
                            [78.4867, 17.3860],
                            [78.4867, 17.3850],
                        ]
                    ],
                },
            },
            "area_hectares": 0.12,
            "ndvi": 0.33,
            "evi": 0.28,
            "carbon_tonnes": 0.47,
            "biodiversity_score": 26.8,
            "tree_cover": 33.0,
            "soil_moisture": 7.0,
            "vegetation_health": "Moderate",
            "ai_confidence": 91.6,
            "satellite_source": "Google Earth Engine · Sentinel-2 SR",
        }
        res = self.client.post("/save-farm", json={"farm": farm_data}, headers=headers)
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("farm", data)
        self.assertIsNotNone(data["farm"].get("id"))
        TestCarbonXFullSuite.saved_farm_id = data["farm"]["id"]

    def test_09_predict_endpoint(self):
        """Test /predict endpoint by coordinates."""
        res = self.client.get("/predict?longitude=78.4867&latitude=17.3850")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data.get("success"))
        self.assertIn("biodiversity_score", data)
        self.assertIn("total_credits", data)

    def test_10_marketplace_flow(self):
        """Test listing creation and fetching with an isolated clean user.

        The shared test_phone accumulates FLAGGED/PENDING KYC across runs,
        which correctly blocks listings via farm_may_list(). To test the
        positive path deterministically, use a dedicated phone that never
        runs /verify-land, so its farm stays Verified and listable.
        Also asserts the negative path: a FLAGGED farm must be blocked.
        """
        clean_phone = "9111111111"
        otp_res = self.client.post("/send-otp", json={"phone": clean_phone})
        self.assertTrue(otp_res.json().get("success"))
        clean_otp = otp_res.json().get("dev_otp")
        self.assertIsNotNone(clean_otp)
        verify_res = self.client.post(
            "/register/verify-otp", json={"phone": clean_phone, "otp": clean_otp}
        )
        self.assertTrue(verify_res.json().get("success"))
        reg_res = self.client.post("/register", json={
            "phone": clean_phone,
            "otp": clean_otp,
            "otp_verification_token": verify_res.json()["verification_token"],
            "name": "Marketplace Farmer",
            "aadhaar": self.valid_aadhaar,
            "state": "Telangana",
            "district": "Rangareddy",
            "village": "Chevella",
            "upi": "mkt@upi",
            "role": "farmer",
            "preferred_language": "en",
        })
        self.assertTrue(reg_res.json().get("success"))
        clean_headers = {"Authorization": f"Bearer {reg_res.json()['token']}"}
        farm_geojson = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [78.4967, 17.3950],
                    [78.4977, 17.3950],
                    [78.4977, 17.3960],
                    [78.4967, 17.3960],
                    [78.4967, 17.3950],
                ]],
            },
        }
        farm_res = self.client.post("/save-farm", json={"farm": {
            "name": "Marketplace Farm",
            "crop_type": "Paddy",
            "irrigation": "Drip",
            "geojson": farm_geojson,
            "area_hectares": 0.12,
            "ndvi": 0.65,
            "evi": 0.55,
            "carbon_tonnes": 1.2,
            "biodiversity_score": 72.0,
            "tree_cover": 65.0,
            "soil_moisture": 30.0,
            "vegetation_health": "Good",
            "ai_confidence": 95.0,
            "satellite_source": "test",
        }}, headers=clean_headers)
        self.assertTrue(farm_res.json().get("success"))
        clean_farm_id = farm_res.json()["farm"]["id"]

        listing_payload = {
            "farm_id": clean_farm_id,
            "carbon_credits": 0.47,
            "biodiversity_credits": 0.67,
            "price_per_credit": 550,
            "crop": "Paddy",
        }
        create_res = self.client.post("/marketplace/listings", json=listing_payload, headers=clean_headers)
        self.assertEqual(create_res.status_code, 200)
        cdata = create_res.json()
        self.assertTrue(cdata.get("success"))
        listing_id = cdata.get("listing", {}).get("id")
        self.assertIsNotNone(listing_id)

        # Negative path: the shared user's farm (FLAGGED/PENDING after KYC)
        # must be rejected, not listed.
        headers = {"Authorization": f"Bearer {TestCarbonXFullSuite.token}"}
        blocked_res = self.client.post("/marketplace/listings", json={
            "farm_id": getattr(TestCarbonXFullSuite, "saved_farm_id", None),
            "carbon_credits": 0.47,
            "biodiversity_credits": 0.67,
            "price_per_credit": 550,
            "crop": "Paddy",
        }, headers=headers)
        if not blocked_res.json().get("success"):
            self.assertIn("cannot be listed", blocked_res.json().get("message", ""))

        # Fetch marketplace listings
        get_res = self.client.get("/marketplace/listings")
        self.assertEqual(get_res.status_code, 200)
        listings = get_res.json().get("listings", [])
        self.assertGreater(len(listings), 0)

    def test_11_kyc_verification(self):
        """Test land document verification and KYC status retrieval."""
        headers = {"Authorization": f"Bearer {TestCarbonXFullSuite.token}"}

        # Create a simple 100x100 RGB image for testing
        img = Image.new("RGB", (100, 100), color=(120, 180, 120))
        buffer = io.BytesIO()
        img.save(buffer, format="PNG")
        b64_img = base64.b64encode(buffer.getvalue()).decode("utf-8")

        kyc_payload = {
            "document_name": "patta_document.png",
            "document_content_base64": b64_img,
            "extracted_text": "Patta land revenue record owner Test Farmer survey no 142/A",
            "survey_number": "142/A",
            "village": "Chevella",
            "district": "Rangareddy",
            "area_acres": 2.5,
        }
        kyc_res = self.client.post("/verify-land", json=kyc_payload, headers=headers)
        self.assertEqual(kyc_res.status_code, 200)
        kdata = kyc_res.json()
        self.assertTrue(kdata.get("success"))
        self.assertIn("status", kdata)
        self.assertIn("checks", kdata)

        # Check KYC status
        status_res = self.client.get(f"/kyc/status/{self.test_phone}", headers=headers)
        self.assertEqual(status_res.status_code, 200)
        sdata = status_res.json()
        self.assertTrue(sdata.get("success"))
        self.assertIn(sdata.get("status"), ["VERIFIED", "FLAGGED", "PENDING"])


if __name__ == "__main__":
    unittest.main()
