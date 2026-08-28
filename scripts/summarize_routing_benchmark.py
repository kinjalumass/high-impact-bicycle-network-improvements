"""Summarize UCS/A* benchmark results."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        default="results/routing/ucs_astar_benchmark.csv",
    )

    parser.add_argument(
        "--summary-output",
        default="results/routing/ucs_astar_benchmark_summary.csv",
    )

    parser.add_argument(
        "--unroutable-output",
        default="results/routing/ucs_astar_unroutable_pairs.csv",
    )

    args = parser.parse_args()

    df = pd.read_csv(
        args.input,
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    summary_records = []

    for algorithm, group in df.groupby("algorithm"):
        found = group.loc[group["found"]].copy()

        summary_records.append(
            {
                "algorithm": algorithm,
                "pairs_total": len(group),
                "pairs_found": int(group["found"].sum()),
                "success_rate": float(group["found"].mean()),
                "mean_runtime_seconds_all": group[
                    "runtime_seconds"
                ].mean(),
                "median_runtime_seconds_all": group[
                    "runtime_seconds"
                ].median(),
                "mean_nodes_expanded_all": group[
                    "nodes_expanded"
                ].mean(),
                "median_nodes_expanded_all": group[
                    "nodes_expanded"
                ].median(),
                "mean_route_cost_routable": found[
                    "route_cost"
                ].mean(),
                "mean_route_distance_routable": found[
                    "route_distance"
                ].mean(),
                "mean_route_edge_count_routable": found[
                    "route_edge_count"
                ].mean(),
            }
        )

    summary = pd.DataFrame(summary_records)

    summary_path = Path(args.summary_output)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary.to_csv(summary_path, index=False)

    pair_status = df.pivot_table(
        index=[
            "origin_node",
            "destination_node",
            "category",
            "demand",
        ],
        columns="algorithm",
        values="found",
        aggfunc="first",
    ).reset_index()

    if {"ucs", "astar"}.issubset(pair_status.columns):
        unroutable = pair_status.loc[
            (~pair_status["ucs"]) & (~pair_status["astar"])
        ].copy()
    else:
        unroutable = pd.DataFrame()

    unroutable_path = Path(args.unroutable_output)
    unroutable.to_csv(unroutable_path, index=False)

    costs = df.loc[df["found"]].pivot_table(
        index=["origin_node", "destination_node"],
        columns="algorithm",
        values="route_cost",
        aggfunc="first",
    ).dropna()

    if {"ucs", "astar"}.issubset(costs.columns):
        differences = (costs["ucs"] - costs["astar"]).abs()

        max_difference = float(differences.max())
        different_pairs = int((differences > 1e-6).sum())
    else:
        max_difference = float("nan")
        different_pairs = 0

    print("Benchmark summary:")
    print(summary.to_string(index=False))

    print()
    print(f"Unroutable OD pairs: {len(unroutable)}")
    print(f"Maximum UCS/A* cost difference: {max_difference}")
    print(f"Pairs with differing optimal costs: {different_pairs}")

    print()
    print(f"Saved summary: {summary_path}")
    print(f"Saved unroutable pairs: {unroutable_path}")


if __name__ == "__main__":
    main()
