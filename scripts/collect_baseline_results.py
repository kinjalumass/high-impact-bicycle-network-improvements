"""Collect lightweight summary outputs from the four baseline experiments."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from bike_improvements.project_paths import course_root


ROOT = course_root() / "baselines"

OUTPUT = Path("results/baseline")

PROFILES = [
    "child",
    "low_confidence_adult",
    "typical_adult",
    "experienced_adult",
]


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)

    summaries = []
    categories = []
    status_rows = []
    manifest_rows = []

    for profile in PROFILES:
        profile_dir = ROOT / profile

        summary_path = profile_dir / "summary.csv"
        category_path = profile_dir / "category_summary.csv"
        routes_path = profile_dir / "od_routes.csv"
        edges_path = profile_dir / "edge_usage.csv"
        origins_path = profile_dir / "origin_search_stats.csv"

        required = [
            summary_path,
            category_path,
            routes_path,
            edges_path,
            origins_path,
        ]

        missing = [
            str(path)
            for path in required
            if not path.exists()
        ]

        if missing:
            raise FileNotFoundError(
                f"{profile} is incomplete. Missing: {missing}"
            )

        summary = pd.read_csv(summary_path)
        category = pd.read_csv(category_path)

        routes = pd.read_csv(
            routes_path,
            dtype={
                "origin_node": str,
                "destination_node": str,
            },
        )

        summaries.append(summary)
        categories.append(category)

        for status, group in routes.groupby(
            ["found", "status"],
            dropna=False,
        ):
            found, status_name = status

            status_rows.append(
                {
                    "rider_profile": profile,
                    "found": found,
                    "status": status_name,
                    "od_records": len(group),
                    "modeled_demand": group["demand"].sum(),
                }
            )

        for path in required:
            manifest_rows.append(
                {
                    "rider_profile": profile,
                    "artifact": path.name,
                    "path": str(path),
                    "size_bytes": path.stat().st_size,
                }
            )

    summary_df = pd.concat(
        summaries,
        ignore_index=True,
    )

    category_df = pd.concat(
        categories,
        ignore_index=True,
    )

    status_df = pd.DataFrame(status_rows)
    manifest_df = pd.DataFrame(manifest_rows)

    # Sanity check: topology is identical, so reachability must match.
    reachability_columns = [
        "od_records",
        "od_records_routed",
        "total_demand",
        "routed_demand",
        "routing_success_rate_by_record",
        "routing_success_rate_by_demand",
    ]

    for column in reachability_columns:
        if summary_df[column].nunique(dropna=False) != 1:
            raise AssertionError(
                f"Reachability differs by profile for {column}."
            )

    summary_df.to_csv(
        OUTPUT / "four_profile_summary.csv",
        index=False,
    )

    category_df.to_csv(
        OUTPUT / "four_profile_category_summary.csv",
        index=False,
    )

    status_df.to_csv(
        OUTPUT / "routing_status_summary.csv",
        index=False,
    )

    manifest_df.to_csv(
        OUTPUT / "baseline_output_manifest.csv",
        index=False,
    )

    print("Four-profile baseline summary:")
    print(summary_df.to_string(index=False))

    print()
    print("Reachability consistency check PASSED.")

    print()
    print("Outputs written to:", OUTPUT)


if __name__ == "__main__":
    main()
