from __future__ import annotations

import json
import urllib.parse
import urllib.request
from typing import Any

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SECONDS = 25
WAY_FETCH_LIMIT = 250
ROAD_FILTER = "|".join(
    [
        "cycleway",
        "residential",
        "living_street",
        "service",
        "unclassified",
        "tertiary",
        "secondary",
        "primary",
        "trunk",
        "path",
        "footway",
        "pedestrian",
        "track",
    ]
)
REQUEST_HEADERS = {
    "Accept": "application/json",
    "User-Agent": "CyclePassMvp/0.1 (+https://github.com/Jakub-Prus/cyclePass)",
}


def search_location(query: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "format": "jsonv2",
            "limit": 5,
            "q": query,
        }
    )
    request = urllib.request.Request(f"{NOMINATIM_URL}?{params}", headers=REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=OVERPASS_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))

    return [
        {
            "display_name": item["display_name"],
            "lat": float(item["lat"]),
            "lon": float(item["lon"]),
        }
        for item in data
    ]


def analyze_area(lat: float, lon: float, radius_m: int) -> list[dict[str, Any]]:
    query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
way(around:{radius_m},{lat},{lon})["highway"~"{ROAD_FILTER}"];
out tags geom;
"""
    request = urllib.request.Request(
        OVERPASS_URL,
        data=query.encode("utf-8"),
        headers={
            **REQUEST_HEADERS,
            "Content-Type": "text/plain;charset=UTF-8",
        },
        method="POST",
    )

    with urllib.request.urlopen(request, timeout=OVERPASS_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))

    return [
        element
        for element in data.get("elements", [])
        if element.get("type") == "way" and isinstance(element.get("geometry"), list)
    ][:WAY_FETCH_LIMIT]
