# MVP Plan

## Goal

Build a city-scale pilot that helps a rider find the best bike route between two points while avoiding roads that are unsafe, hostile, or unsuitable for cycling.

That requires classifying road segments into four classes:

1. protected / dedicated bike infrastructure
2. low-stress mixed street
3. sidewalk/shared path usable by bike
4. not suitable for cycling

These are MVP operational classes derived from the canonical 5-class product taxonomy. For Phase 1, `legally allowed but uncomfortable` and `not suitable / not allowed` are merged into class 4.

## Scope

Inputs:

- OpenStreetMap
- Mapillary
- optional local speed-limit data where OSM is incomplete

Outputs:

- segment class
- confidence
- explanation
- route recommendation
- route-level explanation

## Recommended MVP Strategy

Start with a two-stage system:

1. rule-based baseline from OSM tags
2. vision model only for ambiguous segments
3. routing graph built from scored segments
4. comfort-aware shortest-path search between origin and destination

Examples:

- `cycleway=track` -> likely class 1
- `highway=residential` and `maxspeed<=30` -> likely class 2
- arterial at `60 km/h` with no bike infrastructure -> likely class 4
- unclear or conflicting cases -> send to image model

Routing interpretation:

- segments that are class 4 because they are hostile or effectively unsafe should be excluded or near-excluded from routing
- segments that are legal but uncomfortable should remain available only as costly fallbacks
- protected and low-stress segments should be preferred even when the route is slightly longer in meters

## Annotation Strategy

Target an initial dataset of `5k-20k` segments.

Sampling should include:

- residential streets
- collectors
- arterials
- sidewalks
- industrial roads
- suburban roads
- intersections
- day/night and varied weather when possible

Annotators should see:

- map snippet
- `2-4` street-level views
- key OSM tags

## Phases

### Phase 1

- city-scale pilot
- 4-class classifier
- OSM + Mapillary integration
- web map with scores and explanations
- route graph over nearby scored segments
- start/end route request
- route rendering with route summary and reasoning

### Phase 2

- stronger `0-100` comfort score calibration
- city-scale and corridor-scale bicycle route optimization
- missing-map-data detection
- region-specific legality rules
- route alternatives and rider profile tuning

## Success Criteria

- segment-level predictions are explainable, with stored rule traces or top contributing signals for at least `95%` of scored segments
- uncertainty is surfaced explicitly, with an abstention or `uncertain` path for low-confidence segments
- the labeled evaluation set uses fixed train/validation/test splits with geography held out to reduce leakage
- MVP 4-class macro F1 on the held-out test set is at least `0.70`
- no individual MVP class has F1 below `0.60`
- calibration error is tracked and reviewed before release
- the escalated vision path outperforms the rules-only baseline on the ambiguous subset
- the router should not choose highway or highway-like segments unless protected bicycle infrastructure is explicitly present
- at least one downstream benchmark is defined:
  - routing: preferred-route agreement against curated bicycle routes
  - routing safety: rate of hostile-segment inclusion on benchmark routes
  - QA: precision at top-k for likely missing or inconsistent OSM bike tags
