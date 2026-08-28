"""Generate infrastructure candidates from four-profile baseline routing."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd


PROFILE_ORDER = [
    "child",
    "low_confidence_adult",
    "typical_adult",
    "experienced_adult",
]


def normalize_lts(value: Any) -> int | None:
    """Normalize stored LTS values."""
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



def normalize_lts_values(value: Any) -> set[int]:
    """Return all LTS levels represented by a GraphML edge attribute."""
    if value is None or value == "":
        return set()

    if isinstance(value, (list, tuple, set)):
        values = value
    else:
        text = str(value).strip()

        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            parsed = value

        values = (
            parsed
            if isinstance(parsed, (list, tuple, set))
            else [parsed]
        )

    levels = set()

    for item in values:
        try:
            levels.add(int(float(item)))
        except (TypeError, ValueError):
            continue

    return levels

def normalize_key(value: Any) -> str:
    """Normalize GraphML/CSV edge keys."""
    try:
        return str(int(float(value)))
    except (TypeError, ValueError):
        return str(value)


def canonical_osmid(value: Any) -> str:
    """Return a stable string representation for an OSM identifier."""
    if value is None:
        return ""

    return str(value).strip()


def edge_metadata_dataframe(G: nx.Graph) -> pd.DataFrame:
    """Extract graph metadata needed for physical candidate segments."""
    records = []

    if not G.is_multigraph():
        raise ValueError(
            "Candidate generation currently expects a MultiDiGraph."
        )

    for u, v, key, data in G.edges(
        keys=True,
        data=True,
    ):
        u = str(u)
        v = str(v)

        node_a, node_b = sorted([u, v])

        osmid = canonical_osmid(
            data.get("osmid")
        )

        physical_id = (
            f"{node_a}|{node_b}|{osmid}"
        )

        u_data = G.nodes[u]
        v_data = G.nodes[v]

        lat = (
            float(u_data["y"])
            + float(v_data["y"])
        ) / 2.0

        lon = (
            float(u_data["x"])
            + float(v_data["x"])
        ) / 2.0

        records.append(
            {
                "edge_id": (
                    f"{u}|{v}|{normalize_key(key)}"
                ),
                "physical_id": physical_id,
                "node_a": node_a,
                "node_b": node_b,
                "u": u,
                "v": v,
                "key": normalize_key(key),
                "osmid": osmid,
                "street_name": str(
                    data.get("name", "")
                ).strip(),
                "length_m": float(
                    data["length"]
                ),
                "current_lts": normalize_lts(
                    data.get(
                        "max_lts",
                        data.get("LTS"),
                    )
                ),
                "underlying_lts_values": ",".join(
                    str(level)
                    for level in sorted(
                        {
                            int(float(item))
                            for item in (
                                data.get("LTS")
                                if isinstance(
                                    data.get("LTS"),
                                    (list, tuple, set),
                                )
                                else [data.get("LTS")]
                            )
                            if item not in (None, "")
                        }
                    )
                ),
                "mixed_lts": (
                    len(
                        {
                            int(float(item))
                            for item in (
                                data.get("LTS")
                                if isinstance(
                                    data.get("LTS"),
                                    (list, tuple, set),
                                )
                                else [data.get("LTS")]
                            )
                            if item not in (None, "")
                        }
                    )
                    > 1
                ),
                "latitude": lat,
                "longitude": lon,
            }
        )

    return pd.DataFrame(records)


def load_baseline_edge_usage(
    baseline_root: str | Path,
) -> pd.DataFrame:
    """Load edge usage from all four rider-profile baselines."""
    root = Path(baseline_root)

    frames = []

    for profile in PROFILE_ORDER:
        path = root / profile / "edge_usage.csv"

        if not path.exists():
            raise FileNotFoundError(
                f"Missing baseline edge usage: {path}"
            )

        df = pd.read_csv(
            path,
            dtype={
                "u": str,
                "v": str,
            },
        )

        required = {
            "u",
            "v",
            "key",
            "path_count",
            "cost",
            "length",
        }

        missing = required - set(df.columns)

        if missing:
            raise ValueError(
                f"{path} missing columns: {sorted(missing)}"
            )

        df["rider_profile"] = profile

        df["key"] = df["key"].map(
            normalize_key
        )

        df["edge_id"] = (
            df["u"].astype(str)
            + "|"
            + df["v"].astype(str)
            + "|"
            + df["key"]
        )

        df["path_count"] = pd.to_numeric(
            df["path_count"],
            errors="raise",
        )

        df["cost"] = pd.to_numeric(
            df["cost"],
            errors="raise",
        )

        df["length"] = pd.to_numeric(
            df["length"],
            errors="raise",
        )

        df["stress_penalty"] = np.maximum(
            df["cost"] - df["length"],
            0.0,
        )

        df["profile_preliminary_benefit"] = (
            df["path_count"]
            * df["stress_penalty"]
        )

        frames.append(
            df[
                [
                    "edge_id",
                    "rider_profile",
                    "path_count",
                    "profile_preliminary_benefit",
                ]
            ]
        )

    return pd.concat(
        frames,
        ignore_index=True,
    )


def safe_component_map(
    G: nx.Graph,
) -> dict[str, int]:
    """
    Map nodes to connected components in the LTS 1-2 network.

    Connectivity is evaluated undirected because this stage asks whether
    an infrastructure segment bridges low-stress network islands, not
    whether a particular directed trip is currently feasible.
    """
    safe = nx.Graph()

    for u, v, data in G.edges(data=True):
        level = normalize_lts(
            data.get(
                "max_lts",
                data.get("LTS"),
            )
        )

        if level in {1, 2}:
            safe.add_edge(
                str(u),
                str(v),
            )

    components = sorted(
        nx.connected_components(safe),
        key=len,
        reverse=True,
    )

    mapping = {}

    for component_id, nodes in enumerate(
        components
    ):
        for node in nodes:
            mapping[str(node)] = component_id

    return mapping


def _first_nonempty(values: pd.Series) -> str:
    """Choose one useful text value from a group."""
    for value in values:
        text = str(value).strip()

        if text and text.lower() != "nan":
            return text

    return ""


def build_candidate_screening(
    G: nx.Graph,
    baseline_usage: pd.DataFrame,
    eligible_lts: set[int] | None = None,
) -> pd.DataFrame:
    """Build one row per physical high-stress segment."""
    if eligible_lts is None:
        eligible_lts = {3, 4}

    metadata = edge_metadata_dataframe(G)

    merged = baseline_usage.merge(
        metadata,
        on="edge_id",
        how="left",
        validate="many_to_one",
    )

    if merged["physical_id"].isna().any():
        missing = int(
            merged["physical_id"].isna().sum()
        )

        raise ValueError(
            f"{missing} baseline edge rows could not "
            "be matched to graph metadata."
        )

    profile_stats = (
        merged.groupby(
            [
                "physical_id",
                "rider_profile",
            ],
            as_index=False,
        )
        .agg(
            profile_modeled_demand=(
                "path_count",
                "sum",
            ),
            profile_preliminary_benefit=(
                "profile_preliminary_benefit",
                "sum",
            ),
        )
    )

    demand = profile_stats.pivot(
        index="physical_id",
        columns="rider_profile",
        values="profile_modeled_demand",
    ).fillna(0.0)

    benefit = profile_stats.pivot(
        index="physical_id",
        columns="rider_profile",
        values="profile_preliminary_benefit",
    ).fillna(0.0)

    for profile in PROFILE_ORDER:
        if profile not in demand:
            demand[profile] = 0.0

        if profile not in benefit:
            benefit[profile] = 0.0

    demand = demand[
        PROFILE_ORDER
    ].rename(
        columns={
            profile: f"demand_{profile}"
            for profile in PROFILE_ORDER
        }
    )

    benefit = benefit[
        PROFILE_ORDER
    ].rename(
        columns={
            profile: f"benefit_{profile}"
            for profile in PROFILE_ORDER
        }
    )

    physical = (
        metadata.groupby(
            "physical_id",
            as_index=False,
        )
        .agg(
            node_a=("node_a", "first"),
            node_b=("node_b", "first"),
            osmid=("osmid", _first_nonempty),
            street_name=(
                "street_name",
                _first_nonempty,
            ),
            length_m=("length_m", "max"),
            current_lts=("current_lts", "max"),
            underlying_lts_values=(
                "underlying_lts_values",
                _first_nonempty,
            ),
            mixed_lts=("mixed_lts", "max"),
            latitude=("latitude", "mean"),
            longitude=("longitude", "mean"),
            directed_edge_count=(
                "edge_id",
                "nunique",
            ),
        )
    )

    result = (
        physical
        .merge(
            demand.reset_index(),
            on="physical_id",
            how="left",
        )
        .merge(
            benefit.reset_index(),
            on="physical_id",
            how="left",
        )
    )

    demand_columns = [
        f"demand_{profile}"
        for profile in PROFILE_ORDER
    ]

    benefit_columns = [
        f"benefit_{profile}"
        for profile in PROFILE_ORDER
    ]

    result[demand_columns] = (
        result[demand_columns]
        .fillna(0.0)
    )

    result[benefit_columns] = (
        result[benefit_columns]
        .fillna(0.0)
    )

    result["modeled_demand"] = (
        result[demand_columns].mean(axis=1)
    )

    result["preliminary_benefit"] = (
        result[benefit_columns].mean(axis=1)
    )

    component_map = safe_component_map(G)

    result["safe_component_a"] = (
        result["node_a"].map(component_map)
    )

    result["safe_component_b"] = (
        result["node_b"].map(component_map)
    )

    result["connects_safe_components"] = (
        result["safe_component_a"].notna()
        & result["safe_component_b"].notna()
        & (
            result["safe_component_a"]
            != result["safe_component_b"]
        )
    )

    result = result.loc[
        result["current_lts"].isin(
            eligible_lts
        )
    ].copy()

    # An intervention candidate must represent a homogeneous
    # high-stress simplified segment. Mixed chains can contain
    # substantial existing LTS 1-2 infrastructure and would
    # otherwise overstate improvement length and benefit.
    result = result.loc[
        ~result["mixed_lts"]
    ].copy()

    # No current usage and no direct low-stress connectivity signal gives
    # us no evidence for screening this segment into the top candidates.
    result = result.loc[
        (result["modeled_demand"] > 0)
        | result["connects_safe_components"]
    ].copy()

    result["screening_rank"] = (
        result["preliminary_benefit"]
        .rank(
            method="first",
            ascending=False,
        )
        .astype(int)
    )

    result = result.sort_values(
        [
            "preliminary_benefit",
            "modeled_demand",
        ],
        ascending=False,
    ).reset_index(drop=True)

    return result


def select_candidates(
    screening: pd.DataFrame,
    maximum_candidates: int = 20,
    connectivity_reserve: int = 5,
) -> pd.DataFrame:
    """
    Select the final screening set.

    Most positions are chosen by the demand-weighted stress-penalty proxy.
    A small reserve ensures direct bridges between distinct LTS 1-2
    components are not discarded solely because current demand is low.
    """
    if maximum_candidates <= 0:
        raise ValueError(
            "maximum_candidates must be positive."
        )

    connectivity_reserve = max(
        0,
        min(
            connectivity_reserve,
            maximum_candidates,
        ),
    )

    primary_slots = (
        maximum_candidates
        - connectivity_reserve
    )

    ordered = screening.sort_values(
        [
            "preliminary_benefit",
            "modeled_demand",
        ],
        ascending=False,
    )

    primary = ordered.head(
        primary_slots
    ).copy()

    connectivity = (
        ordered.loc[
            ordered[
                "connects_safe_components"
            ]
        ]
        .loc[
            lambda df: ~df[
                "physical_id"
            ].isin(primary["physical_id"])
        ]
        .head(connectivity_reserve)
        .copy()
    )

    selected = pd.concat(
        [
            primary,
            connectivity,
        ],
        ignore_index=True,
    )

    if len(selected) < maximum_candidates:
        remaining = ordered.loc[
            ~ordered["physical_id"].isin(
                selected["physical_id"]
            )
        ].head(
            maximum_candidates
            - len(selected)
        )

        selected = pd.concat(
            [
                selected,
                remaining,
            ],
            ignore_index=True,
        )

    selected = selected.drop_duplicates(
        subset=["physical_id"]
    )

    selected = selected.sort_values(
        [
            "preliminary_benefit",
            "modeled_demand",
        ],
        ascending=False,
    ).head(maximum_candidates)

    selected = selected.reset_index(
        drop=True
    )

    selected["candidate_id"] = [
        f"C{i:03d}"
        for i in range(
            1,
            len(selected) + 1,
        )
    ]

    def reason(row) -> str:
        reasons = []

        if row["screening_rank"] <= primary_slots:
            reasons.append(
                "high demand-weighted stress penalty"
            )

        if row["connects_safe_components"]:
            reasons.append(
                "directly bridges distinct LTS 1-2 components"
            )

        if not reasons:
            reasons.append(
                "high preliminary screening benefit"
            )

        return "; ".join(reasons)

    selected["selection_reason"] = (
        selected.apply(
            reason,
            axis=1,
        )
    )

    selected["location"] = (
        selected["street_name"]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    missing_location = (
        selected["location"] == ""
    )

    selected.loc[
        missing_location,
        "location",
    ] = selected.loc[
        missing_location
    ].apply(
        lambda row: (
            f"{row['latitude']:.5f}, "
            f"{row['longitude']:.5f}"
        ),
        axis=1,
    )

    first_columns = [
        "candidate_id",
        "location",
        "length_m",
        "current_lts",
        "modeled_demand",
        "preliminary_benefit",
        "selection_reason",
        "physical_id",
        "node_a",
        "node_b",
        "osmid",
        "latitude",
        "longitude",
        "connects_safe_components",
        "screening_rank",
    ]

    remaining_columns = [
        column
        for column in selected.columns
        if column not in first_columns
    ]

    return selected[
        first_columns
        + remaining_columns
    ]
