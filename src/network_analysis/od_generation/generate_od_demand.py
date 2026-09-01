import argparse
import os

import pandas as pd

from network_analysis.graph_builder.build_cost_graph import CITY_OPTIONS, resolve_area
from network_analysis.od_generation.build_poi_od_pairs import build_poi_od_pairs
from network_analysis.od_generation.lodes_pairs import generate_lodes_pairs
from network_analysis.od_generation.lodes_sampling import sample_lodes_trips

# The LODES home->work commute pipeline is driven by this demand category; every other
# category is handled by the population-weighted POI pipeline.
LODES_CATEGORY = "home_office"

DEFAULT_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "config", "demand_parameters.csv"
)

# Population weights are resolved from the requested study region unless an
# explicit node-level population file is supplied with --pop-geojson-path.
DEFAULT_POP_GEOJSON = None


def load_demand(scenario_id=1, config_path=DEFAULT_CONFIG_PATH):
    """
    Read per-category trip counts for a demand scenario from demand_parameters.csv.

    The config's first column holds the category names (home_office, home_school, ...)
    plus a TOTAL row; each remaining column is a scenario, headed by its scenario id.

    Parameters:
    - scenario_id (int | str): Which scenario column to read.
    - config_path (str): Path to demand_parameters.csv.

    Returns:
    - dict: {category_key: int_count} for categories with a positive count in the
      selected scenario (the TOTAL row and blank/NaN entries are dropped).
    """
    config = pd.read_csv(config_path, dtype=str)
    category_col = config.columns[0]
    scenario_col = str(scenario_id)
    if scenario_col not in config.columns:
        raise ValueError(
            f"scenario_id {scenario_id!r} not found in {config_path}; "
            f"available: {list(config.columns[1:])}"
        )

    counts = {}
    for _, row in config.iterrows():
        category = row[category_col]
        if category == "TOTAL":
            continue
        value = row[scenario_col]
        if pd.isna(value) or str(value).strip() == "":
            continue
        count = int(float(value))
        if count > 0:
            counts[category] = count
    return counts


def main(
    area,
    cost_scenario,
    demand_scenario=1,
    data_dir=None,
    config_path=DEFAULT_CONFIG_PATH,
    pop_geojson_path=DEFAULT_POP_GEOJSON,
    output_path=None,
    random_seed=None,
):
    """
    Run both OD generators for a demand scenario and write a single combined CSV.

    Reads the simplified cost graph built by graph_builder/build_cost_graph.py for the given
    area and cost scenario, then writes its intermediates and combined output under
    ``{data_dir}/output/demand_scenarios/demand_scenario_{demand_scenario}/``. The LODES base
    pairs are the exception: they depend only on the graph, so they live alongside it under
    ``output/cost_scenarios/cost_scenario_{cost_scenario}/``.

    Parameters:
    - area (str): Municipality key or 'greater_boston'; resolved to a region name and town list
      by graph_builder.build_cost_graph.resolve_area, so it matches the graph on disk.
    - cost_scenario (int): Cost scenario id whose simplified graph should be routed on.
    - demand_scenario (int | str): Which scenario column to read from demand_parameters.csv.
    - data_dir (str): Root data directory (the parent of raw/, processed/, output/).
    - config_path (str): Path to demand_parameters.csv.
    - pop_geojson_path (str): Node-level population weights for POI home sampling.
    - output_path (str | None): Override for the combined CSV; derived from the scenario when None.
    - random_seed (int | None): Seed for both the LODES sampler and the POI sampler.

    Returns:
    - pd.DataFrame: columns origin_node, destination_node, category, count.
    """
    if data_dir is None:
        raise ValueError("data_dir is required.")

    region_name, cities = resolve_area(area)

    if pop_geojson_path is None:
        pop_geojson_path = os.path.join(
            data_dir,
            "census_results",
            f"{region_name}_cost_scenario_{cost_scenario}_nodes_with_population_web.geojson",
        )

    if not os.path.exists(pop_geojson_path):
        raise FileNotFoundError(
            f"Population allocation not found: {pop_geojson_path}. "
            "Provide the correct node-level population file with --pop-geojson-path."
        )

    # Destinations.csv tags each row with a bare town name ('Boston'), while CITIES holds
    # full place names ('Boston, Massachusetts').
    towns = [name.split(",")[0].strip() for name, _, _ in cities]

    data_dir = data_dir.rstrip("/")
    cost_dir = f"{data_dir}/output/cost_scenarios/cost_scenario_{cost_scenario}"
    demand_dir = f"{data_dir}/output/demand_scenarios/demand_scenario_{demand_scenario}"

    graph_path = f"{cost_dir}/{region_name}_cost_scenario_{cost_scenario}_simplified.graphml"
    # LODES pairs are a function of the graph alone, so they are cost-scenario scoped and
    # shared by every demand scenario routed on the same graph.
    lodes_pairs_path = f"{cost_dir}/{region_name}_lodes_pairs.csv"
    lodes_sample_path = f"{demand_dir}/{region_name}_lodes_sample_demand_scenario_{demand_scenario}.csv"
    poi_pairs_path = f"{demand_dir}/{region_name}_poi_pairs_demand_scenario_{demand_scenario}.csv"
    if output_path is None:
        output_path = f"{demand_dir}/{region_name}_all_pairs_demand_scenario_{demand_scenario}.csv"

    if not os.path.exists(graph_path):
        raise FileNotFoundError(
            f"Cost graph not found: {graph_path}. Build it first with "
            f"'python src/network_analysis/graph_builder/build_cost_graph.py {cost_scenario} {area} "
            f"--data-dir {data_dir}'."
        )

    counts = load_demand(demand_scenario, config_path=config_path)
    print(f"Region {region_name}, cost scenario {cost_scenario}, demand scenario {demand_scenario}")
    print(f"Demand scenario {demand_scenario}: {counts}")

    frames = []

    # LODES commute trips (home_office): build the base pairs then draw the scenario's
    # number of trips, tagging them with the category.
    lodes_count = counts.get(LODES_CATEGORY)
    if lodes_count:
        generate_lodes_pairs(
            graph_path=graph_path,
            output_path=lodes_pairs_path,
        )
        lodes = sample_lodes_trips(
            pairs_path=lodes_pairs_path,
            graph_path=graph_path,
            output_path=lodes_sample_path,
            n_trips=lodes_count,
            random_seed=random_seed,
        )
        lodes = lodes[["origin_node", "destination_node", "count"]].copy()
        lodes["category"] = LODES_CATEGORY
        frames.append(lodes)

    # POI trips for every other category.
    poi_counts = {k: v for k, v in counts.items() if k != LODES_CATEGORY}
    if poi_counts:
        poi = build_poi_od_pairs(
            graph_path=graph_path,
            pop_geojson_path=pop_geojson_path,
            destinations_path=f"{data_dir}/processed/osm/Destinations.csv",
            towns=towns,
            category_counts=poi_counts,
            output_path=poi_pairs_path,
            random_seed=random_seed,
        )
        if not poi.empty:
            frames.append(poi)

    if not frames:
        raise ValueError(
            f"No trips generated for demand scenario {demand_scenario}. Column "
            f"{demand_scenario!r} exists in {config_path} but has no positive counts - "
            f"check that it is not blank."
        )

    combined = pd.concat(frames, ignore_index=True)
    combined = combined[["origin_node", "destination_node", "category", "count"]]

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    combined.to_csv(output_path, index=False)
    print(f"Wrote {len(combined):,} combined OD pairs to {output_path}")
    print(combined.groupby("category")["count"].sum())
    return combined


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Combine LODES + POI OD pairs for a demand scenario.")
    parser.add_argument(
        "cost_scenario",
        type=int,
        help="Cost scenario id whose simplified graph should be routed on",
    )
    parser.add_argument(
        "area",
        choices=CITY_OPTIONS,
        help="Municipality to generate demand for, or 'greater_boston' for all of them combined.",
    )
    parser.add_argument(
        "--demand-scenario",
        type=int,
        default=1,
        help="Scenario column in demand_parameters.csv",
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Root data directory",
    )
    parser.add_argument("--config-path", default=DEFAULT_CONFIG_PATH)
    parser.add_argument(
        "--pop-geojson-path",
        default=DEFAULT_POP_GEOJSON,
        help="Node-level population GeoJSON used to weight POI home sampling",
    )
    parser.add_argument(
        "--output-path",
        default=None,
        help="Override the derived path for the combined OD CSV",
    )
    parser.add_argument("--random-seed", type=int, default=None)
    args = parser.parse_args()
    main(
        area=args.area,
        cost_scenario=args.cost_scenario,
        demand_scenario=args.demand_scenario,
        data_dir=args.data_dir,
        config_path=args.config_path,
        pop_geojson_path=args.pop_geojson_path,
        output_path=args.output_path,
        random_seed=args.random_seed,
    )
