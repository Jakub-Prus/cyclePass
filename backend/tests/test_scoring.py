import unittest

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


if __name__ == "__main__":
    unittest.main()
