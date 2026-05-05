import unittest
from unittest.mock import patch

from backend.app.mapillary import build_bbox, find_nearest_mapillary_image


class MapillaryLookupTests(unittest.TestCase):
    def test_build_bbox_wraps_point_with_expected_ordering(self) -> None:
        bbox = build_bbox({"lat": 52.0, "lon": 16.0}, radius_m=20.0)

        west, south, east, north = bbox
        self.assertLess(west, east)
        self.assertLess(south, north)
        self.assertLess(west, 16.0)
        self.assertGreater(east, 16.0)
        self.assertLess(south, 52.0)
        self.assertGreater(north, 52.0)

    @patch("backend.app.mapillary.ensure_mapillary_is_configured")
    @patch("backend.app.mapillary.fetch_images_in_bbox")
    def test_selects_nearest_image_from_first_radius_with_matches(self, fetch_images_in_bbox, _ensure_configured) -> None:
        fetch_images_in_bbox.side_effect = [
            [
                {
                    "id": "far-image",
                    "captured_at": "2024-01-01T00:00:00Z",
                    "thumb_1024_url": "https://example.com/far.jpg",
                    "computed_geometry": {"type": "Point", "coordinates": [16.002, 52.0]},
                },
                {
                    "id": "near-image",
                    "captured_at": "2024-01-02T00:00:00Z",
                    "thumb_1024_url": "https://example.com/near.jpg",
                    "computed_geometry": {"type": "Point", "coordinates": [16.0001, 52.0]},
                },
            ]
        ]

        result = find_nearest_mapillary_image({"lat": 52.0, "lon": 16.0})

        self.assertEqual(result["image_id"], "near-image")
        self.assertEqual(result["viewer_url"], "https://www.mapillary.com/app/?pKey=near-image")
        self.assertLess(result["distance_m"], 20.0)
        fetch_images_in_bbox.assert_called_once()

    @patch("backend.app.mapillary.ensure_mapillary_is_configured")
    @patch("backend.app.mapillary.fetch_images_in_bbox")
    def test_expands_to_second_radius_when_initial_search_is_empty(self, fetch_images_in_bbox, _ensure_configured) -> None:
        fetch_images_in_bbox.side_effect = [
            [],
            [
                {
                    "id": "fallback-image",
                    "captured_at": "2024-01-03T00:00:00Z",
                    "thumb_1024_url": "https://example.com/fallback.jpg",
                    "computed_geometry": {"type": "Point", "coordinates": [16.0002, 52.0]},
                }
            ],
        ]

        result = find_nearest_mapillary_image({"lat": 52.0, "lon": 16.0})

        self.assertEqual(result["image_id"], "fallback-image")
        self.assertEqual(fetch_images_in_bbox.call_count, 2)


if __name__ == "__main__":
    unittest.main()
