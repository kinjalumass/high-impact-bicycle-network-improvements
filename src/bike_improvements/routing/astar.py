"""A* search for stress-weighted bicycle routing."""

from __future__ import annotations

import math
from heapq import heappop, heappush
from itertools import count
from typing import Any

from bike_improvements.routing.common import (
    PreparedRoutingGraph,
    RouteResult,
    great_circle_distance_m,
    reconstruct_route,
)


def astar_shortest_path(
    graph: PreparedRoutingGraph,
    source: Any,
    target: Any,
) -> RouteResult:
    """
    Find a minimum-cost route using A*.

    The heuristic is:

        straight-line distance * minimum graph cost per meter

    This remains admissible for the project's cost model because network
    route distance cannot be shorter than straight-line distance, and the
    multiplier is the minimum observed cost-per-meter value.
    """
    if source not in graph.adjacency:
        raise ValueError(f"Source node {source!r} is not in the graph.")

    if target not in graph.adjacency:
        raise ValueError(f"Target node {target!r} is not in the graph.")

    if source == target:
        return RouteResult(
            source=source,
            target=target,
            found=True,
            route_cost=0.0,
            route_distance=0.0,
            nodes_expanded=1,
            node_path=[source],
            edge_path=[],
        )

    target_coord = graph.coordinates.get(target)

    def heuristic(node: Any) -> float:
        node_coord = graph.coordinates.get(node)

        # Falling back to zero converts A* into UCS and preserves correctness.
        if node_coord is None or target_coord is None:
            return 0.0

        return (
            great_circle_distance_m(node_coord, target_coord)
            * graph.min_cost_per_meter
        )

    g_score = {source: 0.0}
    predecessor = {}
    settled = set()

    tie_breaker = count()

    heap = [
        (
            heuristic(source),
            0.0,
            next(tie_breaker),
            source,
        )
    ]

    while heap:
        _, current_cost, _, u = heappop(heap)

        if u in settled:
            continue

        settled.add(u)

        if u == target:
            node_path, edge_path, route_distance = reconstruct_route(
                source,
                target,
                predecessor,
            )

            return RouteResult(
                source=source,
                target=target,
                found=True,
                route_cost=current_cost,
                route_distance=route_distance,
                nodes_expanded=len(settled),
                node_path=node_path,
                edge_path=edge_path,
            )

        for edge in graph.adjacency.get(u, ()):
            v = edge.neighbor
            tentative_g = current_cost + edge.cost

            if tentative_g < g_score.get(v, math.inf):
                g_score[v] = tentative_g
                predecessor[v] = (
                    u,
                    edge.key,
                    edge.length,
                )

                estimated_total = tentative_g + heuristic(v)

                heappush(
                    heap,
                    (
                        estimated_total,
                        tentative_g,
                        next(tie_breaker),
                        v,
                    ),
                )

    return RouteResult(
        source=source,
        target=target,
        found=False,
        route_cost=math.inf,
        route_distance=math.inf,
        nodes_expanded=len(settled),
        node_path=[],
        edge_path=[],
    )
