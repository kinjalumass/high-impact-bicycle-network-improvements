"""Create explicit UCS/A* validation tables for the final report."""

from pathlib import Path

import pandas as pd


RESULTS = Path("results/routing")


def main() -> None:
    benchmark = pd.read_csv(
        RESULTS / "ucs_astar_benchmark.csv",
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    summary = pd.read_csv(
        RESULTS / "ucs_astar_benchmark_summary.csv"
    )

    # ------------------------------------------------------------
    # Overall benchmark comparison
    # ------------------------------------------------------------

    indexed = summary.set_index("algorithm")

    ucs = indexed.loc["ucs"]
    astar = indexed.loc["astar"]

    comparison = pd.DataFrame(
        [
            {
                "metric": "Routable pairs",
                "ucs": int(ucs["pairs_found"]),
                "astar": int(astar["pairs_found"]),
                "astar_reduction_pct": 0.0,
            },
            {
                "metric": "Mean runtime (s)",
                "ucs": ucs["mean_runtime_seconds_all"],
                "astar": astar["mean_runtime_seconds_all"],
                "astar_reduction_pct":
                    100
                    * (
                        ucs["mean_runtime_seconds_all"]
                        - astar["mean_runtime_seconds_all"]
                    )
                    / ucs["mean_runtime_seconds_all"],
            },
            {
                "metric": "Median runtime (s)",
                "ucs": ucs["median_runtime_seconds_all"],
                "astar": astar["median_runtime_seconds_all"],
                "astar_reduction_pct":
                    100
                    * (
                        ucs["median_runtime_seconds_all"]
                        - astar["median_runtime_seconds_all"]
                    )
                    / ucs["median_runtime_seconds_all"],
            },
            {
                "metric": "Mean nodes expanded",
                "ucs": ucs["mean_nodes_expanded_all"],
                "astar": astar["mean_nodes_expanded_all"],
                "astar_reduction_pct":
                    100
                    * (
                        ucs["mean_nodes_expanded_all"]
                        - astar["mean_nodes_expanded_all"]
                    )
                    / ucs["mean_nodes_expanded_all"],
            },
            {
                "metric": "Median nodes expanded",
                "ucs": ucs["median_nodes_expanded_all"],
                "astar": astar["median_nodes_expanded_all"],
                "astar_reduction_pct":
                    100
                    * (
                        ucs["median_nodes_expanded_all"]
                        - astar["median_nodes_expanded_all"]
                    )
                    / ucs["median_nodes_expanded_all"],
            },
            {
                "metric": "Mean routable route cost",
                "ucs": ucs["mean_route_cost_routable"],
                "astar": astar["mean_route_cost_routable"],
                "astar_reduction_pct": 0.0,
            },
        ]
    )

    comparison.to_csv(
        RESULTS / "ucs_astar_validation_summary.csv",
        index=False,
    )

    # ------------------------------------------------------------
    # Five representative route checks
    # ------------------------------------------------------------

    routable = benchmark.loc[
        benchmark["found"]
    ].copy()

    paired = routable.pivot_table(
        index=[
            "origin_node",
            "destination_node",
            "category",
            "demand",
        ],
        columns="algorithm",
        values=[
            "route_cost",
            "route_distance",
            "nodes_expanded",
            "runtime_seconds",
            "route_edge_count",
        ],
        aggfunc="first",
    )

    paired.columns = [
        f"{metric}_{algorithm}"
        for metric, algorithm in paired.columns
    ]

    paired = paired.reset_index()

    paired["cost_difference"] = (
        paired["route_cost_ucs"]
        - paired["route_cost_astar"]
    ).abs()

    paired["distance_difference"] = (
        paired["route_distance_ucs"]
        - paired["route_distance_astar"]
    ).abs()

    paired["edge_count_difference"] = (
        paired["route_edge_count_ucs"]
        - paired["route_edge_count_astar"]
    ).abs()

    # Choose representative routes spanning short, medium, and long
    # route distances. This is deterministic.
    paired = paired.sort_values(
        "route_distance_ucs"
    ).reset_index(drop=True)

    positions = [
        0,
        len(paired) // 4,
        len(paired) // 2,
        3 * len(paired) // 4,
        len(paired) - 1,
    ]

    checks = paired.iloc[
        positions
    ].copy()

    checks.insert(
        0,
        "manual_check_id",
        [
            "R1",
            "R2",
            "R3",
            "R4",
            "R5",
        ],
    )

    checks["optimal_cost_match"] = (
        checks["cost_difference"] <= 1e-6
    )

    checks["distance_match"] = (
        checks["distance_difference"] <= 1e-6
    )

    checks["edge_count_match"] = (
        checks["edge_count_difference"] == 0
    )

    checks.to_csv(
        RESULTS / "manual_route_checks.csv",
        index=False,
    )

    print("Benchmark validation:")
    print(
        comparison.to_string(
            index=False
        )
    )

    print()
    print("Representative route checks:")
    print(
        checks[
            [
                "manual_check_id",
                "origin_node",
                "destination_node",
                "category",
                "route_cost_ucs",
                "route_cost_astar",
                "route_distance_ucs",
                "route_distance_astar",
                "route_edge_count_ucs",
                "route_edge_count_astar",
                "nodes_expanded_ucs",
                "nodes_expanded_astar",
                "optimal_cost_match",
                "distance_match",
                "edge_count_match",
            ]
        ].to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()
