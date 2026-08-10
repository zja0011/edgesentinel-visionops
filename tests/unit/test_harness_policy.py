import json
import os
import tempfile
import unittest

from packages.harness.audit import JsonlToolAuditRecorder
from packages.harness.default_tools import build_default_registry
from packages.harness.policy import PolicyEngine, PolicyRule
from packages.harness.registry import (
    ToolDefinition,
    ToolInvocationError,
    ToolRegistry,
)


EMPTY_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}


class PolicyEngineTests(unittest.TestCase):
    def test_allows_auto_execute_rule(self):
        engine = PolicyEngine(
            {
                "vision.read": PolicyRule(
                    "L0",
                    auto_execute=True,
                )
            }
        )

        decision = engine.evaluate("vision.read")

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.reason, "ALLOWED")
        self.assertEqual(decision.to_dict()["risk"], "L0")

    def test_denies_unknown_and_disabled_tools(self):
        engine = PolicyEngine(
            {
                "camera.restart": PolicyRule(
                    "L2",
                    enabled=False,
                )
            }
        )

        self.assertEqual(
            engine.evaluate("system.shell").reason,
            "TOOL_NOT_ALLOWLISTED",
        )
        self.assertEqual(
            engine.evaluate("camera.restart").reason,
            "TOOL_DISABLED",
        )

    def test_requires_confirmation(self):
        engine = PolicyEngine(
            {
                "camera.restart": PolicyRule(
                    "L2",
                    require_confirmation=True,
                )
            }
        )

        self.assertFalse(
            engine.evaluate("camera.restart").allowed
        )
        self.assertTrue(
            engine.evaluate(
                "camera.restart",
                confirmation_granted=True,
            ).allowed
        )


class PolicyRegistryTests(unittest.TestCase):
    def _registry(self, audit_path):
        policy = PolicyEngine(
            {
                "vision.read": PolicyRule(
                    "L0",
                    auto_execute=True,
                )
            }
        )
        registry = ToolRegistry(
            JsonlToolAuditRecorder(audit_path),
            policy_engine=policy,
        )
        registry.register(
            ToolDefinition(
                "vision.read",
                "read state",
                EMPTY_SCHEMA,
                lambda arguments: {"value": 1},
            )
        )
        return registry

    def test_exposes_policy_annotations(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = self._registry(
                os.path.join(directory, "audit.jsonl")
            )

            annotations = registry.schemas()[0]["annotations"]

            self.assertEqual(annotations["riskLevel"], "L0")
            self.assertTrue(annotations["autoExecute"])
            self.assertFalse(
                annotations["requiresConfirmation"]
            )

    def test_audits_allowed_and_denied_policy_decisions(self):
        with tempfile.TemporaryDirectory() as directory:
            audit_path = os.path.join(directory, "audit.jsonl")
            registry = self._registry(audit_path)

            allowed = registry.invoke("vision.read", {})
            with self.assertRaises(ToolInvocationError) as context:
                registry.invoke("system.shell", {})

            self.assertEqual(allowed["status"], "SUCCEEDED")
            self.assertEqual(
                context.exception.code,
                "POLICY_DENIED",
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
            self.assertEqual(
                records[0]["policy"]["reason"],
                "ALLOWED",
            )
            self.assertEqual(
                records[1]["policy"]["reason"],
                "TOOL_NOT_ALLOWLISTED",
            )

    def test_default_registry_denies_system_shell(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
            )

            with self.assertRaises(ToolInvocationError) as context:
                registry.invoke("system.shell", {})

            self.assertEqual(
                context.exception.code,
                "POLICY_DENIED",
            )


if __name__ == "__main__":
    unittest.main()
