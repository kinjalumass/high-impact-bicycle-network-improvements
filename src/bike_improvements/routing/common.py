"""Shared routing structures and utilities."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import networkx as nx


@dataclass(frozen=True)
class EdgeStep:
    """One usable directed edge in the prepared routing graph."""

    neighbor: Any
    cost: float
    length: float
    key: Any = None


@dataclass
class PreparedRoutingGraph:
    """Compact representation used by UCS and A*."""

    adjacency: dict[Any, tuple[EdgeStep, ...]]
    coordinates: dict[Any, tuple[float, float]]
    min_cost_per_meter: float


@dataclass
class RouteResult:
    """Result returned by a routing algorithm."""

    source: Any
    target: Any
    found: bool
    route_cost: float
    route_distance: float
    nodes_expanded: int
    node_path: list[Any]
    edge_path: list[tuple[Any, Any, Any]]


def prepare_routing_graph(
    G: nx.Graph,
    cost_attr: str = "cost",
    length_attr: str = "length",
) -> PreparedRoutingGraph:
    """
    Convert a NetworkX graph into a compact routing structure.

    For MultiDiGraphs, the minimum-cost parallel edge between each ordered
    pair of nodes is used, matching the behavior of the inherited BCU
    routing implementation.
    """
    adjacency: dict[Any, tuple[EdgeStep, ...]] = {}
    ratios: list[float] = []

    for u in G.nodes:
        neighbors: list[EdgeStep] = []

        if G.is_multigraph():
            for v, keyed_edges in G[u].items():
                valid_edges = []

                for key, data in keyed_edges.items():
                    if cost_attr not in data:
                        raise ValueError(
                            f"Edge {(u, v, key)} has no {cost_attr!r} attribute."
                        )

                    cost = float(data[cost_attr])
                    length = float(data.get(length_attr, 0.0))

                    _validate_edge(u, v, key, cost, length)

                    valid_edges.append((key, cost, length))

                key, cost, length = min(
                    valid_edges,
                    key=lambda item: item[1],
                )

                neighbors.append(
                    EdgeStep(
                        neighbor=v,
                        cost=cost,
                        length=length,
                        key=key,
                    )
                )

                if length > 0:
                    ratios.append(cost / length)

        else:
            for v, data in G[u].items():
                if cost_attr not in data:
                    raise ValueError(
                        f"Edge {(u, v)} has no {cost_attr!r} attribute."
                    )

                cost = float(data[cost_attr])
                length = float(data.get(length_attr, 0.0))

                _validate_edge(u, v, None, cost, length)

                neighbors.append(
                    EdgeStep(
                        neighbor=v,
                        cost=cost,
                        length=length,
                    )
                )

                if length > 0:
                    ratios.append(cost / length)

        adjacency[u] = tuple(neighbors)

    coordinates = {}

    for node, data in G.nodes(data=True):
        if "x" in data and "y" in data:
            coordinates[node] = (
                float(data["y"]),  # latitude
                float(data["x"]),  # longitude
            )

    min_cost_per_meter = min(ratios) if ratios else 0.0

    return PreparedRoutingGraph(
        adjacency=adjacency,
        coordinates=coordinates,
        min_cost_per_meter=min_cost_per_meter,
    )


def _validate_edge(
    u: Any,
    v: Any,
    key: Any,
    cost: float,
    length: float,
) -> None:
    """Validate routing edge data."""
    edge_id = (u, v, key) if key is not None else (u, v)

    if not math.isfinite(cost):
        raise ValueError(f"Edge {edge_id} has non-finite cost {cost}.")

    if cost < 0:
        raise ValueError(
            f"Edge {edge_id} has negative cost {cost}. "
            "UCS/A* require nonnegative costs."
        )

    if not math.isfinite(length) or length < 0:
        raise ValueError(
            f"Edge {edge_id} has invalid physical length {length}."
        )


def reconstruct_route(
    source: Any,
    target: Any,
    predecessor: dict[Any, tuple[Any, Any, float]],
) -> tuple[list[Any], list[tuple[Any, Any, Any]], float]:
    """Reconstruct node path, edge path, and total physical distance."""
    node_path = [target]
    edge_path = []
    total_distance = 0.0

    current = target

    while current != source:
        if current not in predecessor:
            return [], [], math.inf

        parent, edge_key, length = predecessor[current]

        edge_path.append((parent, current, edge_key))
        total_distance += length

        current = parent
        node_path.append(current)

    node_path.reverse()
    edge_path.reverse()

    return node_path, edge_path, total_distance


def great_circle_distance_m(
    coord1: tuple[float, float],
    coord2: tuple[float, float],
) -> float:
    """Great-circle distance in meters between two latitude/longitude points."""
    lat1, lon1 = coord1
    lat2, lon2 = coord2

    radius_m = 6_371_008.8

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)

    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1)
        * math.cos(phi2)
        * math.sin(dlambda / 2.0) ** 2
    )

    return 2.0 * radius_m * math.asin(math.sqrt(a))
