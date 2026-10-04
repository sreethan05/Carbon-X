"""Ingest eBird species richness data into ground_truth_samples.

eBird (Cornell Lab) — far denser and better-structured than GBIF for India.
Requires eBird API key (free from https://ebird.org/api/keygen).

Strategy:
- Pull recent complete checklists for India (last 2 years)
- Aggregate to 0.02° grid cells (~2 km) to match model grid
- Count unique species per cell (species richness)
- Upsert to ground_truth_samples with source="ebird", measured_species_count
- Idempotent: re-runs update existing lat/lon grid cells

Usage:
    export EBIRD_API_KEY=your_key
    python scripts/ingest_ebird.py [--days-back 730] [--min-checklists 10]
"""
import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import date, timedelta
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from seed_marketplace_data import run_sql  # noqa: E402


# ─── India bounding box ───
INDIA_BBOX = [68.0, 6.0, 98.0, 38.0]  # [min_lon, min_lat, max_lon, max_lat]
GRID_RESOLUTION = 0.02  # degrees (~2 km at equator)


def get_ebird_key():
    """Get eBird API key from environment."""
    key = os.getenv("EBIRD_API_KEY", "").strip()
    if not key:
        print("ERROR: EBIRD_API_KEY environment variable not set")
        print("Get a free key from https://ebird.org/api/keygen")
        sys.exit(1)
    return key


def grid_cell(lat, lon, resolution=GRID_RESOLUTION):
    """Snap lat/lon to grid cell center."""
    cell_lat = round(round(lat / resolution) * resolution, 4)
    cell_lon = round(round(lon / resolution) * resolution, 4)
    return cell_lat, cell_lon


def fetch_ebird_checklists(api_key, bbox, back_days=730, max_results=10000):
    """Fetch recent checklists for India region via eBird API.
    
    Uses the eBird API v2: https://documenter.getpostman.com/view/664302/S1ENwy59
    """
    import urllib.request
    import urllib.parse
    
    min_lon, min_lat, max_lon, max_lat = bbox
    
    # eBird hotspot search within bbox
    # Note: eBird API doesn't have a direct bbox search for checklists
    # We'll use the region-based approach (India = "IN") and filter by date
    # For more precise bbox, we'd need to iterate hotspots
    
    base_url = "https://api.ebird.org/v2/data/obs/IN/recent"
    params = {
        "back": min(back_days, 30),  # API max is 30 days per call
        "maxResults": max_results,
        "detail": "full",
        "includeProvisional": "true",
        "hotspot": "false",
    }
    
    all_observations = []
    days_fetched = 0
    batch_size = 30
    
    while days_fetched < back_days:
        params["back"] = batch_size
        url = base_url + "?" + urllib.parse.urlencode(params)
        
        req = urllib.request.Request(url)
        req.add_header("X-eBirdApiToken", api_key)
        
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                data = json.loads(response.read().decode())
            
            if not data:
                break
                
            all_observations.extend(data)
            days_fetched += batch_size
            print(f"  Fetched {len(data)} observations (total: {len(all_observations)})")
            
            # Rate limiting: eBird allows 100 requests/minute
            time.sleep(0.6)
            
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print("Rate limited, waiting 60s...")
                time.sleep(60)
                continue
            print(f"HTTP error: {e.code} - {e.read().decode()}")
            break
        except Exception as e:
            print(f"Error fetching eBird data: {e}")
            break
    
    return all_observations


def fetch_ebird_hotspots(api_key, bbox):
    """Fetch all hotspots within India bbox for more targeted queries."""
    import urllib.request
    import urllib.parse
    
    min_lon, min_lat, max_lon, max_lat = bbox
    
    # eBird hotspot search by bbox
    url = f"https://api.ebird.org/v2/ref/hotspot/bbox?lat={min_lat}&lng={min_lon}&dist=1000&fmt=json"
    
    req = urllib.request.Request(url)
    req.add_header("X-eBirdApiToken", api_key)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            hotspots = json.loads(response.read().decode())
        print(f"Found {len(hotspots)} hotspots in region")
        return hotspots
    except Exception as e:
        print(f"Error fetching hotspots: {e}")
        return []


def fetch_checklists_for_hotspot(api_key, hotspot_id, back_days=730):
    """Fetch checklists for a specific hotspot."""
    import urllib.request
    import urllib.parse
    
    url = f"https://api.ebird.org/v2/product/lists/{hotspot_id}"
    params = {"maxResults": 1000}
    
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params))
    req.add_header("X-eBirdApiToken", api_key)
    
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())
        return data
    except Exception as e:
        print(f"  Error fetching checklists for {hotspot_id}: {e}")
        return []


def process_ebird_data(observations, hotspots=None):
    """Aggregate eBird observations to grid cells with species richness."""
    
    # Group by grid cell
    cell_species = defaultdict(set)
    cell_checklists = defaultdict(set)
    cell_observations = defaultdict(int)
    
    for obs in observations:
        lat = obs.get("lat")
        lon = obs.get("lng")
        species_code = obs.get("speciesCode")
        checklist_id = obs.get("subId")
        
        if not all([lat, lon, species_code, checklist_id]):
            continue
        
        # Filter to India bbox
        if not (INDIA_BBOX[1] <= lat <= INDIA_BBOX[3] and 
                INDIA_BBOX[0] <= lon <= INDIA_BBOX[2]):
            continue
        
        cell_lat, cell_lon = grid_cell(lat, lon)
        cell_key = (cell_lat, cell_lon)
        
        cell_species[cell_key].add(species_code)
        cell_checklists[cell_key].add(checklist_id)
        cell_observations[cell_key] += 1
    
    # Build grid cells with sufficient data
    cells = []
    for (cell_lat, cell_lon), species_set in cell_species.items():
        n_checklists = len(cell_checklists[(cell_lat, cell_lon)])
        n_obs = cell_observations[(cell_lat, cell_lon)]
        n_species = len(species_set)
        
        # Only keep cells with enough sampling effort
        if n_checklists >= 3 and n_obs >= 10:
            cells.append({
                "latitude": cell_lat,
                "longitude": cell_lon,
                "measured_species_count": n_species,
                "n_checklists": n_checklists,
                "n_observations": n_obs,
            })
    
    print(f"Processed {len(cells)} grid cells with ≥3 checklists and ≥10 observations")
    return cells


def sql_val(v):
    """Convert Python value to SQL literal."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, (dict, list)):
        return "'" + json.dumps(v).replace("'", "''") + "'"
    return "'" + str(v).replace("'", "''") + "'"


def upsert_to_ground_truth(cells, batch_size=500):
    """Upsert eBird grid cells to ground_truth_samples."""
    if not cells:
        print("No cells to upsert")
        return 0
    
    print(f"Upserting {len(cells)} eBird grid cells...")
    total = 0
    
    for i in range(0, len(cells), batch_size):
        batch = cells[i:i + batch_size]
        values = []
        for c in batch:
            notes = json.dumps({
                "n_checklists": c["n_checklists"],
                "n_observations": c["n_observations"],
                "source_detail": "eBird complete checklists aggregated to 0.02° grid"
            })
            values.append(
                f"({sql_val(c['longitude'])}, {sql_val(c['latitude'])}, "
                f"{sql_val(None)}, {sql_val(c['measured_species_count'])}, "
                f"{sql_val('ebird')}, {sql_val(date.today().isoformat())}, "
                f"{sql_val(notes)})"
            )
        
        values_str = ",\n  ".join(values)
        query = f"""
        insert into public.ground_truth_samples
          (longitude, latitude, measured_soc_tco2e_ha, measured_species_count,
           source, measured_at, notes)
        values {values_str}
        on conflict (longitude, latitude) do update set
          measured_species_count = excluded.measured_species_count,
          source = excluded.source,
          measured_at = excluded.measured_at,
          notes = excluded.notes;
        """
        try:
            run_sql(query)
            total += len(batch)
            print(f"  Batch {i//batch_size + 1}: {len(batch)} upserted")
        except Exception as e:
            print(f"  Batch {i//batch_size + 1} failed: {e}")
    
    return total


def main():
    parser = argparse.ArgumentParser(description="Ingest eBird species richness data")
    parser.add_argument("--days-back", type=int, default=730,
                        help="Days of historical data to fetch (default: 730 = 2 years)")
    parser.add_argument("--min-checklists", type=int, default=3,
                        help="Minimum checklists per grid cell (default: 3)")
    args = parser.parse_args()
    
    print("=" * 60)
    print("EBIRD SPECIES RICHNESS INGESTION")
    print("=" * 60)
    
    api_key = get_ebird_key()
    
    # Strategy: Use hotspot-based fetching for better coverage
    print("Fetching hotspots in India...")
    hotspots = fetch_ebird_hotspots(api_key, INDIA_BBOX)
    
    if not hotspots:
        print("No hotspots found, falling back to region search...")
        observations = fetch_ebird_checklists(api_key, INDIA_BBOX, args.days_back)
    else:
        # Fetch checklists from top hotspots (most active)
        hotspot_ids = [h["locId"] for h in hotspots[:200]]  # Top 200 hotspots
        all_observations = []
        
        for i, hid in enumerate(hotspot_ids):
            print(f"  [{i+1}/{len(hotspot_ids)}] Fetching checklists for {hid}...")
            checklists = fetch_checklists_for_hotspot(api_key, hid, args.days_back)
            all_observations.extend(checklists)
            time.sleep(0.3)  # Rate limit
        
        observations = all_observations
    
    if not observations:
        print("No observations retrieved")
        sys.exit(1)
    
    print(f"Total observations: {len(observations)}")
    
    # Process to grid cells
    cells = process_ebird_data(observations)
    
    if not cells:
        print("No valid grid cells after filtering")
        sys.exit(1)
    
    # Upsert
    upserted = upsert_to_ground_truth(cells)
    
    # Verify
    count_rows = run_sql("select count(*) as n from public.ground_truth_samples where source = 'ebird';")
    print(f"\nDone. {upserted} eBird grid cells upserted.")
    print(f"Total eBird samples in DB: {count_rows[0]['n']}")


if __name__ == "__main__":
    main()