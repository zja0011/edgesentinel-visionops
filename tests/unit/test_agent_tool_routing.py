import json
import os
import shutil
import tempfile
import unittest

from apps.run_agent_evaluation import EvaluationContextEngine
from packages.harness.agent_loop import AgentLoop, AgentResumeError
from packages.harness.checkpoint import JsonTaskCheckpointStore
from packages.harness.mock_model import ModelResponse, ToolCall
from packages.harness.policy import PolicyEngine, PolicyRule
from packages.harness.registry import ToolDefinition, ToolRegistry
from packages.harness.tool_router import ToolSchemaRouter


EMPTY_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


class RecordingModel(object):
    name = "routing-recording-model"

    def __init__(self, first_tool=None):
        self.first_tool = first_tool
        self.visible_tools = []
        self.tool_choices = []

    def generate(self, context, tool_schemas=None, conversation=None):
        del conversation
        self.visible_tools.append(
            [schema["name"] for schema in (tool_schemas or [])]
        )
        if self.first_tool and not context.get("recent_tool_results"):
            return ModelResponse(
                tool_calls=[ToolCall(self.first_tool, {})]
            )
        return ModelResponse(content="done")

    def generate_with_tool_choice(
        self,
        context,
        tool_schemas=None,
        conversation=None,
        tool_choice="auto",
    ):
        self.tool_choices.append(tool_choice)
        return self.generate(
            context,
            tool_schemas=tool_schemas,
            conversation=conversation,
        )


class ListTrace(object):
    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(dict(record))


def build_registry(calls):
    registry = ToolRegistry(
        policy_engine=PolicyEngine(
            {
                "vision.get_people_count": PolicyRule(
                    "L0", auto_execute=True
                ),
                "camera.capture_snapshot": PolicyRule(
                    "L1", require_confirmation=True
                ),
                "camera.restart": PolicyRule(
                    "L2", require_confirmation=True
                ),
            }
        )
    )

    def handler(name):
        def execute(arguments):
            del arguments
            calls.append(name)
            return {"schema_version": "1.0", "ok": True}
        return execute

    registry.register(
        ToolDefinition(
            "vision.get_people_count",
            "Return confirmed people count.",
            EMPTY_SCHEMA,
            handler("vision.get_people_count"),
        )
    )
    registry.register(
        ToolDefinition(
            "camera.capture_snapshot",
            "Capture a camera snapshot with confirmation.",
            EMPTY_SCHEMA,
            handler("camera.capture_snapshot"),
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            "camera.restart",
            "Restart camera inference with confirmation.",
            EMPTY_SCHEMA,
            handler("camera.restart"),
            read_only=False,
        )
    )
    return registry


class AgentToolRoutingTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.mkdtemp(prefix="tool-route-")
        self.calls = []
        self.registry = build_registry(self.calls)
        self.router = ToolSchemaRouter(max_tools=6)

    def tearDown(self):
        shutil.rmtree(self.directory)

    def loop(self, model, trace=None):
        return AgentLoop(
            model=model,
            context_engine=EvaluationContextEngine(),
            tool_registry=self.registry,
            trace_recorder=trace,
            checkpoint_store=JsonTaskCheckpointStore(
                self.directory
            ),
            tool_router=self.router,
            max_steps=3,
        )

    def test_only_selected_schema_reaches_every_model_step(self):
        model = RecordingModel("vision.get_people_count")
        trace = ListTrace()
        result = self.loop(model, trace).run(
            "How many people are currently in the camera view?"
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(
            model.visible_tools,
            [
                ["vision.get_people_count"],
                ["vision.get_people_count"],
            ],
        )
        self.assertEqual(
            result["tool_route"]["selected_tools"],
            ["vision.get_people_count"],
        )
        self.assertEqual(
            model.tool_choices,
            [
                {
                    "type": "function",
                    "function": {
                        "name": "vision.get_people_count"
                    },
                }
            ],
        )
        checkpoint = JsonTaskCheckpointStore(
            self.directory
        ).load(result["task_id"])
        self.assertEqual(
            checkpoint["tool_route"], result["tool_route"]
        )
        self.assertIn(
            "TOOL_ROUTE",
            [record["record_type"] for record in trace.records],
        )

    def test_registered_hidden_tool_is_denied_before_execution(self):
        model = RecordingModel("camera.restart")
        trace = ListTrace()
        result = self.loop(model, trace).run(
            "How many people are in view?"
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(
            result["error"]["code"], "TOOL_ROUTE_NOT_ALLOWED"
        )
        self.assertEqual(self.calls, [])
        self.assertIn(
            "TOOL_ROUTE_DENIED",
            [record["record_type"] for record in trace.records],
        )

    def test_unregistered_tool_still_reaches_default_deny_policy(self):
        model = RecordingModel("system.shell")
        result = self.loop(model).run("Use system.shell now")
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(result["tool_route"]["selected_tools"], [])
        self.assertEqual(
            result["tool_results"][0]["error"]["code"],
            "POLICY_DENIED",
        )
        self.assertEqual(self.calls, [])

    def test_confirmation_resume_keeps_pinned_route(self):
        model = RecordingModel("camera.capture_snapshot")
        loop = self.loop(model)
        pending = loop.run("拍摄当前画面快照")
        self.assertEqual(pending["status"], "AWAITING_CONFIRMATION")
        self.assertEqual(
            pending["tool_route"]["selected_tools"],
            ["camera.capture_snapshot"],
        )
        resumed_model = RecordingModel()
        resumed = self.loop(resumed_model).resume(
            pending["task_id"], confirmation_granted=True
        )
        self.assertEqual(resumed["status"], "COMPLETED")
        self.assertEqual(
            resumed_model.visible_tools,
            [["camera.capture_snapshot"]],
        )
        self.assertEqual(self.calls, ["camera.capture_snapshot"])
        self.assertEqual(
            resumed["tool_route"], pending["tool_route"]
        )

    def test_tampered_checkpoint_route_is_rejected(self):
        model = RecordingModel("camera.capture_snapshot")
        pending = self.loop(model).run("拍摄当前画面快照")
        path = os.path.join(
            self.directory, pending["task_id"] + ".json"
        )
        with open(path, "r", encoding="utf-8") as input_file:
            checkpoint = json.load(input_file)
        checkpoint["tool_route"]["selected_tools"] = [
            "camera.restart"
        ]
        with open(path, "w", encoding="utf-8") as output_file:
            json.dump(checkpoint, output_file)
        with self.assertRaises(AgentResumeError):
            self.loop(RecordingModel()).resume(
                pending["task_id"], confirmation_granted=True
            )


if __name__ == "__main__":
    unittest.main()
