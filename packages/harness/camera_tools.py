"""Confirmation-gated camera snapshot tooling."""

import hashlib
import os
import tempfile
import threading
import time
import uuid

from packages.api.camera_service import (
    CameraStatusService,
    CameraStatusUnavailable,
)
from packages.harness.utf8 import write_json_atomic
from packages.vision.schemas import beijing_timestamp
from packages.vision.state_store import (
    CurrentVisionStateStore,
    VisionStateUnavailable,
)


class CameraSnapshotUnavailable(RuntimeError):
    """Raised when a fresh, valid live frame cannot be archived."""


class CameraRestartUnavailable(RuntimeError):
    """Raised when a bounded vision-worker restart cannot complete."""


class CameraStatusTools(object):
    """Read the bounded supervisor status without camera control."""

    def __init__(
        self,
        project_dir,
        supervisor_state_path=None,
        max_state_age_seconds=10.0,
    ):
        project_dir = os.path.abspath(project_dir)
        self.service = CameraStatusService(
            supervisor_state_path
            or os.path.join(
                project_dir,
                "data",
                "runtime",
                "vision-supervisor.json",
            ),
            max_state_age_seconds=max_state_age_seconds,
        )

    def get_status(self, arguments):
        if arguments:
            raise ValueError("camera status takes no arguments")
        payload = self.service.get_status()
        vision = payload.get("vision") or {}
        payload["healthy"] = bool(
            payload.get("status") == "RUNNING"
            and payload.get("device_available")
            and payload.get("worker_running")
            and not payload.get("state_stale")
            and vision.get("available")
        )
        payload["read_only"] = True
        return payload


class CameraRestartTools(object):
    """Request one supervised worker restart through a fixed control file."""

    def __init__(
        self,
        project_dir,
        supervisor_state_path=None,
        control_path=None,
        max_state_age_seconds=10.0,
        timeout_seconds=90.0,
        poll_seconds=0.25,
    ):
        self.project_dir = os.path.abspath(project_dir)
        runtime_directory = os.path.join(
            self.project_dir,
            "data",
            "runtime",
        )
        self.control_path = os.path.abspath(
            control_path
            or os.path.join(
                runtime_directory,
                "vision-control.json",
            )
        )
        self._require_inside(
            self.control_path,
            runtime_directory,
        )
        self.service = CameraStatusService(
            supervisor_state_path
            or os.path.join(
                runtime_directory,
                "vision-supervisor.json",
            ),
            max_state_age_seconds=max_state_age_seconds,
        )
        self.timeout_seconds = float(timeout_seconds)
        self.poll_seconds = float(poll_seconds)
        if self.timeout_seconds <= 0 or self.poll_seconds <= 0:
            raise ValueError("restart intervals must be positive")
        self._restart_lock = threading.Lock()

    def restart(self, arguments):
        if arguments:
            raise ValueError("camera restart takes no arguments")
        with self._restart_lock:
            before = self._require_healthy(self.service.get_status())
            request_id = "restart_{0}".format(uuid.uuid4().hex)
            requested_at = beijing_timestamp()
            requested_at_epoch = time.time()
            write_json_atomic(
                self.control_path,
                {
                    "schema_version": "1.0",
                    "request_id": request_id,
                    "action": "RESTART",
                    "status": "REQUESTED",
                    "requested_at": requested_at,
                    "requested_at_epoch": requested_at_epoch,
                    "expires_at_epoch": requested_at_epoch + 30.0,
                },
            )
            deadline = time.monotonic() + self.timeout_seconds
            while time.monotonic() < deadline:
                time.sleep(self.poll_seconds)
                try:
                    current = self.service.get_status()
                except CameraStatusUnavailable:
                    continue
                control = current.get("control") or {}
                vision = current.get("vision") or {}
                completed = (
                    control.get("last_request_id") == request_id
                    and control.get("status") == "COMPLETED"
                    and current.get("status") == "RUNNING"
                    and current.get("device_available")
                    and current.get("worker_running")
                    and not current.get("state_stale")
                    and vision.get("available")
                    and int(current.get("generation") or 0)
                    > int(before.get("generation") or 0)
                    and int(current.get("restart_count") or 0)
                    > int(before.get("restart_count") or 0)
                )
                if completed:
                    return {
                        "schema_version": "1.0",
                        "request_id": request_id,
                        "requested_at": requested_at,
                        "completed_at": control.get(
                            "completed_at"
                        ),
                        "before_generation": int(
                            before.get("generation") or 0
                        ),
                        "after_generation": int(
                            current.get("generation") or 0
                        ),
                        "before_restart_count": int(
                            before.get("restart_count") or 0
                        ),
                        "after_restart_count": int(
                            current.get("restart_count") or 0
                        ),
                        "recovery_seconds": round(
                            time.time() - requested_at_epoch,
                            3,
                        ),
                        "vision_frame_id": vision.get("frame_id"),
                        "state_stale": False,
                    }
            raise CameraRestartUnavailable(
                "vision worker did not complete the confirmed restart"
            )

    @staticmethod
    def _require_healthy(payload):
        vision = payload.get("vision") or {}
        if not (
            payload.get("status") == "RUNNING"
            and payload.get("device_available")
            and payload.get("worker_running")
            and not payload.get("state_stale")
            and vision.get("available")
        ):
            raise CameraRestartUnavailable(
                "camera must be healthy before a controlled restart"
            )
        return payload

    @staticmethod
    def _require_inside(path, root):
        path = os.path.realpath(os.path.abspath(path))
        root = os.path.realpath(os.path.abspath(root))
        try:
            inside = os.path.commonpath([path, root]) == root
        except ValueError:
            inside = False
        if not inside:
            raise CameraRestartUnavailable(
                "camera control path escapes the runtime directory"
            )


class CameraSnapshotTools(object):
    MAX_JPEG_BYTES = 20 * 1024 * 1024

    def __init__(
        self,
        project_dir,
        frame_path=None,
        state_path=None,
        max_age_seconds=5.0,
    ):
        self.project_dir = os.path.abspath(project_dir)
        self.frame_path = os.path.abspath(
            frame_path
            or os.path.join(
                self.project_dir,
                "data",
                "state",
                "current-frame.jpg",
            )
        )
        self.state_store = CurrentVisionStateStore(
            state_path
            or os.path.join(
                self.project_dir,
                "data",
                "state",
                "current-vision.json",
            )
        )
        self.max_age_seconds = float(max_age_seconds)
        if self.max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be positive")
        evidence_root = os.path.join(
            self.project_dir,
            "data",
            "evidence",
        )
        self.snapshot_directory = os.path.join(
            evidence_root,
            "manual-snapshots",
        )
        self._require_inside(
            self.snapshot_directory,
            evidence_root,
        )

    def capture_snapshot(self, arguments):
        if arguments:
            raise ValueError("camera snapshot takes no arguments")
        frame = self._read_fresh_frame()
        state = self._read_fresh_state()
        snapshot_id = "snap_{0}".format(uuid.uuid4().hex)
        created_at = beijing_timestamp()
        camera_id = str(
            state["snapshot"].get("camera_id") or "camera"
        )
        filename = "{0}_{1}_{2}.jpg".format(
            self._safe_component(created_at),
            self._safe_component(camera_id),
            snapshot_id,
        )
        path = os.path.abspath(
            os.path.join(self.snapshot_directory, filename)
        )
        self._require_inside(path, self.snapshot_directory)
        self._write_atomic(path, frame["content"])
        return {
            "schema_version": "1.0",
            "snapshot_id": snapshot_id,
            "created_at": created_at,
            "camera_id": camera_id,
            "vision_frame_id": int(
                state["snapshot"]["frame_id"]
            ),
            "vision_timestamp": state["snapshot"]["timestamp"],
            "frame_age_seconds": frame["age_seconds"],
            "evidence_path": os.path.relpath(
                path,
                self.project_dir,
            ).replace(os.sep, "/"),
            "bytes": len(frame["content"]),
            "sha256": hashlib.sha256(frame["content"]).hexdigest(),
        }

    def _read_fresh_frame(self):
        if not os.path.isfile(self.frame_path):
            raise CameraSnapshotUnavailable(
                "latest camera frame does not exist"
            )
        try:
            size = os.path.getsize(self.frame_path)
            if size <= 4 or size > self.MAX_JPEG_BYTES:
                raise CameraSnapshotUnavailable(
                    "latest camera frame size is invalid"
                )
            with open(self.frame_path, "rb") as frame_file:
                content = frame_file.read(self.MAX_JPEG_BYTES + 1)
        except OSError as error:
            raise CameraSnapshotUnavailable(
                "latest camera frame is unavailable"
            ) from error
        if (
            len(content) != size
            or content[:2] != b"\xff\xd8"
            or content[-2:] != b"\xff\xd9"
        ):
            raise CameraSnapshotUnavailable(
                "latest camera frame is not a complete JPEG"
            )
        age_seconds = max(
            0.0,
            time.time() - os.path.getmtime(self.frame_path),
        )
        if age_seconds > self.max_age_seconds:
            raise CameraSnapshotUnavailable(
                "latest camera frame is stale"
            )
        return {
            "content": content,
            "age_seconds": round(age_seconds, 3),
        }

    def _read_fresh_state(self):
        try:
            state = self.state_store.read(
                max_age_seconds=self.max_age_seconds
            )
        except VisionStateUnavailable as error:
            raise CameraSnapshotUnavailable(
                "current vision state is unavailable"
            ) from error
        if state["stale"]:
            raise CameraSnapshotUnavailable(
                "current vision state is stale"
            )
        return state

    def _write_atomic(self, path, content):
        if not os.path.isdir(self.snapshot_directory):
            os.makedirs(self.snapshot_directory)
        self._require_inside(
            self.snapshot_directory,
            os.path.join(
                self.project_dir,
                "data",
                "evidence",
            ),
        )
        self._require_inside(path, self.snapshot_directory)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".snapshot-",
            suffix=".tmp",
            dir=self.snapshot_directory,
        )
        try:
            with os.fdopen(descriptor, "wb") as output_file:
                output_file.write(content)
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(temporary_path, path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def _safe_component(value):
        safe = "".join(
            character
            if character.isalnum() or character in ("-", "_", "+")
            else "_"
            for character in str(value)
        )
        if not safe:
            raise CameraSnapshotUnavailable(
                "snapshot filename component is empty"
            )
        return safe

    @staticmethod
    def _require_inside(path, root):
        path = os.path.realpath(os.path.abspath(path))
        root = os.path.realpath(os.path.abspath(root))
        try:
            inside = os.path.commonpath([path, root]) == root
        except ValueError:
            inside = False
        if not inside:
            raise CameraSnapshotUnavailable(
                "snapshot path escapes the evidence directory"
            )
