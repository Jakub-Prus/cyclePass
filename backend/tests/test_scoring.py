import unittest

from backend.app.main import build_output_segments
from backend.app.osm import split_ways_into_subsegments
from backend.app.scoring import classify_way, parse_maxspeed_to_kph


class ScoringTests(unittest.TestCase):
    def test_parses_mph_speed_limits(self) -> None:
        self.assertEqual(parse_maxspeed_to_kph("20 mph"), 32)

    def test_classifies_protected_cycle_infrastructure(self) -> None:
        result = classify_way(
            {
                "highway": "cycleway",
                "cycleway": "track",
                "bicycle": "designated",
            }
        )
        self.assertEqual(result["bike_crossable_class"], "protected")
        self.assertEqual(result["bike_allowed"], "yes")
        self.assertGreaterEqual(result["bike_comfort"], 80)

    def test_classifies_calm_residential_street_as_low_stress(self) -> None:
        result = classify_way(
            {
                "highway": "residential",
                "maxspeed": "30",
                "sidewalk": "both",
            }
        )
        self.assertEqual(result["bike_crossable_class"], "low-stress")
        self.assertNotEqual(result["bike_allowed"], "no")

    def test_classifies_bike_allowed_paths_as_shared(self) -> None:
        result = classify_way(
            {
                "highway": "path",
                "bicycle": "yes",
                "segregated": "no",
            }
        )
        self.assertEqual(result["bike_crossable_class"], "shared")

    def test_classifies_surfaced_unmapped_footway_as_shared_but_uncertain(self) -> None:
        result = classify_way(
            {
                "highway": "footway",
                "surface": "paving_stones",
                "lit": "yes",
            }
        )
        self.assertEqual(result["bike_crossable_class"], "shared")
        self.assertEqual(result["bike_allowed"], "uncertain")
        self.assertGreaterEqual(result["bike_comfort"], 55)

    def test_classifies_sidewalk_footway_as_shared_without_surface_tag(self) -> None:
        result = classify_way(
            {
                "highway": "footway",
                "footway": "sidewalk",
            }
        )
        self.assertEqual(result["bike_crossable_class"], "shared")
        self.assertEqual(result["bike_allowed"], "uncertain")
        self.assertGreaterEqual(result["bike_comfort"], 50)

    def test_classifies_bicycle_no_trunk_road_as_not_suitable(self) -> None:
        result = classify_way(
            {
                "highway": "trunk",
                "bicycle": "no",
                "maxspeed": "80",
            }
        )
        self.assertEqual(result["bike_crossable_class"], "not-suitable")
        self.assertEqual(result["bike_allowed"], "no")
        self.assertLessEqual(result["bike_comfort"], 10)

    def test_splits_long_way_into_multiple_subsegments(self) -> None:
        way = {
            "id": 123,
            "type": "way",
            "tags": {"highway": "residential"},
            "geometry": [
                {"lat": 52.2297, "lon": 21.0122},
                {"lat": 52.2297, "lon": 21.0126},
                {"lat": 52.2297, "lon": 21.0130},
            ],
        }

        segments = split_ways_into_subsegments([way])

        self.assertGreaterEqual(len(segments), 2)
        self.assertEqual(segments[0]["parent_way_id"], 123)
        self.assertEqual(segments[0]["id"], "123-0")
        self.assertGreaterEqual(len(segments[0]["geometry"]), 2)

    def test_adds_sidewalk_overlay_for_primary_roads_with_sidewalks(self) -> None:
        way = {
            "id": "500-0",
            "parent_way_id": 500,
            "geometry": [
                {"lat": 52.2297, "lon": 21.0122},
                {"lat": 52.2297, "lon": 21.0126},
            ],
            "tags": {
                "highway": "primary",
                "sidewalk": "both",
                "surface": "paving_stones",
                "name": "Test Road",
            },
        }

        output_segments = build_output_segments(way)

        self.assertEqual(len(output_segments), 2)
        self.assertEqual(output_segments[0]["score"]["bike_crossable_class"], "not-suitable")
        self.assertEqual(output_segments[1]["id"], "500-0-sidewalk")
        self.assertEqual(output_segments[1]["score"]["bike_crossable_class"], "shared")
        self.assertEqual(output_segments[1]["score"]["bike_allowed"], "uncertain")


if __name__ == "__main__":
    unittest.main()
