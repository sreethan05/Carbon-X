"""Verra-style PDF certificate generation for retired credit batches.

Renders a single-page A4 landscape certificate: issuer band, buyer, batch
details, the SHA-256 batch hash, security watermark, verification QR code,
and the tamper-evident provenance note.
Pure reportlab — no external services.
Includes thread-safe in-memory LRU caching.
"""
import io
import logging
import re
from collections import OrderedDict
from threading import RLock
from typing import Optional

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.graphics.barcode import qr
from reportlab.graphics.shapes import Drawing
from reportlab.graphics import renderPDF

logger = logging.getLogger("carbonx.certificate")

FOREST = HexColor("#1B4332")
MID = HexColor("#2D6A4F")
GOLD = HexColor("#B7791F")
INK = HexColor("#1F2937")
MUTE = HexColor("#6B7280")
CREAM = HexColor("#F8FAF8")
WATERMARK_PRIMARY = HexColor("#E8EBE8")
WATERMARK_SECONDARY = HexColor("#EFF2EF")


class CertificatePdfCache:
    """Thread-safe LRU cache for rendered certificate PDFs."""

    def __init__(self, maxsize: int = 512):
        self._maxsize = maxsize
        self._cache: OrderedDict[str, bytes] = OrderedDict()
        self._lock = RLock()

    def get(self, key: str) -> Optional[bytes]:
        if not key:
            return None
        with self._lock:
            if key not in self._cache:
                return None
            self._cache.move_to_end(key)
            return self._cache[key]

    def set(self, key: str, value: bytes) -> None:
        if not key:
            return
        with self._lock:
            if key in self._cache:
                self._cache.move_to_end(key)
            self._cache[key] = value
            while len(self._cache) > self._maxsize:
                self._cache.popitem(last=False)

    def invalidate(self, cert_id: str) -> None:
        """Invalidate any cache entry associated with cert_id."""
        if not cert_id:
            return
        cid_str = str(cert_id)
        with self._lock:
            keys_to_remove = [k for k in self._cache if k == cid_str or k.startswith(f"{cid_str}:")]
            for k in keys_to_remove:
                self._cache.pop(k, None)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._cache)

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._cache), "maxsize": self._maxsize}


_pdf_cache = CertificatePdfCache(maxsize=512)


def get_cached_certificate_pdf(cert_id: str) -> Optional[bytes]:
    """Look up a rendered certificate PDF from the LRU cache."""
    return _pdf_cache.get(cert_id)


def invalidate_certificate_pdf(cert_id: str) -> None:
    """Remove every cached variant of a certificate (public/full)."""
    _pdf_cache.invalidate(cert_id)
    prefix = f"{cert_id}:"
    for key in list(getattr(_pdf_cache, "_cache", {}).keys()):
        if str(key).startswith(prefix):
            _pdf_cache.invalidate(key)


def clear_certificate_pdf_cache() -> None:
    """Clear all entries from the LRU cache."""
    _pdf_cache.clear()


def certificate_cache_stats() -> dict:
    """Return current LRU cache statistics."""
    return _pdf_cache.stats()


def _wrapped(c, text, x, y, max_w, font="Helvetica", size=11, leading=15, color=INK):
    c.setFont(font, size)
    c.setFillColor(color)
    words, line = str(text or "").split(), ""
    for w in words:
        trial = (line + " " + w).strip()
        if c.stringWidth(trial, font, size) <= max_w:
            line = trial
        else:
            if line:
                c.drawString(x, y, line)
                y -= leading
            line = _fit_string(c, w, font, size, max_w) if c.stringWidth(w, font, size) > max_w else w
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def _fit_string(c, text: str, font: str, size: float, max_w: float) -> str:
    """Fit a string within max_w, truncating with ellipsis if necessary.

    Uses binary search with an initial width-bounded prefix to guarantee O(log N)
    time even on massive strings (e.g. 50k+ chars), preventing algorithmic DoS.
    """
    if text is None:
        return ""
    # Flatten newlines, tabs, and excess whitespace for single-line display
    s = re.sub(r"[\r\n\t]+", " ", str(text)).strip()
    if max_w <= 0:
        return ""
    if c.stringWidth(s, font, size) <= max_w:
        return s

    ellipsis = "..."
    ellipsis_w = c.stringWidth(ellipsis, font, size)
    if ellipsis_w >= max_w:
        return ellipsis if ellipsis_w == max_w else ""

    # Upper bound estimate: max characters that could conceivably fit.
    # In standard Type 1 fonts at size >= 6, character widths are at least ~1.5 pt.
    max_possible_chars = max(50, int(max_w * 4))
    s = s[:min(len(s), max_possible_chars)]

    low = 0
    high = len(s)
    best = 0
    while low <= high:
        mid = (low + high) // 2
        trial = s[:mid] + ellipsis
        if c.stringWidth(trial, font, size) <= max_w:
            best = mid
            low = mid + 1
        else:
            high = mid - 1

    return (s[:best] + ellipsis) if best > 0 else ellipsis


def render_certificate_pdf(cert: dict, use_cache: bool = True) -> bytes:
    """cert: {id, buyer, farmer_name(s), crop, volume, value, location,
              issued_date, retired_date, batch_hash, listing_id, status}"""
    cert_id = "" if cert.get("id") is None else str(cert.get("id"))
    status = str(cert.get("status") or "RETIRED").upper()
    retired = status == "RETIRED"
    refunded = status == "REFUNDED"
    failed = status == "FAILED"
    disputed = str(cert.get("dispute_status") or "").upper() == "OPEN"
    batch_hash = "" if cert.get("batch_hash") is None else str(cert.get("batch_hash"))
    access = "public" if cert.get("public_view") else "full"
    cache_key = f"{cert_id}:{status}:{batch_hash}:{access}:{disputed}" if cert_id else ""

    if use_cache and cache_key:
        cached = _pdf_cache.get(cache_key)
        if cached is not None:
            return cached

    buf = io.BytesIO()
    w, h = landscape(A4)
    c = canvas.Canvas(buf, pagesize=landscape(A4))

    # Frame
    c.setStrokeColor(FOREST)
    c.setLineWidth(6)
    c.rect(24, 24, w - 48, h - 48, stroke=1, fill=0)
    c.setStrokeColor(GOLD)
    c.setLineWidth(1.4)
    c.rect(34, 34, w - 68, h - 68, stroke=1, fill=0)

    # Security watermark (behind content)
    c.saveState()
    c.setFont("Helvetica-Bold", 34)
    c.setFillColor(WATERMARK_PRIMARY)
    c.translate(w / 2, h / 2 - 25)
    c.rotate(28)
    if refunded:
        watermark_text = "CARBONX REGISTRY · REFUNDED · VOID FOR OFFSET CLAIMS"
    elif failed:
        watermark_text = "CARBONX REGISTRY · SETTLEMENT FAILED · NOT VALID"
    elif disputed:
        watermark_text = "CARBONX REGISTRY · DISPUTED · FROZEN"
    elif retired:
        watermark_text = "CARBONX REGISTRY · PERMANENTLY RETIRED · IMMUTABLE"
    else:
        watermark_text = "CARBONX REGISTRY · ESCROW HELD · PENDING RETIREMENT"
    c.drawCentredString(0, 0, watermark_text)
    c.setFont("Helvetica", 13)
    c.setFillColor(WATERMARK_SECONDARY)
    c.drawCentredString(0, -26, "OFFICIAL DIGITAL RECORD · VERIFIABLE VIA SHA-256 HASH CHAIN")
    c.restoreState()

    # Header band
    c.setFillColor(FOREST)
    c.rect(34, h - 118, w - 68, 84, stroke=0, fill=1)
    c.setFillColor(HexColor("#D1FAE5"))
    c.setFont("Helvetica-Bold", 26)
    c.drawString(64, h - 78, "CarbonX")
    c.setFont("Helvetica", 12.5)
    c.drawString(64, h - 100, "Pilot MRV retirement record — Sentinel-2 based, hash-anchored")
    c.setFillColor(HexColor("#95D5B2"))
    c.setFont("Helvetica-Bold", 11)
    header_cert_label = _fit_string(c, f"Certificate {cert_id}".strip(), "Helvetica-Bold", 11, w / 2 - 80)
    c.drawRightString(w - 64, h - 78, header_cert_label)

    # Title
    y = h - 168
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 21)
    c.drawCentredString(w / 2, y, "This certifies that")
    y -= 34
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(FOREST)
    buyer_name = _fit_string(c, cert.get("buyer") or "—", "Helvetica-Bold", 24, w - 140)
    c.drawCentredString(w / 2, y, buyer_name)
    y -= 26
    c.setFont("Helvetica", 12.5)
    c.setFillColor(MUTE)
    if refunded:
        statement = "was refunded for the following credits — this certificate is void for offset claims."
    elif failed:
        statement = "has a failed settlement — no certificate was issued for these credits."
    elif disputed:
        statement = "has a disputed record — this certificate is frozen pending staff resolution."
    elif retired:
        statement = "has permanently retired the following carbon credits — purchase equals retirement, one step."
    else:
        statement = "holds the following carbon credits in escrow — not yet permanently retired."
    c.drawCentredString(w / 2, y, statement)

    # Details grid
    y -= 52
    vol = cert.get("volume")
    vol_str = f"{vol} tCO2e" if vol is not None else "— tCO2e"
    crop_str = cert.get("crop") or "crop not recorded"
    basis = "PROXY ESTIMATE — not field validated" if str(cert.get("credits_basis") or "").startswith("proxy") else "Field-validated estimate"
    credit_label = "Credits refunded" if refunded else ("Credits retired" if retired else "Credits held")
    rows = [
        (credit_label, vol_str),
        ("Certificate status", (
            "REFUNDED — VOID" if refunded else
            ("SETTLEMENT FAILED" if failed else
             ("DISPUTED — FROZEN" if disputed else status))
        )),
        ("Credit type", f"Agricultural carbon ({crop_str}) — VM0042-structured methodology"),
        ("Estimate basis", basis),
        ("Source parcels", cert.get("location") or "location not recorded"),
        ("Farmers", cert.get("farmer_name") or "not recorded"),
        ("Retirement date", (cert.get("retired_date") or "—") if retired else "Not retired"),
    ]
    col_x = w / 2 - 330
    max_val_w = w - (col_x + 210) - 52
    for label, value in rows:
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(MUTE)
        c.drawString(col_x, y, label.upper())
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(INK)
        val_fitted = _fit_string(c, str(value), "Helvetica-Bold", 13, max_val_w)
        c.drawString(col_x + 210, y, val_fitted)
        y -= 27

    # Hash block & QR verification box
    y -= 16
    box_w = w - 2 * (col_x + 40)
    c.setFillColor(CREAM)
    c.roundRect(col_x, y - 58, box_w, 62, 8, stroke=0, fill=1)
    c.setStrokeColor(MID)
    c.setLineWidth(1)
    c.roundRect(col_x, y - 58, box_w, 62, 8, stroke=1, fill=0)

    # Vector QR code (right side of hash block)
    qr_size = 48
    qr_x = col_x + box_w - qr_size - 10
    qr_drawn = False
    try:
        # Sanitize parameters for verification URL
        safe_id = re.sub(r"[^a-zA-Z0-9_\-\.]", "", cert_id)[:64]
        safe_hash = re.sub(r"[^a-fA-F0-9]", "", batch_hash)[:64]
        verify_url = f"https://carbonx.farm/verify/{safe_id}"
        if safe_hash:
            verify_url += f"?hash={safe_hash}"
        qr_widget = qr.QrCodeWidget(verify_url)
        bounds = qr_widget.getBounds()
        bw = bounds[2] - bounds[0]
        bh = bounds[3] - bounds[1]
        if bw > 0 and bh > 0:
            qr_d = Drawing(qr_size, qr_size, transform=[qr_size / bw, 0, 0, qr_size / bh, 0, 0])
            qr_d.add(qr_widget)
            renderPDF.draw(qr_d, c, qr_x, y - 52)
            c.setFont("Helvetica-Bold", 6.5)
            c.setFillColor(MID)
            c.drawCentredString(qr_x + qr_size / 2, y - 57, "SCAN TO VERIFY")
            qr_drawn = True
    except Exception as e:
        logger.warning("Certificate QR code generation failed: %s", e)

    if not qr_drawn:
        # Graceful placeholder when QR data is invalid or generation fails
        c.setStrokeColor(MUTE)
        c.setLineWidth(0.8)
        c.rect(qr_x, y - 52, qr_size, qr_size, stroke=1, fill=0)
        c.setFont("Helvetica-Bold", 5.5)
        c.setFillColor(MUTE)
        c.drawCentredString(qr_x + qr_size / 2, y - 28, "QR CODE")
        c.drawCentredString(qr_x + qr_size / 2, y - 36, "N/A")
        c.setFont("Helvetica-Bold", 6.5)
        c.setFillColor(MID)
        c.drawCentredString(qr_x + qr_size / 2, y - 57, "VERIFY ONLINE")

    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(MID)
    c.drawString(col_x + 16, y - 12, "TAMPER-EVIDENT BATCH HASH (SHA-256)")
    c.setFont("Courier", 10)
    c.setFillColor(INK)
    hash_str = batch_hash if batch_hash else "NO HASH RECORDED"
    hash_display = _fit_string(c, hash_str, "Courier", 10, qr_x - (col_x + 24))
    c.drawString(col_x + 16, y - 32, hash_display)
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(MUTE)
    c.drawString(col_x + 16, y - 48, "Recompute the full event chain (ISSUE -> SALE -> SPLIT -> RETIRE) any time via GET /ledger/{farm_id}.")

    # Footer signatures
    c.setFont("Helvetica", 9.5)
    c.setFillColor(MUTE)
    footer_state = ("credits permanently retired — no resale possible"
                    if retired else "credits held in escrow — retirement pending")
    c.drawString(64, 62, f"Escrow-settled · conditional split executed (farmer 70% floor) · {footer_state}")
    c.setFont("Helvetica", 8.5)
    c.drawString(64, 46, "Certificate integrity is verifiable against the platform ledger. Escrow simulated in this build; production settles via payment-gateway escrow with the same split logic.")
    c.setStrokeColor(MUTE)
    c.setLineWidth(0.8)
    c.line(w - 320, 70, w - 90, 70)
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(w - 320, 56, "Authorised signatory — CarbonX Registry")

    c.showPage()
    c.save()
    pdf_bytes = buf.getvalue()

    if use_cache:
        if cache_key:
            _pdf_cache.set(cache_key, pdf_bytes)
        if cert_id:
            _pdf_cache.set(cert_id, pdf_bytes)

    return pdf_bytes
