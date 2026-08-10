"""Bounded read-only inventory of EdgeSentinel runtime data."""

import copy
import os
import time

from packages.vision.schemas import beijing_timestamp


class ProjectStorageInventory(object):
    CATEGORY_NAMES = (
        "evidence",
        "events",
        "logs",
        "harness",
        "reports",
        "benchmarks",
        "runtime",
        "state",
        "other",
    )
    MAX_FILES = 100000

    def __init__(
        self,
        project_dir,
        max_files=None,
        cache_seconds=30.0,
        monotonic_clock=None,
    ):
        self.project_dir = os.path.realpath(
            os.path.abspath(project_dir)
        )
        self.data_dir = os.path.realpath(
            os.path.join(self.project_dir, "data")
        )
        self.max_files = int(max_files or self.MAX_FILES)
        if self.max_files < 1 or self.max_files > self.MAX_FILES:
            raise ValueError(
                "max_files must be between 1 and {0}".format(
                    self.MAX_FILES
                )
            )
        if not self._is_within(
            self.data_dir,
            self.project_dir,
        ):
            raise ValueError("data directory escaped project root")
        self.cache_seconds = float(cache_seconds)
        if (
            self.cache_seconds < 0.0
            or self.cache_seconds > 3600.0
        ):
            raise ValueError(
                "cache_seconds must be between 0 and 3600"
            )
        self.monotonic_clock = monotonic_clock or time.monotonic
        self._cached_snapshot = None
        self._cached_at = None

    def snapshot(self):
        now = float(self.monotonic_clock())
        if (
            self._cached_snapshot is not None
            and self._cached_at is not None
            and self.cache_seconds > 0.0
            and now - self._cached_at < self.cache_seconds
        ):
            return copy.deepcopy(self._cached_snapshot)

        payload = self._scan()
        self._cached_snapshot = copy.deepcopy(payload)
        self._cached_at = now
        return payload

    def _scan(self):
        categories = {
            name: {
                "name": name,
                "file_count": 0,
                "directory_count": 0,
                "bytes": 0,
            }
            for name in self.CATEGORY_NAMES
        }
        totals = {
            "file_count": 0,
            "directory_count": 0,
            "bytes": 0,
        }
        skipped_symlinks = 0
        scan_errors = 0
        truncated = False
        stack = [(self.data_dir, None)]

        while stack and not truncated:
            directory, category = stack.pop()
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
                    entry_category = (
                        self._category(entry.name)
                        if category is None
                        else category
                    )
                    if entry.is_dir(follow_symlinks=False):
                        totals["directory_count"] += 1
                        categories[entry_category][
                            "directory_count"
                        ] += 1
                        stack.append(
                            (entry.path, entry_category)
                        )
                        continue
                    if not entry.is_file(follow_symlinks=False):
                        continue
                    if totals["file_count"] >= self.max_files:
                        truncated = True
                        break
                    size = int(
                        entry.stat(follow_symlinks=False).st_size
                    )
                    totals["file_count"] += 1
                    totals["bytes"] += max(0, size)
                    categories[entry_category]["file_count"] += 1
                    categories[entry_category]["bytes"] += max(
                        0,
                        size,
                    )
                except OSError:
                    scan_errors += 1

        category_rows = [
            categories[name]
            for name in self.CATEGORY_NAMES
        ]
        return {
            "schema_version": "1.0",
            "status": (
                "PARTIAL"
                if truncated or scan_errors
                else "COMPLETE"
            ),
            "timestamp": beijing_timestamp(),
            "root": "data",
            "totals": totals,
            "categories": category_rows,
            "skipped_symlinks": skipped_symlinks,
            "scan_errors": scan_errors,
            "truncated": truncated,
            "max_files": self.max_files,
            "cache_seconds": self.cache_seconds,
            "absolute_paths_included": False,
            "read_only": True,
        }

    def _category(self, name):
        return (
            name
            if name in self.CATEGORY_NAMES[:-1]
            else "other"
        )

    @staticmethod
    def _is_within(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except (AttributeError, ValueError):
            prefix = root.rstrip(os.sep) + os.sep
            return path == root or path.startswith(prefix)
