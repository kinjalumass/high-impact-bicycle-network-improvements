# Manual UCS/A* Route Checks

Five representative routable OD pairs were selected from the deterministic routing benchmark. UCS and A* were rerun on the same baseline graph and their complete node and directed-edge sequences were compared.

## R1

- Origin: `11958863758`
- Destination: `11958863748`
- Category: `home_school`
- Generalized route cost: 798.434364
- Physical route distance: 7.984 m
- Directed edges: 2
- UCS nodes expanded: 18
- A* nodes expanded: 5
- Exact node-path match: **True**
- Exact edge-path match: **True**

Path preview:

`11958863758 -> 11958863759 -> 11958863748`

## R2

- Origin: `61366624`
- Destination: `61520462`
- Category: `home_school`
- Generalized route cost: 925.641501
- Physical route distance: 617.094 m
- Directed edges: 8
- UCS nodes expanded: 46
- A* nodes expanded: 27
- Exact node-path match: **True**
- Exact edge-path match: **True**

Path preview:

`61366624 -> 61362399 -> 61493340 -> 61363704 -> 61363698 -> 61367224 -> 61367223 -> 61367225 -> 61520462`

## R3

- Origin: `7893597418`
- Destination: `11630735700`
- Category: `home_store`
- Generalized route cost: 4655.385813
- Physical route distance: 2006.781 m
- Directed edges: 82
- UCS nodes expanded: 10,231
- A* nodes expanded: 3,906
- Exact node-path match: **True**
- Exact edge-path match: **True**

Path preview:

`7893597418 -> 7893597419 -> 71954205 -> 5458392910 -> 6287676998 -> ... -> 5006182988 -> 286557423 -> 6124562825 -> 7628612179 -> 11630735700`

## R4

- Origin: `13064174535`
- Destination: `327375517`
- Category: `home_office`
- Generalized route cost: 36434.472297
- Physical route distance: 3977.439 m
- Directed edges: 94
- UCS nodes expanded: 9,772
- A* nodes expanded: 5,810
- Exact node-path match: **True**
- Exact edge-path match: **True**

Path preview:

`13064174535 -> 7777357947 -> 7610624926 -> 7610624931 -> 61344121 -> ... -> 61342086 -> 7715496472 -> 61506639 -> 7650883861 -> 327375517`

## R5

- Origin: `61340781`
- Destination: `7862026670`
- Category: `home_store`
- Generalized route cost: 15131.029167
- Physical route distance: 12260.469 m
- Directed edges: 215
- UCS nodes expanded: 58,068
- A* nodes expanded: 28,560
- Exact node-path match: **True**
- Exact edge-path match: **True**

Path preview:

`61340781 -> 12644451204 -> 61340619 -> 10771093828 -> 61340818 -> ... -> 7862026668 -> 61406203 -> 5854303710 -> 61450865 -> 7862026670`
