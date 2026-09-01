"""Tests for candidate intervention simulation."""

import networkx as nx
import pandas as pd
import pytest

from bike_improvements.interventions.simulate import (
    apply_candidate_intervention,
    compare_route_results,
)


def test_candidate_intervention_changes_both_directions():
    G = nx.MultiDiGraph()

    G.add_edge(
        "A",
        "B",
        osmid=10,
        length=100.0,
        cost=300.0,
        LTS=3,
        max_lts=3,
    )

    G.add_edge(
        "B",
        "A",
        osmid=10,
        length=100.0,
        cost=300.0,
        LTS=3,
        max_lts=3,
    )

    candidate = pd.Series(
        {
            "candidate_id": "C001",
            "node_a": "A",
            "node_b": "B",
            "osmid": "10",
        }
    )

    weights = {
        1: 1.0,
        2: 1.5,
        3: 3.0,
        4: 6.0,
    }

    modified = apply_candidate_intervention(
        G,
        candidate,
        weights,
        target_lts=2,
    )

    assert len(modified) == 2

    assert G.edges["A", "B", 0]["cost"] == 150.0
    assert G.edges["B", "A", 0]["cost"] == 150.0

    assert G.edges["A", "B", 0]["max_lts"] == 2


def test_route_comparison_computes_weighted_benefit():
    baseline = pd.DataFrame(
        [
            {
                "origin_node": "A",
                "destination_node": "B",
                "category": "home_school",
                "demand": 5.0,
                "found": True,
                "status": "routed",
                "route_cost": 300.0,
                "route_distance": 100.0,
                "route_edge_count": 1,
            }
        ]
    )

    intervention = pd.DataFrame(
        [
            {
                "origin_node": "A",
                "destination_node": "B",
                "category": "home_school",
                "demand": 5.0,
                "found": True,
                "status": "routed",
                "route_cost": 150.0,
                "route_distance": 100.0,
                "route_edge_count": 1,
            }
        ]
    )

    result = compare_route_results(
        baseline,
        intervention,
    )

    row = result.iloc[0]

    assert row["cost_reduction"] == 150.0
    assert row["demand_weighted_cost_reduction"] == 750.0
    assert row["improved"]

def test_route_comparison_rejects_extra_intervention_row():
    baseline = pd.DataFrame(
        [
            {
                "origin_node": "A",
                "destination_node": "B",
                "category": "home_school",
                "demand": 5.0,
                "found": True,
                "status": "routed",
                "route_cost": 300.0,
                "route_distance": 100.0,
                "route_edge_count": 1,
            }
        ]
    )

    intervention = pd.concat(
        [
            baseline.copy(),
            pd.DataFrame(
                [
                    {
                        **baseline.iloc[0].to_dict(),
                        "destination_node": "C",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )

    with pytest.raises(
        ValueError,
        match="OD row counts differ",
    ):
        compare_route_results(
            baseline,
            intervention,
        )

