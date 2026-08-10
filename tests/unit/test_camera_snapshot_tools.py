import json
import os
import tempfile
import time
import unittest

from packages.harness.camera_tools import (
    CameraSnapshotTools,
    CameraSnapshotUnavailable,
    CameraStatusTools,
)
from packages.harness.default_tools import build_default_registry
from packages.harness.registry import ToolInvocationError


JPEG = b"\xff\xd8edge-snapshot\xff\xd9"


def write_live_inputs(directory):
    state_directory = os.path.join(directory, "data", "state")
    os.makedirs(state_directory)
    frame_path = os.path.join(state_directory, "current-frame.jpg")
    state_path = os.path.join(
        state_directory,
        "current-vision.json",
    )
    with open(frame_path, "wb") as frame_file:
        frame_file.write(JPEG)
    with open(state_path, "w", encoding="utf-8") as state_file:
        json.dump(
            {
                "schema_version": "1.6",
                "frame_id": 42,
                "timestamp": "2026-07-26T20:00:00.000+08:00",
                "camera_id": "camera_01",
                "analytics": {},
            },
            state_file,
        )
    return frame_path, state_path


def write_camera_supervisor_state(directory):
    runtime_directory = os.path.join(directory, "data", "runtime")
    if not os.path.isdir(runtime_directory):
        os.makedirs(runtime_directory)
    state_path = os.path.join(
        runtime_directory,
        "vision-supervisor.json",
    )
    with open(state_path, "w", encoding="utf-8") as state_file:
        json.dump(
            {
                "status": "RUNNING",
                "device": "/dev/video0",
                "device_available": True,
                "worker_running": True,
                "worker_pid": 123,
                "generation": 3,
                "restart_count": 2,
                "last_exit_code": 0,
                "started_at": "2026-07-27T10:00:00+08:00",
                "updated_at": "2026-07-27T14:00:00+08:00",
                "vision": {
                    "available": True,
                    "age_seconds": 0.2,
                    "frame_id": 456,
                    "timestamp": "2026-07-27T14:00:00+08:00",
                },
                "command": ["must", "not", "leak"],
            },
            state_file,
        )
    return state_path


class CameraSnapshotToolsTests(unittest.TestCase):
    def test_status_tool_returns_bounded_healthy_read_only_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = write_camera_supervisor_state(directory)
            result = CameraStatusTools(
                directory,
                supervisor_state_path=state_path,
            ).get_status({})

            self.assertTrue(result["healthy"])
            self.assertTrue(result["read_only"])
            self.assertEqual(result["status"], "RUNNING")
            self.assertEqual(result["generation"], 3)
            self.assertEqual(result["restart_count"], 2)
            self.assertEqual(result["vision"]["frame_id"], 456)
            self.assertNotIn("worker_pid", result)
            self.assertNotIn("command", result)

    def test_registry_exposes_camera_status_as_l0_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = write_camera_supervisor_state(directory)
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                camera_state_path=state_path,
            )
            schemas = {
                item["name"]: item
                for item in registry.schemas()
            }
            annotations = schemas["camera.get_status"][
                "annotations"
            ]

            self.assertTrue(annotations["readOnlyHint"])
            self.assertEqual(annotations["riskLevel"], "L0")
            self.assertTrue(annotations["autoExecute"])
            self.assertFalse(annotations["requiresConfirmation"])
            response = registry.invoke("camera.get_status", {})
            self.assertTrue(response["result"]["healthy"])

    def test_confirmation_is_required_before_creating_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            write_live_inputs(directory)
            audit_path = os.path.join(directory, "audit.jsonl")
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                audit_path=audit_path,
            )

            with self.assertRaises(ToolInvocationError) as denied:
                registry.invoke("camera.capture_snapshot", {})

            self.assertEqual(denied.exception.code, "POLICY_DENIED")
            self.assertEqual(
                denied.exception.message,
                "CONFIRMATION_REQUIRED",
            )
            snapshot_directory = os.path.join(
                directory,
                "data",
                "evidence",
                "manual-snapshots",
            )
            self.assertFalse(os.path.exists(snapshot_directory))

            response = registry.invoke(
                "camera.capture_snapshot",
                {},
                confirmation_granted=True,
            )

            result = response["result"]
            path = os.path.join(
                directory,
                *result["evidence_path"].split("/"),
            )
            self.assertEqual(response["status"], "SUCCEEDED")
            self.assertTrue(result["created_at"].endswith("+08:00"))
            self.assertEqual(result["vision_frame_id"], 42)
            self.assertEqual(result["bytes"], len(JPEG))
            self.assertTrue(os.path.isfile(path))
            with open(path, "rb") as snapshot_file:
                self.assertEqual(snapshot_file.read(), JPEG)
            with open(audit_path, "r", encoding="utf-8") as audit:
                records = [json.loads(line) for line in audit]
            self.assertEqual(len(records), 2)
            self.assertEqual(
                records[0]["policy"]["reason"],
                "CONFIRMATION_REQUIRED",
            )
            self.assertEqual(
                records[1]["result_summary"]["snapshot_id"],
                result["snapshot_id"],
            )

    def test_rejects_a_stale_camera_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            frame_path, state_path = write_live_inputs(directory)
            old_time = time.time() - 20
            os.utime(frame_path, (old_time, old_time))
            tools = CameraSnapshotTools(
                directory,
                frame_path=frame_path,
                state_path=state_path,
                max_age_seconds=5,
            )

            with self.assertRaises(CameraSnapshotUnavailable):
                tools.capture_snapshot({})

    def test_rejects_a_stale_vision_state(self):
        with tempfile.TemporaryDirectory() as directory:
            frame_path, state_path = write_live_inputs(directory)
            old_time = time.time() - 20
            os.utime(state_path, (old_time, old_time))
            tools = CameraSnapshotTools(
                directory,
                frame_path=frame_path,
                state_path=state_path,
                max_age_seconds=5,
            )

            with self.assertRaises(CameraSnapshotUnavailable):
                tools.capture_snapshot({})

    def test_rejects_an_incomplete_jpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            frame_path, state_path = write_live_inputs(directory)
            with open(frame_path, "wb") as frame_file:
                frame_file.write(b"\xff\xd8incomplete")
            tools = CameraSnapshotTools(
                directory,
                frame_path=frame_path,
                state_path=state_path,
            )

            with self.assertRaises(CameraSnapshotUnavailable):
                tools.capture_snapshot({})


if __name__ == "__main__":
    unittest.main()
