"""Bounded continuous-runtime qualification for the local Jetson API."""

import json
import math
import time
from urllib import request

from packages.vision.schemas import beijing_timestamp


class RuntimeBenchmarkError(RuntimeError):
    """Raised when a runtime benchmark cannot be configured safely."""


class LocalRuntimeSampler(object):
    ENDPOINTS = {
        "health": "/health",
        "performance": "/api/v1/vision/performance",
        "system": "/api/v1/system/status",
        "camera": "/api/v1/camera/status",
    }

    def __init__(
        self,
        base_url="http://127.0.0.1:8000",
        timeout_seconds=3.0,
        opener=None,
        clock=None,
    ):
        if base_url != "http://127.0.0.1:8000":
            raise RuntimeBenchmarkError(
                "runtime benchmark endpoint must remain local"
            )
        timeout_seconds = float(timeout_seconds)
        if timeout_seconds <= 0.0 or timeout_seconds > 10.0:
            raise RuntimeBenchmarkError(
                "timeout_seconds must be between 0 and 10"
            )
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.opener = opener or request.urlopen
        self.clock = clock or beijing_timestamp

    def sample(self):
        collected_at = self.clock()
        try:
            payloads = {
                name: self._get_json(path)
                for name, path in self.ENDPOINTS.items()
            }
            return self._bounded_sample(
                collected_at,
                payloads,
            )
        except (
            OSError,
            ValueError,
            TypeError,
            KeyError,
            json.JSONDecodeError,
        ) as error:
            return {
                "timestamp": collected_at,
                "status": "ERROR",
                "error_code": error.__class__.__name__[:64],
            }

    def _get_json(self, path):
        response = self.opener(
            self.base_url + path,
            timeout=self.timeout_seconds,
        )
        try:
            content = response.read(1024 * 1024 + 1)
        finally:
            close = getattr(response, "close", None)
            if close is not None:
                close()
        if len(content) > 1024 * 1024:
            raise ValueError("local API response is too large")
        payload = json.loads(content.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("local API response must be an object")
        return payload

    @staticmethod
    def _bounded_sample(collected_at, payloads):
        health = payloads["health"]
        performance = payloads["performance"]
        system = payloads["system"]
        camera = payloads["camera"]
        memory = system.get("memory") or {}
        temperature = system.get("temperature") or {}
        latency = performance.get("pipeline_latency_ms") or {}
        vision = camera.get("vision") or {}
        return {
            "timestamp": collected_at,
            "status": "OK",
            "api_status": health.get("status"),
            "frame_id": int(performance.get("frame_id") or 0),
            "vision_stale": bool(performance.get("stale")),
            "processing_fps": float(
                performance.get("processing_fps") or 0.0
            ),
            "pipeline_p95_ms": LocalRuntimeSampler._optional_float(
                latency.get("p95")
            ),
            "performance_status": performance.get("status"),
            "memory_used_bytes": int(memory.get("used_bytes") or 0),
            "memory_used_percent": LocalRuntimeSampler._optional_float(
                memory.get("used_percent")
            ),
            "maximum_temperature_celsius": (
                LocalRuntimeSampler._optional_float(
                    temperature.get("max_celsius")
                )
            ),
            "camera_status": camera.get("status"),
            "camera_generation": int(
                camera.get("generation") or 0
            ),
            "camera_restart_count": int(
                camera.get("restart_count") or 0
            ),
            "camera_state_stale": bool(
                camera.get("state_stale")
            ),
            "camera_vision_frame_id": int(
                vision.get("frame_id") or 0
            ),
        }

    @staticmethod
    def _optional_float(value):
        if value is None:
            return None
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("metric must be finite")
        return result


class RuntimeBenchmarkEvaluator(object):
    MINIMUM_API_SUCCESS_PERCENT = 95.0
    MINIMUM_VISION_FRESH_PERCENT = 95.0
    MINIMUM_PROCESSING_FPS = 5.0
    MAXIMUM_PIPELINE_P95_MS = 200.0
    MAXIMUM_MEMORY_USED_BYTES = int(3.3 * 1024 * 1024 * 1024)
    MAXIMUM_TEMPERATURE_CELSIUS = 75.0

    def evaluate(
        self,
        samples,
        requested_duration_seconds,
        actual_duration_seconds,
        interval_seconds,
        started_at,
        completed_at,
    ):
        samples = list(samples)
        expected_sample_count = (
            int(
                math.floor(
                    float(requested_duration_seconds)
                    / float(interval_seconds)
                )
            )
            + 1
        )
        successful = [
            sample
            for sample in samples
            if sample.get("status") == "OK"
        ]
        fresh = [
            sample
            for sample in successful
            if not sample.get("vision_stale")
            and not sample.get("camera_state_stale")
        ]
        fps_values = [
            float(sample["processing_fps"])
            for sample in successful
            if sample.get("processing_fps") is not None
        ]
        p95_values = [
            float(sample["pipeline_p95_ms"])
            for sample in successful
            if sample.get("pipeline_p95_ms") is not None
        ]
        memory_values = [
            int(sample["memory_used_bytes"])
            for sample in successful
            if sample.get("memory_used_bytes") is not None
        ]
        temperature_values = [
            float(sample["maximum_temperature_celsius"])
            for sample in successful
            if sample.get("maximum_temperature_celsius")
            is not None
        ]
        frames = [
            int(sample["frame_id"])
            for sample in successful
            if sample.get("frame_id") is not None
        ]
        restart_counts = [
            int(sample["camera_restart_count"])
            for sample in successful
            if sample.get("camera_restart_count") is not None
        ]
        camera_running = bool(successful) and all(
            sample.get("camera_status") == "RUNNING"
            for sample in successful
        )

        sample_count = len(samples)
        success_percent = self._percent(
            len(successful),
            sample_count,
        )
        fresh_percent = self._percent(
            len(fresh),
            len(successful),
        )
        minimum_fps = min(fps_values) if fps_values else None
        average_fps = self._average(fps_values)
        maximum_p95 = max(p95_values) if p95_values else None
        peak_memory = (
            max(memory_values) if memory_values else None
        )
        maximum_temperature = (
            max(temperature_values)
            if temperature_values
            else None
        )
        first_frame = frames[0] if frames else None
        last_frame = frames[-1] if frames else None
        frame_progressed = (
            first_frame is not None
            and last_frame is not None
            and last_frame > first_frame
        )
        restart_delta = (
            max(restart_counts) - min(restart_counts)
            if restart_counts
            else None
        )

        checks = {
            "sample_count_met": (
                sample_count >= expected_sample_count
            ),
            "api_success_met": (
                success_percent
                >= self.MINIMUM_API_SUCCESS_PERCENT
            ),
            "vision_freshness_met": (
                fresh_percent
                >= self.MINIMUM_VISION_FRESH_PERCENT
            ),
            "processing_fps_met": (
                minimum_fps is not None
                and minimum_fps >= self.MINIMUM_PROCESSING_FPS
            ),
            "pipeline_p95_met": (
                maximum_p95 is not None
                and maximum_p95
                <= self.MAXIMUM_PIPELINE_P95_MS
            ),
            "memory_peak_met": (
                peak_memory is not None
                and peak_memory <= self.MAXIMUM_MEMORY_USED_BYTES
            ),
            "temperature_met": (
                maximum_temperature is not None
                and maximum_temperature
                <= self.MAXIMUM_TEMPERATURE_CELSIUS
            ),
            "camera_running_met": camera_running,
            "camera_restart_met": restart_delta == 0,
            "frame_progress_met": frame_progressed,
        }
        return {
            "schema_version": "1.0",
            "status": (
                "PASS"
                if all(checks.values())
                else "FAIL"
            ),
            "started_at": started_at,
            "completed_at": completed_at,
            "requested_duration_seconds": float(
                requested_duration_seconds
            ),
            "actual_duration_seconds": round(
                float(actual_duration_seconds),
                3,
            ),
            "interval_seconds": float(interval_seconds),
            "sample_count": sample_count,
            "expected_sample_count": expected_sample_count,
            "successful_samples": len(successful),
            "failed_samples": sample_count - len(successful),
            "api_success_percent": success_percent,
            "vision_fresh_percent": fresh_percent,
            "frame_progress": {
                "first_frame_id": first_frame,
                "last_frame_id": last_frame,
                "advanced_frames": (
                    last_frame - first_frame
                    if frame_progressed
                    else 0
                ),
            },
            "performance": {
                "minimum_fps": self._rounded(minimum_fps),
                "average_fps": self._rounded(average_fps),
                "maximum_observed_p95_ms": self._rounded(
                    maximum_p95
                ),
            },
            "resources": {
                "peak_memory_used_bytes": peak_memory,
                "peak_memory_used_gib": self._rounded(
                    (
                        peak_memory / float(1024 ** 3)
                        if peak_memory is not None
                        else None
                    )
                ),
                "maximum_temperature_celsius": self._rounded(
                    maximum_temperature
                ),
            },
            "camera": {
                "all_samples_running": camera_running,
                "initial_restart_count": (
                    restart_counts[0] if restart_counts else None
                ),
                "final_restart_count": (
                    restart_counts[-1] if restart_counts else None
                ),
                "restart_count_delta": restart_delta,
            },
            "targets": {
                "minimum_api_success_percent": (
                    self.MINIMUM_API_SUCCESS_PERCENT
                ),
                "minimum_vision_fresh_percent": (
                    self.MINIMUM_VISION_FRESH_PERCENT
                ),
                "minimum_processing_fps": (
                    self.MINIMUM_PROCESSING_FPS
                ),
                "maximum_pipeline_p95_ms": (
                    self.MAXIMUM_PIPELINE_P95_MS
                ),
                "maximum_memory_used_bytes": (
                    self.MAXIMUM_MEMORY_USED_BYTES
                ),
                "maximum_temperature_celsius": (
                    self.MAXIMUM_TEMPERATURE_CELSIUS
                ),
                "maximum_camera_restart_delta": 0,
            },
            "checks": checks,
            "samples": samples,
            "contains_secret": False,
            "read_only_sampling": True,
        }

    @staticmethod
    def _percent(numerator, denominator):
        if denominator <= 0:
            return 0.0
        return round(
            float(numerator) / float(denominator) * 100.0,
            3,
        )

    @staticmethod
    def _average(values):
        if not values:
            return None
        return sum(values) / float(len(values))

    @staticmethod
    def _rounded(value):
        if value is None:
            return None
        return round(float(value), 3)


class RuntimeBenchmarkRunner(object):
    def __init__(
        self,
        sampler,
        evaluator=None,
        monotonic=None,
        sleep=None,
        clock=None,
    ):
        self.sampler = sampler
        self.evaluator = evaluator or RuntimeBenchmarkEvaluator()
        self.monotonic = monotonic or time.monotonic
        self.sleep = sleep or time.sleep
        self.clock = clock or beijing_timestamp

    def run(self, duration_seconds=60.0, interval_seconds=5.0):
        duration_seconds, interval_seconds = self.validate_window(
            duration_seconds,
            interval_seconds,
        )
        started_at = self.clock()
        started = self.monotonic()
        next_sample_at = started
        samples = []
        while True:
            samples.append(self.sampler.sample())
            now = self.monotonic()
            if now - started >= duration_seconds:
                break
            next_sample_at += interval_seconds
            wait_seconds = min(
                max(0.0, next_sample_at - now),
                max(0.0, duration_seconds - (now - started)),
            )
            if wait_seconds > 0.0:
                self.sleep(wait_seconds)
        completed = self.monotonic()
        return self.evaluator.evaluate(
            samples=samples,
            requested_duration_seconds=duration_seconds,
            actual_duration_seconds=completed - started,
            interval_seconds=interval_seconds,
            started_at=started_at,
            completed_at=self.clock(),
        )

    @staticmethod
    def validate_window(duration_seconds, interval_seconds):
        duration_seconds = float(duration_seconds)
        interval_seconds = float(interval_seconds)
        if duration_seconds < 30.0 or duration_seconds > 86400.0:
            raise RuntimeBenchmarkError(
                "duration_seconds must be between 30 and 86400"
            )
        if interval_seconds < 1.0 or interval_seconds > 300.0:
            raise RuntimeBenchmarkError(
                "interval_seconds must be between 1 and 300"
            )
        expected = (
            int(math.floor(duration_seconds / interval_seconds))
            + 1
        )
        if expected > 2881:
            raise RuntimeBenchmarkError(
                "runtime benchmark may contain at most 2881 samples"
            )
        return duration_seconds, interval_seconds
