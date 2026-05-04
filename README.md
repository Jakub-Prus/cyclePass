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

The 5-class list above is the canonical product taxonomy. The MVP uses a 4-class operational model that merges `legally allowed but uncomfortable` into `not suitable for cycling` for the initial release. That mapping should remain explicit everywhere the model, labels, or metrics are defined.

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

## Minimal MVP Stack

The repository now includes a minimal product-shaped MVP with:

- `frontend/`: `React + Vite + TypeScript`
- `backend/`: `FastAPI`
- `scripts/`: small Python helper scripts

What it does:

- searches a place with Nominatim through the backend
- fetches nearby OSM roads from Overpass through the backend
- scores each segment with explicit Python rules
- renders the scored road segments on a React map UI
- shows comfort score, allowed state, confidence, and rule trace

Free data used:

- OpenStreetMap tiles
- Nominatim geocoding
- Overpass API road tags

## Run Locally

Backend:

1. `python -m venv .venv`
2. `.venv\\Scripts\\activate`
3. `pip install -r backend/requirements.txt`
4. `uvicorn backend.app.main:app --reload --port 8001`

Frontend:

1. `cd frontend`
2. `npm install`
3. `npm run dev`
4. Open `http://localhost:5173`

## Validation

Python rule checks:

- `python -m unittest backend.tests.test_scoring`

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
