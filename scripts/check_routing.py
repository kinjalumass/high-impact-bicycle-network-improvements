"""Small routing sanity check."""

import networkx as nx

from bike_improvements.routing import (
    astar_shortest_path,
    prepare_routing_graph,
    ucs_shortest_path,
)


G = nx.MultiDiGraph()
G.graph["crs"] = "EPSG:4326"

G.add_node("A", x=-71.0000, y=42.0000)
G.add_node("B", x=-70.9990, y=42.0000)
G.add_node("C", x=-70.9980, y=42.0000)
G.add_node("D", x=-70.9970, y=42.0000)

G.add_edge("A", "B", cost=100, length=100)
G.add_edge("B", "C", cost=100, length=100)
G.add_edge("C", "D", cost=100, length=100)
G.add_edge("A", "C", cost=350, length=250)
G.add_edge("A", "D", cost=600, length=400)

graph = prepare_routing_graph(G)

for name, algorithm in [
    ("UCS", ucs_shortest_path),
    ("A*", astar_shortest_path),
]:
    result = algorithm(graph, "A", "D")

    print(name)
    print(f"  found:          {result.found}")
    print(f"  route:          {result.node_path}")
    print(f"  route cost:     {result.route_cost}")
    print(f"  distance:       {result.route_distance}")
    print(f"  nodes expanded: {result.nodes_expanded}")
