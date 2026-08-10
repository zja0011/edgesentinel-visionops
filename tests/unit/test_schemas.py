import json
import unittest

from packages.vision.schemas import (
    Detection,
    FrameResult,
    beijing_timestamp,
)


class SchemaTests(unittest.TestCase):
    def test_detection_serialization(self):
        detection = Detection(1, "person", 0.93456789, 1.234, 2.345, 3.456, 4.567)

        self.assertEqual(
            detection.to_dict(),
            {
                "class_id": 1,
                "class_name": "person",
                "confidence": 0.934568,
                "bbox": [1.23, 2.35, 3.46, 4.57],
                "track_id": None,
                "zone_ids": [],
            },
        )

    def test_frame_result_is_json_serializable(self):
        result = FrameResult(
            frame_id=7,
            timestamp="2026-07-22T20:00:00.000+08:00",
            camera_id="camera_01",
            source="/dev/video0",
            width=640,
            height=480,
            inference_ms=42.1239,
            detections=[Detection(1, "person", 0.9, 1, 2, 3, 4)],
        )

        payload = result.to_dict()
        encoded = json.dumps(payload)

        self.assertEqual(payload["schema_version"], "1.6")
        self.assertEqual(payload["inference_ms"], 42.124)
        self.assertEqual(payload["analytics"], {})
        self.assertIn('"person"', encoded)

    def test_timestamp_is_beijing_iso_8601(self):
        value = beijing_timestamp()
        self.assertTrue(value.endswith("+08:00"))
        self.assertEqual(len(value), 29)


if __name__ == "__main__":
    unittest.main()
