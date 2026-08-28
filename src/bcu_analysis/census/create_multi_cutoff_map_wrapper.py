"""Create an HTML wrapper for switching among cutoff-specific maps."""

from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

import pandas as pd

REQUIRED_MANIFEST_COLUMNS = {
    "cutoff_tag",
    "cutoff_miles",
    "tract_data_path",
    "regression_results_path",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a parent HTML visualization that switches among "
            "pre-generated cutoff-specific tract regression maps."
        )
    )

    parser.add_argument(
        "--manifest-path",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--map-root",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--output-path",
        type=Path,
        required=True,
    )

    parser.add_argument(
        "--title",
        default=("Greater Boston Census-Tract Accessibility, Demographics, and Regression Results — Excluding LTS 0"),
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not args.manifest_path.is_file():
        raise FileNotFoundError(args.manifest_path)

    manifest = pd.read_csv(args.manifest_path)

    missing = REQUIRED_MANIFEST_COLUMNS - set(manifest.columns)

    if missing:
        raise ValueError(f"Manifest is missing columns: {sorted(missing)}")

    manifest["cutoff_miles"] = pd.to_numeric(
        manifest["cutoff_miles"],
        errors="raise",
    )

    manifest = manifest.sort_values("cutoff_miles").reset_index(drop=True)

    if manifest["cutoff_miles"].duplicated().any():
        raise ValueError("Manifest contains duplicate cutoff values.")

    if manifest["cutoff_tag"].astype(str).duplicated().any():
        raise ValueError("Manifest contains duplicate cutoff tags.")

    scenarios = []

    wrapper_directory = args.output_path.parent.resolve()

    for row in manifest.itertuples(index=False):
        cutoff_tag = str(row.cutoff_tag)
        cutoff_miles = float(row.cutoff_miles)

        map_path = (
            args.map_root
            / f"cutoff_{cutoff_tag}_miles"
            / "interactive"
            / "tract_regression_demographics_interactive.html"
        ).resolve()

        if not map_path.is_file():
            raise FileNotFoundError(map_path)

        relative_map_path = map_path.relative_to(wrapper_directory.parent)

        scenarios.append(
            {
                "tag": cutoff_tag,
                "miles": cutoff_miles,
                "label": f"{cutoff_miles:g} miles",
                "map_path": f"../{relative_map_path.as_posix()}",
            }
        )

    if not scenarios:
        raise RuntimeError("No cutoff scenarios were found.")

    args.output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    scenario_json = json.dumps(
        scenarios,
        allow_nan=False,
    )

    title_html = html.escape(args.title)

    template = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta
  name="viewport"
  content="width=device-width, initial-scale=1"
>
<title>__TITLE__</title>

<style>
html,
body {
    width: 100%;
    height: 100%;
    margin: 0;
    font-family: Arial, Helvetica, sans-serif;
    color: #222;
    background: #fff;
}

#page {
    display: grid;
    grid-template-rows: auto 1fr;
    width: 100%;
    height: 100%;
}

#toolbar {
    display: flex;
    align-items: center;
    gap: 14px;
    box-sizing: border-box;
    padding: 11px 16px;
    border-bottom: 1px solid #cfcfcf;
    background: #fff;
}

#title {
    flex: 1;
    min-width: 260px;
    font-size: 17px;
    font-weight: 700;
    line-height: 1.25;
}

#cutoff-control {
    display: flex;
    align-items: center;
    gap: 8px;
}

label {
    font-size: 14px;
    font-weight: 700;
    white-space: nowrap;
}

select {
    min-width: 130px;
    padding: 8px 10px;
    border: 1px solid #999;
    border-radius: 4px;
    background: #fff;
    font-size: 14px;
}

#map-frame {
    display: block;
    width: 100%;
    height: 100%;
    border: 0;
}

@media (max-width: 760px) {
    #toolbar {
        align-items: stretch;
        flex-direction: column;
        gap: 8px;
    }

    #cutoff-control {
        width: 100%;
    }

    select {
        flex: 1;
    }
}
</style>
</head>

<body>
<div id="page">
    <header id="toolbar">
        <div id="title">__TITLE__</div>

        <div id="cutoff-control">
            <label for="cutoff-select">
                Distance limit
            </label>

            <select id="cutoff-select"></select>
        </div>
    </header>

    <iframe
      id="map-frame"
      title="Cutoff-specific tract regression map"
    ></iframe>
</div>

<script>
const scenarios = __SCENARIOS__;

const cutoffSelect = document.getElementById(
    "cutoff-select"
);

const mapFrame = document.getElementById(
    "map-frame"
);

function setScenario(tag) {
    const scenario = scenarios.find(
        (candidate) => candidate.tag === tag
    );

    if (!scenario) {
        throw new Error(
            "Unknown cutoff scenario: " + tag
        );
    }

    mapFrame.src = scenario.map_path;

    const url = new URL(window.location.href);
    url.searchParams.set("cutoff", scenario.tag);

    window.history.replaceState(
        {},
        "",
        url
    );
}

scenarios.forEach(
    (scenario) => {
        const option = document.createElement(
            "option"
        );

        option.value = scenario.tag;
        option.textContent = scenario.label;

        cutoffSelect.appendChild(option);
    }
);

const requestedTag = new URL(
    window.location.href
).searchParams.get("cutoff");

const initialScenario = scenarios.find(
    (scenario) => scenario.tag === requestedTag
) || scenarios[0];

cutoffSelect.value = initialScenario.tag;
setScenario(initialScenario.tag);

cutoffSelect.addEventListener(
    "change",
    (event) => {
        setScenario(event.target.value);
    }
);
</script>
</body>
</html>
"""

    rendered = template.replace(
        "__TITLE__",
        title_html,
    )

    rendered = rendered.replace(
        "__SCENARIOS__",
        scenario_json,
    )

    args.output_path.write_text(
        rendered,
        encoding="utf-8",
    )

    print(f"Cutoff scenarios: {len(scenarios)}")

    for scenario in scenarios:
        print(f"  {scenario['label']}: {scenario['map_path']}")

    print(f"Saved: {args.output_path}")


if __name__ == "__main__":
    main()
