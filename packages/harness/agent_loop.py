"""Bounded Agent Loop using context, model, policy, tools, and traces."""

import copy
import threading
import uuid

from packages.harness.hooks import HookDispatchError
from packages.harness.checkpoint import task_result_from_checkpoint
from packages.harness.execution_control import (
    AgentExecutionStopped,
    ExecutionControl,
)
from packages.harness.model_gateway import ModelGatewayError
from packages.harness.registry import ToolInvocationError
from packages.harness.skills import SkillValidationError
from packages.harness.tool_router import (
    ToolRouteError,
    ToolSchemaRouter,
)
from packages.vision.schemas import beijing_timestamp


class AgentResumeError(RuntimeError):
    pass


class AgentLoop(object):
    def __init__(
        self,
        model,
        context_engine,
        tool_registry,
        trace_recorder=None,
        checkpoint_store=None,
        skill_registry=None,
        hook_dispatcher=None,
        tool_router=None,
        max_steps=3,
    ):
        max_steps = int(max_steps)
        if max_steps <= 0 or max_steps > 10:
            raise ValueError("max_steps must be between 1 and 10")
        self.model = model
        self.context_engine = context_engine
        self.tool_registry = tool_registry
        self.trace_recorder = trace_recorder
        self.checkpoint_store = checkpoint_store
        self.skill_registry = skill_registry
        self.hook_dispatcher = hook_dispatcher
        if (
            tool_router is not None
            and not isinstance(tool_router, ToolSchemaRouter)
        ):
            raise TypeError("tool_router must be ToolSchemaRouter")
        self.tool_router = tool_router
        self.max_steps = max_steps
        self._task_locks = {}
        self._task_locks_guard = threading.Lock()
        self._task_routes = {}
        self._task_model_resilience = {}

    @property
    def model_identity(self):
        return getattr(
            self.model,
            "identity",
            self.model.name,
        )

    def run(
        self,
        user_message,
        pause_after_step=None,
        prior_conversation=None,
        execution_control=None,
    ):
        if (
            execution_control is not None
            and not isinstance(execution_control, ExecutionControl)
        ):
            raise TypeError(
                "execution_control must be ExecutionControl"
            )
        if pause_after_step is not None:
            pause_after_step = int(pause_after_step)
            if (
                pause_after_step <= 0
                or pause_after_step >= self.max_steps
            ):
                raise ValueError(
                    "pause_after_step must be between 1 and "
                    "max_steps - 1"
                )
        task_id = "task_{0}".format(uuid.uuid4().hex)
        started_at = beijing_timestamp()
        tool_results = []
        model_history = self._conversation_prefix(
            prior_conversation
        )
        active_skill = (
            self.skill_registry.select(user_message)
            if self.skill_registry is not None
            else None
        )
        tool_route = self._route_tools(
            user_message,
            active_skill,
            prior_conversation,
        )
        if tool_route is not None:
            self._task_routes[task_id] = dict(tool_route)
            self._trace_tool_route(task_id, tool_route)
        if active_skill is not None:
            self._trace(
                {
                    "schema_version": "1.0",
                    "timestamp": beijing_timestamp(),
                    "task_id": task_id,
                    "record_type": "SKILL_SELECTED",
                    "step": 0,
                    "skill_name": active_skill.name,
                    "skill_version": active_skill.version,
                    "skill_sha256": (
                        active_skill.instructions_sha256
                    ),
                }
            )
        self._checkpoint(
            task_id=task_id,
            status="RUNNING",
            user_message=user_message,
            started_at=started_at,
            step=0,
            tool_results=tool_results,
            model_history=model_history,
            active_skill=active_skill,
        )
        result = self._decorate_skill_result(
            self._execute(
                task_id=task_id,
                user_message=user_message,
                started_at=started_at,
                tool_results=tool_results,
                model_history=model_history,
                start_step=1,
                pause_after_step=pause_after_step,
                active_skill=active_skill,
                execution_control=execution_control,
            ),
            active_skill,
        )
        result = self._decorate_tool_route_result(
            result, tool_route
        )
        result = self._decorate_model_resilience_result(
            result,
            self._task_model_resilience.get(task_id),
        )
        if execution_control is not None:
            result["execution"] = execution_control.snapshot()
            self._persist_execution_snapshot(
                task_id, result["execution"]
            )
        return result

    def resume(self, task_id, confirmation_granted=False):
        with self._task_lock(task_id):
            return self._resume(
                task_id,
                confirmation_granted=confirmation_granted,
            )

    def _resume(self, task_id, confirmation_granted=False):
        if self.checkpoint_store is None:
            raise AgentResumeError(
                "checkpoint store is required for resume"
            )
        checkpoint = self.checkpoint_store.load(task_id)
        model_resilience = self._restore_model_resilience(
            checkpoint
        )
        active_skill = self._resolve_checkpoint_skill(checkpoint)
        tool_route = self._restore_tool_route(checkpoint)
        if tool_route is not None:
            self._task_routes[task_id] = dict(tool_route)
        checkpoint_identity = checkpoint.get(
            "model_identity",
            checkpoint.get("model"),
        )
        if checkpoint_identity != self.model_identity:
            raise AgentResumeError(
                "checkpoint model does not match"
            )
        if int(checkpoint.get("max_steps", 0)) != self.max_steps:
            raise AgentResumeError(
                "checkpoint max_steps does not match"
            )
        if checkpoint.get("status") in (
            "COMPLETED",
            "FAILED",
            "CANCELLED",
        ):
            if confirmation_granted:
                raise AgentResumeError(
                    "task has no pending confirmation"
                )
            return self._result_from_checkpoint(checkpoint)
        if checkpoint.get("status") == "AWAITING_CONFIRMATION":
            if not confirmation_granted:
                raise AgentResumeError(
                    "explicit confirmation is required"
                )
            return self._decorate_model_resilience_result(
                self._decorate_tool_route_result(
                    self._decorate_skill_result(
                        self._resume_confirmed_tool(
                            checkpoint,
                            active_skill,
                        ),
                        active_skill,
                    ),
                    tool_route,
                ),
                self._task_model_resilience.get(
                    task_id, model_resilience
                ),
            )
        if checkpoint.get("status") != "RUNNING":
            raise AgentResumeError(
                "checkpoint is not resumable"
            )
        if confirmation_granted:
            raise AgentResumeError(
                "task has no pending confirmation"
            )

        step = int(checkpoint.get("step", 0))
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": beijing_timestamp(),
                "task_id": checkpoint["task_id"],
                "record_type": "TASK_RESUMED",
                "step": step,
            }
        )
        return self._decorate_model_resilience_result(
            self._decorate_tool_route_result(
                self._decorate_skill_result(
                    self._execute(
                        task_id=checkpoint["task_id"],
                        user_message=checkpoint["user_message"],
                        started_at=checkpoint["started_at"],
                        tool_results=list(
                            checkpoint.get("tool_results") or []
                        ),
                        model_history=list(
                            checkpoint.get("model_history") or []
                        ),
                        start_step=step + 1,
                        active_skill=active_skill,
                    ),
                    active_skill,
                ),
                tool_route,
            ),
            self._task_model_resilience.get(
                task_id, model_resilience
            ),
        )

    def cancel(self, task_id):
        with self._task_lock(task_id):
            if self.checkpoint_store is None:
                raise AgentResumeError(
                    "checkpoint store is required for cancellation"
                )
            checkpoint = self.checkpoint_store.load(task_id)
            model_resilience = self._restore_model_resilience(
                checkpoint
            )
            active_skill = self._resolve_checkpoint_skill(
                checkpoint
            )
            tool_route = self._restore_tool_route(checkpoint)
            if tool_route is not None:
                self._task_routes[task_id] = dict(tool_route)
            if checkpoint.get("status") != "AWAITING_CONFIRMATION":
                raise AgentResumeError(
                    "task has no pending confirmation"
                )
            pending = checkpoint.get("pending_confirmation")
            if not isinstance(pending, dict):
                raise AgentResumeError(
                    "pending confirmation is unavailable"
                )
            completed_at = beijing_timestamp()
            tool_name = str(
                pending.get("tool_name") or "unknown"
            )
            answer = (
                "操作已取消，未执行 {0}。".format(tool_name)
            )
            result = {
                "schema_version": "1.0",
                "task_id": checkpoint["task_id"],
                "status": "CANCELLED",
                "model": self.model.name,
                "started_at": checkpoint["started_at"],
                "completed_at": completed_at,
                "steps": int(checkpoint.get("step", 0)),
                "answer": answer,
                "tool_results": list(
                    checkpoint.get("tool_results") or []
                ),
            }
            result = self._decorate_skill_result(
                result,
                active_skill,
            )
            result = self._decorate_tool_route_result(
                result, tool_route
            )
            result = self._decorate_model_resilience_result(
                result, model_resilience
            )
            self._trace(
                {
                    "schema_version": "1.0",
                    "timestamp": completed_at,
                    "task_id": checkpoint["task_id"],
                    "record_type": "CONFIRMATION_CANCELLED",
                    "step": int(checkpoint.get("step", 0)),
                    "tool_name": tool_name,
                    "risk": pending.get("risk"),
                }
            )
            self._trace_task_result(result)
            self._checkpoint(
                task_id=checkpoint["task_id"],
                status="CANCELLED",
                user_message=checkpoint["user_message"],
                started_at=checkpoint["started_at"],
                step=int(checkpoint.get("step", 0)),
                tool_results=result["tool_results"],
                model_history=list(
                    checkpoint.get("model_history") or []
                ),
                answer=answer,
                completed_at=completed_at,
                active_skill=active_skill,
            )
            return result

    def _task_lock(self, task_id):
        task_id = str(task_id or "")
        with self._task_locks_guard:
            lock = self._task_locks.get(task_id)
            if lock is None:
                lock = threading.Lock()
                self._task_locks[task_id] = lock
        return lock

    @staticmethod
    def _conversation_prefix(records):
        records = list(records or [])
        if len(records) > 24:
            raise ValueError(
                "prior conversation exceeds record limit"
            )
        result = []
        for record in records:
            if not isinstance(record, dict):
                raise ValueError(
                    "prior conversation record is invalid"
                )
            role = record.get("role")
            if role == "user":
                context = record.get("context")
                if not isinstance(context, dict):
                    raise ValueError(
                        "prior user context is invalid"
                    )
                result.append(
                    {
                        "role": "user",
                        "context": copy.deepcopy(context),
                    }
                )
            elif role == "assistant":
                content = record.get("content")
                if (
                    not isinstance(content, str)
                    or len(content) > 4000
                ):
                    raise ValueError(
                        "prior assistant content is invalid"
                    )
                result.append(
                    {
                        "role": "assistant",
                        "content": content,
                    }
                )
            else:
                raise ValueError(
                    "prior conversation role is invalid"
                )
        return result

    def _execute(
        self,
        task_id,
        user_message,
        started_at,
        tool_results,
        model_history,
        start_step,
        pause_after_step=None,
        active_skill=None,
        execution_control=None,
    ):
        effective_max_steps = min(
            self.max_steps,
            (
                active_skill.max_steps
                if active_skill is not None
                else self.max_steps
            ),
        )
        for step_number in range(
            int(start_step),
            effective_max_steps + 1,
        ):
            if execution_control is not None:
                try:
                    execution_control.consume_model_call(
                        "before_model"
                    )
                except AgentExecutionStopped as error:
                    return self._stop_execution(
                        task_id,
                        user_message,
                        started_at,
                        step_number,
                        tool_results,
                        model_history,
                        active_skill,
                        error,
                    )
            catalog_schemas = self.tool_registry.schemas()
            tool_route = self._task_routes.get(task_id)
            tool_schemas = catalog_schemas
            if self.tool_router is not None and tool_route is not None:
                tool_schemas = self.tool_router.select_schemas(
                    tool_route, catalog_schemas
                )
            if active_skill is not None:
                required_tools = set(active_skill.required_tools)
                tool_schemas = [
                    schema
                    for schema in tool_schemas
                    if schema.get("name") in required_tools
                ]
            context = self.context_engine.build(
                user_message,
                tool_schemas,
                recent_tool_results=tool_results,
                active_skill=(
                    active_skill.to_context()
                    if active_skill is not None
                    else None
                ),
                available_skills=(
                    self.skill_registry.list_public()
                    if self.skill_registry is not None
                    else []
                ),
            )
            try:
                self._dispatch_hook(
                    "before_model",
                    task_id,
                    step_number,
                    context=context,
                    visible_tool_names=[
                        schema.get("name")
                        for schema in tool_schemas
                    ],
                )
            except HookDispatchError as error:
                return self._fail_hook(
                    task_id=task_id,
                    user_message=user_message,
                    started_at=started_at,
                    step=step_number,
                    tool_results=tool_results,
                    model_history=model_history,
                    active_skill=active_skill,
                    hook_error=error,
                )
            if (
                int(start_step) == 1
                and not any(
                    record.get("role") == "user"
                    and record.get("task_id") == task_id
                    for record in model_history
                )
            ):
                model_history.append(
                    {
                        "role": "user",
                        "context": context,
                        "task_id": task_id,
                    }
                )
            try:
                forced_tool = self._forced_read_only_tool(
                    task_id,
                    step_number,
                    tool_results,
                    tool_schemas,
                )
                if (
                    forced_tool is not None
                    and hasattr(self.model, "generate_with_tool_choice")
                ):
                    response = self.model.generate_with_tool_choice(
                        context,
                        tool_schemas=tool_schemas,
                        conversation=model_history,
                        tool_choice={
                            "type": "function",
                            "function": {"name": forced_tool},
                        },
                    )
                else:
                    response = self.model.generate(
                        context,
                        tool_schemas=tool_schemas,
                        conversation=model_history,
                    )
                self._record_model_resilience(
                    task_id,
                    step_number,
                    getattr(response, "runtime", None),
                )
                if execution_control is not None:
                    try:
                        execution_control.record_model_usage(
                            getattr(response, "usage", None),
                            "after_model",
                        )
                    finally:
                        self._trace_model_usage(
                            task_id,
                            step_number,
                            getattr(response, "usage", None),
                            execution_control.snapshot(),
                        )
                    execution_control.check("after_model")
            except AgentExecutionStopped as error:
                return self._stop_execution(
                    task_id,
                    user_message,
                    started_at,
                    step_number,
                    tool_results,
                    model_history,
                    active_skill,
                    error,
                )
            except ModelGatewayError as error:
                completed_at = beijing_timestamp()
                result = {
                    "schema_version": "1.0",
                    "task_id": task_id,
                    "status": "FAILED",
                    "model": self.model.name,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "steps": step_number,
                    "answer": "",
                    "error": {
                        "code": "MODEL_REQUEST_FAILED",
                        "message": str(error),
                    },
                    "tool_results": tool_results,
                }
                self._trace_task_result(result)
                self._checkpoint(
                    task_id=task_id,
                    status="FAILED",
                    user_message=user_message,
                    started_at=started_at,
                    step=step_number,
                    tool_results=tool_results,
                    model_history=model_history,
                    completed_at=completed_at,
                    error=result["error"],
                    active_skill=active_skill,
                )
                return result
            self._trace(
                {
                    "schema_version": "1.0",
                    "timestamp": beijing_timestamp(),
                    "task_id": task_id,
                    "record_type": "MODEL_DECISION",
                    "step": step_number,
                    "model": self.model.name,
                    "content": response.content,
                    "tool_calls": [
                        tool_call.to_dict()
                        for tool_call in response.tool_calls
                    ],
                }
            )
            visible_tool_names = set(
                schema.get("name") for schema in tool_schemas
            )
            catalog_tool_names = set(
                schema.get("name") for schema in catalog_schemas
            )
            if active_skill is not None:
                required_tools = set(active_skill.required_tools)
                denied_tool = next(
                    (
                        tool_call.name
                        for tool_call in response.tool_calls
                        if tool_call.name not in required_tools
                    ),
                    None,
                )
                if denied_tool is not None:
                    return self._fail_skill_tool_violation(
                        task_id=task_id,
                        user_message=user_message,
                        started_at=started_at,
                        step=step_number,
                        tool_results=tool_results,
                        model_history=model_history,
                        active_skill=active_skill,
                        denied_tool=denied_tool,
                    )
            route_denied_tool = next(
                (
                    tool_call.name
                    for tool_call in response.tool_calls
                    if (
                        tool_call.name in catalog_tool_names
                        and tool_call.name not in visible_tool_names
                    )
                ),
                None,
            )
            if route_denied_tool is not None:
                return self._fail_tool_route_violation(
                    task_id=task_id,
                    user_message=user_message,
                    started_at=started_at,
                    step=step_number,
                    tool_results=tool_results,
                    model_history=model_history,
                    active_skill=active_skill,
                    denied_tool=route_denied_tool,
                )
            try:
                self._dispatch_hook(
                    "after_model",
                    task_id,
                    step_number,
                    tool_calls=[
                        tool_call.to_dict()
                        for tool_call in response.tool_calls
                    ],
                )
            except HookDispatchError as error:
                return self._fail_hook(
                    task_id=task_id,
                    user_message=user_message,
                    started_at=started_at,
                    step=step_number,
                    tool_results=tool_results,
                    model_history=model_history,
                    active_skill=active_skill,
                    hook_error=error,
                )

            if not response.tool_calls:
                completed_at = beijing_timestamp()
                result = {
                    "schema_version": "1.0",
                    "task_id": task_id,
                    "status": "COMPLETED",
                    "model": self.model.name,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "steps": step_number,
                    "answer": response.content,
                    "tool_results": tool_results,
                }
                self._trace_task_result(result)
                self._checkpoint(
                    task_id=task_id,
                    status="COMPLETED",
                    user_message=user_message,
                    started_at=started_at,
                    step=step_number,
                    tool_results=tool_results,
                    model_history=model_history,
                    answer=response.content,
                    completed_at=completed_at,
                    active_skill=active_skill,
                )
                return result

            assistant_tool_calls = []
            for index, tool_call in enumerate(
                response.tool_calls
            ):
                provider_call_id = tool_call.call_id or (
                    "tool_{0}_{1}_{2}".format(
                        task_id[5:13],
                        step_number,
                        index,
                    )
                )
                assistant_tool_calls.append(
                    {
                        "call_id": provider_call_id,
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    }
                )
            model_history.append(
                {
                    "role": "assistant",
                    "content": response.content,
                    "tool_calls": assistant_tool_calls,
                }
            )

            schemas_by_name = {
                schema.get("name"): schema
                for schema in tool_schemas
            }
            confirmation_calls = []
            for tool_call, assistant_tool_call in zip(
                response.tool_calls,
                assistant_tool_calls,
            ):
                annotations = (
                    schemas_by_name.get(tool_call.name, {}).get(
                        "annotations"
                    )
                    or {}
                )
                if annotations.get("requiresConfirmation"):
                    confirmation_calls.append(
                        (
                            tool_call,
                            assistant_tool_call,
                            annotations,
                        )
                    )
            if confirmation_calls:
                if (
                    len(confirmation_calls) != 1
                    or len(response.tool_calls) != 1
                ):
                    return self._fail_ambiguous_confirmation(
                        task_id=task_id,
                        user_message=user_message,
                        started_at=started_at,
                        step=step_number,
                        tool_results=tool_results,
                        model_history=model_history,
                        active_skill=active_skill,
                    )
                tool_call, assistant_tool_call, annotations = (
                    confirmation_calls[0]
                )
                try:
                    self._dispatch_hook(
                        "before_tool",
                        task_id,
                        step_number,
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                        visible_tool_names=list(schemas_by_name),
                        confirmation_granted=False,
                    )
                except HookDispatchError as error:
                    return self._fail_hook(
                        task_id=task_id,
                        user_message=user_message,
                        started_at=started_at,
                        step=step_number,
                        tool_results=tool_results,
                        model_history=model_history,
                        active_skill=active_skill,
                        hook_error=error,
                    )
                pending = {
                    "tool_name": tool_call.name,
                    "arguments": dict(tool_call.arguments),
                    "provider_call_id": assistant_tool_call[
                        "call_id"
                    ],
                    "risk": annotations.get("riskLevel"),
                    "step": step_number,
                }
                self._checkpoint(
                    task_id=task_id,
                    status="AWAITING_CONFIRMATION",
                    user_message=user_message,
                    started_at=started_at,
                    step=step_number,
                    tool_results=tool_results,
                    model_history=model_history,
                    pending_confirmation=pending,
                    active_skill=active_skill,
                )
                self._trace(
                    {
                        "schema_version": "1.0",
                        "timestamp": beijing_timestamp(),
                        "task_id": task_id,
                        "record_type": "CONFIRMATION_REQUIRED",
                        "step": step_number,
                        "tool_name": tool_call.name,
                        "risk": annotations.get("riskLevel"),
                    }
                )
                return {
                    "schema_version": "1.0",
                    "task_id": task_id,
                    "status": "AWAITING_CONFIRMATION",
                    "model": self.model.name,
                    "started_at": started_at,
                    "completed_at": None,
                    "steps": step_number,
                    "answer": "",
                    "tool_results": tool_results,
                    "pending_confirmation": pending,
                }

            for tool_call, assistant_tool_call in zip(
                response.tool_calls,
                assistant_tool_calls,
            ):
                if execution_control is not None:
                    annotations = (
                        schemas_by_name.get(tool_call.name, {}).get(
                            "annotations"
                        )
                        or {}
                    )
                    try:
                        execution_control.consume_tool_call(
                            "before_tool",
                            external_request=bool(
                                annotations.get("openWorldHint")
                            ),
                        )
                    except AgentExecutionStopped as error:
                        return self._stop_execution(
                            task_id,
                            user_message,
                            started_at,
                            step_number,
                            tool_results,
                            model_history,
                            active_skill,
                            error,
                        )
                try:
                    self._dispatch_hook(
                        "before_tool",
                        task_id,
                        step_number,
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                        visible_tool_names=list(schemas_by_name),
                        confirmation_granted=False,
                    )
                except HookDispatchError as error:
                    return self._fail_hook(
                        task_id=task_id,
                        user_message=user_message,
                        started_at=started_at,
                        step=step_number,
                        tool_results=tool_results,
                        model_history=model_history,
                        active_skill=active_skill,
                        hook_error=error,
                    )
                try:
                    tool_result = self.tool_registry.invoke(
                        tool_call.name,
                        tool_call.arguments,
                    )
                except ToolInvocationError as error:
                    tool_result = error.to_dict()
                tool_results.append(tool_result)
                model_history.append(
                    {
                        "role": "tool",
                        "tool_call_id": assistant_tool_call[
                            "call_id"
                        ],
                        "name": tool_call.name,
                        "content": (
                            self.context_engine
                            .bounded_tool_result(tool_result)
                        ),
                    }
                )
                self._trace(
                    {
                        "schema_version": "1.0",
                        "timestamp": beijing_timestamp(),
                        "task_id": task_id,
                        "record_type": "TOOL_RESULT",
                        "step": step_number,
                        "tool_name": tool_call.name,
                        "call_id": tool_result.get("call_id"),
                        "status": tool_result.get("status"),
                        "latency_ms": tool_result.get("latency_ms"),
                        "error_code": (
                            tool_result.get("error") or {}
                        ).get("code"),
                    }
                )
                try:
                    self._dispatch_hook(
                        "after_tool",
                        task_id,
                        step_number,
                        tool_name=tool_call.name,
                        call_id=tool_result.get("call_id"),
                        status=tool_result.get("status"),
                        error_code=(
                            tool_result.get("error") or {}
                        ).get("code"),
                    )
                except HookDispatchError as error:
                    return self._fail_hook(
                        task_id=task_id,
                        user_message=user_message,
                        started_at=started_at,
                        step=step_number,
                        tool_results=tool_results,
                        model_history=model_history,
                        active_skill=active_skill,
                        hook_error=error,
                    )
                if execution_control is not None:
                    try:
                        execution_control.check("after_tool")
                    except AgentExecutionStopped as error:
                        return self._stop_execution(
                            task_id,
                            user_message,
                            started_at,
                            step_number,
                            tool_results,
                            model_history,
                            active_skill,
                            error,
                        )
            self._checkpoint(
                task_id=task_id,
                status="RUNNING",
                user_message=user_message,
                started_at=started_at,
                step=step_number,
                tool_results=tool_results,
                model_history=model_history,
                active_skill=active_skill,
            )
            if step_number == pause_after_step:
                paused = {
                    "schema_version": "1.0",
                    "task_id": task_id,
                    "status": "PAUSED",
                    "model": self.model.name,
                    "started_at": started_at,
                    "completed_at": None,
                    "steps": step_number,
                    "answer": "",
                    "tool_results": tool_results,
                }
                self._trace(
                    {
                        "schema_version": "1.0",
                        "timestamp": beijing_timestamp(),
                        "task_id": task_id,
                        "record_type": "TASK_PAUSED",
                        "step": step_number,
                    }
                )
                return paused

        completed_at = beijing_timestamp()
        result = {
            "schema_version": "1.0",
            "task_id": task_id,
            "status": "FAILED",
            "model": self.model.name,
            "started_at": started_at,
            "completed_at": completed_at,
            "steps": effective_max_steps,
            "answer": "",
            "error": {
                "code": "MAX_STEPS_EXCEEDED",
                "message": "agent loop reached its step limit",
            },
            "tool_results": tool_results,
        }
        self._trace_task_result(result)
        self._checkpoint(
            task_id=task_id,
            status="FAILED",
            user_message=user_message,
            started_at=started_at,
            step=effective_max_steps,
            tool_results=tool_results,
            model_history=model_history,
            completed_at=completed_at,
            error=result["error"],
            active_skill=active_skill,
        )
        return result

    def _resume_confirmed_tool(
        self,
        checkpoint,
        active_skill=None,
    ):
        pending = checkpoint.get("pending_confirmation")
        if not isinstance(pending, dict):
            raise AgentResumeError(
                "pending confirmation is unavailable"
            )
        tool_name = str(pending.get("tool_name") or "")
        arguments = pending.get("arguments")
        provider_call_id = str(
            pending.get("provider_call_id") or ""
        )
        step = int(pending.get("step", 0))
        if (
            not tool_name
            or not isinstance(arguments, dict)
            or not provider_call_id
            or step <= 0
        ):
            raise AgentResumeError(
                "pending confirmation is invalid"
            )
        if (
            active_skill is not None
            and tool_name not in active_skill.required_tools
        ):
            raise AgentResumeError(
                "pending tool is not allowed by pinned skill"
            )
        tool_route = self._task_routes.get(checkpoint["task_id"])
        if tool_route is not None:
            catalog_names = set(
                schema.get("name")
                for schema in self.tool_registry.schemas()
            )
            if (
                tool_name in catalog_names
                and tool_name not in tool_route["selected_tools"]
            ):
                raise AgentResumeError(
                    "pending tool is not allowed by pinned route"
                )
        tool_results = list(
            checkpoint.get("tool_results") or []
        )
        model_history = list(
            checkpoint.get("model_history") or []
        )
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": beijing_timestamp(),
                "task_id": checkpoint["task_id"],
                "record_type": "TASK_RESUMED",
                "step": step,
            }
        )
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": beijing_timestamp(),
                "task_id": checkpoint["task_id"],
                "record_type": "CONFIRMATION_GRANTED",
                "step": step,
                "tool_name": tool_name,
                "risk": pending.get("risk"),
            }
        )
        try:
            self._dispatch_hook(
                "before_tool",
                checkpoint["task_id"],
                step,
                tool_name=tool_name,
                arguments=arguments,
                visible_tool_names=(
                    list(active_skill.required_tools)
                    if active_skill is not None
                    else (
                        list(tool_route["selected_tools"])
                        if tool_route is not None
                        else [
                        schema.get("name")
                        for schema in self.tool_registry.schemas()
                        ]
                    )
                ),
                confirmation_granted=True,
            )
        except HookDispatchError as error:
            return self._fail_hook(
                task_id=checkpoint["task_id"],
                user_message=checkpoint["user_message"],
                started_at=checkpoint["started_at"],
                step=step,
                tool_results=tool_results,
                model_history=model_history,
                active_skill=active_skill,
                hook_error=error,
            )
        try:
            tool_result = self.tool_registry.invoke(
                tool_name,
                arguments,
                confirmation_granted=True,
            )
        except ToolInvocationError as error:
            tool_result = error.to_dict()
        tool_results.append(tool_result)
        model_history.append(
            {
                "role": "tool",
                "tool_call_id": provider_call_id,
                "name": tool_name,
                "content": (
                    self.context_engine
                    .bounded_tool_result(tool_result)
                ),
            }
        )
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": beijing_timestamp(),
                "task_id": checkpoint["task_id"],
                "record_type": "TOOL_RESULT",
                "step": step,
                "tool_name": tool_name,
                "call_id": tool_result.get("call_id"),
                "status": tool_result.get("status"),
                "latency_ms": tool_result.get("latency_ms"),
                "error_code": (
                    tool_result.get("error") or {}
                ).get("code"),
            }
        )
        try:
            self._dispatch_hook(
                "after_tool",
                checkpoint["task_id"],
                step,
                tool_name=tool_name,
                call_id=tool_result.get("call_id"),
                status=tool_result.get("status"),
                error_code=(
                    tool_result.get("error") or {}
                ).get("code"),
            )
        except HookDispatchError as error:
            return self._fail_hook(
                task_id=checkpoint["task_id"],
                user_message=checkpoint["user_message"],
                started_at=checkpoint["started_at"],
                step=step,
                tool_results=tool_results,
                model_history=model_history,
                active_skill=active_skill,
                hook_error=error,
            )
        self._checkpoint(
            task_id=checkpoint["task_id"],
            status="RUNNING",
            user_message=checkpoint["user_message"],
            started_at=checkpoint["started_at"],
            step=step,
            tool_results=tool_results,
            model_history=model_history,
            active_skill=active_skill,
        )
        return self._execute(
            task_id=checkpoint["task_id"],
            user_message=checkpoint["user_message"],
            started_at=checkpoint["started_at"],
            tool_results=tool_results,
            model_history=model_history,
            start_step=step + 1,
            active_skill=active_skill,
        )

    def _fail_ambiguous_confirmation(
        self,
        task_id,
        user_message,
        started_at,
        step,
        tool_results,
        model_history,
        active_skill=None,
    ):
        completed_at = beijing_timestamp()
        error = {
            "code": "AMBIGUOUS_CONFIRMATION_REQUEST",
            "message": (
                "a confirmation step must contain exactly one "
                "tool call"
            ),
        }
        result = {
            "schema_version": "1.0",
            "task_id": task_id,
            "status": "FAILED",
            "model": self.model.name,
            "started_at": started_at,
            "completed_at": completed_at,
            "steps": int(step),
            "answer": "",
            "error": error,
            "tool_results": list(tool_results),
        }
        self._trace_task_result(result)
        self._checkpoint(
            task_id=task_id,
            status="FAILED",
            user_message=user_message,
            started_at=started_at,
            step=step,
            tool_results=tool_results,
            model_history=model_history,
            completed_at=completed_at,
            error=error,
            active_skill=active_skill,
        )
        return result

    def _fail_tool_route_violation(
        self,
        task_id,
        user_message,
        started_at,
        step,
        tool_results,
        model_history,
        active_skill,
        denied_tool,
    ):
        completed_at = beijing_timestamp()
        error = {
            "code": "TOOL_ROUTE_NOT_ALLOWED",
            "message": (
                "the task tool route does not allow tool: {0}".format(
                    denied_tool
                )
            ),
        }
        result = {
            "schema_version": "1.0",
            "task_id": task_id,
            "status": "FAILED",
            "model": self.model.name,
            "started_at": started_at,
            "completed_at": completed_at,
            "steps": int(step),
            "answer": "",
            "error": error,
            "tool_results": list(tool_results),
        }
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": completed_at,
                "task_id": task_id,
                "record_type": "TOOL_ROUTE_DENIED",
                "step": int(step),
                "tool_name": str(denied_tool),
                "error_code": error["code"],
            }
        )
        self._trace_task_result(result)
        self._checkpoint(
            task_id=task_id,
            status="FAILED",
            user_message=user_message,
            started_at=started_at,
            step=step,
            tool_results=tool_results,
            model_history=model_history,
            completed_at=completed_at,
            error=error,
            active_skill=active_skill,
        )
        return result

    def _fail_skill_tool_violation(
        self,
        task_id,
        user_message,
        started_at,
        step,
        tool_results,
        model_history,
        active_skill,
        denied_tool,
    ):
        completed_at = beijing_timestamp()
        error = {
            "code": "SKILL_TOOL_NOT_ALLOWED",
            "message": (
                "the selected skill does not allow tool: {0}".format(
                    denied_tool
                )
            ),
        }
        result = {
            "schema_version": "1.0",
            "task_id": task_id,
            "status": "FAILED",
            "model": self.model.name,
            "started_at": started_at,
            "completed_at": completed_at,
            "steps": int(step),
            "answer": "",
            "error": error,
            "tool_results": list(tool_results),
        }
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": completed_at,
                "task_id": task_id,
                "record_type": "SKILL_POLICY_DENIED",
                "step": int(step),
                "tool_name": str(denied_tool),
                "skill_name": active_skill.name,
                "skill_version": active_skill.version,
                "error_code": error["code"],
            }
        )
        self._trace_task_result(result)
        self._checkpoint(
            task_id=task_id,
            status="FAILED",
            user_message=user_message,
            started_at=started_at,
            step=step,
            tool_results=tool_results,
            model_history=model_history,
            completed_at=completed_at,
            error=error,
            active_skill=active_skill,
        )
        return result

    def _fail_hook(
        self,
        task_id,
        user_message,
        started_at,
        step,
        tool_results,
        model_history,
        active_skill,
        hook_error,
    ):
        completed_at = beijing_timestamp()
        error = {
            "code": str(hook_error.code),
            "message": str(hook_error.message),
        }
        result = {
            "schema_version": "1.0",
            "task_id": task_id,
            "status": "FAILED",
            "model": self.model.name,
            "started_at": started_at,
            "completed_at": completed_at,
            "steps": int(step),
            "answer": "",
            "error": error,
            "tool_results": list(tool_results),
        }
        self._trace_task_result(result)
        self._checkpoint(
            task_id=task_id,
            status="FAILED",
            user_message=user_message,
            started_at=started_at,
            step=step,
            tool_results=tool_results,
            model_history=model_history,
            completed_at=completed_at,
            error=error,
            active_skill=active_skill,
        )
        return result

    @staticmethod
    def _result_from_checkpoint(checkpoint):
        return task_result_from_checkpoint(checkpoint)

    def _resolve_checkpoint_skill(self, checkpoint):
        payload = checkpoint.get("active_skill")
        if payload is None:
            return None
        if self.skill_registry is None:
            raise AgentResumeError(
                "checkpoint skill registry is unavailable"
            )
        try:
            return self.skill_registry.resolve_pinned(payload)
        except SkillValidationError as error:
            raise AgentResumeError(str(error))

    def _stop_execution(
        self,
        task_id,
        user_message,
        started_at,
        step,
        tool_results,
        model_history,
        active_skill,
        stopped,
    ):
        completed_at = beijing_timestamp()
        status = (
            "CANCELLED"
            if stopped.code == "TASK_CANCELLED"
            else "FAILED"
        )
        error = {
            "code": stopped.code,
            "message": "agent execution stopped at a safe point",
            "stage": stopped.stage,
        }
        result = {
            "schema_version": "1.0",
            "task_id": task_id,
            "status": status,
            "model": self.model.name,
            "started_at": started_at,
            "completed_at": completed_at,
            "steps": int(step),
            "answer": "",
            "error": error,
            "tool_results": list(tool_results),
            "execution": dict(stopped.snapshot),
        }
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": completed_at,
                "task_id": task_id,
                "record_type": "EXECUTION_STOPPED",
                "status": status,
                "step": int(step),
                "error_code": stopped.code,
                "stage": stopped.stage,
            }
        )
        self._trace_task_result(result)
        self._checkpoint(
            task_id=task_id,
            status=status,
            user_message=user_message,
            started_at=started_at,
            step=step,
            tool_results=tool_results,
            model_history=model_history,
            completed_at=completed_at,
            error=error,
            active_skill=active_skill,
            execution=stopped.snapshot,
        )
        return result

    def _persist_execution_snapshot(self, task_id, snapshot):
        if self.checkpoint_store is None:
            return
        try:
            checkpoint = self.checkpoint_store.load(task_id)
        except Exception:
            return
        checkpoint["execution"] = dict(snapshot)
        self.checkpoint_store.save(checkpoint)

    def _route_tools(
        self,
        user_message,
        active_skill,
        prior_conversation,
    ):
        if self.tool_router is None:
            return None
        hints = []
        for record in list(prior_conversation or [])[-4:]:
            if not isinstance(record, dict):
                continue
            context = record.get("context")
            if isinstance(context, dict):
                hint = context.get("user_message")
                if hint:
                    hints.append(str(hint))
        return self.tool_router.route(
            user_message,
            self.tool_registry.schemas(),
            required_tools=(
                active_skill.required_tools
                if active_skill is not None
                else None
            ),
            context_hints=hints,
        )

    def _forced_read_only_tool(
        self,
        task_id,
        step_number,
        tool_results,
        tool_schemas,
    ):
        if int(step_number) != 1 or tool_results:
            return None
        route = self._task_routes.get(task_id)
        if (
            not isinstance(route, dict)
            or route.get("mode") != "DETERMINISTIC"
            or route.get("selected_count") != 1
        ):
            return None
        selected = list(route.get("selected_tools") or [])
        if len(selected) != 1 or len(tool_schemas) != 1:
            return None
        schema = tool_schemas[0]
        annotations = schema.get("annotations") or {}
        if (
            schema.get("name") != selected[0]
            or annotations.get("readOnlyHint") is not True
            or annotations.get("autoExecute") is not True
            or annotations.get("requiresConfirmation") is not False
        ):
            return None
        return selected[0]

    def _restore_tool_route(self, checkpoint):
        route = checkpoint.get("tool_route")
        if route is None:
            return None
        if self.tool_router is None:
            raise AgentResumeError(
                "checkpoint tool router is unavailable"
            )
        try:
            return self.tool_router.validate_route(
                route, self.tool_registry.schemas()
            )
        except ToolRouteError as error:
            raise AgentResumeError(str(error))

    def _restore_model_resilience(self, checkpoint):
        payload = checkpoint.get("model_resilience")
        if payload is None:
            return None
        if not isinstance(payload, dict):
            raise AgentResumeError(
                "checkpoint model resilience is invalid"
            )
        required = {
            "schema_version",
            "model_calls",
            "remote_attempts",
            "retry_count",
            "fallback_count",
            "last_requested_mode",
            "last_served_mode",
            "last_fallback_reason",
            "circuit_state",
        }
        if set(payload) != required:
            raise AgentResumeError(
                "checkpoint model resilience is invalid"
            )
        for field in (
            "model_calls",
            "remote_attempts",
            "retry_count",
            "fallback_count",
        ):
            value = payload.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                raise AgentResumeError(
                    "checkpoint model resilience is invalid"
                )
        if payload.get("schema_version") != "1.0":
            raise AgentResumeError(
                "checkpoint model resilience is invalid"
            )
        restored = dict(payload)
        self._task_model_resilience[
            checkpoint["task_id"]
        ] = restored
        return restored

    def _trace_tool_route(self, task_id, route):
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": beijing_timestamp(),
                "task_id": task_id,
                "record_type": "TOOL_ROUTE",
                "step": 0,
                "route_mode": route["mode"],
                "catalog_tools": route["catalog_tools"],
                "selected_count": route["selected_count"],
                "selected_tools": list(route["selected_tools"]),
                "max_tools": route["max_tools"],
                "schema_bytes_before": route[
                    "schema_bytes_before"
                ],
                "schema_bytes_after": route[
                    "schema_bytes_after"
                ],
                "schema_reduction_percent": route[
                    "schema_reduction_percent"
                ],
                "fallback_used": False,
            }
        )

    @staticmethod
    def _decorate_skill_result(result, active_skill):
        if active_skill is None:
            return result
        decorated = dict(result)
        decorated["skill"] = active_skill.to_public()
        return decorated

    @staticmethod
    def _decorate_tool_route_result(result, tool_route):
        if tool_route is None:
            return result
        decorated = dict(result)
        decorated["tool_route"] = dict(tool_route)
        return decorated

    @staticmethod
    def _decorate_model_resilience_result(result, resilience):
        if resilience is None:
            return result
        decorated = dict(result)
        decorated["model_resilience"] = dict(resilience)
        return decorated

    def _record_model_resilience(self, task_id, step, runtime):
        if not isinstance(runtime, dict):
            return
        required = (
            "requested_mode",
            "served_mode",
            "remote_attempts",
            "retry_count",
            "fallback_used",
            "fallback_reason",
            "circuit_state",
        )
        if any(field not in runtime for field in required):
            return
        current = self._task_model_resilience.get(task_id) or {
            "schema_version": "1.0",
            "model_calls": 0,
            "remote_attempts": 0,
            "retry_count": 0,
            "fallback_count": 0,
            "last_requested_mode": None,
            "last_served_mode": None,
            "last_fallback_reason": None,
            "circuit_state": "CLOSED",
        }
        current = dict(current)
        current["model_calls"] += 1
        current["remote_attempts"] += max(
            0, int(runtime.get("remote_attempts") or 0)
        )
        current["retry_count"] += max(
            0, int(runtime.get("retry_count") or 0)
        )
        if runtime.get("fallback_used"):
            current["fallback_count"] += 1
        current["last_requested_mode"] = runtime.get(
            "requested_mode"
        )
        current["last_served_mode"] = runtime.get("served_mode")
        current["last_fallback_reason"] = runtime.get(
            "fallback_reason"
        )
        current["circuit_state"] = runtime.get(
            "circuit_state"
        )
        self._task_model_resilience[task_id] = current
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": beijing_timestamp(),
                "task_id": task_id,
                "record_type": "MODEL_RESILIENCE",
                "step": int(step),
                "requested_mode": runtime.get("requested_mode"),
                "served_mode": runtime.get("served_mode"),
                "remote_attempts": int(
                    runtime.get("remote_attempts") or 0
                ),
                "retry_count": int(
                    runtime.get("retry_count") or 0
                ),
                "fallback_used": bool(
                    runtime.get("fallback_used")
                ),
                "fallback_reason": runtime.get(
                    "fallback_reason"
                ),
                "circuit_state": runtime.get("circuit_state"),
            }
        )

    def _trace_task_result(self, result):
        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": result["completed_at"],
                "task_id": result["task_id"],
                "record_type": "TASK_RESULT",
                "status": result["status"],
                "steps": result["steps"],
                "error_code": (
                    result.get("error") or {}
                ).get("code"),
            }
        )
        self._dispatch_hook(
            "on_task_complete",
            result["task_id"],
            result["steps"],
            status=result["status"],
            error_code=(
                result.get("error") or {}
            ).get("code"),
        )

    def _trace_model_usage(self, task_id, step, usage, snapshot):
        cumulative = dict(snapshot.get("usage") or {})
        cost = dict(snapshot.get("cost_estimate") or {})
        reported = isinstance(usage, dict)

        def safe_usage_value(field):
            if not reported:
                return 0
            value = usage.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or value < 0
            ):
                return 0
            return value

        self._trace(
            {
                "schema_version": "1.0",
                "timestamp": beijing_timestamp(),
                "task_id": task_id,
                "record_type": "MODEL_USAGE",
                "step": int(step),
                "model": self.model.name,
                "usage_reported": reported,
                "prompt_tokens": safe_usage_value(
                    "prompt_tokens"
                ),
                "completion_tokens": safe_usage_value(
                    "completion_tokens"
                ),
                "total_tokens": safe_usage_value("total_tokens"),
                "cumulative_total_tokens": int(
                    cumulative.get("total_tokens") or 0
                ),
                "cost_estimate_available": bool(
                    cost.get("available")
                ),
                "estimated_cost_usd": cost.get(
                    "estimated_cost_usd"
                ),
                "rate_card_id": cost.get("rate_card_id"),
            }
        )

    def _trace(self, record):
        if self.trace_recorder is not None:
            safe_record = dict(record)
            if safe_record.get("record_type") == "MODEL_DECISION":
                safe_calls = []
                for call in safe_record.get("tool_calls") or []:
                    safe_call = dict(call)
                    name = safe_call.get("name")
                    arguments = safe_call.get("arguments") or {}
                    if name == "memory.remember":
                        safe_call["arguments"] = {
                            "kind": arguments.get("kind"),
                            "key_present": bool(arguments.get("key")),
                            "value_length": len(
                                str(arguments.get("value") or "")
                            ),
                            "content_exposed": False,
                        }
                    elif name == "memory.search":
                        safe_call["arguments"] = {
                            "query_present": bool(
                                arguments.get("query")
                            ),
                            "kind": arguments.get("kind"),
                            "limit": arguments.get("limit"),
                            "content_exposed": False,
                        }
                    safe_calls.append(safe_call)
                safe_record["tool_calls"] = safe_calls
            self.trace_recorder.append(safe_record)

    def _dispatch_hook(self, point, task_id, step, **payload):
        if self.hook_dispatcher is None:
            return None
        hook_payload = {
            "task_id": str(task_id),
            "step": int(step),
        }
        hook_payload.update(payload)
        return self.hook_dispatcher.dispatch(
            point,
            hook_payload,
        )

    def _checkpoint(
        self,
        task_id,
        status,
        user_message,
        started_at,
        step,
        tool_results,
        model_history,
        answer="",
        completed_at=None,
        error=None,
        pending_confirmation=None,
        active_skill=None,
        execution=None,
    ):
        if self.checkpoint_store is None:
            return
        checkpoint = {
            "schema_version": "1.0",
            "task_id": task_id,
            "status": status,
            "model": self.model.name,
            "model_identity": self.model_identity,
            "user_message": str(user_message),
            "started_at": started_at,
            "updated_at": beijing_timestamp(),
            "completed_at": completed_at,
            "step": int(step),
            "max_steps": self.max_steps,
            "answer": str(answer),
            "tool_results": list(tool_results),
            "model_history": list(model_history),
            "error": error,
            "pending_confirmation": pending_confirmation,
            "active_skill": (
                active_skill.to_public()
                if active_skill is not None
                else None
            ),
        }
        if execution is not None:
            checkpoint["execution"] = dict(execution)
        tool_route = self._task_routes.get(task_id)
        if tool_route is not None:
            checkpoint["tool_route"] = dict(tool_route)
        model_resilience = self._task_model_resilience.get(task_id)
        if model_resilience is not None:
            checkpoint["model_resilience"] = dict(
                model_resilience
            )
        self.checkpoint_store.save(checkpoint)
        self._dispatch_hook(
            "on_checkpoint",
            task_id,
            step,
            status=status,
        )
