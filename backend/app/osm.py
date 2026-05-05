from __future__ import annotations

import json
import logging
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_TIMEOUT_SECONDS = 25
WAY_FETCH_LIMIT = 600
TARGET_SEGMENT_LENGTH_M = 25
ROUTE_CORRIDOR_PADDING_M = 300
ROUTE_TILE_TARGET_SIZE_M = 1_200
MIN_ROUTE_TILE_SIZE_M = 300
MAX_ROUTE_TILE_SPLIT_DEPTH = 3
OVERPASS_MAX_RETRIES = 3
OVERPASS_RETRY_BACKOFF_SECONDS = 2.0
SLOW_TILE_THRESHOLD_SECONDS = 8.0
PROACTIVE_TILE_SPLIT_MIN_WAYS = 80
OVERPASS_RETRYABLE_STATUS_CODES = {400, 429, 504}
OVERPASS_OVERSIZED_RESPONSE_MARKERS = (
    "timed out",
    "out of memory",
    "runtime error",
    "too many",
)
ROAD_FILTER = "|".join(
    [
        "cycleway",
        "residential",
        "living_street",
        "service",
        "unclassified",
        "tertiary",
        "tertiary_link",
        "secondary",
        "secondary_link",
        "primary",
        "primary_link",
        "trunk",
        "trunk_link",
        "road",
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
LOGGER = logging.getLogger("cyclepass.osm")


def search_location(query: str) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "format": "jsonv2",
            "limit": 5,
            "q": query,
        }
    )
    request = urllib.request.Request(f"{NOMINATIM_URL}?{params}", headers=REQUEST_HEADERS)
    LOGGER.info("Calling Nominatim query=%r", query)
    try:
        with urllib.request.urlopen(request, timeout=OVERPASS_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        log_http_error("Nominatim search failed", error, {"query": query, "url": request.full_url})
        raise
    except urllib.error.URLError as error:
        LOGGER.exception("Nominatim network error query=%r reason=%s", query, error.reason)
        raise

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
    LOGGER.info("Fetching area ways lat=%.6f lon=%.6f radius_m=%s", lat, lon, radius_m)
    return split_ways_into_subsegments(fetch_overpass_ways(query)[:WAY_FETCH_LIMIT])


def analyze_route_area(start: dict[str, float], end: dict[str, float]) -> list[dict[str, Any]]:
    bbox = build_route_bbox(start, end, ROUTE_CORRIDOR_PADDING_M)
    tile_bboxes = select_route_tiles_within_corridor(
        split_bbox_into_tiles(bbox, ROUTE_TILE_TARGET_SIZE_M),
        start,
        end,
        ROUTE_CORRIDOR_PADDING_M,
    )
    tile_bboxes = order_route_tiles(tile_bboxes, start, end)
    way_by_id: dict[int, dict[str, Any]] = {}
    LOGGER.info(
        "Fetching route corridor start=(%.6f, %.6f) end=(%.6f, %.6f) tiles=%s bbox=%s",
        start["lat"],
        start["lon"],
        end["lat"],
        end["lon"],
        len(tile_bboxes),
        bbox,
    )

    for tile_bbox in tile_bboxes:
        if len(way_by_id) >= WAY_FETCH_LIMIT:
            LOGGER.info("Stopping route fetch after reaching way limit=%s", WAY_FETCH_LIMIT)
            break

        LOGGER.info("Fetching route tile bbox=%s", tile_bbox)
        tile_ways = fetch_tile_ways(
            tile_bbox,
            ROUTE_TILE_TARGET_SIZE_M,
            start=start,
            end=end,
            way_limit=WAY_FETCH_LIMIT - len(way_by_id),
        )

        for way in tile_ways:
            way_by_id[way["id"]] = way
            if len(way_by_id) >= WAY_FETCH_LIMIT:
                break

    ways = list(way_by_id.values())
    return split_ways_into_subsegments(ways)


def fetch_tile_ways(
    tile_bbox: dict[str, float],
    target_tile_size_m: float,
    split_depth: int = 0,
    start: dict[str, float] | None = None,
    end: dict[str, float] | None = None,
    way_limit: int | None = None,
) -> list[dict[str, Any]]:
    if way_limit is not None and way_limit <= 0:
        return []

    query = build_bbox_way_query(tile_bbox)
    try:
        fetch_started_at = time.monotonic()
        ways = fetch_overpass_ways(query)
        fetch_elapsed_seconds = time.monotonic() - fetch_started_at
        LOGGER.info(
            "Route tile fetch completed bbox=%s split_depth=%s elapsed_s=%.3f ways=%s way_limit=%s",
            tile_bbox,
            split_depth,
            fetch_elapsed_seconds,
            len(ways),
            way_limit,
        )
        if should_proactively_split_tile(tile_bbox, target_tile_size_m, split_depth, fetch_elapsed_seconds, len(ways)):
            LOGGER.warning(
                "Refetching slow route tile as subtiles bbox=%s split_depth=%s elapsed_s=%.3f ways=%s",
                tile_bbox,
                split_depth,
                fetch_elapsed_seconds,
                len(ways),
            )
            return fetch_split_tile_ways(
                tile_bbox,
                target_tile_size_m,
                split_depth,
                start,
                end,
                way_limit,
            )
        if way_limit is None:
            return ways

        return ways[:way_limit]
    except urllib.error.HTTPError as error:
        if not should_split_route_tile(error, tile_bbox, target_tile_size_m, split_depth):
            raise

    return fetch_split_tile_ways(tile_bbox, target_tile_size_m, split_depth, start, end, way_limit)


def fetch_overpass_ways(query: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        OVERPASS_URL,
        data=query.encode("utf-8"),
        headers={
            **REQUEST_HEADERS,
            "Content-Type": "text/plain;charset=UTF-8",
        },
        method="POST",
    )

    for attempt_index in range(OVERPASS_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(request, timeout=OVERPASS_TIMEOUT_SECONDS) as response:
                data = json.loads(response.read().decode("utf-8"))
            break
        except urllib.error.HTTPError as error:
            log_http_error(
                "Overpass query failed",
                error,
                {
                    "url": OVERPASS_URL,
                    "query_preview": compact_query_preview(query),
                    "attempt": attempt_index + 1,
                },
            )
            if not should_retry_overpass_request(error, attempt_index):
                raise

            delay_seconds = compute_overpass_retry_delay_seconds(error, attempt_index)
            LOGGER.warning(
                "Retrying Overpass query after rate limit delay_s=%.3f attempt=%s query=%s",
                delay_seconds,
                attempt_index + 2,
                compact_query_preview(query),
            )
            time.sleep(delay_seconds)
        except urllib.error.URLError as error:
            LOGGER.exception("Overpass network error reason=%s query=%s", error.reason, compact_query_preview(query))
            raise

    return [
        element
        for element in data.get("elements", [])
        if element.get("type") == "way" and isinstance(element.get("geometry"), list)
    ]


def log_http_error(message: str, error: urllib.error.HTTPError, context: dict[str, Any]) -> None:
    retry_after = error.headers.get("Retry-After")
    response_body = read_error_body(error)
    LOGGER.error(
        "%s status=%s reason=%s retry_after=%r context=%s body=%r",
        message,
        error.code,
        error.reason,
        retry_after,
        context,
        response_body,
    )


def read_error_body(error: urllib.error.HTTPError) -> str:
    cached_body = error.__dict__.get("_cyclepass_response_body")
    if cached_body is not None:
        return cached_body

    try:
        body = error.read().decode("utf-8", errors="replace").strip()
    except Exception:
        return ""

    compact_body = body[:500]
    setattr(error, "_cyclepass_response_body", compact_body)
    return compact_body


def compact_query_preview(query: str) -> str:
    return " ".join(query.split())[:220]


def compute_overpass_retry_delay_seconds(error: urllib.error.HTTPError, attempt_index: int) -> float:
    retry_after = error.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return max(0.0, float(retry_after))
        except ValueError:
            pass

    return OVERPASS_RETRY_BACKOFF_SECONDS * (2**attempt_index)


def should_retry_overpass_request(error: urllib.error.HTTPError, attempt_index: int) -> bool:
    return error.code == 429 and attempt_index < OVERPASS_MAX_RETRIES


def build_bbox_way_query(bbox: dict[str, float]) -> str:
    return f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
way["highway"~"{ROAD_FILTER}"]({bbox['south']},{bbox['west']},{bbox['north']},{bbox['east']});
out tags geom;
"""


def should_split_route_tile(
    error: urllib.error.HTTPError,
    tile_bbox: dict[str, float],
    target_tile_size_m: float,
    split_depth: int,
) -> bool:
    if split_depth >= MAX_ROUTE_TILE_SPLIT_DEPTH:
        return False

    if target_tile_size_m <= MIN_ROUTE_TILE_SIZE_M:
        return False

    if len(split_bbox_into_tiles(tile_bbox, max(MIN_ROUTE_TILE_SIZE_M, target_tile_size_m / 2))) <= 1:
        return False

    if error.code == 504:
        return True

    if error.code not in OVERPASS_RETRYABLE_STATUS_CODES:
        return False

    response_body = read_error_body(error).lower()
    return any(marker in response_body for marker in OVERPASS_OVERSIZED_RESPONSE_MARKERS)


def should_proactively_split_tile(
    tile_bbox: dict[str, float],
    target_tile_size_m: float,
    split_depth: int,
    fetch_elapsed_seconds: float,
    way_count: int,
) -> bool:
    if fetch_elapsed_seconds < SLOW_TILE_THRESHOLD_SECONDS:
        return False

    if way_count < PROACTIVE_TILE_SPLIT_MIN_WAYS:
        return False

    return can_split_route_tile(tile_bbox, target_tile_size_m, split_depth)


def can_split_route_tile(
    tile_bbox: dict[str, float],
    target_tile_size_m: float,
    split_depth: int,
) -> bool:
    if split_depth >= MAX_ROUTE_TILE_SPLIT_DEPTH:
        return False

    if target_tile_size_m <= MIN_ROUTE_TILE_SIZE_M:
        return False

    return len(split_bbox_into_tiles(tile_bbox, max(MIN_ROUTE_TILE_SIZE_M, target_tile_size_m / 2))) > 1


def fetch_split_tile_ways(
    tile_bbox: dict[str, float],
    target_tile_size_m: float,
    split_depth: int,
    start: dict[str, float] | None,
    end: dict[str, float] | None,
    way_limit: int | None,
) -> list[dict[str, Any]]:
    next_tile_size_m = max(MIN_ROUTE_TILE_SIZE_M, target_tile_size_m / 2)
    subtiles = split_bbox_into_tiles(tile_bbox, next_tile_size_m)
    if start is not None and end is not None:
        subtiles = select_route_tiles_within_corridor(subtiles, start, end, ROUTE_CORRIDOR_PADDING_M)
        subtiles = order_route_tiles(subtiles, start, end)
    way_by_id: dict[int, dict[str, Any]] = {}
    LOGGER.warning(
        "Retrying route tile with smaller subtiles bbox=%s split_depth=%s subtile_count=%s next_tile_size_m=%s",
        tile_bbox,
        split_depth + 1,
        len(subtiles),
        next_tile_size_m,
    )

    for subtile_bbox in subtiles:
        if way_limit is not None and len(way_by_id) >= way_limit:
            LOGGER.info("Stopping subtile fetch after reaching way limit=%s", way_limit)
            break

        LOGGER.info("Fetching route subtile bbox=%s", subtile_bbox)
        remaining_way_limit = None if way_limit is None else way_limit - len(way_by_id)
        for way in fetch_tile_ways(
            subtile_bbox,
            next_tile_size_m,
            split_depth + 1,
            start=start,
            end=end,
            way_limit=remaining_way_limit,
        ):
            way_by_id[way["id"]] = way
            if way_limit is not None and len(way_by_id) >= way_limit:
                break

    return list(way_by_id.values())


def split_ways_into_subsegments(ways: list[dict[str, Any]]) -> list[dict[str, Any]]:
    subsegments: list[dict[str, Any]] = []

    for way in ways:
        geometry = way.get("geometry", [])
        if len(geometry) < 2:
            continue

        chunk_index = 0
        current_chunk = [geometry[0]]
        current_length_m = 0.0

        for point_index in range(1, len(geometry)):
            previous_point = geometry[point_index - 1]
            next_point = geometry[point_index]
            segment_length_m = distance_m(previous_point, next_point)

            current_chunk.append(next_point)
            current_length_m += segment_length_m

            is_last_point = point_index == len(geometry) - 1
            if current_length_m >= TARGET_SEGMENT_LENGTH_M or is_last_point:
                if len(current_chunk) >= 2:
                    chunk_length_m = calculate_geometry_length_m(current_chunk)
                    subsegments.append(
                        {
                            "id": f"{way['id']}-{chunk_index}",
                            "parent_way_id": way["id"],
                            "type": "way_segment",
                            "geometry": current_chunk.copy(),
                            "length_m": round(chunk_length_m, 1),
                            "tags": way.get("tags", {}),
                        }
                    )
                    chunk_index += 1

                current_chunk = [next_point]
                current_length_m = 0.0

    return subsegments


def order_route_tiles(
    tile_bboxes: list[dict[str, float]],
    start: dict[str, float],
    end: dict[str, float],
) -> list[dict[str, float]]:
    return sorted(tile_bboxes, key=lambda tile_bbox: route_tile_sort_key(tile_bbox, start, end))


def route_tile_sort_key(
    tile_bbox: dict[str, float],
    start: dict[str, float],
    end: dict[str, float],
) -> tuple[float, float]:
    center_point = tile_center(tile_bbox)
    return (
        distance_m(start, center_point) + distance_m(center_point, end),
        distance_m(start, center_point),
    )


def tile_center(tile_bbox: dict[str, float]) -> dict[str, float]:
    return {
        "lat": (tile_bbox["south"] + tile_bbox["north"]) / 2,
        "lon": (tile_bbox["west"] + tile_bbox["east"]) / 2,
    }


def select_route_tiles_within_corridor(
    tile_bboxes: list[dict[str, float]],
    start: dict[str, float],
    end: dict[str, float],
    corridor_padding_m: float,
) -> list[dict[str, float]]:
    corridor_tiles = [
        tile_bbox
        for tile_bbox in tile_bboxes
        if tile_intersects_route_corridor(tile_bbox, start, end, corridor_padding_m)
    ]
    return corridor_tiles or tile_bboxes


def tile_intersects_route_corridor(
    tile_bbox: dict[str, float],
    start: dict[str, float],
    end: dict[str, float],
    corridor_padding_m: float,
) -> bool:
    tile_center_point = tile_center(tile_bbox)
    tile_half_diagonal_m = distance_m(
        tile_center_point,
        {"lat": tile_bbox["north"], "lon": tile_bbox["east"]},
    )
    return distance_point_to_segment_m(tile_center_point, start, end) <= corridor_padding_m + tile_half_diagonal_m


def distance_m(start: dict[str, float], end: dict[str, float]) -> float:
    mean_latitude_rad = math.radians((start["lat"] + end["lat"]) / 2)
    lat_scale_m = 111_320
    lon_scale_m = 111_320 * math.cos(mean_latitude_rad)
    lat_delta_m = (end["lat"] - start["lat"]) * lat_scale_m
    lon_delta_m = (end["lon"] - start["lon"]) * lon_scale_m
    return math.hypot(lat_delta_m, lon_delta_m)


def distance_point_to_segment_m(
    point: dict[str, float],
    segment_start: dict[str, float],
    segment_end: dict[str, float],
) -> float:
    mean_latitude_rad = math.radians((segment_start["lat"] + segment_end["lat"] + point["lat"]) / 3)
    lat_scale_m = 111_320
    lon_scale_m = 111_320 * math.cos(mean_latitude_rad)

    start_x = segment_start["lon"] * lon_scale_m
    start_y = segment_start["lat"] * lat_scale_m
    end_x = segment_end["lon"] * lon_scale_m
    end_y = segment_end["lat"] * lat_scale_m
    point_x = point["lon"] * lon_scale_m
    point_y = point["lat"] * lat_scale_m

    segment_dx = end_x - start_x
    segment_dy = end_y - start_y
    segment_length_squared = (segment_dx * segment_dx) + (segment_dy * segment_dy)

    if segment_length_squared == 0:
        return math.hypot(point_x - start_x, point_y - start_y)

    projection_ratio = ((point_x - start_x) * segment_dx + (point_y - start_y) * segment_dy) / segment_length_squared
    clamped_ratio = max(0.0, min(1.0, projection_ratio))
    projected_x = start_x + (segment_dx * clamped_ratio)
    projected_y = start_y + (segment_dy * clamped_ratio)
    return math.hypot(point_x - projected_x, point_y - projected_y)


def calculate_geometry_length_m(geometry: list[dict[str, float]]) -> float:
    total_length_m = 0.0
    for point_index in range(1, len(geometry)):
        total_length_m += distance_m(geometry[point_index - 1], geometry[point_index])
    return total_length_m


def build_route_bbox(start: dict[str, float], end: dict[str, float], padding_m: float) -> dict[str, float]:
    min_lat = min(start["lat"], end["lat"])
    max_lat = max(start["lat"], end["lat"])
    min_lon = min(start["lon"], end["lon"])
    max_lon = max(start["lon"], end["lon"])
    latitude_padding = padding_m / 111_320
    mean_latitude_rad = math.radians((start["lat"] + end["lat"]) / 2)
    longitude_scale = max(0.0001, math.cos(mean_latitude_rad))
    longitude_padding = padding_m / (111_320 * longitude_scale)

    return {
        "south": min_lat - latitude_padding,
        "west": min_lon - longitude_padding,
        "north": max_lat + latitude_padding,
        "east": max_lon + longitude_padding,
    }


def split_bbox_into_tiles(bbox: dict[str, float], target_tile_size_m: float) -> list[dict[str, float]]:
    bbox_height_m = distance_m(
        {"lat": bbox["south"], "lon": bbox["west"]},
        {"lat": bbox["north"], "lon": bbox["west"]},
    )
    bbox_width_m = distance_m(
        {"lat": bbox["south"], "lon": bbox["west"]},
        {"lat": bbox["south"], "lon": bbox["east"]},
    )
    row_count = max(1, math.ceil(bbox_height_m / target_tile_size_m))
    column_count = max(1, math.ceil(bbox_width_m / target_tile_size_m))
    lat_step = (bbox["north"] - bbox["south"]) / row_count
    lon_step = (bbox["east"] - bbox["west"]) / column_count
    tiles: list[dict[str, float]] = []

    for row_index in range(row_count):
        tile_south = bbox["south"] + (row_index * lat_step)
        tile_north = bbox["north"] if row_index == row_count - 1 else tile_south + lat_step

        for column_index in range(column_count):
            tile_west = bbox["west"] + (column_index * lon_step)
            tile_east = bbox["east"] if column_index == column_count - 1 else tile_west + lon_step
            tiles.append(
                {
                    "south": tile_south,
                    "west": tile_west,
                    "north": tile_north,
                    "east": tile_east,
                }
            )

    return tiles
