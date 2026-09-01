import json
import pandas as pd
import geopandas as gpd

TRACT_SHP = "ma_tracts_2024/tl_2024_25_tract.shp"
ACS_JSON = "ma_acs_population_2024.json"
OUTPUT = "ma_tracts_population.geojson"

tracts = gpd.read_file(TRACT_SHP)

with open(ACS_JSON, "r") as f:
    raw = json.load(f)

header = raw[0]
rows = raw[1:]
acs = pd.DataFrame(rows, columns=header)

acs["GEOID"] = acs["state"] + acs["county"] + acs["tract"]
acs["population"] = pd.to_numeric(acs["B01003_001E"], errors="coerce")
acs["tract_name"] = acs["NAME"]

acs = acs[["GEOID", "tract_name", "population"]]

tracts = tracts.merge(acs, on="GEOID", how="left")
tracts = tracts[["GEOID", "tract_name", "population", "geometry"]]

tracts.to_file(OUTPUT, driver="GeoJSON")

print("Saved", OUTPUT)
print(tracts[["GEOID", "tract_name", "population"]].head())
print("Missing population rows:", tracts["population"].isna().sum())
