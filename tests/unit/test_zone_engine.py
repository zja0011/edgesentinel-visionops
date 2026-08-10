import unittest

from packages.analytics.zone_engine import (
    Zone,
    ZoneEngine,
    normalized_anchor,
    point_in_polygon,
)
from packages.vision.schemas import Detection


class ZoneEngineTests(unittest.TestCase):
    def setUp(self):
        self.left_zone = Zone(
            zone_id="left",
            name="Left",
            polygon=[(0, 0), (0.5, 0), (0.5, 1), (0, 1)],
            target_classes=["person"],
            anchor="bottom_center",
            minimum_hits=3,
            max_missed_frames=2,
        )
        self.engine = ZoneEngine([self.left_zone])

    def test_point_inside_outside_and_boundary(self):
        polygon = [(0, 0), (0.5, 0), (0.5, 1), (0, 1)]
        self.assertTrue(point_in_polygon((0.25, 0.5), polygon))
        self.assertFalse(point_in_polygon((0.75, 0.5), polygon))
        self.assertTrue(point_in_polygon((0.5, 0.5), polygon))

    def test_bottom_center_anchor_is_normalized(self):
        self.assertEqual(
            normalized_anchor((100, 100, 300, 400), 800, 800, "bottom_center"),
            (0.25, 0.5),
        )

    def test_annotation_respects_class_filter(self):
        person = Detection(1, "person", 0.9, 10, 10, 30, 90)
        chair = Detection(62, "chair", 0.9, 10, 10, 30, 90)
        self.engine.annotate_detections([person, chair], 100, 100)

        self.assertEqual(person.zone_ids, ["left"])
        self.assertEqual(chair.zone_ids, [])

    def test_snapshot_counts_confirmed_tracks(self):
        tracks = [
            {
                "track_id": 4,
                "class_name": "person",
                "bbox": [10, 10, 30, 90],
                "hits": 8,
                "missed_frames": 0,
            },
            {
                "track_id": 5,
                "class_name": "person",
                "bbox": [70, 10, 90, 90],
                "hits": 8,
                "missed_frames": 0,
            },
            {
                "track_id": 6,
                "class_name": "person",
                "bbox": [10, 10, 30, 90],
                "hits": 2,
                "missed_frames": 0,
            },
        ]

        snapshot = self.engine.snapshot(tracks, 100, 100)[0]
        self.assertEqual(snapshot["current_count"], 1)
        self.assertEqual(snapshot["track_ids"], [4])

    def test_snapshot_keeps_short_miss_and_drops_long_miss(self):
        short_miss = {
            "track_id": 4,
            "class_name": "person",
            "bbox": [10, 10, 30, 90],
            "hits": 8,
            "missed_frames": 2,
        }
        long_miss = dict(short_miss, track_id=5, missed_frames=3)

        snapshot = self.engine.snapshot([short_miss, long_miss], 100, 100)[0]
        self.assertEqual(snapshot["track_ids"], [4])


if __name__ == "__main__":
    unittest.main()
