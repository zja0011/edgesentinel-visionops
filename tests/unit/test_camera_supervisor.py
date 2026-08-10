import json
import os
import sys
import tempfile
import threading
import time
import unittest

from apps.vision_supervisor import (
    VisionSupervisor,
    device_available,
    read_restart_request,
    read_vision_freshness,
)
from packages.harness.utf8 import write_json_atomic
from packages.api.camera_service import (
    CameraStatusService,
    CameraStatusUnavailable,
)


class CameraSupervisorTests(unittest.TestCase):
    def test_device_probe_rejects_missing_path_and_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            device = os.path.join(directory, "video0")
            with open(device, "wb") as device_file:
                device_file.write(b"device")

            self.assertTrue(device_available(device))
            self.assertFalse(device_available(directory))
            self.assertFalse(
                device_available(
                    os.path.join(directory, "missing")
                )
            )

    def test_reads_atomic_vision_freshness_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "vision.json")
            with open(
                state_path,
                "w",
                encoding="utf-8",
            ) as state_file:
                json.dump(
                    {
                        "frame_id": 42,
                        "timestamp": "2026-07-26T21:00:00+08:00",
                    },
                    state_file,
                )
            modified = os.path.getmtime(state_path)

            result = read_vision_freshness(
                state_path,
                now=modified + 2.5,
            )

            self.assertTrue(result["available"])
            self.assertEqual(result["age_seconds"], 2.5)
            self.assertEqual(result["frame_id"], 42)

    def test_restarts_failed_worker_until_stop_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            device = os.path.join(directory, "video0")
            state_path = os.path.join(directory, "supervisor.json")
            vision_path = os.path.join(directory, "vision.json")
            with open(device, "wb") as device_file:
                device_file.write(b"device")
            supervisor = VisionSupervisor(
                command=[
                    sys.executable,
                    "-c",
                    "import sys; sys.exit(7)",
                ],
                device_path=device,
                state_path=state_path,
                vision_state_path=vision_path,
                retry_seconds=0.02,
                poll_seconds=0.01,
                fresh_seconds=0.05,
            )
            worker = threading.Thread(target=supervisor.run)
            worker.start()
            deadline = time.time() + 3.0
            observed_restart = False
            while time.time() < deadline:
                if os.path.isfile(state_path):
                    with open(
                        state_path,
                        "r",
                        encoding="utf-8",
                    ) as state_file:
                        state = json.load(state_file)
                    if state.get("restart_count", 0) >= 1:
                        observed_restart = True
                        break
                time.sleep(0.01)
            supervisor.request_stop()
            worker.join(timeout=3.0)

            self.assertTrue(observed_restart)
            self.assertFalse(worker.is_alive())
            with open(
                state_path,
                "r",
                encoding="utf-8",
            ) as state_file:
                final_state = json.load(state_file)
            self.assertEqual(final_state["status"], "STOPPED")
            self.assertGreaterEqual(
                final_state["restart_count"],
                1,
            )
            self.assertEqual(final_state["last_exit_code"], 7)

    def test_rejects_expired_or_replayed_restart_request(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "control.json")
            request_id = "restart_{0}".format("a" * 32)
            write_json_atomic(
                path,
                {
                    "schema_version": "1.0",
                    "request_id": request_id,
                    "action": "RESTART",
                    "status": "REQUESTED",
                    "requested_at": "time",
                    "requested_at_epoch": 100.0,
                    "expires_at_epoch": 130.0,
                },
            )

            self.assertIsNotNone(
                read_restart_request(path, now=110.0)
            )
            self.assertIsNone(
                read_restart_request(
                    path,
                    last_request_id=request_id,
                    now=110.0,
                )
            )
            self.assertIsNone(
                read_restart_request(path, now=131.0)
            )
            current_time = time.time()
            write_json_atomic(
                path,
                {
                    "schema_version": "1.0",
                    "request_id": request_id,
                    "action": "RESTART",
                    "status": "REQUESTED",
                    "requested_at": "time",
                    "requested_at_epoch": current_time,
                    "expires_at_epoch": current_time + 30.0,
                },
            )
            supervisor = VisionSupervisor(
                command=[sys.executable, "-c", "pass"],
                device_path=os.path.join(directory, "video0"),
                state_path=os.path.join(directory, "state.json"),
                vision_state_path=os.path.join(
                    directory,
                    "vision.json",
                ),
                control_path=path,
            )
            self.assertEqual(
                supervisor.last_control_request_id,
                request_id,
            )

    def test_confirmed_control_request_restarts_only_worker(self):
        with tempfile.TemporaryDirectory() as directory:
            device = os.path.join(directory, "video0")
            state_path = os.path.join(
                directory,
                "supervisor.json",
            )
            vision_path = os.path.join(directory, "vision.json")
            control_path = os.path.join(
                directory,
                "control.json",
            )
            with open(device, "wb") as device_file:
                device_file.write(b"device")
            child_code = (
                "import json,time\n"
                "path={0!r}\n"
                "frame=0\n"
                "while True:\n"
                " frame += 1\n"
                " with open(path,'w',encoding='utf-8') as f:\n"
                "  json.dump({{'frame_id':frame,'timestamp':'t'}},f)\n"
                " time.sleep(0.01)\n"
            ).format(vision_path)
            supervisor = VisionSupervisor(
                command=[sys.executable, "-c", child_code],
                device_path=device,
                state_path=state_path,
                vision_state_path=vision_path,
                control_path=control_path,
                retry_seconds=0.02,
                poll_seconds=0.01,
                fresh_seconds=0.2,
                startup_timeout_seconds=2.0,
            )
            worker = threading.Thread(target=supervisor.run)
            worker.start()
            deadline = time.time() + 5.0
            initial = None
            while time.time() < deadline:
                if os.path.isfile(state_path):
                    with open(
                        state_path,
                        "r",
                        encoding="utf-8",
                    ) as state_file:
                        initial = json.load(state_file)
                    if (
                        initial.get("status") == "RUNNING"
                        and initial.get("generation") == 1
                    ):
                        break
                time.sleep(0.01)
            self.assertIsNotNone(initial)
            self.assertEqual(initial["status"], "RUNNING")

            request_id = "restart_{0}".format("b" * 32)
            now = time.time()
            write_json_atomic(
                control_path,
                {
                    "schema_version": "1.0",
                    "request_id": request_id,
                    "action": "RESTART",
                    "status": "REQUESTED",
                    "requested_at": "requested",
                    "requested_at_epoch": now,
                    "expires_at_epoch": now + 30.0,
                },
            )
            completed = None
            while time.time() < deadline:
                with open(
                    state_path,
                    "r",
                    encoding="utf-8",
                ) as state_file:
                    current = json.load(state_file)
                control = current.get("control") or {}
                if (
                    current.get("status") == "RUNNING"
                    and current.get("generation") == 2
                    and control.get("status") == "COMPLETED"
                ):
                    completed = current
                    break
                time.sleep(0.01)
            supervisor.request_stop()
            worker.join(timeout=3.0)

            self.assertIsNotNone(completed)
            self.assertEqual(
                completed["control"]["last_request_id"],
                request_id,
            )
            self.assertEqual(completed["restart_count"], 1)
            self.assertFalse(worker.is_alive())

    def test_camera_status_returns_allowlisted_runtime_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "supervisor.json")
            with open(
                state_path,
                "w",
                encoding="utf-8",
            ) as state_file:
                json.dump(
                    {
                        "status": "RUNNING",
                        "device": "/dev/video0",
                        "device_available": True,
                        "worker_running": True,
                        "worker_pid": 999,
                        "generation": 2,
                        "restart_count": 1,
                        "last_exit_code": 0,
                        "started_at": "start",
                        "updated_at": "update",
                        "vision": {
                            "available": True,
                            "age_seconds": 0.2,
                            "frame_id": 80,
                            "timestamp": "frame",
                        },
                        "command": ["must", "not", "leak"],
                        "control": {
                            "last_request_id": (
                                "restart_{0}".format("c" * 32)
                            ),
                            "status": "COMPLETED",
                            "requested_at": "requested",
                            "completed_at": "completed",
                        },
                    },
                    state_file,
                )

            result = CameraStatusService(state_path).get_status()

            self.assertEqual(result["status"], "RUNNING")
            self.assertEqual(result["generation"], 2)
            self.assertEqual(result["restart_count"], 1)
            self.assertEqual(result["vision"]["frame_id"], 80)
            self.assertEqual(
                result["control"]["status"],
                "COMPLETED",
            )
            self.assertNotIn("worker_pid", result)
            self.assertNotIn("command", result)

    def test_camera_status_rejects_missing_or_unknown_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "supervisor.json")
            service = CameraStatusService(state_path)
            with self.assertRaises(CameraStatusUnavailable):
                service.get_status()
            with open(
                state_path,
                "w",
                encoding="utf-8",
            ) as state_file:
                json.dump({"status": "UNTRUSTED"}, state_file)
            with self.assertRaises(CameraStatusUnavailable):
                service.get_status()


if __name__ == "__main__":
    unittest.main()
