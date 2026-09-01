# Software Provenance and Attribution

This repository is methodologically self-contained: the README and final report describe the complete network construction, demand modeling, routing, intervention-analysis, optimization, and robustness methodology used for the COMPSCI 683 project.

This file records software provenance and attribution for utilities that were adapted from prior work. It is not required to understand the analysis or reproduce the project methodology described in this repository.

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
StressMap project. The source repository is linked above for provenance and comparison.

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
