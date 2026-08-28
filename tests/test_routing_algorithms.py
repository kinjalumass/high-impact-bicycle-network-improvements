"""Tests for UCS and A* routing."""

import math

import networkx as nx

from bike_improvements.routing import (
    astar_shortest_path,
    prepare_routing_graph,
    ucs_shortest_path,
)


def build_test_graph():
    G = nx.MultiDiGraph()
    G.graph["crs"] = "EPSG:4326"

    G.add_node("A", x=-71.0000, y=42.0000)
    G.add_node("B", x=-70.9990, y=42.0000)
    G.add_node("C", x=-70.9980, y=42.0000)
    G.add_node("D", x=-70.9970, y=42.0000)

    # Optimal A -> B -> C -> D
    G.add_edge("A", "B", cost=100.0, length=100.0)
    G.add_edge("B", "C", cost=100.0, length=100.0)
    G.add_edge("C", "D", cost=100.0, length=100.0)

    # More expensive shortcuts
    G.add_edge("A", "C", cost=350.0, length=250.0)
    G.add_edge("A", "D", cost=600.0, length=400.0)

    return G


def test_ucs_finds_optimal_route():
    graph = prepare_routing_graph(build_test_graph())

    result = ucs_shortest_path(graph, "A", "D")

    assert result.found
    assert result.route_cost == 300.0
    assert result.route_distance == 300.0
    assert result.node_path == ["A", "B", "C", "D"]


def test_astar_finds_same_optimal_cost_as_ucs():
    graph = prepare_routing_graph(build_test_graph())

    ucs = ucs_shortest_path(graph, "A", "D")
    astar = astar_shortest_path(graph, "A", "D")

    assert astar.found
    assert math.isclose(astar.route_cost, ucs.route_cost)
    assert math.isclose(astar.route_distance, ucs.route_distance)


def test_same_source_and_target():
    graph = prepare_routing_graph(build_test_graph())

    result = ucs_shortest_path(graph, "A", "A")

    assert result.found
    assert result.route_cost == 0.0
    assert result.route_distance == 0.0


def test_parallel_edges_use_lowest_cost():
    G = build_test_graph()

    # More expensive parallel A -> B edge.
    G.add_edge("A", "B", cost=900.0, length=100.0)

    graph = prepare_routing_graph(G)

    result = ucs_shortest_path(graph, "A", "D")

    assert result.route_cost == 300.0
