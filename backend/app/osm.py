from __future__ import annotations

import json
import math
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
    return split_ways_into_subsegments(fetch_overpass_ways(query)[:WAY_FETCH_LIMIT])


def analyze_route_area(start: dict[str, float], end: dict[str, float]) -> list[dict[str, Any]]:
    bbox = build_route_bbox(start, end, ROUTE_CORRIDOR_PADDING_M)
    tile_bboxes = split_bbox_into_tiles(bbox, ROUTE_TILE_TARGET_SIZE_M)
    way_by_id: dict[int, dict[str, Any]] = {}

    for tile_bbox in tile_bboxes:
        query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
way["highway"~"{ROAD_FILTER}"]({tile_bbox['south']},{tile_bbox['west']},{tile_bbox['north']},{tile_bbox['east']});
out tags geom;
"""
        try:
            tile_ways = fetch_overpass_ways(query)
        except urllib.error.HTTPError as error:
            if error.code != 504 or len(tile_bboxes) == 1:
                raise

            for way in fetch_tile_halves(tile_bbox):
                way_by_id[way["id"]] = way
            continue

        for way in tile_ways:
            way_by_id[way["id"]] = way

    ways = list(way_by_id.values())[:WAY_FETCH_LIMIT]
    return split_ways_into_subsegments(ways)


def fetch_tile_halves(tile_bbox: dict[str, float]) -> list[dict[str, Any]]:
    half_tiles = split_bbox_into_tiles(tile_bbox, ROUTE_TILE_TARGET_SIZE_M / 2)
    way_by_id: dict[int, dict[str, Any]] = {}

    for half_tile in half_tiles:
        query = f"""
[out:json][timeout:{OVERPASS_TIMEOUT_SECONDS}];
way["highway"~"{ROAD_FILTER}"]({half_tile['south']},{half_tile['west']},{half_tile['north']},{half_tile['east']});
out tags geom;
"""
        for way in fetch_overpass_ways(query):
            way_by_id[way["id"]] = way

    return list(way_by_id.values())


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

    with urllib.request.urlopen(request, timeout=OVERPASS_TIMEOUT_SECONDS) as response:
        data = json.loads(response.read().decode("utf-8"))

    return [
        element
        for element in data.get("elements", [])
        if element.get("type") == "way" and isinstance(element.get("geometry"), list)
    ]


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


def distance_m(start: dict[str, float], end: dict[str, float]) -> float:
    mean_latitude_rad = math.radians((start["lat"] + end["lat"]) / 2)
    lat_scale_m = 111_320
    lon_scale_m = 111_320 * math.cos(mean_latitude_rad)
    lat_delta_m = (end["lat"] - start["lat"]) * lat_scale_m
    lon_delta_m = (end["lon"] - start["lon"]) * lon_scale_m
    return math.hypot(lat_delta_m, lon_delta_m)


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
