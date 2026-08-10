"""Confirmed, bounded, privacy-aware long-term Agent memory."""

import json
import os
import re
import threading
import uuid

from packages.harness.utf8 import write_json_atomic
from packages.vision.schemas import beijing_timestamp


MEMORY_ID_PATTERN = re.compile(r"^mem_[0-9a-f]{32}$")
MEMORY_KINDS = ("FACT", "PREFERENCE")
SENSITIVE_PATTERN = re.compile(
    r"(?:\b(?:api[_ -]?key|authorization|password|secret|token)\b"
    r"\s*[:=]|\bbearer\s+[A-Za-z0-9._~+/=-]{8,}|"
    r"\bsk-[A-Za-z0-9_-]{8,})",
    re.IGNORECASE,
)
EVIDENCE_PATTERN = re.compile(
    r"(?:data/evidence/|/api/v1/events/)[^\s\]\[()<>]+",
    re.IGNORECASE,
)


class LongTermMemoryUnavailable(RuntimeError):
    pass


class LongTermMemoryStore(object):
    """Store confirmed facts and preferences in one atomic local file."""

    def __init__(self, directory, max_records=100):
        self.directory = os.path.abspath(directory)
        self.path = os.path.join(self.directory, "memory.json")
        self.max_records = max(1, min(int(max_records), 500))
        self._lock = threading.Lock()

    def remember(self, arguments):
        kind = self._kind(arguments.get("kind"))
        key = self._text(arguments.get("key"), "key", 80)
        value = self._text(arguments.get("value"), "value", 500)
        self._reject_sensitive(key)
        self._reject_sensitive(value)
        normalized_key = key.casefold()
        with self._lock:
            payload = self._load()
            existing = next(
                (
                    record
                    for record in payload["records"]
                    if record["kind"] == kind
                    and record["key"].casefold() == normalized_key
                ),
                None,
            )
            now = beijing_timestamp()
            if existing is None:
                if len(payload["records"]) >= self.max_records:
                    raise LongTermMemoryUnavailable(
                        "long-term memory record limit reached"
                    )
                record = {
                    "memory_id": "mem_{0}".format(uuid.uuid4().hex),
                    "kind": kind,
                    "key": key,
                    "value": value,
                    "revision": 1,
                    "created_at": now,
                    "updated_at": now,
                    "provenance": {
                        "source": "user_confirmed",
                        "confirmation_required": True,
                    },
                }
                payload["records"].append(record)
                action = "CREATED"
            elif existing["value"] == value and existing["key"] == key:
                record = existing
                action = "UNCHANGED"
            else:
                existing["key"] = key
                existing["value"] = value
                existing["revision"] = int(existing["revision"]) + 1
                existing["updated_at"] = now
                record = existing
                action = "UPDATED"
            if action != "UNCHANGED":
                payload["updated_at"] = now
                self._save(payload)
            return self._write_result(record, action)

    def forget(self, arguments):
        memory_id = str(arguments.get("memory_id") or "")
        if not MEMORY_ID_PATTERN.match(memory_id):
            raise LongTermMemoryUnavailable("invalid memory id")
        with self._lock:
            payload = self._load()
            record = next(
                (
                    item
                    for item in payload["records"]
                    if item["memory_id"] == memory_id
                ),
                None,
            )
            if record is None:
                raise LongTermMemoryUnavailable(
                    "long-term memory record does not exist"
                )
            payload["records"] = [
                item
                for item in payload["records"]
                if item["memory_id"] != memory_id
            ]
            payload["updated_at"] = beijing_timestamp()
            self._save(payload)
            return {
                "schema_version": "1.0",
                "status": "FORGOTTEN",
                "memory_id": memory_id,
                "kind": record["kind"],
                "key": record["key"],
                "delete_performed": True,
                "read_only": False,
                "provenance": {
                    "source": "user_confirmed",
                    "confirmation_required": True,
                },
            }

    def search(self, arguments=None):
        arguments = dict(arguments or {})
        query = str(arguments.get("query") or "").strip()
        if len(query) > 100:
            raise LongTermMemoryUnavailable("query is too long")
        kind = arguments.get("kind")
        if kind is not None:
            kind = self._kind(kind)
        limit = arguments.get("limit", 20)
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise LongTermMemoryUnavailable("limit must be an integer")
        if limit < 1 or limit > 20:
            raise LongTermMemoryUnavailable(
                "limit must be between 1 and 20"
            )
        query_folded = query.casefold()
        with self._lock:
            payload = self._load()
            records = []
            ordered = sorted(
                payload["records"],
                key=lambda item: item["updated_at"],
                reverse=True,
            )
            for record in ordered:
                if kind is not None and record["kind"] != kind:
                    continue
                haystack = "{0}\n{1}".format(
                    record["key"],
                    record["value"],
                ).casefold()
                if query_folded and query_folded not in haystack:
                    continue
                records.append(self._public_record(record))
                if len(records) >= limit:
                    break
            return {
                "schema_version": "1.0",
                "status": "AVAILABLE",
                "query": query or None,
                "selected_kind": kind,
                "count": len(records),
                "total_records": len(payload["records"]),
                "records": records,
                "bounded": True,
                "read_only": True,
                "raw_tool_results_stored": False,
                "images_stored": False,
                "evidence_paths_stored": False,
            }

    def summary(self):
        kind_counts = {kind: 0 for kind in MEMORY_KINDS}
        with self._lock:
            payload = self._load()
            for record in payload["records"]:
                kind_counts[record["kind"]] += 1
        return {
            "schema_version": "1.0",
            "status": "AVAILABLE",
            "record_count": len(payload["records"]),
            "max_records": self.max_records,
            "kind_counts": kind_counts,
            "updated_at": payload["updated_at"],
            "confirmation_required_for_writes": True,
            "raw_tool_results_stored": False,
            "images_stored": False,
            "evidence_paths_stored": False,
        }

    def _load(self):
        self._validate_directory()
        if not os.path.exists(self.path):
            return {
                "schema_version": "1.0",
                "updated_at": beijing_timestamp(),
                "records": [],
            }
        if os.path.islink(self.path) or not os.path.isfile(self.path):
            raise LongTermMemoryUnavailable(
                "long-term memory file is invalid"
            )
        try:
            if os.path.getsize(self.path) > 512 * 1024:
                raise LongTermMemoryUnavailable(
                    "long-term memory file exceeds size limit"
                )
            with open(self.path, "r", encoding="utf-8") as input_file:
                payload = json.load(input_file)
        except (OSError, ValueError) as error:
            raise LongTermMemoryUnavailable(
                "long-term memory is unavailable"
            ) from error
        self._validate_payload(payload)
        return payload

    def _save(self, payload):
        self._validate_directory()
        if os.path.islink(self.path):
            raise LongTermMemoryUnavailable(
                "long-term memory file must not be a symbolic link"
            )
        self._validate_payload(payload)
        write_json_atomic(self.path, payload)

    def _validate_directory(self):
        if os.path.islink(self.directory):
            raise LongTermMemoryUnavailable(
                "long-term memory directory must not be a symbolic link"
            )
        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)

    def _validate_payload(self, payload):
        if (
            not isinstance(payload, dict)
            or set(payload) != {
                "schema_version",
                "updated_at",
                "records",
            }
            or payload.get("schema_version") != "1.0"
            or not isinstance(payload.get("updated_at"), str)
            or not isinstance(payload.get("records"), list)
            or len(payload["records"]) > self.max_records
        ):
            raise LongTermMemoryUnavailable(
                "long-term memory payload is invalid"
            )
        identities = set()
        keys = set()
        for record in payload["records"]:
            if not self._valid_record(record):
                raise LongTermMemoryUnavailable(
                    "long-term memory record is invalid"
                )
            identity = record["memory_id"]
            compound_key = (
                record["kind"],
                record["key"].casefold(),
            )
            if identity in identities or compound_key in keys:
                raise LongTermMemoryUnavailable(
                    "long-term memory contains duplicate records"
                )
            identities.add(identity)
            keys.add(compound_key)

    @classmethod
    def _valid_record(cls, record):
        return (
            isinstance(record, dict)
            and set(record) == {
                "memory_id",
                "kind",
                "key",
                "value",
                "revision",
                "created_at",
                "updated_at",
                "provenance",
            }
            and MEMORY_ID_PATTERN.match(
                str(record.get("memory_id") or "")
            )
            and record.get("kind") in MEMORY_KINDS
            and isinstance(record.get("key"), str)
            and 1 <= len(record["key"]) <= 80
            and isinstance(record.get("value"), str)
            and 1 <= len(record["value"]) <= 500
            and isinstance(record.get("revision"), int)
            and not isinstance(record.get("revision"), bool)
            and record["revision"] >= 1
            and isinstance(record.get("created_at"), str)
            and isinstance(record.get("updated_at"), str)
            and record.get("provenance") == {
                "source": "user_confirmed",
                "confirmation_required": True,
            }
        )

    @staticmethod
    def _kind(value):
        value = str(value or "").upper()
        if value not in MEMORY_KINDS:
            raise LongTermMemoryUnavailable(
                "kind must be FACT or PREFERENCE"
            )
        return value

    @staticmethod
    def _text(value, label, maximum):
        if not isinstance(value, str):
            raise LongTermMemoryUnavailable(
                "{0} must be text".format(label)
            )
        value = value.strip()
        if not value or len(value) > maximum:
            raise LongTermMemoryUnavailable(
                "{0} is invalid".format(label)
            )
        return value

    @staticmethod
    def _reject_sensitive(value):
        if SENSITIVE_PATTERN.search(value) or EVIDENCE_PATTERN.search(value):
            raise LongTermMemoryUnavailable(
                "credentials and evidence paths cannot be memorized"
            )

    @staticmethod
    def _public_record(record):
        return {
            "memory_id": record["memory_id"],
            "kind": record["kind"],
            "key": record["key"],
            "value": record["value"],
            "revision": record["revision"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
            "provenance": dict(record["provenance"]),
        }

    def _write_result(self, record, action):
        result = self._public_record(record)
        result.update(
            {
                "schema_version": "1.0",
                "status": action,
                "read_only": False,
            }
        )
        return result
