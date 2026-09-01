import pandas as pd
import geopandas as gpd
import folium
from folium.plugins import MarkerCluster

TRACT_PATH = "data/census/ma_tracts_population.geojson"
NODES_WEB_PATH = "data/census/Boston_nodes_with_population_web.geojson"
ALLOCATION_PATH = "data/census/Boston_node_tract_allocation.csv"
OUTPUT_MAP = "data/census/Boston_census_assignment_map.html"

print("Loading nodes...")
nodes = gpd.read_file(NODES_WEB_PATH)

print("Loading tracts...")
tracts = gpd.read_file(TRACT_PATH)
tracts["GEOID"] = tracts["GEOID"].astype(str)

print("Loading allocation...")
allocation = pd.read_csv(ALLOCATION_PATH, dtype={"GEOID": str})

assigned_tract_ids = set(allocation["GEOID"].astype(str))
tracts = tracts[tracts["GEOID"].isin(assigned_tract_ids)].copy()
tracts = tracts.to_crs("EPSG:4326")

print("Filtering assigned nodes...")
nodes = nodes[nodes["assigned_population"] > 0].copy()

center_lat = nodes.geometry.y.mean()
center_lon = nodes.geometry.x.mean()

print("Creating map...")
m = folium.Map(
    location=[center_lat, center_lon],
    zoom_start=12,
    tiles="cartodbpositron",
)

print("Adding census tracts...")
folium.GeoJson(
    tracts,
    name="Assigned census tracts",
    style_function=lambda feature: {
        "fillColor": "transparent",
        "color": "black",
        "weight": 1,
        "fillOpacity": 0.0,
    },
    tooltip=folium.GeoJsonTooltip(
        fields=["GEOID", "population"],
        aliases=["Tract GEOID", "Tract population"],
        localize=True,
    ),
).add_to(m)

print("Adding assigned population nodes...")

# Keep the map readable by showing all nodes as small points, and large assignments as emphasized points.
low_pop = nodes[nodes["assigned_population"] <= 50].copy()
high_pop = nodes[nodes["assigned_population"] > 50].copy()

# Small assigned nodes.
for _, row in low_pop.iterrows():
    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x],
        radius=1.5,
        weight=0,
        fill=True,
        fill_opacity=0.35,
        popup=(f"Node ID: {row.get('node_id', '')}<br>Assigned population: {row['assigned_population']:.4f}"),
    ).add_to(m)

# Larger assigned nodes, clustered for usability.
cluster = MarkerCluster(name="High assigned population nodes").add_to(m)

for _, row in high_pop.iterrows():
    pop = float(row["assigned_population"])

    radius = min(18, max(4, pop**0.5 / 2))

    folium.CircleMarker(
        location=[row.geometry.y, row.geometry.x],
        radius=radius,
        weight=1,
        fill=True,
        fill_opacity=0.65,
        popup=(f"Node ID: {row.get('node_id', '')}<br>Assigned population: {pop:.2f}"),
    ).add_to(cluster)

print("Adding top 25 highest-population nodes...")
top_nodes = nodes.sort_values("assigned_population", ascending=False).head(25)

for _, row in top_nodes.iterrows():
    pop = float(row["assigned_population"])

    folium.Marker(
        location=[row.geometry.y, row.geometry.x],
        popup=(f"<b>Top assigned node</b><br>Node ID: {row.get('node_id', '')}<br>Assigned population: {pop:.2f}"),
        tooltip=f"{pop:.1f} people",
    ).add_to(m)

folium.LayerControl().add_to(m)

print("Saving map...")
m.save(OUTPUT_MAP)

print("Done.")
print("Saved:", OUTPUT_MAP)
print("Assigned nodes shown:", len(nodes))
print("Assigned tracts shown:", len(tracts))
print("Top node population:", nodes["assigned_population"].max())
