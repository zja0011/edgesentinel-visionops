import json
import os
import tempfile
import unittest

from packages.harness.default_tools import build_default_registry
from packages.harness.agent_loop import AgentLoop
from packages.harness.checkpoint import JsonTaskCheckpointStore
from packages.harness.context import ContextEngine
from packages.harness.long_term_memory import (
    LongTermMemoryStore,
    LongTermMemoryUnavailable,
)
from packages.harness.mock_model import OfflineMockModel
from packages.harness.registry import ToolInvocationError
from packages.harness.trace import JsonlTraceRecorder


class LongTermMemoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = LongTermMemoryStore(
            os.path.join(self.temporary.name, "memory"),
            max_records=3,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_confirmed_records_are_created_updated_and_forgotten(self):
        created = self.store.remember(
            {
                "kind": "PREFERENCE",
                "key": "preferred language",
                "value": "Chinese",
            }
        )
        self.assertEqual(created["status"], "CREATED")
        self.assertEqual(created["revision"], 1)
        self.assertRegex(created["memory_id"], r"^mem_[0-9a-f]{32}$")

        found = self.store.search(
            {"query": "language", "limit": 5}
        )
        self.assertEqual(found["count"], 1)
        self.assertEqual(found["records"][0]["value"], "Chinese")
        self.assertTrue(found["read_only"])
        self.assertFalse(found["evidence_paths_stored"])

        updated = self.store.remember(
            {
                "kind": "PREFERENCE",
                "key": "preferred language",
                "value": "Simplified Chinese",
            }
        )
        self.assertEqual(updated["status"], "UPDATED")
        self.assertEqual(updated["memory_id"], created["memory_id"])
        self.assertEqual(updated["revision"], 2)

        forgotten = self.store.forget(
            {"memory_id": created["memory_id"]}
        )
        self.assertEqual(forgotten["status"], "FORGOTTEN")
        self.assertTrue(forgotten["delete_performed"])
        self.assertEqual(self.store.summary()["record_count"], 0)

    def test_sensitive_content_and_unbounded_growth_are_rejected(self):
        with self.assertRaises(LongTermMemoryUnavailable):
            self.store.remember(
                {
                    "kind": "FACT",
                    "key": "provider",
                    "value": "api_key=sk-not-allowed-here",
                }
            )
        with self.assertRaises(LongTermMemoryUnavailable):
            self.store.remember(
                {
                    "kind": "FACT",
                    "key": "evidence",
                    "value": "data/evidence/private.jpg",
                }
            )
        for index in range(3):
            self.store.remember(
                {
                    "kind": "FACT",
                    "key": "key-{0}".format(index),
                    "value": "value-{0}".format(index),
                }
            )
        with self.assertRaises(LongTermMemoryUnavailable):
            self.store.remember(
                {
                    "kind": "FACT",
                    "key": "overflow",
                    "value": "blocked",
                }
            )

    def test_persisted_schema_contains_only_bounded_current_records(self):
        self.store.remember(
            {"kind": "FACT", "key": "site", "value": "warehouse-a"}
        )
        with open(self.store.path, "r", encoding="utf-8") as input_file:
            payload = json.load(input_file)
        self.assertEqual(
            set(payload),
            {"schema_version", "updated_at", "records"},
        )
        self.assertEqual(
            payload["records"][0]["provenance"],
            {
                "source": "user_confirmed",
                "confirmation_required": True,
            },
        )


class LongTermMemoryHarnessTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.store = LongTermMemoryStore(
            os.path.join(self.temporary.name, "memory")
        )
        self.registry = build_default_registry(
            self.temporary.name,
            os.path.join(self.temporary.name, "events.db"),
            long_term_memory_store=self.store,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_registry_gates_writes_and_auto_executes_search(self):
        schemas = {
            item["name"]: item for item in self.registry.schemas()
        }
        self.assertEqual(
            schemas["memory.search"]["annotations"]["riskLevel"],
            "L0",
        )
        self.assertEqual(
            schemas["memory.remember"]["annotations"]["riskLevel"],
            "L1",
        )
        self.assertTrue(
            schemas["memory.remember"]["annotations"][
                "requiresConfirmation"
            ]
        )
        arguments = {
            "kind": "FACT",
            "key": "site",
            "value": "warehouse-a",
        }
        with self.assertRaises(ToolInvocationError) as caught:
            self.registry.invoke("memory.remember", arguments)
        self.assertEqual(caught.exception.code, "POLICY_DENIED")

        result = self.registry.invoke(
            "memory.remember",
            arguments,
            confirmation_granted=True,
        )
        self.assertEqual(result["status"], "SUCCEEDED")
        found = self.registry.invoke("memory.search", {"limit": 5})
        self.assertEqual(found["result"]["count"], 1)
        audit_path = os.path.join(
            self.temporary.name,
            "data",
            "harness",
            "tool-calls.jsonl",
        )
        with open(audit_path, "r", encoding="utf-8") as audit_file:
            audit_text = audit_file.read()
        self.assertNotIn("warehouse-a", audit_text)
        self.assertNotIn('"key":"site"', audit_text)
        self.assertIn('"content_exposed":false', audit_text)

        with self.assertRaises(ToolInvocationError):
            self.registry.invoke(
                "memory.forget",
                {"memory_id": result["result"]["memory_id"]},
            )

    def test_offline_model_routes_remember_search_and_forget(self):
        model = OfflineMockModel()
        remember = model.generate(
            {"user_message": "remember my preferred language is chinese"}
        )
        self.assertEqual(remember.tool_calls[0].name, "memory.remember")
        self.assertEqual(
            remember.tool_calls[0].arguments["kind"],
            "PREFERENCE",
        )
        search = model.generate(
            {"user_message": "what do you remember about language"}
        )
        self.assertEqual(search.tool_calls[0].name, "memory.search")
        forget = model.generate(
            {
                "user_message": (
                    "forget memory mem_" + "a" * 32
                )
            }
        )
        self.assertEqual(forget.tool_calls[0].name, "memory.forget")

    def test_agent_loop_pauses_persists_retrieves_and_forgets(self):
        database = os.path.join(self.temporary.name, "events.db")
        state = os.path.join(self.temporary.name, "state.json")
        loop = AgentLoop(
            model=OfflineMockModel(),
            context_engine=ContextEngine(database, state),
            tool_registry=self.registry,
            checkpoint_store=JsonTaskCheckpointStore(
                os.path.join(self.temporary.name, "checkpoints")
            ),
            trace_recorder=JsonlTraceRecorder(
                os.path.join(self.temporary.name, "trace.jsonl")
            ),
            max_steps=5,
        )
        pending = loop.run(
            "remember my preferred language is chinese"
        )
        self.assertEqual(pending["status"], "AWAITING_CONFIRMATION")
        self.assertEqual(
            pending["pending_confirmation"]["tool_name"],
            "memory.remember",
        )
        self.assertEqual(pending["tool_results"], [])
        with open(
            os.path.join(self.temporary.name, "trace.jsonl"),
            "r",
            encoding="utf-8",
        ) as trace_file:
            trace_records = [
                json.loads(line) for line in trace_file if line.strip()
            ]
        decision = next(
            record
            for record in trace_records
            if record["record_type"] == "MODEL_DECISION"
        )
        traced_arguments = decision["tool_calls"][0]["arguments"]
        self.assertFalse(traced_arguments["content_exposed"])
        self.assertNotIn("preferred language", str(decision))
        self.assertNotIn("chinese", str(decision))

        confirmed = loop.resume(
            pending["task_id"],
            confirmation_granted=True,
        )
        self.assertEqual(confirmed["status"], "COMPLETED")
        memory_id = confirmed["tool_results"][0]["result"][
            "memory_id"
        ]
        recalled = loop.run(
            "what do you remember about language"
        )
        self.assertEqual(recalled["status"], "COMPLETED")
        self.assertEqual(
            recalled["tool_results"][0]["tool_name"],
            "memory.search",
        )
        self.assertEqual(
            recalled["tool_results"][0]["result"]["count"],
            1,
        )

        forget_pending = loop.run("forget memory " + memory_id)
        self.assertEqual(
            forget_pending["pending_confirmation"]["tool_name"],
            "memory.forget",
        )
        forgotten = loop.resume(
            forget_pending["task_id"],
            confirmation_granted=True,
        )
        self.assertEqual(
            forgotten["tool_results"][0]["result"]["status"],
            "FORGOTTEN",
        )


if __name__ == "__main__":
    unittest.main()
