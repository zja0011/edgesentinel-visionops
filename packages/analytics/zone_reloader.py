"""Fail-safe polling reload for an atomically replaced zone config."""

import hashlib
import os

from packages.analytics.zone_engine import ZoneEngine


class ZoneConfigReloader(object):
    def __init__(self, path, check_interval_frames=30):
        self.path = os.path.abspath(path)
        self.check_interval_frames = int(check_interval_frames)
        if self.check_interval_frames <= 0:
            raise ValueError(
                "check_interval_frames must be positive"
            )
        self.engine, self.version = self._load_stable()
        self.reload_count = 0
        self.last_reload_frame = 0
        self.last_checked_frame = 0
        self.last_error = None
        self._last_reported_error = None

    def poll(self, frame_id):
        frame_id = int(frame_id)
        if (
            frame_id - self.last_checked_frame
            < self.check_interval_frames
        ):
            return None
        self.last_checked_frame = frame_id

        try:
            candidate_version = self._file_version()
        except OSError:
            return self._failure(
                "zone configuration is unavailable"
            )
        if candidate_version == self.version:
            if self.last_error is not None:
                self.last_error = None
                self._last_reported_error = None
                return {
                    "status": "recovered",
                    "version": self.version,
                    "frame_id": frame_id,
                }
            return None

        try:
            candidate_engine, stable_version = self._load_stable()
        except (OSError, KeyError, TypeError, ValueError):
            return self._failure(
                "zone configuration is invalid"
            )
        self.engine = candidate_engine
        self.version = stable_version
        self.reload_count += 1
        self.last_reload_frame = frame_id
        self.last_error = None
        self._last_reported_error = None
        return {
            "status": "reloaded",
            "version": self.version,
            "frame_id": frame_id,
            "zone_count": len(self.engine.zones),
            "reload_count": self.reload_count,
        }

    def snapshot(self):
        return {
            "enabled": True,
            "status": (
                "degraded"
                if self.last_error is not None
                else "active"
            ),
            "version": self.version,
            "zone_count": len(self.engine.zones),
            "reload_count": self.reload_count,
            "last_reload_frame": self.last_reload_frame,
            "check_interval_frames": self.check_interval_frames,
            "last_error": self.last_error,
        }

    def _failure(self, message):
        self.last_error = message
        if message == self._last_reported_error:
            return None
        self._last_reported_error = message
        return {
            "status": "failed",
            "version": self.version,
            "frame_id": self.last_checked_frame,
            "error": message,
        }

    def _load_stable(self):
        version_before = self._file_version()
        engine = ZoneEngine.from_file(self.path)
        version_after = self._file_version()
        if version_before != version_after:
            raise ValueError(
                "zone configuration changed while loading"
            )
        return engine, version_after

    def _file_version(self):
        digest = hashlib.sha256()
        with open(self.path, "rb") as config_file:
            while True:
                block = config_file.read(65536)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()
