"""Run a package of candidate interventions for one rider profile."""

from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

import networkx as nx
import osmnx as ox
import pandas as pd

from bike_improvements.baseline.one_to_many import (
    run_one_to_many_baseline,
)
from bike_improvements.config import load_config
from bike_improvements.interventions.simulate import (
    compare_route_results,
    profile_weights,
)
from bike_improvements.optimization.greedy import (
    apply_candidate_set,
    package_metadata,
)


def find_target_lts(config: dict) -> int:
    """Return configured intervention target LTS."""
    block = config["intervention_evaluation"]
    return int(block["target_lts"])


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--candidate-ids",
        required=True,
        help="Comma-separated candidate IDs, e.g. C001,C002",
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--od", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--baseline-routes", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-origins", type=int)

    args = parser.parse_args()

    candidate_ids = [
        value.strip()
        for value in args.candidate_ids.split(",")
        if value.strip()
    ]

    config = load_config()
    target_lts = find_target_lts(config)

    candidates = pd.read_csv(
        args.candidates,
        dtype={
            "candidate_id": str,
            "node_a": str,
            "node_b": str,
            "osmid": str,
        },
    )

    metadata = package_metadata(
        candidates,
        candidate_ids,
    )

    print("=" * 72)
    print("Combination:", metadata["combination_id"])
    print("Profile:", args.profile)
    print("Project count:", metadata["project_count"])
    print(
        "Cumulative length:",
        metadata["cumulative_length_m"],
        "m",
    )
    print("Target LTS:", target_lts)
    print("=" * 72)

    print("\nLoading graph...")

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

    weights = profile_weights(
        config,
        args.profile,
    )

    modifications = apply_candidate_set(
        G,
        candidates,
        candidate_ids,
        weights,
        target_lts=target_lts,
    )

    print()
    print("Applied interventions:")
    print(modifications.to_string(index=False))

    od = pd.read_csv(
        args.od,
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    baseline = pd.read_csv(
        args.baseline_routes,
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    if args.max_origins is not None:
        origins = pd.Series(
            od["origin_node"].unique()
        ).sample(
            n=min(
                args.max_origins,
                od["origin_node"].nunique(),
            ),
            random_state=683,
        )

        selected = set(origins)

        od = od.loc[
            od["origin_node"].isin(selected)
        ].copy()

        baseline = baseline.loc[
            baseline["origin_node"].isin(selected)
        ].copy()

    print()
    print(
        f"OD records: {len(od):,}; "
        f"demand: {od['count'].sum():,.0f}"
    )
    print(
        "Baseline route rows:",
        f"{len(baseline):,}",
    )

    print("\nRunning package routing...")

    start = perf_counter()

    result = run_one_to_many_baseline(
        G,
        od,
        workers=args.workers,
    )

    elapsed = perf_counter() - start

    intervention_routes = result[0]

    comparison = compare_route_results(
        baseline,
        intervention_routes,
    )

    if len(comparison) != len(baseline):
        raise AssertionError(
            "Baseline/intervention row counts differ."
        )

    if not (
        comparison["baseline_found"]
        == comparison["intervention_found"]
    ).all():
        raise AssertionError(
            "Reachability changed."
        )

    comparable = (
        comparison["baseline_found"]
        & comparison["intervention_found"]
    )

    improved = comparison["improved"]

    routed_demand = float(
        comparison.loc[
            comparable,
            "demand",
        ].sum()
    )

    improved_demand = float(
        comparison.loc[
            improved,
            "demand",
        ].sum()
    )

    total_reduction = float(
        comparison[
            "demand_weighted_cost_reduction"
        ].sum()
    )

    baseline_cost = float(
        (
            comparison.loc[
                comparable,
                "baseline_route_cost",
            ]
            * comparison.loc[
                comparable,
                "demand",
            ]
        ).sum()
    )

    distance_change = float(
        comparison[
            "demand_weighted_distance_change_m"
        ].sum()
    )

    minimum_reduction = float(
        comparison.loc[
            comparable,
            "cost_reduction",
        ].min()
    )

    if minimum_reduction < -1e-8:
        raise AssertionError(
            "Package increased an optimal route cost."
        )

    summary = pd.DataFrame(
        [
            {
                **metadata,
                "rider_profile": args.profile,
                "target_lts": target_lts,
                "modified_directed_edges":
                    int(
                        modifications[
                            "modified_directed_edges"
                        ].sum()
                    ),
                "od_records": len(comparison),
                "routed_od_records":
                    int(comparable.sum()),
                "improved_od_records":
                    int(improved.sum()),
                "total_demand":
                    float(
                        comparison["demand"].sum()
                    ),
                "routed_demand":
                    routed_demand,
                "improved_demand":
                    improved_demand,
                "demand_weighted_route_cost_reduction":
                    total_reduction,
                "percent_baseline_cost_reduction":
                    (
                        100.0
                        * total_reduction
                        / baseline_cost
                        if baseline_cost
                        else 0.0
                    ),
                "demand_weighted_distance_change_m":
                    distance_change,
                "mean_distance_change_m":
                    (
                        distance_change
                        / routed_demand
                        if routed_demand
                        else 0.0
                    ),
                "minimum_cost_reduction":
                    minimum_reduction,
                "runtime_seconds":
                    elapsed,
                "workers":
                    args.workers,
            }
        ]
    )

    output = Path(args.output_dir)
    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    summary.to_csv(
        output / "summary.csv",
        index=False,
    )

    comparison.to_csv(
        output / "od_comparison.csv",
        index=False,
    )

    modifications.to_csv(
        output / "applied_candidates.csv",
        index=False,
    )

    print()
    print("Package summary:")
    print(summary.to_string(index=False))

    print()
    print("Reachability consistency: PASSED")
    print("Outputs:", output)


if __name__ == "__main__":
    main()
