# Identifying High-Impact Bicycle Network Improvements
**COMPSCI 683 — Artificial Intelligence**  
**Kinjal Pandey**  
**University of Massachusetts Amherst**
## Abstract
Bicycle-network planning requires more than identifying streets that appear stressful in isolation. An infrastructure improvement is most valuable when it changes the routes that people can reasonably use and reduces the cumulative stress experienced across trips with meaningful travel demand. This project develops a graph-based framework for identifying high-impact bicycle-network improvements in Greater Boston using Level of Traffic Stress (LTS), modeled origin-destination demand, rider-specific stress preferences, and shortest-path search.
The analysis represents the bicycle network as a directed graph and assigns each edge a generalized traversal cost equal to physical length multiplied by a rider-profile-specific LTS weight. Four rider profiles are modeled: child, low-confidence adult, typical adult, and experienced adult. Uniform-cost search (UCS) and A* are used for route computation, and one-to-many routing is used to evaluate the full modeled demand dataset efficiently.
Twenty candidate high-stress segments were generated using modeled demand and stress exposure. The ten strongest candidates were then evaluated through full before-and-after network simulations in which each candidate's LTS was reduced to 2 and all affected routes were recomputed. Chauncy Street ranked first as an individual intervention, followed by Cambridge Street and Hyde Park Avenue.
A greedy optimization procedure was subsequently used to select a five-project package. Rather than adding isolated candidate benefits, every optimization round rerouted the complete demand set after applying the current package. The final baseline package consisted of C001 Chauncy Street, C002 Cambridge Street, C003 Hyde Park Avenue, C004 Beacon Street, and C006 Dartmouth Street. Its mean demand-weighted generalized-cost reduction across rider profiles was 361,774.05, over approximately 779.67 meters of candidate infrastructure.
Robustness experiments showed that this result was highly stable to resampling modeled travel demand but more sensitive to assumptions about rider stress aversion. An alternate fixed OD sample reproduced the same five-project package exactly and produced only a 0.137% change in the final generalized-cost benefit. Stronger LTS aversion produced a different five-project package with three of the five baseline projects retained. These findings indicate that the framework is highly stable to reasonable demand resampling while emphasizing the importance of behavioral assumptions about how strongly riders avoid stressful infrastructure.
## 1. Introduction
A road segment with high bicycle stress is not automatically a high-priority infrastructure investment. Its practical importance depends on where it lies in the network, how many modeled trips encounter it or could benefit from it, what alternative routes exist, and how different classes of riders respond to traffic stress.
This project asks:
> **Which bicycle-network infrastructure improvements would produce the greatest modeled reduction in travel stress for riders in Greater Boston?**
The project extends prior Boston Cyclists Union and UMass Center for Data Science graph-analysis infrastructure with a project-specific intervention framework. The primary additions are:
- implementation and comparison of UCS and A* routing;
- rider-profile-specific generalized routing costs;
- generation of candidate infrastructure improvements;
- full before-and-after network simulations;
- demand-weighted intervention scoring;
- greedy multi-project optimization; and
- robustness analysis under alternate demand and rider-behavior assumptions.
The purpose is not to predict the exact real-world effect of construction. Instead, the framework provides a reproducible computational method for comparing candidate improvements according to their modeled ability to reduce bicycle travel stress across a large travel-demand sample.
## 2. Data and Network Representation
The study uses a Greater Boston bicycle-network graph derived from OpenStreetMap-based network data developed through the broader Boston Cyclists Union analysis pipeline.
The simplified routing graph contains approximately 98,000 nodes and 280,000 directed edges. Each relevant road segment is associated with a Level of Traffic Stress value from 1 through 4:
- LTS 1: lowest-stress conditions;
- LTS 2: generally comfortable for a broader set of riders;
- LTS 3: higher-stress conditions;
- LTS 4: highest-stress conditions.
The modeled demand dataset contains approximately 42,000 origin-destination records representing 50,000 units of total modeled demand. Trips include several destination categories, including employment, schools, healthcare, transit, greenspace, and stores.
Under the baseline network, 45,568 of the 50,000 modeled demand units were routable, corresponding to a demand-weighted routing success rate of approximately 91.1%. Unroutable demand was retained as a property of network topology rather than altered by the cost-only interventions evaluated here.
## 3. Rider-Specific Generalized Cost
Shortest physical distance alone is insufficient for modeling bicycle-route preference because riders may accept additional distance to avoid stressful roads.
For an edge $e$, generalized traversal cost is modeled as:
$$\mathrm{Cost}(e) = \mathrm{Length}(e) \times \mathrm{StressWeight}(\mathrm{LTS}(e))$$
where the stress weight depends on the rider profile.
Four rider profiles were evaluated:
- Child: strongest baseline aversion to high-stress links;
- Low-confidence adult: similarly strong avoidance of stressful infrastructure;
- Typical adult: moderate stress sensitivity;
- Experienced adult: lowest modeled aversion to higher LTS.
Edges representing unavailable or inappropriate bicycle access receive a very high traversal weight so that they are avoided when feasible alternatives exist.
This formulation allows the routing algorithms to select longer but lower-stress paths when their generalized cost is lower.
## 4. Routing
Both uniform-cost search and A* were implemented and evaluated.
UCS guarantees an optimal route under the generalized edge-cost definition by expanding nodes in increasing path-cost order. A* supplements accumulated path cost with an admissible geographic heuristic to guide the search toward the destination.
Benchmark testing confirmed that both algorithms produced the same optimal route costs for routable test pairs. A* generally reduced search effort relative to UCS while preserving optimality.
### 4.1 UCS and A* Validation

A deterministic benchmark compared UCS and A* on 100 identical origin-destination pairs from the baseline network. Both algorithms found routes for the same 93 pairs, while the remaining seven pairs were unreachable under both algorithms.

| Metric | UCS | A* | A* reduction |
|---|---:|---:|---:|
| Routable pairs | 93 | 93 | — |
| Mean runtime, all pairs | 0.05885 s | 0.05175 s | 12.1% |
| Median runtime, all pairs | 0.02056 s | 0.01099 s | 46.5% |
| Mean nodes expanded | 19,799.55 | 12,033.43 | 39.2% |
| Median nodes expanded | 8,349 | 2,922 | 65.0% |
| Mean generalized cost, routable pairs | 6,965.06 | 6,965.06 | 0% |

The maximum UCS/A* optimal-cost difference across routable benchmark pairs was zero.

Five representative routable OD pairs were then rerun and inspected at the complete node-path and directed-edge-path level. The cases span routes from approximately 8 meters to 12.26 kilometers.

| Check | Trip category | Distance | Directed edges | UCS nodes expanded | A* nodes expanded | Exact node/edge path match |
|---|---|---:|---:|---:|---:|---|
| R1 | School | 7.98 m | 2 | 18 | 5 | Yes |
| R2 | School | 617.09 m | 8 | 46 | 27 | Yes |
| R3 | Store | 2,006.78 m | 82 | 10,231 | 3,906 | Yes |
| R4 | Office | 3,977.44 m | 94 | 9,772 | 5,810 | Yes |
| R5 | Store | 12,260.47 m | 215 | 58,068 | 28,560 | Yes |

For all five inspected routes, UCS and A* produced identical generalized cost, physical distance, complete node sequence, and complete directed-edge sequence. This provides an explicit path-level check in addition to the aggregate optimal-cost benchmark.

The complete validation records, including serialized node and edge sequences, are stored in `results/routing/manual_route_path_checks.csv` and summarized in `results/routing/manual_route_path_checks.md`.

For the large experimental runs, one-to-many routing was used so that routes from a common origin could be computed efficiently across many destination records.
## 5. Baseline Routing Results

![Baseline routing by rider profile](figures/01_baseline_rider_profiles.png)

The four profiles produced meaningfully different baseline route choices.
| Rider profile | Mean generalized route cost | Mean route distance |
|---|---:|---:|
| Child | 5,960.77 | 2,541.03 m |
| Low-confidence adult | 6,087.54 | 2,543.75 m |
| Typical adult | 5,458.90 | 2,452.10 m |
| Experienced adult | 4,924.91 | 2,350.22 m |

The low-confidence and child profiles generally incurred greater generalized costs and slightly longer routes because they were more strongly penalized for using stressful road segments. Experienced riders accepted more stressful links and therefore obtained shorter physical routes on average.
These differences demonstrate why infrastructure ranking should not be based on a single generic cyclist model.
### 5.1 High-Stress Roads Carrying High Modeled Route Load

![Baseline high-stress roads carrying high modeled demand](figures/07_high_stress_high_demand_map.png)

**Figure 7. Baseline high-stress roads carrying high modeled route load.** The map shows LTS 3–4 road segments used by the typical-adult baseline routes and emphasizes segments at or above the 95th percentile of modeled baseline edge use. Among 13,696 used high-stress directed edges, the 95th-percentile threshold was a `path_count` of 136, highlighting 690 directed edges representing 654 physical edge pairs.

This visualization makes the geographic overlap between stressful infrastructure and substantial modeled bicycle-route use explicit. It complements the candidate-generation procedure by showing that high stress alone is not the prioritization criterion; the analysis is particularly interested in high-stress segments that also interact with meaningful modeled travel demand.

## 6. Candidate Generation
The candidate-generation stage screened the bicycle network for high-stress road segments with substantial modeled demand-weighted stress exposure.
Twenty candidates were retained for screening. The strongest ten were advanced to computationally expensive full-intervention simulations.
The top ten represented streets including:
- Chauncy Street;
- Cambridge Street;
- Hyde Park Avenue;
- Beacon Street;
- Dartmouth Street;
- Longwood Avenue;
- Pond Street;
- South Service Road;
- Columbia Road; and
- Massachusetts Avenue.
Nine of the ten fully simulated candidates had baseline LTS 3, while South Service Road had LTS 4.

![Candidate locations](figures/06_candidate_locations.png)

The geographic figure shows representative candidate locations and highlights projects selected in the final baseline optimized package.
## 7. Full Intervention Simulation
Candidate evaluation was not based solely on local properties such as segment demand or length.
For each of the top ten candidates:
- the candidate's LTS was reduced to 2;
- the corresponding rider-specific edge cost was recomputed;
- the complete modeled OD demand set was rerouted;
- intervention routes were compared with baseline routes; and
- demand-weighted generalized-cost reduction was calculated.
This provides an estimate of network-wide modeled benefit rather than simply measuring the improved edge itself.
No candidate was allowed to increase an optimal route's generalized cost. Network topology remained fixed, so interventions changed traversal cost rather than creating new links.
### 7.1 Example Before-and-After Route

![Before and after routing for the C001 Chauncy Street intervention](figures/08_before_after_route_example.png)

**Figure 8. Example before-and-after route under the C001 Chauncy Street intervention.** The example is a typical-adult home-to-office OD record with modeled demand 5. Its generalized route cost decreases from 9,148.81 to 9,073.39 after the Chauncy Street segment is improved from its baseline stress level to LTS 2.

The physical route simultaneously changes from 3,381.89 m and 101 directed edges to 3,744.08 m and 116 directed edges. The two solutions share 75 edges, while 26 edges occur only in the baseline route and 41 occur only in the intervention route. Thus, the post-intervention route is approximately 362.19 m longer but still has 75.42 lower generalized cost.

This example illustrates the purpose of stress-aware routing: an infrastructure improvement can change the preferred route even when the resulting path is physically longer, because the additional distance can be outweighed by lower modeled traffic stress.

### 7.2 Individual Candidate Ranking

![Candidate simulation ranking](figures/02_candidate_simulation_ranking.png)

The full-simulation ranking was:
| Rank | Candidate | Location | Mean generalized-cost reduction |
|---:|---|---|---:|
| 1 | C001 | Chauncy Street | 93,316.79 |
| 2 | C002 | Cambridge Street | 85,055.17 |
| 3 | C003 | Hyde Park Avenue | 75,082.18 |
| 4 | C004 | Beacon Street | 63,188.53 |
| 5 | C006 | Dartmouth Street | 52,581.37 |
| 6 | C007 | Longwood Avenue | 48,695.65 |
| 7 | C005 | Pond Street | 47,615.96 |
| 8 | C010 | South Service Road | 47,575.31 |
| 9 | C008 | Columbia Road | 41,016.96 |
| 10 | C009 | Massachusetts Avenue | 39,577.98 |

Chauncy Street was the strongest single intervention across the four baseline rider profiles.
The ranking also illustrates why full simulation matters. For example, a segment with large local modeled demand does not necessarily produce the largest network-wide reduction in generalized route cost after travelers are allowed to reroute.
## 8. Greedy Multi-Project Optimization
Selecting the five highest-ranked individual interventions would assume that their benefits are independent. In a transportation network, this assumption is not generally valid. Improving one segment can alter routes and therefore change the marginal value of subsequent improvements.
A greedy optimization procedure was therefore used.
At each step:
- all remaining candidates were temporarily added to the already-selected package one at a time;
- the complete OD dataset was rerouted for every rider profile;
- the total package benefit was recomputed;
- the marginal benefit relative to the previous package was calculated; and
- the remaining candidate with the largest marginal benefit was selected.
The optimization was constrained to a maximum of five projects. The original proposal contemplated either a project-count limit or a cumulative improved-road-length limit. The final implementation uses the project-count constraint because physical road length alone is not a credible proxy for implementation cost: projects of similar length can differ substantially in intersection treatment, right-of-way requirements, engineering complexity, and construction requirements. Because a credible project-specific construction-cost model was not available, cumulative candidate length is reported descriptively and used only as a lower-priority tie-breaker rather than imposed as a hard optimization budget.
### 8.1 Greedy Selection Sequence

![Greedy package progression](figures/03_greedy_package_progression.png)

The selected projects were:
| Step | Selected candidate | Package mean benefit | Marginal benefit |
|---:|---|---:|---:|
| 1 | C001 — Chauncy Street | 93,316.79 | 93,316.79 |
| 2 | C002 — Cambridge Street | 178,121.57 | 84,804.78 |
| 3 | C003 — Hyde Park Avenue | 253,261.05 | 75,139.48 |
| 4 | C004 — Beacon Street | 308,539.49 | 55,278.44 |
| 5 | C006 — Dartmouth Street | 361,774.05 | 53,234.57 |

The final package was therefore:
**C001 + C002 + C003 + C004 + C006**
Its cumulative candidate length was approximately 779.67 meters.
## 9. Final Package Effects by Rider Profile

![Final package benefit by rider profile](figures/04_final_package_by_profile.png)

The same infrastructure package produced different levels of modeled benefit across rider types.
| Rider profile | Generalized-cost reduction | Improved modeled demand | Mean distance change |
|---|---:|---:|---:|
| Child | 524,364.96 | 2,642 | -1.57 m |
| Low-confidence adult | 483,479.57 | 2,648 | -1.17 m |
| Typical adult | 320,866.11 | 2,342 | +1.35 m |
| Experienced adult | 118,385.58 | 1,995 | +0.73 m |

The largest generalized-cost benefits accrue to riders with stronger aversion to stressful streets.
Importantly, physical travel distance changes very little. For some profiles, the improved route is slightly longer in physical distance while still having substantially lower generalized cost.
This demonstrates that the principal modeled benefit is stress reduction rather than distance reduction. The infrastructure changes make lower-stress route choices more attractive without necessarily shortening the trip.
## 10. Robustness Analysis
Two sensitivity experiments were conducted.
### 10.1 Alternate OD Sample
A second fixed demand sample was generated using random seed 684 instead of the baseline seed 683 while preserving the same total demand and category totals.
The alternate sample was substantially different at the individual OD-pair level, providing a meaningful test of whether the results depended on one particular random sample.
### 10.2 Higher Rider Stress Aversion
A second experiment used more strongly stress-averse cost scenarios for every rider profile:
- child: scenario 5;
- low-confidence adult: scenario 10;
- typical adult: scenario 15;
- experienced adult: scenario 20.
Candidate simulations and the entire greedy optimization process were rerun under each robustness condition.
### 10.3 Stability Results

![Robustness summary](figures/05_robustness_summary.png)

| Robustness experiment | Spearman rank correlation | Top-5 overlap | Optimized package overlap |
|---|---:|---:|---:|
| Higher stress aversion | 0.467 | 3/5 | 3/5 |
| Alternate OD sample | 0.976 | 5/5 | 5/5 |

The alternate OD sample showed very strong stability.
Its optimized package was exactly:
**C001 + C002 + C003 + C004 + C006**
which is identical to the baseline package.
The alternate-sample package produced a mean generalized-cost reduction of 361,276.70, only 0.137% lower than the baseline value of 361,774.05.
This suggests that the identified priority package is not an artifact of the particular fixed OD sample used for the main experiment.
The higher-stress-aversion experiment was more sensitive. Its optimized package was:
**C001 + C006 + C002 + C005 + C008**
Three projects—C001, C002, and C006—were shared with the baseline five-project package.
The high-aversion experiment also had a lower candidate-rank Spearman correlation of approximately 0.467. This means infrastructure priorities change meaningfully when riders are assumed to penalize high-stress roads more strongly.
The numerical benefit magnitude from the high-aversion experiment should not be directly compared with baseline benefit because changing LTS weights changes the generalized-cost scale itself. Package composition and relative ranking are the more appropriate sensitivity measures for this experiment.
## 11. Discussion
Several conclusions emerge from the experiments.
First, infrastructure benefit is a network effect. A candidate's importance cannot be determined reliably from its local stress level or local demand alone. Full rerouting captures how an improvement changes the set of attractive routes across the network.
Second, lower-confidence riders receive the largest modeled benefits from the selected improvements. The final five-project package particularly benefits child and low-confidence profiles because higher-stress segments carry greater penalties for those riders.
Third, the strongest candidates are relatively stable to demand resampling. The alternate OD experiment reproduced the same top-five candidate set and the exact same optimized five-project package.
Fourth, rider-behavior assumptions matter substantially. More severe stress aversion changed both individual rankings and the final optimized package. This is not a failure of the framework; rather, it identifies an important planning uncertainty. Infrastructure priorities depend partly on whose routing preferences the system is intended to support.
Finally, the selected package primarily reduces modeled traffic stress rather than physical travel distance. The network intervention can therefore provide meaningful modeled benefit even when trip distance stays nearly constant.
## 12. Limitations
This study has several important limitations.
### 12.1 Modeled Demand
The OD dataset represents modeled demand rather than direct observed bicycle-trip counts. The results therefore describe modeled network effects and should not be interpreted as measured causal impacts on actual ridership.
### 12.2 Simplified Infrastructure Intervention
An intervention is modeled by reducing a candidate segment's LTS to 2. Real infrastructure projects vary greatly in design, construction feasibility, intersection treatment, safety performance, and resulting rider perception.
The simulation therefore represents an abstract improvement rather than a detailed engineering design.
### 12.3 No Construction Cost Model
The optimization constrains the number of projects to five rather than imposing a monetary budget. Candidate length is available, but road construction cost does not scale reliably with length alone.
A practical planning application should incorporate project-specific cost estimates and potentially maximize benefit per dollar.
### 12.4 Fixed Network Topology
The intervention analysis modifies stress and generalized cost on existing links. It does not add entirely new bicycle connections or alter the underlying topology.
Consequently, currently unreachable OD pairs remain unreachable.
### 12.5 Behavioral Assumptions
Rider profiles are represented through predetermined LTS weights. Actual cyclists exhibit heterogeneous preferences that may vary with age, trip purpose, time of day, infrastructure type, and other factors.
The robustness analysis demonstrates that results can change when these assumptions change.
### 12.6 Candidate Scope
The optimization operates on the generated candidate set rather than every theoretically possible infrastructure project in Greater Boston. The final package is therefore optimal only within the evaluated greedy candidate-selection framework, not a claim of globally optimal real-world investment.
## 13. Future Work
Several extensions would strengthen the framework.
First, project-specific construction-cost estimates could support budget-constrained optimization and benefit-per-dollar comparisons.
Second, observed bicycle counts, travel surveys, or GPS traces could be used to calibrate OD demand and rider stress preferences.
Third, candidate generation could be expanded to consider missing network links, intersection improvements, protected bicycle lanes, and corridor-scale interventions.
Fourth, demographic and equity variables could be integrated explicitly into the objective function so that infrastructure packages can be evaluated not only by total modeled benefit but also by the distribution of benefits across communities.
Finally, alternative optimization approaches could be compared with greedy selection, including integer programming, beam search, or other combinatorial optimization methods when computational resources permit.
## 14. Conclusion
This project presents a reproducible graph-based approach for identifying high-impact bicycle-network improvements in Greater Boston.
By combining Level of Traffic Stress, modeled travel demand, rider-specific routing preferences, optimal graph search, before-and-after intervention simulation, greedy package optimization, and robustness testing, the analysis moves beyond ranking stressful streets in isolation.
The baseline analysis identified a five-project package consisting of improvements on Chauncy Street, Cambridge Street, Hyde Park Avenue, Beacon Street, and Dartmouth Street. Together, these interventions produced a mean demand-weighted generalized-cost reduction of approximately 361,774 across the four modeled rider profiles.
The package was reproduced exactly under an independent fixed OD sample, providing strong evidence that the result is stable to demand resampling. At the same time, stronger assumptions about riders' aversion to traffic stress changed the infrastructure priorities, demonstrating that behavioral assumptions remain an important source of uncertainty.
Overall, the results show that network-wide routing analysis can provide a more informative basis for bicycle-infrastructure prioritization than stress, length, or demand measurements considered independently.
## Reproducibility
The project repository contains:
- experiment configuration files;
- UCS and A* routing implementations;
- rider-profile graph construction;
- baseline-routing scripts;
- candidate-generation methods;
- intervention-simulation scripts;
- greedy optimization;
- robustness experiments;
- tests;
- generated result tables; and
- final visualization scripts.
All reported numerical results are generated from committed experiment outputs in the results/ directory, while report figures are generated by scripts/create_final_figures.py.
