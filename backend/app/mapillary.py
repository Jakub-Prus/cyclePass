from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .routing import distance_m

MAPILLARY_GRAPH_API_URL = "https://graph.mapillary.com/images"
MAPILLARY_WEB_APP_URL = "https://www.mapillary.com/app/"
MAPILLARY_ACCESS_TOKEN = os.getenv("CYCLEPASS_MAPILLARY_ACCESS_TOKEN", "").strip()
MAPILLARY_TIMEOUT_SECONDS = float(os.getenv("CYCLEPASS_MAPILLARY_TIMEOUT_SECONDS", "12"))
MAPILLARY_SEARCH_LIMIT = 5
MAPILLARY_SEARCH_RADII_M = (20.0, 45.0)
MAPILLARY_IMAGE_FIELDS = (
    "id",
    "captured_at",
    "computed_geometry",
    "thumb_1024_url",
)
EARTH_METERS_PER_DEGREE_LAT = 111_320.0


class MapillaryLookupError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def ensure_mapillary_is_configured() -> None:
    if MAPILLARY_ACCESS_TOKEN:
        return

    raise MapillaryLookupError(
        "Mapillary is not configured. Set CYCLEPASS_MAPILLARY_ACCESS_TOKEN to enable imagery lookup.",
        503,
    )


def find_nearest_mapillary_image(point: dict[str, float]) -> dict[str, Any]:
    ensure_mapillary_is_configured()

    best_match: dict[str, Any] | None = None
    best_distance_m = float("inf")

    for radius_m in MAPILLARY_SEARCH_RADII_M:
        for image in fetch_images_in_bbox(point, radius_m):
            geometry = image.get("computed_geometry")
            candidate_point = parse_point_geometry(geometry)
            if candidate_point is None:
                continue

            candidate_distance_m = distance_m(point, candidate_point)
            if candidate_distance_m >= best_distance_m:
                continue

            best_distance_m = candidate_distance_m
            best_match = image

        if best_match is not None:
            break

    if best_match is None:
        raise MapillaryLookupError("No nearby Mapillary imagery was found for this inspection point.", 404)

    image_id = str(best_match["id"])
    geometry = parse_point_geometry(best_match.get("computed_geometry"))
    if geometry is None:
        raise MapillaryLookupError("Mapillary returned an image without usable geometry.", 502)

    return {
        "image_id": image_id,
        "captured_at": best_match.get("captured_at"),
        "thumb_1024_url": best_match.get("thumb_1024_url"),
        "viewer_url": f"{MAPILLARY_WEB_APP_URL}?pKey={urllib.parse.quote(image_id)}",
        "distance_m": round(best_distance_m, 1),
        "location": geometry,
    }


def fetch_images_in_bbox(point: dict[str, float], radius_m: float) -> list[dict[str, Any]]:
    bbox = build_bbox(point, radius_m)
    params = urllib.parse.urlencode(
        {
            "access_token": MAPILLARY_ACCESS_TOKEN,
            "fields": ",".join(MAPILLARY_IMAGE_FIELDS),
            "bbox": ",".join(format(coordinate, ".7f") for coordinate in bbox),
            "limit": str(MAPILLARY_SEARCH_LIMIT),
        }
    )
    request = urllib.request.Request(
        f"{MAPILLARY_GRAPH_API_URL}?{params}",
        headers={"Accept": "application/json"},
        method="GET",
    )

    try:
        with urllib.request.urlopen(request, timeout=MAPILLARY_TIMEOUT_SECONDS) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        raise MapillaryLookupError(read_mapillary_error_message(error), 502) from error
    except urllib.error.URLError as error:
        raise MapillaryLookupError(f"Mapillary is unavailable: {error.reason}", 502) from error

    data = body.get("data", [])
    if not isinstance(data, list):
        raise MapillaryLookupError("Mapillary returned an invalid images response.", 502)

    return [image for image in data if isinstance(image, dict)]


def build_bbox(point: dict[str, float], radius_m: float) -> tuple[float, float, float, float]:
    latitude_delta = radius_m / EARTH_METERS_PER_DEGREE_LAT
    longitude_scale = max(0.0001, math_cos_latitude(point["lat"]))
    longitude_delta = radius_m / (EARTH_METERS_PER_DEGREE_LAT * longitude_scale)
    return (
        point["lon"] - longitude_delta,
        point["lat"] - latitude_delta,
        point["lon"] + longitude_delta,
        point["lat"] + latitude_delta,
    )


def parse_point_geometry(raw_geometry: Any) -> dict[str, float] | None:
    if not isinstance(raw_geometry, dict):
        return None

    if raw_geometry.get("type") != "Point":
        return None

    coordinates = raw_geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return None

    lon, lat = coordinates[:2]
    return {"lat": float(lat), "lon": float(lon)}


def read_mapillary_error_message(error: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(error.read().decode("utf-8"))
    except Exception:
        return f"Mapillary lookup failed with HTTP {error.code}."

    if isinstance(body.get("error"), dict):
        message = body["error"].get("message")
        if isinstance(message, str) and message.strip():
            return message

    return f"Mapillary lookup failed with HTTP {error.code}."


def math_cos_latitude(latitude: float) -> float:
    from math import cos, radians

    return cos(radians(latitude))
