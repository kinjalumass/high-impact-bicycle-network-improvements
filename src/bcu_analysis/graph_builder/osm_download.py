import json
import os
from pathlib import Path
import requests
import pandas as pd
import osmnx as ox

useragent = {"User-Agent": "bicycle-network-analysis"}

overpass_url = "https://overpass.kumi.systems/api/interpreter"

# Overpass queries are versioned alongside the code, not with the data.
QUERY_DIR = Path(__file__).resolve().parent / 'query'


def query_path(region_name):
    return QUERY_DIR / (region_name + ".query")


def build_tag_query(region_name, cities):
    query_filepath = query_path(region_name)
    query_filepath.parent.mkdir(parents=True, exist_ok=True)
    # Union the area for every city into a single search_area set.
    area_lines = ''.join(
        f'    area["{key}"="{value}"];\n' for _, key, value in cities
    )
    with query_filepath.open(mode='w') as f:
        f.write('[timeout:1800][out:json];\n')
        f.write('(\n')
        f.write(area_lines)
        f.write(')->.search_area;\n')
        f.write('.search_area out body;\n')
        f.write("""
(
    way[highway][footway!=sidewalk][service!=parking_aisle](area.search_area);
    way[footway=sidewalk][bicycle][bicycle!=no][bicycle!=dismount](area.search_area);
);
out qt tags;
            """)
        print(f"{query_filepath} created")


def download_tags(region_name, data_dir):
    """

    https://towardsdatascience.com/loading-data-from-openstreetmap-with-python-and-the-overpass-api-513882a27fd0
    """
    query_filepath = query_path(region_name)
    tags_filepath = os.path.join(data_dir, f'raw/osm/{region_name}_tags.json')
    os.makedirs(os.path.dirname(tags_filepath), exist_ok=True)

    if os.path.exists(tags_filepath):
        print(f"OSM data already downloaded for {region_name}")
    else:
        with open(query_filepath, "r") as f:
            lines = f.readlines()
        overpass_query = "".join(lines)  # .replace('\n','').replace('  ','')

        print(f"Downloaing OSM map data for {region_name}...")
        response = requests.get(overpass_url, headers=useragent, params={"data": overpass_query}, timeout=60 * 5)
        response.raise_for_status()  # Raise error if status code not 200
        data = response.json()

        print(f"\tDownloaded OSM map data for {region_name}")

        with open(tags_filepath, "w") as f:
            json.dump(data, f)
            print(f"Saved {region_name} OSM tag data")


def extract_tags(region_name, data_dir):
    """
    Extract OSM tags to use in download
    """
    # load the data
    way_tags_csv_path = os.path.join(data_dir, f'raw/osm/{region_name}_way_tags.csv')
    os.makedirs(os.path.dirname(way_tags_csv_path), exist_ok=True)
    print(f'Finding way tags for {region_name}...')
    with open(os.path.join(data_dir, f'raw/osm/{region_name}_tags.json'), 'r') as f:
        data = json.load(f)

    # make a dataframe of tags
    dfs = []

    for element in data["elements"]:
        if element["type"] != "way":
            continue
        df = pd.DataFrame.from_dict(element["tags"], orient="index")
        dfs.append(df)

    tags_df = pd.concat(dfs).reset_index()
    tags_df.columns = ["tag", "tagvalue"]

    # count all the unique tag and value combinations
    # tag_value_counts = tags_df.value_counts().reset_index()
    # count all the unique tags
    tag_counts = tags_df["tag"].value_counts().reset_index()

    # explore the tags that start with 'cycleway'
    print(f"Cycleway tags:\n{tag_counts[tag_counts['tag'].str.contains('cycleway')]}")

    way_tags_series = tag_counts["tag"]  # all unique tags from the OSM download
    way_tags_series.to_csv(way_tags_csv_path)
    print(f"\t{way_tags_csv_path} saved.")

    way_tags = list(way_tags_series)

    # add the above list to the global osmnx settings
    ox.settings.useful_tags_way += way_tags
    ox.settings.osm_xml_way_tags = way_tags
    print("Way tags added to osmnx settings.")


def download_graph(region_name, places, data_dir):
    '''
    Download data for a given region.

    `places` is a list of place names (e.g. ["Boston, Massachusetts", ...]);
    graph_from_place merges them all into a single graph saved under `region`.
    '''
    # create a filter to download selected data
    # this filter is based on osmfilter = ox.downloader._get_osm_filter("bike")
    # keeping the footway and construction tags
    osmfilter = (
        '["highway"]["area"!~"yes"]["access"!~"private"]'
        '["highway"!~"abandoned|bus_guideway|corridor|elevator|escalator|motor|'
        'planned|platform|proposed|raceway|steps"]'
        '["service"!~"private"]'
        '["indoor"!~"yes"]'
        '["service"!="parking_aisle"]'
    )

    graph_filepath = f"{data_dir}/raw/osm/{region_name}_raw.graphml"
    print(f"Downloading {region_name} data (this may take some time)...")
    G = ox.graph_from_place(
        places,
        retain_all=True,
        truncate_by_edge=True,
        simplify=False,
        custom_filter=osmfilter,
    )
    print(f"Saving {region_name} graph")
    ox.save_graphml(G, graph_filepath)

        # plot downloaded graph - this is slow for a large area
        # fig, ax = ox.plot_graph(G, node_size=0, edge_color="w", edge_linewidth=0.2)
        # ox.plot_graph(G, node_size=0, edge_color="w", edge_linewidth=0.2)

    # convert graph to node and edge GeoPandas GeoDataFrames
    gdf_nodes, gdf_edges = ox.graph_to_gdfs(G)

    print(f"{gdf_edges.shape=}")
    print(f"{gdf_nodes.shape=}")

    return gdf_nodes, gdf_edges
