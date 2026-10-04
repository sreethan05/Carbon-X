"""Seed the land_registry table with Telangana survey parcels.

Creates 30 realistic smallholder parcels across the Yadadri Bhuvanagiri /
Khammam / Nalgonda belt the platform's FPOs operate in. Deterministic
(seeded PRNG) so re-runs are idempotent: rows are upserted on survey_number.

Usage:
    python scripts/seed_land_registry.py          # uses backend/.env + Management API
    SUPABASE_PROJECT_REF=<ref> python scripts/seed_land_registry.py
"""
import json
import os
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dotenv import load_dotenv  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / "backend" / ".env")

from seed_marketplace_data import run_sql  # noqa: E402  (needs env loaded)

# Real mandal/village belt in Yadadri Bhuvanagiri + neighbouring districts.
PLACES = [
    ("Pochampally", "Yadadri Bhuvanagiri"), ("Ramannapet", "Yadadri Bhuvanagiri"),
    ("Choutuppal", "Yadadri Bhuvanagiri"), ("Atmakur", "Yadadri Bhuvanagiri"),
    ("Thirumalagiri", "Nalgonda"), ("Devarakonda", "Nalgonda"),
    ("Chityala", "Nalgonda"), ("Kattangur", "Nalgonda"),
    ("Kusumanchi", "Khammam"), ("Bonakal", "Khammam"),
    ("Madhira", "Khammam"), ("Wyra", "Khammam"),
]
FIRST_NAMES = [
    "Venkat Rao", "Anjali Devi", "Mohan Reddy", "Farida Begum", "Lakshmi",
    "Srinivas Goud", "Padma", "Rajamouli", "Yadamma", "Narsimha",
    "Sailaja", "Kistaiah", "Anasuya", "Ravi Kumar", "Buchamma",
]
SURNAMES = ["", " ", "Komuravelli", "Gundala", "Kandukuri", "Bandi", "Chiluveru", "Madikonda"]

TIER_BY_AREA = lambda ha: ("Marginal" if ha < 1 else "Small" if ha < 2 else "Semi-Medium")

# Rough bounding boxes around the belt (lat, lon) — parcels sit inside these.
BOXES = [
    (17.25, 17.45, 78.85, 79.10),   # Pochampally belt
    (17.05, 17.25, 79.05, 79.35),   # Chityala / Nalgonda north
    (16.85, 17.05, 79.15, 79.45),   # Devarakonda
    (17.15, 17.35, 79.85, 80.15),   # Khammam west
]


def generate_parcels(n=30):
    rng = random.Random(20261004)
    parcels = []
    seen_surveys = set()
    while len(parcels) < n:
        village, district = rng.choice(PLACES)
        survey = f"{rng.randint(1, 320)}/{rng.randint(1, 30)}{'ABC'[rng.randint(0, 2)] if rng.random() < 0.35 else ''}"
        if (village, survey) in seen_surveys:
            continue
        seen_surveys.add((village, survey))
        ha = round(rng.uniform(0.4, 3.8), 2)
        lat = rng.uniform(*rng.choice(BOXES)[:2])
        lon = rng.uniform(*rng.choice(BOXES)[2:])
        # ~65% have digitised registry geometry (a small square around the point)
        has_geom = rng.random() < 0.65
        d = 0.004  # ~350 m square
        geo = {
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [round(lon - d, 6), round(lat - d, 6)],
                    [round(lon + d, 6), round(lat - d, 6)],
                    [round(lon + d, 6), round(lat + d, 6)],
                    [round(lon - d, 6), round(lat + d, 6)],
                    [round(lon - d, 6), round(lat - d, 6)],
                ]],
            },
        } if has_geom else None
        owner = rng.choice(FIRST_NAMES) + rng.choice(SURNAMES)
        parcels.append({
            "survey_number": survey,
            "village": village,
            "mandal": village,          # mandal == village seat in this dataset
            "district": district,
            "owner_name": owner,
            "area_ha": ha,
            "tier": TIER_BY_AREA(ha),
            "registry_geometry_available": has_geom,
            "geojson": geo,
        })
    return parcels


def sql(v):
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v).replace("'", "''") + "'"
    return "'" + str(v).replace("'", "''") + "'"


def main():
    parcels = generate_parcels(30)
    values = ",\n  ".join(
        "(" + ", ".join(sql(p[k]) for k in (
            "survey_number", "owner_name", "area_ha", "village", "mandal",
            "district", "tier", "registry_geometry_available", "geojson"
        )) + ")"
        for p in parcels
    )
    query = f"""
    insert into public.land_registry
      (survey_number, owner_name, area_ha, village, mandal, district, tier,
       registry_geometry_available, geojson)
    values {values}
    on conflict (survey_number) do update set
      owner_name = excluded.owner_name,
      area_ha = excluded.area_ha,
      tier = excluded.tier,
      registry_geometry_available = excluded.registry_geometry_available,
      geojson = excluded.geojson;
    """
    run_sql(query)
    rows = run_sql("select count(*) as n from public.land_registry;")
    print(f"land_registry seeded — {rows[0]['n']} parcels present (idempotent upsert)")


if __name__ == "__main__":
    main()
