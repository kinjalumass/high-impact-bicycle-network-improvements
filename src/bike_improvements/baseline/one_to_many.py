"""One-to-many UCS baseline routing with per-OD and per-edge outputs."""

from __future__ import annotations

import math
import multiprocessing as mp
from heapq import heappop, heappush
from itertools import count
from time import perf_counter
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd


_WORKER_ADJACENCY = None
_WORKER_EDGE_COUNT = 0


def initialize_worker(adjacency, edge_count):
    """Initialize read-only routing data for a worker."""
    global _WORKER_ADJACENCY, _WORKER_EDGE_COUNT

    _WORKER_ADJACENCY = adjacency
    _WORKER_EDGE_COUNT = edge_count


def prepare_baseline_graph(G: nx.Graph):
    """
    Build compact adjacency and edge-reference structures.

    For parallel edges, routing uses the minimum-cost edge, matching the
    existing path-count implementation.
    """
    adjacency = {}
    edge_refs = []
    edge_index = {}

    if G.is_multigraph():
        for idx, (u, v, key, data) in enumerate(
            G.edges(keys=True, data=True)
        ):
            cost = float(data["cost"])
            length = float(data["length"])

            if not math.isfinite(cost) or cost < 0:
                raise ValueError(
                    f"Invalid routing cost on edge {(u, v, key)}: {cost}"
                )

            if not math.isfinite(length) or length < 0:
                raise ValueError(
                    f"Invalid length on edge {(u, v, key)}: {length}"
                )

            edge_index[(u, v, key)] = idx
            edge_refs.append((u, v, key))

        for u in G.nodes:
            neighbors = []

            for v, keyed_edges in G[u].items():
                best_key, best_data = min(
                    keyed_edges.items(),
                    key=lambda item: float(item[1]["cost"]),
                )

                neighbors.append(
                    (
                        v,
                        float(best_data["cost"]),
                        float(best_data["length"]),
                        edge_index[(u, v, best_key)],
                    )
                )

            adjacency[u] = tuple(neighbors)

    else:
        for idx, (u, v, data) in enumerate(
            G.edges(data=True)
        ):
            cost = float(data["cost"])
            length = float(data["length"])

            if not math.isfinite(cost) or cost < 0:
                raise ValueError(
                    f"Invalid routing cost on edge {(u, v)}: {cost}"
                )

            if not math.isfinite(length) or length < 0:
                raise ValueError(
                    f"Invalid length on edge {(u, v)}: {length}"
                )

            edge_index[(u, v)] = idx
            edge_refs.append((u, v, None))

        for u in G.nodes:
            adjacency[u] = tuple(
                (
                    v,
                    float(data["cost"]),
                    float(data["length"]),
                    edge_index[(u, v)],
                )
                for v, data in G[u].items()
            )

    return adjacency, edge_refs


def prepare_od_tasks(
    od_df: pd.DataFrame,
    graph_nodes,
):
    """Validate OD data and group requested destinations by origin."""
    required = {
        "origin_node",
        "destination_node",
        "category",
        "count",
    }

    missing = required - set(od_df.columns)

    if missing:
        raise ValueError(
            f"OD data missing columns: {sorted(missing)}"
        )

    df = od_df[
        [
            "origin_node",
            "destination_node",
            "category",
            "count",
        ]
    ].copy()

    df = df.dropna(
        subset=[
            "origin_node",
            "destination_node",
            "category",
            "count",
        ]
    )

    df["origin_node"] = df["origin_node"].astype(str)
    df["destination_node"] = df["destination_node"].astype(str)

    df["count"] = pd.to_numeric(
        df["count"],
        errors="raise",
    )

    if (df["count"] < 0).any():
        raise ValueError("OD data contains negative demand.")

    df = df.loc[df["count"] > 0].copy()

    # Combine only true duplicates. Category is deliberately preserved.
    df = (
        df.groupby(
            [
                "origin_node",
                "destination_node",
                "category",
            ],
            as_index=False,
            sort=False,
        )["count"]
        .sum()
    )

    graph_nodes = set(graph_nodes)

    immediate_records = []
    routable_rows = []

    for row in df.itertuples(index=False):
        origin = row.origin_node
        destination = row.destination_node
        category = row.category
        demand = float(row.count)

        origin_exists = origin in graph_nodes
        destination_exists = destination in graph_nodes

        if not origin_exists or not destination_exists:
            if not origin_exists and not destination_exists:
                status = "origin_and_destination_not_in_graph"
            elif not origin_exists:
                status = "origin_not_in_graph"
            else:
                status = "destination_not_in_graph"

            immediate_records.append(
                {
                    "origin_node": origin,
                    "destination_node": destination,
                    "category": category,
                    "demand": demand,
                    "found": False,
                    "status": status,
                    "route_cost": np.nan,
                    "route_distance": np.nan,
                    "route_edge_count": 0,
                }
            )

            continue

        if origin == destination:
            immediate_records.append(
                {
                    "origin_node": origin,
                    "destination_node": destination,
                    "category": category,
                    "demand": demand,
                    "found": True,
                    "status": "self_trip",
                    "route_cost": 0.0,
                    "route_distance": 0.0,
                    "route_edge_count": 0,
                }
            )

            continue

        routable_rows.append(
            (
                origin,
                destination,
                category,
                demand,
            )
        )

    by_origin: dict[str, dict[str, list[tuple[str, float]]]] = {}

    for origin, destination, category, demand in routable_rows:
        destinations = by_origin.setdefault(origin, {})
        metadata = destinations.setdefault(destination, [])
        metadata.append((category, demand))

    tasks = list(by_origin.items())

    stats = {
        "grouped_od_records": len(df),
        "routing_origins": len(tasks),
        "immediate_records": len(immediate_records),
        "routing_records": len(routable_rows),
    }

    return tasks, immediate_records, stats


def route_one_origin(
    origin,
    destination_metadata,
    edge_loads,
):
    """Run one UCS search from an origin to all requested destinations."""
    adjacency = _WORKER_ADJACENCY

    remaining = set(destination_metadata)

    distances = {origin: 0.0}
    predecessor = {origin: None}
    settled = set()

    tie_breaker = count()

    heap = [
        (
            0.0,
            next(tie_breaker),
            origin,
        )
    ]

    start = perf_counter()

    while heap and remaining:
        current_cost, _, u = heappop(heap)

        if u in settled:
            continue

        settled.add(u)

        if u in remaining:
            remaining.remove(u)

            if not remaining:
                break

        for v, edge_cost, edge_length, edge_idx in adjacency.get(
            u,
            (),
        ):
            new_cost = current_cost + edge_cost

            if new_cost < distances.get(v, math.inf):
                distances[v] = new_cost

                predecessor[v] = (
                    u,
                    edge_idx,
                    edge_length,
                )

                heappush(
                    heap,
                    (
                        new_cost,
                        next(tie_breaker),
                        v,
                    ),
                )

    runtime = perf_counter() - start

    records = []

    for destination, metadata in destination_metadata.items():
        if destination in remaining:
            for category, demand in metadata:
                records.append(
                    {
                        "origin_node": origin,
                        "destination_node": destination,
                        "category": category,
                        "demand": demand,
                        "found": False,
                        "status": "no_path",
                        "route_cost": np.nan,
                        "route_distance": np.nan,
                        "route_edge_count": 0,
                    }
                )

            continue

        current = destination

        route_distance = 0.0
        route_edge_count = 0
        route_edge_indices = []

        while current != origin:
            parent, edge_idx, edge_length = predecessor[current]

            route_edge_indices.append(edge_idx)
            route_distance += edge_length
            route_edge_count += 1

            current = parent

        total_demand = sum(
            demand
            for _, demand in metadata
        )

        for edge_idx in route_edge_indices:
            edge_loads[edge_idx] += total_demand

        for category, demand in metadata:
            records.append(
                {
                    "origin_node": origin,
                    "destination_node": destination,
                    "category": category,
                    "demand": demand,
                    "found": True,
                    "status": "routed",
                    "route_cost": distances[destination],
                    "route_distance": route_distance,
                    "route_edge_count": route_edge_count,
                }
            )

    origin_stats = {
        "origin_node": origin,
        "destinations_requested": len(destination_metadata),
        "nodes_expanded": len(settled),
        "runtime_seconds": runtime,
    }

    return records, origin_stats


def process_origin_chunk(origin_chunk):
    """Process a balanced group of origins in one worker."""
    edge_loads = np.zeros(
        _WORKER_EDGE_COUNT,
        dtype=np.float64,
    )

    records = []
    origin_stats = []

    for origin, destination_metadata in origin_chunk:
        origin_records, stats = route_one_origin(
            origin,
            destination_metadata,
            edge_loads,
        )

        records.extend(origin_records)
        origin_stats.append(stats)

    return edge_loads, records, origin_stats


def make_balanced_chunks(tasks, workers):
    """Distribute origins approximately evenly by destination count."""
    if not tasks:
        return []

    n_chunks = min(
        len(tasks),
        max(1, workers * 2),
    )

    bins = [[] for _ in range(n_chunks)]
    loads = [0] * n_chunks

    ordered = sorted(
        tasks,
        key=lambda item: len(item[1]),
        reverse=True,
    )

    for task in ordered:
        idx = min(
            range(n_chunks),
            key=lambda i: loads[i],
        )

        bins[idx].append(task)
        loads[idx] += len(task[1])

    return [
        chunk
        for chunk in bins
        if chunk
    ]


def run_one_to_many_baseline(
    G: nx.Graph,
    od_df: pd.DataFrame,
    workers: int = 1,
):
    """Route a complete OD table with one UCS search per unique origin."""
    adjacency, edge_refs = prepare_baseline_graph(G)

    tasks, immediate_records, input_stats = prepare_od_tasks(
        od_df,
        G.nodes,
    )

    chunks = make_balanced_chunks(
        tasks,
        workers,
    )

    total_edge_loads = np.zeros(
        len(edge_refs),
        dtype=np.float64,
    )

    all_records = list(immediate_records)
    all_origin_stats = []

    if workers <= 1:
        initialize_worker(
            adjacency,
            len(edge_refs),
        )

        for chunk in chunks:
            edge_loads, records, stats = process_origin_chunk(
                chunk
            )

            total_edge_loads += edge_loads
            all_records.extend(records)
            all_origin_stats.extend(stats)

    else:
        with mp.Pool(
            processes=workers,
            initializer=initialize_worker,
            initargs=(
                adjacency,
                len(edge_refs),
            ),
        ) as pool:
            for edge_loads, records, stats in pool.imap_unordered(
                process_origin_chunk,
                chunks,
                chunksize=1,
            ):
                total_edge_loads += edge_loads
                all_records.extend(records)
                all_origin_stats.extend(stats)

    route_df = pd.DataFrame(all_records)
    origin_stats_df = pd.DataFrame(all_origin_stats)

    return (
        route_df,
        total_edge_loads,
        edge_refs,
        origin_stats_df,
        input_stats,
    )


def edge_usage_dataframe(
    G: nx.Graph,
    edge_refs,
    edge_loads,
) -> pd.DataFrame:
    """Convert demand-weighted edge loads into a tabular result."""
    records = []

    is_multi = G.is_multigraph()

    for idx, (u, v, key) in enumerate(edge_refs):
        if is_multi:
            data = G.edges[u, v, key]
        else:
            data = G.edges[u, v]

        records.append(
            {
                "u": u,
                "v": v,
                "key": key,
                "path_count": float(edge_loads[idx]),
                "cost": float(data["cost"]),
                "length": float(data["length"]),
                "max_lts": data.get("max_lts", data.get("LTS")),
                "LTS": data.get("LTS"),
            }
        )

    return pd.DataFrame(records)
