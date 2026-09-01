"""Generate a second fixed OD sample without modifying baseline data."""

from pathlib import Path

import pandas as pd

from bike_improvements.project_paths import course_root, final_root

from network_analysis.od_generation.build_poi_od_pairs import (
    build_poi_od_pairs,
)
from network_analysis.od_generation.generate_od_demand import (
    LODES_CATEGORY,
    load_demand,
)
from network_analysis.od_generation.lodes_sampling import (
    sample_lodes_trips,
)


SEED = 684

FINAL = final_root()

OUT = (
    course_root()
    / "robustness"
    / "od_seed_684"
)

GRAPH = (
    FINAL
    / "output/cost_scenarios/cost_scenario_1/"
    "greater_boston_cost_scenario_1_simplified.graphml"
)

LODES_PAIRS = (
    FINAL
    / "output/cost_scenarios/cost_scenario_1/"
    "greater_boston_lodes_pairs.csv"
)

POPULATION = (
    FINAL
    / "census_results/"
    "greater_boston_cost_scenario_1_"
    "nodes_with_population_web.geojson"
)

DESTINATIONS = (
    FINAL
    / "processed/osm/Destinations.csv"
)

CONFIG = Path(
    "src/network_analysis/od_generation/config/"
    "demand_parameters.csv"
)


def main() -> None:
    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    for path in [
        GRAPH,
        LODES_PAIRS,
        POPULATION,
        DESTINATIONS,
        CONFIG,
    ]:
        if not path.exists():
            raise FileNotFoundError(path)

    counts = load_demand(
        1,
        config_path=str(CONFIG),
    )

    print("Demand counts:", counts)
    print("Random seed:", SEED)

    lodes_count = int(
        counts[LODES_CATEGORY]
    )

    lodes = sample_lodes_trips(
        pairs_path=str(LODES_PAIRS),
        graph_path=str(GRAPH),
        output_path=str(
            OUT / "lodes_sample.csv"
        ),
        n_trips=lodes_count,
        random_seed=SEED,
    )

    lodes = lodes[
        [
            "origin_node",
            "destination_node",
            "count",
        ]
    ].copy()

    lodes["category"] = LODES_CATEGORY

    poi_counts = {
        category: count
        for category, count in counts.items()
        if category != LODES_CATEGORY
    }

    poi = build_poi_od_pairs(
        graph_path=str(GRAPH),
        pop_geojson_path=str(POPULATION),
        destinations_path=str(DESTINATIONS),
        towns=[
            "Boston",
            "Cambridge",
            "Somerville",
            "Brookline",
        ],
        category_counts=poi_counts,
        output_path=str(
            OUT / "poi_pairs.csv"
        ),
        random_seed=SEED,
    )

    combined = pd.concat(
        [
            lodes,
            poi,
        ],
        ignore_index=True,
    )

    combined = combined[
        [
            "origin_node",
            "destination_node",
            "category",
            "count",
        ]
    ]

    output = (
        OUT
        / "greater_boston_all_pairs_seed_684.csv"
    )

    combined.to_csv(
        output,
        index=False,
    )

    total = int(
        combined["count"].sum()
    )

    if total != 50000:
        raise AssertionError(
            f"Expected 50000 trips; got {total}."
        )

    print()
    print("Rows:", len(combined))
    print("Total demand:", total)
    print()
    print(
        combined.groupby("category")[
            "count"
        ].sum()
    )
    print()
    print("Output:", output)


if __name__ == "__main__":
    main()
