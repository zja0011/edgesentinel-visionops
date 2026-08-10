import os
import tempfile
import unittest

from apps.run_agent_evaluation import EvaluationContextEngine
from packages.harness.agent_loop import AgentLoop, AgentResumeError
from packages.harness.checkpoint import JsonTaskCheckpointStore
from packages.harness.mock_model import ModelResponse
from packages.harness.policy import PolicyEngine
from packages.harness.registry import ToolRegistry
from packages.harness.trace import JsonlTraceRecorder
from packages.harness.trace_query import AgentTaskTraceQuery


class RuntimeAwareModel(object):
    name = "runtime-aware-model"
    identity = "runtime-aware-model:test"

    def generate(self, context, tool_schemas=None, conversation=None):
        return ModelResponse(
            "fallback answer",
            runtime={
                "schema_version": "1.0",
                "requested_mode": "remote",
                "served_mode": "offline",
                "remote_attempts": 2,
                "retry_count": 1,
                "fallback_used": True,
                "fallback_reason": "MODEL_NETWORK_ERROR",
                "circuit_state": "CLOSED",
            },
        )


class AgentModelResilienceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        directory = self.temporary_directory.name
        self.checkpoints = JsonTaskCheckpointStore(
            os.path.join(directory, "checkpoints")
        )
        self.trace_path = os.path.join(directory, "trace.jsonl")
        self.loop = AgentLoop(
            model=RuntimeAwareModel(),
            context_engine=EvaluationContextEngine(),
            tool_registry=ToolRegistry(
                policy_engine=PolicyEngine({})
            ),
            trace_recorder=JsonlTraceRecorder(self.trace_path),
            checkpoint_store=self.checkpoints,
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_task_checkpoint_and_trace_retain_resilience_metadata(self):
        result = self.loop.run("general question")

        self.assertEqual(result["status"], "COMPLETED")
        resilience = result["model_resilience"]
        self.assertEqual(resilience["model_calls"], 1)
        self.assertEqual(resilience["remote_attempts"], 2)
        self.assertEqual(resilience["retry_count"], 1)
        self.assertEqual(resilience["fallback_count"], 1)
        self.assertEqual(
            resilience["last_served_mode"], "offline"
        )
        checkpoint = self.checkpoints.load(result["task_id"])
        self.assertEqual(
            checkpoint["model_resilience"], resilience
        )
        trace = AgentTaskTraceQuery(self.trace_path).get(
            result["task_id"]
        )
        records = [
            record
            for record in trace["records"]
            if record.get("record_type") == "MODEL_RESILIENCE"
        ]
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["served_mode"], "offline")
        self.assertEqual(
            records[0]["fallback_reason"],
            "MODEL_NETWORK_ERROR",
        )
        self.assertFalse(trace["model_content_exposed"])

    def test_resume_rejects_tampered_resilience_checkpoint(self):
        result = self.loop.run("general question")
        checkpoint = self.checkpoints.load(result["task_id"])
        checkpoint["model_resilience"]["fallback_count"] = -1
        self.checkpoints.save(checkpoint)

        with self.assertRaises(AgentResumeError):
            self.loop.resume(result["task_id"])


if __name__ == "__main__":
    unittest.main()
