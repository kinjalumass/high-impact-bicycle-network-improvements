"""Apply candidate LTS interventions and compare routing outcomes."""

from __future__ import annotations

from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

from bike_improvements.candidates.constituents import value_set
from bike_improvements.candidates.generate import (
    normalize_lts,
    normalize_lts_values,
)


ROUTE_KEYS = [
    "origin_node",
    "destination_node",
    "category",
]


def profile_weights(
    config: dict,
    profile: str,
) -> dict[int, float]:
    """Return normalized LTS weights for a rider profile."""
    raw = config["rider_profiles"][profile]["lts_weights"]

    return {
        int(level): float(weight)
        for level, weight in raw.items()
    }


def apply_candidate_intervention(
    G: nx.MultiDiGraph,
    candidate: pd.Series | dict[str, Any],
    lts_weights: dict[int, float],
    target_lts: int = 2,
) -> list[tuple[str, str, Any]]:
    """
    Lower one homogeneous physical candidate segment to target LTS.

    All matching directed edges are modified, so a bidirectional physical
    segment is improved in both directions.
    """
    candidate_nodes = {
        str(candidate["node_a"]),
        str(candidate["node_b"]),
    }

    candidate_osmids = value_set(
        candidate["osmid"]
    )

    if target_lts not in lts_weights:
        raise ValueError(
            f"No rider weight defined for target LTS {target_lts}."
        )

    modified = []

    for u, v, key, data in G.edges(
        keys=True,
        data=True,
    ):
        if {
            str(u),
            str(v),
        } != candidate_nodes:
            continue

        if value_set(
            data.get("osmid")
        ) != candidate_osmids:
            continue

        levels = normalize_lts_values(
            data.get("LTS")
        )

        current_lts = normalize_lts(
            data.get(
                "max_lts",
                data.get("LTS"),
            )
        )

        if len(levels) > 1:
            raise ValueError(
                "Mixed-LTS candidate reached intervention stage."
            )

        if current_lts not in {3, 4}:
            raise ValueError(
                f"Candidate edge has LTS {current_lts}, "
                "expected LTS 3 or 4."
            )

        if target_lts >= current_lts:
            raise ValueError(
                f"Target LTS {target_lts} does not improve "
                f"current LTS {current_lts}."
            )

        length = float(data["length"])

        data["cost"] = (
            length
            * float(lts_weights[target_lts])
        )

        data["LTS"] = target_lts
        data["max_lts"] = target_lts

        modified.append(
            (
                str(u),
                str(v),
                key,
            )
        )

    if not modified:
        raise ValueError(
            f"No graph edges matched candidate "
            f"{candidate['candidate_id']}."
        )

    return modified


def compare_route_results(
    baseline: pd.DataFrame,
    intervention: pd.DataFrame,
    tolerance: float = 1e-8,
) -> pd.DataFrame:
    """Compare baseline and intervention routes OD-by-OD."""
    baseline = baseline.copy()
    intervention = intervention.copy()

    for df in (baseline, intervention):
        df["origin_node"] = (
            df["origin_node"].astype(str)
        )
        df["destination_node"] = (
            df["destination_node"].astype(str)
        )

    b = baseline[
        ROUTE_KEYS
        + [
            "demand",
            "found",
            "status",
            "route_cost",
            "route_distance",
            "route_edge_count",
        ]
    ].rename(
        columns={
            "found": "baseline_found",
            "status": "baseline_status",
            "route_cost": "baseline_route_cost",
            "route_distance": "baseline_route_distance",
            "route_edge_count":
                "baseline_route_edge_count",
        }
    )

    i = intervention[
        ROUTE_KEYS
        + [
            "demand",
            "found",
            "status",
            "route_cost",
            "route_distance",
            "route_edge_count",
        ]
    ].rename(
        columns={
            "demand": "intervention_demand",
            "found": "intervention_found",
            "status": "intervention_status",
            "route_cost":
                "intervention_route_cost",
            "route_distance":
                "intervention_route_distance",
            "route_edge_count":
                "intervention_route_edge_count",
        }
    )

    if len(i) != len(b):
        raise ValueError(
            "Baseline/intervention OD row counts differ."
        )

    comparison = b.merge(
        i,
        on=ROUTE_KEYS,
        how="inner",
        validate="one_to_one",
    )

    if len(comparison) != len(b):
        raise ValueError(
            "Baseline/intervention OD rows did not match one-to-one."
        )

    if not np.allclose(
        comparison["demand"],
        comparison["intervention_demand"],
    ):
        raise ValueError(
            "Baseline/intervention demand differs."
        )

    comparison = comparison.drop(
        columns=["intervention_demand"]
    )

    comparable = (
        comparison["baseline_found"]
        & comparison["intervention_found"]
    )

    comparison["cost_reduction"] = np.nan
    comparison["distance_change_m"] = np.nan

    comparison.loc[
        comparable,
        "cost_reduction",
    ] = (
        comparison.loc[
            comparable,
            "baseline_route_cost",
        ]
        - comparison.loc[
            comparable,
            "intervention_route_cost",
        ]
    )

    comparison.loc[
        comparable,
        "distance_change_m",
    ] = (
        comparison.loc[
            comparable,
            "intervention_route_distance",
        ]
        - comparison.loc[
            comparable,
            "baseline_route_distance",
        ]
    )

    materially_worse = (
        comparison.loc[
            comparable,
            "cost_reduction",
        ]
        < -tolerance
    )

    if materially_worse.any():
        raise AssertionError(
            "Lowering candidate edge cost increased an optimal "
            "route cost for at least one OD pair."
        )

    comparison.loc[
        comparable,
        "cost_reduction",
    ] = (
        comparison.loc[
            comparable,
            "cost_reduction",
        ].clip(lower=0.0)
    )

    comparison["improved"] = (
        comparable
        & (
            comparison["cost_reduction"]
            > tolerance
        )
    )

    comparison[
        "demand_weighted_cost_reduction"
    ] = (
        comparison["cost_reduction"].fillna(0.0)
        * comparison["demand"]
    )

    comparison[
        "demand_weighted_distance_change_m"
    ] = (
        comparison["distance_change_m"].fillna(0.0)
        * comparison["demand"]
    )

    return comparison
