from __future__ import annotations

import heapq
import math
from typing import Any

HOSTILE_HIGHWAYS = {"motorway", "motorway_link", "trunk", "trunk_link"}
NODE_PRECISION_DECIMALS = 5
CANDIDATE_SEGMENT_LIMIT = 5
SNAP_CANDIDATE_DISTANCE_BUFFER_M = 150.0
SNAP_CANDIDATE_DISTANCE_MULTIPLIER = 2.5
HOSTILE_ROAD_COST_MULTIPLIER = 12.0
FORBIDDEN_ROAD_COST_MULTIPLIER = 18.0
NOT_SUITABLE_COST_MULTIPLIER = 4.0
SHARED_COST_MULTIPLIER = 1.4
LOW_STRESS_COST_MULTIPLIER = 1.1
PROTECTED_COST_MULTIPLIER = 1.0
UNSAFE_BIKE_ALLOWED_STATE = "no"


def build_route(segments: list[dict[str, Any]], start: dict[str, float], end: dict[str, float]) -> dict[str, Any]:
    for strict_mode in (True, False):
        graph = build_graph(segments, strict_mode=strict_mode)
        if not graph["nodes"]:
            continue

        route_connection = find_best_route_connection(graph, start, end)
        if route_connection is None:
            continue

        start_node_id = route_connection["start_node_id"]
        end_node_id = route_connection["end_node_id"]
        path_segment_ids = route_connection["path_segment_ids"]
        route_segments = [graph["segments_by_id"][segment_id] for segment_id in path_segment_ids]
        route_geometry = merge_route_geometry(route_segments)
        total_length_m = round(sum(segment["length_m"] for segment in route_segments), 1)
        average_comfort = round(
            sum(segment["score"]["bike_comfort"] for segment in route_segments) / len(route_segments)
        )

        return {
            "start": start,
            "end": end,
            "snapped_start": route_connection["snapped_start"],
            "snapped_end": route_connection["snapped_end"],
            "segments": route_segments,
            "geometry": route_geometry,
            "total_length_m": total_length_m,
            "average_comfort": average_comfort,
            "routing_mode": "strict" if strict_mode else "fallback",
            "explanation": build_route_explanation(route_segments, strict_mode=strict_mode),
        }

    raise ValueError("No connected route was found between the selected points.")


def build_graph(segments: list[dict[str, Any]], strict_mode: bool = True) -> dict[str, Any]:
    adjacency: dict[str, list[dict[str, Any]]] = {}
    nodes: dict[str, dict[str, float]] = {}
    segments_by_id: dict[str, dict[str, Any]] = {}

    for segment in segments:
        if not is_route_candidate(segment, strict_mode=strict_mode):
            continue

        geometry = segment.get("geometry", [])
        if len(geometry) < 2:
            continue

        start_node = geometry[0]
        end_node = geometry[-1]
        start_node_id = make_node_id(start_node)
        end_node_id = make_node_id(end_node)
        routing_cost = compute_routing_cost(segment)

        nodes[start_node_id] = {"lat": start_node["lat"], "lon": start_node["lon"]}
        nodes[end_node_id] = {"lat": end_node["lat"], "lon": end_node["lon"]}

        enriched_segment = {
            **segment,
            "from_node_id": start_node_id,
            "to_node_id": end_node_id,
            "routing_cost": routing_cost,
        }
        segments_by_id[segment["id"]] = enriched_segment

        adjacency.setdefault(start_node_id, []).append(
            {"node_id": end_node_id, "segment_id": segment["id"], "cost": routing_cost}
        )
        adjacency.setdefault(end_node_id, []).append(
            {"node_id": start_node_id, "segment_id": segment["id"], "cost": routing_cost}
        )

    return {
        "adjacency": adjacency,
        "nodes": nodes,
        "segments_by_id": segments_by_id,
    }


def is_route_candidate(segment: dict[str, Any], strict_mode: bool) -> bool:
    tags = segment.get("score", {}).get("normalized_tags", {})
    if strict_mode:
        if segment.get("score", {}).get("bike_allowed") == UNSAFE_BIKE_ALLOWED_STATE:
            return False

        if tags.get("highway") in HOSTILE_HIGHWAYS and segment.get("score", {}).get("bike_crossable_class") != "protected":
            return False

    return True


def make_node_id(point: dict[str, float]) -> str:
    return f"{point['lat']:.{NODE_PRECISION_DECIMALS}f},{point['lon']:.{NODE_PRECISION_DECIMALS}f}"


def compute_routing_cost(segment: dict[str, Any]) -> float:
    score = segment["score"]
    comfort_class = score["bike_crossable_class"]
    length_m = segment["length_m"]

    if score["bike_allowed"] == UNSAFE_BIKE_ALLOWED_STATE:
        multiplier = FORBIDDEN_ROAD_COST_MULTIPLIER
    elif comfort_class == "protected":
        multiplier = PROTECTED_COST_MULTIPLIER
    elif comfort_class == "low-stress":
        multiplier = LOW_STRESS_COST_MULTIPLIER
    elif comfort_class == "shared":
        multiplier = SHARED_COST_MULTIPLIER
    else:
        tags = score["normalized_tags"]
        if tags.get("highway") in HOSTILE_HIGHWAYS:
            multiplier = HOSTILE_ROAD_COST_MULTIPLIER
        else:
            multiplier = NOT_SUITABLE_COST_MULTIPLIER

    comfort_discount = max(0.7, 1.2 - (score["bike_comfort"] / 200))
    return round(length_m * multiplier * comfort_discount, 3)


def find_best_route_connection(
    graph: dict[str, Any], start: dict[str, float], end: dict[str, float]
) -> dict[str, Any] | None:
    start_candidates = find_nearest_segment_candidates(graph["segments_by_id"], start)
    end_candidates = find_nearest_segment_candidates(graph["segments_by_id"], end)
    best_connection: dict[str, Any] | None = None
    best_total_cost = math.inf

    for start_candidate in start_candidates:
        for end_candidate in end_candidates:
            for start_node_id in (start_candidate["segment"]["from_node_id"], start_candidate["segment"]["to_node_id"]):
                for end_node_id in (end_candidate["segment"]["from_node_id"], end_candidate["segment"]["to_node_id"]):
                    path_segment_ids = shortest_path(graph["adjacency"], start_node_id, end_node_id)
                    if not path_segment_ids:
                        continue

                    path_cost = sum(
                        graph["segments_by_id"][segment_id]["routing_cost"] for segment_id in path_segment_ids
                    )
                    access_cost = distance_m(start_candidate["snapped_point"], graph["nodes"][start_node_id]) + distance_m(
                        end_candidate["snapped_point"], graph["nodes"][end_node_id]
                    )
                    total_cost = path_cost + access_cost

                    if total_cost >= best_total_cost:
                        continue

                    best_total_cost = total_cost
                    best_connection = {
                        "start_node_id": start_node_id,
                        "end_node_id": end_node_id,
                        "path_segment_ids": path_segment_ids,
                        "snapped_start": start_candidate["snapped_point"],
                        "snapped_end": end_candidate["snapped_point"],
                    }

    return best_connection


def find_nearest_segment_candidates(
    segments_by_id: dict[str, dict[str, Any]], point: dict[str, float]
) -> list[dict[str, Any]]:
    segment_candidates: list[dict[str, Any]] = []

    for segment in segments_by_id.values():
        snapped_point, snapped_distance_m = nearest_point_on_polyline(segment["geometry"], point)
        segment_candidates.append(
            {
                "segment": segment,
                "snapped_point": snapped_point,
                "snapped_distance_m": snapped_distance_m,
            }
        )

    segment_candidates.sort(key=lambda candidate: candidate["snapped_distance_m"])
    if not segment_candidates:
        return []

    nearest_distance_m = segment_candidates[0]["snapped_distance_m"]
    max_candidate_distance_m = max(
        nearest_distance_m + SNAP_CANDIDATE_DISTANCE_BUFFER_M,
        nearest_distance_m * SNAP_CANDIDATE_DISTANCE_MULTIPLIER,
    )
    nearby_candidates = [
        candidate
        for candidate in segment_candidates
        if candidate["snapped_distance_m"] <= max_candidate_distance_m
    ]
    return nearby_candidates[:CANDIDATE_SEGMENT_LIMIT]


def shortest_path(
    adjacency: dict[str, list[dict[str, Any]]], start_node_id: str, end_node_id: str
) -> list[str]:
    frontier: list[tuple[float, str]] = [(0.0, start_node_id)]
    best_cost_by_node = {start_node_id: 0.0}
    previous_step_by_node: dict[str, tuple[str, str]] = {}

    while frontier:
        current_cost, current_node_id = heapq.heappop(frontier)
        if current_node_id == end_node_id:
            return reconstruct_path(previous_step_by_node, start_node_id, end_node_id)

        if current_cost > best_cost_by_node.get(current_node_id, math.inf):
            continue

        for edge in adjacency.get(current_node_id, []):
            next_cost = current_cost + edge["cost"]
            next_node_id = edge["node_id"]

            if next_cost >= best_cost_by_node.get(next_node_id, math.inf):
                continue

            best_cost_by_node[next_node_id] = next_cost
            previous_step_by_node[next_node_id] = (current_node_id, edge["segment_id"])
            heapq.heappush(frontier, (next_cost, next_node_id))

    return []


def reconstruct_path(
    previous_step_by_node: dict[str, tuple[str, str]], start_node_id: str, end_node_id: str
) -> list[str]:
    path_segment_ids: list[str] = []
    current_node_id = end_node_id

    while current_node_id != start_node_id:
        previous_step = previous_step_by_node.get(current_node_id)
        if previous_step is None:
            return []

        previous_node_id, segment_id = previous_step
        path_segment_ids.append(segment_id)
        current_node_id = previous_node_id

    path_segment_ids.reverse()
    return path_segment_ids


def merge_route_geometry(route_segments: list[dict[str, Any]]) -> list[dict[str, float]]:
    route_geometry: list[dict[str, float]] = []

    for segment in route_segments:
        geometry = segment["geometry"]
        if not route_geometry:
            route_geometry.extend(geometry)
            continue

        if points_match(route_geometry[-1], geometry[0]):
            route_geometry.extend(geometry[1:])
            continue

        if points_match(route_geometry[-1], geometry[-1]):
            route_geometry.extend(reversed(geometry[:-1]))
            continue

        route_geometry.extend(geometry)

    return route_geometry


def points_match(left: dict[str, float], right: dict[str, float]) -> bool:
    return make_node_id(left) == make_node_id(right)


def build_route_explanation(route_segments: list[dict[str, Any]], strict_mode: bool) -> list[str]:
    classes = {segment["score"]["bike_crossable_class"] for segment in route_segments}
    explanations: list[str] = ["This is the safest available connected route between the selected points."]

    if not strict_mode:
        explanations.append("Some sections are less comfortable because the network does not provide a fully bike-safe connection end to end.")
    if "protected" in classes:
        explanations.append("The route uses protected or dedicated cycling infrastructure where available.")
    if "low-stress" in classes:
        explanations.append("The route prefers calmer streets over direct but higher-stress road links.")
    if "shared" in classes:
        explanations.append("Shared or sidewalk-style fallback links were used only where they improved continuity.")
    if "not-suitable" in classes:
        explanations.append("Some uncomfortable road segments were kept only as fallback connectors.")
    if not explanations:
        explanations.append("The route was selected from the available rideable road network.")

    return explanations


def distance_m(start: dict[str, float], end: dict[str, float]) -> float:
    mean_latitude_rad = math.radians((start["lat"] + end["lat"]) / 2)
    lat_scale_m = 111_320
    lon_scale_m = 111_320 * math.cos(mean_latitude_rad)
    lat_delta_m = (end["lat"] - start["lat"]) * lat_scale_m
    lon_delta_m = (end["lon"] - start["lon"]) * lon_scale_m
    return math.hypot(lat_delta_m, lon_delta_m)


def nearest_point_on_polyline(
    geometry: list[dict[str, float]], point: dict[str, float]
) -> tuple[dict[str, float], float]:
    nearest_point = geometry[0]
    nearest_distance_m = math.inf

    for point_index in range(1, len(geometry)):
        segment_start = geometry[point_index - 1]
        segment_end = geometry[point_index]
        candidate_point = project_point_to_segment(segment_start, segment_end, point)
        candidate_distance_m = distance_m(candidate_point, point)

        if candidate_distance_m >= nearest_distance_m:
            continue

        nearest_point = candidate_point
        nearest_distance_m = candidate_distance_m

    return nearest_point, nearest_distance_m


def project_point_to_segment(
    segment_start: dict[str, float], segment_end: dict[str, float], point: dict[str, float]
) -> dict[str, float]:
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
        return {"lat": segment_start["lat"], "lon": segment_start["lon"]}

    projection_ratio = ((point_x - start_x) * segment_dx + (point_y - start_y) * segment_dy) / segment_length_squared
    clamped_ratio = max(0.0, min(1.0, projection_ratio))

    projected_x = start_x + (segment_dx * clamped_ratio)
    projected_y = start_y + (segment_dy * clamped_ratio)
    return {
        "lat": projected_y / lat_scale_m,
        "lon": projected_x / lon_scale_m,
    }
