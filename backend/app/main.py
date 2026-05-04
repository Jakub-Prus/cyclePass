from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .osm import analyze_area, search_location
from .scoring import classify_way, summarize_segments

FRONTEND_DEV_ORIGINS = [
    "http://127.0.0.1:5173",
    "http://localhost:5173",
]

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
        score = classify_way(way.get("tags"))
        segments.append(
            {
                "id": way["id"],
                "name": score["normalized_tags"]["name"],
                "geometry": way["geometry"],
                "tags": way.get("tags", {}),
                "score": score,
            }
        )

    return {
        "center": {"lat": payload.lat, "lon": payload.lon},
        "radius_m": payload.radius_m,
        "summary": summarize_segments(segments),
        "segments": segments,
    }
