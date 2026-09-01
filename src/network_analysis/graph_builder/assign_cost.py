import os

import numpy as np
import pandas as pd
import osmnx as ox

from network_analysis.graph_builder import lts_functions as lts

# LTS 0 means "no bike access" and NaN means LTS could not be determined.
# Both are given a large penalty so routing avoids them when any alternative
# exists, without making them strictly impassable.
NO_ACCESS_WEIGHT = 100.0


def lts_edges(region, gdf_edges, data_dir):
    '''
    Calculate the LTS for all edges
    '''
    filepathAll = f"{data_dir}/processed/osm/{region}_all_lts.csv"
    os.makedirs(os.path.dirname(filepathAll), exist_ok=True)

    # Load the configuration files to caluclate ratings
    rating_dict = lts.read_rating()
    tables = lts.read_tables()

    # Process features where side is more important than direction
    gdf_edges = lts.parking_present(gdf_edges, rating_dict)

    # Convert schema to focus on direction
    gdf_edges = lts.convert_both_tag(gdf_edges)

    # Process bike lanes
    gdf_edges = lts.parse_lanes(gdf_edges)

    # Process non-directional data
    gdf_edges = lts.get_prevailing_speed(gdf_edges, rating_dict)
    gdf_edges = lts.get_lanes(gdf_edges, default_lanes=2)
    gdf_edges = lts.get_centerlines(gdf_edges, rating_dict)

    gdf_edges = lts.width_ft(gdf_edges)
    
    gdf_edges = lts.define_narrow_wide(gdf_edges)
    gdf_edges = lts.define_adt(gdf_edges, rating_dict)

    gdf_edges = lts.LTS_separation(gdf_edges)

    lts.column_value_counts(gdf_edges) # Useful for debugging
    all_lts = lts.calculate_lts(gdf_edges, tables)

    gdf_edges = lts.define_zoom(gdf_edges, rating_dict)

    # print(f'{all_lts['LTS'].unique()=}')
    
    # print(f'Saving LTS for {region}')
    all_lts.to_csv(filepathAll)
    # https://geopandas.org/en/stable/docs/reference/api/geopandas.GeoDataFrame.to_file.html

    return all_lts

def build_cost_graph(region_name, cost_scenario, data_dir):
    raw_graph_path = f"{data_dir}/raw/osm/{region_name}_raw.graphml"
    lts_path = f"{data_dir}/processed/osm/{region_name}_all_lts.csv"
    cost_params_path = f"{os.path.dirname(__file__)}/config/cost_parameters.csv"

    # Each row of cost_parameters.csv is one scenario: a length multiplier per
    # LTS level, describing how strongly that rider group avoids the stress.
    print(f"Loading cost scenario {cost_scenario}")
    cost_params = pd.read_csv(cost_params_path).set_index('scenario_id')
    if int(cost_scenario) not in cost_params.index:
        raise ValueError(
            f"Cost scenario {cost_scenario} not in {cost_params_path}. "
            f"Available scenarios: {sorted(cost_params.index)}"
        )
    scenario = cost_params.loc[int(cost_scenario)]
    stress_weights = {
        level: float(scenario[f'lts{level}_weight']) for level in (1, 2, 3, 4)
    }
    print(f"Scenario {cost_scenario} ({scenario['scenario_description']}) "
          f"weights: {stress_weights}")

    def stress_weight(lts):
        """Return the length multiplier for a given LTS value."""
        if lts is None or (isinstance(lts, float) and np.isnan(lts)):
            return NO_ACCESS_WEIGHT
        return stress_weights.get(int(lts), NO_ACCESS_WEIGHT)

    print(f"Loading graph for {region_name}")
    G = ox.load_graphml(raw_graph_path)

    print(f"Loading LTS data for {region_name}")
    lts_df = pd.read_csv(lts_path, usecols=['u', 'v', 'key', 'LTS'],
                         low_memory=False)

    # Map each (u, v, key) edge to its LTS for fast lookup against the graph.
    lts_by_edge = {
        (int(row.u), int(row.v), int(row.key)): row.LTS
        for row in lts_df.itertuples(index=False)
    }

    matched = 0
    missing = 0
    for u, v, k, data in G.edges(keys=True, data=True):
        lts = lts_by_edge.get((u, v, k))
        if lts is None:
            missing += 1
        else:
            matched += 1

        length = float(data.get('length', 0.0))
        data['LTS'] = '' if lts is None or pd.isna(lts) else int(lts)
        data['cost'] = length * stress_weight(lts)

    print(f"Matched LTS for {matched} edges, {missing} edges had no LTS row")

    out_path = f"{data_dir}/output/cost_scenarios/cost_scenario_{cost_scenario}/{region_name}_cost_scenario_{cost_scenario}.graphml"
    ox.save_graphml(G, out_path)
    print(f"Saved cost graph to {out_path}")

    return G


def simplify_cost_graph(region_name, cost_scenario, data_dir):
    """
    Simplify the cost graph, merging chains of edges between intersections
    into single edges. The merged edge's "cost" (and "length") is the sum of
    the costs of the constituent edges that were merged, and "max_lts" is the
    worst (max) stress level along the merged edge.
    """
    in_path = f"{data_dir}/output/cost_scenarios/cost_scenario_{cost_scenario}/{region_name}_cost_scenario_{cost_scenario}.graphml"
    if not os.path.exists(in_path):
        raise FileNotFoundError(f"Cost graph not found: {in_path}")
    print(f"Loading cost graph for {region_name}")
    # cost is a custom attribute, so load_graphml won't coerce it for us.
    G = ox.load_graphml(in_path, edge_dtypes={'cost': float})

    def max_lts(values):
        """
        Worst stress level among merged segments; ignores unknowns.

        LTS 0 means "no bike access" and outranks 1-4, so a chain containing
        any LTS 0 segment is reported as 0 rather than the max of the rest.
        """
        levels = []
        for v in values:
            if v is None or v == '' or pd.isna(v):
                continue
            try:
                level = int(float(v))
            except (ValueError, TypeError):
                continue
            if level == 0:
                return 0
            levels.append(level)
        return max(levels) if levels else ''

    # Seed max_lts from each edge's LTS so the aggregation has it to merge.
    for _, _, data in G.edges(data=True):
        data['max_lts'] = data.get('LTS', '')

    print(f"Simplifying graph ({G.number_of_edges()} edges)")
    # Sum cost and length across the merged segments, and take the worst LTS.
    G_simplified = ox.simplify_graph(
        G,
        edge_attr_aggs={'cost': sum, 'length': sum, 'max_lts': max_lts},
    )
    print(f"Simplified to {G_simplified.number_of_edges()} edges")

    out_path = f"{data_dir}/output/cost_scenarios/cost_scenario_{cost_scenario}/{region_name}_cost_scenario_{cost_scenario}_simplified.graphml"
    ox.save_graphml(G_simplified, out_path)
    print(f"Saved simplified cost graph to {out_path}")

    return G_simplified