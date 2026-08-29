"""Collect robustness intervention rankings and compare with baseline."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
from scipy.stats import spearmanr


COURSE = Path(
    "/work/pi_plunkett_umass_edu/bcu/course_project"
)

OUT = Path("results/robustness")

PROFILES = [
    "child",
    "low_confidence_adult",
    "typical_adult",
    "experienced_adult",
]

CANDIDATES = [
    f"C{i:03d}"
    for i in range(1, 11)
]

MODES = {
    "high_aversion":
        COURSE
        / "robustness/interventions/high_aversion",
    "od_seed_684":
        COURSE
        / "robustness/interventions/od_seed_684",
}


def collect_mode(
    mode: str,
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    missing = []

    for candidate in CANDIDATES:
        for profile in PROFILES:
            path = (
                root
                / candidate
                / profile
                / "summary.csv"
            )

            if not path.exists():
                missing.append(str(path))
                continue

            df = pd.read_csv(path)

            if len(df) != 1:
                raise ValueError(
                    f"{path} contains {len(df)} rows."
                )

            row = df.iloc[0].to_dict()
            row["experiment"] = mode
            rows.append(row)

    if missing:
        raise FileNotFoundError(
            f"{mode}: missing {len(missing)} summaries:\n"
            + "\n".join(missing)
        )

    raw = pd.DataFrame(rows)

    if len(raw) != 40:
        raise AssertionError(
            f"{mode}: expected 40 rows, got {len(raw)}."
        )

    if raw["candidate_id"].nunique() != 10:
        raise AssertionError(
            f"{mode}: expected 10 candidates."
        )

    if raw["rider_profile"].nunique() != 4:
        raise AssertionError(
            f"{mode}: expected 4 profiles."
        )

    ranking = (
        raw.groupby(
            "candidate_id",
            as_index=False,
        )
        .agg(
            profile_count=(
                "rider_profile",
                "nunique",
            ),
            mean_route_cost_reduction=(
                "demand_weighted_route_cost_reduction",
                "mean",
            ),
            min_profile_route_cost_reduction=(
                "demand_weighted_route_cost_reduction",
                "min",
            ),
            max_profile_route_cost_reduction=(
                "demand_weighted_route_cost_reduction",
                "max",
            ),
            mean_percent_cost_reduction=(
                "percent_baseline_cost_reduction",
                "mean",
            ),
            mean_improved_demand=(
                "improved_demand",
                "mean",
            ),
            mean_improved_od_records=(
                "improved_od_records",
                "mean",
            ),
        )
    )

    if not (
        ranking["profile_count"] == 4
    ).all():
        raise AssertionError(
            f"{mode}: incomplete profile aggregation."
        )

    candidates = pd.read_csv(
        "results/candidates/candidate_segments.csv"
    )

    metadata_cols = [
        col
        for col in [
            "candidate_id",
            "location",
            "length_m",
            "current_lts",
        ]
        if col in candidates.columns
    ]

    ranking = ranking.merge(
        candidates[metadata_cols],
        on="candidate_id",
        how="left",
        validate="one_to_one",
    )

    ranking = ranking.sort_values(
        [
            "mean_route_cost_reduction",
            "mean_improved_demand",
            "length_m",
        ],
        ascending=[
            False,
            False,
            True,
        ],
    ).reset_index(drop=True)

    ranking.insert(
        0,
        "robustness_rank",
        range(1, len(ranking) + 1),
    )

    ranking.insert(
        0,
        "experiment",
        mode,
    )

    return raw, ranking


def baseline_columns(
    baseline: pd.DataFrame,
) -> tuple[str, str]:
    rank_candidates = [
        "simulation_rank",
        "rank",
    ]

    benefit_candidates = [
        "mean_route_cost_reduction",
        "mean_demand_weighted_route_cost_reduction",
    ]

    rank_col = next(
        (
            col
            for col in rank_candidates
            if col in baseline.columns
        ),
        None,
    )

    benefit_col = next(
        (
            col
            for col in benefit_candidates
            if col in baseline.columns
        ),
        None,
    )

    if rank_col is None:
        raise KeyError(
            "Could not identify baseline rank column."
        )

    if benefit_col is None:
        raise KeyError(
            "Could not identify baseline benefit column."
        )

    return rank_col, benefit_col


def main() -> None:
    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    baseline = pd.read_csv(
        "results/interventions/"
        "candidate_simulation_ranking.csv"
    )

    rank_col, benefit_col = (
        baseline_columns(baseline)
    )

    baseline_small = baseline[
        [
            "candidate_id",
            rank_col,
            benefit_col,
        ]
    ].rename(
        columns={
            rank_col: "baseline_rank",
            benefit_col:
                "baseline_mean_route_cost_reduction",
        }
    )

    stability_rows = []

    for mode, root in MODES.items():
        raw, ranking = collect_mode(
            mode,
            root,
        )

        raw.to_csv(
            OUT
            / f"{mode}_intervention_profile_results.csv",
            index=False,
        )

        comparison = ranking.merge(
            baseline_small,
            on="candidate_id",
            how="left",
            validate="one_to_one",
        )

        if comparison["baseline_rank"].isna().any():
            raise AssertionError(
                f"{mode}: missing baseline ranks."
            )

        comparison[
            "rank_change_vs_baseline"
        ] = (
            comparison["baseline_rank"]
            - comparison["robustness_rank"]
        )

        comparison[
            "benefit_change_vs_baseline"
        ] = (
            comparison[
                "mean_route_cost_reduction"
            ]
            - comparison[
                "baseline_mean_route_cost_reduction"
            ]
        )

        denominator = comparison[
            "baseline_mean_route_cost_reduction"
        ]

        comparison[
            "benefit_change_pct_vs_baseline"
        ] = (
            100.0
            * comparison[
                "benefit_change_vs_baseline"
            ]
            / denominator
        )

        comparison = comparison.sort_values(
            "robustness_rank"
        )

        comparison.to_csv(
            OUT
            / f"{mode}_candidate_ranking.csv",
            index=False,
        )

        rho = float(
            spearmanr(
                comparison["baseline_rank"],
                comparison["robustness_rank"],
            ).statistic
        )

        baseline_top5 = set(
            comparison.loc[
                comparison["baseline_rank"] <= 5,
                "candidate_id",
            ]
        )

        robustness_top5 = set(
            comparison.loc[
                comparison["robustness_rank"] <= 5,
                "candidate_id",
            ]
        )

        overlap = (
            baseline_top5
            & robustness_top5
        )

        union = (
            baseline_top5
            | robustness_top5
        )

        stability_rows.append(
            {
                "experiment": mode,
                "spearman_rank_correlation": rho,
                "top_5_overlap_count": len(overlap),
                "top_5_jaccard":
                    len(overlap) / len(union),
                "baseline_top_5":
                    ";".join(sorted(baseline_top5)),
                "robustness_top_5":
                    ";".join(sorted(robustness_top5)),
                "shared_top_5":
                    ";".join(sorted(overlap)),
            }
        )

        print()
        print("=" * 90)
        print(mode)
        print("=" * 90)

        print(
            comparison[
                [
                    "robustness_rank",
                    "candidate_id",
                    "location",
                    "mean_route_cost_reduction",
                    "baseline_rank",
                    "rank_change_vs_baseline",
                    "benefit_change_pct_vs_baseline",
                    "mean_improved_demand",
                ]
            ].to_string(index=False)
        )

    stability = pd.DataFrame(
        stability_rows
    )

    stability.to_csv(
        OUT / "ranking_stability_summary.csv",
        index=False,
    )

    print()
    print("=" * 90)
    print("RANKING STABILITY")
    print("=" * 90)
    print(
        stability.to_string(index=False)
    )


if __name__ == "__main__":
    main()
