"""Collect and rank the 40 full intervention simulations."""

from pathlib import Path

import pandas as pd


ROOT = Path(
    "/work/pi_plunkett_umass_edu/bcu/course_project/interventions"
)

OUT = Path("results/interventions")

CANDIDATES_PATH = Path(
    "results/candidates/candidate_segments.csv"
)

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


def main():
    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    summaries = []
    categories = []
    manifest = []
    missing = []

    for candidate_id in CANDIDATES:
        for profile in PROFILES:
            root = (
                ROOT
                / candidate_id
                / profile
            )

            files = {
                "summary":
                    root / "summary.csv",
                "category":
                    root / "category_summary.csv",
                "comparison":
                    root / "od_comparison.csv",
                "origins":
                    root / "origin_search_stats.csv",
            }

            absent = [
                str(path)
                for path in files.values()
                if not path.exists()
            ]

            if absent:
                missing.extend(absent)
                continue

            summary = pd.read_csv(
                files["summary"]
            )

            if len(summary) != 1:
                raise AssertionError(
                    f"Invalid summary: "
                    f"{files['summary']}"
                )

            row = summary.iloc[0]

            if (
                row["candidate_id"]
                != candidate_id
            ):
                raise AssertionError(
                    "Candidate ID mismatch."
                )

            if (
                row["rider_profile"]
                != profile
            ):
                raise AssertionError(
                    "Rider profile mismatch."
                )

            summaries.append(summary)

            categories.append(
                pd.read_csv(
                    files["category"]
                )
            )

            for label, path in files.items():
                manifest.append(
                    {
                        "candidate_id":
                            candidate_id,
                        "rider_profile":
                            profile,
                        "artifact": label,
                        "path": str(path),
                        "size_bytes":
                            path.stat().st_size,
                    }
                )

    if missing:
        print(
            "Experiment is incomplete."
        )
        print(
            "Missing files:",
            len(missing),
        )

        for path in missing[:20]:
            print(path)

        raise SystemExit(1)

    summary = pd.concat(
        summaries,
        ignore_index=True,
    )

    category = pd.concat(
        categories,
        ignore_index=True,
    )

    if len(summary) != 40:
        raise AssertionError(
            f"Expected 40 summaries, "
            f"found {len(summary)}."
        )

    counts = (
        summary.groupby(
            "candidate_id"
        )["rider_profile"]
        .nunique()
    )

    if not (counts == 4).all():
        raise AssertionError(
            "A candidate is missing a profile."
        )

    invariant_columns = [
        "od_records",
        "routed_od_records",
        "total_demand",
        "routed_demand",
    ]

    for column in invariant_columns:
        if (
            summary[column]
            .nunique(dropna=False)
            != 1
        ):
            raise AssertionError(
                f"Invariant differs: {column}"
            )

    if (
        summary[
            "minimum_cost_reduction"
        ]
        < -1e-8
    ).any():
        raise AssertionError(
            "At least one optimal route "
            "became more costly."
        )

    summary[
        "mean_distance_change_m"
    ] = (
        summary[
            "demand_weighted_distance_change_m"
        ]
        / summary["routed_demand"]
    )

    ranking = (
        summary.groupby(
            "candidate_id",
            as_index=False,
        )
        .agg(
            mean_route_cost_reduction=(
                "demand_weighted_route_cost_reduction",
                "mean",
            ),
            total_route_cost_reduction=(
                "demand_weighted_route_cost_reduction",
                "sum",
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
            min_improved_demand=(
                "improved_demand",
                "min",
            ),
            max_improved_demand=(
                "improved_demand",
                "max",
            ),
            mean_improved_od_records=(
                "improved_od_records",
                "mean",
            ),
            mean_distance_change_m=(
                "mean_distance_change_m",
                "mean",
            ),
            mean_runtime_seconds=(
                "runtime_seconds",
                "mean",
            ),
        )
    )

    candidates = pd.read_csv(
        CANDIDATES_PATH
    )

    candidates = candidates.loc[
        candidates["candidate_id"].isin(
            CANDIDATES
        )
    ].copy()

    candidates[
        "screening_rank"
    ] = (
        candidates["candidate_id"]
        .str.replace(
            "C",
            "",
            regex=False,
        )
        .astype(int)
    )

    metadata = [
        "candidate_id",
        "location",
        "length_m",
        "current_lts",
        "modeled_demand",
        "preliminary_benefit",
        "connects_safe_components",
        "screening_rank",
    ]

    ranking = ranking.merge(
        candidates[metadata],
        on="candidate_id",
        how="left",
        validate="one_to_one",
    )

    ranking[
        "benefit_per_meter"
    ] = (
        ranking[
            "mean_route_cost_reduction"
        ]
        / ranking["length_m"]
    )

    ranking = ranking.sort_values(
        [
            "mean_route_cost_reduction",
            "mean_improved_demand",
        ],
        ascending=False,
    ).reset_index(drop=True)

    ranking[
        "simulation_rank"
    ] = range(
        1,
        len(ranking) + 1,
    )

    ranking[
        "rank_change"
    ] = (
        ranking["screening_rank"]
        - ranking["simulation_rank"]
    )

    ranking.to_csv(
        OUT
        / "candidate_simulation_ranking.csv",
        index=False,
    )

    summary.to_csv(
        OUT
        / "four_profile_intervention_summary.csv",
        index=False,
    )

    category.to_csv(
        OUT
        / "four_profile_intervention_category_summary.csv",
        index=False,
    )

    pd.DataFrame(
        manifest
    ).to_csv(
        OUT
        / "intervention_output_manifest.csv",
        index=False,
    )

    print(
        "40 intervention simulations collected."
    )
    print(
        "Invariant checks PASSED."
    )
    print()

    print(
        ranking[
            [
                "simulation_rank",
                "screening_rank",
                "rank_change",
                "candidate_id",
                "location",
                "length_m",
                "mean_route_cost_reduction",
                "benefit_per_meter",
                "mean_percent_cost_reduction",
                "mean_improved_demand",
                "mean_distance_change_m",
            ]
        ].to_string(index=False)
    )


if __name__ == "__main__":
    main()
