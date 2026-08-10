import hashlib
import json
import os
import tempfile
import unittest

from packages.monitoring.benchmark_store import (
    RuntimeBenchmarkStore,
    RuntimeBenchmarkUnavailable,
)


def report(status="PASS"):
    return {
        "schema_version": "1.0",
        "status": status,
        "started_at": "2026-07-28T15:07:52.000+08:00",
        "completed_at": "2026-07-28T15:08:52.000+08:00",
        "requested_duration_seconds": 60.0,
        "actual_duration_seconds": 60.043,
        "interval_seconds": 5.0,
        "sample_count": 13,
        "expected_sample_count": 13,
        "successful_samples": 13,
        "failed_samples": 0,
        "api_success_percent": 100.0,
        "vision_fresh_percent": 100.0,
        "frame_progress": {
            "first_frame_id": 330,
            "last_frame_id": 1200,
            "advanced_frames": 870,
        },
        "performance": {
            "minimum_fps": 14.607,
            "average_fps": 14.738,
            "maximum_observed_p95_ms": 40.317,
        },
        "resources": {
            "peak_memory_used_bytes": 2847560000,
            "peak_memory_used_gib": 2.652,
            "maximum_temperature_celsius": 50.0,
        },
        "camera": {
            "all_samples_running": True,
            "initial_restart_count": 0,
            "final_restart_count": 0,
            "restart_count_delta": 0,
        },
        "targets": {
            "minimum_api_success_percent": 95.0,
            "minimum_vision_fresh_percent": 95.0,
            "minimum_processing_fps": 5.0,
            "maximum_pipeline_p95_ms": 200.0,
            "maximum_memory_used_bytes": 3543348019,
            "maximum_temperature_celsius": 75.0,
            "maximum_camera_restart_delta": 0,
        },
        "checks": {
            "sample_count_met": True,
            "api_success_met": True,
            "vision_freshness_met": True,
            "processing_fps_met": True,
            "pipeline_p95_met": True,
            "memory_peak_met": True,
            "temperature_met": True,
            "camera_running_met": True,
            "camera_restart_met": True,
            "frame_progress_met": True,
        },
        "samples": [{"secret": "must-not-be-returned"}],
        "contains_secret": False,
        "read_only_sampling": True,
    }


class RuntimeBenchmarkStoreTests(unittest.TestCase):
    def write_report(self, directory, name, payload):
        benchmark_dir = os.path.join(
            directory,
            "data",
            "benchmarks",
        )
        if not os.path.isdir(benchmark_dir):
            os.makedirs(benchmark_dir)
        path = os.path.join(benchmark_dir, name)
        content = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
        with open(path, "wb") as output_file:
            output_file.write(content)
        return path, content

    def test_returns_latest_integrity_checked_bounded_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_report(
                directory,
                "runtime-benchmark-20260728T150000+0800.json",
                report(status="FAIL"),
            )
            path, content = self.write_report(
                directory,
                "runtime-benchmark-20260728T150752+0800.json",
                report(),
            )

            result = RuntimeBenchmarkStore(
                directory
            ).get_latest()

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["sample_count"], 13)
            self.assertEqual(
                result["performance"]["minimum_fps"],
                14.607,
            )
            self.assertEqual(
                result["report_sha256"],
                hashlib.sha256(content).hexdigest(),
            )
            self.assertEqual(
                result["report_path"],
                (
                    "data/benchmarks/"
                    "runtime-benchmark-20260728T150752+0800.json"
                ),
            )
            self.assertFalse(result["samples_included"])
            self.assertNotIn("samples", result)
            self.assertNotIn(
                "must-not-be-returned",
                json.dumps(result),
            )
            self.assertFalse(os.path.isabs(result["report_path"]))
            self.assertTrue(result["read_only"])
            self.assertEqual(os.path.getsize(path), len(content))

    def test_rejects_missing_or_invalid_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(RuntimeBenchmarkUnavailable):
                RuntimeBenchmarkStore(directory).get_latest()

            invalid = report()
            invalid["contains_secret"] = True
            self.write_report(
                directory,
                "runtime-benchmark-20260728T150752+0800.json",
                invalid,
            )
            with self.assertRaises(RuntimeBenchmarkUnavailable):
                RuntimeBenchmarkStore(directory).get_latest()

    def test_ignores_untrusted_names_and_escaping_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write_report(
                directory,
                "not-a-runtime-report.json",
                report(),
            )
            outside = os.path.join(directory, "outside.json")
            with open(outside, "w", encoding="utf-8") as output_file:
                json.dump(report(), output_file)
            benchmark_dir = os.path.join(
                directory,
                "data",
                "benchmarks",
            )
            link = os.path.join(
                benchmark_dir,
                "runtime-benchmark-20260728T150752+0800.json",
            )
            try:
                os.symlink(outside, link)
            except (AttributeError, NotImplementedError, OSError):
                self.skipTest("symlinks are unavailable")

            with self.assertRaises(RuntimeBenchmarkUnavailable):
                RuntimeBenchmarkStore(directory).get_latest()


if __name__ == "__main__":
    unittest.main()
