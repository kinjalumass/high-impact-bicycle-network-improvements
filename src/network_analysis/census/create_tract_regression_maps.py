"""Create an interactive Census-tract accessibility and regression map."""

from __future__ import annotations

import argparse
import html
import json
from collections import OrderedDict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import statsmodels.api as sm

SPECIAL_LABELS = {
    "share_under_18": "Population under age 18",
    "share_age_65_plus": "Population age 65 and older",
    "share_non_hispanic_white": "Non-Hispanic White population",
    "share_non_hispanic_black": "Non-Hispanic Black population",
    "share_non_hispanic_aian": "Non-Hispanic AIAN population",
    "share_non_hispanic_asian": "Non-Hispanic Asian population",
    "share_non_hispanic_nhpi": "Non-Hispanic NHPI population",
    "share_non_hispanic_other_race": ("Non-Hispanic other-race population"),
    "share_non_hispanic_multiracial": ("Non-Hispanic multiracial population"),
    "share_hispanic_or_latino": "Hispanic or Latino population",
    "share_people_of_color": "People-of-color population",
    "poverty_rate": "Poverty rate",
    "zero_vehicle_household_rate": "Zero-vehicle household rate",
    "renter_rate": "Renter household rate",
    "disability_rate": "Disability rate",
    "limited_english_household_rate": ("Limited-English household rate"),
    "dominant_tract_median_household_income": ("Median household income"),
    "dominant_tract_median_age": "Median age",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a Census-tract interactive map containing "
            "LTS-0-excluded accessibility, demographics, and "
            "regression residuals."
        )
    )

    parser.add_argument(
        "--tract-path",
        type=Path,
        required=True,
        help=("Tract-level regression data produced from accessibility results that exclude LTS 0."),
    )

    parser.add_argument(
        "--results-path",
        type=Path,
        required=True,
        help=("Tract-level regression results produced from accessibility results that exclude LTS 0."),
    )

    parser.add_argument(
        "--tract-geometry-path",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--title",
        default=("Greater Boston Census-Tract Accessibility, Demographics, and Regression Results - Excluding LTS 0"),
    )

    return parser.parse_args()


def normalize_geoid_value(value: object) -> object:
    if pd.isna(value):
        return pd.NA

    text = str(value).strip()

    if not text:
        return pd.NA

    try:
        number = Decimal(text)

        if number != number.to_integral_value():
            raise ValueError(f"Tract GEOID is not integer-like: {value!r}")

        result = str(int(number)).zfill(11)

        if len(result) != 11:
            raise ValueError(f"Expected an 11-digit tract GEOID: {value!r}")

        return result

    except (InvalidOperation, ValueError):
        digits = "".join(character for character in text if character.isdigit())

        if len(digits) == 11:
            return digits

        return pd.NA


def normalize_geoid(series: pd.Series) -> pd.Series:
    return pd.Series(
        [normalize_geoid_value(value) for value in series],
        index=series.index,
        dtype="string",
    )


def humanize_predictor(predictor: str) -> str:
    if predictor in SPECIAL_LABELS:
        return SPECIAL_LABELS[predictor]

    text = predictor.replace("dominant_tract_", "")
    text = text.replace("_", " ")

    replacements = {
        "aian": "AIAN",
        "nhpi": "NHPI",
        "non hispanic": "Non-Hispanic",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text[:1].upper() + text[1:]


def predictor_format(predictor: str) -> str:
    if predictor.startswith("share_") or predictor.endswith("_rate"):
        return "percent"

    if "income" in predictor:
        return "currency"

    if "age" in predictor:
        return "number"

    return "number"


def effect_scale(effect_unit: str) -> float:
    normalized = str(effect_unit).lower()

    if "10 percentage-point" in normalized:
        return 0.1

    if "10-year" in normalized:
        return 10.0

    if "$10,000" in normalized or "10,000" in normalized:
        return 10_000.0

    return 1.0


def require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(path)

    if not path.is_file():
        raise ValueError(f"Expected a file, but found: {path}")


def read_tract_data(path: Path) -> pd.DataFrame:
    require_file(path)

    data = pd.read_csv(
        path,
        dtype={"dominant_tract_geoid": "string"},
    )

    required = {
        "dominant_tract_geoid",
        "county",
        "represented_population",
        "n_nodes",
        "tract_accessibility",
    }

    missing = required - set(data.columns)

    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")

    data["tract_geoid"] = normalize_geoid(data["dominant_tract_geoid"])

    if data["tract_geoid"].isna().any():
        bad_values = data.loc[
            data["tract_geoid"].isna(),
            "dominant_tract_geoid",
        ].head(10)

        raise ValueError(f"Could not normalize some tract GEOIDs:\n{bad_values.to_string(index=False)}")

    if data["tract_geoid"].duplicated().any():
        raise ValueError(f"Duplicate tract GEOIDs were found in {path}")

    numeric_columns = [
        "represented_population",
        "n_nodes",
        "tract_accessibility",
    ]

    for column in numeric_columns:
        data[column] = pd.to_numeric(
            data[column],
            errors="raise",
        )

    if not data["tract_accessibility"].between(0, 1).all():
        raise ValueError(f"Accessibility values outside [0, 1] in {path}")

    if not (data["represented_population"] > 0).all():
        raise ValueError(f"Nonpositive represented population in {path}")

    return data.sort_values("tract_geoid").reset_index(drop=True)


def read_regression_results(path: Path) -> pd.DataFrame:
    require_file(path)

    results = pd.read_csv(path)

    required = {
        "model_type",
        "predictor",
        "effect_unit",
        "coefficient",
        "coefficient_accessibility_percentage_points",
        "ci_95_low_accessibility_percentage_points",
        "ci_95_high_accessibility_percentage_points",
        "fdr_adjusted_p_value",
        "r_squared",
        "statistically_significant_fdr_0_05",
    }

    missing = required - set(results.columns)

    if missing:
        raise ValueError(f"{path} is missing columns: {sorted(missing)}")

    county_adjusted = results.loc[results["model_type"].astype(str).eq("county_adjusted")].copy()

    if county_adjusted.empty:
        raise ValueError(f"No county-adjusted results found in {path}")

    if county_adjusted["predictor"].duplicated().any():
        raise ValueError(f"Duplicate county-adjusted predictors in {path}")

    return county_adjusted.reset_index(drop=True)


def identify_predictors(
    tract_data: pd.DataFrame,
    results: pd.DataFrame,
) -> list[str]:
    result_predictors = set(results["predictor"].astype(str))

    predictors = [column for column in tract_data.columns if column in result_predictors]

    if not predictors:
        raise ValueError("No tract-level regression predictors were found.")

    return predictors


def build_map_table(
    tract_data: pd.DataFrame,
    predictors: list[str],
) -> pd.DataFrame:
    map_data = tract_data[
        [
            "tract_geoid",
            "county",
            "represented_population",
            "n_nodes",
            *predictors,
        ]
    ].copy()

    map_data["accessibility_exclude_lts0"] = tract_data["tract_accessibility"].to_numpy()

    return map_data


def detect_geometry_geoid_column(
    geometry: gpd.GeoDataFrame,
) -> str:
    preferred = [
        "GEOID",
        "GEOID20",
        "geoid",
        "geoid20",
        "TRACT_GEOID",
        "tract_geoid",
    ]

    for column in preferred:
        if column in geometry.columns:
            return column

    candidates = [column for column in geometry.columns if "geoid" in column.lower()]

    if len(candidates) == 1:
        return candidates[0]

    raise ValueError(
        f"Could not identify a unique GEOID column in the tract geometry file.\nColumns: {list(geometry.columns)}"
    )


def attach_geometry(
    comparison: pd.DataFrame,
    geometry_path: Path,
) -> gpd.GeoDataFrame:
    require_file(geometry_path)

    geometry = gpd.read_file(geometry_path)

    if geometry.crs is None:
        raise ValueError("The tract geometry file does not define a CRS.")

    geoid_column = detect_geometry_geoid_column(geometry)

    geometry["tract_geoid"] = normalize_geoid(geometry[geoid_column])

    geometry = geometry.loc[
        geometry["tract_geoid"].notna(),
        ["tract_geoid", "geometry"],
    ].copy()

    if geometry["tract_geoid"].duplicated().any():
        raise ValueError("Duplicate tract GEOIDs were found in the geometry file.")

    missing_geometry = sorted(set(comparison["tract_geoid"]) - set(geometry["tract_geoid"]))

    if missing_geometry:
        raise ValueError(f"{len(missing_geometry)} matched tracts have no geometry. Examples: {missing_geometry[:10]}")

    mapped = geometry.merge(
        comparison,
        on="tract_geoid",
        how="inner",
        validate="one_to_one",
    )

    mapped = gpd.GeoDataFrame(
        mapped,
        geometry="geometry",
        crs=geometry.crs,
    )

    if len(mapped) != len(comparison):
        raise ValueError(f"Expected {len(comparison)} mapped tracts but found {len(mapped)}.")

    invalid_count = int((~mapped.geometry.is_valid).sum())

    if invalid_count:
        mapped["geometry"] = mapped.geometry.make_valid()

    if mapped.geometry.isna().any():
        raise ValueError("Missing geometry after tract join.")

    if (~mapped.geometry.is_valid).any():
        raise ValueError("Invalid geometry remains after repair.")

    return mapped.sort_values("tract_geoid").reset_index(drop=True)


def result_row(
    results: pd.DataFrame,
    predictor: str,
) -> pd.Series:
    rows = results.loc[results["predictor"].astype(str).eq(predictor)]

    if len(rows) != 1:
        raise ValueError(f"Expected exactly one county-adjusted result for {predictor}; found {len(rows)}.")

    return rows.iloc[0]


def fit_residuals(
    mapped: gpd.GeoDataFrame,
    outcome: str,
    predictor: str,
    saved_result: pd.Series,
) -> tuple[pd.Series, pd.Series, float]:
    frame = mapped[
        [
            outcome,
            predictor,
            "county",
            "represented_population",
        ]
    ].copy()

    for column in [
        outcome,
        predictor,
        "represented_population",
    ]:
        frame[column] = pd.to_numeric(
            frame[column],
            errors="coerce",
        )

    valid = (
        frame[outcome].between(0, 1)
        & frame[predictor].notna()
        & frame["county"].notna()
        & (frame["represented_population"] > 0)
    )

    frame = frame.loc[valid].copy()

    if frame.empty:
        raise ValueError(f"No valid rows for predictor {predictor}.")

    design = pd.DataFrame(
        {
            "predictor": frame[predictor].astype(float),
        },
        index=frame.index,
    )

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
        design,
        has_constant="add",
    )

    weights = frame["represented_population"] / frame["represented_population"].mean()

    model = sm.WLS(
        frame[outcome].astype(float),
        design.astype(float),
        weights=weights.astype(float),
    ).fit()

    scale = effect_scale(saved_result["effect_unit"])

    refitted_effect = float(model.params["predictor"] * scale)

    saved_effect = float(saved_result["coefficient"])

    if not np.isclose(
        refitted_effect,
        saved_effect,
        rtol=1e-6,
        atol=1e-8,
    ):
        raise ValueError(
            "The refitted model does not reproduce the saved "
            f"coefficient for {predictor}.\n"
            f"Saved: {saved_effect}\n"
            f"Refitted: {refitted_effect}"
        )

    predictions = pd.Series(
        np.nan,
        index=mapped.index,
        dtype=float,
    )

    residuals = pd.Series(
        np.nan,
        index=mapped.index,
        dtype=float,
    )

    predictions.loc[frame.index] = model.predict(design)

    residuals.loc[frame.index] = frame[outcome] - predictions.loc[frame.index]

    weighted_residual_mean = float(
        np.average(
            residuals.loc[frame.index],
            weights=frame["represented_population"],
        )
    )

    return (
        predictions,
        residuals,
        weighted_residual_mean,
    )


def build_regression_summary(
    results: pd.DataFrame,
    predictors: list[str],
) -> OrderedDict:
    summary: OrderedDict[str, dict] = OrderedDict()

    for predictor in predictors:
        result = result_row(
            results,
            predictor,
        )

        summary[predictor] = {
            "label": humanize_predictor(predictor),
            "effect_unit": str(result["effect_unit"]),
            "format": predictor_format(predictor),
            "exclude_lts0": {
                "effect_pp": float(result["coefficient_accessibility_percentage_points"]),
                "ci_low_pp": float(result["ci_95_low_accessibility_percentage_points"]),
                "ci_high_pp": float(result["ci_95_high_accessibility_percentage_points"]),
                "fdr": float(result["fdr_adjusted_p_value"]),
                "r_squared": float(result["r_squared"]),
                "significant": bool(result["statistically_significant_fdr_0_05"]),
            },
        }

    return summary


def add_regression_columns(
    mapped: gpd.GeoDataFrame,
    results: pd.DataFrame,
    predictors: list[str],
) -> tuple[gpd.GeoDataFrame, list[str]]:
    validation_lines: list[str] = []

    for predictor in predictors:
        saved_result = result_row(
            results,
            predictor,
        )

        (
            predictions,
            residuals,
            weighted_residual_mean,
        ) = fit_residuals(
            mapped=mapped,
            outcome="accessibility_exclude_lts0",
            predictor=predictor,
            saved_result=saved_result,
        )

        mapped[f"predicted_exclude_lts0__{predictor}"] = predictions

        mapped[f"residual_exclude_lts0__{predictor}"] = residuals

        validation_lines.append(f"exclude_lts0 {predictor} weighted residual mean: {weighted_residual_mean:.12g}")

    return mapped, validation_lines


def symmetric_limit(
    values: np.ndarray,
) -> float:
    finite = values[np.isfinite(values)]

    if finite.size == 0:
        return 1.0

    limit = float(np.max(np.abs(finite)))

    return max(limit, 1e-9)


def finite_range(
    values: pd.Series,
) -> tuple[float, float]:
    numeric = pd.to_numeric(
        values,
        errors="coerce",
    )

    finite = numeric[np.isfinite(numeric)]

    if finite.empty:
        return 0.0, 1.0

    minimum = float(finite.min())
    maximum = float(finite.max())

    if np.isclose(minimum, maximum):
        maximum = minimum + 1.0

    return minimum, maximum


def build_metric_config(
    mapped: gpd.GeoDataFrame,
    predictors: list[str],
    regression_summary: OrderedDict,
) -> OrderedDict:
    metrics: OrderedDict[str, dict] = OrderedDict()

    metrics["accessibility_exclude_lts0"] = {
        "label": "Relative accessibility excluding LTS 0",
        "group": "Accessibility",
        "palette": "sequential",
        "format": "decimal",
        "min": 0.0,
        "max": 1.0,
        "mid": None,
        "predictor": None,
    }

    for predictor in predictors:
        minimum, maximum = finite_range(mapped[predictor])

        metric_format = regression_summary[predictor]["format"]

        if metric_format == "percent":
            minimum = 0.0
            maximum = max(maximum, 1e-9)

        metrics[predictor] = {
            "label": regression_summary[predictor]["label"],
            "group": "Census demographics",
            "palette": "sequential",
            "format": metric_format,
            "min": minimum,
            "max": maximum,
            "mid": None,
            "predictor": predictor,
        }

    for predictor in predictors:
        excluded_column = f"residual_exclude_lts0__{predictor}"

        residual_limit = symmetric_limit(mapped[excluded_column].to_numpy(dtype=float))

        predictor_label = regression_summary[predictor]["label"]

        metrics[excluded_column] = {
            "label": (f"{predictor_label}: regression residual excluding LTS 0"),
            "group": "Regression residuals",
            "palette": "diverging",
            "format": "decimal",
            "min": -residual_limit,
            "max": residual_limit,
            "mid": 0.0,
            "predictor": predictor,
        }

    return metrics


def save_spatial_outputs(
    mapped: gpd.GeoDataFrame,
    output_root: Path,
) -> tuple[Path, Path]:
    data_directory = output_root / "data"

    data_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    gpkg_path = data_directory / "tract_regression_demographics.gpkg"

    geojson_path = data_directory / "tract_regression_demographics.geojson"

    if gpkg_path.exists():
        gpkg_path.unlink()

    if geojson_path.exists():
        geojson_path.unlink()

    mapped.to_file(
        gpkg_path,
        layer="tract_regression_demographics",
        driver="GPKG",
        index=False,
    )

    mapped.to_crs(epsg=4326).to_file(
        geojson_path,
        driver="GeoJSON",
        index=False,
    )

    return gpkg_path, geojson_path


def create_interactive_html(
    mapped: gpd.GeoDataFrame,
    metrics: OrderedDict,
    regression_summary: OrderedDict,
    output_root: Path,
    title: str,
) -> Path:
    interactive_directory = output_root / "interactive"

    interactive_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    output_path = interactive_directory / "tract_regression_demographics_interactive.html"

    web_data = mapped.to_crs(epsg=4326).copy()

    geojson_text = web_data.to_json(drop_id=True)

    metric_json = json.dumps(
        metrics,
        allow_nan=False,
    )

    regression_json = json.dumps(
        regression_summary,
        allow_nan=False,
    )

    template = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE_HTML__</title>

<link
  rel="stylesheet"
  href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"
/>

<style>
html, body {
    height: 100%;
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    color: #222;
}

#layout {
    display: grid;
    grid-template-columns: 410px 1fr;
    height: 100%;
}

#sidebar {
    box-sizing: border-box;
    overflow-y: auto;
    padding: 18px;
    border-right: 1px solid #cfcfcf;
    background: #ffffff;
}

#map {
    height: 100%;
    width: 100%;
}

h1 {
    margin: 0 0 8px;
    font-size: 20px;
    line-height: 1.25;
}

h2 {
    margin: 20px 0 8px;
    font-size: 16px;
}

p {
    margin: 7px 0;
    line-height: 1.4;
}

.small {
    color: #555;
    font-size: 13px;
}

label {
    display: block;
    margin-bottom: 6px;
    font-weight: 600;
}

select {
    box-sizing: border-box;
    width: 100%;
    padding: 9px;
    border: 1px solid #aaa;
    border-radius: 4px;
    background: white;
}

#legend-gradient {
    height: 16px;
    margin-top: 8px;
    border: 1px solid #777;
}

#legend-labels {
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
    font-size: 12px;
}

.summary-box {
    margin-top: 12px;
    padding: 11px;
    border: 1px solid #cfcfcf;
    border-radius: 5px;
    background: #fafafa;
}

.summary-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
}

.summary-value {
    font-weight: 700;
}

.significant {
    color: #8b0000;
    font-weight: 700;
}

.not-significant {
    color: #555;
}

table {
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
}

th, td {
    padding: 6px;
    border-bottom: 1px solid #ddd;
    text-align: right;
    vertical-align: top;
}

th:first-child,
td:first-child {
    text-align: left;
}

details {
    margin-top: 14px;
}

summary {
    cursor: pointer;
    font-weight: 600;
}

.table-wrapper {
    margin-top: 8px;
    overflow-x: auto;
}

.leaflet-tooltip {
    max-width: 340px;
    white-space: normal;
}

.tooltip-title {
    margin-bottom: 5px;
    font-weight: 700;
}

@media (max-width: 800px) {
    #layout {
        grid-template-columns: 1fr;
        grid-template-rows: 390px 1fr;
    }

    #sidebar {
        border-right: 0;
        border-bottom: 1px solid #cfcfcf;
    }
}
</style>
</head>

<body>
<div id="layout">
    <aside id="sidebar">
        <h1>__TITLE_HTML__</h1>

        <p class="small">
            Results for __TRACT_COUNT__ Census tracts using relative
            bicycle accessibility calculated after excluding LTS 0
            paths.
        </p>

        <h2>Map variable</h2>

        <label for="metric-select">
            Select accessibility, Census demographic, or regression layer
        </label>

        <select id="metric-select"></select>

        <div class="summary-box">
            <div id="legend-title"></div>
            <div id="legend-gradient"></div>
            <div id="legend-labels">
                <span id="legend-min"></span>
                <span id="legend-mid"></span>
                <span id="legend-max"></span>
            </div>
        </div>

        <h2>Regression result</h2>

        <div id="regression-panel" class="summary-box">
            Select a demographic or residual layer to display its
            county-adjusted regression result.
        </div>

        <details>
            <summary>All county-adjusted regression coefficients</summary>

            <p class="small">
                Effects are accessibility percentage-point changes for
                the effect unit shown in the table. FDR values are adjusted
                within each model family.
            </p>

            <div class="table-wrapper">
                <table id="coefficient-table">
                    <thead>
                        <tr>
                            <th>Predictor</th>
                            <th>Unit</th>
                            <th>Coefficient</th>
                            <th>R²</th>
                            <th>FDR</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </details>

        <h2>How to read residuals</h2>

        <p class="small">
            A positive residual means observed tract accessibility is
            higher than predicted by the selected demographic predictor
            and county. A negative residual means observed accessibility
            is lower than predicted.
        </p>
    </aside>

    <main id="map"></main>
</div>

<script
  src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js">
</script>

<script>
const geojsonData = __GEOJSON_JSON__;
const metricConfig = __METRIC_JSON__;
const regressionSummary = __REGRESSION_JSON__;

const sequentialPalette = [
    "#f7fbff",
    "#deebf7",
    "#c6dbef",
    "#9ecae1",
    "#6baed6",
    "#3182bd",
    "#08519c"
];

const divergingPalette = [
    "#67001f",
    "#b2182b",
    "#d6604d",
    "#f7f7f7",
    "#4393c3",
    "#2166ac",
    "#053061"
];

let selectedMetric = "accessibility_exclude_lts0";

function isMissing(value) {
    return value === null
        || value === undefined
        || Number.isNaN(Number(value));
}

function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
}

function colorFor(value, config) {
    if (isMissing(value)) {
        return "#bdbdbd";
    }

    const numeric = Number(value);
    const minimum = Number(config.min);
    const maximum = Number(config.max);

    if (config.palette === "diverging") {
        const midpoint = Number(config.mid);
        let normalized;

        if (numeric <= midpoint) {
            const denominator = midpoint - minimum;
            normalized = denominator === 0
                ? 0.5
                : 0.5 * (numeric - minimum) / denominator;
        } else {
            const denominator = maximum - midpoint;
            normalized = denominator === 0
                ? 0.5
                : 0.5 + 0.5 * (numeric - midpoint) / denominator;
        }

        normalized = clamp(normalized, 0, 1);

        const index = Math.round(
            normalized * (divergingPalette.length - 1)
        );

        return divergingPalette[index];
    }

    const denominator = maximum - minimum;

    const normalized = denominator === 0
        ? 0.5
        : clamp((numeric - minimum) / denominator, 0, 1);

    const index = Math.round(
        normalized * (sequentialPalette.length - 1)
    );

    return sequentialPalette[index];
}

function formatValue(value, config) {
    if (isMissing(value)) {
        return "Missing";
    }

    const numeric = Number(value);

    if (config.format === "percent") {
        return (numeric * 100).toFixed(1) + "%";
    }

    if (config.format === "currency") {
        return new Intl.NumberFormat(
            "en-US",
            {
                style: "currency",
                currency: "USD",
                maximumFractionDigits: 0
            }
        ).format(numeric);
    }

    if (config.format === "number") {
        return numeric.toFixed(1);
    }

    return numeric.toFixed(3);
}

function formatPopulation(value) {
    if (isMissing(value)) {
        return "Missing";
    }

    return Number(value).toLocaleString(
        "en-US",
        {
            maximumFractionDigits: 1
        }
    );
}

function formatPValue(value) {
    const numeric = Number(value);

    if (numeric < 0.001) {
        return numeric.toExponential(2);
    }

    return numeric.toFixed(3);
}

function styleFeature(feature) {
    const config = metricConfig[selectedMetric];

    return {
        fillColor: colorFor(
            feature.properties[selectedMetric],
            config
        ),
        color: "#555555",
        weight: 0.55,
        opacity: 1,
        fillOpacity: 0.80
    };
}


function buildTooltip(properties) {
    const config = metricConfig[selectedMetric];

    return [
        '<div class="tooltip-title">'
            + config.label
            + "</div>",
        "<div><b>Tract:</b> "
            + properties.tract_geoid
            + "</div>",
        "<div><b>County:</b> "
            + properties.county
            + "</div>",
        "<div><b>Represented population:</b> "
            + formatPopulation(
                properties.represented_population
            )
            + "</div>",
        "<hr>",
        "<div><b>Selected value:</b> "
            + formatValue(
                properties[selectedMetric],
                config
            )
            + "</div>",
        "<div><b>Accessibility excluding LTS 0:</b> "
            + Number(
                properties.accessibility_exclude_lts0
            ).toFixed(3)
            + "</div>"
    ].join("");
}


function updateLegend() {
    const config = metricConfig[selectedMetric];

    document.getElementById(
        "legend-title"
    ).textContent = config.label;

    const colors = config.palette === "diverging"
        ? divergingPalette
        : sequentialPalette;

    document.getElementById(
        "legend-gradient"
    ).style.background = (
        "linear-gradient(to right, "
        + colors.join(", ")
        + ")"
    );

    document.getElementById(
        "legend-min"
    ).textContent = formatValue(
        config.min,
        config
    );

    document.getElementById(
        "legend-max"
    ).textContent = formatValue(
        config.max,
        config
    );

    document.getElementById(
        "legend-mid"
    ).textContent = (
        config.palette === "diverging"
        ? formatValue(config.mid, config)
        : ""
    );
}

function regressionBlock(label, result) {
    const significanceClass = result.significant
        ? "significant"
        : "not-significant";

    const significanceText = result.significant
        ? "FDR-significant"
        : "Not FDR-significant";

    return [
        "<div>",
        "<b>" + label + "</b><br>",
        '<span class="summary-value">'
            + result.effect_pp.toFixed(3)
            + " accessibility pp</span><br>",
        "95% CI: "
            + result.ci_low_pp.toFixed(3)
            + " to "
            + result.ci_high_pp.toFixed(3)
            + "<br>",
        "FDR: "
            + formatPValue(result.fdr)
            + "<br>",
        '<span class="' + significanceClass + '">'
            + significanceText
            + "</span>",
        "</div>"
    ].join("");
}


function updateRegressionPanel() {
    const config = metricConfig[selectedMetric];
    const panel = document.getElementById(
        "regression-panel"
    );

    if (
        !config.predictor
        || !regressionSummary[config.predictor]
    ) {
        panel.innerHTML = [
            "<b>Accessibility layer</b>",
            "<p>This layer displays relative accessibility ",
            "after excluding LTS 0 paths. Select a Census ",
            "demographic or regression residual layer to view ",
            "the corresponding county-adjusted coefficient.</p>"
        ].join("");

        return;
    }

    const summary = regressionSummary[
        config.predictor
    ];

    panel.innerHTML = [
        "<b>" + summary.label + "</b>",
        '<p class="small">Effect unit: '
            + summary.effect_unit
            + "</p>",
        regressionBlock(
            "Excluding LTS 0",
            summary.exclude_lts0
        )
    ].join("");
}


function populateMetricSelect() {
    const select = document.getElementById(
        "metric-select"
    );

    const groups = new Map();

    Object.entries(metricConfig).forEach(
        ([key, config]) => {
            if (!groups.has(config.group)) {
                groups.set(config.group, []);
            }

            groups.get(config.group).push(
                [key, config]
            );
        }
    );

    groups.forEach(
        (entries, groupName) => {
            const optgroup = document.createElement(
                "optgroup"
            );

            optgroup.label = groupName;

            entries.forEach(
                ([key, config]) => {
                    const option = document.createElement(
                        "option"
                    );

                    option.value = key;
                    option.textContent = config.label;

                    if (key === selectedMetric) {
                        option.selected = true;
                    }

                    optgroup.appendChild(option);
                }
            );

            select.appendChild(optgroup);
        }
    );
}


function populateCoefficientTable() {
    const body = document.querySelector(
        "#coefficient-table tbody"
    );

    Object.values(regressionSummary).forEach(
        (summary) => {
            const row = document.createElement("tr");

            const excludedClass = (
                summary.exclude_lts0.significant
                ? "significant"
                : "not-significant"
            );

            row.innerHTML = [
                "<td>" + summary.label + "</td>",
                "<td>" + summary.effect_unit + "</td>",
                '<td class="' + excludedClass + '">'
                    + summary.exclude_lts0.effect_pp.toFixed(3)
                    + "</td>",
                "<td>"
                    + summary.exclude_lts0.r_squared.toFixed(3)
                    + "</td>",
                "<td>"
                    + formatPValue(
                        summary.exclude_lts0.fdr
                    )
                    + "</td>"
            ].join("");

            body.appendChild(row);
        }
    );
}


const map = L.map(
    "map",
    {
        zoomControl: true
    }
);

L.tileLayer(
    "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
    {
        maxZoom: 19,
        attribution: "&copy; OpenStreetMap contributors"
    }
).addTo(map);

const geoLayer = L.geoJSON(
    geojsonData,
    {
        style: styleFeature,

        onEachFeature: function(feature, layer) {
            layer.on(
                {
                    mouseover: function(event) {
                        event.target.setStyle(
                            {
                                weight: 2,
                                color: "#111111"
                            }
                        );

                        event.target.bindTooltip(
                            buildTooltip(
                                feature.properties
                            ),
                            {
                                sticky: true,
                                direction: "auto"
                            }
                        ).openTooltip();
                    },

                    mouseout: function(event) {
                        geoLayer.resetStyle(
                            event.target
                        );
                    },

                    click: function(event) {
                        L.popup(
                            {
                                maxWidth: 380
                            }
                        )
                        .setLatLng(event.latlng)
                        .setContent(
                            buildTooltip(
                                feature.properties
                            )
                        )
                        .openOn(map);
                    }
                }
            );
        }
    }
).addTo(map);

map.fitBounds(
    geoLayer.getBounds(),
    {
        padding: [10, 10]
    }
);

L.control.scale().addTo(map);

populateMetricSelect();
populateCoefficientTable();
updateLegend();
updateRegressionPanel();

document.getElementById(
    "metric-select"
).addEventListener(
    "change",
    function(event) {
        selectedMetric = event.target.value;

        geoLayer.setStyle(
            styleFeature
        );

        updateLegend();
        updateRegressionPanel();
    }
);
</script>
</body>
</html>
"""

    rendered = template

    rendered = rendered.replace(
        "__TITLE_HTML__",
        html.escape(title),
    )

    rendered = rendered.replace(
        "__TRACT_COUNT__",
        f"{len(mapped):,}",
    )

    rendered = rendered.replace(
        "__GEOJSON_JSON__",
        geojson_text,
    )

    rendered = rendered.replace(
        "__METRIC_JSON__",
        metric_json,
    )

    rendered = rendered.replace(
        "__REGRESSION_JSON__",
        regression_json,
    )

    output_path.write_text(
        rendered,
        encoding="utf-8",
    )

    return output_path


def write_validation_report(
    args: argparse.Namespace,
    mapped: gpd.GeoDataFrame,
    predictors: list[str],
    metrics: OrderedDict,
    regression_validation: list[str],
    gpkg_path: Path,
    geojson_path: Path,
    html_path: Path,
) -> Path:
    validation_directory = args.output_root / "validation"

    validation_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    validation_path = validation_directory / "tract_regression_demographics_validation.txt"

    lines = [
        "TRACT REGRESSION AND DEMOGRAPHICS MAP VALIDATION",
        "================================================",
        "",
        "INPUTS",
        "------",
        f"LTS-0-excluded tract data: {args.tract_path}",
        f"LTS-0-excluded regression results: {args.results_path}",
        f"Tract geometry: {args.tract_geometry_path}",
        "",
        "DATA VALIDATION",
        "---------------",
        f"Mapped tracts: {len(mapped):,}",
        (f"Unique tract GEOIDs: {mapped['tract_geoid'].nunique():,}"),
        (f"Duplicate tract GEOIDs: {mapped['tract_geoid'].duplicated().sum():,}"),
        (f"Missing geometries: {mapped.geometry.isna().sum():,}"),
        (f"Invalid geometries: {(~mapped.geometry.is_valid).sum():,}"),
        (f"Represented population: {mapped['represented_population'].sum():,.6f}"),
        f"Regression predictors included: {len(predictors):,}",
        f"Interactive map variables included: {len(metrics):,}",
        "",
        "PREDICTORS",
        "----------",
        *predictors,
        "",
        "REGRESSION RESIDUAL VALIDATION",
        "------------------------------",
        *regression_validation,
        "",
        "OUTPUTS",
        "-------",
        f"GeoPackage: {gpkg_path}",
        f"GeoJSON: {geojson_path}",
        f"Interactive HTML: {html_path}",
    ]

    validation_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )

    return validation_path


def main() -> None:
    args = parse_args()

    args.output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Loading LTS-0-excluded tract dataset...")

    tract_data = read_tract_data(args.tract_path)

    results = read_regression_results(args.results_path)

    predictors = identify_predictors(
        tract_data=tract_data,
        results=results,
    )

    print(f"County-adjusted predictors found: {len(predictors):,}")

    map_data = build_map_table(
        tract_data=tract_data,
        predictors=predictors,
    )

    print("Joining Census-tract polygons...")

    mapped = attach_geometry(
        comparison=map_data,
        geometry_path=args.tract_geometry_path,
    )

    print("Fitting LTS-0-excluded regression residuals...")

    mapped, regression_validation = add_regression_columns(
        mapped=mapped,
        results=results,
        predictors=predictors,
    )

    regression_summary = build_regression_summary(
        results=results,
        predictors=predictors,
    )

    metrics = build_metric_config(
        mapped=mapped,
        predictors=predictors,
        regression_summary=regression_summary,
    )

    print(f"Interactive variables created: {len(metrics):,}")

    print("Saving spatial data...")

    gpkg_path, geojson_path = save_spatial_outputs(
        mapped=mapped,
        output_root=args.output_root,
    )

    print("Creating interactive map...")

    html_path = create_interactive_html(
        mapped=mapped,
        metrics=metrics,
        regression_summary=regression_summary,
        output_root=args.output_root,
        title=args.title,
    )

    validation_path = write_validation_report(
        args=args,
        mapped=mapped,
        predictors=predictors,
        metrics=metrics,
        regression_validation=regression_validation,
        gpkg_path=gpkg_path,
        geojson_path=geojson_path,
        html_path=html_path,
    )

    print()
    print("MAP CREATION COMPLETE")
    print("=====================")
    print(f"Mapped tracts: {len(mapped):,}")
    print(f"Predictors: {len(predictors):,}")
    print(f"Map variables: {len(metrics):,}")
    print()
    print("Interactive map:")
    print(html_path)
    print()
    print("Validation report:")
    print(validation_path)


if __name__ == "__main__":
    main()
