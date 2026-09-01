import networkx as nx
import pandas as pd
import argparse
from pathlib import Path

def distributions(graph_path, graph_file, output_name, output_path, path_count, distance, max_lts, cost, usage_stress, potential_Dbenefit):

    print("Loading graph...")
    G = nx.read_graphml(f"{graph_path}{graph_file}")

    # Extract edge attributes into a list of dictionaries
    print("Extracting edge attributes...")
    edge_attributes = []
    for u, v, data in G.edges(data=True):
        edge_attributes.append({
            'osmid': data.get('osmid'), #Unique id for each edge
            'usage_stress': data.get('usage_stress'), #path_count*max_lts
            'potential_Dbenefit': data.get('potential_Dbenefit'), #path_count*(cost-distance)
            'path_count' : data.get('path_count'), #number of least-cost paths that cross through the edge
            'distance': data.get('length'), #The length/distance of an edge
            'max_lts': data.get('max_lts'), #The highest stress level present on the edge
            'cost' : data.get('cost') #sum(LTScoefficient*distance) for all smaller segments that make up an edge
        })

    #Convert to a Pandas DataFrame
    df = pd.DataFrame(edge_attributes)
    df.to_csv(f'{output_path}{output_name}.csv', index=False)
    print(f"Saved edge data to: {output_path}{output_name}.csv")

    print(f"For {graph_file}...")
    if path_count:
        df['path_count'] = pd.to_numeric(df['path_count'], errors='coerce')
        df_path_count = df[df['path_count']!=0]
        print("=== USAGE SUMMARY STATISTICS ===")
        print(df_path_count['path_count'].describe())
        print("\n" + "="*40 + "\n")
    if distance:
        df['distance'] = pd.to_numeric(df['distance'], errors='coerce')
        df_distance = df[df['distance']!=0]
        print("=== DISTANCE SUMMARY STATISTICS ===")
        print(df_distance['distance'].describe())
        print("\n" + "="*40 + "\n")
    if max_lts:
        df['max_lts'] = pd.to_numeric(df['max_lts'], errors='coerce')
        df_max_lts = df[df['max_lts']!=0]
        print("=== MAX LTS STATISTICS ===")
        print(df_max_lts['max_lts'].describe())
        print("\n" + "="*40 + "\n")
    if cost:
        df['cost'] = pd.to_numeric(df['cost'], errors='coerce')
        df_cost = df[df['cost']!=0]
        print("=== COST SUMMARY STATISTICS ===")
        print(df_cost['cost'].describe())
        print("\n" + "="*40 + "\n")
    if usage_stress:
        df['usage_stress'] = pd.to_numeric(df['usage_stress'], errors='coerce')
        df_usage_stress = df[df['usage_stress']!=0]
        print("=== USAGE STRESS SUMMARY STATISTICS ===")
        print(df_usage_stress['usage_stress'].describe())
        print("\n" + "="*40 + "\n")
    if potential_Dbenefit:
        df['potential_Dbenefit'] = pd.to_numeric(df['potential_Dbenefit'], errors='coerce')
        df_potential = df[df['potential_Dbenefit']!=0]
        print("=== POTENTIAL DBENFIT SUMMARY STATISTICS ===")
        print(df_potential['potential_Dbenefit'].describe())

def main():
    parser = argparse.ArgumentParser(description="Determining the scenario to be run and what edge metrics to report distributions on.")
    parser.add_argument("dataFolder", type=str, help="The folder which the data is stored (and the output will be stored).")
    parser.add_argument("region", type=str, help="The region which is being considered (Options: Boston, Brookline, Cambridge, Somerville, or All).")
    parser.add_argument("demandScenario", type=int, help="The specific demand scenario being considered (the number that identifies the scenario).")
    parser.add_argument("costScenario", type=int, help="The specific cost scenario being considered (the number that identifies the scenario).")
    parser.add_argument("--no_path_count", action="store_false", help="Call this tag if the distribution of 'path_count' is not wanted")
    parser.add_argument("--no_distance", action="store_false", help="Call if the distribution of 'distance' is not wanted")
    parser.add_argument("--no_max_lts", action="store_false", help="Call if the distribution of 'max_lts' is not wanted")
    parser.add_argument("--no_cost", action="store_false", help="Call if the distribution of 'cost' is not wanted")
    parser.add_argument("--no_usage_stress", action="store_false", help="Call if the distribution of 'usage_stress' is not wanted")
    parser.add_argument("--no_potential_Dbenefit", action="store_false", help="Call if the distribution of 'potential_Dbenefit' is not wanted")
    args = parser.parse_args()

    if args.region == "All":
        graphFile = f"greater_boston_metrics_DS{args.demandScenario}_CS{args.costScenario}.graphml"
        outputName = f"edges_greater_boston_DS{args.demandScenario}_CS{args.costScenario}"
    elif args.region in ['Boston', 'Brookline', 'Cambridge', 'Somerville', 'All']:
        graphFile = f"{args.region}_metrics_DS{args.demandScenario}_CS{args.costScenario}.graphml"
        outputName = f"edges_{args.region}_DS{args.demandScenario}_CS{args.costScenario}"
    else:
        raise ValueError("Invalid region. Please try 'Boston', 'Brookline', 'Cambridge', 'Somerville', or 'All'.")

    graphPath = f"{args.dataFolder}/processed/road_usage_analysis/"
    outputPath = f"{args.dataFolder}/processed/road_usage_analysis/DistributionAnalysis/"
    Path(outputPath).mkdir(
        parents=True,
        exist_ok=True,
    )
    path_count = args.no_path_count
    distance = args.no_distance
    max_lts = args.no_max_lts
    cost = args.no_cost
    usage_stress = args.no_usage_stress
    potential_Dbenefit = args.no_potential_Dbenefit

    distributions(graphPath, graphFile, outputName, outputPath, path_count, distance, max_lts, cost, usage_stress, potential_Dbenefit)

if __name__ == '__main__':
    main()