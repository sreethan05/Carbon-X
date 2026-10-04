import ee, pandas as pd, time, os
from config import DATA, GEE_PROJECT

ee.Initialize(project=GEE_PROJECT)

def get_features(lat, lon, buffer=1500):
    pt  = ee.Geometry.Point([lon, lat]).buffer(buffer)
    col = (ee.ImageCollection("COPERNICUS/S2_SR")
           .filterBounds(pt)
           .filterDate("2023-01-01","2023-12-31")
           .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE",20)))
    s2  = col.median()
    B4, B8, B3, B11 = s2.select("B4"), s2.select("B8"), s2.select("B3"), s2.select("B11")
    stack = (s2.normalizedDifference(["B8","B4"]).rename("NDVI")
              .addBands(s2.normalizedDifference(["B3","B11"]).rename("NDWI"))
              .addBands(s2.expression("((NIR-RED)/(NIR+RED+0.5))*1.5",
                        {"NIR":B8,"RED":B4}).rename("SAVI"))
              .addBands(B4.rename("B4"))
              .addBands(B8.rename("B8"))
              .addBands(B11.rename("B11"))
              .addBands(col.map(lambda i: i.normalizedDifference(["B8","B4"]))
                        .reduce(ee.Reducer.stdDev()).rename("NDVI_STD"))
              .addBands(col.map(lambda i: i.select("B8"))
                        .reduce(ee.Reducer.variance()).rename("B8_VAR")))
    return stack.reduceRegion(
        reducer=ee.Reducer.mean(), geometry=pt, scale=10, maxPixels=1e9
    ).getInfo()

def extract_all():
    richness   = pd.read_csv(f"{DATA}/species_richness_weighted.csv")
    ckpt_path  = f"{DATA}/features_v2_checkpoint.csv"
    out_path   = f"{DATA}/satellite_features_v2.csv"
    done_df    = pd.read_csv(ckpt_path) if os.path.exists(ckpt_path) else pd.DataFrame()
    done_coords= set(zip(done_df.get("latitude",[]), done_df.get("longitude",[])))
    new_rows, failed = [], 0
    for idx, row in richness.iterrows():
        coord = (row["latitude"], row["longitude"])
        if coord in done_coords: continue
        try:
            f = get_features(row["latitude"], row["longitude"])
            if not f or all(v is None for v in f.values()):
                failed += 1; continue
            f.update({"latitude":row["latitude"],"longitude":row["longitude"],
                      "species_count":row["species_count"]})
            new_rows.append(f)
            if len(new_rows) % 50 == 0:
                pd.concat([done_df, pd.DataFrame(new_rows)],
                          ignore_index=True).to_csv(ckpt_path, index=False)
                print(f"Checkpoint: {len(done_df)+len(new_rows)} | failed: {failed}")
                time.sleep(2)
        except Exception as e:
            print(f"Row {idx}: {e}"); failed += 1; time.sleep(3)
    final = pd.concat([done_df, pd.DataFrame(new_rows)], ignore_index=True)
    final.to_csv(out_path, index=False)
    print(f"Done. {len(final)} rows. {failed} failed.")

if __name__ == "__main__":
    extract_all()