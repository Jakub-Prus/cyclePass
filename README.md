# CyclePass

CyclePass is a bike-safe routing project built on top of multimodal road-segment scoring.

The goal is not just bike-lane detection or generic route finding. The system combines street-level imagery, OpenStreetMap attributes, and explicit policy rules to decide whether a road segment is realistically usable by bicycle, how comfortable it is, and whether it should be preferred or avoided when computing a route.

## Problem

Cyclists often get routed onto roads that are technically connected but practically unsafe or hostile, including high-speed roads and highway-like corridors with little or no bicycle protection.

Cycling suitability depends on more than what is visible in a single image. Legal access, speed limits, road class, sidewalks, cycleway tags, separation from traffic, and surface quality all matter.

CyclePass treats this as a road-segment classification and routing problem. Segment-level outputs are the foundation, but the user-facing product goal is to produce bike routes that avoid unsafe or uncomfortable situations rather than blindly follow the geometrically shortest path.

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

The 5-class list above is the canonical product taxonomy. The MVP uses a 4-class operational model that merges `legally allowed but uncomfortable` into `not suitable for cycling` for the initial release. That mapping should remain explicit everywhere the model, labels, or metrics are defined.

## Recommended Product Direction

- bike-safe routing API that prefers comfortable and legally rideable roads
- map QA tool for missing or inconsistent bicycle-related OSM data
- GIS scoring API for road segments as the routing foundation

The routing use case is the strongest product direction because it converts segment-level classification into immediate user value. The core promise is simple: do not send cyclists onto roads that a normal car-oriented map might consider acceptable but that are unsafe or unreasonable for most riders.

## MVP

Phase 1 is a city-scale pilot for comfort-aware bike routing using OpenStreetMap and a 4-class segment classifier.

Classes:

1. protected / dedicated bike infrastructure
2. low-stress mixed street
3. sidewalk/shared path usable by bike
4. not suitable for cycling

MVP mapping from the canonical taxonomy:

- dedicated/protected cycling space -> class 1
- calm mixed traffic street -> class 2
- rideable sidewalk/shared path -> class 3
- legally allowed but uncomfortable -> class 4
- not suitable / not allowed -> class 4

The first implementation should be hybrid:

- rule baseline from OSM tags
- vision model only for ambiguous rule outcomes
- class + confidence + explanation output
- routing graph that converts scored segments into bike-safe routes

## Minimal MVP Stack

The repository now includes a minimal product-shaped MVP with:

- `frontend/`: `React + Vite + TypeScript`
- `backend/`: `FastAPI`
- `scripts/`: small Python helper scripts

What it does:

- searches a place with Nominatim through the backend
- routes through a self-hosted GraphHopper instance built from a local OSM extract
- keeps CyclePass scoring and route explanations in the backend response
- supports click-to-inspect nearest routed edges through GraphHopper
- lets the user switch the map between street and satellite imagery for road inspection
- can open nearby Mapillary street imagery for an inspected road point when a Mapillary access token is configured
- keeps radius-based manual area inspection as an optional legacy Overpass-only tool
- scores each segment with explicit Python rules
- renders the scored road segments on a React map UI
- shows comfort score, allowed state, confidence, and rule trace

Near-term product extension:

- allow a rider to choose start and end points
- compute a route that avoids hostile roads such as highways and high-speed arterials without protection
- prefer protected, low-stress, or otherwise comfortable links even when they are not the raw shortest path in meters

## Target Production Architecture

For the longer-term clean architecture, CyclePass should separate geocoding, routing, scoring, and map overlays into distinct responsibilities:

- geocoding: keep Nominatim for now, with the option to self-host later
- routing: self-host GraphHopper or Valhalla instead of building request-time routes from public Overpass queries
- safety model: keep CyclePass scoring and comfort rules as the project-owned routing preference layer
- UI overlays: use optional local cached OSM data instead of depending on live Overpass responses for the map inspection path

This architecture keeps the product free of third-party routing fees while avoiding public Overpass rate limits in the core route-planning flow.

Free data used:

- OpenStreetMap tiles
- Nominatim geocoding
- local OpenStreetMap extracts imported into GraphHopper
- optional Overpass API road tags for legacy inspection only

## Run Locally

1. Create the backend environment:

   - `python -m venv .venv`
   - `.venv\\Scripts\\activate`
   - `pip install -r backend/requirements.txt`

2. Download GraphHopper and the default Wielkopolskie extract:

   - `python scripts/setup_graphhopper.py`

3. Import the routing graph once:

   - `python scripts/run_graphhopper.py --command import --xms 1g --xmx 2g`

4. Start GraphHopper:

   - `python scripts/run_graphhopper.py --command server --xms 1g --xmx 2g`

5. Start the backend API in a second terminal:

   - `python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8001`

6. Start the frontend in a third terminal:

   - `cd frontend`
   - `npm install`
   - `npm run dev`
   - Open `http://localhost:5173`

Notes:

- The backend expects GraphHopper at `http://127.0.0.1:8989` by default.
- Change the router URL with `CYCLEPASS_GRAPHHOPPER_URL`.
- To enable Mapillary lookup from the inspection panel, set `CYCLEPASS_MAPILLARY_ACCESS_TOKEN`.
- The default inspection UI now uses GraphHopper, not Overpass.
- Legacy area inspection is disabled by default so route planning does not make live Overpass requests.
- Re-enable that legacy endpoint only if needed with `CYCLEPASS_ENABLE_OVERPASS_INSPECTION=1`.

## Validation

Python checks:

- `python -m unittest backend.tests.test_scoring backend.tests.test_routing backend.tests.test_graphhopper backend.tests.test_osm_route_area`
- `python -m compileall backend/app backend/tests scripts`

Frontend build:

- `cd frontend && npm run build`

Sample local script:

- `python scripts/sample_analysis.py`

## Frontend-Only Evaluation

A fully frontend-only architecture is still possible for the rules-only demo, but it stops being the right choice once you want:

- stable API access without browser-side rate-limit pain
- reusable scoring logic shared across UI and scripts
- offline experiments or batch scoring
- later image-model integration

That is why this MVP uses React on the frontend and Python on the backend, while still staying free-data-only and easy to understand.

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
- optimize for cyclist-safe routing, not car-style shortest paths
