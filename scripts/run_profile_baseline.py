"""Run the full one-to-many UCS baseline for one rider profile."""

from __future__ import annotations

import argparse
from pathlib import Path
from time import perf_counter

import networkx as nx
import osmnx as ox
import pandas as pd

from bike_improvements.baseline.one_to_many import (
    edge_usage_dataframe,
    run_one_to_many_baseline,
)
from bike_improvements.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument("--profile", required=True)
    parser.add_argument("--graph", required=True)
    parser.add_argument("--od", required=True)
    parser.add_argument("--output-dir", required=True)

    parser.add_argument(
        "--workers",
        type=int,
        default=1,
    )

    parser.add_argument(
        "--max-origins",
        type=int,
        default=None,
        help="Optional test-mode limit on unique origins.",
    )

    args = parser.parse_args()

    config = load_config()

    if args.profile not in config["rider_profiles"]:
        raise ValueError(
            f"Unknown rider profile: {args.profile}"
        )

    seed = config["reproducibility"]["random_seed"]

    print(f"Profile: {args.profile}")
    print(f"Graph: {args.graph}")
    print(f"OD data: {args.od}")
    print(f"Workers: {args.workers}")

    print("\nLoading graph...")

    G = ox.load_graphml(
        args.graph,
        edge_dtypes={
            "cost": float,
            "length": float,
        },
    )

    # Match graph IDs to the string representation used in the OD table.
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

    print("\nLoading OD data...")

    od = pd.read_csv(
        args.od,
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    if args.max_origins is not None:
        origins = pd.Series(
            od["origin_node"].unique()
        )

        n = min(
            args.max_origins,
            len(origins),
        )

        sampled_origins = set(
            origins.sample(
                n=n,
                random_state=seed,
            )
        )

        od = od.loc[
            od["origin_node"].isin(sampled_origins)
        ].copy()

        print(
            f"TEST MODE: retained {n:,} sampled origins "
            f"and {len(od):,} OD records"
        )

    print(
        f"OD records: {len(od):,}; "
        f"modeled demand: {od['count'].sum():,.0f}"
    )

    start = perf_counter()

    (
        routes,
        edge_loads,
        edge_refs,
        origin_stats,
        input_stats,
    ) = run_one_to_many_baseline(
        G,
        od,
        workers=args.workers,
    )

    elapsed = perf_counter() - start

    routes.insert(
        0,
        "rider_profile",
        args.profile,
    )

    edge_usage = edge_usage_dataframe(
        G,
        edge_refs,
        edge_loads,
    )

    edge_usage.insert(
        0,
        "rider_profile",
        args.profile,
    )

    origin_stats.insert(
        0,
        "rider_profile",
        args.profile,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    routes_path = output_dir / "od_routes.csv"
    edges_path = output_dir / "edge_usage.csv"
    origins_path = output_dir / "origin_search_stats.csv"
    summary_path = output_dir / "summary.csv"
    category_path = output_dir / "category_summary.csv"

    routes.to_csv(
        routes_path,
        index=False,
    )

    edge_usage.to_csv(
        edges_path,
        index=False,
    )

    origin_stats.to_csv(
        origins_path,
        index=False,
    )

    routed = routes.loc[routes["found"]].copy()

    routed_demand = float(
        routed["demand"].sum()
    )

    total_demand = float(
        routes["demand"].sum()
    )

    weighted_cost = float(
        (
            routed["route_cost"]
            * routed["demand"]
        ).sum()
    )

    weighted_distance = float(
        (
            routed["route_distance"]
            * routed["demand"]
        ).sum()
    )

    summary = pd.DataFrame(
        [
            {
                "rider_profile": args.profile,
                "od_records": len(routes),
                "od_records_routed": int(
                    routes["found"].sum()
                ),
                "total_demand": total_demand,
                "routed_demand": routed_demand,
                "routing_success_rate_by_record": float(
                    routes["found"].mean()
                ),
                "routing_success_rate_by_demand": (
                    routed_demand / total_demand
                    if total_demand
                    else 0.0
                ),
                "demand_weighted_total_route_cost": weighted_cost,
                "demand_weighted_mean_route_cost": (
                    weighted_cost / routed_demand
                    if routed_demand
                    else float("nan")
                ),
                "demand_weighted_mean_route_distance_m": (
                    weighted_distance / routed_demand
                    if routed_demand
                    else float("nan")
                ),
                "unique_routing_origins": input_stats[
                    "routing_origins"
                ],
                "total_runtime_seconds": elapsed,
                "workers": args.workers,
            }
        ]
    )

    summary.to_csv(
        summary_path,
        index=False,
    )

    category_rows = []

    for category, group in routes.groupby("category"):
        found = group.loc[group["found"]].copy()

        demand = float(group["demand"].sum())
        found_demand = float(found["demand"].sum())

        category_rows.append(
            {
                "rider_profile": args.profile,
                "category": category,
                "od_records": len(group),
                "od_records_routed": int(
                    group["found"].sum()
                ),
                "total_demand": demand,
                "routed_demand": found_demand,
                "demand_success_rate": (
                    found_demand / demand
                    if demand
                    else 0.0
                ),
                "mean_route_cost": found[
                    "route_cost"
                ].mean(),
                "mean_route_distance_m": found[
                    "route_distance"
                ].mean(),
                "demand_weighted_mean_route_cost": (
                    (
                        found["route_cost"]
                        * found["demand"]
                    ).sum()
                    / found_demand
                    if found_demand
                    else float("nan")
                ),
                "demand_weighted_mean_route_distance_m": (
                    (
                        found["route_distance"]
                        * found["demand"]
                    ).sum()
                    / found_demand
                    if found_demand
                    else float("nan")
                ),
            }
        )

    pd.DataFrame(
        category_rows
    ).to_csv(
        category_path,
        index=False,
    )

    print("\nBaseline complete.")
    print(summary.to_string(index=False))

    print("\nOutputs:")
    print(routes_path)
    print(edges_path)
    print(origins_path)
    print(summary_path)
    print(category_path)


if __name__ == "__main__":
    main()
