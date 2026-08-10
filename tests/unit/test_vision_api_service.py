import json
import os
import tempfile
import unittest

from packages.api.vision_service import (
    LiveFrameService,
    VisionApiUnavailable,
    VisionQueryService,
)


class VisionQueryServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.state_path = os.path.join(
            self.temporary.name,
            "current-vision.json",
        )

    def tearDown(self):
        self.temporary.cleanup()

    def write_state(self):
        with open(
            self.state_path,
            "w",
            encoding="utf-8",
        ) as state_file:
            json.dump(
                {
                    "schema_version": "1.6",
                    "frame_id": 42,
                    "timestamp": "2026-07-25T18:00:00+08:00",
                    "camera_id": "camera_01",
                    "detections": [
                        {
                            "class_name": "bottle",
                            "confidence": 0.92,
                            "bbox": [1, 2, 3, 4],
                            "zone_ids": ["left_zone"],
                        },
                        {
                            "class_name": "bottle",
                            "confidence": 0.42,
                            "bbox": [5, 6, 7, 8],
                            "zone_ids": ["right_zone"],
                        },
                    ],
                    "analytics": {
                        "people": {
                            "current_people": 2,
                            "visible_people": 1,
                            "active_track_ids": [3, 4],
                        },
                        "zone_config": {
                            "enabled": True,
                            "status": "active",
                            "version": "a" * 64,
                            "zone_count": 2,
                            "reload_count": 1,
                            "last_reload_frame": 30,
                            "check_interval_frames": 30,
                            "last_error": None,
                        },
                        "zones": [
                            {
                                "zone_id": "left_zone",
                                "name": "Left Zone",
                                "current_count": 2,
                                "track_ids": [3, 4],
                            },
                            {
                                "zone_id": "right_zone",
                                "name": "Right Zone",
                                "current_count": 0,
                                "track_ids": [],
                            },
                        ],
                        "inventory": {
                            "target_classes": ["bottle", "cup"],
                            "current_counts": {
                                "bottle": 1,
                                "cup": 0,
                            },
                            "visible_counts": {
                                "bottle": 1,
                                "cup": 0,
                            },
                            "active_track_ids": {
                                "bottle": [8],
                            },
                        },
                        "track_history": {
                            "retained_track_count": 1,
                            "visible_track_count": 1,
                            "max_points_per_track": 30,
                            "tracks": [
                                {
                                    "track_id": 3,
                                    "class_name": "person",
                                    "confidence": 0.9,
                                    "visible": True,
                                    "hits": 20,
                                    "missed_frames": 0,
                                    "first_seen_frame": 1,
                                    "last_seen_frame": 42,
                                    "observation_count": 20,
                                    "sampled_point_count": 2,
                                    "movement": "right",
                                    "displacement": 0.4,
                                    "current_zone_ids": [
                                        "left_zone"
                                    ],
                                    "points": [
                                        {
                                            "frame_id": 1,
                                            "x": 0.1,
                                            "y": 0.8,
                                        },
                                        {
                                            "frame_id": 42,
                                            "x": 0.5,
                                            "y": 0.8,
                                        },
                                    ],
                                }
                            ],
                        },
                        "performance": {
                            "status": "MEETS_TARGET",
                            "total_frames": 42,
                            "sample_count": 42,
                            "window_size_frames": 120,
                            "processing_fps": 11.25,
                            "frame_interval_ms": 88.889,
                            "pipeline_latency_ms": {
                                "latest": 43.0,
                                "average": 45.0,
                                "p50": 44.0,
                                "p95": 55.0,
                                "maximum": 60.0,
                            },
                            "targets": {
                                "minimum_fps": 5.0,
                                "maximum_p95_ms": 200.0,
                                "fps_met": True,
                                "p95_met": True,
                                "all_met": True,
                            },
                            "read_only": True,
                        },
                    },
                },
                state_file,
            )

    def test_returns_people_with_freshness_metadata(self):
        self.write_state()
        payload = VisionQueryService(
            self.state_path,
            max_age_seconds=30,
        ).get_people()

        self.assertEqual(payload["schema_version"], "1.0")
        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["current_people"], 2)
        self.assertEqual(payload["camera_id"], "camera_01")
        self.assertFalse(payload["stale"])
        self.assertEqual(
            payload["zone_config"]["version"],
            "a" * 64,
        )

    def test_returns_only_nonzero_stable_objects(self):
        self.write_state()
        payload = VisionQueryService(
            self.state_path,
            max_age_seconds=30,
        ).get_objects()

        self.assertEqual(payload["total_current"], 1)
        self.assertEqual(
            payload["objects"],
            [{"class_name": "bottle", "count": 1}],
        )

    def test_returns_bounded_vision_performance(self):
        self.write_state()

        payload = VisionQueryService(
            self.state_path,
            max_age_seconds=30,
        ).get_performance()

        self.assertEqual(payload["processing_fps"], 11.25)
        self.assertEqual(
            payload["pipeline_latency_ms"]["p95"],
            55.0,
        )
        self.assertTrue(payload["targets"]["all_met"])
        self.assertTrue(payload["read_only"])

    def test_returns_complete_or_filtered_inventory(self):
        self.write_state()
        service = VisionQueryService(
            self.state_path,
            max_age_seconds=30,
        )

        complete = service.get_inventory()
        bottle = service.get_inventory(object_class="bottle")

        self.assertEqual(complete["target_class_count"], 2)
        self.assertEqual(complete["items"][1]["class_name"], "cup")
        self.assertEqual(complete["items"][1]["current_count"], 0)
        self.assertEqual(bottle["selected_object_class"], "bottle")
        self.assertEqual(bottle["total_current"], 1)
        self.assertEqual(bottle["total_visible"], 1)
        self.assertEqual(
            bottle["items"][0]["active_track_ids"],
            [8],
        )

    def test_compares_expected_inventory_without_writing(self):
        self.write_state()
        payload = VisionQueryService(
            self.state_path,
            max_age_seconds=30,
        ).compare_inventory({"bottle": 2})

        self.assertFalse(payload["matches"])
        self.assertEqual(payload["total_expected"], 2)
        self.assertEqual(payload["total_current"], 1)
        self.assertEqual(payload["total_missing"], 1)
        self.assertEqual(
            payload["comparisons"][0]["active_track_ids"],
            [8],
        )
        self.assertTrue(payload["read_only"])

    def test_counts_latest_frame_objects_with_filters(self):
        self.write_state()
        payload = VisionQueryService(
            self.state_path,
            max_age_seconds=30,
        ).count_objects(
            ["bottle"],
            minimum_confidence=0.5,
            zone_id="left_zone",
        )

        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["total_count"], 1)
        self.assertEqual(
            payload["counts"],
            [{"class_name": "bottle", "count": 1}],
        )
        self.assertEqual(payload["selected_zone_id"], "left_zone")
        self.assertNotIn("detections", payload)

    def test_returns_bounded_track_history(self):
        self.write_state()
        payload = VisionQueryService(
            self.state_path,
            max_age_seconds=30,
        ).get_track_history(track_id=3)

        self.assertEqual(payload["status"], "available")
        self.assertEqual(payload["track_count"], 1)
        self.assertEqual(payload["tracks"][0]["movement"], "right")
        self.assertEqual(
            payload["tracks"][0]["points"][-1]["x"],
            0.5,
        )
        self.assertNotIn("bbox", json.dumps(payload))

    def test_returns_all_or_one_current_zone(self):
        self.write_state()
        service = VisionQueryService(
            self.state_path,
            max_age_seconds=30,
        )

        all_zones = service.get_zones()
        left_zone = service.get_zones(zone_id="left_zone")

        self.assertEqual(all_zones["zone_count"], 2)
        self.assertEqual(all_zones["unique_current_count"], 2)
        self.assertEqual(left_zone["zone_count"], 1)
        self.assertEqual(left_zone["selected_zone_id"], "left_zone")
        self.assertEqual(
            left_zone["zones"][0]["track_ids"],
            [3, 4],
        )

    def test_reports_missing_state_as_unavailable(self):
        service = VisionQueryService(self.state_path)

        with self.assertRaises(VisionApiUnavailable):
            service.get_people()
        with self.assertRaises(VisionApiUnavailable):
            service.get_objects()
        with self.assertRaises(VisionApiUnavailable):
            service.get_zones()
        with self.assertRaises(VisionApiUnavailable):
            service.get_inventory()
        with self.assertRaises(VisionApiUnavailable):
            service.compare_inventory({"bottle": 1})
        with self.assertRaises(VisionApiUnavailable):
            service.count_objects(["bottle"])
        with self.assertRaises(VisionApiUnavailable):
            service.get_track_history(track_id=1)

    def test_live_frame_reports_size_age_and_freshness(self):
        frame_path = os.path.join(
            self.temporary.name,
            "current-frame.jpg",
        )
        with open(frame_path, "wb") as frame_file:
            frame_file.write(b"\xff\xd8valid-jpeg")

        payload = LiveFrameService(
            frame_path,
            max_age_seconds=30,
        ).get()

        self.assertEqual(payload["path"], frame_path)
        self.assertEqual(payload["size"], 12)
        self.assertEqual(payload["content"], b"\xff\xd8valid-jpeg")
        self.assertFalse(payload["stale"])

    def test_live_frame_rejects_missing_and_invalid_jpeg(self):
        frame_path = os.path.join(
            self.temporary.name,
            "current-frame.jpg",
        )
        service = LiveFrameService(frame_path)
        with self.assertRaises(VisionApiUnavailable):
            service.get()

        with open(frame_path, "wb") as frame_file:
            frame_file.write(b"not-a-jpeg")
        with self.assertRaises(VisionApiUnavailable):
            service.get()


if __name__ == "__main__":
    unittest.main()
