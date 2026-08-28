# Source Code Provenance

This project builds upon code from the following repositories.

## BCU Graph Analysis

Repository:
https://github.com/kinjalumass/BCU-Graph-Analysis

Reused components include:

- OpenStreetMap graph construction
- Level of Traffic Stress calculation
- stress-weighted edge cost construction
- Census population assignment
- destination extraction
- origin-destination demand generation
- one-to-many Dijkstra/UCS routing
- road-usage metrics
- preliminary corridor analysis

The initial implementation was taken from the `main` branch in August 2026.

## StressMap

Repository:
https://github.com/kinjalumass/StressMap

The graph-building pipeline contains LTS-processing code based on the
StressMap project. The original repository is retained as a Git remote
for provenance and comparison.

## COMPSCI 683 Project-Specific Work

The `src/bike_improvements/` package contains analyses developed
specifically for the course project, including:

- UCS and A* comparison
- rider-profile baseline experiments
- candidate improvement generation
- simulated bicycle-network interventions
- demand-weighted benefit analysis
- greedy project-selection optimization
- robustness analysis
