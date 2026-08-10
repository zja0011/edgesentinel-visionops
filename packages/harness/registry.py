"""Allowlisted tool registration, validation, execution, and auditing."""

import re
import time
import uuid

from packages.vision.schemas import beijing_timestamp


TOOL_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)


class ToolInvocationError(RuntimeError):
    def __init__(self, code, message, call_id, tool_name):
        super(ToolInvocationError, self).__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.call_id = str(call_id)
        self.tool_name = str(tool_name)

    def to_dict(self):
        return {
            "schema_version": "1.0",
            "call_id": self.call_id,
            "tool_name": self.tool_name,
            "status": "FAILED",
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }


class ToolDefinition(object):
    def __init__(
        self,
        name,
        description,
        input_schema,
        handler,
        read_only=True,
        open_world=False,
    ):
        if not TOOL_NAME_PATTERN.match(str(name)):
            raise ValueError("invalid tool name: {0}".format(name))
        if not callable(handler):
            raise TypeError("tool handler must be callable")
        self.name = str(name)
        self.description = str(description)
        self.input_schema = dict(input_schema)
        self.handler = handler
        self.read_only = bool(read_only)
        self.open_world = bool(open_world)

    def to_schema(self):
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.input_schema,
            "annotations": {
                "readOnlyHint": self.read_only,
                "openWorldHint": self.open_world,
            },
        }


class ToolRegistry(object):
    def __init__(self, audit_recorder=None, policy_engine=None):
        self._tools = {}
        self._audit_recorder = audit_recorder
        self._policy_engine = policy_engine

    def register(self, definition):
        if not isinstance(definition, ToolDefinition):
            raise TypeError("definition must be ToolDefinition")
        if definition.name in self._tools:
            raise ValueError(
                "tool is already registered: {0}".format(
                    definition.name
                )
            )
        self._tools[definition.name] = definition

    def schemas(self):
        schemas = []
        for name in sorted(self._tools):
            schema = self._tools[name].to_schema()
            if self._policy_engine is not None:
                policy = self._policy_engine.describe(name)
                if policy is not None:
                    schema["annotations"].update(
                        {
                            "riskLevel": policy["risk"],
                            "autoExecute": policy["auto_execute"],
                            "requiresConfirmation": policy[
                                "require_confirmation"
                            ],
                        }
                    )
            schemas.append(schema)
        return schemas

    def invoke(
        self,
        tool_name,
        arguments=None,
        confirmation_granted=False,
    ):
        tool_name = str(tool_name)
        call_id = "call_{0}".format(uuid.uuid4().hex)
        started_at = beijing_timestamp()
        started_clock = time.monotonic()
        safe_arguments = (
            dict(arguments) if isinstance(arguments, dict) else arguments
        )
        policy = None

        if self._policy_engine is not None:
            policy = self._policy_engine.evaluate(
                tool_name,
                confirmation_granted=confirmation_granted,
            ).to_dict()
            if not policy["allowed"]:
                return self._fail(
                    call_id,
                    tool_name,
                    safe_arguments,
                    started_at,
                    started_clock,
                    "POLICY_DENIED",
                    policy["reason"],
                    policy=policy,
                )

        definition = self._tools.get(tool_name)
        if definition is None:
            return self._fail(
                call_id,
                tool_name,
                safe_arguments,
                started_at,
                started_clock,
                "TOOL_NOT_FOUND",
                "tool is not registered",
                policy=policy,
            )

        try:
            validated_arguments = self._validate_arguments(
                definition.input_schema,
                arguments if arguments is not None else {},
            )
        except (TypeError, ValueError) as error:
            return self._fail(
                call_id,
                tool_name,
                safe_arguments,
                started_at,
                started_clock,
                "INVALID_ARGUMENTS",
                str(error),
                policy=policy,
            )

        try:
            result = definition.handler(validated_arguments)
        except Exception:
            return self._fail(
                call_id,
                tool_name,
                validated_arguments,
                started_at,
                started_clock,
                "TOOL_EXECUTION_FAILED",
                "tool execution failed",
                policy=policy,
            )

        completed_at = beijing_timestamp()
        latency_ms = self._latency_ms(started_clock)
        response = {
            "schema_version": "1.0",
            "call_id": call_id,
            "tool_name": tool_name,
            "status": "SUCCEEDED",
            "started_at": started_at,
            "completed_at": completed_at,
            "latency_ms": latency_ms,
            "result": result,
        }
        self._audit(
            {
                "schema_version": "1.0",
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": validated_arguments,
                "status": "SUCCEEDED",
                "started_at": started_at,
                "completed_at": completed_at,
                "latency_ms": latency_ms,
                "policy": policy,
                "result_summary": self._summarize_result(result),
                "error": None,
            }
        )
        return response

    def _fail(
        self,
        call_id,
        tool_name,
        arguments,
        started_at,
        started_clock,
        code,
        message,
        policy=None,
    ):
        completed_at = beijing_timestamp()
        latency_ms = self._latency_ms(started_clock)
        self._audit(
            {
                "schema_version": "1.0",
                "call_id": call_id,
                "tool_name": tool_name,
                "arguments": arguments,
                "status": "FAILED",
                "started_at": started_at,
                "completed_at": completed_at,
                "latency_ms": latency_ms,
                "policy": policy,
                "result_summary": None,
                "error": {
                    "code": code,
                    "message": message,
                },
            }
        )
        raise ToolInvocationError(
            code,
            message,
            call_id,
            tool_name,
        )

    def _audit(self, record):
        if self._audit_recorder is not None:
            safe_record = dict(record)
            tool_name = str(safe_record.get("tool_name") or "")
            arguments = safe_record.get("arguments")
            if tool_name.startswith("memory.") and isinstance(
                arguments,
                dict,
            ):
                if tool_name == "memory.remember":
                    safe_record["arguments"] = {
                        "kind": arguments.get("kind"),
                        "key_present": bool(arguments.get("key")),
                        "value_length": len(
                            str(arguments.get("value") or "")
                        ),
                        "content_exposed": False,
                    }
                elif tool_name == "memory.search":
                    safe_record["arguments"] = {
                        "query_present": bool(arguments.get("query")),
                        "kind": arguments.get("kind"),
                        "limit": arguments.get("limit"),
                        "content_exposed": False,
                    }
            self._audit_recorder.append(safe_record)

    @staticmethod
    def _latency_ms(started_clock):
        return round((time.monotonic() - started_clock) * 1000.0, 3)

    @staticmethod
    def _summarize_result(result):
        if (
            isinstance(result, dict)
            and "memory_id" in result
            and result.get("kind") in ("FACT", "PREFERENCE")
        ):
            return {
                "status": result.get("status"),
                "memory_id": result.get("memory_id"),
                "kind": result.get("kind"),
                "revision": result.get("revision"),
                "delete_performed": result.get("delete_performed"),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and "records" in result
            and "total_records" in result
            and result.get("bounded")
        ):
            return {
                "status": result.get("status"),
                "count": result.get("count"),
                "total_records": result.get("total_records"),
                "selected_kind": result.get("selected_kind"),
                "bounded": True,
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and result.get("provider") == "open-meteo"
            and "current" in result
        ):
            location = result.get("location") or {}
            current = result.get("current") or {}
            return {
                "provider": "open-meteo",
                "location": location.get("name"),
                "timestamp": current.get("timestamp"),
                "temperature_c": current.get("temperature_c"),
                "weather_code": current.get("weather_code"),
                "external_request": True,
                "read_only": True,
            }
        if (
            isinstance(result, dict)
            and "referenced_evidence_count" in result
            and "valid_evidence_count" in result
            and "issue_count" in result
        ):
            return {
                "status": result.get("status"),
                "checked_event_count": result.get(
                    "checked_event_count"
                ),
                "referenced_evidence_count": result.get(
                    "referenced_evidence_count"
                ),
                "valid_evidence_count": result.get(
                    "valid_evidence_count"
                ),
                "issue_count": result.get("issue_count"),
                "issues_truncated": result.get(
                    "issues_truncated"
                ),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and "track_count" in result
            and "tracks" in result
        ):
            tracks = result.get("tracks") or []
            return {
                "selected_track_id": result.get(
                    "selected_track_id"
                ),
                "selected_object_class": result.get(
                    "selected_object_class"
                ),
                "track_count": result.get("track_count"),
                "track_ids": [
                    item.get("track_id")
                    for item in tracks[:20]
                ],
                "stale": result.get("stale"),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and "requested_classes" in result
            and "counts" in result
        ):
            return {
                "requested_classes": list(
                    result.get("requested_classes") or []
                )[:20],
                "selected_zone_id": result.get(
                    "selected_zone_id"
                ),
                "minimum_confidence": result.get(
                    "minimum_confidence"
                ),
                "total_count": result.get("total_count"),
                "stale": result.get("stale"),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and "comparisons" in result
            and "total_expected" in result
        ):
            return {
                "compared_class_count": result.get(
                    "compared_class_count"
                ),
                "total_expected": result.get("total_expected"),
                "total_current": result.get("total_current"),
                "total_missing": result.get("total_missing"),
                "total_extra": result.get("total_extra"),
                "matches": result.get("matches"),
                "stale": result.get("stale"),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and "window_minutes" in result
            and "removals" in result
        ):
            return {
                "window_minutes": result.get("window_minutes"),
                "selected_object_class": result.get(
                    "selected_object_class"
                ),
                "count": result.get("count"),
                "total_removed_units": result.get(
                    "total_removed_units"
                ),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and "total_events" in result
            and "counts" in result
            and "window" in result
        ):
            return {
                "window_minutes": (
                    result.get("window") or {}
                ).get("minutes"),
                "total_events": result.get("total_events"),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and "cleanup_id" in result
            and "deleted_file_count" in result
        ):
            return {
                "status": result.get("status"),
                "cleanup_id": result.get("cleanup_id"),
                "deleted_file_count": result.get(
                    "deleted_file_count"
                ),
                "deleted_bytes": result.get("deleted_bytes"),
                "failed_file_count": result.get(
                    "failed_file_count"
                ),
                "delete_performed": result.get(
                    "delete_performed"
                ),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and "audit_exists" in result
            and "record_count" in result
            and "records" in result
        ):
            totals = result.get("totals") or {}
            return {
                "status": result.get("status"),
                "audit_exists": result.get("audit_exists"),
                "record_count": result.get("record_count"),
                "returned_count": result.get("returned_count"),
                "deleted_file_count": totals.get(
                    "deleted_file_count"
                ),
                "deleted_bytes": totals.get("deleted_bytes"),
                "failed_file_count": totals.get(
                    "failed_file_count"
                ),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and result.get("mode") == "PREVIEW_ONLY"
            and "candidates" in result
        ):
            candidates = result.get("candidates") or {}
            return {
                "status": result.get("status"),
                "mode": result.get("mode"),
                "candidate_file_count": candidates.get(
                    "file_count"
                ),
                "candidate_bytes": candidates.get("bytes"),
                "delete_performed": result.get(
                    "delete_performed"
                ),
                "read_only": result.get("read_only"),
            }
        if (
            isinstance(result, dict)
            and result.get("root") == "data"
            and "totals" in result
            and "categories" in result
        ):
            totals = result.get("totals") or {}
            return {
                "status": result.get("status"),
                "file_count": totals.get("file_count"),
                "bytes": totals.get("bytes"),
                "truncated": result.get("truncated"),
                "read_only": result.get("read_only"),
            }
        if isinstance(result, dict) and "count" in result:
            return {"count": result["count"]}
        if (
            isinstance(result, dict)
            and "event_id" in result
            and "event_type" in result
            and result.get("read_only")
        ):
            return {
                "event_id": result.get("event_id"),
                "event_type": result.get("event_type"),
                "object_class": result.get("object_class"),
                "status": result.get("status"),
                "has_evidence": bool(
                    result.get("evidence_urls")
                ),
                "read_only": True,
            }
        if (
            isinstance(result, dict)
            and "event" in result
            and "evidence" in result
            and result.get("read_only")
        ):
            event = result.get("event") or {}
            return {
                "event_id": event.get("event_id"),
                "status": result.get("status"),
                "referenced_evidence_count": result.get(
                    "referenced_evidence_count"
                ),
                "valid_evidence_count": result.get(
                    "valid_evidence_count"
                ),
                "issue_count": result.get("issue_count"),
                "read_only": True,
            }
        if isinstance(result, dict) and "current_people" in result:
            return {
                "current_people": result["current_people"],
                "stale": result.get("stale"),
            }
        if (
            isinstance(result, dict)
            and "selected_object_class" in result
            and "items" in result
        ):
            return {
                "selected_object_class": result.get(
                    "selected_object_class"
                ),
                "target_class_count": result.get(
                    "target_class_count"
                ),
                "total_current": result.get("total_current"),
                "total_visible": result.get("total_visible"),
                "stale": result.get("stale"),
                "read_only": result.get("read_only"),
            }
        if isinstance(result, dict) and "total_current" in result:
            return {
                "total_current": result["total_current"],
                "stale": result.get("stale"),
            }
        if (
            isinstance(result, dict)
            and "zone_count" in result
            and "zones" in result
        ):
            return {
                "selected_zone_id": result.get(
                    "selected_zone_id"
                ),
                "zone_count": result.get("zone_count"),
                "occupied_zone_count": result.get(
                    "occupied_zone_count"
                ),
                "unique_current_count": result.get(
                    "unique_current_count"
                ),
                "stale": result.get("stale"),
            }
        if isinstance(result, dict) and "snapshot_id" in result:
            return {
                "snapshot_id": result["snapshot_id"],
                "evidence_path": result.get("evidence_path"),
                "bytes": result.get("bytes"),
            }
        if (
            isinstance(result, dict)
            and "request_id" in result
            and "before_generation" in result
            and "after_generation" in result
        ):
            return {
                "request_id": result.get("request_id"),
                "before_generation": result.get(
                    "before_generation"
                ),
                "after_generation": result.get(
                    "after_generation"
                ),
                "before_restart_count": result.get(
                    "before_restart_count"
                ),
                "after_restart_count": result.get(
                    "after_restart_count"
                ),
                "recovery_seconds": result.get(
                    "recovery_seconds"
                ),
                "vision_frame_id": result.get(
                    "vision_frame_id"
                ),
            }
        if (
            isinstance(result, dict)
            and "device_available" in result
            and "worker_running" in result
            and "generation" in result
        ):
            return {
                "status": result.get("status"),
                "healthy": result.get("healthy"),
                "device_available": result.get(
                    "device_available"
                ),
                "worker_running": result.get("worker_running"),
                "generation": result.get("generation"),
                "restart_count": result.get("restart_count"),
                "state_stale": result.get("state_stale"),
                "read_only": result.get("read_only"),
            }
        if isinstance(result, dict) and "report_id" in result:
            return {
                "report_id": result["report_id"],
                "date": result.get("date"),
                "event_count": result.get("event_count"),
                "report_path": result.get("report_path"),
                "bytes": result.get("bytes"),
            }
        if (
            isinstance(result, dict)
            and result.get("status") == "ACKNOWLEDGED"
            and "event_id" in result
        ):
            return {
                "event_id": result["event_id"],
                "status": result["status"],
                "acknowledged_at": result.get(
                    "acknowledged_at"
                ),
                "already_acknowledged": result.get(
                    "already_acknowledged"
                ),
            }
        if (
            isinstance(result, dict)
            and "checks" in result
            and "read_only" in result
        ):
            return {
                "status": result.get("status"),
                "issues": list(result.get("issues") or [])[:8],
                "read_only": result.get("read_only"),
            }
        return {"returned": result is not None}

    @classmethod
    def _validate_arguments(cls, schema, arguments):
        if not isinstance(arguments, dict):
            raise TypeError("arguments must be a JSON object")

        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        if schema.get("additionalProperties") is False:
            unknown = sorted(set(arguments) - set(properties))
            if unknown:
                raise ValueError(
                    "unknown arguments: {0}".format(
                        ", ".join(unknown)
                    )
                )

        for name in required:
            if name not in arguments:
                raise ValueError(
                    "missing required argument: {0}".format(name)
                )

        validated = {}
        for name, value in arguments.items():
            property_schema = properties.get(name)
            if property_schema is None:
                validated[name] = value
                continue
            validated[name] = cls._validate_value(
                name,
                value,
                property_schema,
            )
        return validated

    @classmethod
    def _validate_value(cls, name, value, schema):
        value_type = schema.get("type")
        if value_type == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(
                    "{0} must be an integer".format(name)
                )
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                raise ValueError(
                    "{0} must be >= {1}".format(name, minimum)
                )
            if maximum is not None and value > maximum:
                raise ValueError(
                    "{0} must be <= {1}".format(name, maximum)
                )
        elif value_type == "number":
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
            ):
                raise TypeError(
                    "{0} must be a number".format(name)
                )
            minimum = schema.get("minimum")
            maximum = schema.get("maximum")
            if minimum is not None and value < minimum:
                raise ValueError(
                    "{0} must be >= {1}".format(name, minimum)
                )
            if maximum is not None and value > maximum:
                raise ValueError(
                    "{0} must be <= {1}".format(name, maximum)
                )
            value = float(value)
        elif value_type == "boolean":
            if not isinstance(value, bool):
                raise TypeError(
                    "{0} must be a boolean".format(name)
                )
        elif value_type == "string":
            if not isinstance(value, str):
                raise TypeError(
                    "{0} must be a string".format(name)
                )
            maximum_length = schema.get("maxLength")
            if maximum_length is not None and len(value) > maximum_length:
                raise ValueError(
                    "{0} is too long".format(name)
                )
            if schema.get("minLength") and not value:
                raise ValueError(
                    "{0} must not be empty".format(name)
                )
            allowed_values = schema.get("enum")
            if (
                isinstance(allowed_values, list)
                and value not in allowed_values
            ):
                raise ValueError(
                    "{0} must be one of: {1}".format(
                        name,
                        ", ".join(str(item) for item in allowed_values),
                    )
                )
        elif value_type == "object":
            if not isinstance(value, dict):
                raise TypeError(
                    "{0} must be an object".format(name)
                )
            minimum_properties = schema.get("minProperties")
            maximum_properties = schema.get("maxProperties")
            if (
                minimum_properties is not None
                and len(value) < minimum_properties
            ):
                raise ValueError(
                    "{0} must contain at least {1} properties".format(
                        name,
                        minimum_properties,
                    )
                )
            if (
                maximum_properties is not None
                and len(value) > maximum_properties
            ):
                raise ValueError(
                    "{0} must contain at most {1} properties".format(
                        name,
                        maximum_properties,
                    )
                )
            additional = schema.get("additionalProperties")
            if additional is False and value:
                raise ValueError(
                    "{0} does not allow properties".format(name)
                )
            if isinstance(additional, dict):
                normalized = {}
                for child_name, child_value in value.items():
                    child_name = str(child_name)
                    normalized[child_name] = cls._validate_value(
                        "{0}.{1}".format(name, child_name),
                        child_value,
                        additional,
                    )
                value = normalized
        elif value_type == "array":
            if not isinstance(value, list):
                raise TypeError(
                    "{0} must be an array".format(name)
                )
            minimum_items = schema.get("minItems")
            maximum_items = schema.get("maxItems")
            if (
                minimum_items is not None
                and len(value) < minimum_items
            ):
                raise ValueError(
                    "{0} must contain at least {1} items".format(
                        name,
                        minimum_items,
                    )
                )
            if (
                maximum_items is not None
                and len(value) > maximum_items
            ):
                raise ValueError(
                    "{0} must contain at most {1} items".format(
                        name,
                        maximum_items,
                    )
                )
            item_schema = schema.get("items")
            if isinstance(item_schema, dict):
                value = [
                    cls._validate_value(
                        "{0}[{1}]".format(name, index),
                        item,
                        item_schema,
                    )
                    for index, item in enumerate(value)
                ]
            if schema.get("uniqueItems") and len(value) != len(
                set(value)
            ):
                raise ValueError(
                    "{0} must contain unique items".format(name)
                )
        else:
            raise ValueError(
                "unsupported schema type for {0}".format(name)
            )
        return value
