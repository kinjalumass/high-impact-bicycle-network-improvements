from __future__ import annotations

import math
import multiprocessing as mp
import os
from heapq import heappop, heappush
from itertools import count
from pathlib import Path
from time import perf_counter

import networkx as nx
import numpy as np
import pandas as pd

import argparse

# Each worker receives several origins at once.
# Increasing this reduces multiprocessing communication but may worsen
# load balancing if some origins are much more expensive than others.
TASK_CHUNKS_PER_WORKER = 2


# ============================================================
# Worker globals
#
# These routing structures are read-only inside each worker.
# ============================================================

_WORKER_ADJACENCY = None
_WORKER_EDGE_COUNT = 0

def initialize_worker(adjacency, edge_count):
    """Make read-only routing data available inside each worker."""
    global _WORKER_ADJACENCY, _WORKER_EDGE_COUNT

    _WORKER_ADJACENCY = adjacency
    _WORKER_EDGE_COUNT = edge_count


# ============================================================
# Routing
# ============================================================

def route_one_origin(origin,destination_counts,edge_loads,):
    """
    Run one Dijkstra search from an origin to all requested destinations.

    The search stops as soon as every requested destination has been
    permanently settled.

    Parameters
    ----------
    origin
        Source node ID.

    destination_counts
        Dictionary mapping destination node IDs to trip demand.

    edge_loads
        NumPy array modified in place. Each position corresponds to one
        graph edge.

    Returns
    -------
    list
        Unreachable OD records.
    """
    adjacency = _WORKER_ADJACENCY

    remaining = set(destination_counts)

    distances = {origin: 0.0}

    # Maps each reached node to:
    # (previous node, index of edge used to reach this node)
    predecessor = {origin: None}

    settled = set()

    # Prevents Python from comparing node IDs when two heap entries have
    # identical distances.
    tie_breaker = count()

    heap = [(0.0, next(tie_breaker), origin)]

    while heap and remaining:
        current_distance, _, u = heappop(heap)

        if u in settled:
            continue

        settled.add(u)

        if u in remaining:
            remaining.remove(u)

            # Every destination has now been reached.
            if not remaining:
                break

        for v, edge_cost, edge_idx in adjacency.get(u, ()):
            new_distance = current_distance + edge_cost

            if new_distance < distances.get(v, math.inf):
                distances[v] = new_distance
                predecessor[v] = (u, edge_idx)

                heappush(
                    heap,
                    (new_distance, next(tie_breaker), v),
                )

    unreachable = []

    # Reconstruct only the paths for destinations we actually need.
    for destination, demand in destination_counts.items():
        if destination in remaining:
            unreachable.append(
                (
                    origin,
                    destination,
                    demand,
                    "no_path",
                )
            )
            continue

        current = destination

        while current != origin:
            parent, edge_idx = predecessor[current]

            edge_loads[edge_idx] += demand
            current = parent

    return unreachable


def process_origin_chunk(origin_chunk):
    """
    Process several origins in one worker invocation.

    Each process keeps its own edge-count array, avoiding locks and
    shared writes.
    """
    edge_loads = np.zeros(
        _WORKER_EDGE_COUNT,
        dtype=np.float64,
    )

    unreachable = []
    processed_pairs = 0

    for origin, destination_counts in origin_chunk:
        unreachable.extend(
            route_one_origin(
                origin,
                destination_counts,
                edge_loads,
            )
        )

        processed_pairs += len(destination_counts)

    return edge_loads, unreachable, processed_pairs


# ============================================================
# Graph preparation
# ============================================================

def prepare_routing_graph(G):
    """
    Validate edge costs and build compact routing structures.

    For a MultiDiGraph, routing uses the cheapest parallel edge between
    each ordered pair of nodes. Path counts are assigned to that specific
    edge key, while other parallel edges remain at zero.

    Returns
    -------
    adjacency : dict
        node -> tuple of (neighbor, cost, edge_index)

    edge_refs : list
        Edge references corresponding to positions in the output count
        array.
    """
    adjacency = {}
    edge_refs = []

    if G.is_multigraph():
        edge_index = {}

        # Give every physical directed edge an integer index.
        for idx, (u, v, key, data) in enumerate(
            G.edges(keys=True, data=True)
        ):
            if "cost" not in data:
                raise ValueError(
                    f"Edge {(u, v, key)} has no 'cost' attribute."
                )

            edge_cost = float(data["cost"])

            if not math.isfinite(edge_cost):
                raise ValueError(
                    f"Edge {(u, v, key)} has non-finite cost "
                    f"{edge_cost}."
                )

            if edge_cost < 0:
                raise ValueError(
                    f"Edge {(u, v, key)} has negative cost "
                    f"{edge_cost}. Dijkstra requires nonnegative costs."
                )

            data["cost"] = edge_cost
            data["path_count"] = 0

            edge_index[(u, v, key)] = idx
            edge_refs.append((u, v, key))

        # For routing, choose the minimum-cost parallel edge for each
        # ordered node pair.
        for u in G.nodes:
            neighbors = []

            for v, keyed_edges in G[u].items():
                best_key, best_data = min(
                    keyed_edges.items(),
                    key=lambda item: item[1]["cost"],
                )

                neighbors.append(
                    (
                        v,
                        best_data["cost"],
                        edge_index[(u, v, best_key)],
                    )
                )

            adjacency[u] = tuple(neighbors)

    else:
        edge_index = {}

        for idx, (u, v, data) in enumerate(
            G.edges(data=True)
        ):
            if "cost" not in data:
                raise ValueError(
                    f"Edge {(u, v)} has no 'cost' attribute."
                )

            edge_cost = float(data["cost"])

            if not math.isfinite(edge_cost):
                raise ValueError(
                    f"Edge {(u, v)} has non-finite cost "
                    f"{edge_cost}."
                )

            if edge_cost < 0:
                raise ValueError(
                    f"Edge {(u, v)} has negative cost "
                    f"{edge_cost}. Dijkstra requires nonnegative costs."
                )

            data["cost"] = edge_cost
            data["path_count"] = 0

            edge_index[(u, v)] = idx
            edge_refs.append((u, v, None))

        for u in G.nodes:
            adjacency[u] = tuple(
                (
                    v,
                    data["cost"],
                    edge_index[(u, v)],
                )
                for v, data in G[u].items()
            )

    return adjacency, edge_refs


def apply_edge_loads(G, edge_refs, edge_loads):
    """Write the combined NumPy count array back onto the graph."""
    is_multigraph = G.is_multigraph()

    for idx, (u, v, key) in enumerate(edge_refs):
        value = float(edge_loads[idx])

        # GraphML writes ordinary Python numeric types more reliably than
        # NumPy scalar types.
        if value.is_integer():
            value = int(value)

        if is_multigraph:
            G.edges[u, v, key]["path_count"] = value
        else:
            G.edges[u, v]["path_count"] = value


# ============================================================
# OD preparation
# ============================================================

def load_and_prepare_od_data(path, graph_nodes):
    """
    Load, validate, aggregate, and group OD demand.

    Returns
    -------
    origin_tasks
        List of:
        (origin, {destination: demand})

    failed_records
        Missing-node OD records.

    input_stats
        Summary information.
    """
    od_df = pd.read_csv(
        path,
        dtype={
            "origin_node": "string",
            "destination_node": "string",
        },
    )

    required_columns = {
        "origin_node",
        "destination_node",
        "count",
    }

    missing_columns = required_columns - set(od_df.columns)

    if missing_columns:
        raise ValueError(
            f"OD file is missing columns: {sorted(missing_columns)}"
        )

    original_row_count = len(od_df)

    # Remove rows with missing required fields.
    od_df = od_df.dropna(
        subset=[
            "origin_node",
            "destination_node",
            "count",
        ]
    ).copy()

    od_df["origin_node"] = od_df["origin_node"].astype(str)
    od_df["destination_node"] = od_df["destination_node"].astype(str)

    od_df["count"] = pd.to_numeric(
        od_df["count"],
        errors="raise",
    )

    if (od_df["count"] < 0).any():
        raise ValueError("OD demand contains negative count values.")

    # Zero-demand records cannot affect edge usage.
    od_df = od_df.loc[od_df["count"] > 0].copy()

    # Combine duplicate OD pairs before routing.
    od_df = (
        od_df.groupby(
            ["origin_node", "destination_node"],
            as_index=False,
            sort=False,
        )["count"]
        .sum()
    )

    unique_pair_count = len(od_df)

    graph_nodes = set(graph_nodes)

    origin_exists = od_df["origin_node"].isin(graph_nodes)
    destination_exists = od_df["destination_node"].isin(graph_nodes)

    missing_mask = ~(origin_exists & destination_exists)

    missing_df = od_df.loc[missing_mask].copy()

    missing_df["reason"] = np.select(
        [
            ~origin_exists.loc[missing_mask]
            & ~destination_exists.loc[missing_mask],

            ~origin_exists.loc[missing_mask],

            ~destination_exists.loc[missing_mask],
        ],
        [
            "origin_and_destination_not_in_graph",
            "origin_not_in_graph",
            "destination_not_in_graph",
        ],
        default="unknown",
    )

    failed_records = list(
        missing_df[
            [
                "origin_node",
                "destination_node",
                "count",
                "reason",
            ]
        ].itertuples(index=False, name=None)
    )

    valid_df = od_df.loc[~missing_mask].copy()

    # Origin == destination contributes no edge usage.
    self_trip_mask = (
        valid_df["origin_node"]
        == valid_df["destination_node"]
    )

    self_trip_count = int(self_trip_mask.sum())

    valid_df = valid_df.loc[~self_trip_mask].copy()

    origin_tasks = []

    for origin, group in valid_df.groupby(
        "origin_node",
        sort=False,
    ):
        destination_counts = dict(
            zip(
                group["destination_node"],
                group["count"],
            )
        )

        origin_tasks.append(
            (origin, destination_counts)
        )

    stats = {
        "original_rows": original_row_count,
        "unique_pairs": unique_pair_count,
        "valid_pairs": len(valid_df),
        "unique_origins": len(origin_tasks),
        "missing_node_pairs": len(missing_df),
        "self_pairs": self_trip_count,
    }

    return origin_tasks, failed_records, stats


def make_balanced_chunks(origin_tasks, chunk_count):
    """
    Distribute expensive origins across chunks approximately evenly.

    Number of destinations is used as a simple estimate of routing work.
    """
    chunk_count = max(
        1,
        min(chunk_count, len(origin_tasks)),
    )

    chunks = [[] for _ in range(chunk_count)]
    loads = [0] * chunk_count

    # Put large origin groups first, then repeatedly assign to the
    # currently lightest chunk.
    sorted_tasks = sorted(
        origin_tasks,
        key=lambda item: len(item[1]),
        reverse=True,
    )

    for task in sorted_tasks:
        lightest_chunk = min(
            range(chunk_count),
            key=loads.__getitem__,
        )

        chunks[lightest_chunk].append(task)
        loads[lightest_chunk] += len(task[1])

    return [
        chunk
        for chunk in chunks
        if chunk
    ]


# ============================================================
# Main execution
# ============================================================

def main():
    #Parser
    parser = argparse.ArgumentParser(description="Specify which graph and which set of origin-destination pairs are being considered for Usage Analysis.")
    parser.add_argument("dataFolder", type=str, help="The folder where all data is stored (and where outputs will be stored).")
    parser.add_argument("demandScenario", type=int, help="The specific demand scenario being considered (Should be the number that identifies the scenario).")
    parser.add_argument("costScenario", type=int, help="The specific cost scenario/graph being considered (Should be the number that identifies the scenario).")
    parser.add_argument("region", type=str, help="The region being considered (Options: Boston, Brookline, Cambridge, Somerville, or All).")
    args = parser.parse_args()

    #Defining folder paths
    OD_FOLDER = Path(f"{args.dataFolder}/output/demand_scenarios/demand_scenario_{args.demandScenario}/")
    GRAPH_FOLDER = Path(f"{args.dataFolder}/output/cost_scenarios/cost_scenario_{args.costScenario}/")
    OUTPUT_FOLDER = Path(f"{args.dataFolder}/processed/road_usage_analysis/")

    #Defining file paths 
    if args.region == "All":
        GRAPH_PATH = GRAPH_FOLDER / f"greater_boston_cost_scenario_{args.costScenario}_simplified.graphml"
        OD_PATH = OD_FOLDER / f"greater_boston_all_pairs_demand_scenario_{args.demandScenario}.csv"
        OUTPUT_GRAPH_PATH = OUTPUT_FOLDER / f"greater_boston_cost_with_pathCount_DS{args.demandScenario}_CS{args.costScenario}.graphml"
        FAILED_OD_PATH = OUTPUT_FOLDER / f"greater_boston_unroutable_pairs_DS{args.demandScenario}_CS{args.costScenario}.csv"
    elif args.region in ["Boston", "Brookline", "Cambridge", "Somerville"]:
        GRAPH_PATH = GRAPH_FOLDER / f"{args.region}_cost_scenario_{args.costScenario}_simplified.graphml"
        OD_PATH = OD_FOLDER / f"{args.region}_all_pairs_demand_scenario_{args.demandScenario}.csv"
        OUTPUT_GRAPH_PATH = OUTPUT_FOLDER / f"{args.region}_cost_with_pathCount_DS{args.demandScenario}_CS{args.costScenario}.graphml"
        FAILED_OD_PATH = OUTPUT_FOLDER / f"{args.region}_unroutable_pairs_DS{args.demandScenario}_CS{args.costScenario}.csv"
    else:
        raise ValueError("Invalid region. Please try 'Boston', 'Brookline', 'Cambridge', 'Somerville', or 'All'")

    Path(OUTPUT_FOLDER).mkdir(
        parents=True,
        exist_ok=True,
    )

    start_time = perf_counter()

    print(f"Reading graph: {GRAPH_PATH}")

    G = nx.read_graphml(GRAPH_PATH)

    if not G.is_directed():
        raise ValueError(
            "The routing graph is not directed. "
            "A directed graph is required for one-way streets."
        )

    print(
        f"Graph loaded: "
        f"{G.number_of_nodes():,} nodes, "
        f"{G.number_of_edges():,} edges, "
        f"type={type(G).__name__}"
    )

    print("Preparing routing adjacency...")

    adjacency, edge_refs = prepare_routing_graph(G)

    print(f"Reading OD demand: {OD_PATH}")

    origin_tasks, failed_records, stats = (
        load_and_prepare_od_data(
            OD_PATH,
            G.nodes,
        )
    )

    print(
        f"Input rows: {stats['original_rows']:,}\n"
        f"Unique OD pairs: {stats['unique_pairs']:,}\n"
        f"Routable non-self pairs: {stats['valid_pairs']:,}\n"
        f"Unique origins: {stats['unique_origins']:,}\n"
        f"Missing-node pairs: {stats['missing_node_pairs']:,}\n"
        f"Self OD pairs skipped: {stats['self_pairs']:,}"
    )

    if not origin_tasks:
        print("No routable OD pairs were found.")

        total_edge_loads = np.zeros(
            len(edge_refs),
            dtype=np.float64,
        )

    else:
        # Under SLURM, use the cores assigned with --cpus-per-task.
        requested_workers = int(
            os.environ.get(
                "SLURM_CPUS_PER_TASK",
                os.cpu_count() or 1,
            )
        )

        worker_count = max(
            1,
            min(requested_workers, len(origin_tasks)),
        )

        chunk_count = min(
            len(origin_tasks),
            worker_count * TASK_CHUNKS_PER_WORKER,
        )

        origin_chunks = make_balanced_chunks(
            origin_tasks,
            chunk_count,
        )

        print(
            f"Routing with {worker_count} worker processes "
            f"across {len(origin_chunks)} balanced chunks."
        )

        total_edge_loads = np.zeros(
            len(edge_refs),
            dtype=np.float64,
        )

        processed_pairs = 0

        if worker_count == 1:
            initialize_worker(
                adjacency,
                len(edge_refs),
            )

            results = map(
                process_origin_chunk,
                origin_chunks,
            )

            for edge_loads, unreachable, pair_count in results:
                total_edge_loads += edge_loads
                failed_records.extend(unreachable)
                processed_pairs += pair_count

        else:
            # Fork is especially useful on Linux HPC systems because the
            # large read-only adjacency structure can be inherited by
            # workers using copy-on-write memory.
            start_method = (
                "fork"
                if "fork" in mp.get_all_start_methods()
                else "spawn"
            )

            context = mp.get_context(start_method)

            with context.Pool(
                processes=worker_count,
                initializer=initialize_worker,
                initargs=(
                    adjacency,
                    len(edge_refs),
                ),
            ) as pool:
                results = pool.imap_unordered(
                    process_origin_chunk,
                    origin_chunks,
                    chunksize=1,
                )

                progress_interval = max(
                    1,
                    len(origin_chunks) // 20,
                )

                for completed, result in enumerate(
                    results,
                    start=1,
                ):
                    edge_loads, unreachable, pair_count = result

                    total_edge_loads += edge_loads
                    failed_records.extend(unreachable)
                    processed_pairs += pair_count

                    if (
                        completed % progress_interval == 0
                        or completed == len(origin_chunks)
                    ):
                        print(
                            f"Completed {completed:,}/"
                            f"{len(origin_chunks):,} chunks; "
                            f"{processed_pairs:,}/"
                            f"{stats['valid_pairs']:,} OD pairs."
                        )

    print("Applying path counts to graph...")

    apply_edge_loads(
        G,
        edge_refs,
        total_edge_loads,
    )

    print(f"Writing graph: {OUTPUT_GRAPH_PATH}")

    nx.write_graphml(
        G,
        OUTPUT_GRAPH_PATH,
    )

    failed_df = pd.DataFrame(
        failed_records,
        columns=[
            "origin_node",
            "destination_node",
            "count",
            "reason",
        ],
    )

    # Always write this file, even when empty, so an old failure file
    # cannot be mistaken for results from the latest run.
    failed_df.to_csv(
        FAILED_OD_PATH,
        index=False,
    )

    elapsed = perf_counter() - start_time

    no_path_count = int(
        (failed_df["reason"] == "no_path").sum()
    ) if not failed_df.empty else 0

    print(
        "\nRouting complete.\n"
        f"Graph saved to: {OUTPUT_GRAPH_PATH}\n"
        f"Failure report saved to: {FAILED_OD_PATH}\n"
        f"No-path OD pairs: {no_path_count:,}\n"
        f"Elapsed time: {elapsed / 60:.2f} minutes"
    )


if __name__ == "__main__":
    main()
