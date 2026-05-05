import unittest

from backend.app.routing import build_route, build_graph


def make_segment(
    segment_id: str,
    geometry: list[dict[str, float]],
    bike_crossable_class: str,
    bike_allowed: str,
    bike_comfort: int,
    highway: str,
) -> dict[str, object]:
    length_m = 0.0
    for point_index in range(1, len(geometry)):
        left = geometry[point_index - 1]
        right = geometry[point_index]
        length_m += abs(right["lon"] - left["lon"]) * 111_320

    return {
        "id": segment_id,
        "name": segment_id,
        "geometry": geometry,
        "tags": {"highway": highway},
        "length_m": length_m,
        "score": {
            "bike_allowed": bike_allowed,
            "bike_comfort": bike_comfort,
            "bike_crossable_class": bike_crossable_class,
            "normalized_tags": {"highway": highway},
        },
    }


class RoutingTests(unittest.TestCase):
    def test_excludes_hostile_highway_segments_from_graph(self) -> None:
        graph = build_graph(
            [
                make_segment(
                    "hostile",
                    [{"lat": 0.0, "lon": 0.0}, {"lat": 0.0, "lon": 0.001}],
                    "not-suitable",
                    "uncertain",
                    5,
                    "trunk",
                )
            ],
            strict_mode=True,
        )

        self.assertEqual(graph["segments_by_id"], {})

    def test_keeps_hostile_highway_segments_in_fallback_graph(self) -> None:
        graph = build_graph(
            [
                make_segment(
                    "hostile",
                    [{"lat": 0.0, "lon": 0.0}, {"lat": 0.0, "lon": 0.001}],
                    "not-suitable",
                    "uncertain",
                    5,
                    "trunk",
                )
            ],
            strict_mode=False,
        )

        self.assertIn("hostile", graph["segments_by_id"])

    def test_prefers_low_stress_detour_over_direct_uncomfortable_road(self) -> None:
        route = build_route(
            [
                make_segment(
                    "direct",
                    [{"lat": 0.0, "lon": 0.0}, {"lat": 0.0, "lon": 0.003}],
                    "not-suitable",
                    "uncertain",
                    20,
                    "secondary",
                ),
                make_segment(
                    "detour-1",
                    [{"lat": 0.0, "lon": 0.0}, {"lat": 0.001, "lon": 0.0}],
                    "low-stress",
                    "yes",
                    72,
                    "residential",
                ),
                make_segment(
                    "detour-2",
                    [{"lat": 0.001, "lon": 0.0}, {"lat": 0.001, "lon": 0.003}],
                    "low-stress",
                    "yes",
                    72,
                    "residential",
                ),
                make_segment(
                    "detour-3",
                    [{"lat": 0.001, "lon": 0.003}, {"lat": 0.0, "lon": 0.003}],
                    "low-stress",
                    "yes",
                    72,
                    "residential",
                ),
            ],
            start={"lat": 0.0, "lon": 0.0},
            end={"lat": 0.0, "lon": 0.003},
        )

        self.assertNotIn("direct", [segment["id"] for segment in route["segments"]])
        self.assertGreater(route["average_comfort"], 60)
        self.assertEqual(route["routing_mode"], "strict")

    def test_falls_back_to_hostile_route_when_no_bike_safe_path_exists(self) -> None:
        route = build_route(
            [
                make_segment(
                    "hostile-link",
                    [{"lat": 0.0, "lon": 0.0}, {"lat": 0.0, "lon": 0.001}],
                    "not-suitable",
                    "no",
                    5,
                    "trunk",
                )
            ],
            start={"lat": 0.0, "lon": 0.0},
            end={"lat": 0.0, "lon": 0.001},
        )

        self.assertEqual([segment["id"] for segment in route["segments"]], ["hostile-link"])
        self.assertEqual(route["routing_mode"], "fallback")
        self.assertIn("safest available connected route", route["explanation"][0])

    def test_snaps_picked_point_to_nearest_road_segment(self) -> None:
        route = build_route(
            [
                make_segment(
                    "main-link",
                    [{"lat": 0.0, "lon": 0.0}, {"lat": 0.0, "lon": 0.002}],
                    "low-stress",
                    "yes",
                    70,
                    "residential",
                )
            ],
            start={"lat": 0.0004, "lon": 0.001},
            end={"lat": 0.0, "lon": 0.002},
        )

        self.assertAlmostEqual(route["snapped_start"]["lat"], 0.0, places=5)
        self.assertAlmostEqual(route["snapped_start"]["lon"], 0.001, places=5)

    def test_raises_when_no_connected_route_exists(self) -> None:
        with self.assertRaisesRegex(ValueError, "No connected route"):
            build_route(
                [
                    make_segment(
                        "left",
                        [{"lat": 0.0, "lon": 0.0}, {"lat": 0.0, "lon": 0.001}],
                        "low-stress",
                        "yes",
                        70,
                        "residential",
                    ),
                    make_segment(
                        "right",
                        [{"lat": 0.01, "lon": 0.01}, {"lat": 0.01, "lon": 0.011}],
                        "low-stress",
                        "yes",
                        70,
                        "residential",
                    ),
                ],
                start={"lat": 0.0, "lon": 0.0},
                end={"lat": 0.01, "lon": 0.011},
            )


if __name__ == "__main__":
    unittest.main()
