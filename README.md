# Identifying High-Impact Bicycle Network Improvements

COMPSCI 683 Project

This project evaluates which bicycle-network infrastructure improvements
could produce the greatest modeled benefit in the Boston/Greater Boston
cycling network using Level of Traffic Stress, modeled travel demand,
population, destinations, and graph-search algorithms.

The project builds upon the Boston Cyclists Union / UMass CDS graph
analysis pipeline and extends it with:

1. UCS and A* routing comparison
2. rider-profile-specific routing
3. candidate infrastructure improvement generation
4. before/after network intervention simulations
5. demand-weighted benefit scoring
6. greedy constrained project selection
7. robustness analysis

## Repository Structure

- `src/bcu_analysis/` — reused graph, demand, routing, and analysis infrastructure
- `src/bike_improvements/` — COMPSCI 683 project-specific implementation
- `configs/` — reproducible experiment configurations
- `scripts/` — experiment entry points
- `tests/` — tests
- `results/` — generated experimental results
- `reports/` — project report material
