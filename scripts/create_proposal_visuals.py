"""Create the final proposal-specific bicycle-network visuals."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

from bike_improvements.interventions.simulate import (
    apply_candidate_intervention,
)
from bike_improvements.routing import (
    prepare_routing_graph,
    ucs_shortest_path,
)


FIGURE_DIR = Path("reports/figures")
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

BASELINE_GRAPH = Path(
    "/work/pi_plunkett_umass_edu/bcu/course_project/"
    "profile_graphs/"
    "greater_boston_typical_adult_scenario_11_simplified.graphml"
)

EDGE_USAGE = Path(
    "/work/pi_plunkett_umass_edu/bcu/course_project/"
    "baselines/typical_adult/edge_usage.csv"
)

C001_COMPARISON = Path(
    "/work/pi_plunkett_umass_edu/bcu/course_project/"
    "interventions/C001/typical_adult/od_comparison.csv"
)

CANDIDATES = Path(
    "results/candidates/candidate_segments.csv"
)

# Baseline typical-adult profile: scenario 11.
TYPICAL_WEIGHTS = {
    1: 1.0,
    2: 1.3,
    3: 2.2,
    4: 4.0,
}

EXAMPLE_ORIGIN = "7686391002"
EXAMPLE_DESTINATION = "8502145362"


def normalize_graph_nodes(
    graph: nx.MultiDiGraph,
) -> nx.MultiDiGraph:
    return nx.relabel_nodes(
        graph,
        {
            node: str(node)
            for node in graph.nodes
        },
        copy=True,
    )


def geometry_xy(
    graph: nx.MultiDiGraph,
    u: str,
    v: str,
    key,
):
    """Return x/y coordinates for one graph edge."""
    data = None

    candidates = [
        key,
        str(key),
    ]

    try:
        candidates.append(int(key))
    except (TypeError, ValueError):
        pass

    edge_dict = graph.get_edge_data(
        str(u),
        str(v),
    )

    if edge_dict is None:
        return None

    for candidate_key in candidates:
        if candidate_key in edge_dict:
            data = edge_dict[candidate_key]
            break

    if data is None:
        # Prepared routing keeps only one minimum-cost parallel edge,
        # so falling back to the first parallel edge is suitable only
        # for visualization if key typing changed during GraphML load.
        data = next(
            iter(edge_dict.values())
        )

    geometry = data.get("geometry")

    if geometry is not None:
        return (
            list(geometry.xy[0]),
            list(geometry.xy[1]),
        )

    if (
        str(u) not in graph.nodes
        or str(v) not in graph.nodes
    ):
        return None

    return (
        [
            float(graph.nodes[str(u)]["x"]),
            float(graph.nodes[str(v)]["x"]),
        ],
        [
            float(graph.nodes[str(u)]["y"]),
            float(graph.nodes[str(v)]["y"]),
        ],
    )


def plot_edge_rows(
    ax,
    graph,
    rows,
    linewidths,
    alpha,
    label=None,
):
    first = True

    for row, linewidth in zip(
        rows.itertuples(index=False),
        linewidths,
    ):
        xy = geometry_xy(
            graph,
            str(row.u),
            str(row.v),
            row.key,
        )

        if xy is None:
            continue

        x, y = xy

        ax.plot(
            x,
            y,
            linewidth=float(linewidth),
            alpha=alpha,
            label=label if first else None,
        )

        first = False


def high_stress_demand_map(
    graph: nx.MultiDiGraph,
) -> tuple[Path, dict]:
    usage = pd.read_csv(
        EDGE_USAGE,
        dtype={
            "u": str,
            "v": str,
        },
    )

    usage["LTS_numeric"] = pd.to_numeric(
        usage["LTS"],
        errors="coerce",
    )

    high_stress = usage.loc[
        (usage["LTS_numeric"] >= 3)
        & (usage["path_count"] > 0)
    ].copy()

    if high_stress.empty:
        raise AssertionError(
            "No used LTS 3-4 edges found."
        )

    threshold = float(
        high_stress[
            "path_count"
        ].quantile(0.95)
    )

    highest_demand = high_stress.loc[
        high_stress["path_count"]
        >= threshold
    ].copy()

    # Reduce visual duplication caused by opposite directions.
    high_stress["pair"] = high_stress.apply(
        lambda row: tuple(
            sorted(
                (
                    str(row["u"]),
                    str(row["v"]),
                )
            )
        ),
        axis=1,
    )

    highest_demand["pair"] = (
        highest_demand.apply(
            lambda row: tuple(
                sorted(
                    (
                        str(row["u"]),
                        str(row["v"]),
                    )
                )
            ),
            axis=1,
        )
    )

    high_stress = (
        high_stress
        .sort_values(
            "path_count",
            ascending=False,
        )
        .drop_duplicates("pair")
    )

    highest_demand = (
        highest_demand
        .sort_values(
            "path_count",
            ascending=False,
        )
        .drop_duplicates("pair")
    )

    fig, ax = plt.subplots(
        figsize=(10, 10)
    )

    # All used LTS 3-4 roads as geographic context.
    plot_edge_rows(
        ax,
        graph,
        high_stress,
        np.full(
            len(high_stress),
            0.35,
        ),
        alpha=0.16,
        label="Used LTS 3–4 road",
    )

    # Highest-demand five percent emphasized.
    loads = highest_demand[
        "path_count"
    ].to_numpy(
        dtype=float
    )

    if len(loads):
        scaled = np.log1p(loads)

        if scaled.max() > scaled.min():
            linewidths = (
                0.8
                + 3.2
                * (
                    scaled
                    - scaled.min()
                )
                / (
                    scaled.max()
                    - scaled.min()
                )
            )
        else:
            linewidths = np.full(
                len(loads),
                2.0,
            )

        plot_edge_rows(
            ax,
            graph,
            highest_demand,
            linewidths,
            alpha=0.85,
            label=(
                "Top 5% modeled-demand load "
                "among used LTS 3–4 roads"
            ),
        )

    ax.set_title(
        "Baseline High-Stress Roads Carrying High Modeled Demand\n"
        "Typical-adult routing profile"
    )

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    ax.legend(
        loc="best",
    )

    ax.set_aspect(
        "equal",
        adjustable="datalim",
    )

    ax.grid(
        alpha=0.12,
    )

    fig.tight_layout()

    output = (
        FIGURE_DIR
        / "07_high_stress_high_demand_map.png"
    )

    fig.savefig(
        output,
        dpi=220,
        bbox_inches="tight",
    )

    plt.close(fig)

    metadata = {
        "profile":
            "typical_adult",
        "used_high_stress_directed_edges":
            int(
                (
                    (usage["LTS_numeric"] >= 3)
                    & (usage["path_count"] > 0)
                ).sum()
            ),
        "high_demand_threshold_path_count":
            threshold,
        "highlighted_directed_edges":
            int(
                (
                    (usage["LTS_numeric"] >= 3)
                    & (
                        usage["path_count"]
                        >= threshold
                    )
                ).sum()
            ),
        "quantile":
            0.95,
    }

    print(
        "Created:",
        output,
    )

    print(
        "High-stress/high-demand threshold:",
        threshold,
    )

    print(
        "Highlighted physical edge pairs:",
        len(highest_demand),
    )

    return output, metadata


def route_edge_set(result):
    return {
        (
            str(u),
            str(v),
            str(key),
        )
        for u, v, key
        in result.edge_path
    }


def plot_route_edges(
    ax,
    graph,
    edges,
    *,
    linewidth,
    linestyle="-",
    alpha=1.0,
    label=None,
):
    first = True

    for u, v, key in edges:
        xy = geometry_xy(
            graph,
            u,
            v,
            key,
        )

        if xy is None:
            continue

        x, y = xy

        ax.plot(
            x,
            y,
            linewidth=linewidth,
            linestyle=linestyle,
            alpha=alpha,
            label=label if first else None,
        )

        first = False


def before_after_route_map(
    baseline_graph: nx.MultiDiGraph,
) -> tuple[Path, dict]:
    comparison = pd.read_csv(
        C001_COMPARISON,
        dtype={
            "origin_node": str,
            "destination_node": str,
        },
    )

    match = comparison.loc[
        (
            comparison["origin_node"]
            == EXAMPLE_ORIGIN
        )
        & (
            comparison["destination_node"]
            == EXAMPLE_DESTINATION
        )
    ]

    if len(match) != 1:
        raise AssertionError(
            "Expected exactly one C001 example OD row."
        )

    recorded = match.iloc[0]

    if not bool(recorded["improved"]):
        raise AssertionError(
            "Selected C001 OD example is not improved."
        )

    candidates = pd.read_csv(
        CANDIDATES,
        dtype={
            "node_a": str,
            "node_b": str,
        },
    )

    candidate_rows = candidates.loc[
        candidates["candidate_id"]
        == "C001"
    ]

    if len(candidate_rows) != 1:
        raise AssertionError(
            "Expected exactly one C001 candidate row."
        )

    candidate = candidate_rows.iloc[0]

    intervention_graph = (
        baseline_graph.copy()
    )

    modified_edges = (
        apply_candidate_intervention(
            intervention_graph,
            candidate,
            TYPICAL_WEIGHTS,
            target_lts=2,
        )
    )

    baseline_prepared = (
        prepare_routing_graph(
            baseline_graph
        )
    )

    intervention_prepared = (
        prepare_routing_graph(
            intervention_graph
        )
    )

    before = ucs_shortest_path(
        baseline_prepared,
        EXAMPLE_ORIGIN,
        EXAMPLE_DESTINATION,
    )

    after = ucs_shortest_path(
        intervention_prepared,
        EXAMPLE_ORIGIN,
        EXAMPLE_DESTINATION,
    )

    if not before.found or not after.found:
        raise AssertionError(
            "Example route was not found."
        )

    # Validate reconstruction against the already-computed
    # intervention comparison artifact.
    if (
        abs(
            before.route_cost
            - float(
                recorded[
                    "baseline_route_cost"
                ]
            )
        )
        > 1e-5
    ):
        raise AssertionError(
            "Reconstructed baseline cost "
            "does not match recorded C001 result."
        )

    if (
        abs(
            after.route_cost
            - float(
                recorded[
                    "intervention_route_cost"
                ]
            )
        )
        > 1e-5
    ):
        raise AssertionError(
            "Reconstructed intervention cost "
            "does not match recorded C001 result."
        )

    before_edges = route_edge_set(
        before
    )

    after_edges = route_edge_set(
        after
    )

    shared = (
        before_edges
        & after_edges
    )

    baseline_only = (
        before_edges
        - after_edges
    )

    intervention_only = (
        after_edges
        - before_edges
    )

    fig, ax = plt.subplots(
        figsize=(10, 9)
    )

    plot_route_edges(
        ax,
        baseline_graph,
        shared,
        linewidth=2.0,
        alpha=0.45,
        label="Shared route",
    )

    plot_route_edges(
        ax,
        baseline_graph,
        baseline_only,
        linewidth=3.2,
        linestyle="--",
        alpha=0.9,
        label="Baseline-only route",
    )

    plot_route_edges(
        ax,
        intervention_graph,
        intervention_only,
        linewidth=3.2,
        alpha=0.9,
        label="Post-intervention-only route",
    )

    # Highlight the physical C001 intervention itself.
    modified_plot_edges = [
        (
            str(u),
            str(v),
            str(key),
        )
        for u, v, key
        in modified_edges
    ]

    plot_route_edges(
        ax,
        intervention_graph,
        modified_plot_edges,
        linewidth=5.0,
        alpha=0.9,
        label="C001 · Chauncy Street improvement",
    )

    origin = baseline_graph.nodes[
        EXAMPLE_ORIGIN
    ]

    destination = baseline_graph.nodes[
        EXAMPLE_DESTINATION
    ]

    ax.scatter(
        [float(origin["x"])],
        [float(origin["y"])],
        s=90,
        marker="o",
        label="Origin",
        zorder=10,
    )

    ax.scatter(
        [float(destination["x"])],
        [float(destination["y"])],
        s=110,
        marker="X",
        label="Destination",
        zorder=10,
    )

    reduction = (
        before.route_cost
        - after.route_cost
    )

    title = (
        "Before vs. After Routing for C001 · Chauncy Street\n"
        "Typical adult · home-to-office trip"
    )

    ax.set_title(title)

    annotation = (
        f"Generalized cost: "
        f"{before.route_cost:,.1f} → "
        f"{after.route_cost:,.1f} "
        f"(−{reduction:,.1f})\n"
        f"Physical distance: "
        f"{before.route_distance:,.0f} m → "
        f"{after.route_distance:,.0f} m\n"
        f"Edges: "
        f"{len(before.edge_path)} → "
        f"{len(after.edge_path)}"
    )

    ax.text(
        0.02,
        0.02,
        annotation,
        transform=ax.transAxes,
        fontsize=9,
        verticalalignment="bottom",
        bbox={
            "boxstyle": "round",
            "facecolor": "white",
            "alpha": 0.85,
        },
    )

    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    ax.legend(
        loc="best",
        fontsize=8,
    )

    ax.set_aspect(
        "equal",
        adjustable="datalim",
    )

    ax.grid(
        alpha=0.12,
    )

    fig.tight_layout()

    output = (
        FIGURE_DIR
        / "08_before_after_route_example.png"
    )

    fig.savefig(
        output,
        dpi=220,
        bbox_inches="tight",
    )

    plt.close(fig)

    metadata = {
        "candidate_id":
            "C001",
        "location":
            "Chauncy Street",
        "rider_profile":
            "typical_adult",
        "category":
            str(recorded["category"]),
        "origin_node":
            EXAMPLE_ORIGIN,
        "destination_node":
            EXAMPLE_DESTINATION,
        "demand":
            float(recorded["demand"]),
        "baseline_route_cost":
            before.route_cost,
        "intervention_route_cost":
            after.route_cost,
        "cost_reduction":
            reduction,
        "baseline_route_distance_m":
            before.route_distance,
        "intervention_route_distance_m":
            after.route_distance,
        "distance_change_m":
            (
                after.route_distance
                - before.route_distance
            ),
        "baseline_edge_count":
            len(before.edge_path),
        "intervention_edge_count":
            len(after.edge_path),
        "shared_edges":
            len(shared),
        "baseline_only_edges":
            len(baseline_only),
        "intervention_only_edges":
            len(intervention_only),
        "modified_candidate_edges":
            len(modified_edges),
    }

    print(
        "Created:",
        output,
    )

    print(
        "Before cost:",
        before.route_cost,
    )

    print(
        "After cost:",
        after.route_cost,
    )

    print(
        "Cost reduction:",
        reduction,
    )

    print(
        "Before distance:",
        before.route_distance,
    )

    print(
        "After distance:",
        after.route_distance,
    )

    print(
        "Baseline-only edges:",
        len(baseline_only),
    )

    print(
        "Intervention-only edges:",
        len(intervention_only),
    )

    return output, metadata


def update_manifest(
    outputs: list[tuple[Path, str]],
) -> None:
    path = (
        FIGURE_DIR
        / "figure_manifest.csv"
    )

    if path.exists():
        manifest = pd.read_csv(path)
    else:
        manifest = pd.DataFrame(
            columns=[
                "figure",
                "description",
            ]
        )

    new = pd.DataFrame(
        [
            {
                "figure": figure.name,
                "description": description,
            }
            for figure, description
            in outputs
        ]
    )

    manifest = pd.concat(
        [
            manifest.loc[
                ~manifest["figure"].isin(
                    new["figure"]
                )
            ],
            new,
        ],
        ignore_index=True,
    )

    manifest.to_csv(
        path,
        index=False,
    )

    print(
        "Updated:",
        path,
    )


def main() -> None:
    print(
        "Loading typical-adult baseline graph:"
    )

    graph = ox.load_graphml(
        BASELINE_GRAPH
    )

    graph = normalize_graph_nodes(
        graph
    )

    print(
        f"Graph: "
        f"{graph.number_of_nodes():,} nodes, "
        f"{graph.number_of_edges():,} edges"
    )

    figure7, metadata7 = (
        high_stress_demand_map(
            graph
        )
    )

    figure8, metadata8 = (
        before_after_route_map(
            graph
        )
    )

    metadata = pd.DataFrame(
        [
            {
                "figure":
                    figure7.name,
                **metadata7,
            },
            {
                "figure":
                    figure8.name,
                **metadata8,
            },
        ]
    )

    metadata_path = (
        FIGURE_DIR
        / "proposal_visual_metadata.csv"
    )

    metadata.to_csv(
        metadata_path,
        index=False,
    )

    print(
        "Created:",
        metadata_path,
    )

    update_manifest(
        [
            (
                figure7,
                (
                    "Baseline typical-adult LTS 3–4 "
                    "road segments, highlighting the "
                    "top five percent by modeled "
                    "demand-weighted edge load."
                ),
            ),
            (
                figure8,
                (
                    "Before/after route example for "
                    "the C001 Chauncy Street intervention "
                    "under the typical-adult profile."
                ),
            ),
        ]
    )


if __name__ == "__main__":
    main()
