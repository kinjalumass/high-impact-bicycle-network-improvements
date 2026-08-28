import osmnx as ox
import geopandas as gpd

from bcu_analysis.census.assignment import assign_population_to_nodes_by_tract_area

print("Loading graph...")
G = ox.load_graphml("data/Boston_3.graphml")
nodes, edges = ox.graph_to_gdfs(G)

print("Loading tracts...")
tracts = gpd.read_file("data/census/ma_tracts_population.geojson")

print("Filtering to first 5 tracts near graph boundary...")
nodes_m = nodes.to_crs("EPSG:26986")
tracts_m = tracts.to_crs("EPSG:26986")
graph_boundary = nodes_m.geometry.union_all().convex_hull
test_tracts = tracts_m[tracts_m.geometry.intersects(graph_boundary)].head(5).to_crs(tracts.crs)

print("Test tracts:", len(test_tracts))

print("Running assignment on small test...")
nodes_with_pop, allocation = assign_population_to_nodes_by_tract_area(
    nodes,
    test_tracts,
    population_col="population",
    tract_id_col="GEOID",
    projected_crs="EPSG:26986",
    candidate_buffer_m=100,
    tract_filter_method="convex_hull",
)

print("Done.")
print("Allocation rows:", len(allocation))
print("Assigned population:", nodes_with_pop["assigned_population"].sum())

tract_share = allocation.groupby("GEOID")["area_share"].sum()
print(tract_share.describe())
