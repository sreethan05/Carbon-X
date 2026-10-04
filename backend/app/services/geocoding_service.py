"""Village and regional geocoding service using OpenStreetMap / Nominatim.
Converts village, district, and state into latitude and longitude coordinates.
"""

import httpx
from typing import Optional, Dict, Any

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "CarbonX-KYC-Verification/1.0 (contact@carbonx.org)"}


def geocode_village(village: str, district: str = "", state: str = "", country: str = "India") -> Optional[Dict[str, Any]]:
    """
    Geocode village/town name to lat/lon using OpenStreetMap Nominatim.
    Tries specific address first, then falls back to wider administrative areas.
    """
    v_clean = (village or "").strip()
    d_clean = (district or "").strip()
    s_clean = (state or "").strip()

    queries = []
    if v_clean and d_clean and s_clean:
        queries.append(f"{v_clean}, {d_clean}, {s_clean}, {country}")
    if v_clean and s_clean:
        queries.append(f"{v_clean}, {s_clean}, {country}")
    if v_clean and d_clean:
        queries.append(f"{v_clean}, {d_clean}, {country}")
    if d_clean and s_clean:
        queries.append(f"{d_clean}, {s_clean}, {country}")
    if v_clean:
        queries.append(f"{v_clean}, {country}")
    if d_clean:
        queries.append(f"{d_clean}, {country}")

    for query in queries:
        try:
            with httpx.Client(timeout=8.0) as client:
                res = client.get(
                    NOMINATIM_URL,
                    params={"q": query, "format": "json", "limit": 1},
                    headers=HEADERS,
                )
                if res.status_code == 200:
                    data = res.json()
                    if data and len(data) > 0:
                        first = data[0]
                        return {
                            "query": query,
                            "lat": float(first["lat"]),
                            "lon": float(first["lon"]),
                            "display_name": first.get("display_name", query),
                        }
        except Exception as exc:
            print(f"Geocoding error for query '{query}': {exc}")
            continue

    return None
