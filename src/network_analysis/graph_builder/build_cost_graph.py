import argparse

from network_analysis.graph_builder import osm_download
from network_analysis.graph_builder import assign_cost

CITIES = {
    'boston': ('Boston, Massachusetts', 'wikipedia', 'en:Boston'),
    'cambridge': ('Cambridge, Massachusetts', 'wikipedia', 'en:Cambridge, Massachusetts'),
    'somerville': ('Somerville, Massachusetts', 'wikipedia', 'en:Somerville, Massachusetts'),
    'brookline': ('Brookline, Massachusetts', 'wikipedia', 'en:Brookline, Massachusetts'),
}

CITY_OPTIONS = list(CITIES) + ["greater_boston"]


def resolve_area(area):
    if area == "greater_boston":
        return "greater_boston", list(CITIES.values())
    return f'{area}_only', [CITIES[area]]


def main(area, cost_scenario, data_dir):
    region_name, cities = resolve_area(area)
    places = [name for name, _, _ in cities]
    print(f"Building {region_name} graph from {len(places)} place(s): {', '.join(places)}")
    print(f"Data directory: {data_dir}")
    osm_download.build_tag_query(region_name, cities)
    osm_download.download_tags(region_name, data_dir)
    osm_download.extract_tags(region_name, data_dir)
    gdf_nodes, gdf_edges = osm_download.download_graph(region_name, places, data_dir)
    assign_cost.lts_edges(region_name, gdf_edges, data_dir)
    assign_cost.build_cost_graph(region_name, cost_scenario, data_dir)
    return assign_cost.simplify_cost_graph(region_name, cost_scenario, data_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download OSM data for an area and build its LTS cost graph.",
    )
    parser.add_argument(
        "cost_scenario",
        type=int,
        help="Cost scenario id from config/cost_parameters.csv",
    )
    parser.add_argument(
        "area",
        choices=CITY_OPTIONS,
        help="Municipality to build, or 'greater_boston' for all of them combined.",
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Root data directory",
    )
    args = parser.parse_args()
    main(area=args.area, cost_scenario=args.cost_scenario, data_dir=args.data_dir)
