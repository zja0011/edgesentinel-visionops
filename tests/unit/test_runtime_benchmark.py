import json
import os
import unittest

from packages.monitoring.runtime_benchmark import (
    LocalRuntimeSampler,
    RuntimeBenchmarkError,
    RuntimeBenchmarkEvaluator,
    RuntimeBenchmarkRunner,
)


def sample(
    frame_id,
    fps=14.0,
    p95=45.0,
    memory=2500000000,
    temperature=50.0,
    restart_count=0,
    stale=False,
    status="OK",
):
    return {
        "timestamp": "2026-07-28T15:00:00.000+08:00",
        "status": status,
        "api_status": "ok",
        "frame_id": frame_id,
        "vision_stale": stale,
        "processing_fps": fps,
        "pipeline_p95_ms": p95,
        "performance_status": "MEETS_TARGET",
        "memory_used_bytes": memory,
        "memory_used_percent": 62.0,
        "maximum_temperature_celsius": temperature,
        "camera_status": "RUNNING",
        "camera_generation": 1,
        "camera_restart_count": restart_count,
        "camera_state_stale": stale,
        "camera_vision_frame_id": frame_id,
    }


class FakeResponse(object):
    def __init__(self, payload):
        self.content = json.dumps(payload).encode("utf-8")
        self.closed = False

    def read(self, unused_limit):
        return self.content

    def close(self):
        self.closed = True


class RuntimeBenchmarkTests(unittest.TestCase):
    def evaluate(self, samples):
        return RuntimeBenchmarkEvaluator().evaluate(
            samples=samples,
            requested_duration_seconds=30.0,
            actual_duration_seconds=30.0,
            interval_seconds=10.0,
            started_at="2026-07-28T15:00:00.000+08:00",
            completed_at="2026-07-28T15:00:30.000+08:00",
        )

    def test_passes_bounded_runtime_targets(self):
        result = self.evaluate(
            [
                sample(100, fps=14.0),
                sample(240, fps=13.5),
                sample(380, fps=14.2),
                sample(520, fps=13.8),
            ]
        )

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["api_success_percent"], 100.0)
        self.assertEqual(result["vision_fresh_percent"], 100.0)
        self.assertEqual(
            result["performance"]["minimum_fps"],
            13.5,
        )
        self.assertEqual(
            result["frame_progress"]["advanced_frames"],
            420,
        )
        self.assertTrue(all(result["checks"].values()))
        self.assertFalse(result["contains_secret"])
        self.assertTrue(result["read_only_sampling"])

    def test_fails_slow_stale_hot_or_restarted_runtime(self):
        result = self.evaluate(
            [
                sample(100),
                sample(
                    100,
                    fps=4.0,
                    p95=250.0,
                    memory=4000000000,
                    temperature=80.0,
                    restart_count=1,
                    stale=True,
                ),
                {
                    "timestamp": "2026-07-28T15:00:20+08:00",
                    "status": "ERROR",
                    "error_code": "OSError",
                },
                sample(100, restart_count=1),
            ]
        )

        self.assertEqual(result["status"], "FAIL")
        self.assertFalse(result["checks"]["api_success_met"])
        self.assertFalse(result["checks"]["processing_fps_met"])
        self.assertFalse(result["checks"]["pipeline_p95_met"])
        self.assertFalse(result["checks"]["memory_peak_met"])
        self.assertFalse(result["checks"]["temperature_met"])
        self.assertFalse(result["checks"]["camera_restart_met"])
        self.assertFalse(result["checks"]["frame_progress_met"])

    def test_sampler_reads_only_bounded_local_api_fields(self):
        payloads = {
            "/health": {"status": "ok", "secret": "not-returned"},
            "/api/v1/vision/performance": {
                "status": "MEETS_TARGET",
                "frame_id": 500,
                "stale": False,
                "processing_fps": 14.8,
                "pipeline_latency_ms": {"p95": 40.3},
                "detections": [{"bbox": [1, 2, 3, 4]}],
            },
            "/api/v1/system/status": {
                "memory": {
                    "used_bytes": 2500000000,
                    "used_percent": 61.0,
                },
                "temperature": {"max_celsius": 50.0},
            },
            "/api/v1/camera/status": {
                "status": "RUNNING",
                "generation": 1,
                "restart_count": 0,
                "state_stale": False,
                "vision": {"frame_id": 500},
                "device": "/dev/video0",
            },
        }

        def opener(url, timeout):
            self.assertEqual(timeout, 3.0)
            path = url.replace("http://127.0.0.1:8000", "")
            return FakeResponse(payloads[path])

        result = LocalRuntimeSampler(
            opener=opener,
            clock=lambda: "2026-07-28T15:00:00.000+08:00",
        ).sample()

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["frame_id"], 500)
        self.assertEqual(result["processing_fps"], 14.8)
        self.assertEqual(result["pipeline_p95_ms"], 40.3)
        self.assertNotIn("detections", result)
        self.assertNotIn("device", result)
        self.assertNotIn("secret", result)

    def test_runner_is_bounded_and_validates_window(self):
        state = {"now": 0.0}

        class FakeSampler(object):
            def sample(self):
                return sample(int(state["now"] * 10) + 1)

        def sleep(seconds):
            state["now"] += seconds

        runner = RuntimeBenchmarkRunner(
            FakeSampler(),
            monotonic=lambda: state["now"],
            sleep=sleep,
            clock=lambda: "2026-07-28T15:00:00.000+08:00",
        )
        result = runner.run(30.0, 5.0)

        self.assertEqual(result["sample_count"], 7)
        self.assertEqual(result["expected_sample_count"], 7)
        self.assertEqual(result["actual_duration_seconds"], 30.0)
        with self.assertRaises(RuntimeBenchmarkError):
            runner.run(29.0, 5.0)
        with self.assertRaises(RuntimeBenchmarkError):
            runner.run(86400.0, 1.0)

    def test_launcher_uses_local_api_and_beijing_result_name(self):
        project_dir = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        path = os.path.join(
            project_dir,
            "scripts",
            "run_runtime_benchmark.sh",
        )
        with open(path, "r", encoding="utf-8") as script_file:
            script = script_file.read()

        self.assertIn("set -euo pipefail", script)
        self.assertIn("apps.runtime_benchmark", script)
        self.assertIn("runtime-benchmark-$STAMP.json", script)
        self.assertIn("'%Y%m%dT%H%M%S+0800'", script)
        self.assertNotIn("curl ", script)
        self.assertNotIn("rm ", script)


if __name__ == "__main__":
    unittest.main()
