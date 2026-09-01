import argparse
from pathlib import Path
from network_analysis.corridor_analysis import core_algorithms as core
from network_analysis.corridor_analysis import export_utils as export

CITIES = {
    'boston': 'Boston, Massachusetts',
    'cambridge': 'Cambridge, Massachusetts',
    'somerville': 'Somerville, Massachusetts',
    'brookline': 'Brookline, Massachusetts',
}
CITY_OPTIONS = list(CITIES) + ["greater_boston"]

def resolve_area(area):
    if area == "greater_boston":
        return "greater_boston"
    return f'{area}'

def main(area, graph_dir, poi_dir, output_dir, min_island_size, link_complexity, demand_scenario, cost_scenario):
    region_name = resolve_area(area)
    
    # GraphML file path mapping
    graph_path = Path(graph_dir) / f"{region_name}_cost_with_pathCount_DS{demand_scenario}_CS{cost_scenario}.graphml"
    
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"Starting Corridor Analysis for {region_name}...")
    print(f"Loading graph from: {graph_path}")
    
    # 1. Process Network Graph
    G = core.load_graph(graph_path)
    G_safe, top_islands, node_to_island = core.process_islands(G, min_island_size, max_islands=15)
    proposed_corridors, missing_edges = core.compute_missing_links(G, top_islands, link_complexity)
    base_size, new_size, roi = core.calculate_roi(G_safe, G, missing_edges)
    
    # Optional POI loading
    poi_data = core.load_poi_data(poi_dir, area=region_name)
    print(f"Loaded POI categories: {list(poi_data.keys())}")
    
    print("\n--- ROI METRICS ---")
    print(f"Baseline Safe Network Nodes: {base_size}")
    print(f"Upgraded Safe Network Nodes: {new_size}")
    print(f"Network Expansion: +{roi:.1f}%\n")
    
    # 2. Exports
    deck = export.build_pydeck_map(G, node_to_island, proposed_corridors, missing_edges)
    
    html_out = out_dir / f"{region_name}_corridors.html"
    gpkg_out = out_dir / f"{region_name}_corridors.gpkg"  
    graphml_out = out_dir / f"{region_name}_updated.graphml"
    
    export.export_to_html(deck, html_out)
    export.export_to_gis(G, proposed_corridors, gpkg_out, format="geopackage") 
    export.export_to_graphml(G, missing_edges, graphml_out)
    
    print(f"Corridor pipeline execution complete. Deliverables saved to: {out_dir}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run continuous corridor bridging analysis on an LTS graph.")
    parser.add_argument("area", choices=CITY_OPTIONS, help="Municipality to process (e.g., 'boston'), or 'greater_boston'.")
    parser.add_argument("--graph-dir", default="./data/processed/road_usage_analysis", help="Directory containing GraphML files.")
    parser.add_argument("--poi-dir", default="./data/processed/osm", help="Directory containing POI CSVs.")
    parser.add_argument("--output-dir", default="./final", help="Directory to save final exports.")
    parser.add_argument("--min-island-size", type=int, default=20, help="Minimum edges required for an island.")
    parser.add_argument("--link-complexity", type=int, default=10, help="Bridging depth.")
    parser.add_argument("--demand-scenario", type=int, default=1, help="Demand Scenario (DS) ID.")
    parser.add_argument("--cost-scenario", type=int, default=1, help="Cost Scenario (CS) ID.")
    
    args = parser.parse_args()
    main(
        area=args.area, 
        graph_dir=args.graph_dir,
        poi_dir=args.poi_dir,
        output_dir=args.output_dir, 
        min_island_size=args.min_island_size, 
        link_complexity=args.link_complexity,
        demand_scenario=args.demand_scenario, 
        cost_scenario=args.cost_scenario
    )
