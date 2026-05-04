# CyclePass

CyclePass is a multimodal road-segment scoring project for cycling passability and rideability classification.

The goal is not just bike-lane detection. The system combines street-level imagery, OpenStreetMap attributes, and optional spatial signals to decide whether a road segment is realistically usable by bicycle.

## Problem

Cycling suitability depends on more than what is visible in a single image. Legal access, speed limits, road class, sidewalks, cycleway tags, separation from traffic, and surface quality all matter.

CyclePass treats this as a road-segment classification problem with structured outputs instead of a single yes/no label.

## Proposed Outputs

- `bike_allowed`: `yes | no | uncertain`
- `bike_comfort`: `0-100`
- `bike_crossable_class`:
  - dedicated/protected cycling space
  - calm mixed traffic street
  - rideable sidewalk/shared path
  - legally allowed but uncomfortable
  - not suitable / not allowed
- `confidence`
- explanation fields derived from map, image, and rules signals

## Recommended Product Direction

- GIS scoring API for road segments
- Map QA tool for missing or inconsistent bicycle-related OSM data
- Routing engine feature for bicycle route optimization

The routing use case is the strongest commercial direction because it converts segment-level classification into user value immediately.

## MVP

Phase 1 is a city-scale pilot with a 4-class classifier using OpenStreetMap and Mapillary.

Classes:

1. protected / dedicated bike infrastructure
2. low-stress mixed street
3. sidewalk/shared path usable by bike
4. not suitable for cycling

The first implementation should be hybrid:

- rule baseline from OSM tags
- vision model only for ambiguous segments
- class + confidence + explanation output

## Repository Docs

- [Project Brief](docs/project-brief.md)
- [Architecture](docs/architecture.md)
- [Data Model](docs/data-model.md)
- [MVP Plan](docs/mvp-plan.md)
- [Data and Licensing](docs/data-and-licensing.md)

## Initial Principles

- use OSM + Mapillary + explicit rules first
- avoid training on Google Street View content
- make legality country-aware
- make outputs uncertainty-aware
- prefer explainable hybrid models over pure vision-only classification
