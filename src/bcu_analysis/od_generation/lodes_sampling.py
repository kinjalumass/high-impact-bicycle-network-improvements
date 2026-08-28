import os

import matplotlib.pyplot as plt
import numpy as np
import osmnx as ox
import pandas as pd
from scipy.stats import lognorm


def sample_lodes_trips(
    pairs_path,
    graph_path,
    output_path,
    n_trips=10000,
    lognormal_mu=0.3551,
    lognormal_sigma=0.7899,
    projected_crs="EPSG:26986",
    random_seed=None,
):
    """
    Randomly sample OD trips, favoring shorter trips and OD pairs used by more employees.

    Each OD pair is assigned a selection weight of:

        weight = employees * lognormal_pdf(straight_line_length_miles)

    where the lognormal density (parameterized in miles) acts as a distance-decay
    term favoring the shorter trips people are more likely to bike. Trips are then
    drawn with replacement in proportion to these weights.

    Parameters:
    - pairs_path (str): CSV of OD pairs with columns origin_node, destination_node, employees.
    - graph_path (str): GraphML used to look up node coordinates for distances.
    - output_path (str): Where to write the sampled trips.
    - n_trips (int): Number of trips to draw (with replacement).
    - lognormal_mu (float): Mean of the underlying normal (log-miles) for the trip-length distribution.
    - lognormal_sigma (float): Std. dev. of the underlying normal (log-miles).
    - projected_crs (str): Metric CRS used to compute straight-line distances.
    - random_seed (int | None): Seed for reproducible sampling.

    Returns:
    - pd.DataFrame: The sampled trips with their computed length and weight.
    """
    pairs = pd.read_csv(pairs_path)
    print(f"OD pairs loaded: {len(pairs):,}")
    print(f"Represented trips (employees): {pairs['employees'].sum():,}")

    # Load graph and project to a metric CRS so distances are in meters
    G = ox.load_graphml(graph_path)
    G_proj = ox.project_graph(G, to_crs=projected_crs)

    # Node -> (x, y) coordinate lookup in projected meters
    node_x = {node: data["x"] for node, data in G_proj.nodes(data=True)}
    node_y = {node: data["y"] for node, data in G_proj.nodes(data=True)}

    # Drop pairs whose endpoints are not present in the graph
    n_pairs = len(pairs)
    pairs = pairs[
        pairs["origin_node"].isin(node_x) & pairs["destination_node"].isin(node_x)
    ].copy()
    if len(pairs) < n_pairs:
        print(f"Dropped {n_pairs - len(pairs):,} pairs with nodes missing from the graph")

    # Straight-line distance between endpoints, meters -> miles
    ox_m = pairs["origin_node"].map(node_x).to_numpy()
    oy_m = pairs["origin_node"].map(node_y).to_numpy()
    dx_m = pairs["destination_node"].map(node_x).to_numpy()
    dy_m = pairs["destination_node"].map(node_y).to_numpy()

    distance_m = np.hypot(dx_m - ox_m, dy_m - oy_m)
    pairs["length_miles"] = distance_m / 1609.344

    # Combined selection weight: employees x lognormal density of the trip length
    density = lognorm.pdf(
        pairs["length_miles"].to_numpy(),
        s=lognormal_sigma,
        scale=np.exp(lognormal_mu),
    )
    pairs["weight"] = pairs["employees"].to_numpy() * density

    # Guard against pairs with zero/degenerate weight (e.g. length 0)
    total_weight = pairs["weight"].sum()
    if total_weight <= 0:
        raise ValueError("All selection weights are zero; check distances and lognormal params.")

    # Draw n_trips selections with replacement in proportion to weight. A
    # multinomial draw is equivalent to n independent weighted draws, and gives
    # the per-pair selection count directly without materializing duplicate rows.
    rng = np.random.default_rng(random_seed)
    probs = pairs["weight"].to_numpy() / total_weight
    pairs["count"] = rng.multinomial(n_trips, probs)

    # Keep only pairs that were selected at least once
    sample = pairs[pairs["count"] > 0].reset_index(drop=True)

    print(f"Sampled {n_trips:,} trips (with replacement)")
    print(f"Unique OD pairs selected: {len(sample):,}")
    weighted_mean = np.average(sample["length_miles"], weights=sample["count"])
    print(f"Mean sampled trip length: {weighted_mean:.2f} miles")

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sample.to_csv(output_path, index=False)
    return sample
