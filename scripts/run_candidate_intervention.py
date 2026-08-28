"""Run one candidate intervention for one rider profile."""

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
    apply_candidate_intervention,
    compare_route_results,
    profile_weights,
)


def find_target_lts(config: dict) -> int:
    """Find the configured intervention target LTS."""
    for value in config.values():
        if isinstance(value, dict) and "target_lts" in value:
            target = value["target_lts"]
            if target is not None:
                return int(target)

    raise KeyError("Configured target_lts was not found.")


def summarize_categories(
    comparison: pd.DataFrame,
    candidate_id: str,
    profile: str,
) -> pd.DataFrame:
    """Summarize before/after effects by destination category."""
    rows = []

    for category, group in comparison.groupby("category"):
        comparable = (
            group["baseline_found"]
            & group["intervention_found"]
        )
        improved = group["improved"]

        routed_demand = float(
            group.loc[comparable, "demand"].sum()
        )
        improved_demand = float(
            group.loc[improved, "demand"].sum()
        )

        reduction = float(
            group[
                "demand_weighted_cost_reduction"
            ].sum()
        )

        baseline_cost = float(
            (
                group.loc[
                    comparable,
                    "baseline_route_cost",
                ]
                * group.loc[
                    comparable,
                    "demand",
                ]
            ).sum()
        )

        rows.append(
            {
                "candidate_id": candidate_id,
                "rider_profile": profile,
                "category": category,
                "od_records": len(group),
                "routed_od_records": int(
                    comparable.sum()
                ),
                "improved_od_records": int(
                    improved.sum()
                ),
                "routed_demand": routed_demand,
                "improved_demand": improved_demand,
                "demand_weighted_route_cost_reduction":
                    reduction,
                "percent_baseline_cost_reduction":
                    (
                        100.0 * reduction / baseline_cost
                        if baseline_cost
                        else 0.0
                    ),
            }
        )

    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--od", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--baseline-routes", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--max-origins", type=int)

    args = parser.parse_args()

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

    matches = candidates.loc[
        candidates["candidate_id"]
        == args.candidate_id
    ]

    if len(matches) != 1:
        raise ValueError(
            f"Expected one row for {args.candidate_id}; "
            f"found {len(matches)}."
        )

    candidate = matches.iloc[0]

    print("=" * 72)
    print("Candidate:", args.candidate_id)
    print("Location:", candidate["location"])
    print("Profile:", args.profile)
    print("Current LTS:", candidate["current_lts"])
    print("Target LTS:", target_lts)
    print("Length:", candidate["length_m"], "m")
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
        {node: str(node) for node in G.nodes},
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

    modified = apply_candidate_intervention(
        G,
        candidate,
        weights,
        target_lts=target_lts,
    )

    print(
        "Modified directed edges:",
        len(modified),
    )

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

    print(
        f"OD records: {len(od):,}; "
        f"demand: {od['count'].sum():,.0f}"
    )
    print(
        "Baseline route rows:",
        f"{len(baseline):,}",
    )

    print("\nRunning intervention routing...")

    start = perf_counter()

    result = run_one_to_many_baseline(
        G,
        od,
        workers=args.workers,
    )

    elapsed = perf_counter() - start

    intervention_routes = result[0]
    origin_stats = result[3]
    input_stats = result[4]

    comparison = compare_route_results(
        baseline,
        intervention_routes,
    )

    if len(comparison) != len(baseline):
        raise AssertionError(
            "Baseline and intervention row counts differ."
        )

    if not (
        comparison["baseline_found"]
        == comparison["intervention_found"]
    ).all():
        raise AssertionError(
            "Reachability changed after cost-only intervention."
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

    intervention_cost = float(
        (
            comparison.loc[
                comparable,
                "intervention_route_cost",
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
            "An intervention route became more costly."
        )

    summary = pd.DataFrame(
        [
            {
                "candidate_id": args.candidate_id,
                "location": candidate["location"],
                "rider_profile": args.profile,
                "current_lts":
                    candidate["current_lts"],
                "target_lts": target_lts,
                "candidate_length_m":
                    candidate["length_m"],
                "modified_directed_edges":
                    len(modified),
                "od_records": len(comparison),
                "routed_od_records":
                    int(comparable.sum()),
                "improved_od_records":
                    int(improved.sum()),
                "total_demand":
                    float(
                        comparison["demand"].sum()
                    ),
                "routed_demand": routed_demand,
                "improved_demand": improved_demand,
                "baseline_weighted_route_cost":
                    baseline_cost,
                "intervention_weighted_route_cost":
                    intervention_cost,
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
                "minimum_cost_reduction":
                    minimum_reduction,
                "routing_origins":
                    input_stats.get(
                        "routing_origins",
                        len(origin_stats),
                    ),
                "runtime_seconds": elapsed,
                "workers": args.workers,
            }
        ]
    )

    categories = summarize_categories(
        comparison,
        args.candidate_id,
        args.profile,
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

    categories.to_csv(
        output / "category_summary.csv",
        index=False,
    )

    comparison.to_csv(
        output / "od_comparison.csv",
        index=False,
    )

    origin_stats.to_csv(
        output / "origin_search_stats.csv",
        index=False,
    )

    print()
    print("Intervention summary:")
    print(summary.to_string(index=False))

    print()
    print("Reachability consistency: PASSED")
    print("Outputs:", output)


if __name__ == "__main__":
    main()
