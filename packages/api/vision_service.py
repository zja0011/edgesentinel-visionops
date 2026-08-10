"""Read-only API facade for the latest atomic vision state."""

import os
import time

from packages.harness.vision_tools import VisionStateTools
from packages.vision.state_store import VisionStateUnavailable


class VisionApiUnavailable(RuntimeError):
    """Raised when the latest vision state cannot serve an API query."""


class LiveFrameService(object):
    def __init__(self, frame_path, max_age_seconds=5.0):
        self.frame_path = os.path.abspath(frame_path)
        self.max_age_seconds = float(max_age_seconds)
        if self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")

    def get(self):
        if not os.path.isfile(self.frame_path):
            raise VisionApiUnavailable(
                "latest vision frame does not exist"
            )
        try:
            with open(self.frame_path, "rb") as frame_file:
                content = frame_file.read()
        except OSError as error:
            raise VisionApiUnavailable(
                "latest vision frame is unavailable"
            ) from error
        if len(content) <= 2 or content[:2] != b"\xff\xd8":
            raise VisionApiUnavailable(
                "latest vision frame is invalid"
            )
        age_seconds = max(
            0.0,
            time.time() - os.path.getmtime(self.frame_path),
        )
        return {
            "path": self.frame_path,
            "content": content,
            "size": len(content),
            "age_seconds": round(age_seconds, 3),
            "stale": age_seconds > self.max_age_seconds,
            "max_age_seconds": self.max_age_seconds,
        }


class VisionQueryService(object):
    API_SCHEMA_VERSION = "1.0"

    def __init__(self, state_path, max_age_seconds=5.0):
        self.tools = VisionStateTools(
            state_path,
            max_age_seconds=max_age_seconds,
        )

    def get_people(self):
        return self._call(self.tools.get_people_count)

    def get_objects(self):
        return self._call(self.tools.get_current_objects)

    def get_performance(self):
        return self._call(self.tools.get_performance)

    def get_inventory(self, object_class=None):
        arguments = {}
        if object_class:
            arguments["object_class"] = object_class
        return self._call(
            self.tools.get_inventory_state,
            arguments=arguments,
        )

    def compare_inventory(self, expected_counts):
        return self._call(
            self.tools.compare_inventory_state,
            arguments={"expected_counts": expected_counts},
        )

    def count_objects(
        self,
        classes,
        minimum_confidence=0.0,
        zone_id=None,
    ):
        arguments = {
            "classes": list(classes),
            "minimum_confidence": minimum_confidence,
        }
        if zone_id:
            arguments["zone_id"] = zone_id
        return self._call(
            self.tools.count_objects,
            arguments=arguments,
        )

    def get_zones(self, zone_id=None):
        arguments = {}
        if zone_id:
            arguments["zone_id"] = zone_id
        return self._call(
            self.tools.get_zone_status,
            arguments=arguments,
        )

    def get_track_history(
        self,
        track_id=None,
        object_class=None,
        limit=10,
    ):
        arguments = {"limit": limit}
        if track_id is not None:
            arguments["track_id"] = track_id
        if object_class:
            arguments["object_class"] = object_class
        return self._call(
            self.tools.get_track_history,
            arguments=arguments,
        )

    def _call(self, handler, arguments=None):
        try:
            payload = handler(arguments or {})
        except (VisionStateUnavailable, RuntimeError) as error:
            raise VisionApiUnavailable(
                "current vision state is unavailable"
            ) from error
        result = {
            "schema_version": self.API_SCHEMA_VERSION,
            "status": "available",
        }
        result.update(payload)
        return result
