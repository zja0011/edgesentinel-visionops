"""Local HTTP API for EdgeSentinel vision state and administration."""

import argparse
import json
import os
import sys
from typing import Any, Dict, Optional
from urllib.parse import urlsplit


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
VENDOR_PYTHON = os.path.join(PROJECT_DIR, "vendor", "python")
if os.path.isdir(VENDOR_PYTHON) and VENDOR_PYTHON not in sys.path:
    sys.path.insert(0, VENDOR_PYTHON)

from fastapi import (
    FastAPI,
    Header,
    HTTPException,
    Query,
    Request,
    Response,
)
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    RedirectResponse,
    StreamingResponse,
)

from packages.api.auth_service import (
    AUTH_COOKIE_NAME,
    AuthenticationError,
    AuthConfigurationError,
    AuthService,
)

from packages.api.evidence_service import (
    EvidenceNotFound,
    EvidenceService,
)
from packages.api.event_service import (
    EventDatabaseUnavailable,
    EventQueryService,
)
from packages.events.summary import EventSummaryService
from packages.api.vision_service import (
    LiveFrameService,
    VisionApiUnavailable,
    VisionQueryService,
)
from packages.api.zone_service import (
    ZoneAuthenticationFailed,
    ZoneConfigUnavailable,
    ZoneQueryService,
    ZoneSaveDisabled,
    ZoneValidationFailed,
    ZoneVersionConflict,
)
from packages.api.agent_service import (
    AgentRequestInvalid,
    add_agent_runtime_health,
    validate_agent_cancellation,
    validate_agent_confirmation,
    validate_model_mode_request,
    validate_agent_task_request,
    validate_session_clear,
)
from packages.api.agent_snapshot_service import (
    AgentSnapshotIntegrityError,
    AgentSnapshotNotFound,
    AgentSnapshotService,
)
from packages.api.agent_report_service import (
    AgentReportIntegrityError,
    AgentReportNotFound,
    AgentReportService,
)
from packages.api.camera_service import (
    CameraStatusService,
    CameraStatusUnavailable,
)
from packages.harness.agent_loop import AgentLoop, AgentResumeError
from packages.harness.checkpoint import (
    CheckpointNotFound,
    JsonTaskCheckpointStore,
    task_result_from_checkpoint,
)
from packages.harness.context import ContextEngine
from packages.harness.default_tools import build_default_registry
from packages.harness.evaluation import (
    EvaluationReportStore,
    EvaluationReportUnavailable,
)
from packages.harness.execution_control import (
    ExecutionControl,
    ExecutionLimits,
    ModelCostPolicy,
)
from packages.harness.inventory_tools import InventoryHistoryTools
from packages.harness.long_term_memory import (
    LongTermMemoryStore,
    LongTermMemoryUnavailable,
)
from packages.harness.hooks import (
    HOOK_POINTS,
    build_default_hook_dispatcher,
)
from packages.harness.model_runtime import (
    ModelModeUnavailable,
    SwitchableModel,
    build_model_from_environment,
    model_runtime_summary,
)
from packages.harness.model_tools import VisionModelTools
from packages.harness.registry import ToolInvocationError
from packages.harness.skills import (
    SkillRegistry,
    SkillValidationError,
)
from packages.harness.session_memory import (
    SessionMemoryStore,
    SessionMemoryUnavailable,
    strip_session_conversation_prefix,
)
from packages.harness.retention_tools import (
    RetentionCleanupHistoryTools,
)
from packages.harness.trace import JsonlTraceRecorder
from packages.harness.trace_query import (
    AgentTaskTraceQuery,
    AgentTraceUnavailable,
)
from packages.harness.tool_router import ToolSchemaRouter
from packages.harness.task_queue import (
    AgentJobCancellationConflict,
    AgentJobIdempotencyConflict,
    AgentJobQueueFull,
    AgentJobUnavailable,
    PersistentAgentJobQueue,
    TERMINAL_STATUSES,
)
from packages.evidence.integrity import (
    EvidenceIntegrityService,
    EvidenceIntegrityUnavailable,
)
from packages.vision.schemas import beijing_timestamp
from packages.monitoring.device import DeviceMonitor
from packages.monitoring.benchmark_store import (
    RuntimeBenchmarkStore,
    RuntimeBenchmarkUnavailable,
)
from packages.monitoring.storage import ProjectStorageInventory
from packages.monitoring.retention import DataRetentionPreview
from packages.vision.model_manifest import ModelManifestUnavailable


DEFAULT_DATABASE = os.path.join(
    PROJECT_DIR,
    "data",
    "events",
    "edgesentinel.db",
)


def create_app(
    database_path=None,
    project_dir=None,
    model=None,
    environ=None,
):
    runtime_environ = os.environ if environ is None else environ
    runtime_project_dir = os.path.abspath(project_dir or PROJECT_DIR)
    runtime_database = database_path or os.path.join(
        runtime_project_dir,
        "data",
        "events",
        "edgesentinel.db",
    )
    service = EventQueryService(runtime_database)
    event_summary_service = EventSummaryService(runtime_database)
    storage_inventory = ProjectStorageInventory(
        runtime_project_dir
    )
    retention_preview = DataRetentionPreview(
        runtime_project_dir
    )
    retention_cleanup_history = RetentionCleanupHistoryTools(
        runtime_project_dir
    )
    evidence_service = EvidenceService(runtime_project_dir)
    evidence_integrity_service = EvidenceIntegrityService(
        runtime_project_dir,
        runtime_database,
    )
    inventory_history_service = InventoryHistoryTools(
        runtime_project_dir,
        runtime_database,
    )
    agent_snapshot_service = AgentSnapshotService(
        runtime_project_dir
    )
    agent_report_service = AgentReportService(
        runtime_project_dir
    )
    evaluation_report_store = EvaluationReportStore(
        os.path.join(
            runtime_project_dir,
            "data",
            "evaluations",
        )
    )

    def decorate_agent_task(task, session_id=None):
        if "steps" not in task and "step" in task:
            task = task_result_from_checkpoint(task)
        else:
            task = dict(task)
        result = agent_report_service.add_url(
            agent_snapshot_service.add_url(task)
        )
        if session_id:
            result["session_id"] = session_id
            try:
                result["memory"] = session_memory_store.get(
                    session_id,
                    include_turns=False,
                )
            except SessionMemoryUnavailable:
                pass
        return result

    def strip_checkpoint_session_prefix(
        task_id,
        expected_record_count=None,
    ):
        checkpoint = checkpoint_store.load(task_id)
        checkpoint_store.save(
            strip_session_conversation_prefix(
                checkpoint,
                task_id,
                expected_record_count=expected_record_count,
            )
        )
    long_term_memory_store = LongTermMemoryStore(
        os.path.join(
            runtime_project_dir,
            "data",
            "harness",
            "long-term-memory",
        ),
        max_records=100,
    )
    tool_registry = build_default_registry(
        runtime_project_dir,
        runtime_database,
        weather_default_location=runtime_environ.get(
            "EDGESENTINEL_WEATHER_DEFAULT_LOCATION"
        ),
        long_term_memory_store=long_term_memory_store,
    )
    try:
        skill_registry = SkillRegistry.load(
            os.path.join(runtime_project_dir, "skills")
        )
        skill_registry.validate_tools(tool_registry.schemas())
    except SkillValidationError as error:
        raise RuntimeError(
            "Agent Skill registry is invalid: {0}".format(error)
        )
    tool_annotations = {
        schema["name"]: dict(schema.get("annotations") or {})
        for schema in tool_registry.schemas()
    }

    def decorate_agent_trace(payload):
        result = dict(payload)
        records = []
        for source_record in payload.get("records") or []:
            record = dict(source_record)
            tool_name = record.get("tool_name")
            if tool_name in tool_annotations:
                record["tool_policy"] = dict(
                    tool_annotations[tool_name]
                )
            calls = []
            for source_call in record.get("tool_calls") or []:
                call = dict(source_call)
                name = call.get("name")
                if name in tool_annotations:
                    call["policy"] = dict(tool_annotations[name])
                calls.append(call)
            if "tool_calls" in record:
                record["tool_calls"] = calls
            records.append(record)
        result["records"] = records
        return result
    state_path = os.path.join(
        runtime_project_dir,
        "data",
        "state",
        "current-vision.json",
    )
    vision_service = VisionQueryService(state_path)
    live_frame_service = LiveFrameService(
        os.path.join(
            runtime_project_dir,
            "data",
            "state",
            "current-frame.jpg",
        )
    )
    device_monitor = DeviceMonitor(runtime_project_dir)
    benchmark_store = RuntimeBenchmarkStore(runtime_project_dir)
    camera_status_service = CameraStatusService(
        os.path.join(
            runtime_project_dir,
            "data",
            "runtime",
            "vision-supervisor.json",
        )
    )
    model_info_service = VisionModelTools(
        os.path.join(
            runtime_project_dir,
            "data",
            "state",
            "current-model.json",
        ),
        runtime_environ.get(
            "EDGESENTINEL_MODEL_ROOT",
            "/jetson-inference/data/networks",
        ),
    )
    zone_service = ZoneQueryService(
        os.path.join(
            runtime_project_dir,
            "configs",
            "zones.json",
        ),
        admin_token=runtime_environ.get(
            "EDGESENTINEL_CONFIG_TOKEN"
        ),
        default_config_path=os.path.join(
            runtime_project_dir,
            "configs",
            "zones.default.json",
        ),
    )
    dashboard_dir = os.path.join(
        runtime_project_dir,
        "apps",
        "dashboard",
    )
    dashboard_assets = {
        "dashboard.css": os.path.join(
            dashboard_dir,
            "dashboard.css",
        ),
        "dashboard.js": os.path.join(
            dashboard_dir,
            "dashboard.js",
        ),
    }
    context_engine = ContextEngine(
        database_path=runtime_database,
        state_path=state_path,
        include_tool_descriptions=False,
    )
    checkpoint_store = JsonTaskCheckpointStore(
        os.path.join(
            runtime_project_dir,
            "data",
            "harness",
            "checkpoints",
        )
    )
    session_memory_store = SessionMemoryStore(
        os.path.join(
            runtime_project_dir,
            "data",
            "harness",
            "sessions",
        ),
        max_sessions=500,
        max_turns=12,
        retention_days=7,
    )
    configured_model = model or build_model_from_environment(
        environ=runtime_environ
    )
    runtime_model = (
        configured_model
        if model is not None
        else SwitchableModel(
            configured_model,
            environ=runtime_environ,
        )
    )
    agent_trace_path = os.path.join(
        runtime_project_dir,
        "data",
        "harness",
        "api-agent-trace.jsonl",
    )
    agent_trace_recorder = JsonlTraceRecorder(agent_trace_path)

    def trace_session_memory(
        task,
        prior_turn_count,
        memory,
        action,
    ):
        if not isinstance(memory, dict):
            return
        agent_trace_recorder.append(
            {
                "schema_version": "1.0",
                "timestamp": beijing_timestamp(),
                "task_id": task.get("task_id"),
                "record_type": "SESSION_MEMORY",
                "step": int(task.get("steps") or 0),
                "status": task.get("status"),
                "memory_action": action,
                "prior_turn_count": int(
                    prior_turn_count or 0
                ),
                "turn_count": int(
                    memory.get("turn_count") or 0
                ),
                "max_turns": int(
                    memory.get("max_turns") or 0
                ),
                "retention_days": int(
                    memory.get("retention_days") or 0
                ),
            }
        )
    hook_dispatcher = build_default_hook_dispatcher(
        audit_recorder=JsonlTraceRecorder(
            os.path.join(
                runtime_project_dir,
                "data",
                "harness",
                "api-agent-hooks.jsonl",
            )
        ),
        trace_recorder=agent_trace_recorder,
    )
    agent_trace_query = AgentTaskTraceQuery(agent_trace_path)
    agent_loop = AgentLoop(
        model=runtime_model,
        context_engine=context_engine,
        tool_registry=tool_registry,
        trace_recorder=agent_trace_recorder,
        checkpoint_store=checkpoint_store,
        skill_registry=skill_registry,
        hook_dispatcher=hook_dispatcher,
        tool_router=ToolSchemaRouter(max_tools=6),
        max_steps=5,
    )

    agent_execution_limits = ExecutionLimits(
        max_wall_seconds=60.0,
        max_model_calls=5,
        max_tool_calls=8,
        max_external_tool_calls=2,
        max_total_tokens=int(
            runtime_environ.get(
                "EDGESENTINEL_AGENT_MAX_TOTAL_TOKENS",
                "16384",
            )
        ),
    )
    cost_environment = {
        "input_usd_per_million": runtime_environ.get(
            "EDGESENTINEL_MODEL_INPUT_USD_PER_MILLION"
        ) or None,
        "output_usd_per_million": runtime_environ.get(
            "EDGESENTINEL_MODEL_OUTPUT_USD_PER_MILLION"
        ) or None,
        "max_estimated_cost_usd": runtime_environ.get(
            "EDGESENTINEL_MODEL_MAX_ESTIMATED_COST_USD"
        ) or None,
        "rate_card_id": runtime_environ.get(
            "EDGESENTINEL_MODEL_RATE_CARD_ID"
        ) or None,
    }
    agent_model_cost_policy = (
        ModelCostPolicy(**cost_environment)
        if any(
            value is not None
            for value in cost_environment.values()
        )
        else ModelCostPolicy()
    )

    def execute_agent_request(request, execution_control=None):
        execution_control = execution_control or ExecutionControl(
            agent_execution_limits,
            cost_policy=agent_model_cost_policy,
        )
        if request["session_id"] is None:
            return decorate_agent_task(
                agent_loop.run(
                    request["message"],
                    execution_control=execution_control,
                )
            )
        session = session_memory_store.get(
            request["session_id"],
            include_turns=False,
        )
        session_id = session["session_id"]
        prior_turn_count = int(session["turn_count"])
        prior_history = session_memory_store.model_history(
            session_id
        )
        result = agent_loop.run(
            request["message"],
            prior_conversation=prior_history,
            execution_control=execution_control,
        )
        memory = session_memory_store.record_task(
            session_id,
            request["message"],
            result,
        )
        trace_session_memory(
            result,
            prior_turn_count,
            memory,
            (
                "PENDING"
                if result.get("status") in (
                    "AWAITING_CONFIRMATION",
                    "PAUSED",
                )
                else "SAVED"
            ),
        )
        if result.get("status") not in (
            "AWAITING_CONFIRMATION",
            "PAUSED",
        ):
            strip_checkpoint_session_prefix(
                result["task_id"],
                len(prior_history),
            )
        return decorate_agent_task(result, session_id)

    agent_job_queue = PersistentAgentJobQueue(
        os.path.join(
            runtime_project_dir,
            "data",
            "harness",
            "jobs",
        ),
        executor=execute_agent_request,
        max_pending=16,
        max_jobs=100,
        retention_hours=24,
        cooperative_cancel=True,
        execution_limits=agent_execution_limits,
        model_cost_policy=agent_model_cost_policy,
    )
    application = FastAPI(
        title="EdgeSentinel VisionOps API",
        description=(
            "Vision APIs plus confirmation-gated local operations."
        ),
        version="1.1.0",
    )
    application.state.agent_model_runtime = runtime_model
    application.state.agent_job_queue = agent_job_queue
    auth_audit_recorder = JsonlTraceRecorder(
        os.path.join(
            runtime_project_dir,
            "data",
            "harness",
            "auth-audit.jsonl",
        )
    )
    try:
        auth_service = AuthService.from_environment(
            runtime_environ,
            audit_recorder=auth_audit_recorder,
        )
    except AuthConfigurationError as error:
        raise RuntimeError(str(error))
    application.state.auth_service = auth_service
    tls_required = str(
        runtime_environ.get("EDGESENTINEL_TLS_ENABLED", "0")
    ).strip().lower() in ("1", "true", "yes", "on")
    tls_public_origin = str(
        runtime_environ.get("EDGESENTINEL_TLS_PUBLIC_ORIGIN", "")
    ).strip().rstrip("/")
    if tls_required:
        parsed_tls_origin = urlsplit(tls_public_origin)
        if (
            parsed_tls_origin.scheme != "https"
            or not parsed_tls_origin.netloc
            or parsed_tls_origin.path not in ("", "/")
            or parsed_tls_origin.query
            or parsed_tls_origin.fragment
            or parsed_tls_origin.username
            or parsed_tls_origin.password
        ):
            raise RuntimeError("TLS public origin is invalid")
        if not auth_service.cookie_secure:
            raise RuntimeError(
                "TLS requires Secure authentication cookies"
            )
    application.state.tls_required = tls_required
    application.state.tls_public_origin = tls_public_origin

    def auth_error_response(error):
        return JSONResponse(
            status_code=error.status_code,
            content={
                "detail": str(error),
                "code": error.code,
            },
            headers={"Cache-Control": "no-store"},
        )

    def request_principal(request):
        if not auth_service.enabled:
            return auth_service.authenticate(None)
        principal = getattr(
            request.state, "auth_principal", None
        )
        if principal is None:
            raise AuthenticationError(
                "AUTH_REQUIRED", "authentication required"
            )
        return principal

    @application.middleware("http")
    async def enforce_authentication(request, call_next):
        path = request.url.path
        client_host = (
            request.client.host
            if request.client is not None
            else ""
        )
        loopback_client = client_host in (
            "127.0.0.1",
            "::1",
            "localhost",
            "testclient",
        )
        forwarded_https = (
            loopback_client
            and request.headers.get(
                "X-Forwarded-Proto", ""
            ).lower() == "https"
        )
        secure_request = (
            request.url.scheme == "https" or forwarded_https
        )
        health_path = path == "/health" or path.startswith(
            "/health/"
        )
        if tls_required and not secure_request and not health_path:
            if (
                request.method.upper() in ("GET", "HEAD")
                and (
                    path == "/dashboard"
                    or path.startswith("/dashboard/assets/")
                )
            ):
                destination = tls_public_origin + path
                if request.url.query:
                    destination += "?" + request.url.query
                return RedirectResponse(destination, status_code=307)
            return JSONResponse(
                status_code=426,
                content={
                    "detail": "HTTPS is required",
                    "code": "TLS_REQUIRED",
                },
                headers={
                    "Cache-Control": "no-store",
                    "Upgrade": "TLS/1.2",
                },
            )
        if not auth_service.enabled:
            return await call_next(request)
        if (
            health_path
            or path == "/dashboard"
            or path.startswith("/dashboard/assets/")
            or path.startswith("/api/v1/auth/")
        ):
            return await call_next(request)
        try:
            principal = auth_service.authenticate(
                request.cookies.get(AUTH_COOKIE_NAME)
            )
            auth_service.require_role(
                principal, "viewer", action=path
            )
            if request.method.upper() not in (
                "GET",
                "HEAD",
                "OPTIONS",
            ):
                auth_service.verify_csrf(
                    principal,
                    request.headers.get("X-EdgeSentinel-CSRF"),
                )
            if (
                (
                    request.method.upper() == "PUT"
                    and path in (
                        "/api/v1/zones",
                        "/api/v1/agent/model-mode",
                    )
                )
                or (
                    request.method.upper() == "POST"
                    and path.startswith(
                        "/api/v1/harness/tools/"
                    )
                )
            ):
                auth_service.require_role(
                    principal, "admin", action=path
                )
            request.state.auth_principal = principal
        except AuthenticationError as error:
            return auth_error_response(error)
        return await call_next(request)

    @application.on_event("shutdown")
    def close_agent_job_queue():
        agent_job_queue.close()

    @application.get("/health", tags=["system"])
    def health(response: Response):
        payload = add_agent_runtime_health(
            service.health(),
            model_runtime_summary(
                application.state.agent_model_runtime
            ),
        )
        payload["authentication"] = auth_service.summary()
        payload["transport_security"] = {
            "schema_version": "1.0",
            "tls_enabled": tls_required,
            "external_https_required": tls_required,
            "public_origin": tls_public_origin or None,
            "secure_cookie": auth_service.cookie_secure,
            "private_key_exposed": False,
        }
        if auth_service.enabled and not auth_service.ready:
            payload["status"] = "degraded"
        if payload["status"] != "ok":
            response.status_code = 503
        return payload

    @application.get(
        "/health/vision",
        tags=["system"],
        include_in_schema=False,
    )
    def vision_health(response: Response):
        try:
            people = vision_service.get_people()
        except VisionApiUnavailable:
            response.status_code = 503
            return {
                "schema_version": "1.0",
                "status": "unavailable",
                "stale": True,
            }
        result = {
            "schema_version": "1.0",
            "status": "available",
            "stale": bool(people.get("stale", True)),
            "frame_id": people.get("frame_id"),
            "age_seconds": people.get("age_seconds"),
            "max_age_seconds": people.get("max_age_seconds"),
            "scene_content_exposed": False,
        }
        if result["stale"]:
            response.status_code = 503
        return result

    @application.get(
        "/api/v1/auth/status",
        tags=["authentication"],
    )
    def get_auth_status():
        return auth_service.summary()

    @application.post(
        "/api/v1/auth/login",
        tags=["authentication"],
    )
    def login(
        payload: Dict[str, Any],
        request: Request,
        response: Response,
    ):
        if set(payload) != {"username", "password"}:
            raise HTTPException(
                status_code=422,
                detail="username and password are required",
            )
        try:
            token, session = auth_service.login(
                payload.get("username"),
                payload.get("password"),
                client_id=(
                    request.client.host
                    if request.client is not None
                    else "unknown"
                ),
            )
        except AuthenticationError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=str(error),
                headers={"X-Auth-Error": error.code},
            )
        response.set_cookie(
            key=AUTH_COOKIE_NAME,
            value=token,
            max_age=auth_service.session_ttl_seconds,
            httponly=True,
            secure=auth_service.cookie_secure,
            samesite="strict",
            path="/",
        )
        response.headers["Cache-Control"] = "no-store"
        return session

    @application.get(
        "/api/v1/auth/session",
        tags=["authentication"],
    )
    def get_auth_session(request: Request):
        if not auth_service.enabled:
            return {
                "schema_version": "1.0",
                "enabled": False,
                "authenticated": True,
                "username": "development",
                "role": "admin",
                "expires_at": None,
                "csrf_token": None,
            }
        try:
            principal = auth_service.authenticate(
                request.cookies.get(AUTH_COOKIE_NAME)
            )
        except AuthenticationError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=str(error),
                headers={"X-Auth-Error": error.code},
            )
        result = AuthService._public_session(principal)
        result["enabled"] = True
        return result

    @application.post(
        "/api/v1/auth/logout",
        tags=["authentication"],
    )
    def logout(request: Request, response: Response):
        try:
            token = request.cookies.get(AUTH_COOKIE_NAME)
            principal = auth_service.authenticate(token)
            auth_service.verify_csrf(
                principal,
                request.headers.get("X-EdgeSentinel-CSRF"),
            )
            auth_service.logout(token, principal)
        except AuthenticationError as error:
            raise HTTPException(
                status_code=error.status_code,
                detail=str(error),
                headers={"X-Auth-Error": error.code},
            )
        response.delete_cookie(
            AUTH_COOKIE_NAME,
            path="/",
            httponly=True,
            secure=auth_service.cookie_secure,
            samesite="strict",
        )
        response.headers["Cache-Control"] = "no-store"
        return {
            "schema_version": "1.0",
            "authenticated": False,
        }

    @application.get(
        "/api/v1/agent/model-mode",
        tags=["agent"],
    )
    def get_agent_model_mode():
        return {
            "schema_version": "1.0",
            **model_runtime_summary(
                application.state.agent_model_runtime
            ),
        }

    @application.put(
        "/api/v1/agent/model-mode",
        tags=["agent"],
    )
    def set_agent_model_mode(payload: Dict[str, Any]):
        try:
            requested_mode = validate_model_mode_request(payload)
        except AgentRequestInvalid as error:
            raise HTTPException(status_code=422, detail=str(error))
        runtime = application.state.agent_model_runtime
        if not isinstance(runtime, SwitchableModel):
            raise HTTPException(
                status_code=409,
                detail="model runtime is not switchable",
            )
        try:
            summary = runtime.set_mode(requested_mode)
        except ModelModeUnavailable as error:
            raise HTTPException(status_code=409, detail=str(error))
        return {
            "schema_version": "1.0",
            **summary,
        }

    @application.get(
        "/api/v1/weather/current",
        tags=["weather"],
    )
    def get_current_weather(
        location: Optional[str] = Query(
            None,
            min_length=2,
            max_length=80,
        ),
    ):
        try:
            response = tool_registry.invoke(
                "weather.get_current",
                {"location": location} if location else {},
            )
        except ToolInvocationError as error:
            raise HTTPException(
                status_code=503,
                detail=(
                    "weather lookup failed; use a concrete city name "
                    "and verify that the Jetson can reach the fixed "
                    "HTTPS weather provider"
                ),
            )
        return response["result"]

    @application.get(
        "/dashboard",
        include_in_schema=False,
    )
    def dashboard():
        return FileResponse(
            os.path.join(dashboard_dir, "index.html"),
            media_type="text/html; charset=utf-8",
            headers={"Cache-Control": "no-cache"},
        )

    @application.get(
        "/dashboard/assets/{asset_name}",
        include_in_schema=False,
    )
    def dashboard_asset(asset_name: str):
        path = dashboard_assets.get(asset_name)
        if path is None or not os.path.isfile(path):
            raise HTTPException(
                status_code=404,
                detail="dashboard asset not found",
            )
        media_type = (
            "text/css; charset=utf-8"
            if asset_name.endswith(".css")
            else "application/javascript; charset=utf-8"
        )
        return FileResponse(
            path,
            media_type=media_type,
            headers={"Cache-Control": "no-cache"},
        )

    @application.get(
        "/api/v1/vision/people",
        tags=["vision"],
    )
    def get_current_people():
        try:
            return vision_service.get_people()
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="current vision state is unavailable",
            )

    @application.get(
        "/api/v1/vision/objects",
        tags=["vision"],
    )
    def get_current_objects():
        try:
            return vision_service.get_objects()
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="current vision state is unavailable",
            )

    @application.get(
        "/api/v1/vision/count",
        tags=["vision"],
    )
    def count_current_objects(
        object_class: str = Query(
            ...,
            min_length=1,
            max_length=64,
        ),
        minimum_confidence: float = Query(
            0.0,
            ge=0.0,
            le=1.0,
        ),
        zone_id: Optional[str] = Query(
            None,
            min_length=1,
            max_length=64,
        ),
    ):
        try:
            return vision_service.count_objects(
                [object_class],
                minimum_confidence=minimum_confidence,
                zone_id=zone_id,
            )
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="current object count is unavailable",
            )

    @application.get(
        "/api/v1/vision/tracks",
        tags=["vision"],
    )
    def get_current_track_history(
        track_id: Optional[int] = Query(None, ge=1),
        object_class: Optional[str] = Query(
            None,
            min_length=1,
            max_length=64,
        ),
        limit: int = Query(10, ge=1, le=20),
    ):
        if track_id is None and not object_class:
            raise HTTPException(
                status_code=422,
                detail="track_id or object_class is required",
            )
        try:
            return vision_service.get_track_history(
                track_id=track_id,
                object_class=object_class,
                limit=limit,
            )
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="current track history is unavailable",
            )

    @application.get(
        "/api/v1/vision/inventory",
        tags=["vision"],
    )
    def get_current_inventory(
        object_class: Optional[str] = None,
    ):
        try:
            return vision_service.get_inventory(
                object_class=object_class
            )
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="current inventory state is unavailable",
            )

    @application.get(
        "/api/v1/inventory/compare",
        tags=["inventory"],
    )
    def compare_current_inventory(
        object_class: str = Query(
            ...,
            min_length=1,
            max_length=64,
        ),
        expected_count: int = Query(..., ge=0, le=100),
    ):
        try:
            return vision_service.compare_inventory(
                {object_class: expected_count}
            )
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="inventory comparison is unavailable",
            )

    @application.get(
        "/api/v1/inventory/removed",
        tags=["inventory"],
    )
    def get_removed_inventory_items(
        minutes: int = Query(10, ge=1, le=1440),
        object_class: Optional[str] = Query(
            None,
            alias="object_class",
        ),
        camera_id: Optional[str] = Query(
            None,
            alias="camera_id",
        ),
        limit: int = Query(20, ge=1, le=50),
    ):
        try:
            return inventory_history_service.get_removed_items(
                {
                    "minutes": minutes,
                    "object_class": object_class,
                    "camera_id": camera_id,
                    "limit": limit,
                }
            )
        except RuntimeError:
            raise HTTPException(
                status_code=503,
                detail="inventory history is unavailable",
            )

    @application.get(
        "/api/v1/vision/zones",
        tags=["vision"],
    )
    def get_current_zones(zone_id: Optional[str] = None):
        try:
            return vision_service.get_zones(zone_id=zone_id)
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="current zone state is unavailable",
            )

    @application.get(
        "/api/v1/vision/frame",
        tags=["vision"],
        responses={
            200: {
                "content": {"image/jpeg": {}},
                "description": "Latest annotated vision frame",
            },
            503: {"description": "Latest frame unavailable"},
        },
    )
    def get_current_frame():
        try:
            frame = live_frame_service.get()
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="latest vision frame is unavailable",
            )
        return Response(
            content=frame["content"],
            media_type="image/jpeg",
            headers={
                "Cache-Control": "no-store, max-age=0",
                "X-Vision-Frame-Age": str(frame["age_seconds"]),
                "X-Vision-Frame-Stale": str(
                    frame["stale"]
                ).lower(),
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get(
        "/api/v1/vision/model",
        tags=["vision"],
    )
    def get_current_model():
        try:
            return model_info_service.get_model_info({})
        except ModelManifestUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail=str(error),
            )

    @application.get(
        "/api/v1/vision/performance",
        tags=["vision"],
    )
    def get_vision_performance():
        try:
            return vision_service.get_performance()
        except VisionApiUnavailable:
            raise HTTPException(
                status_code=503,
                detail="vision performance metrics are unavailable",
            )

    @application.get(
        "/api/v1/system/status",
        tags=["system"],
    )
    def get_system_status():
        return device_monitor.snapshot()

    @application.get(
        "/api/v1/system/storage",
        tags=["system"],
    )
    def get_project_storage_usage():
        return storage_inventory.snapshot()

    @application.get(
        "/api/v1/system/retention-preview",
        tags=["system"],
    )
    def get_data_retention_preview():
        return retention_preview.preview()

    @application.get(
        "/api/v1/system/retention-cleanup-history",
        tags=["system"],
    )
    def get_retention_cleanup_history(
        limit: int = Query(10, ge=1, le=20),
    ):
        try:
            return retention_cleanup_history.get_history(
                {"limit": limit}
            )
        except RuntimeError as error:
            raise HTTPException(
                status_code=503,
                detail=str(error),
            )

    @application.get(
        "/api/v1/system/benchmark",
        tags=["system"],
    )
    def get_runtime_benchmark():
        try:
            return benchmark_store.get_latest()
        except RuntimeBenchmarkUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail=str(error),
            )

    @application.get(
        "/api/v1/camera/status",
        tags=["camera"],
    )
    def get_camera_status():
        try:
            return camera_status_service.get_status()
        except CameraStatusUnavailable as error:
            raise HTTPException(
                status_code=503,
                detail=str(error),
            )

    @application.get(
        "/api/v1/zones",
        tags=["zones"],
    )
    def get_zones():
        try:
            return zone_service.get_zones()
        except ZoneConfigUnavailable:
            raise HTTPException(
                status_code=503,
                detail="zone configuration is unavailable",
            )

    @application.get(
        "/api/v1/zones/defaults",
        tags=["zones"],
    )
    def get_default_zones():
        try:
            return zone_service.get_default_zones()
        except ZoneConfigUnavailable:
            raise HTTPException(
                status_code=503,
                detail="default zone configuration is unavailable",
            )

    @application.put(
        "/api/v1/zones",
        tags=["zones"],
    )
    def save_zones(
        payload: Dict[str, Any],
        config_token: Optional[str] = Header(
            None,
            alias="X-EdgeSentinel-Config-Token",
        ),
    ):
        try:
            return zone_service.save_zones(
                payload,
                config_token,
            )
        except ZoneSaveDisabled as error:
            raise HTTPException(
                status_code=503,
                detail=str(error),
            )
        except ZoneAuthenticationFailed as error:
            raise HTTPException(
                status_code=401,
                detail=str(error),
            )
        except ZoneVersionConflict as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            )
        except ZoneValidationFailed as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            )
        except ZoneConfigUnavailable:
            raise HTTPException(
                status_code=503,
                detail="zone configuration is unavailable",
            )

    @application.get("/api/v1/events", tags=["events"])
    def list_events(
        limit: int = Query(20, ge=1, le=100),
        event_type: Optional[str] = Query(None, alias="type"),
        object_class: Optional[str] = Query(
            None,
            alias="object_class",
        ),
        camera_id: Optional[str] = Query(None, alias="camera_id"),
        minutes: Optional[int] = Query(None, ge=1, le=1440),
        status: Optional[str] = Query(None),
        severity: Optional[str] = Query(None),
        cursor: Optional[str] = Query(None, max_length=2048),
    ):
        try:
            payload = service.list_events(
                limit=limit,
                event_type=event_type,
                object_class=object_class,
                camera_id=camera_id,
                minutes=minutes,
                status=status,
                severity=severity,
                cursor=cursor,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            )
        except EventDatabaseUnavailable:
            raise HTTPException(
                status_code=503,
                detail="event database is unavailable",
            )
        payload["events"] = [
            evidence_service.add_urls(event)
            for event in payload["events"]
        ]
        return payload

    @application.get(
        "/api/v1/events/summary/recent",
        tags=["events"],
    )
    def summarize_recent_events(
        minutes: int = Query(10, ge=1, le=1440),
        event_type: Optional[str] = Query(None, alias="type"),
        object_class: Optional[str] = Query(
            None,
            alias="object_class",
        ),
        camera_id: Optional[str] = Query(
            None,
            alias="camera_id",
        ),
        status: Optional[str] = Query(None),
        severity: Optional[str] = Query(None),
        bucket_minutes: Optional[int] = Query(None),
        compare_previous: bool = Query(False),
        comparison_offset_minutes: Optional[int] = Query(
            None,
            ge=1,
            le=10080,
        ),
        include_reference_baselines: bool = Query(False),
        change_threshold_percent: int = Query(
            25,
            ge=1,
            le=500,
        ),
        change_threshold_events: int = Query(
            10,
            ge=1,
            le=1000,
        ),
        recent_limit: int = Query(5, ge=1, le=10),
    ):
        try:
            return event_summary_service.summarize(
                minutes=minutes,
                event_type=event_type,
                object_class=object_class,
                camera_id=camera_id,
                status=status,
                severity=severity,
                bucket_minutes=bucket_minutes,
                compare_previous=compare_previous,
                comparison_offset_minutes=(
                    comparison_offset_minutes
                ),
                include_reference_baselines=(
                    include_reference_baselines
                ),
                change_threshold_percent=(
                    change_threshold_percent
                ),
                change_threshold_events=change_threshold_events,
                recent_limit=recent_limit,
            )
        except ValueError as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            )
        except EventDatabaseUnavailable:
            raise HTTPException(
                status_code=503,
                detail="event summary is unavailable",
            )

    @application.get(
        "/api/v1/events/evidence-integrity",
        tags=["events"],
    )
    def verify_recent_event_evidence(
        limit: int = Query(50, ge=1, le=100),
        minutes: Optional[int] = Query(
            None,
            ge=1,
            le=1440,
        ),
    ):
        try:
            return evidence_integrity_service.verify_recent(
                {
                    "limit": limit,
                    "minutes": minutes,
                }
            )
        except EventDatabaseUnavailable:
            raise HTTPException(
                status_code=503,
                detail="event evidence integrity is unavailable",
            )

    @application.get(
        "/api/v1/events/{event_id}/evidence-integrity",
        tags=["events"],
    )
    def verify_exact_event_evidence(event_id: str):
        try:
            return evidence_integrity_service.verify_event(
                {"event_id": event_id}
            )
        except EvidenceIntegrityUnavailable as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
            )
        except EventDatabaseUnavailable:
            raise HTTPException(
                status_code=503,
                detail="event evidence integrity is unavailable",
            )

    @application.get(
        "/api/v1/events/{event_id}",
        tags=["events"],
    )
    def get_event(event_id: str):
        try:
            event = service.get_event(event_id)
        except EventDatabaseUnavailable:
            raise HTTPException(
                status_code=503,
                detail="event database is unavailable",
            )
        if event is None:
            raise HTTPException(
                status_code=404,
                detail="event not found",
            )
        return evidence_service.add_urls(event)

    @application.get(
        "/api/v1/events/{event_id}/evidence/{kind}",
        tags=["evidence"],
        responses={
            200: {
                "content": {"image/jpeg": {}},
                "description": "JPEG event evidence",
            },
            404: {"description": "Evidence not found"},
        },
    )
    def get_evidence(event_id: str, kind: str):
        try:
            event = service.get_event(event_id)
        except EventDatabaseUnavailable:
            raise HTTPException(
                status_code=503,
                detail="event database is unavailable",
            )
        if event is None:
            raise HTTPException(
                status_code=404,
                detail="event not found",
            )
        try:
            path = evidence_service.resolve(event, kind)
        except EvidenceNotFound:
            raise HTTPException(
                status_code=404,
                detail="evidence not found",
            )
        return FileResponse(
            path,
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, max-age=60",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get(
        "/api/v1/harness/tools",
        tags=["harness"],
    )
    def list_tools():
        tools = tool_registry.schemas()
        return {
            "schema_version": "1.0",
            "count": len(tools),
            "tools": tools,
        }

    @application.get(
        "/api/v1/harness/skills",
        tags=["harness"],
    )
    def list_skills():
        skills = skill_registry.list_public()
        return {
            "schema_version": "1.0",
            "count": len(skills),
            "skills": skills,
            "read_only": True,
        }

    @application.get(
        "/api/v1/harness/evaluations/latest",
        tags=["harness"],
    )
    def get_latest_harness_evaluation():
        try:
            return evaluation_report_store.latest()
        except EvaluationReportUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error))

    @application.get(
        "/api/v1/harness/hooks",
        tags=["harness"],
    )
    def list_hooks():
        hooks = hook_dispatcher.list_public()
        return {
            "schema_version": "1.0",
            "count": len(hooks),
            "hooks": hooks,
            "points": list(HOOK_POINTS),
            "read_only": True,
        }

    @application.post(
        "/api/v1/harness/tools/{tool_name}/invoke",
        tags=["harness"],
    )
    def invoke_tool(
        tool_name: str,
        arguments: Dict[str, Any],
    ):
        try:
            return tool_registry.invoke(tool_name, arguments)
        except ToolInvocationError as error:
            status_code = {
                "TOOL_NOT_FOUND": 404,
                "INVALID_ARGUMENTS": 422,
                "POLICY_DENIED": 403,
                "TOOL_EXECUTION_FAILED": 503,
            }.get(error.code, 500)
            raise HTTPException(
                status_code=status_code,
                detail=error.to_dict(),
            )

    @application.post(
        "/api/v1/agent/sessions",
        tags=["agent"],
    )
    def create_agent_session():
        try:
            return session_memory_store.create()
        except SessionMemoryUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error))

    @application.get(
        "/api/v1/agent/memories",
        tags=["agent"],
    )
    def list_agent_memories(
        query: Optional[str] = Query(None, max_length=100),
        kind: Optional[str] = Query(None),
        limit: int = Query(20, ge=1, le=20),
    ):
        arguments = {"limit": limit}
        if query is not None:
            arguments["query"] = query
        if kind is not None:
            arguments["kind"] = kind
        try:
            return long_term_memory_store.search(arguments)
        except LongTermMemoryUnavailable as error:
            message = str(error)
            status_code = 422 if "kind must" in message else 503
            raise HTTPException(
                status_code=status_code,
                detail=message,
            )

    @application.get(
        "/api/v1/agent/memories/status",
        tags=["agent"],
    )
    def get_agent_memory_status():
        try:
            return long_term_memory_store.summary()
        except LongTermMemoryUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error))

    @application.get(
        "/api/v1/agent/sessions/{session_id}",
        tags=["agent"],
    )
    def get_agent_session(session_id: str):
        try:
            return session_memory_store.get(
                session_id,
                include_turns=True,
            )
        except SessionMemoryUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error))

    @application.post(
        "/api/v1/agent/sessions/{session_id}/clear",
        tags=["agent"],
    )
    def clear_agent_session(
        session_id: str,
        payload: Dict[str, Any],
    ):
        try:
            validate_session_clear(payload)
            return session_memory_store.clear(session_id)
        except AgentRequestInvalid as error:
            raise HTTPException(status_code=422, detail=str(error))
        except SessionMemoryUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error))

    @application.post(
        "/api/v1/agent/tasks",
        tags=["agent"],
    )
    def run_agent_task(payload: Dict[str, Any]):
        try:
            request = validate_agent_task_request(payload)
            return execute_agent_request(request)
        except AgentRequestInvalid as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            )
        except SessionMemoryUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error))

    @application.post(
        "/api/v1/agent/jobs",
        tags=["agent"],
        status_code=202,
    )
    def submit_agent_job(
        payload: Dict[str, Any],
        response: Response,
        idempotency_key: Optional[str] = Header(
            None,
            alias="Idempotency-Key",
        ),
    ):
        try:
            request = validate_agent_task_request(payload)
            job = agent_job_queue.submit(
                request,
                idempotency_key=idempotency_key,
            )
            if job.get("idempotent_replay"):
                response.status_code = 200
            return job
        except (AgentRequestInvalid, ValueError) as error:
            raise HTTPException(status_code=422, detail=str(error))
        except AgentJobIdempotencyConflict as error:
            raise HTTPException(status_code=409, detail=str(error))
        except AgentJobQueueFull as error:
            raise HTTPException(status_code=429, detail=str(error))
        except AgentJobUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error))

    @application.get(
        "/api/v1/agent/jobs/{job_id}",
        tags=["agent"],
    )
    def get_agent_job(job_id: str):
        try:
            return agent_job_queue.get(job_id)
        except AgentJobUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error))

    @application.post(
        "/api/v1/agent/jobs/{job_id}/cancel",
        tags=["agent"],
    )
    def cancel_agent_job(
        job_id: str,
        payload: Dict[str, Any],
    ):
        try:
            validate_agent_cancellation(payload)
            return agent_job_queue.cancel(job_id)
        except AgentRequestInvalid as error:
            raise HTTPException(status_code=422, detail=str(error))
        except AgentJobUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error))
        except AgentJobCancellationConflict as error:
            raise HTTPException(status_code=409, detail=str(error))

    @application.get(
        "/api/v1/agent/jobs/{job_id}/events",
        tags=["agent"],
    )
    def stream_agent_job(
        job_id: str,
        after: int = Query(-1, ge=-1),
    ):
        try:
            agent_job_queue.get(job_id)
        except AgentJobUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error))

        def event_stream():
            sequence = int(after)
            while True:
                try:
                    job, changed = agent_job_queue.wait_for_change(
                        job_id,
                        sequence,
                        timeout=15.0,
                    )
                except AgentJobUnavailable:
                    return
                if not changed:
                    yield ": keepalive\n\n"
                    continue
                sequence = int(job["sequence"])
                yield (
                    "id: {0}\n"
                    "event: status\n"
                    "data: {1}\n\n"
                ).format(
                    sequence,
                    json.dumps(
                        job,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
                if job["status"] in TERMINAL_STATUSES:
                    return

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
                "X-Content-Type-Options": "nosniff",
            },
        )

    @application.get(
        "/api/v1/agent/tasks/{task_id}",
        tags=["agent"],
    )
    def get_agent_task(task_id: str):
        try:
            checkpoint = checkpoint_store.load(task_id)
            session_id = session_memory_store.find_session_for_task(
                task_id
            )
            return decorate_agent_task(
                checkpoint,
                session_id,
            )
        except CheckpointNotFound:
            raise HTTPException(
                status_code=404,
                detail="agent task checkpoint not found",
            )
        except SessionMemoryUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error))

    @application.get(
        "/api/v1/agent/tasks/{task_id}/trace",
        tags=["agent"],
    )
    def get_agent_task_trace(
        task_id: str,
        limit: int = Query(50, ge=1, le=100),
    ):
        try:
            checkpoint_store.load(task_id)
            return decorate_agent_trace(
                agent_trace_query.get(task_id, limit=limit)
            )
        except CheckpointNotFound:
            raise HTTPException(
                status_code=404,
                detail="agent task checkpoint not found",
            )
        except AgentTraceUnavailable:
            raise HTTPException(
                status_code=503,
                detail="agent task trace is unavailable",
            )

    @application.get(
        "/api/v1/agent/tasks/{task_id}/snapshot",
        tags=["agent"],
        responses={
            200: {
                "content": {"image/jpeg": {}},
                "description": "Integrity-checked Agent snapshot",
            },
            404: {"description": "Snapshot not found"},
            409: {"description": "Snapshot integrity mismatch"},
        },
    )
    def get_agent_snapshot(task_id: str):
        try:
            checkpoint = checkpoint_store.load(task_id)
            snapshot = agent_snapshot_service.resolve(checkpoint)
        except CheckpointNotFound:
            raise HTTPException(
                status_code=404,
                detail="agent task checkpoint not found",
            )
        except AgentSnapshotNotFound as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
            )
        except AgentSnapshotIntegrityError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            )
        return Response(
            content=snapshot["content"],
            media_type="image/jpeg",
            headers={
                "Cache-Control": "private, no-cache",
                "Content-Disposition": (
                    'inline; filename="{0}"'.format(
                        snapshot["filename"]
                    )
                ),
                "ETag": '"{0}"'.format(snapshot["sha256"]),
                "X-Content-Type-Options": "nosniff",
                "X-EdgeSentinel-Snapshot-SHA256": (
                    snapshot["sha256"]
                ),
            },
        )

    @application.get(
        "/api/v1/agent/tasks/{task_id}/report",
        tags=["agent"],
        responses={
            200: {
                "content": {"text/markdown": {}},
                "description": "Integrity-checked Agent report",
            },
            404: {"description": "Report not found"},
            409: {"description": "Report integrity mismatch"},
        },
    )
    def get_agent_report(task_id: str):
        try:
            checkpoint = checkpoint_store.load(task_id)
            report = agent_report_service.resolve(checkpoint)
        except CheckpointNotFound:
            raise HTTPException(
                status_code=404,
                detail="agent task checkpoint not found",
            )
        except AgentReportNotFound as error:
            raise HTTPException(
                status_code=404,
                detail=str(error),
            )
        except AgentReportIntegrityError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            )
        return Response(
            content=report["content"],
            media_type="text/markdown",
            headers={
                "Cache-Control": "private, no-cache",
                "Content-Disposition": (
                    'attachment; filename="{0}"'.format(
                        report["filename"]
                    )
                ),
                "ETag": '"{0}"'.format(report["sha256"]),
                "X-Content-Type-Options": "nosniff",
                "X-EdgeSentinel-Report-SHA256": (
                    report["sha256"]
                ),
            },
        )

    @application.post(
        "/api/v1/agent/tasks/{task_id}/confirm",
        tags=["agent"],
    )
    def confirm_agent_task(
        task_id: str,
        payload: Dict[str, Any],
        request: Request,
    ):
        try:
            validate_agent_confirmation(payload)
            pending_checkpoint = checkpoint_store.load(task_id)
            pending = pending_checkpoint.get(
                "pending_confirmation"
            ) or {}
            risk = str(pending.get("risk") or "L3").upper()
            minimum_role = (
                "operator" if risk in ("L0", "L1") else "admin"
            )
            principal = request_principal(request)
            tool_name = str(
                pending.get("tool_name") or "unknown"
            )
            auth_service.require_role(
                principal,
                minimum_role,
                action="confirm:{0}".format(tool_name),
            )
            result = agent_loop.resume(
                task_id,
                confirmation_granted=True,
            )
            confirmed_by = {
                "username": principal["username"],
                "role": principal["role"],
            }
            result["confirmed_by"] = confirmed_by
            terminal_checkpoint = checkpoint_store.load(task_id)
            terminal_checkpoint["confirmed_by"] = confirmed_by
            checkpoint_store.save(terminal_checkpoint)
            auth_service.audit_authorized(
                principal,
                "confirm:{0}".format(tool_name),
                task_id=task_id,
                tool_name=tool_name,
                risk=risk,
            )
            finalized = session_memory_store.finalize_task(
                task_id,
                result,
            )
            if finalized is not None:
                prior_turn_count = max(
                    0,
                    int(
                        finalized["memory"].get("turn_count")
                        or 0
                    ) - 1,
                )
                trace_session_memory(
                    result,
                    prior_turn_count,
                    finalized["memory"],
                    "FINALIZED",
                )
                strip_checkpoint_session_prefix(
                    task_id,
                )
            return decorate_agent_task(
                result,
                (
                    finalized["session_id"]
                    if finalized is not None
                    else None
                ),
            )
        except AgentRequestInvalid as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            )
        except CheckpointNotFound:
            raise HTTPException(
                status_code=404,
                detail="agent task checkpoint not found",
            )
        except AgentResumeError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            )
        except SessionMemoryUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error))

    @application.post(
        "/api/v1/agent/tasks/{task_id}/cancel",
        tags=["agent"],
    )
    def cancel_agent_task(
        task_id: str,
        payload: Dict[str, Any],
    ):
        try:
            validate_agent_cancellation(payload)
            result = agent_loop.cancel(task_id)
            finalized = session_memory_store.finalize_task(
                task_id,
                result,
            )
            if finalized is not None:
                prior_turn_count = max(
                    0,
                    int(
                        finalized["memory"].get("turn_count")
                        or 0
                    ) - 1,
                )
                trace_session_memory(
                    result,
                    prior_turn_count,
                    finalized["memory"],
                    "FINALIZED",
                )
                strip_checkpoint_session_prefix(
                    task_id,
                )
            return decorate_agent_task(
                result,
                (
                    finalized["session_id"]
                    if finalized is not None
                    else None
                ),
            )
        except AgentRequestInvalid as error:
            raise HTTPException(
                status_code=422,
                detail=str(error),
            )
        except CheckpointNotFound:
            raise HTTPException(
                status_code=404,
                detail="agent task checkpoint not found",
            )
        except AgentResumeError as error:
            raise HTTPException(
                status_code=409,
                detail=str(error),
            )
        except SessionMemoryUnavailable as error:
            raise HTTPException(status_code=503, detail=str(error))

    return application


app = create_app()


def build_parser():
    parser = argparse.ArgumentParser(
        description="Run the EdgeSentinel local vision operations API."
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--database", default=DEFAULT_DATABASE)
    parser.add_argument("--log-level", default="info")
    return parser


def main():
    args = build_parser().parse_args()
    if args.port <= 0 or args.port > 65535:
        raise SystemExit("--port must be between 1 and 65535")

    import uvicorn

    uvicorn.run(
        create_app(args.database),
        host=args.host,
        port=args.port,
        log_level=args.log_level,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
