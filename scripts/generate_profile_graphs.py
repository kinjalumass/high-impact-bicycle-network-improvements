"""Generate simplified Greater Boston graphs for the four rider profiles."""

from __future__ import annotations

import argparse
import gc
from pathlib import Path

import osmnx as ox
import pandas as pd

from bike_improvements.baseline.profile_graph import (
    apply_profile_costs,
    simplify_profile_graph,
)
from bike_improvements.config import load_config


GENERATED_PROFILES = (
    "low_confidence_adult",
    "typical_adult",
    "experienced_adult",
)


def profile_weights(profile: dict) -> dict[int, float]:
    """Normalize YAML LTS-weight keys and values."""
    return {
        int(level): float(weight)
        for level, weight in profile["lts_weights"].items()
    }


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--unsimplified",
        required=True,
        help="Scenario-1 unsimplified Greater Boston GraphML.",
    )

    parser.add_argument(
        "--child-reference",
        required=True,
        help="Existing validated scenario-1 simplified graph.",
    )

    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory for generated profile GraphML files.",
    )

    parser.add_argument(
        "--manifest",
        default="results/baseline/profile_graph_manifest.csv",
    )

    args = parser.parse_args()

    config = load_config()
    profiles = config["rider_profiles"]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    records = []

    # Child profile uses the validated scenario 1 graph
    # against our reconstruction code exactly.
    child = profiles["child"]

    records.append(
        {
            "profile": "child",
            "scenario_id": child["scenario_id"],
            "graph_path": str(Path(args.child_reference).resolve()),
            "generated_by_course_project": False,
            "lts1_weight": child["lts_weights"][1],
            "lts2_weight": child["lts_weights"][2],
            "lts3_weight": child["lts_weights"][3],
            "lts4_weight": child["lts_weights"][4],
            "nodes": 98168,
            "edges": 279932,
        }
    )

    for profile_name in GENERATED_PROFILES:
        profile = profiles[profile_name]
        weights = profile_weights(profile)

        scenario_id = profile["scenario_id"]

        output_path = (
            output_dir
            / f"greater_boston_{profile_name}_scenario_{scenario_id}_simplified.graphml"
        )

        print()
        print("=" * 72)
        print(f"Generating profile: {profile_name}")
        print(f"Scenario: {scenario_id}")
        print(f"Weights: {weights}")
        print("=" * 72)

        # Reload for each profile so we do not retain multiple 450 MB
        # unsimplified graph copies in memory.
        print("Loading unsimplified Greater Boston graph...")

        G = ox.load_graphml(
            args.unsimplified,
            edge_dtypes={"cost": float},
        )

        print(
            f"Loaded {G.number_of_nodes():,} nodes, "
            f"{G.number_of_edges():,} edges"
        )

        print("Applying rider-profile edge costs...")

        apply_profile_costs(
            G,
            weights,
            copy_graph=False,
        )

        print("Simplifying weighted graph...")

        simplified = simplify_profile_graph(G)

        print(
            f"Simplified to {simplified.number_of_nodes():,} nodes, "
            f"{simplified.number_of_edges():,} edges"
        )

        print(f"Saving {output_path} ...")
        ox.save_graphml(simplified, output_path)

        records.append(
            {
                "profile": profile_name,
                "scenario_id": scenario_id,
                "graph_path": str(output_path.resolve()),
                "generated_by_course_project": True,
                "lts1_weight": weights[1],
                "lts2_weight": weights[2],
                "lts3_weight": weights[3],
                "lts4_weight": weights[4],
                "nodes": simplified.number_of_nodes(),
                "edges": simplified.number_of_edges(),
            }
        )

        del simplified
        del G
        gc.collect()

    manifest = pd.DataFrame(records)

    manifest_path = Path(args.manifest)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    manifest.to_csv(manifest_path, index=False)

    print()
    print("Profile graph generation complete.")
    print()
    print(manifest.to_string(index=False))
    print()
    print(f"Manifest saved to: {manifest_path}")


if __name__ == "__main__":
    main()
