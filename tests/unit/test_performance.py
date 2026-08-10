import unittest

from packages.analytics.performance import VisionPerformanceTracker


class VisionPerformanceTrackerTests(unittest.TestCase):
    def test_reports_rolling_fps_latency_and_targets(self):
        tracker = VisionPerformanceTracker(window_size=4)

        tracker.update(40.0, monotonic_time=10.0)
        tracker.update(50.0, monotonic_time=10.1)
        tracker.update(60.0, monotonic_time=10.2)
        result = tracker.update(70.0, monotonic_time=10.3)

        self.assertEqual(result["status"], "MEETS_TARGET")
        self.assertEqual(result["total_frames"], 4)
        self.assertEqual(result["sample_count"], 4)
        self.assertAlmostEqual(
            result["processing_fps"],
            10.0,
            places=2,
        )
        self.assertEqual(
            result["pipeline_latency_ms"]["average"],
            55.0,
        )
        self.assertEqual(
            result["pipeline_latency_ms"]["p50"],
            50.0,
        )
        self.assertEqual(
            result["pipeline_latency_ms"]["p95"],
            70.0,
        )
        self.assertTrue(result["targets"]["all_met"])
        self.assertTrue(result["read_only"])

    def test_keeps_only_the_bounded_recent_window(self):
        tracker = VisionPerformanceTracker(window_size=3)

        for index in range(5):
            result = tracker.update(
                10.0 + index,
                monotonic_time=float(index),
            )

        self.assertEqual(result["total_frames"], 5)
        self.assertEqual(result["sample_count"], 3)
        self.assertEqual(
            result["pipeline_latency_ms"]["maximum"],
            14.0,
        )

    def test_marks_warmup_and_below_target(self):
        tracker = VisionPerformanceTracker(window_size=3)

        warming = tracker.update(250.0, monotonic_time=1.0)
        slow = tracker.update(250.0, monotonic_time=2.0)

        self.assertEqual(warming["status"], "WARMING_UP")
        self.assertEqual(slow["status"], "BELOW_TARGET")
        self.assertFalse(slow["targets"]["fps_met"])
        self.assertFalse(slow["targets"]["p95_met"])

    def test_rejects_invalid_configuration_and_samples(self):
        with self.assertRaises(ValueError):
            VisionPerformanceTracker(window_size=1)
        tracker = VisionPerformanceTracker(window_size=2)
        with self.assertRaises(ValueError):
            tracker.update(-1.0)
        tracker.update(10.0, monotonic_time=2.0)
        with self.assertRaises(ValueError):
            tracker.update(10.0, monotonic_time=1.0)


if __name__ == "__main__":
    unittest.main()
