import pandas as pd
import geopandas as gpd
import osmnx as ox
import os
import random
from bcu_analysis.od_generation.poi_destination_choice import choose_destination


# POI categories keyed by the demand-scenario config keys (see config/demand_parameters.csv).
# Each entry lists the `type` values it matches in Destinations.csv, plus the
# destination-choice rule applied to the snapped candidates.
CATEGORY_CONFIGS = {
    "home_school": {"type": ["school"], "rule": "closest_only"},
    "home_healthcare": {"type": ["pharmacy","hospital","doctors","clinic","dentist"], "rule": "closest_only"},
    # Rail only: bus_stop dominates Destinations.csv ~23:1 and would swamp rail access.
    "home_transit": {"type": ["train","subway","light_rail","light_rail;subway"], "rule": "lognormal"},
    "home_store": {"type": ["supermarket","convenience"], "rule": "lognormal"},
    "home_greenspace": {"type": ["greenspace"], "rule": "lognormal"},
}


def build_poi_od_pairs(
    graph_path,
    pop_geojson_path,
    destinations_path,
    towns=None,
    category_counts=None,
    output_path=None,
    random_seed=None,
):
    """
    Generate POI origin-destination pairs with a per-pair draw count.

    Parameters:
    - graph_path (str): GraphML used to snap homes and destinations to nodes.
    - pop_geojson_path (str): Population-weighted node geojson used to sample homes.
    - destinations_path (str): Destinations.csv with columns name, type, latitude,
      longitude, town.
    - towns (list[str] | None): Restrict destinations to these `town` values. All rows
      are used when None.
    - category_counts (dict | None): {category_key: n_homes} for the POI categories to
      draw (keys from CATEGORY_CONFIGS). Categories with no/zero count are skipped.
      Defaults to 100 homes for every category.
    - output_path (str | None): If given, also write the pairs to this CSV.
    - random_seed (int | None): Seed for reproducible home and destination sampling.

    Returns:
    - pd.DataFrame: columns origin_node, destination_node, category, count.
    """
    print("Starting POI Origin-Destination Generation...")

    # sample_homes and choose_destination both draw from the global `random` module, so a
    # single seed here makes the whole POI pipeline reproducible.
    if random_seed is not None:
        random.seed(random_seed)

    if category_counts is None:
        category_counts = {category: 100 for category in CATEGORY_CONFIGS}

    G = ox.load_graphml(graph_path)
    G_proj = ox.project_graph(G, to_crs="EPSG:26986")

    pop_data = gpd.read_file(pop_geojson_path)
    pop_nodes = ox.distance.nearest_nodes(G, X=pop_data.geometry.x, Y=pop_data.geometry.y)

    def sample_homes(num_homes):
        return random.choices(pop_nodes, weights=pop_data['assigned_population'].values, k=num_homes)

    def load_and_snap_from_df(df, trip_types):
        filtered_df = df[df["type"].isin(trip_types)]
        if filtered_df.empty:
            print(f"WARNING: destination list for {trip_types} is empty, skipping")
            return []
        snapped = ox.distance.nearest_nodes(G, X=filtered_df['longitude'].values, Y=filtered_df['latitude'].values)
        # sorted() rather than list() so a seeded run is reproducible.
        return sorted(set(snapped))

    demand = pd.read_csv(destinations_path)

    if towns is not None:
        demand = demand[demand["town"].isin(towns)]
        print(f"Using {len(demand)} destinations in {', '.join(towns)}")

    od_pairs = {}
    for category, config in CATEGORY_CONFIGS.items():
        n_homes = int(category_counts.get(category, 0) or 0)
        if n_homes <= 0:
            continue

        dest_nodes = load_and_snap_from_df(demand, config["type"])
        if not dest_nodes: continue

        home_nodes = sample_homes(n_homes)
        for origin in home_nodes:
            chosen_dest = choose_destination(origin, dest_nodes, G_proj, rule=config["rule"])

            key = (origin, chosen_dest, category)
            if key in od_pairs:
                od_pairs[key]["count"] += 1
            else:
                od_pairs[key] = {
                    "origin_node": origin,
                    "destination_node": chosen_dest,
                    "category": category,
                    "count": 1
                }

    pairs_df = pd.DataFrame(
        list(od_pairs.values()),
        columns=["origin_node", "destination_node", "category", "count"],
    )
    print(f"Generated {len(pairs_df)} POI pairs.")

    if output_path is not None:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        pairs_df.to_csv(output_path, index=False)

    return pairs_df