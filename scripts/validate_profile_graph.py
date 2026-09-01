"""Validate profile graph reconstruction against reference scenario 1."""

from __future__ import annotations

import argparse
import math

import osmnx as ox

from bike_improvements.baseline.profile_graph import build_profile_graph
from bike_improvements.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--unsimplified", required=True)
    parser.add_argument("--reference", required=True)

    args = parser.parse_args()

    config = load_config()

    weights = {
        int(level): float(weight)
        for level, weight in config[
            "rider_profiles"
        ]["child"]["lts_weights"].items()
    }

    print("Loading unsimplified graph...")
    G = ox.load_graphml(
        args.unsimplified,
        edge_dtypes={"cost": float},
    )

    print("Rebuilding scenario-1 simplified graph...")
    rebuilt = build_profile_graph(G, weights)

    print("Loading existing reference graph...")
    reference = ox.load_graphml(
        args.reference,
        edge_dtypes={"cost": float},
    )

    print()
    print(
        "Rebuilt:",
        f"{rebuilt.number_of_nodes():,}",
        "nodes,",
        f"{rebuilt.number_of_edges():,}",
        "edges",
    )

    print(
        "Reference:",
        f"{reference.number_of_nodes():,}",
        "nodes,",
        f"{reference.number_of_edges():,}",
        "edges",
    )

    assert rebuilt.number_of_nodes() == reference.number_of_nodes()
    assert rebuilt.number_of_edges() == reference.number_of_edges()

    checked = 0
    mismatches = 0
    max_difference = 0.0

    for u, v, key, ref_data in reference.edges(
        keys=True,
        data=True,
    ):
        if not rebuilt.has_edge(u, v, key):
            mismatches += 1
            continue

        new_data = rebuilt.edges[u, v, key]

        ref_cost = float(ref_data["cost"])
        new_cost = float(new_data["cost"])

        difference = abs(ref_cost - new_cost)
        max_difference = max(max_difference, difference)

        if not math.isclose(
            ref_cost,
            new_cost,
            rel_tol=1e-9,
            abs_tol=1e-6,
        ):
            mismatches += 1

        checked += 1

    print()
    print("Edges checked:", f"{checked:,}")
    print("Cost mismatches:", f"{mismatches:,}")
    print("Maximum cost difference:", max_difference)

    if mismatches:
        raise AssertionError(
            "Rebuilt scenario-1 graph does not match reference."
        )

    print()
    print("Profile graph validation PASSED.")


if __name__ == "__main__":
    main()
