import os

import geopandas as gpd
import osmnx as ox
from bcu_analysis.od_generation.lodes_io import read_lodes_data, read_crosswalk

def generate_lodes_pairs(
    graph_path,
    output_path,
    year=2023,
    geographic_crs="EPSG:4326",
    projected_crs="EPSG:26986",
    maximum_snap_distance_m=500,
):
    #Load and project graph
    G = ox.load_graphml(graph_path)
    G_proj = ox.project_graph(G, to_crs=projected_crs)

    # Download and format MA OD data
    od = read_lodes_data("od", "ma", None, "JT01", year)
    od["h_geocode"] = od["h_geocode"].astype(str).str.zfill(15)
    od["w_geocode"] = od["w_geocode"].astype(str).str.zfill(15)

    print(f"Massachusetts OD pairs: {len(od):,}")
    print(f"Represented primary jobs: {od['S000'].sum():,}")

    #Load crosswalk
    crosswalk = read_crosswalk("ma", cols=["blklatdd", "blklondd"])

    # Align block IDs with the zero-padded 15-char geocodes used in the OD data
    crosswalk["tabblk2020"] = crosswalk["tabblk2020"].astype(str).str.zfill(15)

    # Drop blocks with missing coordinates before building geometry
    n_blocks = len(crosswalk)
    crosswalk = crosswalk.dropna(subset=["blklatdd", "blklondd"]).copy()
    if len(crosswalk) < n_blocks:
        print(f"Dropped {n_blocks - len(crosswalk):,} blocks with missing coordinates")

    # Convert Crosswalk to GeoDataFrame and project CRS
    crosswalk = gpd.GeoDataFrame(
        crosswalk,
        geometry=gpd.points_from_xy(
            x=crosswalk["blklondd"], y=crosswalk["blklatdd"], crs=geographic_crs
        ),
    )
    crosswalk = crosswalk.to_crs(projected_crs)

    #Snap to graph
    nearest_nodes, nearest_distances = ox.distance.nearest_nodes(
        G_proj,
        X=crosswalk.geometry.x.to_numpy(),
        Y=crosswalk.geometry.y.to_numpy(),
        return_dist=True,
    )

    crosswalk["graph_node"] = nearest_nodes
    crosswalk["snap_distance_m"] = nearest_distances

    #Filter by distance
    graph_blocks = crosswalk[
        crosswalk["snap_distance_m"]
        <= maximum_snap_distance_m
    ].copy()

    print(
        f"Blocks within {maximum_snap_distance_m} m of the graph: "
        f"{len(graph_blocks):,} of {len(crosswalk):,}"
    )

    graph_block_ids = set(graph_blocks["tabblk2020"])

    #Filter OD pairs
    od_graph_region = od[
        od["h_geocode"].isin(graph_block_ids)
        & od["w_geocode"].isin(graph_block_ids)
    ].copy()

    #Save a dataframe of trips
    node_lookup = graph_blocks[["tabblk2020", "graph_node"]]

    origin_lookup = node_lookup.rename(
        columns={
            "tabblk2020": "h_geocode",
            "graph_node": "origin_node",
        }
    )

    destination_lookup = node_lookup.rename(
        columns={
            "tabblk2020": "w_geocode",
            "graph_node": "destination_node",
        }
    )

    trip_pairs = (
        od_graph_region
        .merge(origin_lookup, on="h_geocode")
        .merge(destination_lookup, on="w_geocode")
        .groupby(
            ["origin_node", "destination_node"],
            as_index=False,
        )["S000"]
        .sum()
        .rename(columns={"S000": "employees"})
    )

    #Save to csv
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    trip_pairs.to_csv(output_path, index=False)