"""KYC document analysis and verification service for CarbonX.

Performs:
1. Tesseract OCR text extraction on uploaded land records (Patta, 7/12, etc.).
2. Village geocoding via OpenStreetMap / Nominatim.
3. Satellite NDVI assessment for the farmer's land location via Google Earth Engine.
4. Aadhaar Verhoeff validation and duplicate hash checks.
"""

import base64
import hashlib
import io
import os
from difflib import SequenceMatcher
from typing import Any, Optional

from PIL import Image

from app.services.geocoding_service import geocode_village
from app.services.gee_service import get_ndvi_at_point

LAND_DOCUMENT_KEYWORDS = (
    "patta", "pattadar", "7/12", "land revenue", "survey no",
    "survey number", "khata", "khasra", "revenue record", "acre", "hectare",
    "dharani", "meeseva", "bhulekh", "jamabandi", "ror", "passbook", "adangal",
    "pahani", "chitta", "khatian", "deed", "ownership", "title", "government",
    "telangana", "andhra", "karnataka", "maharashtra", "district", "village",
)


def _configure_tesseract():
    """Detect and configure Tesseract executable on Windows or system PATH.

    Returns None (silent) when the binary is missing so callers fall back
    to user-supplied `extracted_text` / Azure Document Intelligence.
    """
    try:
        import shutil

        import pytesseract
        windows_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
            os.path.expandvars(r"%LOCALAPPDATA%\Tesseract-OCR\tesseract.exe"),
        ]
        for path in windows_paths:
            if os.path.exists(path):
                pytesseract.pytesseract.tesseract_cmd = path
                return pytesseract
        # No hard-coded Windows path found — trust PATH, else give up silently.
        if shutil.which("tesseract") or shutil.which(pytesseract.pytesseract.tesseract_cmd):
            return pytesseract
        return None
    except ImportError:
        return None


def validate_aadhaar(number: str) -> bool:
    """Validate the 12-digit Aadhaar number using the Verhoeff checksum."""
    digits = str(number or "").replace(" ", "").replace("-", "")
    if len(digits) != 12 or not digits.isdigit() or digits[0] in "01":
        return False
    multiplication = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
        (2, 3, 4, 0, 1, 7, 8, 9, 5, 6), (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
        (4, 0, 1, 2, 3, 9, 5, 6, 7, 8), (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
        (6, 5, 9, 8, 7, 1, 0, 4, 3, 2), (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
        (8, 7, 6, 5, 9, 3, 2, 1, 0, 4), (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
    )
    permutation = (
        (0, 1, 2, 3, 4, 5, 6, 7, 8, 9), (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
        (5, 8, 0, 3, 7, 9, 6, 1, 4, 2), (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
        (9, 4, 5, 3, 1, 2, 6, 8, 7, 0), (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
        (2, 7, 9, 3, 8, 0, 6, 4, 1, 5), (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
    )
    check = 0
    for index, char in enumerate(reversed(digits)):
        check = multiplication[check][permutation[index % 8][int(char)]]
    return check == 0


def _average_hash(image: Image.Image) -> str:
    pixels = list(image.convert("L").resize((16, 16)).getdata())
    average = sum(pixels) / len(pixels)
    return "".join("1" if pixel >= average else "0" for pixel in pixels)


def _extract_ocr_text(image: Image.Image) -> tuple[str, bool]:
    """Run Tesseract OCR on a PIL image.

    Silent fallback: returns ("", False) when the binary is missing so the
    pipeline can use `extracted_text` / Azure instead. No noisy traceback.
    """
    pytess = _configure_tesseract()
    if not pytess:
        return "", False
    try:
        text = pytess.image_to_string(image)
        return text.strip(), True
    except Exception:
        return "", False


def _match_name(owner_name: str, text: str) -> tuple[int, bool]:
    """Check if owner name appears in OCR text (exact, token, or fuzzy)."""
    owner_clean = owner_name.lower().strip()
    text_clean = text.lower().strip()
    if not owner_clean or not text_clean:
        return 0, False

    # 1. Direct substring match
    if owner_clean in text_clean:
        return 100, True

    # 2. Token overlap (e.g. first name or last name match with length >= 3)
    owner_tokens = [tok for tok in owner_clean.split() if len(tok) >= 3]
    for tok in owner_tokens:
        if tok in text_clean:
            return 85, True

    # 3. Fuzzy line-by-line match
    best_ratio = 0
    for line in text_clean.splitlines():
        line = line.strip()
        if not line:
            continue
        ratio = round(SequenceMatcher(None, owner_clean, line).ratio() * 100)
        if ratio > best_ratio:
            best_ratio = ratio

    overall_ratio = round(SequenceMatcher(None, owner_clean, text_clean).ratio() * 100)
    score = max(best_ratio, overall_ratio)
    return score, score >= 60


def analyse_document(
    content_base64: str,
    filename: str,
    owner_name: str,
    extracted_text: str = "",
    known_hashes: Optional[list[str]] = None,
    village: str = "",
    district: str = "",
    state: str = "",
) -> dict[str, Any]:
    if not content_base64:
        content_base64 = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    try:
        raw = base64.b64decode(content_base64, validate=False)
    except Exception:
        raw = b""
    if not raw or len(raw) > 8 * 1024 * 1024:
        raw = b"empty_or_oversized_doc"

    sha256 = hashlib.sha256(raw).hexdigest()
    image_hash = ""
    exif_present = False
    image_readable = False
    ocr_available = False
    ocr_text = ""

    try:
        with Image.open(io.BytesIO(raw)) as image:
            image_readable = True
            exif_present = bool(image.getexif())
            image_hash = _average_hash(image)
            ocr_text, ocr_available = _extract_ocr_text(image)
    except Exception as exc:
        print(f"Image read error: {exc}")

    # Merge OCR text with any user-submitted text
    full_text = f"{ocr_text} {extracted_text}".strip()

    duplicate = sha256 in (known_hashes or [])
    keyword_source = f"{filename} {full_text}".lower()
    keywords_found = [word for word in LAND_DOCUMENT_KEYWORDS if word in keyword_source]

    # Owner name matching
    name_score, name_match = _match_name(owner_name, full_text)

    # Village geocoding & NDVI retrieval
    geocoded_location = None
    satellite_ndvi = None
    geocode_ndvi_available = False

    if village or district or state:
        geo = geocode_village(village, district, state)
        if geo:
            geocoded_location = geo
            satellite_ndvi = get_ndvi_at_point(geo["lat"], geo["lon"])
            geocode_ndvi_available = True

    return {
        "document_sha256": sha256,
        "perceptual_hash": image_hash,
        "image_readable": image_readable,
        "exif_present": exif_present,
        "duplicate_detected": duplicate,
        "keywords_found": keywords_found,
        "keywords_valid": bool(keywords_found),
        "name_match_score": name_score,
        "name_match": name_match,
        "ocr_available": ocr_available,
        "ocr_text_preview": ocr_text[:300] if ocr_text else "",
        "geocoded_location": geocoded_location,
        "satellite_ndvi": satellite_ndvi,
        "geocode_ndvi_available": geocode_ndvi_available,
    }
