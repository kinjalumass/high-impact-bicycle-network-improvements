"""Create final report figures for the COMPSCI 683 bicycle project."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd


FIGURE_DIR = Path("reports/figures")
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_LABELS = {
    "child": "Child",
    "low_confidence_adult": "Low-confidence adult",
    "typical_adult": "Typical adult",
    "experienced_adult": "Experienced adult",
}


def require_columns(
    df: pd.DataFrame,
    columns: list[str],
    source: str,
) -> None:
    missing = [
        column
        for column in columns
        if column not in df.columns
    ]

    if missing:
        raise ValueError(
            f"{source} missing columns: {missing}"
        )


def save_figure(
    fig: plt.Figure,
    filename: str,
) -> Path:
    path = FIGURE_DIR / filename

    fig.savefig(
        path,
        dpi=220,
        bbox_inches="tight",
    )

    plt.close(fig)

    print("Created:", path)

    return path


def baseline_profile_figure() -> Path:
    path = (
        "results/baseline/"
        "four_profile_summary.csv"
    )

    df = pd.read_csv(path)

    require_columns(
        df,
        [
            "rider_profile",
            "demand_weighted_mean_route_cost",
            "demand_weighted_mean_route_distance_m",
        ],
        path,
    )

    fig, ax = plt.subplots(
        figsize=(8.5, 6.0)
    )

    x = df[
        "demand_weighted_mean_route_distance_m"
    ]

    y = df[
        "demand_weighted_mean_route_cost"
    ]

    ax.scatter(
        x,
        y,
        s=110,
    )

    for _, row in df.iterrows():
        label = PROFILE_LABELS.get(
            row["rider_profile"],
            row["rider_profile"],
        )

        ax.annotate(
            label,
            (
                row[
                    "demand_weighted_mean_route_distance_m"
                ],
                row[
                    "demand_weighted_mean_route_cost"
                ],
            ),
            xytext=(6, 6),
            textcoords="offset points",
            fontsize=9,
        )

    ax.set_title(
        "Baseline Routing by Rider Profile"
    )

    ax.set_xlabel(
        "Demand-weighted mean route distance (m)"
    )

    ax.set_ylabel(
        "Demand-weighted mean generalized route cost"
    )

    ax.yaxis.set_major_formatter(
        FuncFormatter(
            lambda value, _: f"{value:,.0f}"
        )
    )

    ax.grid(
        alpha=0.2,
    )

    fig.tight_layout()

    return save_figure(
        fig,
        "01_baseline_rider_profiles.png",
    )


def candidate_ranking_figure() -> Path:
    path = (
        "results/interventions/"
        "candidate_simulation_ranking.csv"
    )

    df = pd.read_csv(path)

    require_columns(
        df,
        [
            "candidate_id",
            "location",
            "mean_route_cost_reduction",
            "simulation_rank",
        ],
        path,
    )

    df = df.sort_values(
        "simulation_rank"
    ).copy()

    labels = (
        df["candidate_id"]
        + " · "
        + df["location"]
    )

    fig, ax = plt.subplots(
        figsize=(10.5, 7.0)
    )

    bars = ax.barh(
        labels,
        df["mean_route_cost_reduction"],
    )

    ax.invert_yaxis()

    ax.set_title(
        "Full-Simulation Ranking of Candidate Improvements"
    )

    ax.set_xlabel(
        "Mean demand-weighted generalized-cost reduction"
    )

    ax.xaxis.set_major_formatter(
        FuncFormatter(
            lambda value, _: f"{value:,.0f}"
        )
    )

    ax.grid(
        axis="x",
        alpha=0.2,
    )

    for bar, value in zip(
        bars,
        df["mean_route_cost_reduction"],
    ):
        ax.text(
            value,
            bar.get_y()
            + bar.get_height() / 2,
            f"  {value:,.0f}",
            va="center",
            fontsize=8,
        )

    fig.tight_layout()

    return save_figure(
        fig,
        "02_candidate_simulation_ranking.png",
    )


def greedy_progression_figure() -> Path:
    path = (
        "results/optimization/"
        "greedy_selection.csv"
    )

    df = pd.read_csv(path)

    require_columns(
        df,
        [
            "step",
            "selected_candidate",
            "mean_total_benefit",
            "marginal_benefit",
        ],
        path,
    )

    fig, ax = plt.subplots(
        figsize=(8.5, 6.0)
    )

    ax.plot(
        df["step"],
        df["mean_total_benefit"],
        marker="o",
        linewidth=2,
    )

    for _, row in df.iterrows():
        ax.annotate(
            (
                f"{row['selected_candidate']}\n"
                f"+{row['marginal_benefit']:,.0f}"
            ),
            (
                row["step"],
                row["mean_total_benefit"],
            ),
            xytext=(0, 10),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )

    ax.set_title(
        "Greedy Construction of the Five-Project Package"
    )

    ax.set_xlabel(
        "Greedy selection step"
    )

    ax.set_ylabel(
        "Mean demand-weighted generalized-cost reduction"
    )

    ax.set_xticks(
        df["step"]
    )

    ax.yaxis.set_major_formatter(
        FuncFormatter(
            lambda value, _: f"{value:,.0f}"
        )
    )

    ax.grid(
        alpha=0.2,
    )

    fig.tight_layout()

    return save_figure(
        fig,
        "03_greedy_package_progression.png",
    )


def final_package_profiles_figure() -> Path:
    path = (
        "results/optimization/"
        "greedy_final_package_profile_results.csv"
    )

    df = pd.read_csv(path)

    require_columns(
        df,
        [
            "rider_profile",
            "demand_weighted_route_cost_reduction",
            "improved_demand",
        ],
        path,
    )

    df = df.copy()

    df["profile_label"] = (
        df["rider_profile"]
        .map(PROFILE_LABELS)
        .fillna(df["rider_profile"])
    )

    fig, ax = plt.subplots(
        figsize=(9.0, 6.0)
    )

    bars = ax.bar(
        df["profile_label"],
        df[
            "demand_weighted_route_cost_reduction"
        ],
    )

    ax.set_title(
        "Benefit of the Final Five-Project Package by Rider Profile"
    )

    ax.set_ylabel(
        "Demand-weighted generalized-cost reduction"
    )

    ax.yaxis.set_major_formatter(
        FuncFormatter(
            lambda value, _: f"{value:,.0f}"
        )
    )

    ax.tick_params(
        axis="x",
        rotation=15,
    )

    ax.grid(
        axis="y",
        alpha=0.2,
    )

    for bar, value in zip(
        bars,
        df[
            "demand_weighted_route_cost_reduction"
        ],
    ):
        ax.text(
            bar.get_x()
            + bar.get_width() / 2,
            value,
            f"{value:,.0f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    fig.tight_layout()

    return save_figure(
        fig,
        "04_final_package_by_profile.png",
    )


def robustness_figure() -> Path:
    path = (
        "results/robustness/"
        "robustness_summary.csv"
    )

    df = pd.read_csv(path)

    require_columns(
        df,
        [
            "experiment",
            "spearman_rank_correlation",
            "top_5_overlap_count",
            "optimized_package_overlap_fraction",
        ],
        path,
    )

    display_names = {
        "high_aversion":
            "Higher stress aversion",
        "od_seed_684":
            "Alternate OD sample",
    }

    experiments = [
        display_names.get(
            value,
            value,
        )
        for value in df["experiment"]
    ]

    metric_names = [
        "Rank correlation",
        "Top-5 overlap",
        "Package overlap",
    ]

    values = np.column_stack(
        [
            df[
                "spearman_rank_correlation"
            ].to_numpy(),
            (
                df[
                    "top_5_overlap_count"
                ].to_numpy()
                / 5.0
            ),
            df[
                "optimized_package_overlap_fraction"
            ].to_numpy(),
        ]
    )

    fig, ax = plt.subplots(
        figsize=(9.0, 6.0)
    )

    x = np.arange(
        len(metric_names)
    )

    width = 0.34

    for index, experiment in enumerate(
        experiments
    ):
        offset = (
            index
            - (len(experiments) - 1) / 2
        ) * width

        bars = ax.bar(
            x + offset,
            values[index],
            width,
            label=experiment,
        )

        for bar, value in zip(
            bars,
            values[index],
        ):
            ax.text(
                bar.get_x()
                + bar.get_width() / 2,
                value,
                f"{value:.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )

    ax.set_title(
        "Robustness of Candidate Ranking and Optimized Package"
    )

    ax.set_ylabel(
        "Stability relative to baseline"
    )

    ax.set_xticks(
        x,
        metric_names,
    )

    ax.set_ylim(
        0,
        1.12,
    )

    ax.legend()

    ax.grid(
        axis="y",
        alpha=0.2,
    )

    fig.tight_layout()

    return save_figure(
        fig,
        "05_robustness_summary.png",
    )


def candidate_map_figure() -> Path:
    candidate_path = (
        "results/candidates/"
        "candidate_segments.csv"
    )

    ranking_path = (
        "results/interventions/"
        "candidate_simulation_ranking.csv"
    )

    greedy_path = (
        "results/optimization/"
        "greedy_selection.csv"
    )

    candidates = pd.read_csv(
        candidate_path
    )

    ranking = pd.read_csv(
        ranking_path
    )

    greedy = pd.read_csv(
        greedy_path
    )

    require_columns(
        candidates,
        [
            "candidate_id",
            "latitude",
            "longitude",
            "location",
        ],
        candidate_path,
    )

    require_columns(
        ranking,
        [
            "candidate_id",
            "simulation_rank",
        ],
        ranking_path,
    )

    require_columns(
        greedy,
        [
            "step",
            "package_ids",
        ],
        greedy_path,
    )

    top10 = (
        ranking[
            [
                "candidate_id",
                "simulation_rank",
            ]
        ]
        .merge(
            candidates[
                [
                    "candidate_id",
                    "latitude",
                    "longitude",
                    "location",
                ]
            ],
            on="candidate_id",
            how="left",
            validate="one_to_one",
        )
        .sort_values(
            "simulation_rank"
        )
    )

    if (
        top10[
            [
                "latitude",
                "longitude",
            ]
        ]
        .isna()
        .any()
        .any()
    ):
        raise ValueError(
            "Missing coordinates for a top-10 candidate."
        )

    final_row = (
        greedy.sort_values(
            "step"
        )
        .iloc[-1]
    )

    selected = {
        value.strip()
        for value in str(
            final_row["package_ids"]
        ).split(";")
        if value.strip()
    }

    top10["selected"] = (
        top10["candidate_id"]
        .isin(selected)
    )

    fig, ax = plt.subplots(
        figsize=(9.0, 8.0)
    )

    other = top10.loc[
        ~top10["selected"]
    ]

    chosen = top10.loc[
        top10["selected"]
    ]

    ax.scatter(
        other["longitude"],
        other["latitude"],
        s=70,
        marker="o",
        label="Other simulated top-10 candidate",
    )

    ax.scatter(
        chosen["longitude"],
        chosen["latitude"],
        s=180,
        marker="*",
        label="Selected in baseline five-project package",
    )

    for _, row in top10.iterrows():
        ax.annotate(
            (
                f"{row['candidate_id']}\n"
                f"{row['location']}"
            ),
            (
                row["longitude"],
                row["latitude"],
            ),
            xytext=(5, 5),
            textcoords="offset points",
            fontsize=7,
        )

    mean_latitude = float(
        top10["latitude"].mean()
    )

    ax.set_aspect(
        1.0
        / np.cos(
            np.deg2rad(
                mean_latitude
            )
        )
    )

    ax.set_title(
        "Representative Locations of Top Candidate Improvements"
    )

    ax.set_xlabel(
        "Longitude"
    )

    ax.set_ylabel(
        "Latitude"
    )

    ax.legend(
        loc="best",
    )

    ax.grid(
        alpha=0.2,
    )

    fig.tight_layout()

    return save_figure(
        fig,
        "06_candidate_locations.png",
    )


def main() -> None:
    outputs = [
        (
            baseline_profile_figure(),
            (
                "Baseline generalized route cost "
                "and physical route distance by rider profile."
            ),
        ),
        (
            candidate_ranking_figure(),
            (
                "Top ten candidate infrastructure "
                "segments ranked after full rerouting simulation."
            ),
        ),
        (
            greedy_progression_figure(),
            (
                "Cumulative modeled benefit across "
                "the five greedy optimization steps."
            ),
        ),
        (
            final_package_profiles_figure(),
            (
                "Final five-project package benefit "
                "for each rider profile."
            ),
        ),
        (
            robustness_figure(),
            (
                "Ranking and package stability under "
                "higher stress aversion and alternate OD sampling."
            ),
        ),
        (
            candidate_map_figure(),
            (
                "Representative geographic locations "
                "of the ten fully simulated candidates, "
                "highlighting the baseline optimized package."
            ),
        ),
    ]

    new_manifest = pd.DataFrame(
        [
            {
                "figure": path.name,
                "description": description,
            }
            for path, description in outputs
        ]
    )

    manifest_path = (
        FIGURE_DIR
        / "figure_manifest.csv"
    )

    if manifest_path.exists():
        existing = pd.read_csv(
            manifest_path
        )

        manifest = pd.concat(
            [
                existing.loc[
                    ~existing["figure"].isin(
                        new_manifest["figure"]
                    )
                ],
                new_manifest,
            ],
            ignore_index=True,
        )
    else:
        manifest = new_manifest

    manifest = (
        manifest
        .sort_values("figure")
        .reset_index(drop=True)
    )

    manifest.to_csv(
        manifest_path,
        index=False,
    )

    print()
    print("Figure manifest:")
    print(
        manifest.to_string(
            index=False
        )
    )


if __name__ == "__main__":
    main()
