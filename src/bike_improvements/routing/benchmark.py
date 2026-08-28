"""Benchmark UCS and A* on identical origin-destination pairs."""

from __future__ import annotations

from time import perf_counter
from typing import Callable

import pandas as pd

from bike_improvements.routing.astar import astar_shortest_path
from bike_improvements.routing.common import PreparedRoutingGraph
from bike_improvements.routing.ucs import ucs_shortest_path


RoutingAlgorithm = Callable


def benchmark_routing(
    graph: PreparedRoutingGraph,
    od_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Run UCS and A* on the same OD pairs.

    Returns one row per OD pair per algorithm.
    """
    required = {"origin_node", "destination_node"}

    missing = required - set(od_df.columns)

    if missing:
        raise ValueError(
            f"OD data is missing required columns: {sorted(missing)}"
        )

    algorithms: dict[str, RoutingAlgorithm] = {
        "ucs": ucs_shortest_path,
        "astar": astar_shortest_path,
    }

    records = []

    for row in od_df.itertuples(index=False):
        source = str(row.origin_node)
        target = str(row.destination_node)

        category = getattr(row, "category", None)
        demand = getattr(row, "count", 1)

        if source not in graph.adjacency or target not in graph.adjacency:
            continue

        for algorithm_name, algorithm in algorithms.items():
            start = perf_counter()

            result = algorithm(
                graph,
                source,
                target,
            )

            runtime = perf_counter() - start

            records.append(
                {
                    "origin_node": source,
                    "destination_node": target,
                    "category": category,
                    "demand": demand,
                    "algorithm": algorithm_name,
                    "found": result.found,
                    "route_cost": result.route_cost,
                    "route_distance": result.route_distance,
                    "nodes_expanded": result.nodes_expanded,
                    "runtime_seconds": runtime,
                    "route_edge_count": len(result.edge_path),
                }
            )

    return pd.DataFrame.from_records(records)
