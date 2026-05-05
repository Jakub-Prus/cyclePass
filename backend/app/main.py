from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .osm import analyze_area, analyze_route_area, search_location
from .routing import build_route
from .scoring import classify_way, summarize_segments

FRONTEND_DEV_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]
SIDEWALK_ELIGIBLE_HIGHWAYS = {"primary", "primary_link", "trunk", "trunk_link"}
SIDEWALK_PRESENT_VALUES = {"yes", "both", "left", "right"}

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
    radius_m: int = Field(ge=300, le=3000)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/search")
def search(query: str) -> list[dict[str, float | str]]:
    if not query.strip():
        raise HTTPException(status_code=400, detail="query is required")

    try:
        return search_location(query)
    except Exception as error:  # pragma: no cover - network dependent
        raise HTTPException(status_code=502, detail=f"search failed: {error}") from error


@app.post("/api/analyze")
def analyze(payload: AnalyzeRequest) -> dict[str, object]:
    try:
        raw_segments = analyze_area(payload.lat, payload.lon, payload.radius_m)
    except Exception as error:  # pragma: no cover - network dependent
        raise HTTPException(status_code=502, detail=f"analysis failed: {error}") from error

    segments = []
    for way in raw_segments:
        segments.extend(build_output_segments(way))

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
        raw_segments = analyze_route_area(start, end)
    except Exception as error:  # pragma: no cover - network dependent
        raise HTTPException(status_code=502, detail=f"route analysis failed: {error}") from error

    segments = []
    for way in raw_segments:
        segments.extend(build_output_segments(way))

    try:
        route_result = build_route(
            segments,
            start=start,
            end=end,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return {
        "start": route_result["start"],
        "end": route_result["end"],
        "snapped_start": route_result["snapped_start"],
        "snapped_end": route_result["snapped_end"],
        "routing_mode": route_result["routing_mode"],
        "radius_m": payload.radius_m,
        "total_length_m": route_result["total_length_m"],
        "average_comfort": route_result["average_comfort"],
        "explanation": route_result["explanation"],
        "segments": route_result["segments"],
        "geometry": route_result["geometry"],
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
