import os
import pandas as pd

try:
    from config import DATA, GRID_SIZE
except ImportError:
    from src.config import DATA, GRID_SIZE

def aggregate():
    csv_in = os.path.join(DATA, "gbif_raw_large.csv")
    if not os.path.exists(csv_in):
        print(f"Error: {csv_in} not found. Run download_gbif.py first.")
        return pd.DataFrame(columns=["latitude", "longitude", "species_count", "observation_count"])
    df = pd.read_csv(csv_in)
    df["lat_grid"] = ((df["decimalLatitude"]  / GRID_SIZE).round() * GRID_SIZE).round(6)
    df["lon_grid"] = ((df["decimalLongitude"] / GRID_SIZE).round() * GRID_SIZE).round(6)
    richness = df.groupby(["lat_grid", "lon_grid"]).agg(
        species_count    =("species", "nunique"),
        observation_count=("species", "count")
    ).reset_index()
    richness.columns = ["latitude", "longitude", "species_count", "observation_count"]
    richness = richness[richness["species_count"] > 2]
    csv_out = os.path.join(DATA, "species_richness_weighted.csv")
    richness.to_csv(csv_out, index=False)
    print(f"Grid cells: {len(richness)} saved to {csv_out}")
    return richness

if __name__ == "__main__":
    aggregate()