import json
import os
import tempfile
import threading
import time
import unittest

from packages.harness.default_tools import build_default_registry
from packages.harness.registry import ToolInvocationError
from packages.harness.utf8 import write_json_atomic


def supervisor_payload(
    generation,
    restart_count,
    frame_id,
    control=None,
):
    return {
        "schema_version": "1.0",
        "status": "RUNNING",
        "device": "/dev/video0",
        "device_available": True,
        "worker_running": True,
        "worker_pid": 999,
        "generation": generation,
        "restart_count": restart_count,
        "last_exit_code": 0,
        "started_at": "start",
        "updated_at": "update",
        "vision": {
            "available": True,
            "age_seconds": 0.1,
            "frame_id": frame_id,
            "timestamp": "frame",
        },
        "control": control or {
            "last_request_id": None,
            "status": None,
            "requested_at": None,
            "completed_at": None,
        },
    }


class CameraRestartToolsTests(unittest.TestCase):
    def test_l2_restart_requires_confirmation_and_waits_for_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = os.path.join(directory, "data", "runtime")
            os.makedirs(runtime)
            state_path = os.path.join(
                runtime,
                "vision-supervisor.json",
            )
            control_path = os.path.join(
                runtime,
                "vision-control.json",
            )
            audit_path = os.path.join(directory, "audit.jsonl")
            write_json_atomic(
                state_path,
                supervisor_payload(3, 2, 400),
            )
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                audit_path=audit_path,
                camera_state_path=state_path,
                camera_control_path=control_path,
                camera_restart_timeout_seconds=2.0,
            )
            schema = {
                item["name"]: item
                for item in registry.schemas()
            }["camera.restart"]
            annotations = schema["annotations"]
            self.assertFalse(annotations["readOnlyHint"])
            self.assertEqual(annotations["riskLevel"], "L2")
            self.assertFalse(annotations["autoExecute"])
            self.assertTrue(annotations["requiresConfirmation"])

            with self.assertRaises(ToolInvocationError) as denied:
                registry.invoke("camera.restart", {})
            self.assertEqual(
                denied.exception.message,
                "CONFIRMATION_REQUIRED",
            )
            self.assertFalse(os.path.exists(control_path))

            responder_error = []

            def complete_request():
                try:
                    deadline = time.time() + 2.0
                    while (
                        time.time() < deadline
                        and not os.path.isfile(control_path)
                    ):
                        time.sleep(0.01)
                    with open(
                        control_path,
                        "r",
                        encoding="utf-8",
                    ) as control_file:
                        request = json.load(control_file)
                    write_json_atomic(
                        state_path,
                        supervisor_payload(
                            4,
                            3,
                            1,
                            control={
                                "last_request_id": request[
                                    "request_id"
                                ],
                                "status": "COMPLETED",
                                "requested_at": request[
                                    "requested_at"
                                ],
                                "completed_at": "completed",
                            },
                        ),
                    )
                except Exception as error:
                    responder_error.append(error)

            responder = threading.Thread(target=complete_request)
            responder.start()
            response = registry.invoke(
                "camera.restart",
                {},
                confirmation_granted=True,
            )
            responder.join(timeout=2.0)

            self.assertEqual(responder_error, [])
            self.assertEqual(response["status"], "SUCCEEDED")
            result = response["result"]
            self.assertEqual(result["before_generation"], 3)
            self.assertEqual(result["after_generation"], 4)
            self.assertEqual(result["before_restart_count"], 2)
            self.assertEqual(result["after_restart_count"], 3)
            self.assertEqual(result["vision_frame_id"], 1)
            self.assertFalse(result["state_stale"])
            self.assertTrue(
                result["request_id"].startswith("restart_")
            )
            with open(
                audit_path,
                "r",
                encoding="utf-8",
            ) as audit_file:
                records = [
                    json.loads(line) for line in audit_file
                ]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[1]["policy"]["risk"], "L2")
            self.assertEqual(
                records[1]["result_summary"]["after_generation"],
                4,
            )


if __name__ == "__main__":
    unittest.main()
