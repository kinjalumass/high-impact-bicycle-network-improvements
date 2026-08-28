"""Map selected candidates to original unsimplified road segments."""

from __future__ import annotations

import argparse
from pathlib import Path

import osmnx as ox
import pandas as pd

from bike_improvements.candidates.constituents import (
    candidate_constituent_summary,
    candidate_constituents_dataframe,
)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--unsimplified",
        required=True,
    )

    parser.add_argument(
        "--simplified",
        required=True,
    )

    parser.add_argument(
        "--candidates",
        required=True,
    )

    parser.add_argument(
        "--constituents-output",
        required=True,
    )

    parser.add_argument(
        "--summary-output",
        default=(
            "results/candidates/"
            "candidate_constituent_summary.csv"
        ),
    )

    args = parser.parse_args()

    print("Loading unsimplified graph...")

    G_unsimplified = ox.load_graphml(
        args.unsimplified,
        edge_dtypes={
            "cost": float,
            "length": float,
        },
    )

    print(
        f"Unsimplified: "
        f"{G_unsimplified.number_of_nodes():,} nodes, "
        f"{G_unsimplified.number_of_edges():,} edges"
    )

    print("Loading simplified graph...")

    G_simplified = ox.load_graphml(
        args.simplified,
        edge_dtypes={
            "cost": float,
            "length": float,
        },
    )

    print(
        f"Simplified: "
        f"{G_simplified.number_of_nodes():,} nodes, "
        f"{G_simplified.number_of_edges():,} edges"
    )

    candidates = pd.read_csv(
        args.candidates,
        dtype={
            "node_a": str,
            "node_b": str,
        },
    )

    print(
        f"Mapping {len(candidates)} candidates..."
    )

    constituents = (
        candidate_constituents_dataframe(
            G_unsimplified,
            G_simplified,
            candidates,
        )
    )

    summary = candidate_constituent_summary(
        constituents,
        candidates,
    )

    constituent_path = Path(
        args.constituents_output
    )

    constituent_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    constituents.to_csv(
        constituent_path,
        index=False,
    )

    summary_path = Path(
        args.summary_output
    )

    summary_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary.to_csv(
        summary_path,
        index=False,
    )

    print()
    print("Candidate constituent summary:")
    print(summary.to_string(index=False))

    print()
    print(
        "Mixed candidates:",
        int(summary["mixed_lts"].sum()),
    )

    print()
    print(
        "Constituent mapping:",
        constituent_path,
    )

    print(
        "Summary:",
        summary_path,
    )


if __name__ == "__main__":
    main()
