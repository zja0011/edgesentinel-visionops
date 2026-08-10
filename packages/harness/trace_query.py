"""Bounded, sanitized read-only access to Agent task traces."""

import json
import os
import re

from packages.harness.checkpoint import TASK_ID_PATTERN


SENSITIVE_KEY_PATTERN = re.compile(
    r"(?:api[_-]?key|authorization|password|secret|token)",
    re.IGNORECASE,
)
ALLOWED_RECORD_FIELDS = (
    "timestamp",
    "record_type",
    "step",
    "model",
    "status",
    "tool_name",
    "call_id",
    "error_code",
    "risk",
    "steps",
    "latency_ms",
    "skill_name",
    "skill_version",
    "skill_sha256",
    "hook_point",
    "hook_name",
    "failure_policy",
    "timeout_ms",
    "decision",
    "memory_action",
    "prior_turn_count",
    "turn_count",
    "max_turns",
    "retention_days",
    "stage",
    "usage_reported",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "cumulative_total_tokens",
    "cost_estimate_available",
    "estimated_cost_usd",
    "rate_card_id",
    "route_mode",
    "catalog_tools",
    "selected_count",
    "max_tools",
    "schema_bytes_before",
    "schema_bytes_after",
    "schema_reduction_percent",
    "fallback_used",
    "requested_mode",
    "served_mode",
    "remote_attempts",
    "retry_count",
    "fallback_reason",
    "circuit_state",
)


class AgentTraceUnavailable(LookupError):
    pass


class AgentTaskTraceQuery(object):
    def __init__(
        self,
        path,
        max_scan_bytes=2 * 1024 * 1024,
        max_records=100,
    ):
        self.path = os.path.abspath(path)
        self.max_scan_bytes = max(
            64 * 1024,
            min(int(max_scan_bytes), 8 * 1024 * 1024),
        )
        self.max_records = max(1, min(int(max_records), 200))

    def get(self, task_id, limit=50):
        task_id = self._validate_task_id(task_id)
        limit = max(1, min(int(limit), self.max_records))
        if os.path.islink(self.path):
            raise AgentTraceUnavailable(
                "agent trace file must not be a symbolic link"
            )
        if not os.path.isfile(self.path):
            return self._payload(task_id, [], False)
        try:
            file_size = os.path.getsize(self.path)
            start = max(0, file_size - self.max_scan_bytes)
            records = []
            with open(self.path, "rb") as trace_file:
                if start:
                    trace_file.seek(start)
                    trace_file.readline()
                for raw_line in trace_file:
                    if len(raw_line) > 128 * 1024:
                        continue
                    try:
                        line = raw_line.decode("utf-8")
                    except UnicodeError:
                        continue
                    if len(line) > 128 * 1024:
                        continue
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if (
                        not isinstance(record, dict)
                        or record.get("task_id") != task_id
                    ):
                        continue
                    records.append(self._sanitize_record(record))
        except (OSError, UnicodeError) as error:
            raise AgentTraceUnavailable(
                "agent trace file is unavailable"
            ) from error
        count_before_limit = len(records)
        records = records[-limit:]
        truncated = bool(
            start > 0 or count_before_limit > len(records)
        )
        return self._payload(task_id, records, truncated)

    @staticmethod
    def _validate_task_id(task_id):
        task_id = str(task_id or "")
        if not TASK_ID_PATTERN.match(task_id):
            raise AgentTraceUnavailable("invalid task id")
        return task_id

    @classmethod
    def _sanitize_record(cls, record):
        result = {
            "schema_version": "1.0",
        }
        for field in ALLOWED_RECORD_FIELDS:
            value = record.get(field)
            if isinstance(value, (str, int, float, bool)):
                if isinstance(value, str):
                    value = value[:256]
                result[field] = value
        tool_calls = record.get("tool_calls")
        if isinstance(tool_calls, list):
            result["tool_calls"] = [
                cls._sanitize_tool_call(item)
                for item in tool_calls[:8]
                if isinstance(item, dict)
            ]
        selected_tools = record.get("selected_tools")
        if isinstance(selected_tools, list):
            result["selected_tools"] = [
                str(name)[:128]
                for name in selected_tools[:8]
                if isinstance(name, str)
            ]
        return result

    @classmethod
    def _sanitize_tool_call(cls, tool_call):
        return {
            "name": str(tool_call.get("name") or "")[:128],
            "arguments": cls._sanitize_value(
                tool_call.get("arguments") or {},
                depth=0,
            ),
        }

    @classmethod
    def _sanitize_value(cls, value, depth):
        if depth >= 4:
            return "[TRUNCATED]"
        if isinstance(value, dict):
            result = {}
            for key in sorted(value, key=lambda item: str(item))[:32]:
                key_text = str(key)[:128]
                if SENSITIVE_KEY_PATTERN.search(key_text):
                    result[key_text] = "[REDACTED]"
                else:
                    result[key_text] = cls._sanitize_value(
                        value[key],
                        depth + 1,
                    )
            return result
        if isinstance(value, list):
            return [
                cls._sanitize_value(item, depth + 1)
                for item in value[:32]
            ]
        if isinstance(value, str):
            return value[:512]
        if value is None or isinstance(value, (int, float, bool)):
            return value
        return str(value)[:256]

    @staticmethod
    def _payload(task_id, records, truncated):
        return {
            "schema_version": "1.0",
            "task_id": task_id,
            "count": len(records),
            "records": list(records),
            "truncated": bool(truncated),
            "read_only": True,
            "model_content_exposed": False,
            "raw_trace_exposed": False,
        }
