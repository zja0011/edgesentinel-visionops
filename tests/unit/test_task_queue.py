import json
import os
import tempfile
import threading
import time
import unittest

from packages.harness.execution_control import AgentExecutionStopped
from packages.harness.task_queue import (
    AgentJobCancellationConflict,
    AgentJobIdempotencyConflict,
    AgentJobUnavailable,
    PersistentAgentJobQueue,
)


TASK_ID = "task_" + ("a" * 32)


def request(message="Question"):
    return {"message": message, "session_id": None}


def result():
    return {
        "task_id": TASK_ID,
        "status": "COMPLETED",
        "model": "test-model",
        "steps": 2,
    }


class PersistentAgentJobQueueTests(unittest.TestCase):
    def _wait_terminal(self, queue, job_id, timeout=3.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            job = queue.get(job_id)
            if job["status"] in (
                "COMPLETED",
                "FAILED",
                "CANCELLED",
                "INTERRUPTED",
            ):
                return job
            time.sleep(0.01)
        self.fail("job did not reach a terminal state")

    def test_executes_and_persists_only_bounded_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = PersistentAgentJobQueue(directory, lambda _: result())
            try:
                submitted = queue.submit(
                    request("api_key=must-not-persist")
                )
                completed = self._wait_terminal(
                    queue,
                    submitted["job_id"],
                )

                self.assertEqual(completed["status"], "COMPLETED")
                self.assertEqual(completed["task_id"], TASK_ID)
                self.assertFalse(completed["request_body_persisted"])
                path = os.path.join(
                    directory,
                    submitted["job_id"] + ".json",
                )
                with open(path, "r", encoding="utf-8") as input_file:
                    persisted = input_file.read()
                self.assertNotIn("api_key", persisted)
                self.assertNotIn("must-not-persist", persisted)
                self.assertNotIn("message", persisted)
            finally:
                queue.close()

    def test_idempotency_replays_same_request_and_rejects_change(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []

            def executor(payload):
                calls.append(payload)
                return result()

            queue = PersistentAgentJobQueue(directory, executor)
            try:
                first = queue.submit(
                    request("same"),
                    idempotency_key="request-key-0001",
                )
                replay = queue.submit(
                    request("same"),
                    idempotency_key="request-key-0001",
                )
                self.assertEqual(first["job_id"], replay["job_id"])
                self.assertTrue(replay["idempotent_replay"])
                with self.assertRaises(AgentJobIdempotencyConflict):
                    queue.submit(
                        request("changed"),
                        idempotency_key="request-key-0001",
                    )
                self._wait_terminal(queue, first["job_id"])
                self.assertEqual(len(calls), 1)
            finally:
                queue.close()

    def test_cancels_only_queued_job(self):
        with tempfile.TemporaryDirectory() as directory:
            started = threading.Event()
            release = threading.Event()

            def executor(_):
                started.set()
                release.wait(2.0)
                return result()

            queue = PersistentAgentJobQueue(directory, executor)
            try:
                running = queue.submit(request("first"))
                self.assertTrue(started.wait(1.0))
                queued = queue.submit(request("second"))
                cancelled = queue.cancel(queued["job_id"])
                self.assertEqual(cancelled["status"], "CANCELLED")
                with self.assertRaises(AgentJobCancellationConflict):
                    queue.cancel(running["job_id"])
                release.set()
                self._wait_terminal(queue, running["job_id"])
            finally:
                release.set()
                queue.close()

    def test_wait_for_change_reports_sequence_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            release = threading.Event()

            def executor(_):
                release.wait(2.0)
                return result()

            queue = PersistentAgentJobQueue(directory, executor)
            try:
                job = queue.submit(request())
                changed, did_change = queue.wait_for_change(
                    job["job_id"],
                    after_sequence=-1,
                    timeout=0.2,
                )
                self.assertTrue(did_change)
                self.assertGreaterEqual(changed["sequence"], 0)
                deadline = time.time() + 1.0
                current = queue.get(job["job_id"])
                while (
                    current["status"] != "RUNNING"
                    and time.time() < deadline
                ):
                    time.sleep(0.01)
                    current = queue.get(job["job_id"])
                self.assertEqual(current["status"], "RUNNING")
                same, did_change = queue.wait_for_change(
                    job["job_id"],
                    after_sequence=current["sequence"],
                    timeout=0.05,
                )
                self.assertFalse(did_change)
                self.assertEqual(same["sequence"], current["sequence"])
            finally:
                release.set()
                queue.close()

    def test_restart_marks_unfinished_metadata_interrupted(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = PersistentAgentJobQueue(directory, lambda _: result())
            try:
                completed = self._wait_terminal(
                    queue,
                    queue.submit(request())["job_id"],
                )
            finally:
                queue.close()
            path = os.path.join(
                directory,
                completed["job_id"] + ".json",
            )
            with open(path, "r", encoding="utf-8") as input_file:
                metadata = json.load(input_file)
            metadata["status"] = "RUNNING"
            metadata["completed_at"] = None
            with open(path, "w", encoding="utf-8") as output_file:
                json.dump(metadata, output_file)

            restarted = PersistentAgentJobQueue(
                directory,
                lambda _: result(),
            )
            try:
                recovered = restarted.get(completed["job_id"])
                self.assertEqual(recovered["status"], "INTERRUPTED")
                self.assertEqual(
                    recovered["error_code"],
                    "SERVICE_RESTARTED",
                )
            finally:
                restarted.close()

    def test_cooperatively_cancels_a_running_job(self):
        with tempfile.TemporaryDirectory() as directory:
            started = threading.Event()

            def executor(_, control):
                started.set()
                while True:
                    try:
                        control.check("test_safe_point")
                    except AgentExecutionStopped as stopped:
                        return {
                            "task_id": TASK_ID,
                            "status": "CANCELLED",
                            "model": "test-model",
                            "steps": 1,
                            "error": {"code": stopped.code},
                            "execution": stopped.snapshot,
                        }
                    time.sleep(0.005)

            queue = PersistentAgentJobQueue(
                directory,
                executor,
                cooperative_cancel=True,
            )
            try:
                submitted = queue.submit(request("running"))
                self.assertTrue(started.wait(1.0))
                running = queue.get(submitted["job_id"])
                self.assertEqual(running["status"], "RUNNING")
                self.assertTrue(running["safe_cancel"])
                requested = queue.cancel(submitted["job_id"])
                self.assertEqual(requested["status"], "RUNNING")
                self.assertTrue(requested["cancel_pending"])
                self.assertFalse(requested["safe_cancel"])
                terminal = self._wait_terminal(
                    queue, submitted["job_id"]
                )
                self.assertEqual(terminal["status"], "CANCELLED")
                self.assertEqual(terminal["task_status"], "CANCELLED")
                self.assertEqual(
                    terminal["error_code"], "TASK_CANCELLED"
                )
                self.assertEqual(terminal["task_id"], TASK_ID)
                self.assertTrue(
                    terminal["execution"]["cancel_requested"]
                )
                self.assertFalse(
                    terminal["execution"]["force_terminated"]
                )
            finally:
                queue.close()

    def test_rejects_tampered_execution_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            queue = PersistentAgentJobQueue(directory, lambda _: result())
            try:
                completed = self._wait_terminal(
                    queue, queue.submit(request())["job_id"]
                )
            finally:
                queue.close()
            path = os.path.join(
                directory, completed["job_id"] + ".json"
            )
            with open(path, "r", encoding="utf-8") as input_file:
                metadata = json.load(input_file)
            metadata["execution"]["secret"] = "must-not-be-exposed"
            with open(path, "w", encoding="utf-8") as output_file:
                json.dump(metadata, output_file)

            restarted = PersistentAgentJobQueue(
                directory, lambda _: result()
            )
            try:
                with self.assertRaises(AgentJobUnavailable):
                    restarted.get(completed["job_id"])
            finally:
                restarted.close()


if __name__ == "__main__":
    unittest.main()
