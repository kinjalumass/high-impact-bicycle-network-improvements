"""Tests for greedy intervention package utilities."""

import networkx as nx
import pandas as pd
import pytest

from bike_improvements.optimization.greedy import (
    apply_candidate_set,
    candidate_rows,
    package_metadata,
)


def candidates():
    return pd.DataFrame(
        [
            {
                "candidate_id": "C001",
                "node_a": "A",
                "node_b": "B",
                "osmid": "1",
                "length_m": 100.0,
                "current_lts": 3,
            },
            {
                "candidate_id": "C002",
                "node_a": "B",
                "node_b": "C",
                "osmid": "2",
                "length_m": 50.0,
                "current_lts": 4,
            },
        ]
    )


def graph():
    G = nx.MultiDiGraph()

    G.add_edge(
        "A",
        "B",
        key=0,
        osmid="1",
        length=100.0,
        cost=300.0,
        LTS=3,
        max_lts=3,
    )

    G.add_edge(
        "B",
        "C",
        key=0,
        osmid="2",
        length=50.0,
        cost=300.0,
        LTS=4,
        max_lts=4,
    )

    return G


def test_package_metadata():
    result = package_metadata(
        candidates(),
        ["C001", "C002"],
    )

    assert result["combination_id"] == "C001+C002"
    assert result["candidate_ids"] == "C001;C002"
    assert result["project_count"] == 2
    assert result["cumulative_length_m"] == 150.0


def test_candidate_rows_preserves_requested_order():
    rows = candidate_rows(
        candidates(),
        ["C002", "C001"],
    )

    assert rows["candidate_id"].tolist() == [
        "C002",
        "C001",
    ]


def test_candidate_rows_rejects_duplicates():
    with pytest.raises(ValueError):
        candidate_rows(
            candidates(),
            ["C001", "C001"],
        )


def test_apply_candidate_set_updates_all_projects():
    G = graph()

    modifications = apply_candidate_set(
        G,
        candidates(),
        ["C001", "C002"],
        {
            1: 1.0,
            2: 1.5,
            3: 3.0,
            4: 6.0,
        },
        target_lts=2,
    )

    assert len(modifications) == 2

    assert G["A"]["B"][0]["max_lts"] == 2
    assert G["B"]["C"][0]["max_lts"] == 2

    assert G["A"]["B"][0]["cost"] == 150.0
    assert G["B"]["C"][0]["cost"] == 75.0
