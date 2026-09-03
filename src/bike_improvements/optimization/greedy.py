"""Utilities for greedy combinations of bicycle interventions."""

from __future__ import annotations

from collections.abc import Iterable

import networkx as nx
import pandas as pd

from bike_improvements.interventions.simulate import (
    apply_candidate_intervention,
)


def candidate_rows(
    candidates: pd.DataFrame,
    candidate_ids: Iterable[str],
) -> pd.DataFrame:
    """Return candidate rows in the requested order."""
    ids = list(candidate_ids)

    if not ids:
        raise ValueError("At least one candidate is required.")

    if len(ids) != len(set(ids)):
        raise ValueError("Candidate IDs must be unique.")

    indexed = candidates.set_index("candidate_id", drop=False)

    missing = [candidate_id for candidate_id in ids if candidate_id not in indexed.index]

    if missing:
        raise ValueError(f"Unknown candidate IDs: {missing}")

    return indexed.loc[ids].copy()


def apply_candidate_set(
    G: nx.MultiDiGraph,
    candidates: pd.DataFrame,
    candidate_ids: Iterable[str],
    lts_weights: dict[int, float],
    *,
    target_lts: int = 2,
) -> pd.DataFrame:
    """Apply every intervention in a candidate package."""
    rows = candidate_rows(
        candidates,
        candidate_ids,
    )

    records = []

    for _, candidate in rows.iterrows():
        modified = apply_candidate_intervention(
            G,
            candidate,
            lts_weights,
            target_lts=target_lts,
        )

        records.append(
            {
                "candidate_id": candidate["candidate_id"],
                "length_m": float(candidate["length_m"]),
                "modified_directed_edges": len(modified),
            }
        )

    return pd.DataFrame(records)


def package_metadata(
    candidates: pd.DataFrame,
    candidate_ids: Iterable[str],
) -> dict:
    """Return stable metadata for a candidate package."""
    rows = candidate_rows(
        candidates,
        candidate_ids,
    )

    ids = rows["candidate_id"].astype(str).tolist()

    return {
        "combination_id": "+".join(ids),
        "candidate_ids": ";".join(ids),
        "project_count": len(ids),
        "cumulative_length_m": float(rows["length_m"].sum()),
    }
