import json
import os
import tempfile
import unittest

from packages.harness.trace_query import (
    AgentTaskTraceQuery,
    AgentTraceUnavailable,
)


TASK_ID = "task_" + ("a" * 32)
OTHER_TASK_ID = "task_" + ("b" * 32)


class AgentTaskTraceQueryTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.trace_path = os.path.join(
            self.temporary_directory.name,
            "api-agent-trace.jsonl",
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def _write(self, records):
        with open(
            self.trace_path,
            "w",
            encoding="utf-8",
        ) as output_file:
            for record in records:
                output_file.write(
                    json.dumps(record, ensure_ascii=False) + "\n"
                )

    def test_filters_task_and_removes_model_content(self):
        self._write(
            [
                {
                    "task_id": OTHER_TASK_ID,
                    "record_type": "TASK_RESULT",
                    "status": "FAILED",
                },
                {
                    "schema_version": "1.0",
                    "timestamp": "2026-07-30T12:00:00+08:00",
                    "task_id": TASK_ID,
                    "record_type": "MODEL_DECISION",
                    "step": 1,
                    "model": "deepseek-v4-flash",
                    "content": "must not be exposed",
                    "tool_calls": [
                        {
                            "name": "weather.get_current",
                            "arguments": {
                                "location": "武汉",
                                "api_key": "must-not-leak",
                            },
                        }
                    ],
                },
            ]
        )

        payload = AgentTaskTraceQuery(self.trace_path).get(TASK_ID)

        self.assertEqual(payload["count"], 1)
        self.assertTrue(payload["read_only"])
        self.assertFalse(payload["model_content_exposed"])
        self.assertFalse(payload["raw_trace_exposed"])
        record = payload["records"][0]
        self.assertNotIn("content", record)
        arguments = record["tool_calls"][0]["arguments"]
        self.assertEqual(arguments["location"], "武汉")
        self.assertEqual(arguments["api_key"], "[REDACTED]")
        self.assertNotIn("must-not-leak", str(payload))

    def test_applies_record_limit_and_reports_truncation(self):
        self._write(
            [
                {
                    "task_id": TASK_ID,
                    "record_type": "TOOL_RESULT",
                    "step": index,
                    "tool_name": "event.query",
                    "status": "SUCCEEDED",
                }
                for index in range(1, 6)
            ]
        )

        payload = AgentTaskTraceQuery(self.trace_path).get(
            TASK_ID,
            limit=2,
        )

        self.assertEqual(payload["count"], 2)
        self.assertTrue(payload["truncated"])
        self.assertEqual(payload["records"][0]["step"], 4)
        self.assertEqual(payload["records"][1]["step"], 5)

    def test_exposes_only_pinned_skill_identity(self):
        self._write(
            [
                {
                    "task_id": TASK_ID,
                    "record_type": "SKILL_SELECTED",
                    "step": 0,
                    "skill_name": "vision.investigate_removed_item",
                    "skill_version": "1.0.0",
                    "skill_sha256": "a" * 64,
                    "instructions": "must not be exposed",
                }
            ]
        )

        payload = AgentTaskTraceQuery(self.trace_path).get(TASK_ID)

        record = payload["records"][0]
        self.assertEqual(
            record["skill_name"],
            "vision.investigate_removed_item",
        )
        self.assertEqual(record["skill_version"], "1.0.0")
        self.assertNotIn("instructions", record)

    def test_exposes_bounded_hook_metadata_without_payload(self):
        self._write(
            [
                {
                    "task_id": TASK_ID,
                    "record_type": "HOOK_RESULT",
                    "step": 1,
                    "hook_point": "before_tool",
                    "hook_name": "guard.tool_visibility",
                    "failure_policy": "FAIL_CLOSED",
                    "timeout_ms": 100,
                    "status": "SUCCEEDED",
                    "decision": "ALLOW",
                    "latency_ms": 0.3,
                    "payload": {"api_key": "must-not-leak"},
                }
            ]
        )

        payload = AgentTaskTraceQuery(self.trace_path).get(TASK_ID)

        record = payload["records"][0]
        self.assertEqual(record["hook_point"], "before_tool")
        self.assertEqual(
            record["hook_name"],
            "guard.tool_visibility",
        )
        self.assertEqual(record["decision"], "ALLOW")
        self.assertNotIn("payload", record)
        self.assertNotIn("must-not-leak", str(payload))

    def test_exposes_only_bounded_session_memory_metadata(self):
        self._write(
            [
                {
                    "task_id": TASK_ID,
                    "record_type": "SESSION_MEMORY",
                    "step": 2,
                    "status": "COMPLETED",
                    "memory_action": "SAVED",
                    "prior_turn_count": 1,
                    "turn_count": 2,
                    "max_turns": 12,
                    "retention_days": 7,
                    "session_id": "sess_" + ("c" * 32),
                    "turns": [
                        {"user_message": "must not be exposed"}
                    ],
                }
            ]
        )

        payload = AgentTaskTraceQuery(self.trace_path).get(TASK_ID)

        record = payload["records"][0]
        self.assertEqual(record["memory_action"], "SAVED")
        self.assertEqual(record["prior_turn_count"], 1)
        self.assertEqual(record["turn_count"], 2)
        self.assertEqual(record["max_turns"], 12)
        self.assertEqual(record["retention_days"], 7)
        self.assertNotIn("session_id", record)
        self.assertNotIn("turns", record)
        self.assertNotIn("must not be exposed", str(payload))

    def test_exposes_bounded_tool_route_without_prompt_content(self):
        self._write(
            [
                {
                    "task_id": TASK_ID,
                    "record_type": "TOOL_ROUTE",
                    "route_mode": "DETERMINISTIC",
                    "catalog_tools": 30,
                    "selected_tools": [
                        "vision.get_people_count",
                    ],
                    "selected_count": 1,
                    "max_tools": 6,
                    "schema_bytes_before": 20000,
                    "schema_bytes_after": 600,
                    "schema_reduction_percent": 97.0,
                    "fallback_used": False,
                    "user_message": "must not be exposed",
                }
            ]
        )

        payload = AgentTaskTraceQuery(self.trace_path).get(TASK_ID)
        record = payload["records"][0]

        self.assertEqual(record["route_mode"], "DETERMINISTIC")
        self.assertEqual(
            record["selected_tools"],
            ["vision.get_people_count"],
        )
        self.assertEqual(record["schema_reduction_percent"], 97.0)
        self.assertNotIn("user_message", record)
        self.assertNotIn("must not be exposed", str(payload))

    def test_exposes_model_resilience_without_error_body(self):
        self._write(
            [
                {
                    "task_id": TASK_ID,
                    "record_type": "MODEL_RESILIENCE",
                    "step": 1,
                    "requested_mode": "remote",
                    "served_mode": "offline",
                    "remote_attempts": 2,
                    "retry_count": 1,
                    "fallback_used": True,
                    "fallback_reason": "MODEL_NETWORK_ERROR",
                    "circuit_state": "OPEN",
                    "provider_error_body": "must not be exposed",
                }
            ]
        )

        payload = AgentTaskTraceQuery(self.trace_path).get(TASK_ID)
        record = payload["records"][0]

        self.assertEqual(record["served_mode"], "offline")
        self.assertEqual(record["remote_attempts"], 2)
        self.assertEqual(
            record["fallback_reason"], "MODEL_NETWORK_ERROR"
        )
        self.assertNotIn("provider_error_body", record)
        self.assertNotIn("must not be exposed", str(payload))

    def test_missing_file_returns_empty_read_only_payload(self):
        payload = AgentTaskTraceQuery(self.trace_path).get(TASK_ID)

        self.assertEqual(payload["records"], [])
        self.assertEqual(payload["count"], 0)
        self.assertFalse(payload["truncated"])

    def test_rejects_invalid_task_id(self):
        with self.assertRaises(AgentTraceUnavailable):
            AgentTaskTraceQuery(self.trace_path).get("../trace")

    def test_ignores_malformed_and_oversized_lines(self):
        with open(self.trace_path, "wb") as output_file:
            output_file.write(b"{invalid}\n")
            output_file.write(b"x" * (128 * 1024 + 1) + b"\n")
            output_file.write(
                json.dumps(
                    {
                        "task_id": TASK_ID,
                        "record_type": "TASK_RESULT",
                        "status": "COMPLETED",
                    }
                ).encode("utf-8")
                + b"\n"
            )

        payload = AgentTaskTraceQuery(self.trace_path).get(TASK_ID)

        self.assertEqual(payload["count"], 1)
        self.assertEqual(
            payload["records"][0]["record_type"],
            "TASK_RESULT",
        )


if __name__ == "__main__":
    unittest.main()
