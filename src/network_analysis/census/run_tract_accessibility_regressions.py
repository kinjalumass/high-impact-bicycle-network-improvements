"""Aggregate node accessibility to Census tracts and run weighted regressions."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.multitest import multipletests


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=("Aggregate node accessibility to Census tracts and run tract-level regressions.")
    )

    parser.add_argument(
        "--input-path",
        type=Path,
        required=True,
        help=("Node-level CSV containing accessibility, population weights, tract assignments, and demographics."),
    )

    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="Directory for tract data, regression results, and summaries.",
    )

    return parser.parse_args()


# Each tuple contains:
# column name, coefficient interpretation, scaling denominator.
#
# Share and rate columns are divided by 0.10 so their coefficients
# represent a 10-percentage-point increase.
PREDICTORS = [
    ("share_under_18", "10 percentage-point increase", 0.10),
    ("share_age_65_plus", "10 percentage-point increase", 0.10),
    ("share_non_hispanic_black", "10 percentage-point increase", 0.10),
    ("share_non_hispanic_aian", "10 percentage-point increase", 0.10),
    ("share_non_hispanic_asian", "10 percentage-point increase", 0.10),
    ("share_non_hispanic_nhpi", "10 percentage-point increase", 0.10),
    (
        "share_non_hispanic_other_race",
        "10 percentage-point increase",
        0.10,
    ),
    (
        "share_non_hispanic_multiracial",
        "10 percentage-point increase",
        0.10,
    ),
    ("share_hispanic_or_latino", "10 percentage-point increase", 0.10),
    ("share_people_of_color", "10 percentage-point increase", 0.10),
    ("poverty_rate", "10 percentage-point increase", 0.10),
    (
        "zero_vehicle_household_rate",
        "10 percentage-point increase",
        0.10,
    ),
    ("renter_rate", "10 percentage-point increase", 0.10),
    ("disability_rate", "10 percentage-point increase", 0.10),
    (
        "limited_english_household_rate",
        "10 percentage-point increase",
        0.10,
    ),
    (
        "dominant_tract_median_household_income",
        "$10,000 increase",
        10000.0,
    ),
    ("dominant_tract_median_age", "10-year increase", 10.0),
]


def numeric(series: pd.Series) -> pd.Series:
    """Convert a series to numeric values."""
    return pd.to_numeric(series, errors="coerce")


def build_tract_table(data: pd.DataFrame) -> pd.DataFrame:
    """Build one population-weighted observation per Census tract."""
    available_predictors = [column for column, _, _ in PREDICTORS if column in data.columns]

    required_columns = {
        "node_id",
        "dominant_tract_geoid",
        "dominant_tract_county",
        "dominant_tract_population_share",
        "assigned_total_population",
        "relative_accessibility",
        "accessibility_status",
    }

    missing = sorted(required_columns.difference(data.columns))

    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    work = data.copy()

    work["assigned_total_population"] = numeric(work["assigned_total_population"])

    work["relative_accessibility"] = numeric(work["relative_accessibility"])

    work["dominant_tract_population_share"] = numeric(work["dominant_tract_population_share"])

    for column in available_predictors:
        work[column] = numeric(work[column])

    # Only use nodes whose entire population allocation came from
    # one Census tract. Mixed nodes would otherwise be attributed
    # completely to their dominant tract.
    valid = work[
        work["accessibility_status"].astype(str).str.lower().eq("success")
        & work["dominant_tract_geoid"].notna()
        & work["relative_accessibility"].between(0, 1)
        & (work["assigned_total_population"] > 0)
        & work["dominant_tract_population_share"].ge(0.999999)
    ].copy()

    if valid.empty:
        raise RuntimeError("No valid single-tract node rows were found.")

    valid["_weight"] = valid["assigned_total_population"]

    valid["_weighted_accessibility"] = valid["_weight"] * valid["relative_accessibility"]

    aggregation: dict[str, str] = {
        "_weight": "sum",
        "_weighted_accessibility": "sum",
        "node_id": "count",
        "dominant_tract_county": "first",
    }

    for column in available_predictors:
        weighted_column = f"_weighted__{column}"

        valid[weighted_column] = valid["_weight"] * valid[column]

        aggregation[weighted_column] = "sum"

    tracts = (
        valid.groupby(
            "dominant_tract_geoid",
            dropna=False,
        )
        .agg(aggregation)
        .reset_index()
        .rename(
            columns={
                "_weight": "represented_population",
                "node_id": "n_nodes",
                "dominant_tract_county": "county",
            }
        )
    )

    tracts["tract_accessibility"] = tracts["_weighted_accessibility"] / tracts["represented_population"]

    for column in available_predictors:
        weighted_column = f"_weighted__{column}"

        tracts[column] = tracts[weighted_column] / tracts["represented_population"]

    keep_columns = [
        "dominant_tract_geoid",
        "county",
        "represented_population",
        "n_nodes",
        "tract_accessibility",
        *available_predictors,
    ]

    return tracts[keep_columns].sort_values("dominant_tract_geoid").reset_index(drop=True)


def fit_regression(
    tracts: pd.DataFrame,
    predictor: str,
    effect_unit: str,
    scaling_denominator: float,
    model_type: str,
) -> dict[str, object] | None:
    """Fit one population-weighted tract regression."""
    required = [
        "tract_accessibility",
        "represented_population",
        "county",
        predictor,
    ]

    frame = tracts[required].replace([np.inf, -np.inf], np.nan).dropna().copy()

    frame = frame[frame["tract_accessibility"].between(0, 1) & (frame["represented_population"] > 0)].copy()

    if len(frame) < 30:
        return None

    if frame[predictor].nunique() < 3:
        return None

    frame["scaled_predictor"] = frame[predictor] / scaling_denominator

    design = pd.DataFrame(
        {
            "predictor": frame["scaled_predictor"],
        },
        index=frame.index,
    )

    if model_type == "county_adjusted":
        county_dummies = pd.get_dummies(
            frame["county"].astype(str),
            prefix="county",
            drop_first=True,
            dtype=float,
        )

        design = pd.concat(
            [design, county_dummies],
            axis=1,
        )

    design = sm.add_constant(
        design.astype(float),
        has_constant="add",
    )

    # Preserve relative population weighting without treating every
    # resident as a separate independent statistical observation.
    weights = frame["represented_population"] / frame["represented_population"].mean()

    try:
        result = sm.WLS(
            frame["tract_accessibility"].astype(float),
            design,
            weights=weights.astype(float),
        ).fit(cov_type="HC3")
    except (ValueError, np.linalg.LinAlgError):
        return None

    confidence_interval = result.conf_int().loc["predictor"]

    coefficient = float(result.params["predictor"])

    low = float(confidence_interval.iloc[0])

    high = float(confidence_interval.iloc[1])

    return {
        "model_type": model_type,
        "predictor": predictor,
        "effect_unit": effect_unit,
        "coefficient": coefficient,
        "coefficient_accessibility_percentage_points": (coefficient * 100.0),
        "ci_95_low": low,
        "ci_95_high": high,
        "ci_95_low_accessibility_percentage_points": (low * 100.0),
        "ci_95_high_accessibility_percentage_points": (high * 100.0),
        "standard_error": float(result.bse["predictor"]),
        "p_value": float(result.pvalues["predictor"]),
        "r_squared": float(result.rsquared),
        "n_tracts": len(frame),
        "represented_population": float(frame["represented_population"].sum()),
        "predictor_mean_raw": float(frame[predictor].mean()),
        "predictor_sd_raw": float(frame[predictor].std()),
        "nonzero_tracts": int((frame[predictor].abs() > 1e-12).sum()),
    }


def main() -> None:
    """Build the tract dataset and run the regressions."""
    args = parse_args()

    if not args.input_path.exists():
        raise FileNotFoundError(f"Input file not found: {args.input_path}")

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"Loading: {args.input_path}")

    data = pd.read_csv(
        args.input_path,
        low_memory=False,
    )

    print(f"Node rows loaded: {len(data):,}")

    tracts = build_tract_table(data)

    print(f"Single-tract Census observations: {len(tracts):,}")

    print(f"Represented population: {tracts['represented_population'].sum():,.2f}")

    tract_data_path = args.output_dir / "tract_level_regression_data.csv"

    tracts.to_csv(
        tract_data_path,
        index=False,
    )

    rows: list[dict[str, object]] = []

    for (
        predictor,
        effect_unit,
        scaling_denominator,
    ) in PREDICTORS:
        if predictor not in tracts.columns:
            print(f"Skipping missing predictor: {predictor}")
            continue

        for model_type in (
            "unadjusted",
            "county_adjusted",
        ):
            row = fit_regression(
                tracts=tracts,
                predictor=predictor,
                effect_unit=effect_unit,
                scaling_denominator=scaling_denominator,
                model_type=model_type,
            )

            if row is not None:
                rows.append(row)

    if not rows:
        raise RuntimeError("No tract-level regressions could be fitted.")

    results = pd.DataFrame(rows)

    results["fdr_adjusted_p_value"] = np.nan

    for indexes in results.groupby("model_type").groups.values():
        adjusted = multipletests(
            results.loc[
                indexes,
                "p_value",
            ].to_numpy(),
            method="fdr_bh",
        )[1]

        results.loc[
            indexes,
            "fdr_adjusted_p_value",
        ] = adjusted

    results["statistically_significant_fdr_0_05"] = results["fdr_adjusted_p_value"] < 0.05

    results = results.sort_values(
        [
            "model_type",
            "fdr_adjusted_p_value",
            "predictor",
        ],
        ascending=[True, True, True],
    ).reset_index(drop=True)

    results_path = args.output_dir / "tract_level_regression_results.csv"

    summary_path = args.output_dir / "tract_level_regression_summary.txt"

    results.to_csv(
        results_path,
        index=False,
    )

    display_columns = [
        "model_type",
        "predictor",
        "effect_unit",
        "coefficient_accessibility_percentage_points",
        "ci_95_low_accessibility_percentage_points",
        "ci_95_high_accessibility_percentage_points",
        "p_value",
        "fdr_adjusted_p_value",
        "n_tracts",
        "nonzero_tracts",
        "r_squared",
    ]

    summary_lines = [
        "Tract-level accessibility regressions",
        "=====================================",
        "",
        ("Outcome: population-weighted mean relative accessibility per tract"),
        ("Observations: nodes assigned entirely to one dominant Census tract"),
        ("Weights: represented tract population, normalized to mean 1"),
        ("Models: unadjusted and adjusted for county fixed effects"),
        "Uncertainty: HC3 robust standard errors",
        ("Multiple testing: Benjamini-Hochberg FDR within each model type"),
        "Interpretation: descriptive association, not causation",
        "",
        results[display_columns].to_string(index=False),
        "",
        f"Tract data: {tract_data_path}",
        f"Detailed results: {results_path}",
    ]

    summary_path.write_text(
        "\n".join(summary_lines),
        encoding="utf-8",
    )

    print("\nTRACT-LEVEL RESULTS")
    print("===================")

    print(results[display_columns].to_string(index=False))

    print(f"\nSaved: {tract_data_path}")
    print(f"Saved: {results_path}")
    print(f"Saved: {summary_path}")


if __name__ == "__main__":
    main()
