"""Verra-style PDF certificate generation for retired credit batches.

Renders a single-page A4 landscape certificate: issuer band, buyer, batch
details, the SHA-256 batch hash, and the tamper-evident provenance note.
Pure reportlab — no external services.
"""
import io
from datetime import datetime, timezone

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

FOREST = HexColor("#1B4332")
MID = HexColor("#2D6A4F")
GOLD = HexColor("#B7791F")
INK = HexColor("#1F2937")
MUTE = HexColor("#6B7280")
CREAM = HexColor("#F8FAF8")


def _wrapped(c, text, x, y, max_w, font="Helvetica", size=11, leading=15, color=INK):
    c.setFont(font, size)
    c.setFillColor(color)
    words, line = text.split(), ""
    for w in words:
        trial = (line + " " + w).strip()
        if c.stringWidth(trial, font, size) <= max_w:
            line = trial
        else:
            c.drawString(x, y, line)
            y -= leading
            line = w
    if line:
        c.drawString(x, y, line)
        y -= leading
    return y


def render_certificate_pdf(cert: dict) -> bytes:
    """cert: {id, buyer, farmer_name(s), crop, volume, value, location,
              issued_date, retired_date, batch_hash, listing_id}"""
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

    # Header band
    c.setFillColor(FOREST)
    c.rect(34, h - 118, w - 68, 84, stroke=0, fill=1)
    c.setFillColor(HexColor("#D1FAE5"))
    c.setFont("Helvetica-Bold", 26)
    c.drawString(64, h - 78, "CarbonX")
    c.setFont("Helvetica", 12.5)
    c.drawString(64, h - 100, "Carbon Credit Retirement Certificate — Sentinel-2 verified, hash-anchored")
    c.setFillColor(HexColor("#95D5B2"))
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(w - 64, h - 78, f"Certificate {cert.get('id', '')}")

    # Title
    y = h - 168
    c.setFillColor(INK)
    c.setFont("Helvetica-Bold", 21)
    c.drawCentredString(w / 2, y, "This certifies that")
    y -= 34
    c.setFont("Helvetica-Bold", 24)
    c.setFillColor(FOREST)
    c.drawCentredString(w / 2, y, cert.get("buyer") or "Corporate Buyer")
    y -= 26
    c.setFont("Helvetica", 12.5)
    c.setFillColor(MUTE)
    c.drawCentredString(w / 2, y, "has permanently retired the following carbon credits — purchase equals retirement, one step.")

    # Details grid
    y -= 52
    rows = [
        ("Credits retired", f"{cert.get('volume', '—')} tCO2e"),
        ("Credit type", f"Agricultural carbon ({cert.get('crop') or 'Mixed Crop'}) — VM0042-aligned methodology"),
        ("Source parcels", cert.get("location") or "Telangana, India"),
        ("Verified farmers", cert.get("farmer_name") or "Registered smallholders"),
        ("Retirement date", cert.get("retired_date") or datetime.now(timezone.utc).strftime("%d %B %Y")),
    ]
    col_x = w / 2 - 330
    for label, value in rows:
        c.setFont("Helvetica-Bold", 11)
        c.setFillColor(MUTE)
        c.drawString(col_x, y, label.upper())
        c.setFont("Helvetica-Bold", 13)
        c.setFillColor(INK)
        c.drawString(col_x + 210, y, str(value))
        y -= 27

    # Hash block
    y -= 16
    c.setFillColor(CREAM)
    c.roundRect(col_x, y - 58, w - 2 * (col_x + 40), 62, 8, stroke=0, fill=1)
    c.setStrokeColor(MID)
    c.setLineWidth(1)
    c.roundRect(col_x, y - 58, w - 2 * (col_x + 40), 62, 8, stroke=1, fill=0)
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(MID)
    c.drawString(col_x + 16, y - 12, "TAMPER-EVIDENT BATCH HASH (SHA-256)")
    c.setFont("Courier", 11)
    c.setFillColor(INK)
    c.drawString(col_x + 16, y - 32, str(cert.get("batch_hash") or ""))
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(MUTE)
    c.drawString(col_x + 16, y - 48, "Recompute the full event chain (ISSUE -> SALE -> SPLIT -> RETIRE) any time via GET /ledger/{farm_id}.")

    # Footer signatures
    c.setFont("Helvetica", 9.5)
    c.setFillColor(MUTE)
    c.drawString(64, 62, "Escrow-settled · conditional split executed (farmer 70% floor) · credits permanently retired — no resale possible")
    c.setFont("Helvetica", 8.5)
    c.drawString(64, 46, "Certificate integrity is verifiable against the platform ledger. Escrow simulated in this build; production settles via payment-gateway escrow with the same split logic.")
    c.setStrokeColor(MUTE)
    c.setLineWidth(0.8)
    c.line(w - 320, 70, w - 90, 70)
    c.setFont("Helvetica-Oblique", 10)
    c.drawString(w - 320, 56, "Authorised signatory — CarbonX Registry")

    c.showPage()
    c.save()
    return buf.getvalue()
