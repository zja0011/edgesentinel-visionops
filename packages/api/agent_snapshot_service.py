"""Safe, integrity-checked access to Agent-created snapshots."""

import hashlib
import os
from urllib.parse import quote


class AgentSnapshotNotFound(LookupError):
    """Raised when a task has no safely resolvable snapshot."""


class AgentSnapshotIntegrityError(RuntimeError):
    """Raised when stored evidence no longer matches its audit result."""


class AgentSnapshotService(object):
    MAX_JPEG_BYTES = 20 * 1024 * 1024

    def __init__(self, project_dir):
        self.project_dir = os.path.realpath(
            os.path.abspath(project_dir)
        )
        self.snapshot_directory = os.path.realpath(
            os.path.join(
                self.project_dir,
                "data",
                "evidence",
                "manual-snapshots",
            )
        )

    def add_url(self, task):
        payload = dict(task)
        if self._snapshot_result(task) is not None:
            task_id = quote(str(task["task_id"]), safe="")
            payload["snapshot_url"] = (
                "/api/v1/agent/tasks/{0}/snapshot".format(
                    task_id
                )
            )
        return payload

    def resolve(self, task):
        result = self._snapshot_result(task)
        if result is None:
            raise AgentSnapshotNotFound(
                "task has no completed snapshot"
            )
        stored_path = result.get("evidence_path")
        if (
            not isinstance(stored_path, str)
            or not stored_path
            or os.path.isabs(stored_path)
        ):
            raise AgentSnapshotNotFound(
                "snapshot path is unavailable"
            )
        candidate = os.path.realpath(
            os.path.abspath(
                os.path.join(self.project_dir, stored_path)
            )
        )
        try:
            common_root = os.path.commonpath(
                [self.snapshot_directory, candidate]
            )
        except ValueError:
            common_root = ""
        if common_root != self.snapshot_directory:
            raise AgentSnapshotNotFound(
                "snapshot path is outside manual evidence"
            )
        if os.path.splitext(candidate)[1].lower() not in (
            ".jpg",
            ".jpeg",
        ):
            raise AgentSnapshotNotFound(
                "unsupported snapshot file type"
            )
        if not os.path.isfile(candidate):
            raise AgentSnapshotNotFound(
                "snapshot file does not exist"
            )
        try:
            size = os.path.getsize(candidate)
            if size <= 4 or size > self.MAX_JPEG_BYTES:
                raise AgentSnapshotIntegrityError(
                    "snapshot size is invalid"
                )
            with open(candidate, "rb") as snapshot_file:
                content = snapshot_file.read(
                    self.MAX_JPEG_BYTES + 1
                )
        except OSError as error:
            raise AgentSnapshotNotFound(
                "snapshot file is unavailable"
            ) from error
        if (
            len(content) != size
            or content[:2] != b"\xff\xd8"
            or content[-2:] != b"\xff\xd9"
        ):
            raise AgentSnapshotIntegrityError(
                "snapshot is not a complete JPEG"
            )
        recorded_size = result.get("bytes")
        recorded_sha256 = str(result.get("sha256") or "").lower()
        actual_sha256 = hashlib.sha256(content).hexdigest()
        if (
            not isinstance(recorded_size, int)
            or recorded_size != size
            or recorded_sha256 != actual_sha256
        ):
            raise AgentSnapshotIntegrityError(
                "snapshot does not match its audit result"
            )
        return {
            "content": content,
            "path": candidate,
            "filename": os.path.basename(candidate),
            "bytes": size,
            "sha256": actual_sha256,
            "snapshot_id": result.get("snapshot_id"),
        }

    @staticmethod
    def _snapshot_result(task):
        tool_results = task.get("tool_results") or []
        for tool_result in reversed(tool_results):
            if (
                tool_result.get("tool_name")
                == "camera.capture_snapshot"
                and tool_result.get("status") == "SUCCEEDED"
                and isinstance(tool_result.get("result"), dict)
            ):
                return tool_result["result"]
        return None
