import requests, pandas as pd, time, os

try:
    from config import DATA
except ImportError:
    from src.config import DATA

def download_gbif_india(limit=15000):
    url, all_records, offset = "https://api.gbif.org/v1/occurrence/search", [], 0
    consecutive_errors = 0
    while len(all_records) < limit and consecutive_errors < 5:
        try:
            r = requests.get(url, params={
                "country": "IN", "basisOfRecord": "HUMAN_OBSERVATION",
                "hasCoordinate": True, "hasGeospatialIssue": False,
                "limit": 300, "offset": offset
            }, timeout=30)
            r.raise_for_status()
            results = r.json().get("results", [])
            if not results:
                break
            all_records.extend(results)
            offset += 300
            consecutive_errors = 0
            print(f"Downloaded {len(all_records)}...")
            time.sleep(0.5)
        except Exception as e:
            consecutive_errors += 1
            print(f"Error ({consecutive_errors}/5): {e}")
            time.sleep(5)
    if not all_records:
        print("No records retrieved.")
        return pd.DataFrame(columns=["decimalLatitude", "decimalLongitude", "species"])
    df = pd.DataFrame(all_records)
    cols = [c for c in ["decimalLatitude", "decimalLongitude", "species"] if c in df.columns]
    if len(cols) == 3:
        df = df[cols].dropna()
    else:
        df = pd.DataFrame(columns=["decimalLatitude", "decimalLongitude", "species"])
    os.makedirs(DATA, exist_ok=True)
    out_path = os.path.join(DATA, "gbif_raw_large.csv")
    df.to_csv(out_path, index=False)
    print(f"Saved {len(df)} records to {out_path}.")
    return df

if __name__ == "__main__":
    download_gbif_india()