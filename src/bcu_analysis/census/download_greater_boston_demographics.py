"""Download and prepare ACS demographic estimates for allocated tracts."""

import argparse
import os
from pathlib import Path

import pandas as pd
import requests


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description=(
            "Download and prepare ACS demographic estimates for Census tracts represented in a node-allocation file."
        )
    )

    parser.add_argument(
        "--allocation-path",
        type=Path,
        required=True,
        help=("CSV containing allocated Census tract GEOIDs and assigned population."),
    )

    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="Directory for raw and cleaned ACS CSV outputs.",
    )

    parser.add_argument(
        "--acs-year",
        type=int,
        default=2024,
        help="ACS five-year dataset year. Default: 2024.",
    )

    return parser.parse_args()


COUNTIES = {
    "017": "Middlesex",
    "021": "Norfolk",
    "025": "Suffolk",
}


AGE_UNDER_18_COLUMNS = [
    "B01001_003E",
    "B01001_004E",
    "B01001_005E",
    "B01001_006E",
    "B01001_027E",
    "B01001_028E",
    "B01001_029E",
    "B01001_030E",
]

AGE_65_PLUS_COLUMNS = [
    "B01001_020E",
    "B01001_021E",
    "B01001_022E",
    "B01001_023E",
    "B01001_024E",
    "B01001_025E",
    "B01001_044E",
    "B01001_045E",
    "B01001_046E",
    "B01001_047E",
    "B01001_048E",
    "B01001_049E",
]

DISABILITY_COLUMNS = [
    "C18108_003E",
    "C18108_004E",
    "C18108_007E",
    "C18108_008E",
    "C18108_011E",
    "C18108_012E",
]

LIMITED_ENGLISH_COLUMNS = [
    "C16002_004E",
    "C16002_007E",
    "C16002_010E",
    "C16002_013E",
]


VARIABLES = [
    # Population and age
    "B01003_001E",
    "B01001_001E",
    *AGE_UNDER_18_COLUMNS,
    *AGE_65_PLUS_COLUMNS,
    # Race and ethnicity
    "B03002_001E",
    "B03002_003E",
    "B03002_004E",
    "B03002_005E",
    "B03002_006E",
    "B03002_007E",
    "B03002_008E",
    "B03002_009E",
    "B03002_012E",
    # Poverty
    "B17001_001E",
    "B17001_002E",
    # Median income and age
    "B19013_001E",
    "B01002_001E",
    # Vehicle availability
    "B08201_001E",
    "B08201_002E",
    # Housing tenure
    "B25003_001E",
    "B25003_003E",
    # Disability
    "C18108_001E",
    *DISABILITY_COLUMNS,
    # Limited-English-speaking households
    "C16002_001E",
    *LIMITED_ENGLISH_COLUMNS,
]


def chunked(values, size):
    """Yield fixed-size chunks from a list."""

    for start in range(0, len(values), size):
        yield values[start : start + size]


def fetch_county_batch(
    acs_url,
    county_code,
    variables,
    api_key,
):
    """Download one variable batch for every tract in a county."""

    parameters = {
        "get": ",".join(["NAME", *variables]),
        "for": "tract:*",
        "in": (f"state:25 county:{county_code}"),
        "key": api_key,
    }

    response = requests.get(
        acs_url,
        params=parameters,
        timeout=120,
    )

    if not response.ok:
        raise RuntimeError(
            f"Census API request failed.\nStatus: {response.status_code}\nResponse: {response.text[:1000]}"
        )

    payload = response.json()

    return pd.DataFrame(
        payload[1:],
        columns=payload[0],
    )


def fetch_county(
    acs_url,
    county_code,
    api_key,
):
    """Download every requested variable for one county."""

    county_data = None

    # Keep requests below the Census API variable limit.
    for batch_number, batch in enumerate(
        chunked(VARIABLES, 40),
        start=1,
    ):
        print(f"  County {county_code}, batch {batch_number}")

        batch_data = fetch_county_batch(
            acs_url=acs_url,
            county_code=county_code,
            variables=batch,
            api_key=api_key,
        )

        if county_data is None:
            county_data = batch_data
        else:
            county_data = county_data.merge(
                batch_data,
                on=[
                    "NAME",
                    "state",
                    "county",
                    "tract",
                ],
                how="outer",
                validate="one_to_one",
            )

    return county_data


def safe_ratio(
    numerator,
    denominator,
):
    """Calculate a ratio only where the denominator is positive."""

    valid_denominator = denominator.where(denominator > 0)

    return numerator / valid_denominator


def main() -> None:
    args = parse_args()

    if args.acs_year < 2009:
        raise ValueError("ACS five-year data are not available before 2009.")

    if not args.allocation_path.is_file():
        raise FileNotFoundError(args.allocation_path)

    args.output_directory.mkdir(
        parents=True,
        exist_ok=True,
    )

    acs_url = f"https://api.census.gov/data/{args.acs_year}/acs/acs5"

    raw_output_path = args.output_directory / (f"greater_boston_{args.acs_year}_acs_demographics_raw.csv")

    clean_output_path = args.output_directory / (f"greater_boston_{args.acs_year}_acs_demographics_by_tract.csv")
    api_key = os.environ.get("CENSUS_API_KEY")

    if not api_key:
        raise RuntimeError("CENSUS_API_KEY is not set.")

    print("Loading tract allocation...")

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

    allocated_geoids = set(allocation["GEOID"].unique())

    print(f"Allocated tracts expected: {len(allocated_geoids):,}")

    county_frames = []

    print("Downloading ACS data...")

    for county_code, county_name in COUNTIES.items():
        print(f"{county_name} County ({county_code})")

        county_data = fetch_county(
            acs_url=acs_url,
            county_code=county_code,
            api_key=api_key,
        )

        county_frames.append(county_data)

    raw = pd.concat(
        county_frames,
        ignore_index=True,
    )

    raw["GEOID"] = raw["state"] + raw["county"] + raw["tract"]

    raw["county_name"] = raw["county"].map(COUNTIES)

    for variable in VARIABLES:
        raw[variable] = pd.to_numeric(
            raw[variable],
            errors="coerce",
        )

        # ACS uses negative special values when an
        # estimate is unavailable or not applicable.
        raw.loc[
            raw[variable] < 0,
            variable,
        ] = pd.NA

    raw.to_csv(
        raw_output_path,
        index=False,
    )

    selected = raw.loc[raw["GEOID"].isin(allocated_geoids)].copy()

    selected_geoids = set(selected["GEOID"])

    missing_geoids = sorted(allocated_geoids - selected_geoids)

    extra_geoids = sorted(selected_geoids - allocated_geoids)

    selected["total_population"] = selected["B01003_001E"]

    selected["age_under_18"] = selected[AGE_UNDER_18_COLUMNS].sum(
        axis=1,
        min_count=1,
    )

    selected["age_65_plus"] = selected[AGE_65_PLUS_COLUMNS].sum(
        axis=1,
        min_count=1,
    )

    selected["age_18_to_64"] = selected["total_population"] - selected["age_under_18"] - selected["age_65_plus"]

    selected["non_hispanic_white"] = selected["B03002_003E"]

    selected["non_hispanic_black"] = selected["B03002_004E"]

    selected["non_hispanic_aian"] = selected["B03002_005E"]

    selected["non_hispanic_asian"] = selected["B03002_006E"]

    selected["non_hispanic_nhpi"] = selected["B03002_007E"]

    selected["non_hispanic_other_race"] = selected["B03002_008E"]

    selected["non_hispanic_multiracial"] = selected["B03002_009E"]

    selected["hispanic_or_latino"] = selected["B03002_012E"]

    selected["poverty_universe"] = selected["B17001_001E"]

    selected["below_poverty"] = selected["B17001_002E"]

    selected["median_household_income"] = selected["B19013_001E"]

    selected["median_age"] = selected["B01002_001E"]

    selected["vehicle_households"] = selected["B08201_001E"]

    selected["zero_vehicle_households"] = selected["B08201_002E"]

    selected["occupied_housing_units"] = selected["B25003_001E"]

    selected["renter_occupied_units"] = selected["B25003_003E"]

    selected["disability_universe"] = selected["C18108_001E"]

    selected["people_with_disability"] = selected[DISABILITY_COLUMNS].sum(
        axis=1,
        min_count=1,
    )

    selected["limited_english_household_universe"] = selected["C16002_001E"]

    selected["limited_english_households"] = selected[LIMITED_ENGLISH_COLUMNS].sum(
        axis=1,
        min_count=1,
    )

    # Tract-level percentage measures.
    selected["share_under_18"] = safe_ratio(
        selected["age_under_18"],
        selected["total_population"],
    )

    selected["share_age_65_plus"] = safe_ratio(
        selected["age_65_plus"],
        selected["total_population"],
    )

    selected["share_non_hispanic_white"] = safe_ratio(
        selected["non_hispanic_white"],
        selected["total_population"],
    )

    selected["share_non_hispanic_black"] = safe_ratio(
        selected["non_hispanic_black"],
        selected["total_population"],
    )

    selected["share_non_hispanic_asian"] = safe_ratio(
        selected["non_hispanic_asian"],
        selected["total_population"],
    )

    selected["share_hispanic_or_latino"] = safe_ratio(
        selected["hispanic_or_latino"],
        selected["total_population"],
    )

    selected["poverty_rate"] = safe_ratio(
        selected["below_poverty"],
        selected["poverty_universe"],
    )

    selected["zero_vehicle_household_rate"] = safe_ratio(
        selected["zero_vehicle_households"],
        selected["vehicle_households"],
    )

    selected["renter_rate"] = safe_ratio(
        selected["renter_occupied_units"],
        selected["occupied_housing_units"],
    )

    selected["disability_rate"] = safe_ratio(
        selected["people_with_disability"],
        selected["disability_universe"],
    )

    selected["limited_english_household_rate"] = safe_ratio(
        selected["limited_english_households"],
        selected["limited_english_household_universe"],
    )

    clean_columns = [
        "GEOID",
        "NAME",
        "county",
        "county_name",
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
        "median_household_income",
        "median_age",
        "share_under_18",
        "share_age_65_plus",
        "share_non_hispanic_white",
        "share_non_hispanic_black",
        "share_non_hispanic_asian",
        "share_hispanic_or_latino",
        "poverty_rate",
        "zero_vehicle_household_rate",
        "renter_rate",
        "disability_rate",
        "limited_english_household_rate",
    ]

    clean = selected[clean_columns].sort_values("GEOID").reset_index(drop=True)

    clean.to_csv(
        clean_output_path,
        index=False,
    )

    race_columns = [
        "non_hispanic_white",
        "non_hispanic_black",
        "non_hispanic_aian",
        "non_hispanic_asian",
        "non_hispanic_nhpi",
        "non_hispanic_other_race",
        "non_hispanic_multiracial",
        "hispanic_or_latino",
    ]

    race_sum = clean[race_columns].sum(
        axis=1,
        min_count=1,
    )

    population_crosscheck = selected["B01003_001E"] - selected["B01001_001E"]

    allocated_population_total = allocation["assigned_population"].sum()

    print()
    print("ACS DEMOGRAPHIC SUMMARY")
    print("=======================")
    print(f"County tracts downloaded: {len(raw):,}")
    print(f"Allocated tracts retained: {len(clean):,}")
    print(f"Missing allocated GEOIDs: {len(missing_geoids):,}")
    print(f"Unexpected retained GEOIDs: {len(extra_geoids):,}")

    print()
    print(
        "ACS population total:",
        f"{clean['total_population'].sum():,.3f}",
    )
    print(
        "Allocation population total:",
        f"{allocated_population_total:,.3f}",
    )
    print(
        "Population difference:",
        f"{clean['total_population'].sum() - allocated_population_total:,.3f}",
    )

    print()
    print(
        "Maximum B01003/B01001 population difference:",
        f"{population_crosscheck.abs().max():,.3f}",
    )
    print(
        "Maximum race/ethnicity sum difference:",
        f"{(race_sum - clean['total_population']).abs().max():,.3f}",
    )

    print()
    print("Missing values")
    print("--------------")

    missing_summary = clean.isna().sum().loc[lambda values: values > 0]

    if missing_summary.empty:
        print("None")
    else:
        print(missing_summary.to_string())

    print()
    print("Selected rate summary")
    print("---------------------")

    rate_columns = [
        "share_under_18",
        "share_age_65_plus",
        "poverty_rate",
        "zero_vehicle_household_rate",
        "renter_rate",
        "disability_rate",
        "limited_english_household_rate",
    ]

    print(clean[rate_columns].describe().T.to_string())

    print()
    print("Saved:")
    print(raw_output_path)
    print(clean_output_path)


if __name__ == "__main__":
    main()
