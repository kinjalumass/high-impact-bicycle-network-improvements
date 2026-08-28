"""Generate the proposal's <=20 candidate bicycle improvements."""

from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx
import osmnx as ox

from bike_improvements.candidates.generate import (
    build_candidate_screening,
    load_baseline_edge_usage,
    select_candidates,
)
from bike_improvements.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--graph",
        required=True,
    )

    parser.add_argument(
        "--baseline-root",
        required=True,
    )

    parser.add_argument(
        "--screening-output",
        required=True,
    )

    parser.add_argument(
        "--candidate-output",
        default=(
            "results/candidates/"
            "candidate_segments.csv"
        ),
    )

    args = parser.parse_args()

    config = load_config()

    candidate_config = config[
        "candidate_generation"
    ]

    maximum = int(
        candidate_config[
            "maximum_candidates"
        ]
    )

    eligible_lts = set(
        int(value)
        for value in candidate_config[
            "eligible_lts"
        ]
    )

    connectivity_reserve = int(
        candidate_config[
            "connectivity_reserve"
        ]
    )

    print("Loading Greater Boston graph...")

    G = ox.load_graphml(
        args.graph,
        edge_dtypes={
            "cost": float,
            "length": float,
        },
    )

    nx.relabel_nodes(
        G,
        {
            node: str(node)
            for node in G.nodes
        },
        copy=False,
    )

    print(
        f"Graph: {G.number_of_nodes():,} nodes, "
        f"{G.number_of_edges():,} edges"
    )

    print("Loading four-profile edge usage...")

    usage = load_baseline_edge_usage(
        args.baseline_root
    )

    print(
        f"Baseline edge-profile rows: "
        f"{len(usage):,}"
    )

    print("Building physical-segment screening table...")

    screening = build_candidate_screening(
        G,
        usage,
        eligible_lts=eligible_lts,
    )

    print(
        f"Eligible high-stress physical segments: "
        f"{len(screening):,}"
    )

    candidates = select_candidates(
        screening,
        maximum_candidates=maximum,
        connectivity_reserve=(
            connectivity_reserve
        ),
    )

    screening_path = Path(
        args.screening_output
    )

    screening_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    screening.to_csv(
        screening_path,
        index=False,
    )

    candidate_path = Path(
        args.candidate_output
    )

    candidate_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    candidates.to_csv(
        candidate_path,
        index=False,
    )

    print()
    print("Selected candidates:")
    print(
        candidates[
            [
                "candidate_id",
                "location",
                "length_m",
                "current_lts",
                "modeled_demand",
                "preliminary_benefit",
                "connects_safe_components",
                "selection_reason",
            ]
        ].to_string(index=False)
    )

    print()
    print(
        f"Full screening table: "
        f"{screening_path}"
    )

    print(
        f"Final candidate table: "
        f"{candidate_path}"
    )


if __name__ == "__main__":
    main()
