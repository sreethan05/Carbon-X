import pandas as pd
from config import DATA, GRID_SIZE

def aggregate():
    df = pd.read_csv(f"{DATA}/gbif_raw_large.csv")
    df["lat_grid"] = (df["decimalLatitude"]  / GRID_SIZE).round() * GRID_SIZE
    df["lon_grid"] = (df["decimalLongitude"] / GRID_SIZE).round() * GRID_SIZE
    richness = df.groupby(["lat_grid","lon_grid"]).agg(
        species_count    =("species","nunique"),
        observation_count=("species","count")
    ).reset_index()
    richness.columns = ["latitude","longitude","species_count","observation_count"]
    richness = richness[richness["species_count"] > 2]
    richness.to_csv(f"{DATA}/species_richness_weighted.csv", index=False)
    print(f"Grid cells: {len(richness)}")
    return richness

if __name__ == "__main__":
    aggregate()