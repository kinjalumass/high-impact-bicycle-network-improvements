"""Create scatter plots for notable Census demographic regressions."""

from __future__ import annotations

import argparse
import base64
import html
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from bcu_analysis.census.run_tract_accessibility_regressions import (
    PREDICTORS,
)

PREDICTOR_LABELS = {
    "share_under_18": "Population under age 18",
    "share_age_65_plus": "Population age 65 and older",
    "share_non_hispanic_black": "Non-Hispanic Black population",
    "share_non_hispanic_aian": "Non-Hispanic AIAN population",
    "share_non_hispanic_asian": "Non-Hispanic Asian population",
    "share_non_hispanic_nhpi": "Non-Hispanic NHPI population",
    "share_non_hispanic_other_race": "Non-Hispanic other-race population",
    "share_non_hispanic_multiracial": "Non-Hispanic multiracial population",
    "share_hispanic_or_latino": "Hispanic or Latino population",
    "share_people_of_color": "People-of-color population",
    "poverty_rate": "Poverty rate",
    "zero_vehicle_household_rate": "Zero-vehicle household rate",
    "renter_rate": "Renter household rate",
    "disability_rate": "Disability rate",
    "limited_english_household_rate": "Limited-English household rate",
    "dominant_tract_median_household_income": "Median household income",
    "dominant_tract_median_age": "Median age",
}

PREDICTOR_CONFIGURATION = {
    predictor: {
        "effect_unit": effect_unit,
        "scaling_denominator": scaling_denominator,
    }
    for predictor, effect_unit, scaling_denominator in PREDICTORS
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create population-weighted county-adjusted scatter plots for notable tract-level demographic regressions."
        )
    )

    parser.add_argument(
        "--tract-path",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--results-path",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--fdr-threshold",
        type=float,
        default=0.05,
    )
    parser.add_argument(
        "--max-plots",
        type=int,
        default=8,
    )
    parser.add_argument(
        "--fallback-count",
        type=int,
        default=4,
        help=("Number of lowest-FDR results to plot when no model passes the requested FDR threshold."),
    )
    parser.add_argument(
        "--title-suffix",
        default="",
    )

    return parser.parse_args()


def slugify(value: str) -> str:
    slug = re.sub(
        r"[^a-z0-9]+",
        "_",
        value.lower(),
    ).strip("_")

    return slug or "plot"


def format_p_value(value: float) -> str:
    if value < 0.001:
        return f"{value:.2e}"

    return f"{value:.3f}"


def display_x(
    values: pd.Series | np.ndarray,
    predictor: str,
) -> pd.Series | np.ndarray:
    if predictor.startswith("share_") or predictor.endswith("_rate"):
        return values * 100.0

    if predictor == "dominant_tract_median_household_income":
        return values / 1000.0

    return values


def x_axis_label(predictor: str) -> str:
    label = PREDICTOR_LABELS.get(
        predictor,
        predictor.replace("_", " ").title(),
    )

    if predictor.startswith("share_") or predictor.endswith("_rate"):
        return f"{label} (%)"

    if predictor == "dominant_tract_median_household_income":
        return f"{label} ($1,000s)"

    if predictor == "dominant_tract_median_age":
        return f"{label} (years)"

    return label


def load_inputs(
    tract_path: Path,
    results_path: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not tract_path.is_file():
        raise FileNotFoundError(tract_path)

    if not results_path.is_file():
        raise FileNotFoundError(results_path)

    tracts = pd.read_csv(
        tract_path,
        dtype={"dominant_tract_geoid": "string"},
    )

    results = pd.read_csv(results_path)

    required_tract_columns = {
        "dominant_tract_geoid",
        "county",
        "represented_population",
        "tract_accessibility",
    }

    missing_tract = required_tract_columns - set(tracts.columns)

    if missing_tract:
        raise ValueError(f"Tract data is missing required columns: {sorted(missing_tract)}")

    required_result_columns = {
        "model_type",
        "predictor",
        "effect_unit",
        "coefficient",
        "coefficient_accessibility_percentage_points",
        "ci_95_low_accessibility_percentage_points",
        "ci_95_high_accessibility_percentage_points",
        "fdr_adjusted_p_value",
        "r_squared",
        "n_tracts",
    }

    missing_results = required_result_columns - set(results.columns)

    if missing_results:
        raise ValueError(f"Regression results are missing required columns: {sorted(missing_results)}")

    return tracts, results


def select_notable_results(
    results: pd.DataFrame,
    fdr_threshold: float,
    max_plots: int,
    fallback_count: int,
) -> pd.DataFrame:
    county_adjusted = results.loc[results["model_type"].eq("county_adjusted")].copy()

    if county_adjusted.empty:
        raise RuntimeError("No county-adjusted regression results were found.")

    county_adjusted["fdr_adjusted_p_value"] = pd.to_numeric(
        county_adjusted["fdr_adjusted_p_value"],
        errors="raise",
    )

    county_adjusted = county_adjusted.sort_values(
        [
            "fdr_adjusted_p_value",
            "predictor",
        ],
        ascending=[True, True],
    ).reset_index(drop=True)

    selected = county_adjusted.loc[county_adjusted["fdr_adjusted_p_value"] <= fdr_threshold].copy()

    if selected.empty:
        selected = county_adjusted.head(min(fallback_count, len(county_adjusted))).copy()

        selected["selection_reason"] = "Lowest FDR values; none passed the requested threshold"
    else:
        selected["selection_reason"] = f"County-adjusted FDR <= {fdr_threshold:g}"

    return selected.head(max_plots).reset_index(drop=True)


def prepare_model(
    tracts: pd.DataFrame,
    predictor: str,
    scaling_denominator: float,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    object,
]:
    required_columns = [
        "tract_accessibility",
        "represented_population",
        "county",
        predictor,
    ]

    frame = tracts[required_columns].replace([np.inf, -np.inf], np.nan).dropna().copy()

    numeric_columns = [
        "tract_accessibility",
        "represented_population",
        predictor,
    ]

    for column in numeric_columns:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

    frame = frame.dropna(subset=numeric_columns).copy()

    frame = frame.loc[frame["tract_accessibility"].between(0, 1) & frame["represented_population"].gt(0)].copy()

    if len(frame) < 30:
        raise RuntimeError(f"{predictor}: fewer than 30 valid tracts")

    frame["county"] = frame["county"].astype(str)

    frame["scaled_predictor"] = frame[predictor] / scaling_denominator

    design = pd.DataFrame(
        {
            "predictor": frame["scaled_predictor"],
        },
        index=frame.index,
    )

    county_dummies = pd.get_dummies(
        frame["county"],
        prefix="county",
        drop_first=True,
        dtype=float,
    )

    design = pd.concat(
        [
            design,
            county_dummies,
        ],
        axis=1,
    )

    design = sm.add_constant(
        design.astype(float),
        has_constant="add",
    )

    weights = frame["represented_population"] / frame["represented_population"].mean()

    model = sm.WLS(
        frame["tract_accessibility"].astype(float),
        design,
        weights=weights.astype(float),
    ).fit(cov_type="HC3")

    return frame, design, model


def prediction_frame(
    x_values: np.ndarray,
    county: str,
    design_columns: list[str],
    scaling_denominator: float,
) -> pd.DataFrame:
    prediction = pd.DataFrame(
        0.0,
        index=range(len(x_values)),
        columns=design_columns,
    )

    prediction["const"] = 1.0

    prediction["predictor"] = x_values / scaling_denominator

    county_column = f"county_{county}"

    if county_column in prediction.columns:
        prediction[county_column] = 1.0

    return prediction


def create_plot(
    tracts: pd.DataFrame,
    result: pd.Series,
    output_path: Path,
    title_suffix: str,
) -> dict[str, object]:
    predictor = str(result["predictor"])

    if predictor not in PREDICTOR_CONFIGURATION:
        raise ValueError(f"Unknown predictor configuration: {predictor}")

    configuration = PREDICTOR_CONFIGURATION[predictor]

    scaling_denominator = float(configuration["scaling_denominator"])

    frame, design, model = prepare_model(
        tracts=tracts,
        predictor=predictor,
        scaling_denominator=scaling_denominator,
    )

    saved_coefficient = float(result["coefficient"])

    fitted_coefficient = float(model.params["predictor"])

    if not np.isclose(
        fitted_coefficient,
        saved_coefficient,
        rtol=1e-8,
        atol=1e-10,
    ):
        raise RuntimeError(
            f"{predictor}: fitted coefficient "
            f"{fitted_coefficient} does not match saved "
            f"coefficient {saved_coefficient}"
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    figure, axis = plt.subplots(
        figsize=(11.5, 7.5),
    )

    maximum_population = float(frame["represented_population"].max())

    county_order = sorted(frame["county"].unique().tolist())

    for county in county_order:
        county_frame = frame.loc[frame["county"].eq(county)].copy()

        population_ratio = county_frame["represented_population"] / maximum_population

        marker_sizes = 22.0 + 145.0 * np.sqrt(population_ratio)

        points = axis.scatter(
            display_x(
                county_frame[predictor],
                predictor,
            ),
            county_frame["tract_accessibility"] * 100.0,
            s=marker_sizes,
            alpha=0.66,
            linewidths=0.35,
            label=county,
        )

        x_min = float(county_frame[predictor].min())

        x_max = float(county_frame[predictor].max())

        if np.isclose(x_min, x_max):
            continue

        raw_x = np.linspace(
            x_min,
            x_max,
            100,
        )

        prediction = prediction_frame(
            x_values=raw_x,
            county=county,
            design_columns=design.columns.tolist(),
            scaling_denominator=scaling_denominator,
        )

        predicted_y = model.predict(prediction)

        face_colors = points.get_facecolor()

        line_kwargs: dict[str, object] = {}

        if len(face_colors):
            line_kwargs["color"] = face_colors[0]

        axis.plot(
            display_x(
                raw_x,
                predictor,
            ),
            predicted_y * 100.0,
            linewidth=2.0,
            **line_kwargs,
        )

    predictor_label = PREDICTOR_LABELS.get(
        predictor,
        predictor.replace("_", " ").title(),
    )

    title = f"Relative accessibility and {predictor_label}"

    if title_suffix:
        title = f"{title}\n{title_suffix}"

    axis.set_title(
        title,
        fontsize=15,
        pad=13,
    )

    axis.set_xlabel(
        x_axis_label(predictor),
        fontsize=12,
    )

    axis.set_ylabel(
        "Population-weighted relative accessibility (%)",
        fontsize=12,
    )

    axis.grid(
        alpha=0.22,
        linewidth=0.6,
    )

    axis.set_axisbelow(True)

    effect_pp = float(result["coefficient_accessibility_percentage_points"])

    ci_low = float(result["ci_95_low_accessibility_percentage_points"])

    ci_high = float(result["ci_95_high_accessibility_percentage_points"])

    fdr = float(result["fdr_adjusted_p_value"])

    r_squared = float(result["r_squared"])

    n_tracts = int(result["n_tracts"])

    effect_unit = str(result["effect_unit"])

    annotation = "\n".join(
        [
            "County-adjusted population-weighted WLS",
            (f"Effect: {effect_pp:+.3f} accessibility percentage points per {effect_unit}"),
            f"95% CI: [{ci_low:+.3f}, {ci_high:+.3f}]",
            f"FDR-adjusted p-value: {format_p_value(fdr)}",
            f"Full-model R²: {r_squared:.3f}",
            f"Census tracts: {n_tracts:,}",
            "Descriptive association; not causation",
        ]
    )

    axis.text(
        0.015,
        0.985,
        annotation,
        transform=axis.transAxes,
        va="top",
        ha="left",
        fontsize=9.5,
        bbox={
            "boxstyle": "round,pad=0.55",
            "facecolor": "white",
            "edgecolor": "#777777",
            "alpha": 0.92,
        },
    )

    axis.legend(
        title="County",
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        borderaxespad=0,
        frameon=True,
    )

    figure.tight_layout(
        rect=(0.0, 0.0, 0.82, 1.0),
    )

    figure.savefig(
        output_path,
        dpi=300,
        bbox_inches="tight",
    )

    plt.close(figure)

    return {
        "predictor": predictor,
        "predictor_label": predictor_label,
        "effect_unit": effect_unit,
        "coefficient_accessibility_percentage_points": effect_pp,
        "ci_95_low_accessibility_percentage_points": ci_low,
        "ci_95_high_accessibility_percentage_points": ci_high,
        "fdr_adjusted_p_value": fdr,
        "r_squared": r_squared,
        "n_tracts": n_tracts,
        "plot_path": output_path.name,
        "selection_reason": result["selection_reason"],
    }


def write_gallery(
    records: list[dict[str, object]],
    output_path: Path,
    title_suffix: str,
) -> None:
    cards = []

    for record in records:
        predictor_label = html.escape(str(record["predictor_label"]))

        image_path = output_path.parent / str(record["plot_path"])

        if not image_path.is_file():
            raise FileNotFoundError(image_path)

        encoded_image = base64.b64encode(image_path.read_bytes()).decode("ascii")

        image_uri = "data:image/png;base64," + encoded_image

        effect = float(record["coefficient_accessibility_percentage_points"])

        fdr = float(record["fdr_adjusted_p_value"])

        r_squared = float(record["r_squared"])

        cards.append(
            f"""
            <article class="card">
                <h2>{predictor_label}</h2>
                <a href="{image_uri}">
                    <img
                      src="{image_uri}"
                      alt="{predictor_label} regression scatter plot"
                    >
                </a>
                <p>
                    Effect: {effect:+.3f} accessibility percentage
                    points; FDR {format_p_value(fdr)};
                    R² {r_squared:.3f}.
                </p>
            </article>
            """
        )

    suffix = html.escape(title_suffix)

    rendered = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta
  name="viewport"
  content="width=device-width, initial-scale=1"
>
<title>Notable Census demographic regressions</title>
<style>
body {{
    margin: 0;
    padding: 24px;
    font-family: Arial, Helvetica, sans-serif;
    color: #222;
    background: #f4f4f4;
}}

h1 {{
    margin: 0 0 6px;
}}

.subtitle {{
    margin: 0 0 22px;
    color: #555;
}}

.grid {{
    display: grid;
    grid-template-columns: repeat(
        auto-fit,
        minmax(440px, 1fr)
    );
    gap: 22px;
}}

.card {{
    padding: 16px;
    border: 1px solid #ccc;
    border-radius: 7px;
    background: white;
}}

.card h2 {{
    margin: 0 0 12px;
    font-size: 18px;
}}

.card img {{
    display: block;
    width: 100%;
    height: auto;
}}

.card p {{
    margin: 12px 0 0;
    line-height: 1.45;
}}
</style>
</head>
<body>
<h1>Notable Census demographic regression results</h1>
<p class="subtitle">{suffix}</p>
<div class="grid">
{"".join(cards)}
</div>
</body>
</html>
"""

    output_path.write_text(
        rendered,
        encoding="utf-8",
    )


def main() -> None:
    args = parse_args()

    if not 0 < args.fdr_threshold <= 1:
        raise ValueError("--fdr-threshold must be between 0 and 1.")

    if args.max_plots < 1:
        raise ValueError("--max-plots must be at least 1.")

    tracts, results = load_inputs(
        tract_path=args.tract_path,
        results_path=args.results_path,
    )

    selected = select_notable_results(
        results=results,
        fdr_threshold=args.fdr_threshold,
        max_plots=args.max_plots,
        fallback_count=args.fallback_count,
    )

    args.output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    print(f"Selected notable regressions: {len(selected)}")

    records = []

    for rank, row in selected.iterrows():
        predictor = str(row["predictor"])

        filename = f"{rank + 1:02d}_{slugify(predictor)}_scatter.png"

        output_path = args.output_dir / filename

        print(f"Creating: {output_path}")

        record = create_plot(
            tracts=tracts,
            result=row,
            output_path=output_path,
            title_suffix=args.title_suffix,
        )

        records.append(record)

    manifest = pd.DataFrame(records)

    manifest_path = args.output_dir / "notable_regression_scatterplots.csv"

    manifest.to_csv(
        manifest_path,
        index=False,
    )

    gallery_path = args.output_dir / "notable_regression_scatterplots.html"

    write_gallery(
        records=records,
        output_path=gallery_path,
        title_suffix=args.title_suffix,
    )

    print()
    print(
        manifest[
            [
                "predictor",
                "coefficient_accessibility_percentage_points",
                "fdr_adjusted_p_value",
                "r_squared",
                "plot_path",
            ]
        ].to_string(index=False)
    )

    print()
    print(f"Manifest: {manifest_path}")
    print(f"Gallery: {gallery_path}")


if __name__ == "__main__":
    main()
