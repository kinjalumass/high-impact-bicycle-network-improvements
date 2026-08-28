"""Tests for full baseline one-to-many routing."""

import math

import networkx as nx
import pandas as pd

from bike_improvements.baseline.one_to_many import (
    edge_usage_dataframe,
    run_one_to_many_baseline,
)


def build_graph():
    G = nx.MultiDiGraph()

    G.add_edge(
        "A",
        "B",
        cost=100.0,
        length=100.0,
        LTS=1,
        max_lts=1,
    )

    G.add_edge(
        "B",
        "C",
        cost=200.0,
        length=100.0,
        LTS=2,
        max_lts=2,
    )

    G.add_edge(
        "A",
        "C",
        cost=500.0,
        length=150.0,
        LTS=3,
        max_lts=3,
    )

    return G


def test_one_search_preserves_od_metadata():
    G = build_graph()

    od = pd.DataFrame(
        [
            {
                "origin_node": "A",
                "destination_node": "C",
                "category": "home_school",
                "count": 2,
            },
            {
                "origin_node": "A",
                "destination_node": "C",
                "category": "home_healthcare",
                "count": 3,
            },
        ]
    )

    routes, loads, refs, stats, _ = run_one_to_many_baseline(
        G,
        od,
        workers=1,
    )

    assert len(routes) == 2
    assert routes["found"].all()

    assert set(routes["category"]) == {
        "home_school",
        "home_healthcare",
    }

    assert set(routes["route_cost"]) == {300.0}
    assert set(routes["route_distance"]) == {200.0}

    usage = edge_usage_dataframe(
        G,
        refs,
        loads,
    )

    used = usage.loc[usage["path_count"] > 0]

    assert len(used) == 2
    assert set(used["path_count"]) == {5.0}

    assert len(stats) == 1


def test_unreachable_destination_is_preserved():
    G = build_graph()
    G.add_node("D")

    od = pd.DataFrame(
        [
            {
                "origin_node": "A",
                "destination_node": "D",
                "category": "home_office",
                "count": 4,
            }
        ]
    )

    routes, _, _, _, _ = run_one_to_many_baseline(
        G,
        od,
        workers=1,
    )

    row = routes.iloc[0]

    assert not row["found"]
    assert row["status"] == "no_path"
    assert math.isnan(row["route_cost"])
