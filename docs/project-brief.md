# Project Brief

## Summary

CyclePass classifies whether a road segment is realistically usable by bicycle and how comfortable it is for different riders.

This is better framed as cycling passability / rideability classification than bike-lane detection. The core unit is a short road segment rather than a full road or a single image.

## Why This Project Matters

Existing work tends to focus on one narrow task:

- bikeability scoring from imagery
- bike-lane detection
- traffic-sign or object detection
- bikeway-network extraction

CyclePass combines these into a more useful product: a multimodal road-segment scorer that reasons over both visual and map-based evidence.

## Inputs

For each road segment:

- street-level imagery from Mapillary or first-party captures
- OpenStreetMap tags such as `highway=*`, `cycleway=*`, `sidewalk=*`, `bicycle=*`, `maxspeed=*`
- optional satellite tiles
- optional slope / elevation
- optional traffic volume proxies
- optional lane count and intersection context

## Outputs

- `bike_allowed`
- `bike_comfort`
- `bike_crossable_class`
- `confidence`
- explanation and evidence fields

## Suggested Classification Taxonomy

Canonical product classes:

1. dedicated/protected cycling space
2. calm mixed traffic street
3. rideable sidewalk/shared path
4. legally allowed but uncomfortable
5. not suitable / not allowed

MVP operational classes:

1. protected / dedicated bike infrastructure
2. low-stress mixed street
3. sidewalk/shared path usable by bike
4. not suitable for cycling

MVP mapping:

- canonical class 1 -> MVP class 1
- canonical class 2 -> MVP class 2
- canonical class 3 -> MVP class 3
- canonical classes 4 and 5 -> MVP class 4

## Annotation Dimensions

Do not start with only a binary crossable label. Capture these dimensions first:

- legally rideable
- physically rideable
- comfortable for an average cyclist
- safe for child / novice riders
- facility type
- confidence

Then derive product-facing labels from those dimensions.

The derivation should preserve the distinction between legal rideability, physical traversability, and comfort/safety class.

## Risks

- legality varies by country and city
- sidewalks may be physically usable but legally forbidden
- speed-limit coverage may be incomplete
- a single image can miss hidden barriers or width constraints
- intersections are harder than mid-block segments
- narrowness and safety are partly subjective without geometry estimation

## Recommendation

Start with a hybrid rule-based + ML MVP:

- OSM-driven baseline
- image model only for ambiguous rule outcomes
- explainable outputs
- country-specific rules added later
