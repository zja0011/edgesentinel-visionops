"""Read-only camera supervisor status for the local API."""

import json
import os
import time


class CameraStatusUnavailable(RuntimeError):
    pass


class CameraStatusService(object):
    ALLOWED_STATUSES = (
        "STARTING",
        "RUNNING",
        "CAMERA_OFFLINE",
        "WAITING_FOR_CAMERA",
        "RESTARTING",
        "VISION_STALLED",
        "STOPPED",
    )

    def __init__(self, state_path, max_state_age_seconds=10.0):
        self.state_path = os.path.abspath(state_path)
        self.max_state_age_seconds = float(
            max_state_age_seconds
        )
        if self.max_state_age_seconds <= 0:
            raise ValueError(
                "max_state_age_seconds must be positive"
            )

    def get_status(self):
        if not os.path.isfile(self.state_path):
            raise CameraStatusUnavailable(
                "camera supervisor state does not exist"
            )
        try:
            with open(
                self.state_path,
                "r",
                encoding="utf-8",
            ) as state_file:
                state = json.load(state_file)
            age_seconds = max(
                0.0,
                time.time() - os.path.getmtime(self.state_path),
            )
        except (OSError, ValueError) as error:
            raise CameraStatusUnavailable(
                "camera supervisor state is unavailable"
            ) from error
        status = state.get("status")
        if status not in self.ALLOWED_STATUSES:
            raise CameraStatusUnavailable(
                "camera supervisor status is invalid"
            )
        vision = state.get("vision") or {}
        control = state.get("control") or {}
        control_status = control.get("status")
        if control_status not in (
            None,
            "ACCEPTED",
            "COMPLETED",
        ):
            control_status = None
        return {
            "schema_version": "1.0",
            "status": status,
            "device": str(state.get("device") or ""),
            "device_available": bool(
                state.get("device_available")
            ),
            "worker_running": bool(state.get("worker_running")),
            "generation": int(state.get("generation") or 0),
            "restart_count": int(
                state.get("restart_count") or 0
            ),
            "last_exit_code": state.get("last_exit_code"),
            "started_at": state.get("started_at"),
            "updated_at": state.get("updated_at"),
            "state_age_seconds": round(age_seconds, 3),
            "state_stale": (
                age_seconds > self.max_state_age_seconds
            ),
            "vision": {
                "available": bool(vision.get("available")),
                "age_seconds": vision.get("age_seconds"),
                "frame_id": vision.get("frame_id"),
                "timestamp": vision.get("timestamp"),
            },
            "control": {
                "last_request_id": (
                    str(control.get("last_request_id"))
                    if control.get("last_request_id")
                    else None
                ),
                "status": control_status,
                "requested_at": control.get("requested_at"),
                "completed_at": control.get("completed_at"),
            },
        }
