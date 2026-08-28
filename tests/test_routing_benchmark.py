"""Tests for the UCS/A* benchmark layer."""

import math

import networkx as nx
import pandas as pd

from bike_improvements.routing.benchmark import benchmark_routing
from bike_improvements.routing.common import prepare_routing_graph


def build_test_graph():
    G = nx.MultiDiGraph()

    G.add_node("A", x=-71.000, y=42.000)
    G.add_node("B", x=-70.999, y=42.000)
    G.add_node("C", x=-70.998, y=42.000)

    G.add_edge("A", "B", cost=100.0, length=100.0)
    G.add_edge("B", "C", cost=100.0, length=100.0)
    G.add_edge("A", "C", cost=300.0, length=250.0)

    return G


def test_benchmark_runs_both_algorithms():
    graph = prepare_routing_graph(build_test_graph())

    od = pd.DataFrame(
        [
            {
                "origin_node": "A",
                "destination_node": "C",
                "category": "home_school",
                "count": 2,
            }
        ]
    )

    results = benchmark_routing(graph, od)

    assert len(results) == 2
    assert set(results["algorithm"]) == {"ucs", "astar"}
    assert results["found"].all()

    costs = dict(
        zip(
            results["algorithm"],
            results["route_cost"],
        )
    )

    assert math.isclose(costs["ucs"], 200.0)
    assert math.isclose(costs["astar"], 200.0)
    assert math.isclose(costs["ucs"], costs["astar"])


def test_benchmark_preserves_od_metadata():
    graph = prepare_routing_graph(build_test_graph())

    od = pd.DataFrame(
        [
            {
                "origin_node": "A",
                "destination_node": "C",
                "category": "home_healthcare",
                "count": 5,
            }
        ]
    )

    results = benchmark_routing(graph, od)

    assert set(results["category"]) == {"home_healthcare"}
    assert set(results["demand"]) == {5}
