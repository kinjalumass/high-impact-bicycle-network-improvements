"""Assign ACS demographic estimates and accessibility results to graph nodes."""

import argparse
from pathlib import Path

import numpy as np
import osmnx as ox
import pandas as pd


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=("Assign ACS demographic estimates to graph nodes and join node-level accessibility results.")
    )

    parser.add_argument(
        "--graph-path",
        type=Path,
        required=True,
        help="GraphML file containing the analysis graph.",
    )

    parser.add_argument(
        "--allocation-path",
        type=Path,
        required=True,
        help="Census tract-to-node allocation CSV.",
    )

    parser.add_argument(
        "--tract-demographics-path",
        type=Path,
        required=True,
        help="Clean tract-level ACS demographics CSV.",
    )

    parser.add_argument(
        "--accessibility-path",
        type=Path,
        required=True,
        help="Node-level accessibility-results CSV.",
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="Directory for node-level demographic outputs.",
    )

    parser.add_argument(
        "--output-prefix",
        required=True,
        help=("Filename prefix, such as greater_boston_pruned or greater_boston_exclude_lts0."),
    )

    return parser.parse_args()


ADDITIVE_COLUMNS = [
    "total_population",
    "age_under_18",
    "age_18_to_64",
    "age_65_plus",
    "non_hispanic_white",
    "non_hispanic_black",
    "non_hispanic_aian",
    "non_hispanic_asian",
    "non_hispanic_nhpi",
    "non_hispanic_other_race",
    "non_hispanic_multiracial",
    "hispanic_or_latino",
    "poverty_universe",
    "below_poverty",
    "vehicle_households",
    "zero_vehicle_households",
    "occupied_housing_units",
    "renter_occupied_units",
    "disability_universe",
    "people_with_disability",
    "limited_english_household_universe",
    "limited_english_households",
]


def safe_ratio(
    numerator: pd.Series,
    denominator: pd.Series,
) -> pd.Series:
    """Divide only where the denominator is positive."""

    valid_denominator = denominator.where(denominator > 0)

    return numerator / valid_denominator


def sum_with_missing(series: pd.Series):
    """Sum while preserving missing when every value is missing."""

    return series.sum(min_count=1)


def main() -> None:
    args = parse_args()

    required_inputs = [
        args.graph_path,
        args.allocation_path,
        args.tract_demographics_path,
        args.accessibility_path,
    ]

    for input_path in required_inputs:
        if not input_path.is_file():
            raise FileNotFoundError(input_path)

    if not args.output_prefix.strip():
        raise ValueError("--output-prefix cannot be empty.")

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_csv = args.output_directory / (f"{args.output_prefix}_nodes_with_demographics_and_accessibility.csv")

    output_parquet = args.output_directory / (
        f"{args.output_prefix}_nodes_with_demographics_and_accessibility.parquet"
    )

    dominant_tract_output = args.output_directory / f"{args.output_prefix}_node_dominant_tract.csv"
    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Loading pruned graph...")

    graph = ox.load_graphml(args.graph_path)

    graph_nodes = pd.DataFrame(
        [
            {
                "node_id": str(node_id),
                "longitude": float(attributes["x"]),
                "latitude": float(attributes["y"]),
            }
            for node_id, attributes in graph.nodes(data=True)
        ]
    )

    print(f"Graph nodes: {len(graph_nodes):,}")

    print("Loading tract-to-node allocation...")

    allocation = pd.read_csv(
        args.allocation_path,
        dtype={
            "node_id": str,
            "GEOID": str,
        },
    )

    allocation["GEOID"] = (
        allocation["GEOID"]
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
        .str.zfill(11)
    )

    allocation["area_share"] = pd.to_numeric(
        allocation["area_share"],
        errors="coerce",
    )

    allocation["assigned_population"] = pd.to_numeric(
        allocation["assigned_population"],
        errors="coerce",
    )

    print(f"Allocation rows: {len(allocation):,}")

    print("Loading tract demographics...")

    tracts = pd.read_csv(
        args.tract_demographics_path,
        dtype={"GEOID": str},
    )

    tracts["GEOID"] = (
        tracts["GEOID"]
        .str.replace(
            r"\.0$",
            "",
            regex=True,
        )
        .str.zfill(11)
    )

    required_tract_columns = [
        "GEOID",
        "NAME",
        "county_name",
        "median_household_income",
        "median_age",
        *ADDITIVE_COLUMNS,
    ]

    missing_columns = [column for column in required_tract_columns if column not in tracts.columns]

    if missing_columns:
        raise KeyError(f"Missing demographic columns: {missing_columns}")

    tract_columns = tracts[required_tract_columns].copy()

    merged = allocation.merge(
        tract_columns,
        on="GEOID",
        how="left",
        validate="many_to_one",
        indicator=True,
    )

    unmatched_allocation_rows = (merged["_merge"].ne("both")).sum()

    if unmatched_allocation_rows:
        raise ValueError(f"Allocation rows without ACS tract data: {unmatched_allocation_rows:,}")

    merged = merged.drop(columns="_merge")

    print("Allocating additive demographic counts...")

    contribution_columns = []

    for column in ADDITIVE_COLUMNS:
        contribution_column = f"assigned_{column}"

        merged[contribution_column] = (
            pd.to_numeric(
                merged[column],
                errors="coerce",
            )
            * merged["area_share"]
        )

        contribution_columns.append(contribution_column)

    population_difference = merged["assigned_total_population"] - merged["assigned_population"]

    print(
        "Maximum population allocation difference:",
        f"{population_difference.abs().max():.12f}",
    )

    node_aggregation = {column: sum_with_missing for column in contribution_columns}

    node_aggregation["GEOID"] = "nunique"
    node_aggregation["area_share"] = "count"

    node_demographics = (
        merged.groupby(
            "node_id",
            as_index=False,
        )
        .agg(node_aggregation)
        .rename(
            columns={
                "GEOID": "contributing_tract_count",
                "area_share": "allocation_row_count",
            }
        )
    )

    print("Selecting each node's dominant contributing tract...")

    dominant = (
        merged.sort_values(
            [
                "node_id",
                "assigned_population",
                "area_share",
                "GEOID",
            ],
            ascending=[
                True,
                False,
                False,
                True,
            ],
        )
        .drop_duplicates(
            subset="node_id",
            keep="first",
        )[
            [
                "node_id",
                "GEOID",
                "NAME",
                "county_name",
                "assigned_population",
                "median_household_income",
                "median_age",
            ]
        ]
        .rename(
            columns={
                "GEOID": "dominant_tract_geoid",
                "NAME": "dominant_tract_name",
                "county_name": "dominant_tract_county",
                "assigned_population": ("dominant_tract_population_contribution"),
                "median_household_income": ("dominant_tract_median_household_income"),
                "median_age": ("dominant_tract_median_age"),
            }
        )
    )

    dominant.to_csv(
        dominant_tract_output,
        index=False,
    )

    node_demographics = node_demographics.merge(
        dominant,
        on="node_id",
        how="left",
        validate="one_to_one",
    )

    node_demographics["dominant_tract_population_share"] = safe_ratio(
        node_demographics["dominant_tract_population_contribution"],
        node_demographics["assigned_total_population"],
    )

    print("Calculating node-level demographic rates...")

    node_demographics["share_under_18"] = safe_ratio(
        node_demographics["assigned_age_under_18"],
        node_demographics["assigned_total_population"],
    )

    node_demographics["share_age_18_to_64"] = safe_ratio(
        node_demographics["assigned_age_18_to_64"],
        node_demographics["assigned_total_population"],
    )

    node_demographics["share_age_65_plus"] = safe_ratio(
        node_demographics["assigned_age_65_plus"],
        node_demographics["assigned_total_population"],
    )

    race_rate_columns = {
        "share_non_hispanic_white": ("assigned_non_hispanic_white"),
        "share_non_hispanic_black": ("assigned_non_hispanic_black"),
        "share_non_hispanic_aian": ("assigned_non_hispanic_aian"),
        "share_non_hispanic_asian": ("assigned_non_hispanic_asian"),
        "share_non_hispanic_nhpi": ("assigned_non_hispanic_nhpi"),
        "share_non_hispanic_other_race": ("assigned_non_hispanic_other_race"),
        "share_non_hispanic_multiracial": ("assigned_non_hispanic_multiracial"),
        "share_hispanic_or_latino": ("assigned_hispanic_or_latino"),
    }

    for rate_column, count_column in race_rate_columns.items():
        node_demographics[rate_column] = safe_ratio(
            node_demographics[count_column],
            node_demographics["assigned_total_population"],
        )

    node_demographics["share_people_of_color"] = 1 - node_demographics["share_non_hispanic_white"]

    node_demographics["poverty_rate"] = safe_ratio(
        node_demographics["assigned_below_poverty"],
        node_demographics["assigned_poverty_universe"],
    )

    node_demographics["zero_vehicle_household_rate"] = safe_ratio(
        node_demographics["assigned_zero_vehicle_households"],
        node_demographics["assigned_vehicle_households"],
    )

    node_demographics["renter_rate"] = safe_ratio(
        node_demographics["assigned_renter_occupied_units"],
        node_demographics["assigned_occupied_housing_units"],
    )

    node_demographics["disability_rate"] = safe_ratio(
        node_demographics["assigned_people_with_disability"],
        node_demographics["assigned_disability_universe"],
    )

    node_demographics["limited_english_household_rate"] = safe_ratio(
        node_demographics["assigned_limited_english_households"],
        node_demographics["assigned_limited_english_household_universe"],
    )

    print("Joining all pruned graph nodes...")

    output = graph_nodes.merge(
        node_demographics,
        on="node_id",
        how="left",
        validate="one_to_one",
    )

    output["demographic_status"] = np.where(
        output["allocation_row_count"].notna(),
        "allocated",
        "outside_or_unallocated",
    )

    zero_population = output["demographic_status"].eq("allocated") & output["assigned_total_population"].fillna(0).eq(
        0
    )

    output.loc[
        zero_population,
        "demographic_status",
    ] = "allocated_zero_population"

    print("Joining accessibility results...")

    accessibility = pd.read_csv(
        args.accessibility_path,
        dtype={"node_id": str},
    )

    accessibility_columns = [
        "node_id",
        "absolute_accessibility_miles",
        "distance_reachable_road_miles",
        "relative_accessibility",
        "calculation_status",
    ]

    missing_accessibility_columns = [column for column in accessibility_columns if column not in accessibility.columns]

    if missing_accessibility_columns:
        raise KeyError(f"Missing accessibility columns: {missing_accessibility_columns}")

    accessibility = accessibility[accessibility_columns].rename(
        columns={"calculation_status": ("accessibility_status")}
    )

    output = output.merge(
        accessibility,
        on="node_id",
        how="left",
        validate="one_to_one",
    )

    output.to_csv(
        output_csv,
        index=False,
    )

    output.to_parquet(
        output_parquet,
        index=False,
    )

    print()
    print("NODE DEMOGRAPHIC ASSIGNMENT SUMMARY")
    print("===================================")
    print(f"Output nodes: {len(output):,}")
    print(
        "Unique output nodes:",
        f"{output['node_id'].nunique():,}",
    )

    print()
    print("Demographic status")
    print("------------------")
    print(output["demographic_status"].value_counts(dropna=False).to_string())

    assigned_population_total = output["assigned_total_population"].sum()

    allocation_population_total = allocation["assigned_population"].sum()

    print()
    print(
        "Node assigned population total:",
        f"{assigned_population_total:,.6f}",
    )
    print(
        "Allocation population total:",
        f"{allocation_population_total:,.6f}",
    )
    print(
        "Population difference:",
        f"{assigned_population_total - allocation_population_total:,.12f}",
    )

    age_sum = output["assigned_age_under_18"] + output["assigned_age_18_to_64"] + output["assigned_age_65_plus"]

    race_columns = [
        "assigned_non_hispanic_white",
        "assigned_non_hispanic_black",
        "assigned_non_hispanic_aian",
        "assigned_non_hispanic_asian",
        "assigned_non_hispanic_nhpi",
        "assigned_non_hispanic_other_race",
        "assigned_non_hispanic_multiracial",
        "assigned_hispanic_or_latino",
    ]

    race_sum = output[race_columns].sum(
        axis=1,
        min_count=1,
    )

    age_total_difference = (age_sum - output["assigned_total_population"]).abs().max()

    race_total_difference = (race_sum - output["assigned_total_population"]).abs().max()

    print()
    print("DEMOGRAPHIC CONSISTENCY")
    print("-----------------------")
    print(
        "Maximum node age-total difference:",
        f"{age_total_difference:.12f}",
    )
    print(
        "Maximum node race-total difference:",
        f"{race_total_difference:.12f}",
    )

    rate_columns = [
        "share_under_18",
        "share_age_65_plus",
        "share_non_hispanic_black",
        "share_non_hispanic_asian",
        "share_hispanic_or_latino",
        "share_people_of_color",
        "poverty_rate",
        "zero_vehicle_household_rate",
        "renter_rate",
        "disability_rate",
        "limited_english_household_rate",
    ]

    invalid_rate_counts = {}

    for column in rate_columns:
        invalid_rate_counts[column] = (
            output[column].notna()
            & ~output[column].between(
                0,
                1,
            )
        ).sum()

    print()
    print("RATES OUTSIDE 0–1")
    print("-----------------")
    print(pd.Series(invalid_rate_counts).to_string())

    missing_median_income = output["dominant_tract_median_household_income"].isna().sum()

    missing_median_age = output["dominant_tract_median_age"].isna().sum()

    print()
    print("Missing non-additive estimates")
    print("------------------------------")
    print(
        "Nodes missing dominant-tract median income:",
        f"{missing_median_income:,}",
    )
    print(
        "Nodes missing dominant-tract median age:",
        f"{missing_median_age:,}",
    )

    print()
    print("Selected node-level rate summary")
    print("--------------------------------")

    print(output[rate_columns].describe().T.to_string())

    print()
    print("Saved:")
    print(output_csv)
    print(output_parquet)
    print(dominant_tract_output)


if __name__ == "__main__":
    main()
