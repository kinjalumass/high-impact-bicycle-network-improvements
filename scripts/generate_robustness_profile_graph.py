"""Generate one alternative rider-profile graph for robustness analysis."""

from __future__ import annotations

import argparse
import gc
from pathlib import Path

import osmnx as ox
import pandas as pd
import yaml

from bike_improvements.project_paths import course_root, data_relative_path, final_root

from bike_improvements.baseline.profile_graph import (
    apply_profile_costs,
    simplify_profile_graph,
)


UNSIMPLIFIED = (
    final_root()
    / "output"
    / "cost_scenarios"
    / "cost_scenario_1"
    / "greater_boston_cost_scenario_1.graphml"
)

COST_PARAMETERS = Path(
    "src/network_analysis/graph_builder/config/"
    "cost_parameters.csv"
)

OUTPUT_DIR = (
    course_root()
    / "robustness"
    / "profile_graphs"
)

VALID_PROFILES = (
    "child",
    "low_confidence_adult",
    "typical_adult",
    "experienced_adult",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        required=True,
        choices=VALID_PROFILES,
    )
    args = parser.parse_args()

    with open("configs/experiment.yaml") as f:
        config = yaml.safe_load(f)

    scenario_id = int(
        config["robustness"][
            "alternative_profile_scenarios"
        ][args.profile]
    )

    params = pd.read_csv(
        COST_PARAMETERS
    ).set_index("scenario_id")

    if scenario_id not in params.index:
        raise ValueError(
            f"Scenario {scenario_id} not found."
        )

    row = params.loc[scenario_id]

    weights = {
        level: float(
            row[f"lts{level}_weight"]
        )
        for level in (1, 2, 3, 4)
    }

    print("=" * 72)
    print("Robustness profile:", args.profile)
    print("Scenario:", scenario_id)
    print(
        "Description:",
        row["scenario_description"],
    )
    print("Weights:", weights)
    print("=" * 72)

    print("Loading unsimplified graph...")

    G = ox.load_graphml(
        UNSIMPLIFIED,
        edge_dtypes={"cost": float},
    )

    print(
        f"Loaded {G.number_of_nodes():,} nodes, "
        f"{G.number_of_edges():,} edges"
    )

    print(
        "Applying alternative stress weights..."
    )

    apply_profile_costs(
        G,
        weights,
        copy_graph=False,
    )

    print("Simplifying graph...")

    H = simplify_profile_graph(G)

    print(
        f"Simplified to "
        f"{H.number_of_nodes():,} nodes, "
        f"{H.number_of_edges():,} edges"
    )

    if H.number_of_nodes() != 98168:
        raise AssertionError(
            "Unexpected node count."
        )

    if H.number_of_edges() != 279932:
        raise AssertionError(
            "Unexpected edge count."
        )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = (
        OUTPUT_DIR
        / (
            f"greater_boston_{args.profile}_"
            f"scenario_{scenario_id}_"
            "simplified.graphml"
        )
    )

    print("Saving:", output)

    ox.save_graphml(
        H,
        output,
    )

    record = pd.DataFrame(
        [
            {
                "profile": args.profile,
                "scenario_id": scenario_id,
                "scenario_description":
                    row["scenario_description"],
                "lts1_weight": weights[1],
                "lts2_weight": weights[2],
                "lts3_weight": weights[3],
                "lts4_weight": weights[4],
                "nodes": H.number_of_nodes(),
                "edges": H.number_of_edges(),
                "graph_path": data_relative_path(output),
            }
        ]
    )

    manifest = (
        OUTPUT_DIR
        / f"{args.profile}_manifest.csv"
    )

    record.to_csv(
        manifest,
        index=False,
    )

    print()
    print(record.to_string(index=False))
    print()
    print("Complete.")

    del H
    del G
    gc.collect()


if __name__ == "__main__":
    main()
