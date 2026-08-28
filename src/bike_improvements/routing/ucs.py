"""Uniform Cost Search for stress-weighted bicycle routing."""

from __future__ import annotations

import math
from heapq import heappop, heappush
from itertools import count
from typing import Any

from bike_improvements.routing.common import (
    PreparedRoutingGraph,
    RouteResult,
    reconstruct_route,
)


def ucs_shortest_path(
    graph: PreparedRoutingGraph,
    source: Any,
    target: Any,
) -> RouteResult:
    """Find a minimum-cost path using Uniform Cost Search."""
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

    distances = {source: 0.0}
    predecessor = {}
    settled = set()

    tie_breaker = count()
    heap = [(0.0, next(tie_breaker), source)]

    while heap:
        current_cost, _, u = heappop(heap)

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
            new_cost = current_cost + edge.cost

            if new_cost < distances.get(v, math.inf):
                distances[v] = new_cost
                predecessor[v] = (
                    u,
                    edge.key,
                    edge.length,
                )

                heappush(
                    heap,
                    (
                        new_cost,
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
