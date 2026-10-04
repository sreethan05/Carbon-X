"""Canonical sample/demo data for CarbonX.

Two consumers:
- scripts/seed_marketplace_data.py — seeds this data into the live Supabase DB.
- The open GET /marketplace/listings endpoint — serves FALLBACK_LISTINGS when the
  live database is unreachable, so the dashboard always has data.

The listing tuples in LISTINGS are the single source of truth; materialize_listings()
turns them into rows shaped like marketplace_listings DB rows.
"""
import uuid
from datetime import datetime, timedelta, timezone

from app.supabase_db import LISTING_SORT_COLUMNS

# Fallback rows use a fixed reference date so their "days ago" values stay stable.
FALLBACK_AS_OF = datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc)

TEST_FARMER_PHONE = "9876543210"
TEST_FARMER_NAME = "Test Farmer"
TEST_FARM_ID = "172d370a-f799-4c18-a82a-e38f4edbcdea"
IMAGE_URL = "https://images.unsplash.com/photo-1500937386664-56d1dfef3854?auto=format&fit=crop&q=80&w=400"

FARMERS = {
    "9000000001": {"name": "Venkat Rao", "state": "Telangana", "district": "Khammam", "village": "Bonakal", "upi": "venkatrao@upi"},
    "9000000002": {"name": "Anjali Devi", "state": "Telangana", "district": "Nizamabad", "village": "Yellareddy", "upi": "anjalidevi@upi"},
    "9000000003": {"name": "Mohan Reddy", "state": "Telangana", "district": "Karimnagar", "village": "Jagtial", "upi": "mohanreddy@upi"},
    "9000000004": {"name": "Farida Begum", "state": "Telangana", "district": "Nalgonda", "village": "Devarakonda", "upi": "faridabegum@upi"},
}

FARMS = [
    {"key": "venkat_rice", "phone": "9000000001", "name": "Sri Venkateswara Organic Farm", "crop": "Rice", "area": 2.4, "carbon": 82, "score": 720, "ndvi": 0.78, "evi": 0.65, "soil": 41, "trees": 28, "irrigation": "Drip"},
    {"key": "venkat_maize", "phone": "9000000001", "name": "Godavari Maize Plot", "crop": "Maize", "area": 1.6, "carbon": 64, "score": 260, "ndvi": 0.71, "evi": 0.58, "soil": 36, "trees": 12, "irrigation": "Canal"},
    {"key": "anjali_millet", "phone": "9000000002", "name": "Anjali Millet Farm", "crop": "Millets", "area": 1.8, "carbon": 38, "score": 190, "ndvi": 0.62, "evi": 0.51, "soil": 29, "trees": 18, "irrigation": "Rainfed"},
    {"key": "anjali_turmeric", "phone": "9000000002", "name": "Turmeric Gold Plot", "crop": "Turmeric", "area": 1.1, "carbon": 51, "score": 180, "ndvi": 0.69, "evi": 0.55, "soil": 44, "trees": 9, "irrigation": "Drip"},
    {"key": "mohan_cotton", "phone": "9000000003", "name": "Reddy Cotton Fields", "crop": "Cotton", "area": 3.2, "carbon": 105, "score": 520, "ndvi": 0.74, "evi": 0.61, "soil": 33, "trees": 34, "irrigation": "Drip"},
    {"key": "mohan_sugarcane", "phone": "9000000003", "name": "Sugarcane Green Plot", "crop": "Sugarcane", "area": 2.0, "carbon": 132, "score": 240, "ndvi": 0.81, "evi": 0.70, "soil": 52, "trees": 15, "irrigation": "Canal"},
    {"key": "farida_chilli", "phone": "9000000004", "name": "Green Chilli Estate", "crop": "Chilli", "area": 1.2, "carbon": 33, "score": 150, "ndvi": 0.66, "evi": 0.53, "soil": 31, "trees": 11, "irrigation": "Drip"},
]

# (farm_key|None, farmer_phone, crop, location, size_label, model, status,
#  carbon_credits, biodiversity_credits, price,
#  days_ago, expires_in_days, token_id, tx_hash)
LISTINGS = [
    ("venkat_rice", "9000000001", "Rice", "Bonakal, Khammam, Telangana", "2.4 ha", "Fixed Price", "Active", 78, 18, 540, 1, None, None, None),
    ("venkat_maize", "9000000001", "Maize", "Bonakal, Khammam, Telangana", "1.6 ha", "Fixed Price", "Active", 58, 6, 520, 3, 7, None, None),
    ("anjali_millet", "9000000002", "Millets", "Yellareddy, Nizamabad, Telangana", "1.8 ha", "Fixed Price", "Active", 38, 4, 610, 4, None, None, None),
    ("anjali_turmeric", "9000000002", "Turmeric", "Yellareddy, Nizamabad, Telangana", "1.1 ha", "Fixed Price", "Active", 50, 5, 590, 6, 3, None, None),
    ("mohan_cotton", "9000000003", "Cotton", "Jagtial, Karimnagar, Telangana", "3.2 ha", "Fixed Price", "Active", 105, 13, 495, 7, None, None, None),
    ("mohan_sugarcane", "9000000003", "Sugarcane", "Jagtial, Karimnagar, Telangana", "2.0 ha", "Fixed Price", "Active", 132, 6, 530, 9, 10, None, None),
    ("farida_chilli", "9000000004", "Chilli", "Devarakonda, Nalgonda, Telangana", "1.2 ha", "Fixed Price", "Active", 33, 3, 650, 11, None, None, None),
    (None, TEST_FARMER_PHONE, "Paddy", "Moinabad, Rangareddy, Telangana", "0.1 ha", "Fixed Price", "Sold", 0.92, 0.22, 575, 20, None, "CX-TOK-0041", "0x9f3e7a2b41d8c6e5f0a1b9c8d7e6f5a4b3c2d1e0"),
    ("mohan_cotton", "9000000003", "Cotton", "Jagtial, Karimnagar, Telangana", "2.8 ha", "Fixed Price", "Expired", 82, 8, 560, 16, -5, None, None),
    ("venkat_rice", "9000000001", "Rice", "Bonakal, Khammam, Telangana", "2.0 ha", "Fixed Price", "Sold", 68, 16, 530, 12, None, "CX-TOK-0037", "0x7b1c95d2e8f4a307c6b19e5d8f2a4c7e9b1d6f30"),
]


def farm_geojson():
    return {
        "type": "Feature",
        "geometry": {
            "type": "Polygon",
            "coordinates": [[[79.15, 17.25], [79.16, 17.25], [79.16, 17.26], [79.15, 17.26], [79.15, 17.25]]],
        },
    }


def _fallback_farm_id(farm_key):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"carbonx:demo-farm:{farm_key}"))


def materialize_listings(as_of=None, farm_ids=None, with_ids=False):
    """Build listing rows shaped like marketplace_listings DB rows.

    as_of: reference datetime for created_at/updated_at/expires_at (default: fixed FALLBACK_AS_OF).
    farm_ids: real farm ids from the live DB (used when seeding); keys of FARMS entries.
    with_ids: attach deterministic static ids (used for endpoint fallback rows).
    """
    as_of = as_of or FALLBACK_AS_OF
    farm_ids = farm_ids or {}
    rows = []
    for i, tup in enumerate(LISTINGS):
        (farm_key, phone, crop, location, size_label, model, status, cc, bc,
         price, days_ago, expires_in_days, token_id, tx_hash) = tup
        farmer = FARMERS.get(phone)
        if farm_key:
            farm_id = farm_ids.get(farm_key) or _fallback_farm_id(farm_key)
        else:
            farm_id = TEST_FARM_ID
        created = (as_of - timedelta(days=days_ago)).isoformat()
        expires = (
            (as_of + timedelta(days=expires_in_days)).isoformat()
            if expires_in_days is not None
            else None
        )
        row = {
            "farm_id": farm_id,
            "farmer_phone": phone,
            "farmer_name": farmer["name"] if farmer else TEST_FARMER_NAME,
            "crop": crop,
            "location": location,
            "size_label": size_label,
            "listing_model": model,
            "price_per_credit": price,
            "total_credits": round(cc + bc, 2),
            "carbon_credits": cc,
            "biodiversity_credits": bc,
            "status": status,
            "expires_at": expires,
            "image_url": IMAGE_URL,
            "token_id": token_id,
            "tx_hash": tx_hash,
            "created_at": created,
            "updated_at": created,
        }
        if with_ids:
            row["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"carbonx:demo-listing:{i}"))
        rows.append(row)
    return rows


# Static rows served when the live database is unreachable.
FALLBACK_LISTINGS = materialize_listings(with_ids=True)


def _text(v):
    return str(v or "").lower()


def _sort_key(sort_col):
    def key(row):
        v = row.get(sort_col)
        if v is None:
            return (0, 0.0, "")
        if isinstance(v, (int, float)):
            return (1, float(v), "")
        return (2, 0.0, str(v).lower())

    return key


def filter_listings(
    rows,
    status="Active",
    crop=None,
    location=None,
    farmer_phone=None,
    farm_id=None,
    listing_model=None,
    min_price=None,
    max_price=None,
    min_credits=None,
    max_credits=None,
    search=None,
    sort="created_at",
    order="desc",
    limit=50,
    offset=0,
):
    """Apply the same filters as db.get_listings_filtered() to in-memory rows."""
    out = rows
    if status and status.strip().lower() != "all":
        out = [r for r in out if r.get("status") == status]
    if crop:
        out = [r for r in out if crop.lower() in _text(r.get("crop"))]
    if location:
        out = [r for r in out if location.lower() in _text(r.get("location"))]
    if farmer_phone:
        out = [r for r in out if r.get("farmer_phone") == farmer_phone]
    if farm_id:
        out = [r for r in out if r.get("farm_id") == farm_id]
    if listing_model:
        out = [r for r in out if listing_model.lower() in _text(r.get("listing_model"))]
    if min_price is not None:
        out = [r for r in out if float(r.get("price_per_credit") or 0) >= min_price]
    if max_price is not None:
        out = [r for r in out if float(r.get("price_per_credit") or 0) <= max_price]
    if min_credits is not None:
        out = [r for r in out if float(r.get("total_credits") or 0) >= min_credits]
    if max_credits is not None:
        out = [r for r in out if float(r.get("total_credits") or 0) <= max_credits]
    if search:
        needle = search.lower()
        out = [
            r for r in out
            if any(needle in _text(r.get(k)) for k in ("farmer_name", "crop", "location"))
        ]

    sort_col = sort if sort in LISTING_SORT_COLUMNS else "created_at"
    out = sorted(out, key=_sort_key(sort_col), reverse=str(order).lower() != "asc")

    total = len(out)
    return {"total": total, "listings": out[offset: offset + limit]}
