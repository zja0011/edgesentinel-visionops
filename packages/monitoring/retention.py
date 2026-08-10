"""Bounded dry-run preview for fixed EdgeSentinel data retention."""

import copy
from datetime import datetime
import hashlib
import json
import os
import time

from packages.vision.schemas import (
    BEIJING_TIMEZONE,
    beijing_timestamp,
)


class DataRetentionPreview(object):
    MAX_FILES = 100000
    MAX_CANDIDATES = 1000
    DEFAULT_CANDIDATE_LIMIT = 100
    POLICY = (
        {
            "category": "logs",
            "relative_root": "data/logs",
            "retention_days": 3,
            "min_keep_files": 5,
            "filename_rule": "all_regular_files",
        },
        {
            "category": "harness",
            "relative_root": "data/harness",
            "retention_days": 7,
            "min_keep_files": 5,
            "filename_rule": "all_regular_files",
        },
        {
            "category": "runtime",
            "relative_root": "data/runtime",
            "retention_days": 3,
            "min_keep_files": 5,
            "filename_rule": "edgesentinel-*.log",
        },
    )
    PROTECTED_SCOPES = (
        "data/evidence",
        "data/events",
        "data/reports",
        "data/benchmarks",
        "data/state",
        "data/runtime/service.json",
        "data/runtime/vision-supervisor.json",
        "data/runtime/vision-control.json",
    )

    def __init__(
        self,
        project_dir,
        max_files=None,
        candidate_limit=None,
        cache_seconds=60.0,
        epoch_clock=None,
        monotonic_clock=None,
    ):
        self.project_dir = os.path.realpath(
            os.path.abspath(project_dir)
        )
        self.data_dir = os.path.realpath(
            os.path.join(self.project_dir, "data")
        )
        if not self._is_within(
            self.data_dir,
            self.project_dir,
        ):
            raise ValueError("data directory escaped project root")
        self.max_files = int(max_files or self.MAX_FILES)
        if self.max_files < 1 or self.max_files > self.MAX_FILES:
            raise ValueError(
                "max_files must be between 1 and {0}".format(
                    self.MAX_FILES
                )
            )
        self.candidate_limit = int(
            candidate_limit or self.DEFAULT_CANDIDATE_LIMIT
        )
        if (
            self.candidate_limit < 1
            or self.candidate_limit > self.MAX_CANDIDATES
        ):
            raise ValueError(
                "candidate_limit must be between 1 and {0}".format(
                    self.MAX_CANDIDATES
                )
            )
        self.cache_seconds = float(cache_seconds)
        if (
            self.cache_seconds < 0.0
            or self.cache_seconds > 3600.0
        ):
            raise ValueError(
                "cache_seconds must be between 0 and 3600"
            )
        self.epoch_clock = epoch_clock or time.time
        self.monotonic_clock = monotonic_clock or time.monotonic
        self._cached_snapshot = None
        self._cached_at = None

    def preview(self, force=False):
        monotonic_now = float(self.monotonic_clock())
        if (
            not force
            and
            self._cached_snapshot is not None
            and self._cached_at is not None
            and self.cache_seconds > 0.0
            and monotonic_now - self._cached_at
            < self.cache_seconds
        ):
            return copy.deepcopy(self._cached_snapshot)

        payload = self._scan(float(self.epoch_clock()))
        self._cached_snapshot = copy.deepcopy(payload)
        self._cached_at = monotonic_now
        return payload

    def invalidate_cache(self):
        self._cached_snapshot = None
        self._cached_at = None

    def _scan(self, now_epoch):
        rows = []
        scanned = {
            "file_count": 0,
            "directory_count": 0,
            "bytes": 0,
        }
        skipped_symlinks = 0
        scan_errors = 0
        truncated = False

        for rule in self.POLICY:
            if truncated:
                break
            scope = os.path.join(
                self.project_dir,
                *rule["relative_root"].split("/"),
            )
            if not os.path.lexists(scope):
                continue
            if os.path.islink(scope):
                skipped_symlinks += 1
                continue
            real_scope = os.path.realpath(scope)
            if not self._is_within(real_scope, self.data_dir):
                scan_errors += 1
                continue
            stack = [real_scope]
            while stack and not truncated:
                directory = stack.pop()
                try:
                    entries = list(os.scandir(directory))
                except OSError:
                    scan_errors += 1
                    continue
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            skipped_symlinks += 1
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            scanned["directory_count"] += 1
                            stack.append(entry.path)
                            continue
                        if not entry.is_file(
                            follow_symlinks=False
                        ):
                            continue
                        if (
                            scanned["file_count"]
                            >= self.max_files
                        ):
                            truncated = True
                            break
                        stat_result = entry.stat(
                            follow_symlinks=False
                        )
                        size = max(0, int(stat_result.st_size))
                        scanned["file_count"] += 1
                        scanned["bytes"] += size
                        if (
                            self._matches(rule, entry.name)
                            and (
                                rule["category"] != "runtime"
                                or os.path.dirname(entry.path)
                                == real_scope
                            )
                        ):
                            rows.append(
                                {
                                    "category": rule["category"],
                                    "absolute_path": entry.path,
                                    "relative_path": (
                                        self._relative_path(
                                            entry.path
                                        )
                                    ),
                                    "bytes": size,
                                    "modified_epoch": float(
                                        stat_result.st_mtime
                                    ),
                                }
                            )
                    except OSError:
                        scan_errors += 1

        candidate_rows = []
        category_summaries = []
        for rule in self.POLICY:
            matching = [
                row
                for row in rows
                if row["category"] == rule["category"]
            ]
            matching.sort(
                key=lambda row: (
                    row["modified_epoch"],
                    row["relative_path"],
                ),
                reverse=True,
            )
            protected = set(
                row["relative_path"]
                for row in matching[
                    : rule["min_keep_files"]
                ]
            )
            cutoff = (
                now_epoch
                - float(rule["retention_days"]) * 86400.0
            )
            category_candidates = [
                row
                for row in matching
                if row["relative_path"] not in protected
                and row["modified_epoch"] < cutoff
            ]
            category_candidates.sort(
                key=lambda row: (
                    row["modified_epoch"],
                    row["relative_path"],
                )
            )
            candidate_rows.extend(category_candidates)
            category_summaries.append(
                {
                    "category": rule["category"],
                    "retention_days": rule["retention_days"],
                    "min_keep_files": rule["min_keep_files"],
                    "matched_file_count": len(matching),
                    "candidate_file_count": len(
                        category_candidates
                    ),
                    "candidate_bytes": sum(
                        row["bytes"]
                        for row in category_candidates
                    ),
                }
            )

        candidate_rows.sort(
            key=lambda row: (
                row["modified_epoch"],
                row["relative_path"],
            )
        )
        returned = candidate_rows[: self.candidate_limit]
        public_candidates = [
            self._public_candidate(row, now_epoch)
            for row in returned
        ]
        return {
            "schema_version": "1.0",
            "status": (
                "PARTIAL"
                if truncated or scan_errors
                else "COMPLETE"
            ),
            "generated_at": beijing_timestamp(),
            "mode": "PREVIEW_ONLY",
            "root": "data",
            "policy": [
                dict(rule) for rule in self.POLICY
            ],
            "protected_scopes": list(self.PROTECTED_SCOPES),
            "scanned": scanned,
            "candidates": {
                "file_count": len(candidate_rows),
                "bytes": sum(
                    row["bytes"] for row in candidate_rows
                ),
                "returned_count": len(returned),
            },
            "plan_id": self.plan_id_for(public_candidates),
            "by_category": category_summaries,
            "candidate_files": public_candidates,
            "candidate_files_truncated": (
                len(candidate_rows) > len(returned)
            ),
            "skipped_symlinks": skipped_symlinks,
            "scan_errors": scan_errors,
            "truncated": truncated,
            "max_files": self.max_files,
            "candidate_limit": self.candidate_limit,
            "cache_seconds": self.cache_seconds,
            "delete_performed": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    @staticmethod
    def _matches(rule, filename):
        if rule["filename_rule"] == "all_regular_files":
            return True
        return (
            filename.startswith("edgesentinel-")
            and filename.endswith(".log")
        )

    def _relative_path(self, path):
        relative = os.path.relpath(path, self.project_dir)
        return relative.replace(os.sep, "/")

    @staticmethod
    def _public_candidate(row, now_epoch):
        modified = datetime.fromtimestamp(
            row["modified_epoch"],
            BEIJING_TIMEZONE,
        )
        fingerprint = DataRetentionPreview.file_fingerprint(
            row["relative_path"],
            row["bytes"],
            row["modified_epoch"],
        )
        return {
            "category": row["category"],
            "path": row["relative_path"],
            "bytes": row["bytes"],
            "age_days": round(
                max(
                    0.0,
                    (
                        now_epoch - row["modified_epoch"]
                    )
                    / 86400.0,
                ),
                3,
            ),
            "modified_at": (
                modified.strftime("%Y-%m-%dT%H:%M:%S")
                + "+08:00"
            ),
            "fingerprint": fingerprint,
        }

    @staticmethod
    def file_fingerprint(path, size, modified_epoch):
        value = "{0}\n{1}\n{2:.9f}".format(
            str(path),
            int(size),
            float(modified_epoch),
        ).encode("utf-8")
        return hashlib.sha256(value).hexdigest()[:24]

    @staticmethod
    def plan_id_for(candidate_files):
        rows = [
            {
                "path": item.get("path"),
                "bytes": int(item.get("bytes") or 0),
                "modified_at": item.get("modified_at"),
                "fingerprint": item.get("fingerprint"),
            }
            for item in candidate_files
        ]
        encoded = json.dumps(
            rows,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return "ret_{0}".format(
            hashlib.sha256(encoded).hexdigest()[:32]
        )

    @staticmethod
    def _is_within(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except (AttributeError, ValueError):
            prefix = root.rstrip(os.sep) + os.sep
            return path == root or path.startswith(prefix)
