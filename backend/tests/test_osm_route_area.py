import unittest

from backend.app.osm import build_route_bbox, split_bbox_into_tiles


class OsmRouteAreaTests(unittest.TestCase):
    def test_build_route_bbox_adds_padding_around_endpoints(self) -> None:
        bbox = build_route_bbox(
            start={"lat": 52.0, "lon": 21.0},
            end={"lat": 52.002, "lon": 21.004},
            padding_m=300,
        )

        self.assertLess(bbox["south"], 52.0)
        self.assertLess(bbox["west"], 21.0)
        self.assertGreater(bbox["north"], 52.002)
        self.assertGreater(bbox["east"], 21.004)

    def test_split_bbox_into_tiles_breaks_large_area_into_multiple_tiles(self) -> None:
        tiles = split_bbox_into_tiles(
            {
                "south": 52.0,
                "west": 21.0,
                "north": 52.03,
                "east": 21.03,
            },
            target_tile_size_m=1_200,
        )

        self.assertGreater(len(tiles), 1)
        self.assertEqual(tiles[0]["south"], 52.0)
        self.assertEqual(tiles[-1]["east"], 21.03)


if __name__ == "__main__":
    unittest.main()
