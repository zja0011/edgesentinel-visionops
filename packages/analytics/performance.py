"""Bounded rolling performance metrics for the live vision loop."""

import math
import time
from collections import deque


class VisionPerformanceTracker(object):
    def __init__(
        self,
        window_size=120,
        minimum_fps=5.0,
        maximum_p95_ms=200.0,
    ):
        window_size = int(window_size)
        minimum_fps = float(minimum_fps)
        maximum_p95_ms = float(maximum_p95_ms)
        if window_size < 2 or window_size > 3600:
            raise ValueError(
                "window_size must be between 2 and 3600"
            )
        if minimum_fps <= 0.0:
            raise ValueError("minimum_fps must be positive")
        if maximum_p95_ms <= 0.0:
            raise ValueError(
                "maximum_p95_ms must be positive"
            )
        self.window_size = window_size
        self.minimum_fps = minimum_fps
        self.maximum_p95_ms = maximum_p95_ms
        self._latencies = deque(maxlen=window_size)
        self._timestamps = deque(maxlen=window_size)
        self._total_frames = 0

    def update(self, pipeline_latency_ms, monotonic_time=None):
        latency = float(pipeline_latency_ms)
        if not math.isfinite(latency) or latency < 0.0:
            raise ValueError(
                "pipeline_latency_ms must be finite and non-negative"
            )
        timestamp = (
            time.monotonic()
            if monotonic_time is None
            else float(monotonic_time)
        )
        if not math.isfinite(timestamp):
            raise ValueError(
                "monotonic_time must be finite"
            )
        if self._timestamps and timestamp < self._timestamps[-1]:
            raise ValueError(
                "monotonic_time must not move backwards"
            )
        self._latencies.append(latency)
        self._timestamps.append(timestamp)
        self._total_frames += 1
        return self.snapshot()

    def snapshot(self):
        sample_count = len(self._latencies)
        sorted_latencies = sorted(self._latencies)
        processing_fps = 0.0
        frame_interval_ms = None
        if len(self._timestamps) >= 2:
            elapsed = (
                self._timestamps[-1] - self._timestamps[0]
            )
            if elapsed > 0.0:
                processing_fps = (
                    len(self._timestamps) - 1
                ) / elapsed
                frame_interval_ms = 1000.0 / processing_fps

        latest = (
            float(self._latencies[-1])
            if self._latencies
            else None
        )
        average = (
            sum(self._latencies) / sample_count
            if sample_count
            else None
        )
        p50 = self._percentile(sorted_latencies, 0.50)
        p95 = self._percentile(sorted_latencies, 0.95)
        maximum = (
            float(sorted_latencies[-1])
            if sorted_latencies
            else None
        )
        warmed_up = len(self._timestamps) >= 2
        fps_met = (
            warmed_up and processing_fps >= self.minimum_fps
        )
        p95_met = (
            p95 is not None and p95 <= self.maximum_p95_ms
        )
        if not warmed_up:
            status = "WARMING_UP"
        elif fps_met and p95_met:
            status = "MEETS_TARGET"
        else:
            status = "BELOW_TARGET"
        return {
            "schema_version": "1.0",
            "status": status,
            "total_frames": self._total_frames,
            "sample_count": sample_count,
            "window_size_frames": self.window_size,
            "processing_fps": self._rounded(processing_fps),
            "frame_interval_ms": self._rounded(
                frame_interval_ms
            ),
            "pipeline_latency_ms": {
                "latest": self._rounded(latest),
                "average": self._rounded(average),
                "p50": self._rounded(p50),
                "p95": self._rounded(p95),
                "maximum": self._rounded(maximum),
            },
            "targets": {
                "minimum_fps": self.minimum_fps,
                "maximum_p95_ms": self.maximum_p95_ms,
                "fps_met": fps_met,
                "p95_met": p95_met,
                "all_met": fps_met and p95_met,
            },
            "read_only": True,
        }

    @staticmethod
    def _percentile(sorted_values, percentile):
        if not sorted_values:
            return None
        rank = int(math.ceil(percentile * len(sorted_values)))
        index = max(0, min(len(sorted_values) - 1, rank - 1))
        return float(sorted_values[index])

    @staticmethod
    def _rounded(value):
        if value is None:
            return None
        return round(float(value), 3)
