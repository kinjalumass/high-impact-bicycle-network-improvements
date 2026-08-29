"""Collect one robustness greedy optimization round."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


COURSE = Path(
    "/work/pi_plunkett_umass_edu/bcu/course_project"
)

PROFILES = [
    "child",
    "low_confidence_adult",
    "typical_adult",
    "experienced_adult",
]


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--mode",
        required=True,
        choices=[
            "high_aversion",
            "od_seed_684",
        ],
    )

    parser.add_argument(
        "--round",
        type=int,
        required=True,
    )

    parser.add_argument(
        "--base-ids",
        required=True,
    )

    parser.add_argument(
        "--candidates",
        required=True,
    )

    args = parser.parse_args()

    base_ids = [
        x.strip()
        for x in args.base_ids.split(",")
        if x.strip()
    ]

    candidates = [
        x.strip()
        for x in args.candidates.split(",")
        if x.strip()
    ]

    output = (
        Path("results/robustness/optimization")
        / args.mode
    )

    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    rows = []
    missing = []

    for candidate in candidates:
        package_ids = base_ids + [candidate]
        package_name = "_".join(package_ids)

        for profile in PROFILES:
            path = (
                COURSE
                / "robustness"
                / "optimization"
                / args.mode
                / f"round_{args.round}"
                / package_name
                / profile
                / "summary.csv"
            )

            if not path.exists():
                missing.append(str(path))
                continue

            df = pd.read_csv(path)

            if len(df) != 1:
                raise AssertionError(
                    f"Expected one row in {path}."
                )

            rows.append(
                df.iloc[0].to_dict()
            )

    if missing:
        print(
            f"Round {args.round} incomplete."
        )
        print(
            "Missing summaries:",
            len(missing),
        )

        for path in missing[:20]:
            print(path)

        raise SystemExit(1)

    raw = pd.DataFrame(rows)

    expected = len(candidates) * 4

    if len(raw) != expected:
        raise AssertionError(
            f"Expected {expected} rows; "
            f"found {len(raw)}."
        )

    grouped = (
        raw.groupby(
            [
                "combination_id",
                "candidate_ids",
                "project_count",
                "cumulative_length_m",
            ],
            as_index=False,
        )
        .agg(
            profile_count=(
                "rider_profile",
                "nunique",
            ),
            mean_total_benefit=(
                "demand_weighted_route_cost_reduction",
                "mean",
            ),
            min_profile_benefit=(
                "demand_weighted_route_cost_reduction",
                "min",
            ),
            max_profile_benefit=(
                "demand_weighted_route_cost_reduction",
                "max",
            ),
            mean_improved_demand=(
                "improved_demand",
                "mean",
            ),
            mean_improved_od_records=(
                "improved_od_records",
                "mean",
            ),
            mean_percent_cost_reduction=(
                "percent_baseline_cost_reduction",
                "mean",
            ),
        )
    )

    if not (
        grouped["profile_count"] == 4
    ).all():
        raise AssertionError(
            "A package is missing a rider profile."
        )

    selection_path = (
        output / "greedy_selection.csv"
    )

    if selection_path.exists():
        selection = pd.read_csv(
            selection_path
        )
    else:
        selection = pd.DataFrame()

    if args.round == 2:
        ranking = pd.read_csv(
            "results/robustness/"
            f"{args.mode}_candidate_ranking.csv"
        )

        first_id = base_ids[0]

        first = ranking.loc[
            ranking["candidate_id"] == first_id
        ]

        if len(first) != 1:
            raise AssertionError(
                f"Could not find isolated result for {first_id}."
            )

        base_benefit = float(
            first[
                "mean_route_cost_reduction"
            ].iloc[0]
        )

        candidate_table = pd.read_csv(
            "results/candidates/"
            "candidate_segments.csv"
        )

        first_length = float(
            candidate_table.loc[
                candidate_table["candidate_id"]
                == first_id,
                "length_m",
            ].iloc[0]
        )

        if selection.empty:
            selection = pd.DataFrame(
                [
                    {
                        "step": 1,
                        "selected_candidate":
                            first_id,
                        "package_ids":
                            first_id,
                        "project_count": 1,
                        "cumulative_length_m":
                            first_length,
                        "mean_total_benefit":
                            base_benefit,
                        "marginal_benefit":
                            base_benefit,
                    }
                ]
            )

    else:
        previous = selection.loc[
            selection["step"]
            == args.round - 1
        ]

        if len(previous) != 1:
            raise AssertionError(
                "Previous greedy selection not found."
            )

        base_benefit = float(
            previous[
                "mean_total_benefit"
            ].iloc[0]
        )

    grouped["marginal_benefit"] = (
        grouped["mean_total_benefit"]
        - base_benefit
    )

    grouped["candidate_added"] = (
        grouped["candidate_ids"]
        .str.split(";")
        .str[-1]
    )

    grouped = grouped.sort_values(
        [
            "marginal_benefit",
            "mean_improved_demand",
            "cumulative_length_m",
        ],
        ascending=[
            False,
            False,
            True,
        ],
    ).reset_index(drop=True)

    grouped["round_rank"] = range(
        1,
        len(grouped) + 1,
    )

    best = grouped.iloc[0]

    if float(
        best["marginal_benefit"]
    ) < -1e-8:
        raise AssertionError(
            "Best remaining project has "
            "negative marginal benefit."
        )

    new_row = pd.DataFrame(
        [
            {
                "step": args.round,
                "selected_candidate":
                    best["candidate_added"],
                "package_ids":
                    best["candidate_ids"],
                "project_count":
                    best["project_count"],
                "cumulative_length_m":
                    best["cumulative_length_m"],
                "mean_total_benefit":
                    best["mean_total_benefit"],
                "marginal_benefit":
                    best["marginal_benefit"],
            }
        ]
    )

    selection = selection.loc[
        selection["step"] != args.round
    ]

    selection = pd.concat(
        [
            selection,
            new_row,
        ],
        ignore_index=True,
    ).sort_values("step")

    grouped.to_csv(
        output
        / f"greedy_round_{args.round}_evaluations.csv",
        index=False,
    )

    raw.to_csv(
        output
        / f"greedy_round_{args.round}_profile_results.csv",
        index=False,
    )

    selection.to_csv(
        selection_path,
        index=False,
    )

    print()
    print(
        f"{args.mode} greedy round "
        f"{args.round} complete."
    )
    print()

    print(
        grouped[
            [
                "round_rank",
                "candidate_added",
                "candidate_ids",
                "mean_total_benefit",
                "marginal_benefit",
                "mean_improved_demand",
                "cumulative_length_m",
            ]
        ].to_string(index=False)
    )

    print()
    print("Selection:")
    print(
        selection.to_string(index=False)
    )


if __name__ == "__main__":
    main()
