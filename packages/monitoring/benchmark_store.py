"""Safely expose the newest persisted runtime benchmark summary."""

import hashlib
import json
import os
import re


class RuntimeBenchmarkUnavailable(RuntimeError):
    """Raised when no valid bounded benchmark report is available."""


class RuntimeBenchmarkStore(object):
    MAX_REPORT_BYTES = 4 * 1024 * 1024
    FILENAME_PATTERN = re.compile(
        r"^runtime-benchmark-\d{8}T\d{6}\+0800\.json$"
    )
    CHECK_NAMES = (
        "sample_count_met",
        "api_success_met",
        "vision_freshness_met",
        "processing_fps_met",
        "pipeline_p95_met",
        "memory_peak_met",
        "temperature_met",
        "camera_running_met",
        "camera_restart_met",
        "frame_progress_met",
    )

    def __init__(self, project_dir):
        self.project_dir = os.path.realpath(
            os.path.abspath(project_dir)
        )
        self.benchmark_dir = os.path.realpath(
            os.path.join(
                self.project_dir,
                "data",
                "benchmarks",
            )
        )
        self._require_inside(
            self.benchmark_dir,
            self.project_dir,
        )

    def get_latest(self):
        path = self._latest_path()
        try:
            size_bytes = os.path.getsize(path)
        except OSError as error:
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark report is unavailable"
            ) from error
        if size_bytes <= 0 or size_bytes > self.MAX_REPORT_BYTES:
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark report size is invalid"
            )
        try:
            with open(path, "rb") as report_file:
                content = report_file.read(self.MAX_REPORT_BYTES + 1)
        except OSError as error:
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark report is unreadable"
            ) from error
        if len(content) != size_bytes:
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark report changed while reading"
            )
        try:
            payload = json.loads(content.decode("utf-8"))
        except (UnicodeError, ValueError) as error:
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark report is invalid JSON"
            ) from error
        return self._bounded_summary(
            path,
            content,
            payload,
        )

    def _latest_path(self):
        if not os.path.isdir(self.benchmark_dir):
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark directory does not exist"
            )
        candidates = []
        try:
            names = os.listdir(self.benchmark_dir)
        except OSError as error:
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark directory is unreadable"
            ) from error
        for name in names:
            if not self.FILENAME_PATTERN.match(name):
                continue
            candidate = os.path.realpath(
                os.path.join(self.benchmark_dir, name)
            )
            try:
                self._require_inside(
                    candidate,
                    self.benchmark_dir,
                )
            except RuntimeBenchmarkUnavailable:
                continue
            if os.path.isfile(candidate):
                candidates.append((name, candidate))
        if not candidates:
            raise RuntimeBenchmarkUnavailable(
                "no runtime benchmark report exists"
            )
        candidates.sort(reverse=True)
        return candidates[0][1]

    def _bounded_summary(self, path, content, payload):
        if not isinstance(payload, dict):
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark report must be an object"
            )
        status = payload.get("status")
        if (
            payload.get("schema_version") != "1.0"
            or status not in ("PASS", "FAIL")
            or payload.get("contains_secret") is not False
            or payload.get("read_only_sampling") is not True
        ):
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark report contract is invalid"
            )
        performance = payload.get("performance") or {}
        resources = payload.get("resources") or {}
        camera = payload.get("camera") or {}
        progress = payload.get("frame_progress") or {}
        targets = payload.get("targets") or {}
        checks = payload.get("checks") or {}
        if not all(
            isinstance(checks.get(name), bool)
            for name in self.CHECK_NAMES
        ):
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark checks are invalid"
            )
        relative_path = os.path.relpath(
            path,
            self.project_dir,
        ).replace(os.sep, "/")
        return {
            "schema_version": "1.0",
            "status": status,
            "started_at": payload.get("started_at"),
            "completed_at": payload.get("completed_at"),
            "requested_duration_seconds": payload.get(
                "requested_duration_seconds"
            ),
            "actual_duration_seconds": payload.get(
                "actual_duration_seconds"
            ),
            "sample_count": payload.get("sample_count"),
            "expected_sample_count": payload.get(
                "expected_sample_count"
            ),
            "api_success_percent": payload.get(
                "api_success_percent"
            ),
            "vision_fresh_percent": payload.get(
                "vision_fresh_percent"
            ),
            "frame_progress": {
                "first_frame_id": progress.get(
                    "first_frame_id"
                ),
                "last_frame_id": progress.get("last_frame_id"),
                "advanced_frames": progress.get(
                    "advanced_frames"
                ),
            },
            "performance": {
                "minimum_fps": performance.get("minimum_fps"),
                "average_fps": performance.get("average_fps"),
                "maximum_observed_p95_ms": performance.get(
                    "maximum_observed_p95_ms"
                ),
            },
            "resources": {
                "peak_memory_used_bytes": resources.get(
                    "peak_memory_used_bytes"
                ),
                "peak_memory_used_gib": resources.get(
                    "peak_memory_used_gib"
                ),
                "maximum_temperature_celsius": resources.get(
                    "maximum_temperature_celsius"
                ),
            },
            "camera": {
                "all_samples_running": camera.get(
                    "all_samples_running"
                ),
                "restart_count_delta": camera.get(
                    "restart_count_delta"
                ),
            },
            "targets": {
                "minimum_api_success_percent": targets.get(
                    "minimum_api_success_percent"
                ),
                "minimum_vision_fresh_percent": targets.get(
                    "minimum_vision_fresh_percent"
                ),
                "minimum_processing_fps": targets.get(
                    "minimum_processing_fps"
                ),
                "maximum_pipeline_p95_ms": targets.get(
                    "maximum_pipeline_p95_ms"
                ),
                "maximum_memory_used_bytes": targets.get(
                    "maximum_memory_used_bytes"
                ),
                "maximum_temperature_celsius": targets.get(
                    "maximum_temperature_celsius"
                ),
                "maximum_camera_restart_delta": targets.get(
                    "maximum_camera_restart_delta"
                ),
            },
            "checks": {
                name: checks[name]
                for name in self.CHECK_NAMES
            },
            "report_path": relative_path,
            "report_bytes": len(content),
            "report_sha256": hashlib.sha256(content).hexdigest(),
            "samples_included": False,
            "contains_secret": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    @staticmethod
    def _require_inside(path, root):
        path = os.path.realpath(path)
        root = os.path.realpath(root)
        if path == root:
            return
        if not path.startswith(root + os.sep):
            raise RuntimeBenchmarkUnavailable(
                "runtime benchmark path escapes its trusted root"
            )
