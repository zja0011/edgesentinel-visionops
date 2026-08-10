import json
import os
import tempfile
import unittest

from packages.harness.session_memory import (
    SessionMemoryStore,
    SessionMemoryUnavailable,
    strip_session_conversation_prefix,
)


TASK_ONE = "task_" + ("a" * 32)
TASK_TWO = "task_" + ("b" * 32)


def task_result(task_id, status="COMPLETED", answer="answer"):
    return {
        "task_id": task_id,
        "status": status,
        "answer": answer,
    }


class SessionMemoryStoreTests(unittest.TestCase):
    def test_persists_only_bounded_conversation_turns(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionMemoryStore(directory, max_turns=2)
            session = store.create()

            store.record_task(
                session["session_id"],
                "Remember bottle.",
                task_result(
                    TASK_ONE,
                    answer="I will remember bottle in this session.",
                ),
            )
            store.record_task(
                session["session_id"],
                "Second question.",
                task_result(TASK_TWO, answer="Second answer."),
            )

            loaded = store.get(session["session_id"])
            self.assertEqual(loaded["turn_count"], 2)
            self.assertFalse(loaded["raw_tool_results_stored"])
            self.assertFalse(loaded["images_stored"])
            self.assertFalse(loaded["evidence_paths_stored"])
            self.assertNotIn("tool_results", loaded)
            self.assertTrue(
                all(
                    "tool_results" not in turn
                    for turn in loaded["turns"]
                )
            )
            history = store.model_history(session["session_id"])
            self.assertEqual(
                [record["role"] for record in history],
                ["user", "assistant", "user", "assistant"],
            )

    def test_pending_confirmation_finalizes_after_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionMemoryStore(directory)
            session_id = store.create()["session_id"]
            store.record_task(
                session_id,
                "Capture a snapshot.",
                task_result(
                    TASK_ONE,
                    status="AWAITING_CONFIRMATION",
                    answer="",
                ),
            )

            pending = store.get(session_id)
            self.assertEqual(pending["turn_count"], 0)
            self.assertEqual(pending["pending_task_count"], 1)

            finalized = store.finalize_task(
                TASK_ONE,
                task_result(
                    TASK_ONE,
                    status="COMPLETED",
                    answer="Snapshot saved.",
                ),
            )

            self.assertEqual(finalized["session_id"], session_id)
            loaded = store.get(session_id)
            self.assertEqual(loaded["turn_count"], 1)
            self.assertEqual(loaded["pending_task_count"], 0)

    def test_clear_overwrites_memory_without_deleting_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionMemoryStore(directory)
            session_id = store.create()["session_id"]
            store.record_task(
                session_id,
                "Question.",
                task_result(TASK_ONE),
            )

            result = store.clear(session_id)

            self.assertEqual(result["status"], "CLEARED")
            self.assertEqual(result["cleared_turns"], 1)
            self.assertEqual(store.get(session_id)["turn_count"], 0)
            self.assertTrue(
                os.path.isfile(
                    os.path.join(directory, session_id + ".json")
                )
            )

    def test_rejects_invalid_id_and_oversized_turn(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionMemoryStore(directory)
            session_id = store.create()["session_id"]

            with self.assertRaises(SessionMemoryUnavailable):
                store.get("../session")
            with self.assertRaises(SessionMemoryUnavailable):
                store.record_task(
                    session_id,
                    "x" * 1001,
                    task_result(TASK_ONE),
                )

    def test_rejects_expired_or_corrupted_session(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionMemoryStore(directory)
            session_id = store.create()["session_id"]
            path = os.path.join(directory, session_id + ".json")
            with open(path, "r", encoding="utf-8") as input_file:
                payload = json.load(input_file)
            payload["expires_at_epoch"] = 0
            with open(path, "w", encoding="utf-8") as output_file:
                json.dump(payload, output_file)

            with self.assertRaises(SessionMemoryUnavailable):
                store.get(session_id)

    def test_session_file_never_contains_task_tool_payload(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionMemoryStore(directory)
            session_id = store.create()["session_id"]
            result = task_result(TASK_ONE)
            result["tool_results"] = [
                {
                    "evidence_path": "private.jpg",
                    "api_key": "must-not-persist",
                }
            ]

            store.record_task(session_id, "Question.", result)

            with open(
                os.path.join(directory, session_id + ".json"),
                "r",
                encoding="utf-8",
            ) as input_file:
                persisted = input_file.read()
            self.assertNotIn("private.jpg", persisted)
            self.assertNotIn("must-not-persist", persisted)
            self.assertNotIn("tool_results", persisted)

    def test_redacts_credentials_and_evidence_references_in_text(self):
        with tempfile.TemporaryDirectory() as directory:
            store = SessionMemoryStore(directory)
            session_id = store.create()["session_id"]
            store.record_task(
                session_id,
                "Use api_key=fixture-user-secret-value",
                task_result(
                    TASK_ONE,
                    answer=(
                        "Saved data/evidence/manual/file.jpg and "
                        "/api/v1/events/evt_x/evidence/primary"
                    ),
                ),
            )

            loaded = store.get(session_id)
            rendered = json.dumps(
                loaded["turns"],
                ensure_ascii=False,
            )
            self.assertNotIn("fixture-user-secret", rendered)
            self.assertNotIn("data/evidence", rendered)
            self.assertNotIn("/api/v1/events", rendered)
            self.assertIn("[REDACTED_CREDENTIAL]", rendered)
            self.assertIn(
                "[REDACTED_EVIDENCE_REFERENCE]",
                rendered,
            )

    def test_terminal_checkpoint_strips_prior_session_prefix(self):
        checkpoint = {
            "task_id": TASK_TWO,
            "model_history": [
                {"role": "user", "context": {"old": 1}},
                {"role": "assistant", "content": "old answer"},
                {
                    "role": "user",
                    "task_id": TASK_TWO,
                    "context": {"current": 1},
                },
                {"role": "assistant", "content": "new answer"},
            ],
        }

        stripped = strip_session_conversation_prefix(
            checkpoint,
            TASK_TWO,
            expected_record_count=2,
        )

        self.assertEqual(len(stripped["model_history"]), 2)
        self.assertEqual(
            stripped["model_history"][0]["task_id"],
            TASK_TWO,
        )
        self.assertEqual(len(checkpoint["model_history"]), 4)

    def test_checkpoint_strip_rejects_missing_or_ambiguous_marker(self):
        with self.assertRaises(SessionMemoryUnavailable):
            strip_session_conversation_prefix(
                {"model_history": []},
                TASK_ONE,
            )
        duplicate = {
            "model_history": [
                {"role": "user", "task_id": TASK_ONE},
                {"role": "user", "task_id": TASK_ONE},
            ]
        }
        with self.assertRaises(SessionMemoryUnavailable):
            strip_session_conversation_prefix(
                duplicate,
                TASK_ONE,
            )


if __name__ == "__main__":
    unittest.main()
