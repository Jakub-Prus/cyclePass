from __future__ import annotations

import logging
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .graphhopper import GraphHopperRouteError, build_graphhopper_inspection, build_graphhopper_route
from .mapillary import MapillaryLookupError, find_nearest_mapillary_image
from .osm import analyze_area, search_location
from .scoring import classify_way, summarize_segments

FRONTEND_DEV_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
SIDEWALK_ELIGIBLE_HIGHWAYS = {"primary", "primary_link", "trunk", "trunk_link"}
SIDEWALK_PRESENT_VALUES = {"yes", "both", "left", "right"}
ENABLE_OVERPASS_ANALYSIS = os.getenv("CYCLEPASS_ENABLE_OVERPASS_INSPECTION", "0") == "1"
OVERPASS_DISABLED_MESSAGE = (
    "Area inspection is disabled in self-hosted mode. "
    "Set CYCLEPASS_ENABLE_OVERPASS_INSPECTION=1 to re-enable the legacy Overpass inspection endpoint."
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
LOGGER = logging.getLogger("cyclepass.api")

app = FastAPI(title="CyclePass API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_DEV_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    lat: float
    lon: float
    radius_m: int = Field(ge=150, le=900)


class RouteRequest(BaseModel):
    start_lat: float
    start_lon: float
    end_lat: float
    end_lon: float


class InspectRequest(BaseModel):
    lat: float
    lon: float


class MapillaryRequest(BaseModel):
    lat: float
    lon: float


@app.get("/api/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "routing_provider": "graphhopper",
        "overpass_inspection": "enabled" if ENABLE_OVERPASS_ANALYSIS else "disabled",
    }


@app.get("/api/search")
def search(query: str) -> list[dict[str, float | str]]:
    if not query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    try:
        LOGGER.info("Search request started query=%r", query)
        return search_location(query)
    except Exception as error:  # pragma: no cover - network dependent
        LOGGER.exception("Search request failed query=%r", query)
        raise HTTPException(status_code=502, detail=f"search failed: {error}") from error


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest) -> dict[str, object]:
    if not ENABLE_OVERPASS_ANALYSIS:
        raise HTTPException(status_code=503, detail=OVERPASS_DISABLED_MESSAGE)

    try:
        LOGGER.info(
            "Area analysis started lat=%.6f lon=%.6f radius_m=%s",
            payload.lat,
            payload.lon,
            payload.radius_m,
        )
        raw_segments = analyze_area(payload.lat, payload.lon, payload.radius_m)
    except Exception as error:  # pragma: no cover - network dependent
        LOGGER.exception(
            "Area analysis failed lat=%.6f lon=%.6f radius_m=%s",
            payload.lat,
            payload.lon,
            payload.radius_m,
        )
        raise HTTPException(status_code=502, detail=f"analysis failed: {error}") from error

    segments = []
    for way in raw_segments:
        segments.extend(build_output_segments(way))

    LOGGER.info(
        "Area analysis completed lat=%.6f lon=%.6f radius_m=%s ways=%s segments=%s",
        payload.lat,
        payload.lon,
        payload.radius_m,
        len(raw_segments),
        len(segments),
    )

    return {
        "center": {"lat": payload.lat, "lon": payload.lon},
        "radius_m": payload.radius_m,
        "summary": summarize_segments(segments),
        "segments": segments,
    }


@app.post("/api/route")
def route(payload: RouteRequest) -> dict[str, object]:
    start = {"lat": payload.start_lat, "lon": payload.start_lon}
    end = {"lat": payload.end_lat, "lon": payload.end_lon}

    try:
        LOGGER.info(
            "Route analysis started start=(%.6f, %.6f) end=(%.6f, %.6f)",
            payload.start_lat,
            payload.start_lon,
            payload.end_lat,
            payload.end_lon,
        )
        route_result = build_graphhopper_route(start=start, end=end)
    except GraphHopperRouteError as error:
        LOGGER.exception(
            "Route analysis failed start=(%.6f, %.6f) end=(%.6f, %.6f)",
            payload.start_lat,
            payload.start_lon,
            payload.end_lat,
            payload.end_lon,
        )
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    LOGGER.info(
        "Route analysis completed start=(%.6f, %.6f) end=(%.6f, %.6f) segments=%s routing_mode=%s total_length_m=%.1f avg_comfort=%s",
        payload.start_lat,
        payload.start_lon,
        payload.end_lat,
        payload.end_lon,
        len(route_result["segments"]),
        route_result["routing_mode"],
        route_result["total_length_m"],
        route_result["average_comfort"],
    )

    return {
        "start": route_result["start"],
        "end": route_result["end"],
        "snapped_start": route_result["snapped_start"],
        "snapped_end": route_result["snapped_end"],
        "routing_mode": route_result["routing_mode"],
        "total_length_m": route_result["total_length_m"],
        "average_comfort": route_result["average_comfort"],
        "explanation": route_result["explanation"],
        "segments": route_result["segments"],
        "geometry": route_result["geometry"],
    }


@app.post("/api/inspect")
def inspect(payload: InspectRequest) -> dict[str, object]:
    point = {"lat": payload.lat, "lon": payload.lon}

    try:
        LOGGER.info("Inspection started point=(%.6f, %.6f)", payload.lat, payload.lon)
        inspection_result = build_graphhopper_inspection(point)
    except GraphHopperRouteError as error:
        LOGGER.exception("Inspection failed point=(%.6f, %.6f)", payload.lat, payload.lon)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    LOGGER.info(
        "Inspection completed point=(%.6f, %.6f) snapped=(%.6f, %.6f) segment=%s class=%s",
        payload.lat,
        payload.lon,
        inspection_result["snapped_point"]["lat"],
        inspection_result["snapped_point"]["lon"],
        inspection_result["segment"]["id"],
        inspection_result["segment"]["score"]["bike_crossable_class"],
    )

    return inspection_result


@app.post("/api/mapillary")
def mapillary_lookup(payload: MapillaryRequest) -> dict[str, object]:
    point = {"lat": payload.lat, "lon": payload.lon}

    try:
        LOGGER.info("Mapillary lookup started point=(%.6f, %.6f)", payload.lat, payload.lon)
        result = find_nearest_mapillary_image(point)
    except MapillaryLookupError as error:
        LOGGER.exception("Mapillary lookup failed point=(%.6f, %.6f)", payload.lat, payload.lon)
        raise HTTPException(status_code=error.status_code, detail=str(error)) from error

    LOGGER.info(
        "Mapillary lookup completed point=(%.6f, %.6f) image_id=%s distance_m=%.1f",
        payload.lat,
        payload.lon,
        result["image_id"],
        result["distance_m"],
    )
    return {
        "requested_point": point,
        **result,
    }


def build_output_segments(way: dict[str, object]) -> list[dict[str, object]]:
    output_segments = [serialize_segment(way)]

    if should_add_sidewalk_overlay(way.get("tags", {})):
        output_segments.append(serialize_segment(build_sidewalk_overlay_segment(way)))

    return output_segments


def serialize_segment(way: dict[str, object]) -> dict[str, object]:
    tags = way.get("tags", {})
    score = classify_way(tags)
    return {
        "id": way["id"],
        "parent_way_id": way.get("parent_way_id"),
        "name": score["normalized_tags"]["name"],
        "geometry": way["geometry"],
        "length_m": way.get("length_m", 0.0),
        "tags": tags,
        "score": score,
    }


def should_add_sidewalk_overlay(tags: dict[str, str]) -> bool:
    return tags.get("highway") in SIDEWALK_ELIGIBLE_HIGHWAYS and tags.get("sidewalk") in SIDEWALK_PRESENT_VALUES


def build_sidewalk_overlay_segment(way: dict[str, object]) -> dict[str, object]:
    source_tags = way.get("tags", {})
    road_name = source_tags.get("name") or source_tags.get("ref") or "Unnamed road"

    return {
        "id": f"{way['id']}-sidewalk",
        "parent_way_id": way.get("parent_way_id") or way["id"],
        "geometry": way["geometry"],
        "tags": {
            "highway": "footway",
            "footway": "sidewalk",
            "name": f"Sidewalk along {road_name}",
            "surface": source_tags.get("surface", ""),
            "lit": source_tags.get("lit", ""),
            "sidewalk": source_tags.get("sidewalk", ""),
            "cyclepass:derived": "sidewalk_overlay",
            "cyclepass:source_highway": source_tags.get("highway", ""),
        },
    }
