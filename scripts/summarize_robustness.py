"""Create final robustness summary across ranking and package tests."""

from pathlib import Path

import pandas as pd


BASELINE_PACKAGE = [
    "C001",
    "C002",
    "C003",
    "C004",
    "C006",
]

BASELINE_MEAN_BENEFIT = 361774.0542953967

ROOT = Path("results/robustness")


def package_set(value: str) -> set[str]:
    return {
        x.strip()
        for x in value.split(";")
        if x.strip()
    }


def main() -> None:
    stability = pd.read_csv(
        ROOT / "ranking_stability_summary.csv"
    )

    rows = []

    for mode in [
        "high_aversion",
        "od_seed_684",
    ]:
        selection = pd.read_csv(
            ROOT
            / "optimization"
            / mode
            / "greedy_selection.csv"
        )

        final = selection.loc[
            selection["step"] == 5
        ]

        if len(final) != 1:
            raise AssertionError(
                f"{mode}: expected one step-5 package."
            )

        final = final.iloc[0]

        package = package_set(
            final["package_ids"]
        )

        baseline = set(
            BASELINE_PACKAGE
        )

        shared = package & baseline
        union = package | baseline

        rank_row = stability.loc[
            stability["experiment"] == mode
        ]

        if len(rank_row) != 1:
            raise AssertionError(
                f"{mode}: ranking stability row missing."
            )

        rank_row = rank_row.iloc[0]

        benefit = float(
            final["mean_total_benefit"]
        )

        comparable_benefit = (
            mode == "od_seed_684"
        )

        rows.append(
            {
                "experiment": mode,
                "spearman_rank_correlation":
                    rank_row[
                        "spearman_rank_correlation"
                    ],
                "top_5_overlap_count":
                    int(
                        rank_row[
                            "top_5_overlap_count"
                        ]
                    ),
                "top_5_jaccard":
                    rank_row["top_5_jaccard"],
                "baseline_package":
                    ";".join(BASELINE_PACKAGE),
                "robustness_package":
                    final["package_ids"],
                "optimized_package_overlap_count":
                    len(shared),
                "optimized_package_overlap_fraction":
                    len(shared) / len(baseline),
                "optimized_package_jaccard":
                    len(shared) / len(union),
                "shared_optimized_projects":
                    ";".join(sorted(shared)),
                "robustness_final_mean_benefit":
                    benefit,
                "robustness_final_length_m":
                    float(
                        final["cumulative_length_m"]
                    ),
                "benefit_directly_comparable_to_baseline":
                    comparable_benefit,
                "benefit_change_vs_baseline":
                    (
                        benefit
                        - BASELINE_MEAN_BENEFIT
                        if comparable_benefit
                        else None
                    ),
                "benefit_change_pct_vs_baseline":
                    (
                        100.0
                        * (
                            benefit
                            - BASELINE_MEAN_BENEFIT
                        )
                        / BASELINE_MEAN_BENEFIT
                        if comparable_benefit
                        else None
                    ),
            }
        )

    summary = pd.DataFrame(rows)

    summary.to_csv(
        ROOT / "robustness_summary.csv",
        index=False,
    )

    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
