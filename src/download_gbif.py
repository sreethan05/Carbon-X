import requests, pandas as pd, time, os
from config import DATA

def download_gbif_india(limit=15000):
    url, all_records, offset = "https://api.gbif.org/v1/occurrence/search", [], 0
    while len(all_records) < limit:
        try:
            r = requests.get(url, params={
                "country":"IN","basisOfRecord":"HUMAN_OBSERVATION",
                "hasCoordinate":True,"hasGeospatialIssue":False,
                "limit":300,"offset":offset
            }, timeout=30)
            results = r.json().get("results",[])
            if not results: break
            all_records.extend(results)
            offset += 300
            print(f"Downloaded {len(all_records)}...")
            time.sleep(0.5)
        except Exception as e:
            print(f"Error: {e}"); time.sleep(5)
    df = pd.DataFrame(all_records)
    df = df[["decimalLatitude","decimalLongitude","species"]].dropna()
    os.makedirs(DATA, exist_ok=True)
    df.to_csv(f"{DATA}/gbif_raw_large.csv", index=False)
    print(f"Saved {len(df)} records.")
    return df

if __name__ == "__main__":
    download_gbif_india()