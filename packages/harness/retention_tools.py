"""Read-only Harness wrapper for fixed data retention preview."""

import json
import os
import re
import stat
import uuid

from packages.monitoring.retention import DataRetentionPreview
from packages.vision.schemas import beijing_timestamp


class RetentionPreviewTools(object):
    def __init__(self, project_dir, previewer=None):
        self.previewer = previewer or DataRetentionPreview(
            project_dir
        )

    def preview(self, unused_arguments):
        return self.previewer.preview()


class RetentionCleanupHistoryTools(object):
    AUDIT_RELATIVE_PATH = (
        "data/runtime/retention-cleanup-audit.jsonl"
    )
    MAX_RETURNED_RECORDS = 20
    MAX_READ_BYTES = 2 * 1024 * 1024
    CLEANUP_ID_PATTERN = re.compile(r"^clean_[0-9a-f]{32}$")
    PLAN_ID_PATTERN = re.compile(r"^ret_[0-9a-f]{32}$")

    def __init__(self, project_dir):
        self.project_dir = os.path.realpath(
            os.path.abspath(project_dir)
        )
        self.audit_path = os.path.join(
            self.project_dir,
            *self.AUDIT_RELATIVE_PATH.split("/"),
        )
        if not self._is_within(
            os.path.realpath(self.audit_path),
            self.project_dir,
        ):
            raise ValueError("cleanup audit path escaped project")

    def get_history(self, arguments):
        limit = int(arguments.get("limit", 10))
        if limit < 1 or limit > self.MAX_RETURNED_RECORDS:
            raise ValueError("limit must be between 1 and 20")
        if not os.path.lexists(self.audit_path):
            return self._empty_payload(limit)

        stat_result = os.lstat(self.audit_path)
        if (
            stat.S_ISLNK(stat_result.st_mode)
            or not stat.S_ISREG(stat_result.st_mode)
            or os.path.realpath(self.audit_path) != self.audit_path
        ):
            raise RuntimeError(
                "cleanup audit is not a trusted regular file"
            )

        size = max(0, int(stat_result.st_size))
        truncated = size > self.MAX_READ_BYTES
        with open(self.audit_path, "rb") as audit_file:
            if truncated:
                audit_file.seek(size - self.MAX_READ_BYTES)
            raw = audit_file.read(self.MAX_READ_BYTES)
        if truncated:
            newline = raw.find(b"\n")
            raw = raw[newline + 1 :] if newline >= 0 else b""

        prepared = {}
        completed = []
        invalid_records = 0
        for raw_line in raw.splitlines():
            if not raw_line.strip():
                continue
            try:
                record = json.loads(raw_line.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                invalid_records += 1
                continue
            if not isinstance(record, dict):
                invalid_records += 1
                continue
            cleanup_id = str(record.get("cleanup_id") or "")
            plan_id = str(record.get("plan_id") or "")
            status_text = str(record.get("status") or "")
            if (
                not self.CLEANUP_ID_PATTERN.match(cleanup_id)
                or not self.PLAN_ID_PATTERN.match(plan_id)
            ):
                invalid_records += 1
                continue
            if status_text == "PREPARED":
                prepared[cleanup_id] = record
                continue
            if status_text not in ("COMPLETED", "PARTIAL"):
                invalid_records += 1
                continue
            initial = prepared.get(cleanup_id) or {}
            completed.append(
                {
                    "cleanup_id": cleanup_id,
                    "timestamp": record.get("timestamp"),
                    "status": status_text,
                    "plan_id": plan_id,
                    "candidate_file_count": self._safe_count(
                        initial.get("candidate_file_count")
                    ),
                    "candidate_bytes": self._safe_count(
                        initial.get("candidate_bytes")
                    ),
                    "deleted_file_count": self._safe_count(
                        record.get("deleted_file_count")
                    ),
                    "deleted_bytes": self._safe_count(
                        record.get("deleted_bytes")
                    ),
                    "failed_file_count": self._safe_count(
                        record.get("failed_file_count")
                    ),
                }
            )

        returned = list(reversed(completed[-limit:]))
        return {
            "schema_version": "1.0",
            "status": (
                "PARTIAL"
                if truncated or invalid_records
                else "COMPLETE"
            ),
            "generated_at": beijing_timestamp(),
            "audit_path": self.AUDIT_RELATIVE_PATH,
            "audit_exists": True,
            "record_count": len(completed),
            "returned_count": len(returned),
            "records": returned,
            "totals": {
                "deleted_file_count": sum(
                    item["deleted_file_count"]
                    for item in completed
                ),
                "deleted_bytes": sum(
                    item["deleted_bytes"] for item in completed
                ),
                "failed_file_count": sum(
                    item["failed_file_count"]
                    for item in completed
                ),
            },
            "invalid_records": invalid_records,
            "truncated": truncated,
            "max_read_bytes": self.MAX_READ_BYTES,
            "limit": limit,
            "paths_included": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    def _empty_payload(self, limit):
        return {
            "schema_version": "1.0",
            "status": "COMPLETE",
            "generated_at": beijing_timestamp(),
            "audit_path": self.AUDIT_RELATIVE_PATH,
            "audit_exists": False,
            "record_count": 0,
            "returned_count": 0,
            "records": [],
            "totals": {
                "deleted_file_count": 0,
                "deleted_bytes": 0,
                "failed_file_count": 0,
            },
            "invalid_records": 0,
            "truncated": False,
            "max_read_bytes": self.MAX_READ_BYTES,
            "limit": limit,
            "paths_included": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    @staticmethod
    def _safe_count(value):
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _is_within(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except (AttributeError, ValueError):
            prefix = root.rstrip(os.sep) + os.sep
            return path == root or path.startswith(prefix)


class RetentionCleanupTools(object):
    AUDIT_RELATIVE_PATH = (
        "data/runtime/retention-cleanup-audit.jsonl"
    )

    def __init__(self, project_dir, previewer=None):
        self.project_dir = os.path.realpath(
            os.path.abspath(project_dir)
        )
        self.previewer = previewer or DataRetentionPreview(
            project_dir
        )
        self.audit_path = os.path.join(
            self.project_dir,
            *self.AUDIT_RELATIVE_PATH.split("/"),
        )
        if not self._is_within(
            os.path.realpath(self.audit_path),
            self.project_dir,
        ):
            raise ValueError("cleanup audit path escaped project")

    def cleanup(self, arguments):
        plan_id = str(arguments.get("plan_id") or "")
        requested_paths = list(
            arguments.get("candidate_paths") or []
        )
        if not requested_paths:
            raise ValueError("candidate_paths cannot be empty")
        if len(set(requested_paths)) != len(requested_paths):
            raise ValueError("candidate_paths must be unique")

        current = self.previewer.preview(force=True)
        if current.get("status") != "COMPLETE":
            raise RuntimeError(
                "retention preview must be complete"
            )
        current_by_path = {
            item["path"]: item
            for item in current.get("candidate_files") or []
        }
        selected = []
        for path in requested_paths:
            item = current_by_path.get(path)
            if item is None:
                raise RuntimeError(
                    "retention plan is stale or path is ineligible"
                )
            selected.append(item)
        expected_plan_id = DataRetentionPreview.plan_id_for(
            selected
        )
        if plan_id != expected_plan_id:
            raise RuntimeError("retention plan id does not match")

        validated = [
            self._validate_candidate(item)
            for item in selected
        ]
        cleanup_id = "clean_{0}".format(uuid.uuid4().hex)
        requested_bytes = sum(
            item["bytes"] for item in selected
        )
        self._append_audit(
            {
                "schema_version": "1.0",
                "cleanup_id": cleanup_id,
                "timestamp": beijing_timestamp(),
                "status": "PREPARED",
                "plan_id": plan_id,
                "candidate_file_count": len(selected),
                "candidate_bytes": requested_bytes,
                "candidate_paths": list(requested_paths),
                "confirmation_required": True,
            }
        )

        deleted_paths = []
        deleted_bytes = 0
        failed_paths = []
        for absolute_path, item in validated:
            try:
                self._recheck_candidate(absolute_path, item)
                os.unlink(absolute_path)
                deleted_paths.append(item["path"])
                deleted_bytes += int(item["bytes"])
            except (OSError, ValueError):
                failed_paths.append(item["path"])

        status_text = (
            "COMPLETED" if not failed_paths else "PARTIAL"
        )
        self._append_audit(
            {
                "schema_version": "1.0",
                "cleanup_id": cleanup_id,
                "timestamp": beijing_timestamp(),
                "status": status_text,
                "plan_id": plan_id,
                "deleted_file_count": len(deleted_paths),
                "deleted_bytes": deleted_bytes,
                "deleted_paths": deleted_paths,
                "failed_file_count": len(failed_paths),
                "failed_paths": failed_paths,
            }
        )
        self.previewer.invalidate_cache()
        return {
            "schema_version": "1.0",
            "status": status_text,
            "cleanup_id": cleanup_id,
            "plan_id": plan_id,
            "deleted_file_count": len(deleted_paths),
            "deleted_bytes": deleted_bytes,
            "deleted_paths": deleted_paths,
            "failed_file_count": len(failed_paths),
            "failed_paths": failed_paths,
            "audit_path": self.AUDIT_RELATIVE_PATH,
            "delete_performed": bool(deleted_paths),
            "confirmation_required": True,
            "absolute_paths_included": False,
            "read_only": False,
        }

    def _validate_candidate(self, item):
        relative_path = str(item.get("path") or "")
        allowed = (
            relative_path.startswith("data/logs/")
            or relative_path.startswith("data/harness/")
            or (
                relative_path.startswith(
                    "data/runtime/edgesentinel-"
                )
                and relative_path.endswith(".log")
                and relative_path.count("/") == 2
            )
        )
        if (
            not allowed
            or relative_path.startswith("/")
            or ".." in relative_path.split("/")
        ):
            raise ValueError("candidate path is outside policy")
        absolute_path = os.path.abspath(
            os.path.join(
                self.project_dir,
                *relative_path.split("/"),
            )
        )
        if not self._is_within(
            absolute_path,
            self.project_dir,
        ):
            raise ValueError("candidate path escaped project")
        real_path = os.path.realpath(absolute_path)
        if (
            real_path != absolute_path
            or not self._is_within(
                real_path,
                self.previewer.data_dir,
            )
        ):
            raise ValueError(
                "candidate path contains a symlink or escaped data"
            )
        self._recheck_candidate(absolute_path, item)
        return absolute_path, item

    @staticmethod
    def _recheck_candidate(absolute_path, item):
        stat_result = os.lstat(absolute_path)
        if (
            stat.S_ISLNK(stat_result.st_mode)
            or not stat.S_ISREG(stat_result.st_mode)
        ):
            raise ValueError("candidate is not a regular file")
        if int(stat_result.st_size) != int(item.get("bytes") or 0):
            raise ValueError("candidate size changed")
        fingerprint = DataRetentionPreview.file_fingerprint(
            item.get("path"),
            stat_result.st_size,
            stat_result.st_mtime,
        )
        if fingerprint != item.get("fingerprint"):
            raise ValueError("candidate timestamp changed")

    def _append_audit(self, payload):
        parent = os.path.dirname(self.audit_path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        with open(
            self.audit_path,
            "a",
            encoding="utf-8",
        ) as audit_file:
            audit_file.write(
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
            audit_file.write("\n")
            audit_file.flush()
            os.fsync(audit_file.fileno())

    @staticmethod
    def _is_within(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except (AttributeError, ValueError):
            prefix = root.rstrip(os.sep) + os.sep
            return path == root or path.startswith(prefix)
