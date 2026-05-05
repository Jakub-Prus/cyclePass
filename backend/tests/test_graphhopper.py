import unittest

from backend.app.graphhopper import build_inspection_result, build_route_result_from_graphhopper


class GraphHopperRouteTests(unittest.TestCase):
    def test_builds_cyclepass_route_from_graphhopper_path_details(self) -> None:
        route = build_route_result_from_graphhopper(
            {
                "paths": [
                    {
                        "distance": 222.6,
                        "points": {
                            "type": "LineString",
                            "coordinates": [
                                [17.5000, 51.9700],
                                [17.5010, 51.9700],
                                [17.5020, 51.9700],
                            ],
                        },
                        "snapped_waypoints": {
                            "type": "LineString",
                            "coordinates": [
                                [17.5000, 51.9700],
                                [17.5020, 51.9700],
                            ],
                        },
                        "details": {
                            "edge_id": [[0, 1, 1001], [1, 2, 1002]],
                            "street_name": [[0, 2, "Example Street"]],
                            "road_class": [[0, 1, "CYCLEWAY"], [1, 2, "PRIMARY"]],
                            "surface": [[0, 2, "ASPHALT"]],
                            "smoothness": [[0, 2, "GOOD"]],
                            "max_speed": [[0, 1, 20], [1, 2, 50]],
                            "bike_network": [[0, 1, "LOCAL"], [1, 2, "MISSING"]],
                            "bike_access": [[0, 2, True]],
                            "bike_priority": [[0, 1, 1.0], [1, 2, 0.9]],
                            "get_off_bike": [[0, 1, False], [1, 2, False]],
                            "road_environment": [[0, 2, "ROAD"]],
                            "lanes": [[0, 2, 1]],
                        },
                    }
                ]
            },
            start={"lat": 51.9700, "lon": 17.5000},
            end={"lat": 51.9700, "lon": 17.5020},
        )

        self.assertEqual(route["routing_mode"], "strict")
        self.assertEqual(len(route["segments"]), 2)
        self.assertEqual(route["segments"][0]["score"]["bike_crossable_class"], "protected")
        self.assertEqual(route["segments"][1]["score"]["normalized_tags"]["highway"], "primary")
        self.assertEqual(route["segments"][1]["score"]["normalized_tags"]["bike_priority"], 0.9)
        self.assertGreater(route["average_comfort"], 40)
        self.assertEqual(route["snapped_start"]["lon"], 17.5)
        self.assertEqual(route["snapped_end"]["lon"], 17.502)

    def test_marks_get_off_bike_edges_as_dismount(self) -> None:
        route = build_route_result_from_graphhopper(
            {
                "paths": [
                    {
                        "distance": 111.3,
                        "points": {
                            "type": "LineString",
                            "coordinates": [
                                [17.5000, 51.9700],
                                [17.5010, 51.9700],
                            ],
                        },
                        "snapped_waypoints": {
                            "type": "LineString",
                            "coordinates": [
                                [17.5000, 51.9700],
                                [17.5010, 51.9700],
                            ],
                        },
                        "details": {
                            "edge_id": [[0, 1, 2001]],
                            "street_name": [[0, 1, "Walk bike section"]],
                            "road_class": [[0, 1, "FOOTWAY"]],
                            "surface": [[0, 1, "PAVED"]],
                            "smoothness": [[0, 1, "GOOD"]],
                            "max_speed": [[0, 1, 5]],
                            "bike_network": [[0, 1, "MISSING"]],
                            "bike_access": [[0, 1, True]],
                            "bike_priority": [[0, 1, 0.7]],
                            "get_off_bike": [[0, 1, True]],
                            "road_environment": [[0, 1, "ROAD"]],
                            "lanes": [[0, 1, 1]],
                        },
                    }
                ]
            },
            start={"lat": 51.9700, "lon": 17.5000},
            end={"lat": 51.9700, "lon": 17.5010},
        )

        segment = route["segments"][0]
        self.assertEqual(segment["score"]["bike_allowed"], "uncertain")
        self.assertEqual(segment["score"]["normalized_tags"]["bicycle"], "dismount")

    def test_selects_segment_nearest_to_snapped_point_for_inspection(self) -> None:
        route_result = {
            "segments": [
                {
                    "id": "left",
                    "name": "Left",
                    "geometry": [{"lat": 52.0, "lon": 16.0}, {"lat": 52.0, "lon": 16.001}],
                    "length_m": 100.0,
                    "tags": {},
                    "score": {
                        "bike_allowed": "yes",
                        "bike_comfort": 80,
                        "bike_crossable_class": "low-stress",
                        "normalized_tags": {},
                    },
                },
                {
                    "id": "right",
                    "name": "Right",
                    "geometry": [{"lat": 52.0, "lon": 16.01}, {"lat": 52.0, "lon": 16.011}],
                    "length_m": 100.0,
                    "tags": {},
                    "score": {
                        "bike_allowed": "yes",
                        "bike_comfort": 80,
                        "bike_crossable_class": "protected",
                        "normalized_tags": {},
                    },
                },
            ]
        }

        inspection = build_inspection_result(
            point={"lat": 52.0, "lon": 16.0105},
            snapped_point={"lat": 52.0, "lon": 16.0103},
            route_result=route_result,
        )

        self.assertEqual(inspection["segment"]["id"], "right")
        self.assertGreaterEqual(inspection["snap_distance_m"], 0.0)


if __name__ == "__main__":
    unittest.main()
