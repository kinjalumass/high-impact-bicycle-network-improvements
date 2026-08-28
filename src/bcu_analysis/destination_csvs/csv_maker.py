import json
import os
from pathlib import Path
import requests
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point, Polygon
from shapely.ops import unary_union
import time
import argparse

useragent = {'User-Agent': 'bcu-labs'}
queryFolder = 'src/bcu_analysis/destination_csvs/query'
overpass_url = "https://overpass-api.de/api/interpreter"
OVERWRITE = False

# Taken from StressMap Code 
def build_query(region, key, value, type, tags):
    global OVERWRITE
    filepath = Path(queryFolder) / f'{region}{type}Destinations.query'
    filepath.parent.mkdir(exist_ok=True)
    if filepath.exists() and (OVERWRITE is False):
        print(f"{region} query already exists")
    else:
        OVERWRITE = True
        # Modified overpass query (was 'outdated')
        with filepath.open(mode='w') as f:
            f.write('[timeout:180][out:json];\n')
            f.write(f'area["{key}"="{value}"]->.search_area;\n')
            f.write('(\n')
            for tag in tags:
                f.write(f'  nwr[{tag}](area.search_area);\n')
            f.write(');\n')
            f.write('out body geom;\n')
        print(f'{filepath} created')



# Taken from StressMap code + edits
def download_osm(region, type, dataFolder):
    global OVERWRITE
    queryFilepath = os.path.join(queryFolder, f'{region}{type}Destinations.query')
    dataFilepath = os.path.join(dataFolder, f'{region}_{type}_Destinations.json')
    if os.path.exists(dataFilepath) and (OVERWRITE is False):
        print(f'OSM data already downloaded for {region}')
    else:
        OVERWRITE = True
        with open(queryFilepath, 'r') as f:
            overpass_query = f.read()
        print(f'Downloading OSM map data for {region}...')
        # Attempts overpass api up to 10 times 
        max_attempts = 10
        for i in range(max_attempts):
            try: 
                response = requests.get(overpass_url, headers=useragent, params={'data': overpass_query}, timeout=300)
                response.raise_for_status()
                data = response.json()
                print(f'\tDownloaded OSM map data for {region}')
                with open(dataFilepath, 'w') as f:
                    json.dump(data, f)
                print(f'Saved {region} map data')
                break
            except requests.exceptions.HTTPError as err:
                if i==max_attempts-1:
                        print("Maximum number of attempts reached")
                        raise err 
                elif err.response.status_code == 504:
                    print("The Overpass server took too long to respond (504 Gateway Timeout).")
                    print("Attempting Dowload again")
                    print(f"{max_attempts-1-i} attempts left")
                    time.sleep(5)
                    continue
                elif err.response.status_code == 429:
                    print("Too many requests at once")
                    print("Waiting to try again.")
                    time.sleep(10)
                    print("Attempting Download again")
                    print(f"{max_attempts-1-i} attempts left")
                    continue
                else:
                    raise err



def read_raw_file(region, type, dataFolder):
    # Reads the json file and creates the csv file that will contain the coordinate table
    json_filepath = Path(dataFolder) / f'{region}_{type}_Destinations.json'
    
    with open(json_filepath, 'r', encoding='utf-8') as f:
        osm_data = json.load(f)
    
    # Loads all of the raw OSM pieces (nodes, ways, and relations) and stores as 'elements'
    elements = osm_data.get('elements', [])

    return elements



def stores_name_geometry_type(elements, type):
    # Create empty lists to store nodes and ways/relations separately 
    polygons_list = []
    nodes_list = []

    # 1. Map elements precisely by their architectural structure
    for el in elements:
        tags = el.get('tags', {})

        name = tags.get('name', 'unnamed').strip().lower()
        # Determining the 'specific' variable (to indicate what type of destination something is)
        if type == 'Store':
            specific = tags.get('shop', 'NaN')
        elif type == 'TransitStation':
            is_bus_stop = tags.get('highway', 'NaN')
            if is_bus_stop == 'bus_stop':
                specific = is_bus_stop
            else:
                specific = tags.get('station', 'NaN')
                if specific == 'NaN' or specific == 'yes' or specific == '26':
                    amenity = tags.get('amenity', 'NaN')
                    railway = tags.get('railway', 'NaN')
                    building = tags.get('building', 'NaN')
                    if railway == 'station':
                        specific = 'train'
                    elif building == 'train_station':
                        specific = 'train'
                    elif amenity != 'NaN':
                        specific = amenity
                    else:
                        specific = building
        elif type == 'Healthcare':
            specific = tags.get('amenity', 'NaN')
        else:
            specific = type.lower()
        
        # Handle standalone coordinates (extracts the latitude and longitude point for each node and stores it in the 'nodes_list')
        if el.get('type') == 'node':
            lat, lon = el.get('lat'), el.get('lon')
            if lat and lon:
                nodes_list.append({'name': name, 'geometry': Point(lon, lat), 'type': specific})
                
        # Handle standard ways (a line or a simple enclosed shape)
        # extracts all of the points that make up the way, and if the way is a shape/polygon, links the points (in case of overlapping edges or small gaps) and stores in 'polygons_list')
        # lines are not included (lines are typically only used to identify roads, rivers, bridges, etc.)
        elif el.get('type') == 'way' and 'geometry' in el:
            coords = [(pt['lon'], pt['lat']) for pt in el['geometry']]
            if len(coords) >= 3:
                polygons_list.append({'name': name, 'geometry': Polygon(coords).buffer(0), 'type': specific})
                
        # Handle complex relations natively (complex shapes/areas that require multiple different ways to cover the area- ex. unsmooth edges --> multiple ways used to cover the area OR courtyard within a building --> inner and outer ways/boundaries required)
        # iterates through all of the outer ways within the relation and stores them in 'outer_polys' (disregards all inner holes- this is not important for finding locations of places)
        # merges the 'outer_polys' (dissolves overlapping or internal lines) to create 1 big continuous boundary
        # stores the unified polygon in 'polygons_list'
        elif el.get('type') == 'relation' and 'members' in el:
            outer_polys = []
            for member in el['members']:
                if member.get('role') == 'outer' and 'geometry' in member:
                    coords = [(pt['lon'], pt['lat']) for pt in member['geometry']]
                    if len(coords) >= 3:
                        outer_polys.append(Polygon(coords).buffer(0))
            if outer_polys:
                # Merge multi-part relations into one unified spatial asset
                unified_relation_geom = unary_union(outer_polys)
                polygons_list.append({'name': name, 'geometry': unified_relation_geom, 'type': specific})

    return [polygons_list, nodes_list]



def eliminate_overlaps(features, region):
    polygons_list = features[0]
    nodes_list = features[1]

    # 2. Prevent overlapping assets using systematic spatial indices
    # Create list that will contain all of the features (nodes or polygons) that do not overlap with oneanother (to avoid double-counting a location)
    cleaned_features = []
    
    if polygons_list:
        # Converts shapes/polygons and nodes into a digital map dataframe
        gdf_poly = gpd.GeoDataFrame(polygons_list, geometry='geometry', crs="EPSG:4326")
        
        # 1. Project to a meter-based system before running spatial calculations (to measure physical distances/overlapping more accurately)
        gdf_poly = gdf_poly.to_crs("EPSG:3857")
        
        # 2. Snap tiny gaps using meters instead of degrees (1 meter out, 1 meter back)
        # Makes sure all shapes/polygons are closed 
        gdf_poly['geometry'] = gdf_poly.geometry.buffer(1.0).buffer(-1.0)
        
        # Keep the first unique structure if they physically intersect
        # Create a grid index so shape/node look-up is faster
        spatial_index = gdf_poly.sindex
        # Create list of features to exclude/delete
        discard_indices = set()
        
        for idx, row in gdf_poly.iterrows():
            if idx in discard_indices:
                continue
            # Find everything intersecting this feature
            # Uses the index to find other shapes that sit in the bounds of the current shape
            possible_matches_index = spatial_index.intersection(row.geometry.bounds)
            # Extracts data of the shapes that sit in the bounds
            possible_matches = gdf_poly.iloc[possible_matches_index]
            # Determines, based on the data, which shapes ACTUALLY overlap 
            precise_matches = possible_matches[possible_matches.intersects(row.geometry)]
            
            for match_idx in precise_matches.index:
                if match_idx != idx:
                    discard_indices.add(match_idx)
                    
        gdf_poly_clean = gdf_poly.drop(index=list(discard_indices))
        
        # 3. Transform back to EPSG:4326 to align with the rest of the script
        gdf_poly_clean = gdf_poly_clean.to_crs("EPSG:4326")
        cleaned_features.append(gdf_poly_clean)

    # 3. Filter nodes out if they sit inside OR touch polygon boundaries
    if nodes_list and polygons_list:
        # Converts nodes into a digital map dataframe
        gdf_nodes = gpd.GeoDataFrame(nodes_list, geometry='geometry', crs="EPSG:4326")
        # Flattens all of the individual polygons into a single object 
        combined_polys = unary_union([p['geometry'] for p in polygons_list])
        
        # Use intersects to catch points sitting perfectly on boundary edges or inside boundaries
        nodes_outside = gdf_nodes[~gdf_nodes.intersects(combined_polys)]
        if not nodes_outside.empty:
            cleaned_features.append(nodes_outside)
    elif nodes_list:
        # If there happen to be no shapes/polygons, then we keep all nodes
        cleaned_features.append(gpd.GeoDataFrame(nodes_list, geometry='geometry', crs="EPSG:4326"))

    if not cleaned_features:
        print(f"No valid elements found for processing in {region}.")
        return

    # Combine everything back together cleanly
    gdf_locations = pd.concat(cleaned_features, ignore_index=True)

    return gdf_locations



def store_as_csv(gdf_locations, region, type, dataFolder):
    csv_output_path = Path(dataFolder) / f'{region}{type}_Coordinates.csv' 
    
    # 4. Project and extract coordinates accurately
    # Converts list of shapes/nodes to a digital map (in meters)
    gdf_projected = gdf_locations.to_crs("EPSG:3857")
    # Calculates center of every shape (or node) and returns the latitude and longitude of the center point
    centroids_latlon = gdf_projected.geometry.centroid.to_crs("EPSG:4326")
    
    gdf_locations['latitude'] = centroids_latlon.geometry.y
    gdf_locations['longitude'] = centroids_latlon.geometry.x

    df_final_output = pd.DataFrame(gdf_locations.drop(columns=['geometry']))
    df_final_output.to_csv(csv_output_path, index=False, encoding='utf-8')
    
    print(f"Success! Table containing {len(df_final_output)} unique locations saved.")
    print(df_final_output.head())



def remove_logan_airport(csv_path):
    # Load the data from the source file
    df = pd.read_csv(csv_path)
    
    # Define approximate bounding box coordinates for Logan Airport
    lat_min, lat_max = 42.359320, 42.371473
    lon_min, lon_max = -71.026328, -71.013028
    
    # Identify locations located inside the airport boundary
    in_airport = (
        (df['latitude'] >= lat_min) & (df['latitude'] <= lat_max) &
        (df['longitude'] >= lon_min) & (df['longitude'] <= lon_max)
    )
    
    # Keep only the rows outside the airport
    filtered_df = df[~in_airport]
    removed_locations = df[in_airport]['name'].tolist()
    
    # Overwrite the original file
    filtered_df.to_csv(csv_path, index=False)
    print(f"File successfully updated and overwritten: {csv_path}")
    print(f"{len(removed_locations)} locations removed: {removed_locations}")
    print(f"{len(filtered_df)} locations remaining")



def remove_island_locations(csv_path):
    print(f"Reading generated dataset from {csv_path}...")
    df = pd.read_csv(csv_path)
    initial_count = len(df)

    # Island logic bounding box parameters for Boston Harbor
    is_island = (df['longitude'] > -71.017) & (df['latitude'] < 42.357)
    
    removed_locations = df[is_island]['name'].tolist()
    df_cleaned = df[~is_island]
    final_count = len(df_cleaned)

    df_cleaned.to_csv(csv_path, index=False, encoding='utf-8')
    print(f"Removed {len(removed_locations)} island location(s): {removed_locations}")
    print(f"Success! Overwrote {csv_path}. Cleaned rows from {initial_count} down to {final_count}.")



def main(rebuild=False):
    # Argparser
    parser = argparse.ArgumentParser(description="Parameters to determine the type and filtering of destinations and the region being considered.")
    parser.add_argument("dataFolder", type=str, help="The path that all outputs are being stored.")
    # Original dataFolder = '/work/pi_plunkett_umass_edu/bcu/data/processed/osm'
    parser.add_argument("region", type=str, help="The region being considered.(Options: Boston, Brookline, Cambridge, and Somerville)")
    args = parser.parse_args() 
    print("Working Under...")
    print(f"region: {args.region}")
    print(f"data folder: {args.dataFolder}")

    dataFolder = f"{args.dataFolder}/processed/osm"

    global OVERWRITE
    OVERWRITE = rebuild
    Path(args.dataFolder).mkdir(exist_ok=True)
    # Defining region, key, and value
    if args.region == "Boston":
        region = 'Boston'
        key = 'wikipedia'
        value = 'en:Boston'
    elif args.region == "Cambridge":
        region = 'Cambridge'
        key = 'wikipedia'
        value = 'en:Cambridge, Massachusetts'
    elif args.region == "Brookline":
        region = 'Brookline'
        key = 'wikipedia'
        value = 'en:Brookline, Massachusetts'
    elif args.region == "Somerville":
        region = 'Somerville'
        key = 'wikipedia'
        value = 'en:Somerville, Massachusetts'
    else:
        raise ValueError("A key-value pair has not been written for the inputted town.")
    TypesAndTags = {
        'Store' : ['shop=supermarket', 'shop=convenience'], 
        'Greenspace': ['leisure=park'],
        'Healthcare' : ['amenity=pharmacy', 'amenity=hospital', 'amenity=doctors', 'amenity=dentist', 'amenity=clinic'], 
        'TransitStation' : ['public_transport=station', 'highway=bus_stop'], 
        'School' : ['amenity=school']
    }
    # Island filter, Airport filter
    TypesAndFilters = {
        'Store' : [True, True],
        'Greenspace': [True, False],
        'Healthcare' : [True, False], 
        'TransitStation' : [True, False], 
        'School' : [True, False]
    }

    #Run pipeline
    for type, tags in TypesAndTags.items():
        build_query(region, key, value, type, tags)
        download_osm(region, type, dataFolder)
        elements = read_raw_file(region, type, dataFolder)
        features = stores_name_geometry_type(elements, type)
        gdf_locations = eliminate_overlaps(features, region)
        store_as_csv(gdf_locations, region, type, dataFolder)
        if TypesAndFilters.get(type)[1]:
            remove_logan_airport(f"{dataFolder}/{region}{type}_Coordinates.csv")
        if TypesAndFilters.get(type)[0]:
            remove_island_locations(f"{dataFolder}/{region}{type}_Coordinates.csv")

if __name__ == '__main__':
    main(rebuild=True)