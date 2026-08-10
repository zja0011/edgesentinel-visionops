"""Atomic persistence and freshness checks for the latest vision state."""

import json
import os
import tempfile
import time


class VisionStateUnavailable(RuntimeError):
    """Raised when no valid current vision state can be read."""


class CurrentVisionStateStore(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def write(self, frame_result):
        payload = (
            frame_result.to_dict()
            if hasattr(frame_result, "to_dict")
            else dict(frame_result)
        )
        parent = os.path.dirname(self.path)
        if not os.path.isdir(parent):
            os.makedirs(parent)

        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".current-vision-",
            suffix=".tmp",
            dir=parent,
        )
        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as state_file:
                json.dump(
                    payload,
                    state_file,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                state_file.write("\n")
                state_file.flush()
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def read(self, max_age_seconds=5.0):
        max_age_seconds = float(max_age_seconds)
        if max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        if not os.path.isfile(self.path):
            raise VisionStateUnavailable(
                "current vision state does not exist"
            )

        try:
            with open(self.path, "r", encoding="utf-8") as state_file:
                payload = json.load(state_file)
        except (OSError, ValueError) as error:
            raise VisionStateUnavailable(
                "current vision state is invalid"
            ) from error

        if not isinstance(payload, dict):
            raise VisionStateUnavailable(
                "current vision state must be a JSON object"
            )
        for required in (
            "frame_id",
            "timestamp",
            "camera_id",
            "analytics",
        ):
            if required not in payload:
                raise VisionStateUnavailable(
                    "current vision state is missing {0}".format(
                        required
                    )
                )

        age_seconds = max(
            0.0,
            time.time() - os.path.getmtime(self.path),
        )
        return {
            "snapshot": payload,
            "age_seconds": round(age_seconds, 3),
            "stale": age_seconds > max_age_seconds,
            "max_age_seconds": max_age_seconds,
        }
