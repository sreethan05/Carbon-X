"""Create safe, fictional images for testing the CarbonX verification demo.

They are intentionally watermarked DEMO ONLY and are not government documents.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT_DIR = Path(__file__).resolve().parents[1] / "demo-assets"
WIDTH, HEIGHT = 1600, 1050


def font(size, bold=False):
    candidates = [
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\calibrib.ttf" if bold else r"C:\Windows\Fonts\calibri.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def make_document(filename, title, details, accent, watermark):
    image = Image.new("RGB", (WIDTH, HEIGHT), "#fffdf7")
    draw = ImageDraw.Draw(image)

    draw.rectangle((0, 0, WIDTH, 125), fill=accent)
    draw.text((70, 34), title, font=font(44, True), fill="white")
    draw.text((70, 87), "Fictional test record — not valid for legal, financial, or identity use", font=font(19), fill="#e8f1ea")
    draw.rounded_rectangle((70, 175, WIDTH - 70, HEIGHT - 90), radius=18, outline="#cddbd0", width=3, fill="#ffffff")
    draw.text((120, 220), "LAND OWNERSHIP VERIFICATION — DEMO DATA", font=font(30, True), fill="#173d25")

    y = 320
    for label, value in details:
        draw.text((135, y), label, font=font(25, True), fill="#45604c")
        draw.text((545, y), value, font=font(28), fill="#202d24")
        draw.line((130, y + 48, WIDTH - 130, y + 48), fill="#e2ebe3", width=2)
        y += 86

    watermark_font = font(70, True)
    draw.text((205, 770), watermark, font=watermark_font, fill="#d95050")
    draw.text((125, 935), "Created by CarbonX for OCR, duplicate, EXIF and verification-flow testing only.", font=font(19), fill="#627265")

    # Creates harmless EXIF metadata so the backend's EXIF check can be exercised.
    exif = Image.Exif()
    exif[306] = "2026:09:04 10:30:00"
    OUT_DIR.mkdir(exist_ok=True)
    image.save(OUT_DIR / filename, "JPEG", quality=94, exif=exif)


def main():
    make_document(
        "demo_land_record_valid.jpg",
        "CARBONX • DEMO LAND RECORD",
        [
            ("Owner name", "Demo Farmer"),
            ("Survey number", "CX-42/2B"),
            ("Village", "Venkateshwara Pally"),
            ("District", "Warangal, Telangana"),
            ("Recorded area", "1.80 acres"),
            ("Land use", "Agricultural crop land"),
        ],
        "#1e6a42",
        "DEMO ONLY — FICTIONAL RECORD",
    )
    make_document(
        "demo_land_record_flagged.jpg",
        "CARBONX • ALTERED TEST RECORD",
        [
            ("Owner name", "Different Person"),
            ("Survey number", "ALTERED-000"),
            ("Village", "Unknown settlement"),
            ("District", "Test district"),
            ("Recorded area", "0.00 acres"),
            ("Land use", "Unverified text"),
        ],
        "#8c3434",
        "DEMO FLAGGED — INTENTIONALLY INVALID",
    )


if __name__ == "__main__":
    main()
