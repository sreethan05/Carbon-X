"""Unit tests for the evidence capture service (ray casting, EXIF GPS,
sanitization, hashing, evidence_flags). Hermetic — no network, no live DB.

Run from backend/: python -m unittest tests.test_evidence_service -v
"""
import hashlib
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""

_EVIDENCE_TMP = tempfile.mkdtemp(prefix="carbonx_evidence_test_")
os.environ["CARBONX_EVIDENCE_DIR"] = _EVIDENCE_TMP


def setUpModule():
    # Re-assert the override at run time: discovery imports every test module
    # before running any, so another module may have replaced the env var.
    os.environ["CARBONX_EVIDENCE_DIR"] = _EVIDENCE_TMP

from PIL import Image  # noqa: E402
from PIL.TiffImagePlugin import IFDRational  # noqa: E402

from app.services import evidence_service as evidence  # noqa: E402
from app import supabase_db as _db  # noqa: E402

# post-import reset: another test module may have imported app.main, which
# load_dotenv(override=True)s backend/.env back into the environment.
for _k in ("SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
           "VITE_SUPABASE_URL", "VITE_SUPABASE_ANON_KEY"):
    os.environ.pop(_k, None)
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = ""
_db._supabase = None
_db._ready = False


def tearDownModule():
    shutil.rmtree(_EVIDENCE_TMP, ignore_errors=True)


SQUARE = {
    "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": [
        [[79.15, 17.25], [79.16, 17.25], [79.16, 17.26], [79.15, 17.26], [79.15, 17.25]]]},
}

DONUT = {
    "type": "Feature",
    "geometry": {"type": "Polygon", "coordinates": [
        [[79.0, 17.0], [79.2, 17.0], [79.2, 17.2], [79.0, 17.2], [79.0, 17.0]],
        [[79.08, 17.08], [79.12, 17.08], [79.12, 17.12], [79.08, 17.12], [79.08, 17.08]],
    ]},
}

MULTI = {
    "type": "MultiPolygon",
    "coordinates": [
        [[[79.0, 17.0], [79.01, 17.0], [79.01, 17.01], [79.0, 17.01], [79.0, 17.0]]],
        [[[80.0, 18.0], [80.01, 18.0], [80.01, 18.01], [80.0, 18.01], [80.0, 18.0]]],
    ],
}


def _dms(value):
    value = abs(value)
    degrees = int(value)
    minutes_float = (value - degrees) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60, 4)
    return (degrees, minutes, seconds)


def make_jpeg(gps=None):
    """Real JPEG bytes; ``gps`` = (lat, lon, lat_ref, lon_ref) or None."""
    image = Image.new("RGB", (16, 16), "green")
    buffer = io.BytesIO()
    if gps is not None:
        latitude, longitude, lat_ref, lon_ref = gps
        exif = Image.Exif()
        exif[34853] = {
            1: lat_ref, 2: _dms(latitude),
            3: lon_ref, 4: _dms(longitude),
        }
        image.save(buffer, format="JPEG", exif=exif)
    else:
        image.save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeExif:
    """Minimal stand-in for Pillow's Image.Exif — fabricates an IFD for tests
    only; the service itself never invents coordinates."""

    def __init__(self, gps):
        self._gps = gps

    def get_ifd(self, tag):
        return self._gps if tag == 34853 else {}


class PointInPolygonTests(unittest.TestCase):
    def test_inside_and_outside(self):
        self.assertTrue(evidence.point_in_polygon(17.255, 79.155, SQUARE))
        self.assertFalse(evidence.point_in_polygon(17.30, 79.155, SQUARE))
        self.assertFalse(evidence.point_in_polygon(17.255, 79.30, SQUARE))

    def test_boundary_point_counts_as_inside(self):
        self.assertTrue(evidence.point_in_polygon(17.25, 79.155, SQUARE))

    def test_raw_polygon_geometry_without_feature_wrapper(self):
        self.assertTrue(evidence.point_in_polygon(17.255, 79.155, SQUARE["geometry"]))

    def test_multipolygon_second_ring(self):
        self.assertTrue(evidence.point_in_polygon(17.005, 79.005, MULTI))
        self.assertTrue(evidence.point_in_polygon(18.005, 80.005, MULTI))
        self.assertFalse(evidence.point_in_polygon(17.5, 79.5, MULTI))

    def test_hole_is_excluded(self):
        self.assertTrue(evidence.point_in_polygon(17.05, 79.05, DONUT))
        self.assertFalse(evidence.point_in_polygon(17.10, 79.10, DONUT))

    def test_degenerate_and_invalid_polygons(self):
        collinear = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [2, 0], [0, 0]]]}
        self.assertFalse(evidence.point_in_polygon(0.5, 1.0, collinear))
        two_points = {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [0, 0]]]}
        self.assertFalse(evidence.point_in_polygon(0.5, 0.5, two_points))
        empty = {"type": "Polygon", "coordinates": []}
        self.assertFalse(evidence.point_in_polygon(0.5, 0.5, empty))
        point_geom = {"type": "Point", "coordinates": [79.15, 17.25]}
        self.assertFalse(evidence.point_in_polygon(17.25, 79.15, point_geom))
        self.assertFalse(evidence.point_in_polygon(17.25, 79.15, None))

    def test_geometry_collection_polygon(self):
        geom_coll = {
            "type": "GeometryCollection",
            "geometries": [
                {"type": "Point", "coordinates": [0, 0]},
                SQUARE["geometry"],
            ],
        }
        self.assertTrue(evidence.point_in_polygon(17.255, 79.155, geom_coll))
        self.assertFalse(evidence.point_in_polygon(17.30, 79.155, geom_coll))

    def test_verify_inside_boundary_non_finite_coords(self):
        inside, reason = evidence.verify_inside_boundary(float("nan"), 79.155, SQUARE)
        self.assertFalse(inside)
        self.assertIn("finite", reason.lower())
        inside, reason = evidence.verify_inside_boundary(17.255, float("inf"), SQUARE)
        self.assertFalse(inside)
        self.assertIn("finite", reason.lower())

    def test_verify_inside_boundary_reasons(self):
        inside, reason = evidence.verify_inside_boundary(17.255, 79.155, SQUARE)
        self.assertTrue(inside)
        self.assertIn("inside", reason.lower())
        outside, reason = evidence.verify_inside_boundary(17.30, 79.155, SQUARE)
        self.assertFalse(outside)
        self.assertIn("outside", reason.lower())
        verified, reason = evidence.verify_inside_boundary(17.25, 79.15, None)
        self.assertFalse(verified)
        self.assertIn("No farm boundary", reason)
        verified, reason = evidence.verify_inside_boundary(17.25, 79.15, {"type": "Point", "coordinates": [0, 0]})
        self.assertFalse(verified)
        self.assertIn("not a valid", reason)


class SanitizeFarmIdTests(unittest.TestCase):
    def test_valid_ids_pass_through(self):
        for farm_id in ("farm-a", "FARM_1", "abc123", "a-b_c-9"):
            self.assertEqual(evidence.sanitize_farm_id(farm_id), farm_id)

    def test_unsafe_ids_rejected(self):
        for farm_id in ("../etc", "a/b", "a b", "farm.1", "", "  ", None, "ünicode", "a\\b"):
            self.assertIsNone(evidence.sanitize_farm_id(farm_id), farm_id)

    def test_store_photo_file_rejects_unsafe_id(self):
        with self.assertRaises(ValueError):
            evidence.store_photo_file("../evil", b"x", "0" * 64, "jpg")

    def test_list_records_invalid_farm_id_returns_empty(self):
        self.assertEqual(evidence.list_records("../invalid/farm"), [])


class HashingAndStorageTests(unittest.TestCase):
    def test_sha256_stable_known_vector(self):
        expected = hashlib.sha256(b"carbonx").hexdigest()
        self.assertEqual(evidence.sha256_hex(b"carbonx"), expected)
        self.assertEqual(evidence.sha256_hex(b"carbonx"), evidence.sha256_hex(b"carbonx"))
        self.assertEqual(len(evidence.sha256_hex(b"")), 64)

    def test_store_photo_file_writes_content_and_uses_env_dir(self):
        data = b"evidence-bytes"
        digest = evidence.sha256_hex(data)
        path = evidence.store_photo_file("farm-store", data, digest, "jpg")
        self.assertTrue(path.startswith(_EVIDENCE_TMP))
        self.assertEqual(os.path.basename(path), f"{digest[:16]}.jpg")
        with open(path, "rb") as handle:
            self.assertEqual(handle.read(), data)


class ExifGpsTests(unittest.TestCase):
    def test_extract_exif_gps_north_east(self):
        coords = evidence.extract_exif_gps(make_jpeg((17.25, 79.155, "N", "E")))
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords["latitude"], 17.25, places=4)
        self.assertAlmostEqual(coords["longitude"], 79.155, places=4)

    def test_extract_exif_gps_south_west_is_negative(self):
        coords = evidence.extract_exif_gps(make_jpeg((17.25, 79.155, "S", "W")))
        self.assertIsNotNone(coords)
        self.assertAlmostEqual(coords["latitude"], -17.25, places=4)
        self.assertAlmostEqual(coords["longitude"], -79.155, places=4)

    def test_jpeg_without_gps_returns_none(self):
        self.assertIsNone(evidence.extract_exif_gps(make_jpeg(None)))

    def test_non_image_bytes_return_none(self):
        self.assertIsNone(evidence.extract_exif_gps(b"definitely not an image"))

    def test_parse_exif_gps_with_ifdrational_values(self):
        fake = FakeExif({
            1: b"N",
            2: (IFDRational(17, 1), IFDRational(15, 1), IFDRational(0, 1)),
            3: b"E",
            4: (IFDRational(79, 1), IFDRational(9, 1), IFDRational(18, 1)),
        })
        coords = evidence.parse_exif_gps(fake)
        self.assertAlmostEqual(coords["latitude"], 17.25, places=6)
        self.assertAlmostEqual(coords["longitude"], 79.155, places=6)

    def test_missing_hemisphere_reference_is_refused(self):
        fake = FakeExif({2: (17.25, 0, 0), 4: (79.155, 0, 0)})
        self.assertIsNone(evidence.parse_exif_gps(fake))

    def test_missing_hemisphere_reference_with_negative_value_refused(self):
        fake = FakeExif({2: (-17.25, 0, 0), 4: (-79.155, 0, 0)})
        self.assertIsNone(evidence.parse_exif_gps(fake))

    def test_out_of_range_values_refused(self):
        fake = FakeExif({1: "N", 2: (95.0, 0, 0), 3: "E", 4: (79.0, 0, 0)})
        self.assertIsNone(evidence.parse_exif_gps(fake))

    def test_malformed_gps_ifd_never_raises(self):
        self.assertIsNone(evidence.parse_exif_gps(FakeExif({2: "garbage", 4: None})))
        self.assertIsNone(evidence.parse_exif_gps(None))

        class Broken:
            def get_ifd(self, tag):
                raise RuntimeError("boom")

        self.assertIsNone(evidence.parse_exif_gps(Broken()))


class InspectPhotoTests(unittest.TestCase):
    def test_valid_jpeg(self):
        result = evidence.inspect_photo(make_jpeg(None))
        self.assertEqual(result["mime"], "image/jpeg")
        self.assertEqual(result["ext"], "jpg")
        self.assertIsNone(result["exif"])

    def test_valid_png(self):
        buffer = io.BytesIO()
        Image.new("RGB", (8, 8), "blue").save(buffer, format="PNG")
        result = evidence.inspect_photo(buffer.getvalue())
        self.assertEqual(result["mime"], "image/png")
        self.assertEqual(result["ext"], "png")

    def test_junk_bytes_rejected(self):
        with self.assertRaises(evidence.EvidenceImageError):
            evidence.inspect_photo(b"not an image at all")

    def test_empty_bytes_rejected(self):
        with self.assertRaises(evidence.EvidenceImageError):
            evidence.inspect_photo(b"")

    def test_oversize_rejected(self):
        with self.assertRaises(evidence.PhotoTooLargeError):
            evidence.inspect_photo(b"\x00" * (evidence.MAX_PHOTO_BYTES + 1))


class EvidenceFlagsTests(unittest.TestCase):
    def setUp(self):
        evidence.reset_memory()

    def _photo(self, farm_id, inside=False, with_coords=True):
        evidence.persist_record({
            "farm_id": farm_id, "kind": "photo", "sha256": "a" * 64,
            "mime": "image/jpeg", "size_bytes": 10,
            "latitude": 17.25 if with_coords else None,
            "longitude": 79.155 if with_coords else None,
            "inside_boundary": inside, "captured_at": None,
            "created_by": "9000000001",
        })

    def _geotag(self, farm_id, inside):
        evidence.persist_record({
            "farm_id": farm_id, "kind": "geotag", "sha256": None, "mime": None,
            "size_bytes": None, "latitude": 17.25, "longitude": 79.155,
            "inside_boundary": inside, "captured_at": None,
            "created_by": "9000000001",
        })

    def test_empty_state_is_all_false(self):
        flags = evidence.evidence_flags("farm-empty")
        self.assertEqual(flags, {
            "practice_photo": False, "geotag_inside_boundary": False,
            "demo_mode": True, "photo_count": 0, "geotag_count": 0,
            "last_photo_at": None,
        })

    def test_photo_without_coords_sets_practice_photo_only(self):
        self._photo("farm-p", with_coords=False)
        flags = evidence.evidence_flags("farm-p")
        self.assertTrue(flags["practice_photo"])
        self.assertFalse(flags["geotag_inside_boundary"])
        self.assertEqual(flags["photo_count"], 1)
        self.assertEqual(flags["geotag_count"], 0)
        self.assertIsInstance(flags["last_photo_at"], str)

    def test_outside_geotag_does_not_pass(self):
        self._geotag("farm-out", inside=False)
        flags = evidence.evidence_flags("farm-out")
        self.assertFalse(flags["practice_photo"])
        self.assertFalse(flags["geotag_inside_boundary"])
        self.assertEqual(flags["geotag_count"], 1)

    def test_inside_geotag_passes(self):
        self._geotag("farm-in", inside=True)
        flags = evidence.evidence_flags("farm-in")
        self.assertTrue(flags["geotag_inside_boundary"])
        self.assertEqual(flags["geotag_count"], 1)

    def test_photo_with_in_bounds_exif_counts_as_geotag(self):
        self._photo("farm-exif", inside=True)
        flags = evidence.evidence_flags("farm-exif")
        self.assertTrue(flags["practice_photo"])
        self.assertTrue(flags["geotag_inside_boundary"])
        self.assertEqual(flags["photo_count"], 1)
        self.assertEqual(flags["geotag_count"], 1)

    def test_flags_are_farm_scoped(self):
        self._geotag("farm-one", inside=True)
        flags = evidence.evidence_flags("farm-two")
        self.assertFalse(flags["practice_photo"])
        self.assertFalse(flags["geotag_inside_boundary"])

    def test_list_evidence_caps_and_strips_created_by(self):
        for index in range(7):
            self._photo(f"farm-cap-{index}", with_coords=False)
        for index in range(7):
            self._geotag("farm-cap", inside=index % 2 == 0)
        listing = evidence.list_evidence("farm-cap", per_kind=5)
        self.assertEqual(len(listing["photos"]), 0)  # photos are a different farm
        self.assertEqual(len(listing["geotags"]), 5)
        for record in listing["geotags"]:
            self.assertNotIn("created_by", record)
            self.assertIn("inside_boundary", record)
            self.assertIn("created_at", record)


if __name__ == "__main__":
    unittest.main()
