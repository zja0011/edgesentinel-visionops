import os
import tempfile
import unittest

from packages.harness.checkpoint import (
    CheckpointNotFound,
    JsonTaskCheckpointStore,
    task_result_from_checkpoint,
)


TASK_ID = "task_0123456789abcdef0123456789abcdef"


class JsonTaskCheckpointStoreTests(unittest.TestCase):
    def test_projects_internal_checkpoint_to_public_task_contract(self):
        task = task_result_from_checkpoint(
            {
                "schema_version": "1.0",
                "task_id": TASK_ID,
                "status": "COMPLETED",
                "model": "chat-completions-compatible",
                "started_at": "2026-08-10T13:00:00+08:00",
                "completed_at": "2026-08-10T13:00:01+08:00",
                "step": 1,
                "answer": "hello",
                "tool_results": [],
                "user_message": "must not be exposed",
                "model_history": [{"content": "must not be exposed"}],
            }
        )

        self.assertEqual(task["steps"], 1)
        self.assertNotIn("step", task)
        self.assertNotIn("user_message", task)
        self.assertNotIn("model_history", task)

    def test_atomically_saves_and_loads_checkpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonTaskCheckpointStore(directory)

            path = store.save(
                {
                    "task_id": TASK_ID,
                    "status": "RUNNING",
                    "user_message": "当前有几个人？",
                }
            )
            checkpoint = store.load(TASK_ID)

            self.assertTrue(os.path.isfile(path))
            self.assertEqual(checkpoint["status"], "RUNNING")
            self.assertEqual(
                [
                    name
                    for name in os.listdir(directory)
                    if name.endswith(".tmp")
                ],
                [],
            )

    def test_overwrites_same_task_with_latest_state(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonTaskCheckpointStore(directory)
            store.save(
                {"task_id": TASK_ID, "status": "RUNNING"}
            )
            store.save(
                {"task_id": TASK_ID, "status": "COMPLETED"}
            )

            checkpoint = store.load(TASK_ID)

            self.assertEqual(
                checkpoint["status"],
                "COMPLETED",
            )
            self.assertEqual(len(os.listdir(directory)), 1)

    def test_rejects_invalid_and_missing_task_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            store = JsonTaskCheckpointStore(directory)
            for task_id in (
                "../secret",
                "task_not_hex",
                "task_" + "0" * 31,
                "task_" + "0" * 33,
            ):
                with self.subTest(task_id=task_id):
                    with self.assertRaises(CheckpointNotFound):
                        store.load(task_id)
            with self.assertRaises(CheckpointNotFound):
                store.load(TASK_ID)


if __name__ == "__main__":
    unittest.main()
