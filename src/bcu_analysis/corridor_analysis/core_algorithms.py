import networkx as nx
import pandas as pd
from pathlib import Path

def load_graph(graph_path):
    path = Path(graph_path)
    if not path.exists():
        raise FileNotFoundError(f"GraphML not found at {path}")
    return nx.read_graphml(path)

def load_poi_data(poi_dir, area="boston"):
    """
    Loads POI CSVs from /work/pi_plunkett_umass_edu/bcu/data/processed/osm.
    Combines all 4 municipalities if area is 'greater_boston'.
    """
    categories = ["Greenspaces", "Healthcare", "Office", "TransitStation"]
    
    if area == "greater_boston":
        cities = ["Boston", "Brookline", "Cambridge", "Somerville"]
    else:
        # Capitalize area name (e.g., 'boston' -> 'Boston')
        cities = [area.capitalize()]
        
    dfs = {cat: [] for cat in categories}
    
    for city in cities:
        for cat in categories:
            file_path = Path(poi_dir) / f"{city}{cat}.csv"
            if file_path.exists():
                df = pd.read_csv(file_path)
                df["city"] = city
                dfs[cat].append(df)
                
    # Concatenate dataframes for each category
    combined_dfs = {}
    for cat, list_of_dfs in dfs.items():
        if list_of_dfs:
            combined_dfs[cat] = pd.concat(list_of_dfs, ignore_index=True)
            
    return combined_dfs

def process_islands(G, min_island_size, max_islands):
    safe_edges = []
    for u, v, k, data in G.edges(data=True, keys=True):
        lts = str(data.get('LTS', data.get('lts', '3'))).strip()
        if lts in ['1', '2', '1.0', '2.0']:
            safe_edges.append((u, v, k))

    G_safe = G.edge_subgraph(safe_edges).copy()
    small_comps = [c for c in nx.connected_components(nx.Graph(G_safe)) if len(c) < min_island_size]
    for comp in small_comps:
        G_safe.remove_nodes_from(comp)

    components = sorted(nx.connected_components(nx.Graph(G_safe)), key=len, reverse=True)
    top_islands = components[:max_islands]

    node_to_island = {}
    for island_id, nodes in enumerate(top_islands):
        for node in nodes:
            node_to_island[node] = island_id

    return G_safe, top_islands, node_to_island

def compute_missing_links(G, top_islands, link_complexity):
    proposed_corridors = []
    missing_edges = set()
    
    if len(top_islands) < 2:
        return proposed_corridors, missing_edges

    G_undirected = G.to_undirected()
    num_links_to_calculate = min(link_complexity, len(top_islands) - 1)
    
    for i in range(num_links_to_calculate):
        island_a = top_islands[i]
        island_b = top_islands[i+1]
        
        d_src, d_tgt = f"SRC_{i}", f"TGT_{i}"
        G_undirected.add_node(d_src)
        G_undirected.add_node(d_tgt)
        
        for n in island_a: G_undirected.add_edge(d_src, n)
        for n in island_b: G_undirected.add_edge(n, d_tgt)
            
        try:
            path = nx.shortest_path(G_undirected, d_src, d_tgt)
            actual_path = path[1:-1]
            
            corridor_score = 0
            corridor_edge_list = []
            
            for j in range(len(actual_path) - 1):
                node_u, node_v = actual_path[j], actual_path[j+1]
                
                if G_undirected.is_multigraph():
                    benefit = max([float(d.get('potential_Dbenefit', 0)) for d in G_undirected[node_u][node_v].values()])
                else:
                    benefit = float(G_undirected[node_u][node_v].get('potential_Dbenefit', 0))
                    
                corridor_score += benefit
                corridor_edge_list.append((node_u, node_v))
                
                missing_edges.add((node_u, node_v))
                missing_edges.add((node_v, node_u))
            
            proposed_corridors.append({
                "id": f"Link between Zones {i+1} and {i+2}",
                "edges": set(corridor_edge_list),
                "score": corridor_score
            })
            
        except nx.NetworkXNoPath:
            pass
        
        G_undirected.remove_node(d_src)
        G_undirected.remove_node(d_tgt)

    proposed_corridors.sort(key=lambda x: x["score"], reverse=True)
    return proposed_corridors, missing_edges

def calculate_roi(G_safe, G_original, missing_edges):
    if not G_safe.nodes:
        return 0, 0, 0.0

    current_giant_component = max(nx.connected_components(nx.Graph(G_safe)), key=len)
    baseline_size = len(current_giant_component)

    G_hypothetical = G_safe.copy()
    for u, v in missing_edges:
        if G_original.has_edge(u, v):
            edge_data = G_original.get_edge_data(u, v)[0] 
            G_hypothetical.add_edge(u, v, **edge_data)

    new_giant_component = max(nx.connected_components(nx.Graph(G_hypothetical)), key=len)
    upgraded_size = len(new_giant_component)
    
    percentage_increase = ((upgraded_size - baseline_size) / baseline_size) * 100 if baseline_size > 0 else 0
    return baseline_size, upgraded_size, percentage_increase
