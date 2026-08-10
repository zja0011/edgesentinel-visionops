"""Bounded persistent metadata queue for asynchronous Agent tasks."""

import hashlib
import json
import os
import re
import threading
import time
import uuid
from collections import deque

from packages.harness.execution_control import (
    ExecutionControl,
    ExecutionLimits,
    ModelCostPolicy,
)
from packages.harness.utf8 import write_json_atomic
from packages.vision.schemas import beijing_timestamp


JOB_ID_PATTERN = re.compile(r"^job_[0-9a-f]{32}$")
TASK_ID_PATTERN = re.compile(r"^task_[0-9a-f]{32}$")
IDEMPOTENCY_KEY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$"
)
TERMINAL_STATUSES = (
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "INTERRUPTED",
)
ACTIVE_STATUSES = ("QUEUED", "RUNNING")


class AgentJobUnavailable(LookupError):
    pass


class AgentJobQueueFull(RuntimeError):
    pass


class AgentJobIdempotencyConflict(RuntimeError):
    pass


class AgentJobCancellationConflict(RuntimeError):
    pass


class PersistentAgentJobQueue(object):
    """Single-worker queue with durable metadata and no request replay."""

    def __init__(
        self,
        directory,
        executor,
        max_pending=16,
        max_jobs=100,
        retention_hours=24,
        cooperative_cancel=False,
        execution_limits=None,
        model_cost_policy=None,
    ):
        if not callable(executor):
            raise ValueError("executor must be callable")
        self.directory = os.path.abspath(directory)
        self.executor = executor
        self.max_pending = max(1, min(int(max_pending), 64))
        self.max_jobs = max(10, min(int(max_jobs), 500))
        self.retention_seconds = max(
            3600,
            min(int(retention_hours) * 3600, 7 * 86400),
        )
        self.cooperative_cancel = bool(cooperative_cancel)
        self.execution_limits = execution_limits or ExecutionLimits()
        if not isinstance(self.execution_limits, ExecutionLimits):
            raise TypeError("execution_limits must be ExecutionLimits")
        self.model_cost_policy = (
            model_cost_policy or ModelCostPolicy()
        )
        if not isinstance(self.model_cost_policy, ModelCostPolicy):
            raise TypeError(
                "model_cost_policy must be ModelCostPolicy"
            )
        self._condition = threading.Condition()
        self._jobs = {}
        self._requests = {}
        self._queue = deque()
        self._controls = {}
        self._closed = False
        self._validate_directory()
        self._load_metadata()
        self._worker = threading.Thread(
            target=self._worker_main,
            name="edgesentinel-agent-job-worker",
        )
        self._worker.daemon = True
        self._worker.start()

    def submit(self, request, idempotency_key=None):
        request = self._validate_request(request)
        key_hash = self._idempotency_hash(idempotency_key)
        request_hash = self._request_hash(request)
        with self._condition:
            self._ensure_open()
            self._prune_locked()
            if key_hash:
                existing = self._find_idempotent_locked(key_hash)
                if existing is not None:
                    if existing["request_sha256"] != request_hash:
                        raise AgentJobIdempotencyConflict(
                            "idempotency key was used for another request"
                        )
                    result = self._public(existing)
                    result["idempotent_replay"] = True
                    return result
            queued_count = sum(
                1
                for job in self._jobs.values()
                if job["status"] == "QUEUED"
            )
            if queued_count >= self.max_pending:
                raise AgentJobQueueFull("agent job queue is full")
            if len(self._jobs) >= self.max_jobs:
                self._remove_oldest_terminal_locked()
            if len(self._jobs) >= self.max_jobs:
                raise AgentJobQueueFull(
                    "agent job retention capacity is full"
                )
            now_epoch = time.time()
            job_id = "job_{0}".format(uuid.uuid4().hex)
            job = {
                "schema_version": "1.0",
                "job_id": job_id,
                "status": "QUEUED",
                "created_at": beijing_timestamp(),
                "updated_at": beijing_timestamp(),
                "started_at": None,
                "completed_at": None,
                "created_epoch": now_epoch,
                "updated_epoch": now_epoch,
                "sequence": 0,
                "task_id": None,
                "task_status": None,
                "model": None,
                "steps": None,
                "error_code": None,
                "idempotency_sha256": key_hash,
                "request_sha256": request_hash,
                "cancel_requested_at": None,
                "execution": self._empty_execution(),
            }
            self._jobs[job_id] = job
            self._requests[job_id] = dict(request)
            self._queue.append(job_id)
            self._save(job)
            self._condition.notify_all()
            result = self._public(job)
            result["idempotent_replay"] = False
            return result

    def get(self, job_id):
        job_id = self._validate_job_id(job_id)
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                raise AgentJobUnavailable("agent job does not exist")
            return self._public(job)

    def cancel(self, job_id):
        job_id = self._validate_job_id(job_id)
        with self._condition:
            job = self._jobs.get(job_id)
            if job is None:
                raise AgentJobUnavailable("agent job does not exist")
            if job["status"] == "CANCELLED":
                return self._public(job)
            if job["status"] == "RUNNING" and self.cooperative_cancel:
                control = self._controls.get(job_id)
                if control is None:
                    raise AgentJobCancellationConflict(
                        "running job cancellation is unavailable"
                    )
                if not job.get("cancel_requested_at"):
                    control.request_cancel()
                    job["cancel_requested_at"] = beijing_timestamp()
                    job["execution"] = control.snapshot()
                    self._touch_locked(job)
                return self._public(job)
            if job["status"] != "QUEUED":
                raise AgentJobCancellationConflict(
                    "job cannot be cancelled at a safe point"
                )
            self._requests.pop(job_id, None)
            self._transition_locked(job, "CANCELLED")
            return self._public(job)

    def wait_for_change(self, job_id, after_sequence, timeout=15.0):
        job_id = self._validate_job_id(job_id)
        after_sequence = int(after_sequence)
        timeout = max(0.1, min(float(timeout), 30.0))
        deadline = time.time() + timeout
        with self._condition:
            while True:
                job = self._jobs.get(job_id)
                if job is None:
                    raise AgentJobUnavailable(
                        "agent job does not exist"
                    )
                if (
                    int(job["sequence"]) > after_sequence
                    or job["status"] in TERMINAL_STATUSES
                ):
                    return self._public(job), True
                remaining = deadline - time.time()
                if remaining <= 0:
                    return self._public(job), False
                self._condition.wait(remaining)

    def close(self, timeout=2.0):
        with self._condition:
            self._closed = True
            for control in self._controls.values():
                control.request_cancel()
            self._condition.notify_all()
        self._worker.join(max(0.0, float(timeout)))

    def _worker_main(self):
        while True:
            with self._condition:
                while not self._queue and not self._closed:
                    self._condition.wait()
                if self._closed:
                    return
                job_id = self._queue.popleft()
                job = self._jobs.get(job_id)
                request = self._requests.pop(job_id, None)
                if (
                    job is None
                    or job["status"] != "QUEUED"
                    or request is None
                ):
                    continue
                control = ExecutionControl(
                    self.execution_limits,
                    cost_policy=self.model_cost_policy,
                )
                self._controls[job_id] = control
                job["execution"] = control.snapshot()
                self._transition_locked(job, "RUNNING")
            try:
                result = (
                    self.executor(dict(request), control)
                    if self.cooperative_cancel
                    else self.executor(dict(request))
                )
                if not isinstance(result, dict):
                    raise RuntimeError("executor returned invalid result")
                task_id = str(result.get("task_id") or "")
                if not TASK_ID_PATTERN.match(task_id):
                    raise RuntimeError("executor omitted task id")
                with self._condition:
                    job = self._jobs[job_id]
                    job["task_id"] = task_id
                    job["task_status"] = str(
                        result.get("status") or "UNKNOWN"
                    )[:64]
                    job["model"] = str(
                        result.get("model") or "unknown"
                    )[:128]
                    job["steps"] = int(result.get("steps") or 0)
                    job["execution"] = dict(
                        result.get("execution")
                        or control.snapshot()
                    )
                    task_status = job["task_status"]
                    task_error_code = str(
                        (result.get("error") or {}).get("code") or ""
                    )[:64]
                    if task_status == "CANCELLED":
                        job["error_code"] = (
                            task_error_code or "TASK_CANCELLED"
                        )
                        self._transition_locked(job, "CANCELLED")
                    elif task_status == "FAILED" and (
                        task_error_code.endswith("BUDGET_EXCEEDED")
                        or task_error_code == "DEADLINE_EXCEEDED"
                    ):
                        job["error_code"] = task_error_code
                        self._transition_locked(job, "FAILED")
                    else:
                        self._transition_locked(job, "COMPLETED")
            except Exception:
                with self._condition:
                    job = self._jobs.get(job_id)
                    if job is not None and job["status"] == "RUNNING":
                        job["error_code"] = "EXECUTION_FAILED"
                        job["execution"] = control.snapshot()
                        self._transition_locked(job, "FAILED")
            finally:
                with self._condition:
                    self._controls.pop(job_id, None)

    def _transition_locked(self, job, status):
        now = beijing_timestamp()
        now_epoch = time.time()
        if status == "RUNNING":
            job["started_at"] = now
        if status in TERMINAL_STATUSES:
            job["completed_at"] = now
        job["status"] = status
        job["updated_at"] = now
        job["updated_epoch"] = now_epoch
        job["sequence"] = int(job["sequence"]) + 1
        self._save(job)
        self._condition.notify_all()

    def _touch_locked(self, job):
        job["updated_at"] = beijing_timestamp()
        job["updated_epoch"] = time.time()
        job["sequence"] = int(job["sequence"]) + 1
        self._save(job)
        self._condition.notify_all()

    def _load_metadata(self):
        now = time.time()
        for name in sorted(os.listdir(self.directory))[:1000]:
            job_id, extension = os.path.splitext(name)
            if extension != ".json" or not JOB_ID_PATTERN.match(job_id):
                continue
            path = self._path(job_id)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            try:
                if os.path.getsize(path) > 64 * 1024:
                    continue
                with open(path, "r", encoding="utf-8") as input_file:
                    job = json.load(input_file)
                if "cancel_requested_at" not in job:
                    job["cancel_requested_at"] = None
                if "execution" not in job:
                    job["execution"] = self._empty_execution()
                self._validate_job(job, job_id)
            except (OSError, TypeError, ValueError, AgentJobUnavailable):
                continue
            if (
                job["status"] in TERMINAL_STATUSES
                and now - float(job["updated_epoch"])
                > self.retention_seconds
            ):
                try:
                    os.unlink(path)
                except OSError:
                    pass
                continue
            if job["status"] in ACTIVE_STATUSES:
                job["error_code"] = "SERVICE_RESTARTED"
                job["status"] = "INTERRUPTED"
                job["completed_at"] = beijing_timestamp()
                job["updated_at"] = beijing_timestamp()
                job["updated_epoch"] = now
                job["sequence"] = int(job["sequence"]) + 1
                self._save(job)
            self._jobs[job_id] = job

    def _prune_locked(self):
        cutoff = time.time() - self.retention_seconds
        expired = [
            job_id
            for job_id, job in self._jobs.items()
            if (
                job["status"] in TERMINAL_STATUSES
                and float(job["updated_epoch"]) < cutoff
            )
        ]
        for job_id in expired:
            self._remove_job_locked(job_id)

    def _remove_oldest_terminal_locked(self):
        candidates = [
            job
            for job in self._jobs.values()
            if job["status"] in TERMINAL_STATUSES
        ]
        if candidates:
            oldest = min(
                candidates,
                key=lambda item: float(item["updated_epoch"]),
            )
            self._remove_job_locked(oldest["job_id"])

    def _remove_job_locked(self, job_id):
        self._jobs.pop(job_id, None)
        self._requests.pop(job_id, None)
        path = self._path(job_id)
        if os.path.isfile(path) and not os.path.islink(path):
            try:
                os.unlink(path)
            except OSError:
                pass

    def _find_idempotent_locked(self, key_hash):
        matches = [
            job
            for job in self._jobs.values()
            if job.get("idempotency_sha256") == key_hash
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda item: float(item["created_epoch"]),
        )

    def _save(self, job):
        self._validate_job(job, job["job_id"])
        path = self._path(job["job_id"])
        if os.path.islink(path):
            raise AgentJobUnavailable(
                "agent job file must not be a symbolic link"
            )
        write_json_atomic(path, job)

    def _validate_job(self, job, job_id):
        if not isinstance(job, dict):
            raise AgentJobUnavailable("agent job is invalid")
        required = {
            "schema_version",
            "job_id",
            "status",
            "created_at",
            "updated_at",
            "started_at",
            "completed_at",
            "created_epoch",
            "updated_epoch",
            "sequence",
            "task_id",
            "task_status",
            "model",
            "steps",
            "error_code",
            "idempotency_sha256",
            "request_sha256",
            "cancel_requested_at",
            "execution",
        }
        if (
            set(job) != required
            or job.get("schema_version") != "1.0"
            or job.get("job_id") != job_id
            or job.get("status")
            not in ACTIVE_STATUSES + TERMINAL_STATUSES
            or not isinstance(job.get("sequence"), int)
            or int(job["sequence"]) < 0
            or not isinstance(job.get("created_epoch"), (int, float))
            or not isinstance(job.get("updated_epoch"), (int, float))
            or not re.match(
                r"^[0-9a-f]{64}$",
                str(job.get("request_sha256") or ""),
            )
            or not isinstance(job.get("execution"), dict)
        ):
            raise AgentJobUnavailable("agent job is invalid")
        task_id = job.get("task_id")
        if task_id is not None and not TASK_ID_PATTERN.match(
            str(task_id)
        ):
            raise AgentJobUnavailable("agent job task id is invalid")
        key_hash = job.get("idempotency_sha256")
        if key_hash is not None and not re.match(
            r"^[0-9a-f]{64}$",
            str(key_hash),
        ):
            raise AgentJobUnavailable(
                "agent job idempotency metadata is invalid"
            )
        self._validate_execution(job["execution"])

    @staticmethod
    def _validate_execution(execution):
        if not isinstance(execution, dict) or set(execution) != {
            "schema_version",
            "limits",
            "usage",
            "cost_estimate",
            "remaining_wall_seconds",
            "cancel_requested",
            "cancel_reason",
            "stop_code",
            "stop_stage",
            "cooperative",
            "force_terminated",
        }:
            raise AgentJobUnavailable(
                "agent job execution metadata is invalid"
            )
        limits = execution.get("limits")
        usage = execution.get("usage")
        cost = execution.get("cost_estimate")
        if (
            execution.get("schema_version") != "1.0"
            or not isinstance(limits, dict)
            or set(limits) != {
                "max_wall_seconds",
                "max_model_calls",
                "max_tool_calls",
                "max_external_tool_calls",
                "max_total_tokens",
            }
            or not isinstance(usage, dict)
            or set(usage) != {
                "elapsed_seconds",
                "model_calls",
                "tool_calls",
                "external_tool_calls",
                "model_usage_reports",
                "model_usage_missing",
                "prompt_tokens",
                "completion_tokens",
                "total_tokens",
            }
            or not isinstance(cost, dict)
            or set(cost) != {
                "available",
                "currency",
                "rate_card_id",
                "input_usd_per_million",
                "output_usd_per_million",
                "max_estimated_cost_usd",
                "estimated_cost_usd",
            }
            or execution.get("cancel_reason")
            not in (None, "USER_REQUESTED")
            or execution.get("stop_code")
            not in (
                None,
                "TASK_CANCELLED",
                "DEADLINE_EXCEEDED",
                "MODEL_CALL_BUDGET_EXCEEDED",
                "TOOL_CALL_BUDGET_EXCEEDED",
                "EXTERNAL_REQUEST_BUDGET_EXCEEDED",
                "MODEL_TOKEN_BUDGET_EXCEEDED",
                "MODEL_COST_BUDGET_EXCEEDED",
                "MODEL_USAGE_INVALID",
            )
            or not isinstance(execution.get("cancel_requested"), bool)
            or execution.get("cooperative") is not True
            or execution.get("force_terminated") is not False
        ):
            raise AgentJobUnavailable(
                "agent job execution metadata is invalid"
            )
        numeric_values = (
            limits.get("max_wall_seconds"),
            limits.get("max_model_calls"),
            limits.get("max_tool_calls"),
            limits.get("max_external_tool_calls"),
            usage.get("elapsed_seconds"),
            usage.get("model_calls"),
            usage.get("tool_calls"),
            usage.get("external_tool_calls"),
            limits.get("max_total_tokens"),
            usage.get("model_usage_reports"),
            usage.get("model_usage_missing"),
            usage.get("prompt_tokens"),
            usage.get("completion_tokens"),
            usage.get("total_tokens"),
            execution.get("remaining_wall_seconds"),
        )
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or value < 0
            for value in numeric_values
        ):
            raise AgentJobUnavailable(
                "agent job execution counters are invalid"
            )
        if (
            not isinstance(cost.get("available"), bool)
            or cost.get("currency") != "USD"
        ):
            raise AgentJobUnavailable(
                "agent job cost estimate is invalid"
            )
        cost_values = (
            cost.get("input_usd_per_million"),
            cost.get("output_usd_per_million"),
            cost.get("max_estimated_cost_usd"),
            cost.get("estimated_cost_usd"),
        )
        if cost["available"]:
            if (
                not isinstance(cost.get("rate_card_id"), str)
                or not cost["rate_card_id"]
                or any(
                    isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or value < 0
                    for value in cost_values
                )
            ):
                raise AgentJobUnavailable(
                    "agent job cost estimate is invalid"
                )
        elif (
            cost.get("rate_card_id") is not None
            or any(value is not None for value in cost_values)
        ):
            raise AgentJobUnavailable(
                "agent job cost estimate is invalid"
            )
        stop_stage = execution.get("stop_stage")
        if stop_stage is not None and (
            not isinstance(stop_stage, str)
            or not stop_stage
            or len(stop_stage) > 64
        ):
            raise AgentJobUnavailable(
                "agent job execution stage is invalid"
            )

    def _validate_directory(self):
        if os.path.islink(self.directory):
            raise AgentJobUnavailable(
                "agent job directory must not be a symbolic link"
            )
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)

    @staticmethod
    def _validate_request(request):
        if not isinstance(request, dict) or set(request) != {
            "message",
            "session_id",
        }:
            raise ValueError("agent job request is invalid")
        message = request.get("message")
        if (
            not isinstance(message, str)
            or not message.strip()
            or len(message) > 1000
        ):
            raise ValueError("agent job message is invalid")
        session_id = request.get("session_id")
        if session_id is not None and not re.match(
            r"^sess_[0-9a-f]{32}$",
            str(session_id),
        ):
            raise ValueError("agent job session id is invalid")
        return {
            "message": message.strip(),
            "session_id": session_id,
        }

    @staticmethod
    def _request_hash(request):
        rendered = json.dumps(
            request,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(rendered).hexdigest()

    @staticmethod
    def _idempotency_hash(key):
        if key is None:
            return None
        if (
            not isinstance(key, str)
            or not IDEMPOTENCY_KEY_PATTERN.match(key)
        ):
            raise ValueError("idempotency key is invalid")
        return hashlib.sha256(key.encode("utf-8")).hexdigest()

    def _path(self, job_id):
        return os.path.join(
            self.directory,
            self._validate_job_id(job_id) + ".json",
        )

    @staticmethod
    def _validate_job_id(job_id):
        job_id = str(job_id or "")
        if not JOB_ID_PATTERN.match(job_id):
            raise AgentJobUnavailable("invalid agent job id")
        return job_id

    def _ensure_open(self):
        if self._closed:
            raise AgentJobUnavailable("agent job queue is closed")

    def _public(self, job):
        running_cancel_available = (
            self.cooperative_cancel
            and job["status"] == "RUNNING"
            and not job.get("cancel_requested_at")
        )
        return {
            "schema_version": "1.0",
            "job_id": job["job_id"],
            "status": job["status"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "started_at": job["started_at"],
            "completed_at": job["completed_at"],
            "sequence": int(job["sequence"]),
            "task_id": job["task_id"],
            "task_status": job["task_status"],
            "model": job["model"],
            "steps": job["steps"],
            "error_code": job["error_code"],
            "queue": {
                "max_pending": self.max_pending,
                "max_retained_jobs": self.max_jobs,
                "retention_hours": int(
                    self.retention_seconds / 3600
                ),
                "workers": 1,
            },
            "request_body_persisted": False,
            "safe_cancel": (
                job["status"] == "QUEUED"
                or running_cancel_available
            ),
            "cancel_pending": bool(
                job.get("cancel_requested_at")
                and job["status"] == "RUNNING"
            ),
            "cancel_requested_at": job.get(
                "cancel_requested_at"
            ),
            "execution": dict(job.get("execution") or {}),
        }

    def _empty_execution(self):
        return {
            "schema_version": "1.0",
            "limits": self.execution_limits.to_dict(),
            "usage": {
                "elapsed_seconds": 0.0,
                "model_calls": 0,
                "tool_calls": 0,
                "external_tool_calls": 0,
                "model_usage_reports": 0,
                "model_usage_missing": 0,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
            "cost_estimate": self.model_cost_policy.to_dict(),
            "remaining_wall_seconds": (
                self.execution_limits.max_wall_seconds
            ),
            "cancel_requested": False,
            "cancel_reason": None,
            "stop_code": None,
            "stop_stage": None,
            "cooperative": True,
            "force_terminated": False,
        }
