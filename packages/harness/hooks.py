"""Bounded Agent lifecycle Hooks with timeout and failure policy."""

import copy
import queue
import re
import threading
import time

from packages.vision.schemas import beijing_timestamp


HOOK_POINTS = (
    "before_model",
    "after_model",
    "before_tool",
    "after_tool",
    "on_checkpoint",
    "on_task_complete",
)
FAILURE_POLICIES = ("FAIL_CLOSED", "CONTINUE")
HOOK_NAME_PATTERN = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+$"
)


class HookDispatchError(RuntimeError):
    def __init__(self, code, message, record):
        super(HookDispatchError, self).__init__(message)
        self.code = str(code)
        self.message = str(message)
        self.record = dict(record)


class HookDefinition(object):
    def __init__(
        self,
        name,
        point,
        handler,
        timeout_ms=100,
        failure_policy="FAIL_CLOSED",
        description="",
    ):
        if not HOOK_NAME_PATTERN.match(str(name)):
            raise ValueError("hook name is invalid")
        if point not in HOOK_POINTS:
            raise ValueError("hook point is invalid")
        if not callable(handler):
            raise TypeError("hook handler must be callable")
        timeout_ms = int(timeout_ms)
        if timeout_ms < 1 or timeout_ms > 5000:
            raise ValueError(
                "hook timeout_ms must be between 1 and 5000"
            )
        if failure_policy not in FAILURE_POLICIES:
            raise ValueError("hook failure policy is invalid")
        description = str(description).strip()
        if not description or len(description) > 300:
            raise ValueError("hook description is invalid")
        self.name = str(name)
        self.point = str(point)
        self.handler = handler
        self.timeout_ms = timeout_ms
        self.failure_policy = str(failure_policy)
        self.description = description

    def to_public(self):
        return {
            "name": self.name,
            "point": self.point,
            "description": self.description,
            "timeout_ms": self.timeout_ms,
            "failure_policy": self.failure_policy,
        }


class HookDispatcher(object):
    def __init__(
        self,
        definitions=None,
        audit_recorder=None,
        trace_recorder=None,
    ):
        self._hooks = {point: [] for point in HOOK_POINTS}
        self.audit_recorder = audit_recorder
        self.trace_recorder = trace_recorder
        for definition in definitions or []:
            self.register(definition)

    def register(self, definition):
        if not isinstance(definition, HookDefinition):
            raise TypeError("hook definition must be HookDefinition")
        if any(
            item.name == definition.name
            for hooks in self._hooks.values()
            for item in hooks
        ):
            raise ValueError("hook is already registered")
        self._hooks[definition.point].append(definition)
        self._hooks[definition.point].sort(
            key=lambda item: item.name
        )

    def list_public(self):
        return [
            definition.to_public()
            for point in HOOK_POINTS
            for definition in self._hooks[point]
        ]

    def dispatch(self, point, payload):
        if point not in HOOK_POINTS:
            raise ValueError("hook point is invalid")
        if not isinstance(payload, dict):
            raise TypeError("hook payload must be an object")
        records = []
        for definition in self._hooks[point]:
            record = self._run_one(definition, payload)
            records.append(record)
            self._record(record)
            if (
                record["status"] != "SUCCEEDED"
                and definition.failure_policy == "FAIL_CLOSED"
            ):
                raise HookDispatchError(
                    record.get("error_code")
                    or "HOOK_EXECUTION_FAILED",
                    "hook {0} rejected lifecycle point {1}".format(
                        definition.name,
                        point,
                    ),
                    record,
                )
            if (
                record.get("decision") == "DENY"
                and definition.failure_policy == "FAIL_CLOSED"
            ):
                raise HookDispatchError(
                    record.get("error_code") or "HOOK_REJECTED",
                    "hook {0} rejected lifecycle point {1}".format(
                        definition.name,
                        point,
                    ),
                    record,
                )
        return {
            "schema_version": "1.0",
            "point": point,
            "allowed": not any(
                record.get("decision") == "DENY"
                for record in records
            ),
            "records": records,
        }

    def _run_one(self, definition, payload):
        started_at = beijing_timestamp()
        started_clock = time.monotonic()
        output_queue = queue.Queue(maxsize=1)
        safe_payload = copy.deepcopy(payload)

        def invoke():
            try:
                output_queue.put(
                    ("result", definition.handler(safe_payload)),
                    block=False,
                )
            except Exception:
                output_queue.put(
                    ("error", None),
                    block=False,
                )

        worker = threading.Thread(
            target=invoke,
            name="hook-{0}".format(definition.name),
        )
        worker.daemon = True
        worker.start()
        worker.join(definition.timeout_ms / 1000.0)
        latency_ms = round(
            (time.monotonic() - started_clock) * 1000.0,
            3,
        )
        base = {
            "schema_version": "1.0",
            "timestamp": started_at,
            "task_id": str(payload.get("task_id") or ""),
            "record_type": "HOOK_RESULT",
            "step": int(payload.get("step") or 0),
            "hook_point": definition.point,
            "hook_name": definition.name,
            "failure_policy": definition.failure_policy,
            "timeout_ms": definition.timeout_ms,
            "latency_ms": latency_ms,
        }
        if worker.is_alive():
            return dict(
                base,
                status="TIMED_OUT",
                decision="DENY",
                error_code="HOOK_TIMEOUT",
            )
        try:
            result_type, result = output_queue.get_nowait()
        except queue.Empty:
            result_type, result = "error", None
        if result_type == "error":
            return dict(
                base,
                status="FAILED",
                decision="DENY",
                error_code="HOOK_EXECUTION_FAILED",
            )
        try:
            decision = self._validate_result(result)
        except (TypeError, ValueError):
            return dict(
                base,
                status="FAILED",
                decision="DENY",
                error_code="HOOK_RESULT_INVALID",
            )
        return dict(
            base,
            status="SUCCEEDED",
            decision=(
                "ALLOW" if decision["allow"] else "DENY"
            ),
            error_code=decision.get("code"),
        )

    @staticmethod
    def _validate_result(result):
        if result is None:
            return {"allow": True}
        if not isinstance(result, dict):
            raise TypeError("hook result must be an object")
        if set(result) - {"allow", "code"}:
            raise ValueError("hook result fields are invalid")
        if not isinstance(result.get("allow"), bool):
            raise TypeError("hook allow decision must be boolean")
        code = result.get("code")
        if code is not None:
            code = str(code)
            if not re.match(r"^[A-Z][A-Z0-9_]{1,63}$", code):
                raise ValueError("hook result code is invalid")
        if not result["allow"] and not code:
            raise ValueError("denied hook result requires a code")
        return {"allow": result["allow"], "code": code}

    def _record(self, record):
        if self.audit_recorder is not None:
            self.audit_recorder.append(record)
        if self.trace_recorder is not None:
            self.trace_recorder.append(record)


def _before_model_guard(payload):
    context = payload.get("context")
    tool_names = payload.get("visible_tool_names")
    if not isinstance(context, dict) or not isinstance(
        tool_names,
        list,
    ):
        return {"allow": False, "code": "MODEL_CONTEXT_INVALID"}
    permissions = context.get("permissions") or {}
    allowed_tools = permissions.get("allowed_tools")
    if (
        permissions.get("arbitrary_shell") is not False
        or sorted(allowed_tools or []) != sorted(tool_names)
    ):
        return {
            "allow": False,
            "code": "MODEL_CONTEXT_PERMISSION_MISMATCH",
        }
    return {"allow": True}


def _after_model_guard(payload):
    tool_calls = payload.get("tool_calls")
    if not isinstance(tool_calls, list) or len(tool_calls) > 8:
        return {"allow": False, "code": "MODEL_OUTPUT_INVALID"}
    if any(
        not isinstance(item, dict)
        or not isinstance(item.get("name"), str)
        or not isinstance(item.get("arguments"), dict)
        for item in tool_calls
    ):
        return {"allow": False, "code": "MODEL_OUTPUT_INVALID"}
    return {"allow": True}


def _before_tool_guard(payload):
    tool_name = payload.get("tool_name")
    visible = payload.get("visible_tool_names")
    if (
        not isinstance(tool_name, str)
        or not isinstance(visible, list)
        or tool_name not in visible
    ):
        return {"allow": False, "code": "TOOL_NOT_VISIBLE"}
    return {"allow": True}


def _allow(_payload):
    return {"allow": True}


def build_default_hook_dispatcher(
    audit_recorder=None,
    trace_recorder=None,
):
    definitions = [
        HookDefinition(
            "guard.model_context",
            "before_model",
            _before_model_guard,
            timeout_ms=100,
            failure_policy="FAIL_CLOSED",
            description=(
                "Verify bounded model context and advertised permissions."
            ),
        ),
        HookDefinition(
            "guard.model_output",
            "after_model",
            _after_model_guard,
            timeout_ms=100,
            failure_policy="FAIL_CLOSED",
            description=(
                "Validate bounded structural model output."
            ),
        ),
        HookDefinition(
            "guard.tool_visibility",
            "before_tool",
            _before_tool_guard,
            timeout_ms=100,
            failure_policy="FAIL_CLOSED",
            description=(
                "Deny tools that were not visible to the model."
            ),
        ),
        HookDefinition(
            "observer.tool_result",
            "after_tool",
            _allow,
            timeout_ms=100,
            failure_policy="CONTINUE",
            description="Record bounded tool completion metadata.",
        ),
        HookDefinition(
            "observer.checkpoint",
            "on_checkpoint",
            _allow,
            timeout_ms=100,
            failure_policy="CONTINUE",
            description="Record successful checkpoint persistence.",
        ),
        HookDefinition(
            "observer.task_complete",
            "on_task_complete",
            _allow,
            timeout_ms=100,
            failure_policy="CONTINUE",
            description="Record terminal Agent task completion.",
        ),
    ]
    return HookDispatcher(
        definitions,
        audit_recorder=audit_recorder,
        trace_recorder=trace_recorder,
    )
