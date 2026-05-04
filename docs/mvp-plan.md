# MVP Plan

## Goal

Build a city-scale pilot that classifies road segments into four classes:

1. protected / dedicated bike infrastructure
2. low-stress mixed street
3. sidewalk/shared path usable by bike
4. not suitable for cycling

## Scope

Inputs:

- OpenStreetMap
- Mapillary
- optional local speed-limit data where OSM is incomplete

Outputs:

- class
- confidence
- explanation

## Recommended MVP Strategy

Start with a two-stage system:

1. rule-based baseline from OSM tags
2. vision model only for ambiguous segments

Examples:

- `cycleway=track` -> likely class 1
- `highway=residential` and `maxspeed<=30` -> likely class 2
- arterial at `60 km/h` with no bike infrastructure -> likely class 4
- unclear or conflicting cases -> send to image model

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

### Phase 2

- `0-100` comfort score
- bicycle route optimization
- missing-map-data detection
- region-specific legality rules

## Success Criteria

- segment-level predictions are explainable
- uncertainty is surfaced explicitly
- rules baseline handles easy cases reliably
- vision model improves ambiguous cases
- system is usable for routing or QA workflows
