import threading
import unittest

from apps.run_agent_evaluation import EvaluationContextEngine
from packages.harness.agent_loop import AgentLoop
from packages.harness.execution_control import (
    ExecutionControl,
    ExecutionLimits,
)
from packages.harness.mock_model import ModelResponse, ToolCall
from packages.harness.policy import PolicyEngine, PolicyRule
from packages.harness.registry import ToolDefinition, ToolRegistry


EMPTY_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


def registry_with_counter(counter):
    registry = ToolRegistry(
        policy_engine=PolicyEngine(
            {"vision.test": PolicyRule("L0", auto_execute=True)}
        )
    )

    def execute(arguments):
        del arguments
        counter.append("called")
        return {"schema_version": "1.0", "count": 1}

    registry.register(
        ToolDefinition(
            "vision.test",
            "Isolated test tool.",
            EMPTY_SCHEMA,
            execute,
        )
    )
    return registry


class BlockingModel(object):
    name = "blocking-test-model"

    def __init__(self):
        self.started = threading.Event()
        self.release = threading.Event()

    def generate(self, context, tool_schemas=None, conversation=None):
        del context, tool_schemas, conversation
        self.started.set()
        self.release.wait(2.0)
        return ModelResponse(content="finished")


class OneToolThenAnswerModel(object):
    name = "one-tool-test-model"

    def generate(self, context, tool_schemas=None, conversation=None):
        del tool_schemas, conversation
        if context.get("recent_tool_results"):
            return ModelResponse(content="done")
        return ModelResponse(tool_calls=[ToolCall("vision.test", {})])


class TwoToolModel(object):
    name = "two-tool-test-model"

    def generate(self, context, tool_schemas=None, conversation=None):
        del context, tool_schemas, conversation
        return ModelResponse(
            tool_calls=[
                ToolCall("vision.test", {}),
                ToolCall("vision.test", {}),
            ]
        )


class AdvancingModel(object):
    name = "deadline-test-model"

    def __init__(self, clock):
        self.clock = clock

    def generate(self, context, tool_schemas=None, conversation=None):
        del context, tool_schemas, conversation
        self.clock[0] += 2.0
        return ModelResponse(content="late")


class UsageModel(object):
    name = "usage-test-model"

    def __init__(self, total_tokens=120):
        self.total_tokens = total_tokens

    def generate(self, context, tool_schemas=None, conversation=None):
        del context, tool_schemas, conversation
        return ModelResponse(
            content="done",
            usage={
                "prompt_tokens": self.total_tokens - 20,
                "completion_tokens": 20,
                "total_tokens": self.total_tokens,
            },
        )


class InvalidUsageModel(object):
    name = "invalid-usage-test-model"

    def generate(self, context, tool_schemas=None, conversation=None):
        del context, tool_schemas, conversation
        return ModelResponse(
            content="unsafe",
            usage={
                "prompt_tokens": "unknown",
                "completion_tokens": 1,
                "total_tokens": 1,
            },
        )


class ListTraceRecorder(object):
    def __init__(self):
        self.records = []

    def append(self, record):
        self.records.append(dict(record))


class AgentExecutionControlTests(unittest.TestCase):
    def test_running_model_is_cancelled_at_after_model_safe_point(self):
        model = BlockingModel()
        calls = []
        loop = AgentLoop(
            model,
            EvaluationContextEngine(),
            registry_with_counter(calls),
            max_steps=3,
        )
        control = ExecutionControl()
        holder = {}

        def run():
            holder["result"] = loop.run(
                "wait", execution_control=control
            )

        worker = threading.Thread(target=run)
        worker.start()
        self.assertTrue(model.started.wait(1.0))
        self.assertTrue(control.request_cancel())
        model.release.set()
        worker.join(2.0)
        self.assertFalse(worker.is_alive())
        result = holder["result"]
        self.assertEqual(result["status"], "CANCELLED")
        self.assertEqual(result["error"]["code"], "TASK_CANCELLED")
        self.assertEqual(result["error"]["stage"], "after_model")
        self.assertEqual(result["execution"]["usage"]["model_calls"], 1)
        self.assertFalse(result["execution"]["force_terminated"])
        self.assertEqual(calls, [])

    def test_model_budget_stops_before_second_model_call(self):
        calls = []
        loop = AgentLoop(
            OneToolThenAnswerModel(),
            EvaluationContextEngine(),
            registry_with_counter(calls),
            max_steps=3,
        )
        result = loop.run(
            "test",
            execution_control=ExecutionControl(
                ExecutionLimits(max_model_calls=1)
            ),
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(
            result["error"]["code"],
            "MODEL_CALL_BUDGET_EXCEEDED",
        )
        self.assertEqual(calls, ["called"])

    def test_tool_budget_stops_before_second_tool(self):
        calls = []
        loop = AgentLoop(
            TwoToolModel(),
            EvaluationContextEngine(),
            registry_with_counter(calls),
            max_steps=3,
        )
        result = loop.run(
            "test",
            execution_control=ExecutionControl(
                ExecutionLimits(max_tool_calls=1)
            ),
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(
            result["error"]["code"],
            "TOOL_CALL_BUDGET_EXCEEDED",
        )
        self.assertEqual(calls, ["called"])

    def test_deadline_is_checked_after_model_returns(self):
        clock = [10.0]
        control = ExecutionControl(
            ExecutionLimits(max_wall_seconds=1),
            clock=lambda: clock[0],
        )
        loop = AgentLoop(
            AdvancingModel(clock),
            EvaluationContextEngine(),
            registry_with_counter([]),
            max_steps=3,
        )
        result = loop.run("test", execution_control=control)
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(
            result["error"]["code"], "DEADLINE_EXCEEDED"
        )
        self.assertEqual(result["error"]["stage"], "after_model")

    def test_provider_usage_reaches_result_checkpoint_and_trace(self):
        trace = ListTraceRecorder()
        loop = AgentLoop(
            UsageModel(),
            EvaluationContextEngine(),
            registry_with_counter([]),
            trace_recorder=trace,
            max_steps=3,
        )
        result = loop.run(
            "test", execution_control=ExecutionControl()
        )
        self.assertEqual(result["status"], "COMPLETED")
        self.assertEqual(
            result["execution"]["usage"]["total_tokens"], 120
        )
        usage_records = [
            record
            for record in trace.records
            if record["record_type"] == "MODEL_USAGE"
        ]
        self.assertEqual(len(usage_records), 1)
        self.assertTrue(usage_records[0]["usage_reported"])
        self.assertEqual(
            usage_records[0]["cumulative_total_tokens"], 120
        )
        self.assertNotIn("content", usage_records[0])

    def test_token_budget_stops_after_bounded_model_response(self):
        loop = AgentLoop(
            UsageModel(total_tokens=140),
            EvaluationContextEngine(),
            registry_with_counter([]),
            max_steps=3,
        )
        result = loop.run(
            "test",
            execution_control=ExecutionControl(
                ExecutionLimits(max_total_tokens=128)
            ),
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(
            result["error"]["code"],
            "MODEL_TOKEN_BUDGET_EXCEEDED",
        )
        self.assertEqual(
            result["execution"]["usage"]["total_tokens"], 140
        )

    def test_invalid_usage_fails_closed_without_trace_crash(self):
        trace = ListTraceRecorder()
        loop = AgentLoop(
            InvalidUsageModel(),
            EvaluationContextEngine(),
            registry_with_counter([]),
            trace_recorder=trace,
            max_steps=3,
        )
        result = loop.run(
            "test", execution_control=ExecutionControl()
        )
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(
            result["error"]["code"], "MODEL_USAGE_INVALID"
        )
        self.assertIn(
            "MODEL_USAGE",
            [record["record_type"] for record in trace.records],
        )


if __name__ == "__main__":
    unittest.main()
