"""Run the deterministic, isolated EdgeSentinel Agent evaluation suite."""

import argparse
import os
import sys
import tempfile


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from packages.harness.agent_loop import AgentLoop
from packages.harness.checkpoint import JsonTaskCheckpointStore
from packages.harness.evaluation import (
    EvaluationDataset,
    EvaluationReportStore,
    HarnessEvaluationRunner,
)
from packages.harness.mock_model import OfflineMockModel
from packages.harness.policy import PolicyEngine, PolicyRule
from packages.harness.registry import ToolDefinition, ToolRegistry
from packages.harness.utf8 import print_json_utf8


EMPTY_OBJECT_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


class EvaluationContextEngine(object):
    """Provider-safe context without production state dependencies."""

    def build(
        self,
        user_message,
        tool_schemas,
        recent_tool_results=None,
        active_skill=None,
        available_skills=None,
    ):
        del active_skill, available_skills
        return {
            "schema_version": "1.0",
            "user_message": str(user_message),
            "vision": {
                "status": "isolated",
                "stale": False,
            },
            "recent_events": {
                "status": "isolated",
                "count": 0,
                "events": [],
            },
            "available_tools": [
                {
                    "name": schema.get("name"),
                    "risk": (
                        schema.get("annotations") or {}
                    ).get("riskLevel"),
                }
                for schema in list(tool_schemas)
            ],
            "recent_tool_results": [
                self.bounded_tool_result(item)
                for item in list(recent_tool_results or [])[-3:]
            ],
            "permissions": {
                "mode": "default_deny",
                "arbitrary_shell": False,
            },
        }

    @staticmethod
    def bounded_tool_result(result):
        result = dict(result or {})
        bounded = {
            "tool_name": result.get("tool_name"),
            "status": result.get("status"),
            "error_code": (result.get("error") or {}).get("code"),
        }
        payload = result.get("result")
        if isinstance(payload, dict):
            bounded["result"] = dict(payload)
        return bounded


class RecordingOfflineModel(object):
    name = "offline-rule-mock"
    identity = "offline-rule-mock:evaluation"

    def __init__(self):
        self._delegate = OfflineMockModel()
        self.tool_calls = []

    def generate(self, context, tool_schemas=None, conversation=None):
        response = self._delegate.generate(
            context,
            tool_schemas=tool_schemas,
            conversation=conversation,
        )
        self.tool_calls.extend(
            tool_call.to_dict()
            for tool_call in response.tool_calls
        )
        return response


class IsolatedAgentCaseExecutor(object):
    """Execute cases through the real loop, registry, and policy engine."""

    def __call__(self, case):
        counters = {}

        def handler(name, result):
            def execute(arguments):
                del arguments
                counters[name] = counters.get(name, 0) + 1
                return dict(result)

            return execute

        rules = {
            "vision.get_people_count": PolicyRule(
                "L0", auto_execute=True
            ),
            "vision.get_current_objects": PolicyRule(
                "L0", auto_execute=True
            ),
            "event.query": PolicyRule("L0", auto_execute=True),
            "camera.capture_snapshot": PolicyRule(
                "L1", require_confirmation=True
            ),
            "camera.restart": PolicyRule(
                "L2", require_confirmation=True
            ),
        }
        policy = PolicyEngine(rules)
        registry = ToolRegistry(policy_engine=policy)
        registry.register(
            ToolDefinition(
                "vision.get_people_count",
                "Return the isolated current people count.",
                EMPTY_OBJECT_SCHEMA,
                handler(
                    "vision.get_people_count",
                    {
                        "schema_version": "1.0",
                        "current_people": 1,
                        "visible_people": 1,
                        "stale": False,
                        "read_only": True,
                    },
                ),
            )
        )
        registry.register(
            ToolDefinition(
                "vision.get_current_objects",
                "Return isolated stable objects.",
                EMPTY_OBJECT_SCHEMA,
                handler(
                    "vision.get_current_objects",
                    {
                        "schema_version": "1.0",
                        "objects": [],
                        "total_current": 0,
                        "stale": False,
                        "read_only": True,
                    },
                ),
            )
        )
        registry.register(
            ToolDefinition(
                "event.query",
                "Query isolated recent events.",
                {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "minimum": 1,
                            "maximum": 100,
                        },
                        "object_class": {
                            "type": "string",
                            "minLength": 1,
                            "maxLength": 64,
                        },
                    },
                    "additionalProperties": False,
                },
                handler(
                    "event.query",
                    {
                        "schema_version": "1.0",
                        "count": 0,
                        "events": [],
                        "read_only": True,
                    },
                ),
            )
        )
        registry.register(
            ToolDefinition(
                "camera.capture_snapshot",
                "Confirmation-gated isolated snapshot.",
                EMPTY_OBJECT_SCHEMA,
                handler("camera.capture_snapshot", {}),
                read_only=False,
            )
        )
        registry.register(
            ToolDefinition(
                "camera.restart",
                "Confirmation-gated isolated camera restart.",
                EMPTY_OBJECT_SCHEMA,
                handler("camera.restart", {}),
                read_only=False,
            )
        )
        registry.register(
            ToolDefinition(
                "system.shell",
                "Unallowlisted safety canary.",
                EMPTY_OBJECT_SCHEMA,
                handler("system.shell", {}),
                read_only=False,
                open_world=True,
            )
        )

        model = RecordingOfflineModel()
        with tempfile.TemporaryDirectory(
            prefix="edgesentinel-eval-"
        ) as checkpoint_dir:
            loop = AgentLoop(
                model=model,
                context_engine=EvaluationContextEngine(),
                tool_registry=registry,
                checkpoint_store=JsonTaskCheckpointStore(
                    checkpoint_dir
                ),
                max_steps=3,
            )
            task = loop.run(case["message"])

        first_call = model.tool_calls[0] if model.tool_calls else {}
        tool_name = first_call.get("name")
        arguments = dict(first_call.get("arguments") or {})
        tool_results = list(task.get("tool_results") or [])
        pending = task.get("pending_confirmation") or {}
        if pending:
            tool_status = "NOT_EXECUTED"
            error_code = "CONFIRMATION_REQUIRED"
        elif tool_results:
            tool_status = tool_results[0].get("status")
            error_code = (
                tool_results[0].get("error") or {}
            ).get("code")
        else:
            tool_status = "NOT_EXECUTED"
            error_code = None
        policy_description = policy.describe(tool_name)
        return {
            "task_status": task.get("status"),
            "tool_name": tool_name,
            "arguments": arguments,
            "tool_status": tool_status,
            "error_code": error_code,
            "risk": (
                policy_description.get("risk")
                if policy_description is not None
                else "UNALLOWLISTED"
            ),
            "executed_handler_count": counters.get(tool_name, 0),
        }


def run_evaluation(dataset_path, output_directory):
    dataset = EvaluationDataset.load(dataset_path)
    report = HarnessEvaluationRunner(
        dataset,
        IsolatedAgentCaseExecutor(),
    ).run()
    result_path = EvaluationReportStore(output_directory).save(report)
    return report, result_path


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run the isolated Agent Harness evaluation suite."
    )
    parser.add_argument(
        "--dataset",
        default=os.path.join(
            PROJECT_DIR, "evals", "agent-routing-v1.json"
        ),
    )
    parser.add_argument(
        "--output-directory",
        default=os.path.join(PROJECT_DIR, "data", "evaluations"),
    )
    args = parser.parse_args(argv)
    report, result_path = run_evaluation(
        args.dataset,
        args.output_directory,
    )
    print_json_utf8(report)
    print("")
    print("Agent Evaluation acceptance summary:")
    print("Status: {0}".format(report["status"]))
    print(
        "Dataset: {0}@{1}".format(
            report["dataset"]["dataset_id"],
            report["dataset"]["version"],
        )
    )
    print(
        "Cases: {0}/{1}".format(
            report["summary"]["passed_cases"],
            report["summary"]["total_cases"],
        )
    )
    print(
        "Tool selection: {0:.1f}%".format(
            100.0
            * report["metrics"]["tool_selection_accuracy"][
                "rate"
            ]
        )
    )
    print(
        "Argument accuracy: {0:.1f}%".format(
            100.0
            * report["metrics"]["argument_accuracy"]["rate"]
        )
    )
    print(
        "Policy violations: {0}".format(
            report["metrics"]["unexpected_policy_violations"]
        )
    )
    print("External requests: False")
    print("Device tools executed: False")
    print("Prompts stored: False")
    print("Result: {0}".format(result_path))
    if report["status"] != "PASS":
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
