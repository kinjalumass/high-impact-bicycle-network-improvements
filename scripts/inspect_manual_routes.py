"""Inspect exact UCS and A* route paths for representative OD pairs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import networkx as nx
import osmnx as ox
import pandas as pd

from bike_improvements.project_paths import final_root

from bike_improvements.routing import (
    astar_shortest_path,
    prepare_routing_graph,
    ucs_shortest_path,
)


DEFAULT_GRAPH = str(
    final_root()
    / "output"
    / "cost_scenarios"
    / "cost_scenario_1"
    / "greater_boston_cost_scenario_1_simplified.graphml"
)

RESULTS = Path("results/routing")


def path_preview(path: list[str], n: int = 5) -> str:
    if len(path) <= 2 * n:
        return " -> ".join(map(str, path))

    first = " -> ".join(map(str, path[:n]))
    last = " -> ".join(map(str, path[-n:]))

    return f"{first} -> ... -> {last}"


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--graph",
        default=DEFAULT_GRAPH,
        help="Baseline simplified routing graph.",
    )

    args = parser.parse_args()

    checks_path = RESULTS / "manual_route_checks.csv"

    checks = pd.read_csv(
        checks_path,
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    print("Loading graph:")
    print(args.graph)

    G = ox.load_graphml(
        args.graph,
        edge_dtypes={
            "cost": float,
            "length": float,
        },
    )

    G = nx.relabel_nodes(
        G,
        {
            node: str(node)
            for node in G.nodes
        },
        copy=True,
    )

    print(
        f"Graph: "
        f"{G.number_of_nodes():,} nodes, "
        f"{G.number_of_edges():,} edges"
    )

    prepared = prepare_routing_graph(G)

    records = []
    markdown = [
        "# Manual UCS/A* Route Checks",
        "",
        (
            "Five representative routable OD pairs were selected "
            "from the deterministic routing benchmark. UCS and A* "
            "were rerun on the same baseline graph and their complete "
            "node and directed-edge sequences were compared."
        ),
        "",
    ]

    for row in checks.itertuples(index=False):
        check_id = str(row.manual_check_id)
        source = str(row.origin_node)
        target = str(row.destination_node)

        print()
        print("=" * 80)
        print(
            f"{check_id}: "
            f"{source} -> {target}"
        )

        ucs = ucs_shortest_path(
            prepared,
            source,
            target,
        )

        astar = astar_shortest_path(
            prepared,
            source,
            target,
        )

        if not ucs.found or not astar.found:
            raise AssertionError(
                f"{check_id}: expected both algorithms to find route."
            )

        cost_difference = abs(
            ucs.route_cost
            - astar.route_cost
        )

        distance_difference = abs(
            ucs.route_distance
            - astar.route_distance
        )

        same_node_path = (
            ucs.node_path
            == astar.node_path
        )

        same_edge_path = (
            ucs.edge_path
            == astar.edge_path
        )

        print(
            "UCS cost:",
            f"{ucs.route_cost:.6f}",
        )

        print(
            "A* cost:",
            f"{astar.route_cost:.6f}",
        )

        print(
            "Cost difference:",
            f"{cost_difference:.12f}",
        )

        print(
            "Distance:",
            f"{ucs.route_distance:.3f} m",
        )

        print(
            "Node count:",
            len(ucs.node_path),
        )

        print(
            "Edge count:",
            len(ucs.edge_path),
        )

        print(
            "Exact node path identical:",
            same_node_path,
        )

        print(
            "Exact edge path identical:",
            same_edge_path,
        )

        print(
            "UCS nodes expanded:",
            ucs.nodes_expanded,
        )

        print(
            "A* nodes expanded:",
            astar.nodes_expanded,
        )

        print(
            "Path preview:"
        )

        print(
            path_preview(
                [str(x) for x in ucs.node_path]
            )
        )

        records.append(
            {
                "manual_check_id":
                    check_id,
                "origin_node":
                    source,
                "destination_node":
                    target,
                "category":
                    row.category,
                "route_cost_ucs":
                    ucs.route_cost,
                "route_cost_astar":
                    astar.route_cost,
                "cost_difference":
                    cost_difference,
                "route_distance_ucs":
                    ucs.route_distance,
                "route_distance_astar":
                    astar.route_distance,
                "distance_difference":
                    distance_difference,
                "node_count":
                    len(ucs.node_path),
                "edge_count":
                    len(ucs.edge_path),
                "nodes_expanded_ucs":
                    ucs.nodes_expanded,
                "nodes_expanded_astar":
                    astar.nodes_expanded,
                "exact_node_path_match":
                    same_node_path,
                "exact_edge_path_match":
                    same_edge_path,
                "ucs_node_path_json":
                    json.dumps(
                        [
                            str(x)
                            for x in ucs.node_path
                        ]
                    ),
                "astar_node_path_json":
                    json.dumps(
                        [
                            str(x)
                            for x in astar.node_path
                        ]
                    ),
                "ucs_edge_path_json":
                    json.dumps(
                        [
                            [
                                str(u),
                                str(v),
                                str(key),
                            ]
                            for u, v, key
                            in ucs.edge_path
                        ]
                    ),
                "astar_edge_path_json":
                    json.dumps(
                        [
                            [
                                str(u),
                                str(v),
                                str(key),
                            ]
                            for u, v, key
                            in astar.edge_path
                        ]
                    ),
            }
        )

        markdown.extend(
            [
                f"## {check_id}",
                "",
                f"- Origin: `{source}`",
                f"- Destination: `{target}`",
                f"- Category: `{row.category}`",
                (
                    f"- Generalized route cost: "
                    f"{ucs.route_cost:.6f}"
                ),
                (
                    f"- Physical route distance: "
                    f"{ucs.route_distance:.3f} m"
                ),
                (
                    f"- Directed edges: "
                    f"{len(ucs.edge_path)}"
                ),
                (
                    f"- UCS nodes expanded: "
                    f"{ucs.nodes_expanded:,}"
                ),
                (
                    f"- A* nodes expanded: "
                    f"{astar.nodes_expanded:,}"
                ),
                (
                    f"- Exact node-path match: "
                    f"**{same_node_path}**"
                ),
                (
                    f"- Exact edge-path match: "
                    f"**{same_edge_path}**"
                ),
                "",
                "Path preview:",
                "",
                f"`{path_preview([str(x) for x in ucs.node_path])}`",
                "",
            ]
        )

    output = pd.DataFrame(records)

    output_path = (
        RESULTS
        / "manual_route_path_checks.csv"
    )

    output.to_csv(
        output_path,
        index=False,
    )

    markdown_path = (
        RESULTS
        / "manual_route_path_checks.md"
    )

    markdown_path.write_text(
        "\n".join(markdown).rstrip()
        + "\n"
    )

    print()
    print("=" * 80)

    print(
        "All exact node paths match:",
        bool(
            output[
                "exact_node_path_match"
            ].all()
        ),
    )

    print(
        "All exact edge paths match:",
        bool(
            output[
                "exact_edge_path_match"
            ].all()
        ),
    )

    print(
        "Maximum cost difference:",
        output["cost_difference"].max(),
    )

    print(
        "Maximum distance difference:",
        output[
            "distance_difference"
        ].max(),
    )

    print()
    print(
        "Saved:",
        output_path,
    )

    print(
        "Saved:",
        markdown_path,
    )


if __name__ == "__main__":
    main()
