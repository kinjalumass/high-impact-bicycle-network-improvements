"""Run UCS/A* comparison on a real bicycle network and OD sample."""

from __future__ import annotations

import argparse
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd

from bike_improvements.config import load_config
from bike_improvements.routing.benchmark import benchmark_routing
from bike_improvements.routing.common import prepare_routing_graph


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--graph",
        required=True,
        help="Path to simplified cost GraphML file.",
    )

    parser.add_argument(
        "--od",
        required=True,
        help="Path to OD demand CSV.",
    )

    parser.add_argument(
        "--sample-size",
        type=int,
        default=100,
        help="Number of unique OD pairs to benchmark.",
    )

    parser.add_argument(
        "--output",
        default="results/routing/ucs_astar_benchmark.csv",
    )

    args = parser.parse_args()

    config = load_config()

    seed = config["reproducibility"]["random_seed"]

    print(f"Loading graph: {args.graph}")
    G = ox.load_graphml(args.graph)

    # Normalize OSM node IDs to strings so they match the OD CSV.
    G = nx.relabel_nodes(
        G,
        {node: str(node) for node in G.nodes},
        copy=True,
    )

    print(
        f"Graph loaded: "
        f"{G.number_of_nodes():,} nodes, "
        f"{G.number_of_edges():,} edges"
    )

    print(f"Loading OD data: {args.od}")
    od = pd.read_csv(
        args.od,
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    od = od.loc[
        od["origin_node"] != od["destination_node"]
    ].copy()

    if len(od) > args.sample_size:
        od = od.sample(
            n=args.sample_size,
            random_state=seed,
        )

    print(f"Benchmark OD pairs: {len(od):,}")

    prepared = prepare_routing_graph(G)

    print(
        f"Minimum cost per meter: "
        f"{prepared.min_cost_per_meter:.6f}"
    )

    results = benchmark_routing(
        prepared,
        od,
    )

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    results.to_csv(output, index=False)

    print()
    print("Results by algorithm:")

    summary = (
        results.groupby("algorithm")
        .agg(
            pairs=("found", "size"),
            routes_found=("found", "sum"),
            mean_runtime_seconds=("runtime_seconds", "mean"),
            median_runtime_seconds=("runtime_seconds", "median"),
            mean_nodes_expanded=("nodes_expanded", "mean"),
            median_nodes_expanded=("nodes_expanded", "median"),
        )
    )

    print(summary)

    # Verify that both algorithms produce the same optimal costs.
    comparison = results.pivot_table(
        index=["origin_node", "destination_node"],
        columns="algorithm",
        values="route_cost",
        aggfunc="first",
    )

    comparison = comparison.dropna()

    if {"ucs", "astar"}.issubset(comparison.columns):
        differences = (
            comparison["ucs"] - comparison["astar"]
        ).abs()

        max_difference = differences.max()

        print()
        print(
            "Maximum UCS/A* route-cost difference:",
            max_difference,
        )

        if max_difference > 1e-6:
            raise AssertionError(
                "UCS and A* produced different optimal route costs."
            )

        print("Optimal-cost equivalence check passed.")

    print()
    print(f"Saved benchmark: {output}")


if __name__ == "__main__":
    main()
