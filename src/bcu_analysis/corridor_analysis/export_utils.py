import pydeck as pdk
import geopandas as gpd
import networkx as nx
from shapely import wkt
from shapely.geometry import LineString
from pathlib import Path

COLORS = [
    [216, 112, 147, 240], [20, 184, 166, 240], [139, 92, 246, 240], [16, 185, 129, 240],
    [217, 119, 6, 240], [6, 182, 212, 240], [244, 63, 94, 240], [37, 99, 235, 240],
    [132, 204, 22, 240], [249, 115, 22, 240], [99, 102, 241, 240], [168, 85, 247, 240],
    [234, 179, 8, 240], [236, 72, 153, 240]
]

def build_pydeck_map(G, node_to_island, proposed_corridors, missing_edges, show_missing_links=True):
    background_paths, island_paths, missing_paths = [], [], []

    for u, v, k, data in G.edges(data=True, keys=True):
        geom_wkt = data.get('geometry', None)
        if geom_wkt:
            geom = wkt.loads(geom_wkt) if isinstance(geom_wkt, str) else geom_wkt
            coords = list(geom.coords)
        else:
            try:
                coords = [[float(G.nodes[u]['x']), float(G.nodes[u]['y'])],
                          [float(G.nodes[v]['x']), float(G.nodes[v]['y'])]]
            except KeyError:
                continue
        
        lts = str(data.get('LTS', data.get('lts', '3'))).strip()
        is_safe = lts in ['1', '2', '1.0', '2.0']
        in_island = is_safe and u in node_to_island and v in node_to_island and node_to_island[u] == node_to_island[v]

        is_missing_link = False
        is_top_priority = False
        priority_rank = 0
        
        if show_missing_links:
            for rank, corridor in enumerate(proposed_corridors):
                if (u, v) in corridor["edges"] or (v, u) in corridor["edges"]:
                    is_missing_link = True
                    if rank < 3:  
                        is_top_priority = True
                        priority_rank = rank + 1
                    break

        if is_missing_link:
            if is_top_priority:
                missing_paths.append({"path": coords, "color": [255, 255, 0, 255], "width": 8.0, "name": f'Top Priority #{priority_rank}', "lts": "High ROI Bridge"})
            else:
                missing_paths.append({"path": coords, "color": [225, 29, 72, 255], "width": 5.0, "name": "Proposed Bridge Corridor", "lts": "Proposed Bridge"})
        elif in_island:
            island_id = node_to_island[u]
            color = COLORS[island_id % len(COLORS)]
            island_paths.append({"path": coords, "color": color, "width": 3.0, "name": f'Safe Network (Zone {island_id+1})', "lts": lts})
        else:
            background_paths.append({"path": coords, "color": [150, 150, 150, 200], "width": 2.0, "name": "High-Stress", "lts": lts})

    layers = [
        pdk.Layer("PathLayer", data=background_paths, get_path="path", get_color="color", get_width="width", width_scale=1, width_min_pixels=1.5, pickable=True),
        pdk.Layer("PathLayer", data=island_paths, get_path="path", get_color="color", get_width="width", width_scale=1, width_min_pixels=2, pickable=True),
        pdk.Layer("PathLayer", data=missing_paths, get_path="path", get_color="color", get_width="width", width_scale=1, width_min_pixels=4, pickable=True)
    ]

    view_state = pdk.ViewState(latitude=42.3601, longitude=-71.0589, zoom=13.5, pitch=25, bearing=0)
    return pdk.Deck(layers=layers, initial_view_state=view_state, map_style="road", tooltip={"html": "<b>{name}</b><br/>LTS: {lts}"})

def export_to_html(deck, output_path):
    deck.to_html(str(output_path))
    print(f"Interactive HTML map saved to {output_path}")

def export_to_gis(G, proposed_corridors, output_path, format="geopackage"):
    records = []
    for rank, corridor in enumerate(proposed_corridors):
        for u, v in corridor["edges"]:
            if G.has_edge(u, v):
                data = G.get_edge_data(u, v)[0]
                geom_wkt = data.get('geometry', None)
                if geom_wkt:
                    geom = wkt.loads(geom_wkt) if isinstance(geom_wkt, str) else geom_wkt
                else:
                    geom = LineString([(float(G.nodes[u]['x']), float(G.nodes[u]['y'])), 
                                       (float(G.nodes[v]['x']), float(G.nodes[v]['y']))])
                
                records.append({
                    "u": u, "v": v, "corridor_rank": rank + 1, "score": corridor["score"],
                    "name": data.get("name", "Unknown"), "geometry": geom
                })
    
    if not records:
        print("No corridors to export.")
        return

    gdf = gpd.GeoDataFrame(records, geometry="geometry", crs="EPSG:4326")
    
    # Updated to support GeoPackage!
    if format.lower() == "geopackage":
        gdf.to_file(output_path, driver="GPKG")
    elif format.lower() == "geojson":
        gdf.to_file(output_path, driver="GeoJSON")
        
    print(f"GIS data exported to {output_path} as {format}")

def export_to_graphml(G, missing_edges, output_path):
    G_export = G.copy()
    for u, v, k, data in G_export.edges(data=True, keys=True):
        if (u, v) in missing_edges or (v, u) in missing_edges:
            data['is_proposed_corridor'] = 'True'
        else:
            data['is_proposed_corridor'] = 'False'
    nx.write_graphml(G_export, output_path)
    print(f"Updated GraphML saved to {output_path}")
