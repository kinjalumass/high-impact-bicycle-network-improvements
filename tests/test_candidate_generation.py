"""Tests for candidate infrastructure screening."""

import networkx as nx
import pandas as pd

from bike_improvements.candidates.generate import (
    PROFILE_ORDER,
    build_candidate_screening,
    select_candidates,
)


def build_graph():
    G = nx.MultiDiGraph()

    coords = {
        "A": (-71.00, 42.00),
        "B": (-70.99, 42.00),
        "C": (-70.98, 42.00),
        "D": (-70.97, 42.00),
        "E": (-70.96, 42.00),
        "F": (-70.95, 42.00),
    }

    for node, (x, y) in coords.items():
        G.add_node(node, x=x, y=y)

    # Two low-stress islands.
    G.add_edge(
        "A", "B",
        osmid=1,
        name="Safe West",
        length=100,
        cost=100,
        LTS=1,
        max_lts=1,
    )

    G.add_edge(
        "C", "D",
        osmid=2,
        name="Safe East",
        length=100,
        cost=100,
        LTS=1,
        max_lts=1,
    )

    # High-stress bridge.
    G.add_edge(
        "B", "C",
        osmid=10,
        name="Bridge Street",
        length=100,
        cost=300,
        LTS=3,
        max_lts=3,
    )

    G.add_edge(
        "C", "B",
        osmid=10,
        name="Bridge Street",
        length=100,
        cost=300,
        LTS=3,
        max_lts=3,
    )

    # Separate high-stress segment.
    G.add_edge(
        "E", "F",
        osmid=20,
        name="Traffic Road",
        length=100,
        cost=500,
        LTS=4,
        max_lts=4,
    )

    return G


def usage_for_graph(G):
    rows = []

    for profile in PROFILE_ORDER:
        for u, v, key, data in G.edges(
            keys=True,
            data=True,
        ):
            path_count = 0

            if {u, v} == {"B", "C"}:
                path_count = 10

            if {u, v} == {"E", "F"}:
                path_count = 20

            rows.append(
                {
                    "edge_id": f"{u}|{v}|{key}",
                    "rider_profile": profile,
                    "path_count": path_count,
                    "profile_preliminary_benefit": (
                        path_count
                        * max(
                            data["cost"] - data["length"],
                            0,
                        )
                    ),
                }
            )

    return pd.DataFrame(rows)


def test_screening_finds_connectivity_bridge():
    G = build_graph()

    screening = build_candidate_screening(
        G,
        usage_for_graph(G),
        eligible_lts={3, 4},
    )

    bridge = screening.loc[
        screening["street_name"] == "Bridge Street"
    ].iloc[0]

    assert bridge["current_lts"] == 3
    assert bridge["connects_safe_components"]
    assert bridge["modeled_demand"] == 20


def test_selection_respects_maximum():
    G = build_graph()

    screening = build_candidate_screening(
        G,
        usage_for_graph(G),
    )

    selected = select_candidates(
        screening,
        maximum_candidates=2,
        connectivity_reserve=1,
    )

    assert len(selected) == 2
    assert selected["candidate_id"].is_unique
    assert "Bridge Street" in set(
        selected["location"]
    )


def test_mixed_lts_simplified_segment_is_excluded():
    G = build_graph()

    G.add_edge(
        "A",
        "D",
        osmid=[30, 31],
        name="Mixed Corridor",
        length=300,
        cost=500,
        LTS=[2, 3],
        max_lts=3,
    )

    usage = usage_for_graph(G)

    screening = build_candidate_screening(
        G,
        usage,
        eligible_lts={3, 4},
    )

    assert "Mixed Corridor" not in set(
        screening["street_name"]
    )
