"""Tests for rider-profile graph construction."""

import math

import networkx as nx

from bike_improvements.baseline.profile_graph import (
    NO_ACCESS_WEIGHT,
    apply_profile_costs,
    stress_weight,
)


def test_stress_weight():
    weights = {
        1: 1.0,
        2: 1.5,
        3: 3.0,
        4: 6.0,
    }

    assert stress_weight(1, weights) == 1.0
    assert stress_weight("2", weights) == 1.5
    assert stress_weight(3.0, weights) == 3.0
    assert stress_weight(4, weights) == 6.0

    assert stress_weight(0, weights) == NO_ACCESS_WEIGHT
    assert stress_weight("", weights) == NO_ACCESS_WEIGHT
    assert stress_weight(None, weights) == NO_ACCESS_WEIGHT


def test_apply_profile_costs():
    G = nx.MultiDiGraph()

    G.add_edge(
        "A",
        "B",
        length=100.0,
        LTS=1,
        cost=999.0,
    )

    G.add_edge(
        "B",
        "C",
        length=200.0,
        LTS=3,
        cost=999.0,
    )

    weights = {
        1: 1.0,
        2: 1.5,
        3: 3.0,
        4: 6.0,
    }

    H = apply_profile_costs(G, weights)

    assert math.isclose(
        H.edges["A", "B", 0]["cost"],
        100.0,
    )

    assert math.isclose(
        H.edges["B", "C", 0]["cost"],
        600.0,
    )

    # Original graph must not be modified.
    assert G.edges["A", "B", 0]["cost"] == 999.0
