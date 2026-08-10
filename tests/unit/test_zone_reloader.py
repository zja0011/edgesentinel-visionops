import json
import os
import tempfile
import unittest

from packages.analytics.zone_reloader import ZoneConfigReloader


class ZoneConfigReloaderTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.path = os.path.join(
            self.temporary.name,
            "zones.json",
        )
        self.write(0.49)

    def tearDown(self):
        self.temporary.cleanup()

    def write(self, right_edge):
        with open(self.path, "w", encoding="utf-8") as output:
            json.dump(
                {
                    "coordinate_space": "normalized",
                    "zones": [
                        {
                            "id": "left_zone",
                            "name": "Left Zone",
                            "polygon": [
                                [0.0, 0.0],
                                [right_edge, 0.0],
                                [right_edge, 1.0],
                                [0.0, 1.0],
                            ],
                            "target_classes": ["person"],
                            "anchor": "bottom_center",
                            "minimum_hits": 3,
                            "max_missed_frames": 2,
                        }
                    ],
                },
                output,
            )

    def test_initial_snapshot_exposes_active_version(self):
        reloader = ZoneConfigReloader(
            self.path,
            check_interval_frames=5,
        )

        snapshot = reloader.snapshot()

        self.assertEqual(snapshot["status"], "active")
        self.assertEqual(snapshot["zone_count"], 1)
        self.assertEqual(len(snapshot["version"]), 64)
        self.assertEqual(snapshot["reload_count"], 0)
        self.assertEqual(snapshot["check_interval_frames"], 5)

    def test_reloads_only_after_the_poll_interval(self):
        reloader = ZoneConfigReloader(
            self.path,
            check_interval_frames=5,
        )
        original_version = reloader.version
        self.write(0.4)

        self.assertIsNone(reloader.poll(4))
        result = reloader.poll(5)

        self.assertEqual(result["status"], "reloaded")
        self.assertNotEqual(reloader.version, original_version)
        self.assertEqual(reloader.reload_count, 1)
        self.assertEqual(reloader.last_reload_frame, 5)
        self.assertEqual(
            reloader.engine.zones[0].polygon[1],
            (0.4, 0.0),
        )

    def test_invalid_update_keeps_the_last_valid_engine(self):
        reloader = ZoneConfigReloader(
            self.path,
            check_interval_frames=1,
        )
        original_version = reloader.version
        original_engine = reloader.engine
        with open(self.path, "w", encoding="utf-8") as output:
            output.write("{invalid")

        result = reloader.poll(1)

        self.assertEqual(result["status"], "failed")
        self.assertIs(reloader.engine, original_engine)
        self.assertEqual(reloader.version, original_version)
        self.assertEqual(reloader.snapshot()["status"], "degraded")
        self.assertIsNone(reloader.poll(2))

    def test_valid_update_recovers_after_an_invalid_file(self):
        reloader = ZoneConfigReloader(
            self.path,
            check_interval_frames=1,
        )
        with open(self.path, "w", encoding="utf-8") as output:
            output.write("{invalid")
        reloader.poll(1)
        self.write(0.45)

        result = reloader.poll(2)

        self.assertEqual(result["status"], "reloaded")
        self.assertEqual(reloader.snapshot()["status"], "active")
        self.assertIsNone(reloader.snapshot()["last_error"])


if __name__ == "__main__":
    unittest.main()
