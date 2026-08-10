import json
import os
import tempfile
import unittest

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.harness.audit import JsonlToolAuditRecorder
from packages.harness.default_tools import build_default_registry
from packages.harness.registry import (
    ToolDefinition,
    ToolInvocationError,
    ToolRegistry,
)


SIMPLE_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
        },
    },
    "additionalProperties": False,
}


class ToolRegistryTests(unittest.TestCase):
    def test_lists_registered_tool_schema(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                "test.echo",
                "Echo arguments.",
                SIMPLE_SCHEMA,
                lambda arguments: arguments,
            )
        )

        schemas = registry.schemas()

        self.assertEqual(schemas[0]["name"], "test.echo")
        self.assertTrue(
            schemas[0]["annotations"]["readOnlyHint"]
        )

    def test_invokes_tool_with_validated_arguments(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                "test.echo",
                "Echo arguments.",
                SIMPLE_SCHEMA,
                lambda arguments: {"count": arguments["limit"]},
            )
        )

        response = registry.invoke("test.echo", {"limit": 3})

        self.assertEqual(response["status"], "SUCCEEDED")
        self.assertEqual(response["result"], {"count": 3})
        self.assertTrue(response["started_at"].endswith("+08:00"))

    def test_rejects_unknown_tool(self):
        registry = ToolRegistry()

        with self.assertRaises(ToolInvocationError) as raised:
            registry.invoke("unknown.tool", {})

        self.assertEqual(raised.exception.code, "TOOL_NOT_FOUND")

    def test_rejects_unknown_wrong_type_and_out_of_range_arguments(self):
        registry = ToolRegistry()
        registry.register(
            ToolDefinition(
                "test.echo",
                "Echo arguments.",
                SIMPLE_SCHEMA,
                lambda arguments: arguments,
            )
        )

        invalid_arguments = (
            {"unexpected": 1},
            {"limit": "3"},
            {"limit": 0},
            {"limit": 11},
        )
        for arguments in invalid_arguments:
            with self.assertRaises(ToolInvocationError) as raised:
                registry.invoke("test.echo", arguments)
            self.assertEqual(
                raised.exception.code,
                "INVALID_ARGUMENTS",
            )

    def test_audits_success_without_copying_full_result(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "audit.jsonl")
            registry = ToolRegistry(JsonlToolAuditRecorder(path))
            registry.register(
                ToolDefinition(
                    "test.echo",
                    "Echo arguments.",
                    SIMPLE_SCHEMA,
                    lambda arguments: {
                        "count": 2,
                        "events": [{"secret": "not-audited"}],
                    },
                )
            )

            response = registry.invoke("test.echo", {"limit": 2})

            with open(path, "r", encoding="utf-8") as audit_file:
                record = json.loads(audit_file.readline())
            self.assertEqual(
                record["call_id"],
                response["call_id"],
            )
            self.assertEqual(
                record["result_summary"],
                {"count": 2},
            )
            self.assertNotIn("events", record)

    def test_audits_failed_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "audit.jsonl")
            registry = ToolRegistry(JsonlToolAuditRecorder(path))
            registry.register(
                ToolDefinition(
                    "test.echo",
                    "Echo arguments.",
                    SIMPLE_SCHEMA,
                    lambda arguments: arguments,
                )
            )

            with self.assertRaises(ToolInvocationError):
                registry.invoke("test.echo", {"limit": 0})

            with open(path, "r", encoding="utf-8") as audit_file:
                record = json.loads(audit_file.readline())
            self.assertEqual(record["status"], "FAILED")
            self.assertEqual(
                record["error"]["code"],
                "INVALID_ARGUMENTS",
            )

    def test_event_query_tool_reads_real_sqlite_events(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            audit = os.path.join(directory, "tool-calls.jsonl")
            store = SqliteEventStore(database)
            store.append(
                Event(
                    event_type="OBJECT_APPEARED",
                    timestamp="2026-07-24T20:00:00.000+08:00",
                    frame_id=1,
                    camera_id="camera_01",
                    zone_id="global",
                    zone_name="Global Scene",
                    track_id=None,
                    object_class="bottle",
                    event_id="evt_tool_test",
                )
            )
            store.close()
            registry = build_default_registry(
                directory,
                database,
                audit,
            )

            response = registry.invoke(
                "event.query",
                {"object_class": "bottle", "limit": 1},
            )

            self.assertEqual(response["result"]["count"], 1)
            self.assertEqual(
                response["result"]["events"][0]["event_id"],
                "evt_tool_test",
            )
            self.assertTrue(os.path.isfile(audit))
            schema = next(
                tool
                for tool in registry.schemas()
                if tool["name"] == "event.query"
            )
            self.assertEqual(
                schema["inputSchema"]["properties"]["minutes"][
                    "maximum"
                ],
                1440,
            )
            self.assertEqual(
                schema["inputSchema"]["properties"]["severity"][
                    "enum"
                ],
                ["INFO", "MEDIUM", "HIGH", "CRITICAL"],
            )
            self.assertEqual(
                schema["inputSchema"]["properties"]["cursor"][
                    "maxLength"
                ],
                2048,
            )
            summary_schema = next(
                tool
                for tool in registry.schemas()
                if tool["name"] == "event.summarize"
            )
            self.assertEqual(
                summary_schema["annotations"]["riskLevel"],
                "L0",
            )
            self.assertEqual(
                summary_schema["inputSchema"]["properties"][
                    "recent_limit"
                ]["maximum"],
                10,
            )
            self.assertEqual(
                summary_schema["inputSchema"]["properties"][
                    "severity"
                ]["enum"],
                ["INFO", "MEDIUM", "HIGH", "CRITICAL"],
            )
            self.assertEqual(
                summary_schema["inputSchema"]["properties"][
                    "bucket_minutes"
                ]["enum"],
                [15, 30, 60],
            )
            self.assertEqual(
                summary_schema["inputSchema"]["properties"][
                    "compare_previous"
                ]["type"],
                "boolean",
            )
            self.assertEqual(
                summary_schema["inputSchema"]["properties"][
                    "change_threshold_percent"
                ]["default"],
                25,
            )
            self.assertEqual(
                summary_schema["inputSchema"]["properties"][
                    "change_threshold_events"
                ]["default"],
                10,
            )
            self.assertEqual(
                summary_schema["inputSchema"]["properties"][
                    "comparison_offset_minutes"
                ]["maximum"],
                10080,
            )
            self.assertEqual(
                summary_schema["inputSchema"]["properties"][
                    "include_reference_baselines"
                ]["type"],
                "boolean",
            )
            summary_response = registry.invoke(
                "event.summarize",
                {
                    "minutes": 1440,
                    "recent_limit": 5,
                    "compare_previous": True,
                    "status": "OPEN",
                    "severity": "INFO",
                },
            )
            self.assertEqual(
                summary_response["status"],
                "SUCCEEDED",
            )
            self.assertIn(
                "comparison",
                summary_response["result"],
            )
            with self.assertRaises(ToolInvocationError) as raised:
                registry.invoke(
                    "event.summarize",
                    {"compare_previous": "true"},
                )
            self.assertEqual(
                raised.exception.code,
                "INVALID_ARGUMENTS",
            )


if __name__ == "__main__":
    unittest.main()
