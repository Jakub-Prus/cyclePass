from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .routing import build_route_explanation, distance_m, is_route_candidate, nearest_point_on_polyline
from .scoring import classify_way

LOGGER = logging.getLogger("cyclepass.graphhopper")

GRAPHHOPPER_BASE_URL = os.getenv("CYCLEPASS_GRAPHHOPPER_URL", "http://127.0.0.1:8989").rstrip("/")
GRAPHHOPPER_ROUTE_URL = f"{GRAPHHOPPER_BASE_URL}/route"
GRAPHHOPPER_NEAREST_URL = f"{GRAPHHOPPER_BASE_URL}/nearest"
GRAPHHOPPER_TIMEOUT_SECONDS = float(os.getenv("CYCLEPASS_GRAPHHOPPER_TIMEOUT_SECONDS", "20"))
GRAPHHOPPER_PROFILE = os.getenv("CYCLEPASS_GRAPHHOPPER_PROFILE", "cyclepass_bike")
INSPECTION_PROBE_DISTANCE_M = 8.0
GRAPH_ROUTE_DETAIL_NAMES = [
    "edge_id",
    "street_name",
    "road_class",
    "road_environment",
    "max_speed",
    "surface",
    "smoothness",
    "bike_network",
    "bike_access",
    "bike_priority",
    "get_off_bike",
    "lanes",
]
JSON_HEADERS = {
    "Accept": "application/json",
    "Content-Type": "application/json",
}
MISSING_DETAIL_VALUE = "MISSING"
UNKNOWN_STREET_NAME = "Unnamed segment"


class GraphHopperRouteError(Exception):
    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


def build_graphhopper_route(start: dict[str, float], end: dict[str, float]) -> dict[str, Any]:
    payload = build_route_payload(
        [
            [start["lon"], start["lat"]],
            [end["lon"], end["lat"]],
        ]
    )
    LOGGER.info(
        "Requesting GraphHopper route start=(%.6f, %.6f) end=(%.6f, %.6f) profile=%s",
        start["lat"],
        start["lon"],
        end["lat"],
        end["lon"],
        GRAPHHOPPER_PROFILE,
    )
    data = request_graphhopper_json(GRAPHHOPPER_ROUTE_URL, payload)
    return build_route_result_from_graphhopper(data, start=start, end=end)


def build_graphhopper_inspection(point: dict[str, float]) -> dict[str, Any]:
    snapped_point = fetch_graphhopper_nearest(point)
    probe_target = offset_point(point, east_m=INSPECTION_PROBE_DISTANCE_M, north_m=INSPECTION_PROBE_DISTANCE_M / 2)
    route_result = build_graphhopper_route(start=point, end=probe_target)
    return build_inspection_result(point, snapped_point, route_result)


def build_route_payload(points: list[list[float]]) -> dict[str, Any]:
    return {
        "points": points,
        "profile": GRAPHHOPPER_PROFILE,
        "points_encoded": False,
        "instructions": False,
        "calc_points": True,
        "details": GRAPH_ROUTE_DETAIL_NAMES,
        "locale": "en",
    }


def request_graphhopper_json(url: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers=JSON_HEADERS,
        method="GET" if payload is None else "POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=GRAPHHOPPER_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        message = read_graphhopper_error_message(error)
        LOGGER.error("GraphHopper request failed url=%s status=%s message=%s", url, error.code, message)
        raise GraphHopperRouteError(message, 400 if error.code < 500 else 502) from error
    except urllib.error.URLError as error:
        LOGGER.exception("GraphHopper network error url=%s reason=%s", url, error.reason)
        raise GraphHopperRouteError(f"GraphHopper is unavailable: {error.reason}", 502) from error


def read_graphhopper_error_message(error: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(error.read().decode("utf-8"))
    except Exception:
        return f"GraphHopper routing failed with HTTP {error.code}."

    if isinstance(body.get("message"), str) and body["message"].strip():
        return body["message"]

    hints = body.get("hints", [])
    if hints:
        hint_messages = [hint.get("message", "").strip() for hint in hints if isinstance(hint, dict)]
        joined_messages = "; ".join(message for message in hint_messages if message)
        if joined_messages:
            return joined_messages

    return f"GraphHopper routing failed with HTTP {error.code}."


def fetch_graphhopper_nearest(point: dict[str, float]) -> dict[str, float]:
    params = urllib.parse.urlencode(
        {
            "point": f"{point['lat']},{point['lon']}",
            "profile": GRAPHHOPPER_PROFILE,
        }
    )
    response = request_graphhopper_json(f"{GRAPHHOPPER_NEAREST_URL}?{params}")
    coordinates = response.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        raise GraphHopperRouteError("GraphHopper returned an invalid nearest-point response.", 502)

    lon, lat = coordinates[:2]
    return {"lat": float(lat), "lon": float(lon)}


def build_route_result_from_graphhopper(
    payload: dict[str, Any],
    start: dict[str, float],
    end: dict[str, float],
) -> dict[str, Any]:
    paths = payload.get("paths", [])
    if not paths:
        raise GraphHopperRouteError("GraphHopper returned no route.", 502)

    path = paths[0]
    route_geometry = decode_linestring(path.get("points"))
    if len(route_geometry) < 2:
        raise GraphHopperRouteError("GraphHopper returned an invalid route geometry.", 502)

    snapped_waypoints = decode_linestring(path.get("snapped_waypoints"))
    snapped_start = snapped_waypoints[0] if snapped_waypoints else route_geometry[0]
    snapped_end = snapped_waypoints[-1] if snapped_waypoints else route_geometry[-1]
    segments = build_route_segments(route_geometry, path.get("details", {}))
    strict_mode = all(is_route_candidate(segment, strict_mode=True) for segment in segments)
    total_length_m = round(float(path.get("distance", 0.0)), 1)
    average_comfort = compute_average_comfort(segments, total_length_m)

    return {
        "start": start,
        "end": end,
        "snapped_start": snapped_start,
        "snapped_end": snapped_end,
        "routing_mode": "strict" if strict_mode else "fallback",
        "total_length_m": total_length_m,
        "average_comfort": average_comfort,
        "explanation": build_route_explanation(segments, strict_mode=strict_mode),
        "segments": segments,
        "geometry": route_geometry,
    }


def build_inspection_result(
    point: dict[str, float],
    snapped_point: dict[str, float],
    route_result: dict[str, Any],
) -> dict[str, Any]:
    segment = select_nearest_route_segment(route_result["segments"], snapped_point)
    snapped_segment_point, snapped_segment_distance_m = nearest_point_on_polyline(segment["geometry"], snapped_point)
    return {
        "requested_point": point,
        "snapped_point": snapped_point,
        "segment_point": snapped_segment_point,
        "snap_distance_m": round(distance_m(point, snapped_point), 1),
        "segment_distance_m": round(snapped_segment_distance_m, 1),
        "segment": segment,
    }


def decode_linestring(raw_geometry: Any) -> list[dict[str, float]]:
    if not isinstance(raw_geometry, dict):
        return []

    coordinates = raw_geometry.get("coordinates")
    if not isinstance(coordinates, list):
        return []

    points: list[dict[str, float]] = []
    for coordinate in coordinates:
        if not isinstance(coordinate, list) or len(coordinate) < 2:
            continue

        lon, lat = coordinate[:2]
        points.append({"lat": float(lat), "lon": float(lon)})

    return points


def build_route_segments(route_geometry: list[dict[str, float]], details: dict[str, Any]) -> list[dict[str, Any]]:
    edge_intervals = normalize_detail_intervals(details.get("edge_id"))
    if not edge_intervals:
        edge_intervals = [[0, max(1, len(route_geometry) - 1), 0]]

    segments: list[dict[str, Any]] = []
    for segment_index, edge_interval in enumerate(edge_intervals):
        start_index, end_index, edge_id = edge_interval
        segment_geometry = slice_route_geometry(route_geometry, start_index, end_index)
        if len(segment_geometry) < 2:
            continue

        tags = build_segment_tags(details, start_index, end_index)
        score = classify_way(tags)
        segments.append(
            {
                "id": f"gh-{edge_id}-{segment_index}",
                "parent_way_id": edge_id,
                "name": tags.get("name", UNKNOWN_STREET_NAME),
                "geometry": segment_geometry,
                "length_m": round(calculate_geometry_length_m(segment_geometry), 1),
                "tags": tags,
                "score": score,
            }
        )

    if segments:
        return segments

    fallback_tags = build_segment_tags(details, 0, max(1, len(route_geometry) - 1))
    return [
        {
            "id": "gh-route-0",
            "parent_way_id": 0,
            "name": fallback_tags.get("name", UNKNOWN_STREET_NAME),
            "geometry": route_geometry,
            "length_m": round(calculate_geometry_length_m(route_geometry), 1),
            "tags": fallback_tags,
            "score": classify_way(fallback_tags),
        }
    ]


def normalize_detail_intervals(raw_intervals: Any) -> list[list[Any]]:
    if not isinstance(raw_intervals, list):
        return []

    normalized: list[list[Any]] = []
    for interval in raw_intervals:
        if not isinstance(interval, list) or len(interval) != 3:
            continue

        start_index, end_index, value = interval
        normalized.append([int(start_index), int(end_index), value])

    return normalized


def slice_route_geometry(
    route_geometry: list[dict[str, float]],
    start_index: int,
    end_index: int,
) -> list[dict[str, float]]:
    bounded_start = max(0, min(start_index, len(route_geometry) - 1))
    bounded_end = max(bounded_start + 1, min(end_index, len(route_geometry) - 1))
    return route_geometry[bounded_start : bounded_end + 1]


def build_segment_tags(details: dict[str, Any], start_index: int, end_index: int) -> dict[str, str]:
    road_class = normalize_detail_value(get_detail_value(details, "road_class", start_index, end_index))
    bike_network = normalize_detail_value(get_detail_value(details, "bike_network", start_index, end_index))
    bike_access = get_detail_value(details, "bike_access", start_index, end_index)
    bike_priority = get_detail_value(details, "bike_priority", start_index, end_index)
    get_off_bike = get_detail_value(details, "get_off_bike", start_index, end_index)
    road_environment = normalize_detail_value(get_detail_value(details, "road_environment", start_index, end_index))
    surface = normalize_detail_value(get_detail_value(details, "surface", start_index, end_index))
    smoothness = normalize_detail_value(get_detail_value(details, "smoothness", start_index, end_index))
    street_name = normalize_street_name(get_detail_value(details, "street_name", start_index, end_index))
    max_speed = get_detail_value(details, "max_speed", start_index, end_index)
    lanes = get_detail_value(details, "lanes", start_index, end_index)

    tags = {
        "name": street_name,
        "highway": road_class,
        "bicycle": derive_bicycle_tag(bike_access, get_off_bike, road_class, bike_network, bike_priority),
        "surface": surface,
        "smoothness": smoothness,
        "maxspeed": normalize_numeric_detail(max_speed),
        "lanes": normalize_numeric_detail(lanes),
        "cyclepass:router": "graphhopper",
        "cyclepass:road_environment": road_environment,
        "cyclepass:bike_network": bike_network,
        "cyclepass:bike_priority": normalize_numeric_detail(bike_priority),
    }

    if get_off_bike is True:
        tags["cyclepass:get_off_bike"] = "yes"

    return {key: value for key, value in tags.items() if value != ""}


def get_detail_value(details: dict[str, Any], detail_name: str, start_index: int, end_index: int) -> Any:
    intervals = normalize_detail_intervals(details.get(detail_name))
    if not intervals:
        return None

    best_value = None
    best_overlap = -1
    for interval_start, interval_end, value in intervals:
        overlap = min(end_index, interval_end) - max(start_index, interval_start)
        if overlap < 0:
            continue

        if overlap > best_overlap:
            best_overlap = overlap
            best_value = value

    return best_value


def normalize_detail_value(raw_value: Any) -> str:
    if raw_value is None:
        return ""

    normalized = str(raw_value).strip().lower()
    if normalized == "" or normalized == MISSING_DETAIL_VALUE.lower():
        return ""

    return normalized.replace(" ", "_")


def normalize_street_name(raw_value: Any) -> str:
    if raw_value is None:
        return UNKNOWN_STREET_NAME

    normalized = str(raw_value).strip()
    return normalized or UNKNOWN_STREET_NAME


def normalize_numeric_detail(raw_value: Any) -> str:
    if raw_value is None:
        return ""

    if isinstance(raw_value, bool):
        return ""

    if isinstance(raw_value, int):
        return str(raw_value)

    if isinstance(raw_value, float):
        if raw_value.is_integer():
            return str(int(raw_value))
        return f"{raw_value:.1f}"

    text = str(raw_value).strip()
    if text == "" or text.lower() == MISSING_DETAIL_VALUE.lower():
        return ""

    return text


def derive_bicycle_tag(
    bike_access: Any,
    get_off_bike: Any,
    road_class: str,
    bike_network: str,
    bike_priority: Any,
) -> str:
    if get_off_bike is True:
        return "dismount"

    if bike_access is False:
        return "no"

    if bike_access is True:
        return "yes"

    if road_class == "cycleway" or bike_network != "":
        return "yes"

    if isinstance(bike_priority, (int, float)) and bike_priority >= 0.85:
        return "yes"

    return ""


def calculate_geometry_length_m(geometry: list[dict[str, float]]) -> float:
    total_length_m = 0.0
    for point_index in range(1, len(geometry)):
        total_length_m += distance_m(geometry[point_index - 1], geometry[point_index])
    return total_length_m


def compute_average_comfort(route_segments: list[dict[str, Any]], total_length_m: float) -> int:
    if not route_segments:
        return 0

    if total_length_m <= 0:
        return round(sum(segment["score"]["bike_comfort"] for segment in route_segments) / len(route_segments))

    weighted_total = sum(segment["score"]["bike_comfort"] * segment["length_m"] for segment in route_segments)
    return round(weighted_total / total_length_m)


def select_nearest_route_segment(
    route_segments: list[dict[str, Any]],
    point: dict[str, float],
) -> dict[str, Any]:
    if not route_segments:
        raise GraphHopperRouteError("GraphHopper returned no route segments to inspect.", 502)

    best_segment = route_segments[0]
    best_distance_m = float("inf")
    for segment in route_segments:
        _, candidate_distance_m = nearest_point_on_polyline(segment["geometry"], point)
        if candidate_distance_m < best_distance_m:
            best_segment = segment
            best_distance_m = candidate_distance_m

    return best_segment


def offset_point(point: dict[str, float], east_m: float, north_m: float) -> dict[str, float]:
    latitude_delta = north_m / 111_320
    longitude_scale = max(0.0001, math_cos_latitude(point["lat"]))
    longitude_delta = east_m / (111_320 * longitude_scale)
    return {
        "lat": point["lat"] + latitude_delta,
        "lon": point["lon"] + longitude_delta,
    }


def math_cos_latitude(latitude: float) -> float:
    from math import cos, radians

    return cos(radians(latitude))
