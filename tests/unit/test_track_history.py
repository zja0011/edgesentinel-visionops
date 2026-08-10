import unittest

from packages.analytics.track_history import build_track_history
from packages.vision.schemas import Detection


class TrackHistoryTests(unittest.TestCase):
    def test_normalizes_samples_and_labels_movement(self):
        detection = Detection(
            1,
            "person",
            0.9,
            40,
            20,
            60,
            80,
            track_id=7,
            zone_ids=["right_zone"],
        )
        track = {
            "track_id": 7,
            "class_name": "person",
            "confidence": 0.9,
            "hits": 40,
            "missed_frames": 0,
            "first_seen_frame": 1,
            "last_seen_frame": 40,
            "trajectory": [
                {
                    "frame_id": frame_id,
                    "center_x": 10 + frame_id,
                    "center_y": 50,
                }
                for frame_id in range(1, 41)
            ],
        }

        result = build_track_history(
            [track],
            [detection],
            width=100,
            height=100,
            max_points=10,
        )

        summary = result["tracks"][0]
        self.assertEqual(result["visible_track_count"], 1)
        self.assertEqual(summary["movement"], "right")
        self.assertGreater(summary["displacement"], 0.3)
        self.assertEqual(summary["observation_count"], 40)
        self.assertEqual(summary["sampled_point_count"], 10)
        self.assertEqual(
            summary["current_zone_ids"],
            ["right_zone"],
        )
        self.assertEqual(summary["points"][0]["frame_id"], 1)
        self.assertEqual(summary["points"][-1]["frame_id"], 40)
        self.assertNotIn("bbox", summary)

    def test_marks_small_jitter_stationary_and_retains_missed(self):
        result = build_track_history(
            [
                {
                    "track_id": 3,
                    "class_name": "bottle",
                    "confidence": 0.8,
                    "hits": 2,
                    "missed_frames": 1,
                    "first_seen_frame": 5,
                    "last_seen_frame": 6,
                    "trajectory": [
                        {
                            "frame_id": 5,
                            "center_x": 50,
                            "center_y": 50,
                        },
                        {
                            "frame_id": 6,
                            "center_x": 51,
                            "center_y": 51,
                        },
                    ],
                }
            ],
            [],
            width=100,
            height=100,
        )

        summary = result["tracks"][0]
        self.assertFalse(summary["visible"])
        self.assertEqual(summary["movement"], "stationary")
        self.assertEqual(result["visible_track_count"], 0)


if __name__ == "__main__":
    unittest.main()
