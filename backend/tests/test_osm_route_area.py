import unittest
import urllib.error
from email.message import Message
from unittest.mock import patch

from backend.app.osm import (
    build_route_bbox,
    compute_overpass_retry_delay_seconds,
    fetch_overpass_ways,
    fetch_tile_ways,
    order_route_tiles,
    select_route_tiles_within_corridor,
    split_bbox_into_tiles,
)


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

    def test_order_route_tiles_prefers_tiles_along_route_line(self) -> None:
        ordered_tiles = order_route_tiles(
            [
                {"south": 52.001, "west": 21.01, "north": 52.002, "east": 21.011},
                {"south": 52.0, "west": 21.0, "north": 52.001, "east": 21.001},
                {"south": 52.01, "west": 21.0, "north": 52.011, "east": 21.001},
            ],
            start={"lat": 52.0, "lon": 21.0},
            end={"lat": 52.01, "lon": 21.01},
        )

        self.assertEqual(ordered_tiles[0]["south"], 52.0)
        self.assertEqual(ordered_tiles[1]["south"], 52.001)
        self.assertEqual(ordered_tiles[2]["south"], 52.01)

    def test_fetch_tile_ways_splits_timed_out_tiles_into_subtiles(self) -> None:
        tile_bbox = {
            "south": 52.0,
            "west": 21.0,
            "north": 52.01,
            "east": 21.01,
        }
        timeout_error = urllib.error.HTTPError(
            url="https://overpass-api.de/api/interpreter",
            code=504,
            msg="Gateway Timeout",
            hdrs=None,
            fp=None,
        )

        with patch(
            "backend.app.osm.fetch_overpass_ways",
            side_effect=[
                timeout_error,
                [{"id": 1, "type": "way", "geometry": [{"lat": 52.0, "lon": 21.0}, {"lat": 52.0, "lon": 21.005}]}],
                [{"id": 2, "type": "way", "geometry": [{"lat": 52.0, "lon": 21.005}, {"lat": 52.005, "lon": 21.01}]}],
                [{"id": 3, "type": "way", "geometry": [{"lat": 52.005, "lon": 21.0}, {"lat": 52.01, "lon": 21.005}]}],
                [{"id": 4, "type": "way", "geometry": [{"lat": 52.005, "lon": 21.005}, {"lat": 52.01, "lon": 21.01}]}],
            ],
        ):
            ways = fetch_tile_ways(tile_bbox, target_tile_size_m=1_200)

        self.assertEqual([way["id"] for way in ways], [1, 2, 3, 4])

    def test_fetch_tile_ways_stops_split_fetches_after_reaching_way_limit(self) -> None:
        tile_bbox = {
            "south": 52.0,
            "west": 21.0,
            "north": 52.01,
            "east": 21.01,
        }
        timeout_error = urllib.error.HTTPError(
            url="https://overpass-api.de/api/interpreter",
            code=504,
            msg="Gateway Timeout",
            hdrs=None,
            fp=None,
        )

        with patch(
            "backend.app.osm.fetch_overpass_ways",
            side_effect=[
                timeout_error,
                [{"id": 1, "type": "way", "geometry": [{"lat": 52.0, "lon": 21.0}, {"lat": 52.0, "lon": 21.005}]}],
                [{"id": 2, "type": "way", "geometry": [{"lat": 52.0, "lon": 21.005}, {"lat": 52.005, "lon": 21.01}]}],
                [{"id": 3, "type": "way", "geometry": [{"lat": 52.005, "lon": 21.0}, {"lat": 52.01, "lon": 21.005}]}],
            ],
        ) as fetch_overpass_ways:
            ways = fetch_tile_ways(
                tile_bbox,
                target_tile_size_m=1_200,
                start={"lat": 52.0, "lon": 21.0},
                end={"lat": 52.01, "lon": 21.01},
                way_limit=2,
            )

        self.assertEqual([way["id"] for way in ways], [1, 2])
        self.assertEqual(fetch_overpass_ways.call_count, 3)

    def test_select_route_tiles_within_corridor_skips_far_diagonal_tiles(self) -> None:
        selected_tiles = select_route_tiles_within_corridor(
            [
                {"south": 52.0, "west": 21.0, "north": 52.01, "east": 21.01},
                {"south": 52.0, "west": 21.01, "north": 52.01, "east": 21.02},
                {"south": 52.02, "west": 21.0, "north": 52.03, "east": 21.01},
            ],
            start={"lat": 52.0, "lon": 21.0},
            end={"lat": 52.02, "lon": 21.02},
            corridor_padding_m=300,
        )

        self.assertEqual(len(selected_tiles), 2)
        self.assertEqual(selected_tiles[0]["west"], 21.0)
        self.assertEqual(selected_tiles[1]["west"], 21.01)

    def test_fetch_overpass_ways_retries_after_rate_limit(self) -> None:
        rate_limit_headers = Message()
        rate_limit_headers["Retry-After"] = "0"
        rate_limit_error = urllib.error.HTTPError(
            url="https://overpass-api.de/api/interpreter",
            code=429,
            msg="Too Many Requests",
            hdrs=rate_limit_headers,
            fp=None,
        )

        class FakeResponse:
            def __enter__(self) -> "FakeResponse":
                return self

            def __exit__(self, exc_type, exc, tb) -> None:
                return None

            def read(self) -> bytes:
                return b'{"elements":[{"type":"way","id":1,"geometry":[{"lat":52.0,"lon":21.0},{"lat":52.0,"lon":21.01}]}]}'

        with patch("backend.app.osm.urllib.request.urlopen", side_effect=[rate_limit_error, FakeResponse()]), patch(
            "backend.app.osm.time.sleep"
        ) as sleep:
            ways = fetch_overpass_ways("[out:json];way(1,2,3,4);out geom;")

        self.assertEqual([way["id"] for way in ways], [1])
        sleep.assert_called_once_with(0.0)

    def test_compute_overpass_retry_delay_uses_exponential_backoff_without_header(self) -> None:
        rate_limit_error = urllib.error.HTTPError(
            url="https://overpass-api.de/api/interpreter",
            code=429,
            msg="Too Many Requests",
            hdrs=Message(),
            fp=None,
        )

        self.assertEqual(compute_overpass_retry_delay_seconds(rate_limit_error, 0), 2.0)
        self.assertEqual(compute_overpass_retry_delay_seconds(rate_limit_error, 1), 4.0)

    def test_fetch_tile_ways_refetches_slow_tiles_as_subtiles(self) -> None:
        tile_bbox = {
            "south": 52.0,
            "west": 21.0,
            "north": 52.01,
            "east": 21.01,
        }
        slow_ways = [
            {
                "id": way_id,
                "type": "way",
                "geometry": [{"lat": 52.0, "lon": 21.0}, {"lat": 52.0, "lon": 21.001}],
            }
            for way_id in range(100, 180)
        ]
        split_ways = [
            [{"id": 1, "type": "way", "geometry": [{"lat": 52.0, "lon": 21.0}, {"lat": 52.0, "lon": 21.005}]}],
            [{"id": 2, "type": "way", "geometry": [{"lat": 52.0, "lon": 21.005}, {"lat": 52.005, "lon": 21.01}]}],
            [{"id": 3, "type": "way", "geometry": [{"lat": 52.005, "lon": 21.0}, {"lat": 52.01, "lon": 21.005}]}],
            [{"id": 4, "type": "way", "geometry": [{"lat": 52.005, "lon": 21.005}, {"lat": 52.01, "lon": 21.01}]}],
        ]

        with patch("backend.app.osm.fetch_overpass_ways", side_effect=[slow_ways, *split_ways]), patch(
            "backend.app.osm.time.monotonic",
            side_effect=[0.0, 9.0, 10.0, 10.1, 11.0, 11.1, 12.0, 12.1, 13.0, 13.1],
        ):
            ways = fetch_tile_ways(
                tile_bbox,
                target_tile_size_m=1_200,
                start={"lat": 52.0, "lon": 21.0},
                end={"lat": 52.01, "lon": 21.01},
                way_limit=4,
            )

        self.assertEqual([way["id"] for way in ways], [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
