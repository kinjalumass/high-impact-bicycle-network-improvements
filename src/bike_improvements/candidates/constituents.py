"""Map simplified candidate segments back to original OSM graph edges."""

from __future__ import annotations

import ast
import math
from collections import defaultdict
from typing import Any

import networkx as nx
import pandas as pd

from bike_improvements.candidates.generate import (
    edge_metadata_dataframe,
    normalize_lts,
)


def value_set(value: Any) -> set[str]:
    """Normalize scalar/list-like GraphML attributes to strings."""
    if value is None or value == "":
        return set()

    if isinstance(value, (list, tuple, set)):
        return {str(item) for item in value}

    text = str(value).strip()

    try:
        parsed = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return {text}

    if isinstance(parsed, (list, tuple, set)):
        return {str(item) for item in parsed}

    return {str(parsed)}


def build_osmid_index(
    G: nx.MultiDiGraph,
):
    """Index unsimplified directed edges by OSM identifier."""
    index = defaultdict(list)

    for u, v, key, data in G.edges(
        keys=True,
        data=True,
    ):
        for osmid in value_set(
            data.get("osmid")
        ):
            index[osmid].append(
                (
                    str(u),
                    str(v),
                    str(key),
                    data,
                )
            )

    return index


def reconstruct_simplified_edge(
    G_unsimplified: nx.MultiDiGraph,
    osmid_index,
    source: str,
    target: str,
    simplified_data: dict,
):
    """
    Reconstruct one simplified directed edge from original edges.

    Candidate OSM IDs restrict the search. The reconstructed total length
    must match the simplified edge length.
    """
    allowed_osmids = value_set(
        simplified_data.get("osmid")
    )

    if not allowed_osmids:
        raise ValueError(
            f"Simplified edge {source}->{target} has no OSM IDs."
        )

    H = nx.MultiDiGraph()

    seen = set()

    for osmid in allowed_osmids:
        for u, v, key, data in osmid_index.get(
            osmid,
            [],
        ):
            ref = (u, v, key)

            if ref in seen:
                continue

            seen.add(ref)

            H.add_edge(
                u,
                v,
                key=key,
                length=float(data["length"]),
                original_data=data,
            )

    if source not in H or target not in H:
        raise ValueError(
            f"Could not construct candidate subgraph "
            f"for {source}->{target}."
        )

    try:
        node_path = nx.shortest_path(
            H,
            source=source,
            target=target,
            weight="length",
        )
    except nx.NetworkXNoPath as exc:
        raise ValueError(
            f"No unsimplified path found for "
            f"{source}->{target}."
        ) from exc

    edges = []

    for sequence, (u, v) in enumerate(
        zip(
            node_path[:-1],
            node_path[1:],
        ),
        start=1,
    ):
        choices = H[u][v]

        key, selected = min(
            choices.items(),
            key=lambda item: float(
                item[1]["length"]
            ),
        )

        original = selected[
            "original_data"
        ]

        edges.append(
            {
                "sequence": sequence,
                "u": str(u),
                "v": str(v),
                "key": str(key),
                "length_m": float(
                    original["length"]
                ),
                "current_lts": normalize_lts(
                    original.get("LTS")
                ),
                "name": original.get("name"),
                "osmid": original.get("osmid"),
            }
        )

    reconstructed_length = sum(
        edge["length_m"]
        for edge in edges
    )

    expected_length = float(
        simplified_data["length"]
    )

    if not math.isclose(
        reconstructed_length,
        expected_length,
        rel_tol=1e-8,
        abs_tol=1e-5,
    ):
        raise ValueError(
            f"Length mismatch for {source}->{target}: "
            f"reconstructed={reconstructed_length}, "
            f"simplified={expected_length}"
        )

    return edges


def candidate_constituents_dataframe(
    G_unsimplified: nx.MultiDiGraph,
    G_simplified: nx.MultiDiGraph,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """Map every selected candidate to original directed edges."""
    # Normalize graph node IDs.
    nx.relabel_nodes(
        G_unsimplified,
        {
            node: str(node)
            for node in G_unsimplified.nodes
        },
        copy=False,
    )

    nx.relabel_nodes(
        G_simplified,
        {
            node: str(node)
            for node in G_simplified.nodes
        },
        copy=False,
    )

    osmid_index = build_osmid_index(
        G_unsimplified
    )

    metadata = edge_metadata_dataframe(
        G_simplified
    )

    records = []

    for candidate in candidates.itertuples(
        index=False
    ):
        matches = metadata.loc[
            metadata["physical_id"]
            == candidate.physical_id
        ]

        if matches.empty:
            raise ValueError(
                f"No simplified edge found for "
                f"{candidate.candidate_id}"
            )

        for simplified in matches.itertuples(
            index=False
        ):
            key = int(float(simplified.key))

            data = G_simplified.edges[
                simplified.u,
                simplified.v,
                key,
            ]

            reconstructed = (
                reconstruct_simplified_edge(
                    G_unsimplified,
                    osmid_index,
                    simplified.u,
                    simplified.v,
                    data,
                )
            )

            direction = (
                f"{simplified.u}->{simplified.v}"
            )

            for edge in reconstructed:
                node_a, node_b = sorted(
                    [
                        edge["u"],
                        edge["v"],
                    ]
                )

                physical_osmids = sorted(
                    value_set(edge["osmid"])
                )

                constituent_physical_id = (
                    f"{node_a}|{node_b}|"
                    f"{','.join(physical_osmids)}"
                )

                records.append(
                    {
                        "candidate_id":
                            candidate.candidate_id,
                        "candidate_location":
                            candidate.location,
                        "simplified_direction":
                            direction,
                        "sequence":
                            edge["sequence"],
                        "constituent_u":
                            edge["u"],
                        "constituent_v":
                            edge["v"],
                        "constituent_key":
                            edge["key"],
                        "constituent_physical_id":
                            constituent_physical_id,
                        "length_m":
                            edge["length_m"],
                        "current_lts":
                            edge["current_lts"],
                        "is_high_stress":
                            edge["current_lts"]
                            in {3, 4},
                        "name":
                            edge["name"],
                        "osmid":
                            edge["osmid"],
                    }
                )

    return pd.DataFrame(records)


def candidate_constituent_summary(
    constituents: pd.DataFrame,
    candidates: pd.DataFrame,
) -> pd.DataFrame:
    """Create physical-length and LTS summaries for candidates."""
    # Collapse reverse-direction duplicates into physical pieces.
    physical = (
        constituents.sort_values(
            [
                "candidate_id",
                "constituent_physical_id",
            ]
        )
        .drop_duplicates(
            [
                "candidate_id",
                "constituent_physical_id",
            ]
        )
        .copy()
    )

    rows = []

    for candidate in candidates.itertuples(
        index=False
    ):
        group = physical.loc[
            physical["candidate_id"]
            == candidate.candidate_id
        ].copy()

        high = group.loc[
            group["is_high_stress"]
        ]

        low = group.loc[
            ~group["is_high_stress"]
        ]

        lts_values = sorted(
            {
                int(value)
                for value in group[
                    "current_lts"
                ].dropna()
            }
        )

        high_names = sorted(
            {
                str(value)
                for value in high["name"].dropna()
                if str(value).strip()
            }
        )

        network_length = float(
            group["length_m"].sum()
        )

        improvement_length = float(
            high["length_m"].sum()
        )

        rows.append(
            {
                "candidate_id":
                    candidate.candidate_id,
                "location":
                    candidate.location,
                "simplified_length_m":
                    float(candidate.length_m),
                "reconstructed_physical_length_m":
                    network_length,
                "improvement_length_m":
                    improvement_length,
                "existing_low_stress_length_m":
                    float(
                        low["length_m"].sum()
                    ),
                "high_stress_fraction":
                    (
                        improvement_length
                        / network_length
                        if network_length
                        else 0.0
                    ),
                "underlying_lts_values":
                    ",".join(
                        str(value)
                        for value in lts_values
                    ),
                "mixed_lts":
                    len(lts_values) > 1,
                "physical_constituent_count":
                    len(group),
                "high_stress_names":
                    " | ".join(high_names),
            }
        )

    return pd.DataFrame(rows)
