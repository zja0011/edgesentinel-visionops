"""Bounded, privacy-aware persistent short-term Agent sessions."""

import json
import os
import re
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone

from packages.harness.utf8 import write_json_atomic
from packages.vision.schemas import beijing_timestamp


SESSION_ID_PATTERN = re.compile(r"^sess_[0-9a-f]{32}$")
TASK_ID_PATTERN = re.compile(r"^task_[0-9a-f]{32}$")
TURN_ID_PATTERN = re.compile(r"^turn_[0-9a-f]{32}$")
BEIJING_TIMEZONE = timezone(timedelta(hours=8))
EVIDENCE_PATH_PATTERN = re.compile(
    r"(?:data/evidence/|/api/v1/events/)[^\s\]\[()<>]+",
    re.IGNORECASE,
)
CREDENTIAL_PATTERN = re.compile(
    r"\b(?:api[_ -]?key|authorization|password|secret|token)\b"
    r"\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
    re.IGNORECASE,
)
BEARER_PATTERN = re.compile(
    r"\bbearer\s+[A-Za-z0-9._~+/=-]{12,}",
    re.IGNORECASE,
)
PROVIDER_KEY_PATTERN = re.compile(
    r"\bsk-[A-Za-z0-9_-]{12,}",
    re.IGNORECASE,
)


class SessionMemoryUnavailable(LookupError):
    pass


def strip_session_conversation_prefix(
    checkpoint,
    task_id,
    expected_record_count=None,
):
    """Return a checkpoint copy containing only this task's history."""
    task_id = str(task_id or "")
    if not TASK_ID_PATTERN.match(task_id):
        raise SessionMemoryUnavailable("invalid task id")
    if not isinstance(checkpoint, dict):
        raise SessionMemoryUnavailable("checkpoint is invalid")
    result = dict(checkpoint)
    model_history = list(result.get("model_history") or [])
    marker_indexes = [
        index
        for index, record in enumerate(model_history)
        if (
            isinstance(record, dict)
            and record.get("role") == "user"
            and record.get("task_id") == task_id
        )
    ]
    if len(marker_indexes) != 1:
        raise SessionMemoryUnavailable(
            "checkpoint current-task marker is inconsistent"
        )
    prefix_count = marker_indexes[0]
    if (
        expected_record_count is not None
        and prefix_count
        != max(0, int(expected_record_count or 0))
    ):
        raise SessionMemoryUnavailable(
            "checkpoint session prefix is inconsistent"
        )
    result["model_history"] = model_history[prefix_count:]
    return result


class SessionMemoryStore(object):
    def __init__(
        self,
        directory,
        max_sessions=100,
        max_turns=12,
        retention_days=7,
    ):
        self.directory = os.path.abspath(directory)
        self.max_sessions = max(1, min(int(max_sessions), 500))
        self.max_turns = max(1, min(int(max_turns), 50))
        self.retention_days = max(
            1,
            min(int(retention_days), 30),
        )
        self._locks = {}
        self._locks_guard = threading.Lock()
        self._directory_lock = threading.Lock()

    def create(self):
        self._validate_directory()
        with self._directory_lock:
            self.prune_expired()
            if len(self._session_files()) >= self.max_sessions:
                raise SessionMemoryUnavailable(
                    "active session limit reached"
                )
            session_id = "sess_{0}".format(uuid.uuid4().hex)
            now_epoch = time.time()
            payload = {
                "schema_version": "1.0",
                "session_id": session_id,
                "created_at": beijing_timestamp(),
                "updated_at": beijing_timestamp(),
                "expires_at": self._timestamp_from_epoch(
                    now_epoch + self.retention_days * 86400
                ),
                "expires_at_epoch": (
                    now_epoch + self.retention_days * 86400
                ),
                "turns": [],
                "pending_tasks": {},
            }
            self._save(payload)
        return self._public(payload, include_turns=True)

    def prune_expired(self):
        now_epoch = time.time()
        removed = 0
        for session_id in self._session_files():
            path = self._path(session_id)
            if os.path.islink(path) or not os.path.isfile(path):
                continue
            try:
                if os.path.getsize(path) > 512 * 1024:
                    continue
                with open(path, "r", encoding="utf-8") as input_file:
                    payload = json.load(input_file)
                if (
                    payload.get("session_id") == session_id
                    and float(payload.get("expires_at_epoch"))
                    <= now_epoch
                ):
                    os.unlink(path)
                    removed += 1
            except (OSError, TypeError, ValueError):
                continue
        return removed

    def get(self, session_id, include_turns=True):
        payload = self._load(session_id)
        return self._public(
            payload,
            include_turns=include_turns,
        )

    def get_or_create(self, session_id=None):
        if session_id:
            return self.get(session_id, include_turns=True)
        return self.create()

    def model_history(self, session_id):
        payload = self._load(session_id)
        history = []
        for turn in payload["turns"][-self.max_turns :]:
            history.append(
                {
                    "role": "user",
                    "context": {
                        "schema_version": "1.0",
                        "user_message": turn["user_message"],
                        "session_memory": {
                            "source_task_id": turn["task_id"],
                            "recorded_at": turn["recorded_at"],
                        },
                    },
                }
            )
            history.append(
                {
                    "role": "assistant",
                    "content": turn["assistant_answer"],
                }
            )
        return history

    def record_task(
        self,
        session_id,
        user_message,
        task_result,
    ):
        task_id = str(task_result.get("task_id") or "")
        if not TASK_ID_PATTERN.match(task_id):
            raise SessionMemoryUnavailable("invalid task id")
        user_message = self._bounded_text(
            user_message,
            "user message",
            1000,
        )
        user_message = self._redact_memory_text(user_message)
        with self._lock(session_id):
            payload = self._load(session_id)
            status = str(task_result.get("status") or "")
            if status in ("AWAITING_CONFIRMATION", "PAUSED"):
                pending = dict(payload.get("pending_tasks") or {})
                if len(pending) >= 8 and task_id not in pending:
                    raise SessionMemoryUnavailable(
                        "pending task limit reached"
                    )
                pending[task_id] = {
                    "user_message": user_message,
                    "recorded_at": beijing_timestamp(),
                }
                payload["pending_tasks"] = pending
            elif status in ("COMPLETED", "CANCELLED"):
                self._append_turn(
                    payload,
                    task_id,
                    user_message,
                    task_result.get("answer") or "",
                    status,
                )
            payload["updated_at"] = beijing_timestamp()
            self._save(payload)
            return self._public(payload, include_turns=False)

    def finalize_task(self, task_id, task_result):
        task_id = str(task_id or "")
        if not TASK_ID_PATTERN.match(task_id):
            raise SessionMemoryUnavailable("invalid task id")
        for session_id in self._session_files():
            with self._lock(session_id):
                try:
                    payload = self._load(session_id)
                except SessionMemoryUnavailable:
                    continue
                pending = dict(payload.get("pending_tasks") or {})
                pending_turn = pending.get(task_id)
                if pending_turn is None:
                    continue
                status = str(task_result.get("status") or "")
                if status in ("COMPLETED", "CANCELLED"):
                    self._append_turn(
                        payload,
                        task_id,
                        pending_turn["user_message"],
                        task_result.get("answer") or "",
                        status,
                    )
                    pending.pop(task_id, None)
                elif status == "FAILED":
                    pending.pop(task_id, None)
                payload["pending_tasks"] = pending
                payload["updated_at"] = beijing_timestamp()
                self._save(payload)
                return {
                    "session_id": session_id,
                    "memory": self._public(
                        payload,
                        include_turns=False,
                    ),
                }
        return None

    def find_session_for_task(self, task_id):
        task_id = str(task_id or "")
        if not TASK_ID_PATTERN.match(task_id):
            raise SessionMemoryUnavailable("invalid task id")
        for session_id in self._session_files():
            try:
                payload = self._load(session_id)
            except SessionMemoryUnavailable:
                continue
            if task_id in (payload.get("pending_tasks") or {}):
                return session_id
            if any(
                turn.get("task_id") == task_id
                for turn in payload.get("turns") or []
            ):
                return session_id
        return None

    def clear(self, session_id):
        with self._lock(session_id):
            payload = self._load(session_id)
            cleared_turns = len(payload["turns"])
            payload["turns"] = []
            payload["pending_tasks"] = {}
            payload["updated_at"] = beijing_timestamp()
            self._save(payload)
            return {
                "schema_version": "1.0",
                "session_id": session_id,
                "cleared_turns": cleared_turns,
                "status": "CLEARED",
                "read_only": False,
            }

    def _append_turn(
        self,
        payload,
        task_id,
        user_message,
        assistant_answer,
        status,
    ):
        assistant_answer = self._bounded_text(
            assistant_answer or "No textual answer was produced.",
            "assistant answer",
            4000,
        )
        assistant_answer = self._redact_memory_text(
            assistant_answer
        )
        turns = list(payload.get("turns") or [])
        turns.append(
            {
                "turn_id": "turn_{0}".format(uuid.uuid4().hex),
                "task_id": task_id,
                "recorded_at": beijing_timestamp(),
                "status": status,
                "user_message": user_message,
                "assistant_answer": assistant_answer,
                "source": "agent_task",
            }
        )
        payload["turns"] = turns[-self.max_turns :]
        pending = dict(payload.get("pending_tasks") or {})
        pending.pop(task_id, None)
        payload["pending_tasks"] = pending

    def _load(self, session_id):
        session_id = self._validate_session_id(session_id)
        self._validate_directory()
        path = self._path(session_id)
        if os.path.islink(path) or not os.path.isfile(path):
            raise SessionMemoryUnavailable("session does not exist")
        try:
            if os.path.getsize(path) > 512 * 1024:
                raise SessionMemoryUnavailable(
                    "session file exceeds size limit"
                )
            with open(path, "r", encoding="utf-8") as input_file:
                payload = json.load(input_file)
        except (OSError, ValueError) as error:
            raise SessionMemoryUnavailable(
                "session is unavailable"
            ) from error
        self._validate_payload(payload, session_id)
        if float(payload["expires_at_epoch"]) <= time.time():
            raise SessionMemoryUnavailable("session has expired")
        return payload

    def _save(self, payload):
        session_id = self._validate_session_id(
            payload.get("session_id")
        )
        self._validate_directory()
        path = self._path(session_id)
        if os.path.islink(path):
            raise SessionMemoryUnavailable(
                "session file must not be a symbolic link"
            )
        write_json_atomic(path, payload)

    def _validate_payload(self, payload, session_id):
        if not isinstance(payload, dict):
            raise SessionMemoryUnavailable(
                "session payload is invalid"
            )
        if (
            payload.get("schema_version") != "1.0"
            or payload.get("session_id") != session_id
            or not isinstance(payload.get("turns"), list)
            or len(payload["turns"]) > self.max_turns
            or not isinstance(payload.get("pending_tasks"), dict)
            or len(payload["pending_tasks"]) > 8
        ):
            raise SessionMemoryUnavailable(
                "session payload is invalid"
            )
        if set(payload) != {
            "schema_version",
            "session_id",
            "created_at",
            "updated_at",
            "expires_at",
            "expires_at_epoch",
            "turns",
            "pending_tasks",
        }:
            raise SessionMemoryUnavailable(
                "session payload fields are invalid"
            )
        if (
            not self._is_timestamp(payload.get("created_at"))
            or not self._is_timestamp(payload.get("updated_at"))
            or not self._is_timestamp(payload.get("expires_at"))
            or not isinstance(
                payload.get("expires_at_epoch"),
                (int, float),
            )
        ):
            raise SessionMemoryUnavailable(
                "session timestamps are invalid"
            )
        for turn in payload["turns"]:
            if (
                not isinstance(turn, dict)
                or set(turn) != {
                    "turn_id",
                    "task_id",
                    "recorded_at",
                    "status",
                    "user_message",
                    "assistant_answer",
                    "source",
                }
                or not TURN_ID_PATTERN.match(
                    str(turn.get("turn_id") or "")
                )
                or not TASK_ID_PATTERN.match(
                    str(turn.get("task_id") or "")
                )
                or not self._is_timestamp(
                    turn.get("recorded_at")
                )
                or turn.get("status")
                not in ("COMPLETED", "CANCELLED")
                or not isinstance(turn.get("user_message"), str)
                or not turn.get("user_message")
                or len(turn["user_message"]) > 1000
                or not isinstance(
                    turn.get("assistant_answer"),
                    str,
                )
                or not turn.get("assistant_answer")
                or len(turn["assistant_answer"]) > 4000
                or turn.get("source") != "agent_task"
            ):
                raise SessionMemoryUnavailable(
                    "session turn is invalid"
                )
        for task_id, pending in payload["pending_tasks"].items():
            if (
                not TASK_ID_PATTERN.match(str(task_id or ""))
                or not isinstance(pending, dict)
                or set(pending) != {
                    "user_message",
                    "recorded_at",
                }
                or not isinstance(
                    pending.get("user_message"),
                    str,
                )
                or not pending.get("user_message")
                or len(pending["user_message"]) > 1000
                or not self._is_timestamp(
                    pending.get("recorded_at")
                )
            ):
                raise SessionMemoryUnavailable(
                    "pending session task is invalid"
                )

    def _session_files(self):
        self._validate_directory()
        result = []
        for name in sorted(os.listdir(self.directory))[:1000]:
            session_id, extension = os.path.splitext(name)
            if extension == ".json" and SESSION_ID_PATTERN.match(
                session_id
            ):
                result.append(session_id)
        return result

    def _validate_directory(self):
        if os.path.islink(self.directory):
            raise SessionMemoryUnavailable(
                "session directory must not be a symbolic link"
            )
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)

    def _path(self, session_id):
        return os.path.join(
            self.directory,
            self._validate_session_id(session_id) + ".json",
        )

    def _lock(self, session_id):
        session_id = self._validate_session_id(session_id)
        with self._locks_guard:
            lock = self._locks.get(session_id)
            if lock is None:
                lock = threading.Lock()
                self._locks[session_id] = lock
        return lock

    @staticmethod
    def _validate_session_id(session_id):
        session_id = str(session_id or "")
        if not SESSION_ID_PATTERN.match(session_id):
            raise SessionMemoryUnavailable("invalid session id")
        return session_id

    @staticmethod
    def _bounded_text(value, label, maximum):
        if not isinstance(value, str):
            raise SessionMemoryUnavailable(
                "{0} must be text".format(label)
            )
        value = value.strip()
        if not value or len(value) > maximum:
            raise SessionMemoryUnavailable(
                "{0} is invalid".format(label)
            )
        return value

    @staticmethod
    def _timestamp_from_epoch(value):
        timestamp = datetime.fromtimestamp(
            value,
            BEIJING_TIMEZONE,
        )
        return (
            timestamp.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "+08:00"
        )

    @staticmethod
    def _is_timestamp(value):
        return (
            isinstance(value, str)
            and 10 <= len(value) <= 64
            and "T" in value
        )

    @staticmethod
    def _redact_memory_text(value):
        value = EVIDENCE_PATH_PATTERN.sub(
            "[REDACTED_EVIDENCE_REFERENCE]",
            value,
        )
        value = CREDENTIAL_PATTERN.sub(
            "[REDACTED_CREDENTIAL]",
            value,
        )
        value = BEARER_PATTERN.sub(
            "[REDACTED_CREDENTIAL]",
            value,
        )
        return PROVIDER_KEY_PATTERN.sub(
            "[REDACTED_CREDENTIAL]",
            value,
        )

    def _public(self, payload, include_turns):
        result = {
            "schema_version": "1.0",
            "session_id": payload["session_id"],
            "created_at": payload["created_at"],
            "updated_at": payload["updated_at"],
            "expires_at": payload["expires_at"],
            "turn_count": len(payload["turns"]),
            "pending_task_count": len(
                payload.get("pending_tasks") or {}
            ),
            "retention_days": self.retention_days,
            "max_turns": self.max_turns,
            "persistent_across_restart": True,
            "raw_tool_results_stored": False,
            "images_stored": False,
            "evidence_paths_stored": False,
        }
        if include_turns:
            result["turns"] = [
                dict(turn) for turn in payload["turns"]
            ]
        return result
