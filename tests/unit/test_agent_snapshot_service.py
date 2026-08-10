import hashlib
import os
import tempfile
import unittest

from packages.api.agent_snapshot_service import (
    AgentSnapshotIntegrityError,
    AgentSnapshotNotFound,
    AgentSnapshotService,
)


TASK_ID = "task_0123456789abcdef0123456789abcdef"


def make_task(result=None):
    tool_results = []
    if result is not None:
        tool_results.append(
            {
                "tool_name": "camera.capture_snapshot",
                "status": "SUCCEEDED",
                "result": result,
            }
        )
    return {
        "task_id": TASK_ID,
        "status": "COMPLETED",
        "tool_results": tool_results,
    }


class AgentSnapshotServiceTests(unittest.TestCase):
    def _snapshot(self, directory, content=None):
        content = content or b"\xff\xd8snapshot-test\xff\xd9"
        relative_path = (
            "data/evidence/manual-snapshots/test.jpg"
        )
        absolute_path = os.path.join(
            directory,
            *relative_path.split("/"),
        )
        os.makedirs(os.path.dirname(absolute_path))
        with open(absolute_path, "wb") as snapshot_file:
            snapshot_file.write(content)
        result = {
            "snapshot_id": "snap_test",
            "evidence_path": relative_path,
            "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest(),
        }
        return absolute_path, result, content

    def test_adds_task_bound_url_and_resolves_verified_jpeg(self):
        with tempfile.TemporaryDirectory() as directory:
            absolute_path, result, content = self._snapshot(
                directory
            )
            service = AgentSnapshotService(directory)
            task = make_task(result)

            payload = service.add_url(task)
            snapshot = service.resolve(task)

            self.assertEqual(
                payload["snapshot_url"],
                (
                    "/api/v1/agent/tasks/{0}/snapshot".format(
                        TASK_ID
                    )
                ),
            )
            self.assertEqual(snapshot["content"], content)
            self.assertEqual(snapshot["path"], absolute_path)
            self.assertEqual(snapshot["bytes"], len(content))
            self.assertEqual(
                snapshot["sha256"],
                result["sha256"],
            )

    def test_task_without_successful_snapshot_has_no_url(self):
        with tempfile.TemporaryDirectory() as directory:
            service = AgentSnapshotService(directory)
            task = make_task()

            self.assertNotIn(
                "snapshot_url",
                service.add_url(task),
            )
            with self.assertRaises(AgentSnapshotNotFound):
                service.resolve(task)

    def test_rejects_paths_outside_manual_snapshot_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            content = b"\xff\xd8outside\xff\xd9"
            outside_path = os.path.join(directory, "outside.jpg")
            with open(outside_path, "wb") as snapshot_file:
                snapshot_file.write(content)
            result = {
                "snapshot_id": "snap_outside",
                "evidence_path": (
                    "data/evidence/manual-snapshots/"
                    "../../../outside.jpg"
                ),
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }

            with self.assertRaises(AgentSnapshotNotFound):
                AgentSnapshotService(directory).resolve(
                    make_task(result)
                )

    def test_rejects_snapshot_changed_after_audit(self):
        with tempfile.TemporaryDirectory() as directory:
            absolute_path, result, unused_content = self._snapshot(
                directory
            )
            with open(absolute_path, "wb") as snapshot_file:
                snapshot_file.write(
                    b"\xff\xd8tampered-snapshot\xff\xd9"
                )

            with self.assertRaises(AgentSnapshotIntegrityError):
                AgentSnapshotService(directory).resolve(
                    make_task(result)
                )


if __name__ == "__main__":
    unittest.main()
