"""Create rider-profile-specific bicycle routing graphs."""

from __future__ import annotations

import copy
import math
from typing import Any

import networkx as nx
import osmnx as ox
import pandas as pd


NO_ACCESS_WEIGHT = 100.0


def normalize_lts(value: Any) -> int | None:
    """Convert a stored LTS value to an integer level when possible."""
    if value is None or value == "":
        return None

    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass

    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def stress_weight(
    lts_value: Any,
    lts_weights: dict[int, float],
) -> float:
    """
    Return the profile-specific multiplier for an LTS value.

    Unknown LTS and LTS 0 use the configured no-access penalty.
    """
    level = normalize_lts(lts_value)

    if level is None or level == 0:
        return NO_ACCESS_WEIGHT

    return float(lts_weights.get(level, NO_ACCESS_WEIGHT))


def apply_profile_costs(
    G: nx.MultiDiGraph,
    lts_weights: dict[int, float],
    *,
    copy_graph: bool = True,
) -> nx.MultiDiGraph:
    """Recalculate edge costs for one rider profile."""
    H = copy.deepcopy(G) if copy_graph else G

    for u, v, key, data in H.edges(keys=True, data=True):
        if "length" not in data:
            raise ValueError(
                f"Edge {(u, v, key)} is missing physical length."
            )

        length = float(data["length"])

        if not math.isfinite(length) or length < 0:
            raise ValueError(
                f"Edge {(u, v, key)} has invalid length {length}."
            )

        multiplier = stress_weight(
            data.get("LTS"),
            lts_weights,
        )

        data["cost"] = length * multiplier

    return H


def _max_lts(values: list[Any]) -> int | str:
    """
    Return the worst LTS value across segments being simplified.

    LTS 0 represents no bike access and therefore outranks levels 1-4.
    """
    levels = []

    for value in values:
        level = normalize_lts(value)

        if level is None:
            continue

        if level == 0:
            return 0

        levels.append(level)

    return max(levels) if levels else ""


def simplify_profile_graph(
    G: nx.MultiDiGraph,
) -> nx.MultiDiGraph:
    """Simplify a profile graph while preserving summed cost and length."""
    for _, _, data in G.edges(data=True):
        data["max_lts"] = data.get("LTS", "")

    return ox.simplify_graph(
        G,
        edge_attr_aggs={
            "cost": sum,
            "length": sum,
            "max_lts": _max_lts,
        },
    )


def build_profile_graph(
    G: nx.MultiDiGraph,
    lts_weights: dict[int, float],
) -> nx.MultiDiGraph:
    """Apply rider weights and return the corresponding simplified graph."""
    weighted = apply_profile_costs(
        G,
        lts_weights,
        copy_graph=True,
    )

    return simplify_profile_graph(weighted)
