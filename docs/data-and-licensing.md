# Data and Licensing

## Recommended Data Sources

- OpenStreetMap for road network and bicycle-related tags
- Mapillary for street-level imagery and detections
- first-party 360 captures where possible
- city open data for speed limits, traffic restrictions, or infrastructure layers
- optional commercial imagery with explicit ML rights

## Important Restriction

Do not use Google Street View as the primary ML training source for this project.

The project should avoid training on content whose platform terms restrict use for machine learning or model improvement.

## Why Mapillary Fits

Mapillary is directly relevant because it provides:

- street-level imagery
- developer tooling
- traffic-sign and object detections
- related datasets that can support model development

## Licensing Policy for v1

- prefer open or explicitly licensed data sources
- keep source attribution per dataset
- separate training, validation, and derived artifacts by source
- document country-specific legal assumptions separately from model weights

## Data Quality Caveats

- OSM coverage varies by region
- speed-limit fields may be incomplete
- sidewalk and cycleway tags may be missing or inconsistent
- imagery freshness varies across cities
- legal riding rules are jurisdiction-specific

## Practical Rule

Use OSM + Mapillary + project-owned captures as the safe default stack for the MVP.
