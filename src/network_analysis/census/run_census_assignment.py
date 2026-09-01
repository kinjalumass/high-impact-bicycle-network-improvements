"""Assign Census tract population to graph nodes for a selected region."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import geopandas as gpd
import osmnx as ox
import pandas as pd

from network_analysis.census.assignment import assign_population_to_nodes_by_tract_area

REGIONS = {
    "boston": ("Boston, Massachusetts, USA",),
    "brookline": ("Brookline, Massachusetts, USA",),
    "cambridge": ("Cambridge, Massachusetts, USA",),
    "somerville": ("Somerville, Massachusetts, USA",),
    "greater-boston": (
        "Boston, Massachusetts, USA",
        "Brookline, Massachusetts, USA",
        "Cambridge, Massachusetts, USA",
        "Somerville, Massachusetts, USA",
    ),
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Assign Census population to graph nodes for one city or the "
            "combined Boston, Brookline, Cambridge, and Somerville study area."
        )
    )
    parser.add_argument("--region", required=True, choices=sorted(REGIONS))
    parser.add_argument(
        "--graph-path",
        type=Path,
        required=True,
        help="GraphML file whose nodes will receive Census population.",
    )
    parser.add_argument(
        "--tract-path",
        type=Path,
        required=True,
        help="GeoJSON containing Census tract geometry and population.",
    )
    parser.add_argument(
        "--output-directory",
        type=Path,
        required=True,
        help="Directory where generated assignment outputs will be written.",
    )
    parser.add_argument(
        "--output-prefix",
        help=(
            "Prefix for generated files. If omitted, the selected region is "
            "used without assuming that the graph is pruned."
        ),
    )
    parser.add_argument("--candidate-buffer-m", type=float, default=100.0)
    parser.add_argument("--min-region-overlap-share", type=float, default=0.50)
    return parser.parse_args(argv)


def load_boundary(region: str) -> gpd.GeoDataFrame:
    boundaries = []

    for place in REGIONS[region]:
        print(f"Loading boundary: {place}")
        boundary = ox.geocode_to_gdf(place)

        if boundary.empty:
            raise RuntimeError(f"No municipal boundary returned for {place}")

        boundaries.append(boundary[["geometry"]].copy())

    combined = gpd.GeoDataFrame(
        pd.concat(boundaries, ignore_index=True),
        crs=boundaries[0].crs,
    )

    return gpd.GeoDataFrame(
        {"region": [region], "geometry": [combined.geometry.union_all()]},
        crs=combined.crs,
    )


def output_paths(
    directory: Path,
    region: str,
    output_prefix: str | None = None,
) -> dict[str, Path]:
    region_slug = region.replace("-", "_")
    prefix = (output_prefix or region_slug).replace("-", "_")
    boundary_name = (
        "greater_boston_four_city_boundary.geojson"
        if region == "greater-boston"
        else f"{region_slug}_boundary.geojson"
    )

    return {
        "allocation_csv": directory / f"{prefix}_node_tract_allocation.csv",
        "allocation_parquet": directory / f"{prefix}_node_tract_allocation.parquet",
        "nodes_gpkg": directory / f"{prefix}_nodes_with_population.gpkg",
        "nodes_parquet": directory / f"{prefix}_nodes_with_population.parquet",
        "nodes_web": directory / f"{prefix}_nodes_with_population_web.geojson",
        "boundary": directory / boundary_name,
    }


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)

    if not args.graph_path.exists():
        raise FileNotFoundError(f"Graph file not found: {args.graph_path}")
    if not args.tract_path.exists():
        raise FileNotFoundError(f"Tract file not found: {args.tract_path}")
    if args.candidate_buffer_m < 0:
        raise ValueError("--candidate-buffer-m must be non-negative")
    if not 0 <= args.min_region_overlap_share <= 1:
        raise ValueError("--min-region-overlap-share must be between 0 and 1")

    args.output_directory.mkdir(parents=True, exist_ok=True)
    paths = output_paths(
        args.output_directory,
        args.region,
        args.output_prefix,
    )

    print(f"Selected region: {args.region}")
    print(f"Graph: {args.graph_path}")
    print(f"Tracts: {args.tract_path}")
    print(f"Output prefix: {(args.output_prefix or args.region).replace('-', '_')}")

    graph = ox.load_graphml(args.graph_path)
    nodes, _ = ox.graph_to_gdfs(graph)
    tracts = gpd.read_file(args.tract_path)

    missing = {"GEOID", "population"} - set(tracts.columns)
    if missing:
        raise ValueError(
            "Tract file is missing required columns: " + ", ".join(sorted(missing))
        )

    tracts["GEOID"] = (
        tracts["GEOID"]
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.zfill(11)
    )
    tracts["population"] = pd.to_numeric(tracts["population"], errors="coerce")

    boundary = load_boundary(args.region)
    boundary.to_file(paths["boundary"], driver="GeoJSON")

    nodes_with_population, allocation = assign_population_to_nodes_by_tract_area(
        nodes_gdf=nodes,
        tracts_gdf=tracts,
        population_col="population",
        tract_id_col="GEOID",
        projected_crs="EPSG:26986",
        candidate_buffer_m=args.candidate_buffer_m,
        tract_filter_method="none",
        region_boundary_gdf=boundary,
        min_region_overlap_share=args.min_region_overlap_share,
        verbose=True,
    )

    if allocation.empty:
        raise RuntimeError("No population-allocation rows were produced")

    allocation["node_id"] = allocation["node_id"].astype(str)
    allocation["GEOID"] = allocation["GEOID"].astype(str).str.zfill(11)
    nodes_with_population["node_id"] = nodes_with_population["node_id"].astype(str)

    allocation.to_csv(paths["allocation_csv"], index=False)
    allocation.to_parquet(paths["allocation_parquet"], index=False)
    nodes_with_population.to_file(paths["nodes_gpkg"], driver="GPKG")
    nodes_with_population.to_parquet(paths["nodes_parquet"])
    nodes_with_population.to_crs("EPSG:4326").to_file(
        paths["nodes_web"],
        driver="GeoJSON",
    )

    share_sums = allocation.groupby("GEOID")["area_share"].sum()
    print()
    print("ALLOCATION SUMMARY")
    print("==================")
    print(f"Region: {args.region}")
    print(f"Graph nodes: {graph.number_of_nodes():,}")
    print(f"Allocated nodes: {allocation['node_id'].nunique():,}")
    print(f"Assigned tracts: {allocation['GEOID'].nunique():,}")
    print(
        "Assigned population: "
        f"{allocation['assigned_population'].sum():,.3f}"
    )
    print(
        "Tracts not summing near 1: "
        f"{(~share_sums.between(0.999999, 1.000001)).sum():,}"
    )
    print("Saved outputs:")
    for path in paths.values():
        print(path)


if __name__ == "__main__":
    main()
