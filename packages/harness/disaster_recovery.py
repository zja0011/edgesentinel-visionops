"""Bounded local disaster-recovery backups and restore validation.

The online service may create and inspect backups.  Applying a restore is
deliberately restricted to an explicit maintenance-mode caller so that an
Agent task cannot overwrite a live event database.
"""

import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import uuid

from packages.vision.schemas import beijing_timestamp


class DisasterRecoveryStore(object):
    SCHEMA_VERSION = "1.0"
    BACKUP_ID_PATTERN = re.compile(r"^dr_[0-9a-f]{32}$")
    PLAN_ID_PATTERN = re.compile(r"^drp_[0-9a-f]{32}$")
    RESTORE_PHRASE = "RESTORE_DISASTER_RECOVERY"
    MAX_FILES = 10000
    MAX_BYTES = 2 * 1024 * 1024 * 1024
    MAX_STATUS_BACKUPS = 20
    MAX_SCAN_BACKUPS = 200
    SQLITE_RELATIVE_PATH = "data/events/edgesentinel.db"
    MANIFEST_NAME = "manifest.json"
    MANIFEST_HASH_NAME = "manifest.sha256"
    PAYLOAD_DIRECTORY = "files"
    PROTECTED_SOURCES = (
        "configs/zones.json",
        "configs/backups",
        "data/events",
        "data/evidence",
        "data/reports",
        "data/benchmarks",
        "data/harness/long-term-memory",
    )
    EXCLUDED_CREDENTIAL_ROOTS = (
        "/etc/edgesentinel-visionops",
        "data/runtime/tls",
    )

    def __init__(
        self,
        project_dir,
        recovery_relative_path="data/recovery",
        max_files=None,
        max_bytes=None,
    ):
        self.project_dir = os.path.realpath(os.path.abspath(project_dir))
        self.recovery_dir = os.path.abspath(
            os.path.join(
                self.project_dir,
                *str(recovery_relative_path).split("/"),
            )
        )
        if not self._is_within(self.recovery_dir, self.project_dir):
            raise ValueError("recovery directory escaped project")
        self.backups_dir = os.path.join(self.recovery_dir, "backups")
        self.rollbacks_dir = os.path.join(self.recovery_dir, "rollbacks")
        self.max_files = int(max_files or self.MAX_FILES)
        self.max_bytes = int(max_bytes or self.MAX_BYTES)
        if self.max_files < 1 or self.max_bytes < 1:
            raise ValueError("recovery bounds must be positive")

    def create_backup(self, unused_arguments=None):
        self._ensure_trusted_directory(self.recovery_dir, create=True)
        self._ensure_trusted_directory(self.backups_dir, create=True)
        backup_id = "dr_{0}".format(uuid.uuid4().hex)
        stage_dir = tempfile.mkdtemp(
            prefix=".staging-{0}-".format(backup_id),
            dir=self.recovery_dir,
        )
        final_dir = os.path.join(self.backups_dir, backup_id)
        payload_dir = os.path.join(stage_dir, self.PAYLOAD_DIRECTORY)
        os.makedirs(payload_dir)
        try:
            entries = []
            totals = {"file_count": 0, "bytes": 0}
            for relative_path in self.PROTECTED_SOURCES:
                if relative_path == "data/events":
                    self._collect_directory(
                        relative_path,
                        payload_dir,
                        entries,
                        totals,
                        excluded_names=(
                            "edgesentinel.db",
                            "edgesentinel.db-wal",
                            "edgesentinel.db-shm",
                        ),
                    )
                    database_path = self._project_path(
                        self.SQLITE_RELATIVE_PATH
                    )
                    if os.path.isfile(database_path):
                        self._copy_sqlite_snapshot(
                            database_path,
                            self._payload_path(
                                payload_dir,
                                self.SQLITE_RELATIVE_PATH,
                            ),
                        )
                        self._add_payload_entry(
                            payload_dir,
                            self.SQLITE_RELATIVE_PATH,
                            entries,
                            totals,
                            kind="sqlite_snapshot",
                        )
                    continue
                source = self._project_path(relative_path)
                if not os.path.lexists(source):
                    continue
                source_stat = os.lstat(source)
                if stat.S_ISDIR(source_stat.st_mode):
                    self._collect_directory(
                        relative_path,
                        payload_dir,
                        entries,
                        totals,
                    )
                elif stat.S_ISREG(source_stat.st_mode):
                    self._copy_regular_source(
                        source,
                        self._payload_path(payload_dir, relative_path),
                    )
                    self._add_payload_entry(
                        payload_dir,
                        relative_path,
                        entries,
                        totals,
                    )
                else:
                    raise RuntimeError(
                        "protected source is not a regular file or directory"
                    )

            entries.sort(key=lambda item: item["path"])
            manifest = {
                "schema_version": self.SCHEMA_VERSION,
                "backup_id": backup_id,
                "created_at": beijing_timestamp(),
                "status": "COMPLETE",
                "mode": "CONSISTENT_LOCAL_BACKUP",
                "restore_semantics": "OVERWRITE_LISTED_FILES_ONLY",
                "files": entries,
                "totals": totals,
                "source_roots": list(self.PROTECTED_SOURCES),
                "sqlite_consistent": any(
                    item["kind"] == "sqlite_snapshot" for item in entries
                ),
                "credentials_included": False,
                "excluded_credential_roots": list(
                    self.EXCLUDED_CREDENTIAL_ROOTS
                ),
                "symlinks_followed": False,
                "absolute_paths_included": False,
            }
            manifest_path = os.path.join(stage_dir, self.MANIFEST_NAME)
            self._write_json_file(manifest_path, manifest)
            manifest_sha256 = self._sha256_file(manifest_path)
            self._write_text_file(
                os.path.join(stage_dir, self.MANIFEST_HASH_NAME),
                manifest_sha256 + "\n",
            )
            os.replace(stage_dir, final_dir)
            stage_dir = None
            return self._public_backup_summary(
                manifest,
                manifest_sha256,
            )
        finally:
            if stage_dir and os.path.isdir(stage_dir):
                shutil.rmtree(stage_dir)

    def get_status(self, arguments=None):
        limit = int((arguments or {}).get("limit", 10))
        if limit < 1 or limit > self.MAX_STATUS_BACKUPS:
            raise ValueError("limit must be between 1 and 20")
        verified_backups = []
        invalid_backups = 0
        truncated = False
        if os.path.lexists(self.backups_dir):
            self._ensure_trusted_directory(self.backups_dir)
            candidates = []
            for name in os.listdir(self.backups_dir):
                candidate = os.path.join(self.backups_dir, name)
                try:
                    modified = float(os.lstat(candidate).st_mtime)
                except OSError:
                    invalid_backups += 1
                    continue
                candidates.append((modified, name))
            candidates.sort(reverse=True)
            if len(candidates) > self.MAX_SCAN_BACKUPS:
                truncated = True
                candidates = candidates[: self.MAX_SCAN_BACKUPS]
            for unused_modified, name in candidates:
                if not self.BACKUP_ID_PATTERN.match(name):
                    invalid_backups += 1
                    continue
                try:
                    manifest, digest = self._load_verified_manifest(name)
                    verified_backups.append(
                        self._public_backup_summary(manifest, digest)
                    )
                except (OSError, ValueError, RuntimeError):
                    invalid_backups += 1
            verified_backups.sort(
                key=lambda item: item.get("created_at") or "",
                reverse=True,
            )
        backups = verified_backups[:limit]
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": (
                "COMPLETE"
                if not invalid_backups and not truncated
                else "PARTIAL"
            ),
            "generated_at": beijing_timestamp(),
            "backup_count": len(verified_backups),
            "returned_count": len(backups),
            "invalid_backup_count": invalid_backups,
            "truncated": truncated,
            "backups": backups,
            "credentials_included": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    def preview_restore(self, arguments):
        backup_id = str(arguments.get("backup_id") or "")
        manifest, manifest_sha256 = self._load_verified_manifest(backup_id)
        changed = []
        unchanged_count = 0
        missing_count = 0
        fingerprint_parts = [backup_id, manifest_sha256]
        for entry in manifest["files"]:
            relative_path = entry["path"]
            target = self._project_path(relative_path)
            current = self._current_fingerprint(target)
            fingerprint_parts.append(
                "{0}:{1}".format(relative_path, current)
            )
            if current == entry["sha256"]:
                unchanged_count += 1
                continue
            if current == "MISSING":
                missing_count += 1
                disposition = "CREATE"
            else:
                disposition = "OVERWRITE"
            if len(changed) < 100:
                changed.append(
                    {
                        "path": relative_path,
                        "action": disposition,
                        "bytes": entry["bytes"],
                    }
                )
        plan_id = "drp_{0}".format(
            hashlib.sha256(
                "\n".join(fingerprint_parts).encode("utf-8")
            ).hexdigest()[:32]
        )
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": "COMPLETE",
            "mode": "PREVIEW_ONLY",
            "backup_id": backup_id,
            "plan_id": plan_id,
            "manifest_sha256": manifest_sha256,
            "file_count": manifest["totals"]["file_count"],
            "bytes": manifest["totals"]["bytes"],
            "changed_file_count": (
                manifest["totals"]["file_count"] - unchanged_count
            ),
            "unchanged_file_count": unchanged_count,
            "missing_file_count": missing_count,
            "changes": changed,
            "changes_truncated": (
                manifest["totals"]["file_count"]
                - unchanged_count
                > len(changed)
            ),
            "delete_performed": False,
            "restore_performed": False,
            "credentials_included": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    def apply_restore(
        self,
        backup_id,
        plan_id,
        confirmation,
        maintenance_mode=False,
    ):
        if not maintenance_mode:
            raise RuntimeError("restore requires host maintenance mode")
        if str(confirmation) != self.RESTORE_PHRASE:
            raise ValueError("invalid disaster recovery confirmation phrase")
        preview = self.preview_restore({"backup_id": backup_id})
        if str(plan_id) != preview["plan_id"]:
            raise RuntimeError("restore plan is stale or does not match")
        manifest, manifest_sha256 = self._load_verified_manifest(backup_id)
        restore_id = "restore_{0}".format(uuid.uuid4().hex)
        rollback_dir = os.path.join(self.rollbacks_dir, restore_id)
        rollback_payload = os.path.join(
            rollback_dir,
            self.PAYLOAD_DIRECTORY,
        )
        self._ensure_trusted_directory(self.rollbacks_dir, create=True)
        os.makedirs(rollback_payload)
        rollback_entries = []
        created_paths = []
        replaced_paths = []
        try:
            for entry in manifest["files"]:
                relative_path = entry["path"]
                target = self._project_path(relative_path)
                if os.path.lexists(target):
                    self._validate_regular_target(target)
                    self._copy_regular_source(
                        target,
                        self._payload_path(
                            rollback_payload,
                            relative_path,
                        ),
                    )
                    rollback_entries.append(relative_path)
                else:
                    created_paths.append(relative_path)
            self._write_json_file(
                os.path.join(rollback_dir, "rollback.json"),
                {
                    "schema_version": self.SCHEMA_VERSION,
                    "restore_id": restore_id,
                    "backup_id": backup_id,
                    "created_at": beijing_timestamp(),
                    "replaced_paths": rollback_entries,
                    "created_paths": created_paths,
                    "credentials_included": False,
                },
            )
            backup_payload = os.path.join(
                self.backups_dir,
                backup_id,
                self.PAYLOAD_DIRECTORY,
            )
            for entry in manifest["files"]:
                relative_path = entry["path"]
                source = self._payload_path(
                    backup_payload,
                    relative_path,
                )
                target = self._project_path(relative_path)
                self._atomic_replace_from(source, target)
                if self._sha256_file(target) != entry["sha256"]:
                    raise RuntimeError("restored file integrity mismatch")
                if entry["kind"] == "sqlite_snapshot":
                    self._verify_sqlite_file(target)
                replaced_paths.append(relative_path)
        except Exception:
            self._rollback_restore(
                rollback_payload,
                rollback_entries,
                created_paths,
            )
            raise
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": "COMPLETED",
            "restore_id": restore_id,
            "backup_id": backup_id,
            "plan_id": plan_id,
            "manifest_sha256": manifest_sha256,
            "restored_file_count": len(replaced_paths),
            "rollback_file_count": len(rollback_entries),
            "rollback_available": True,
            "service_maintenance_required": True,
            "confirmation_required": True,
            "credentials_included": False,
            "absolute_paths_included": False,
            "read_only": False,
        }

    def _collect_directory(
        self,
        relative_root,
        payload_dir,
        entries,
        totals,
        excluded_names=(),
    ):
        source_root = self._project_path(relative_root)
        if not os.path.lexists(source_root):
            return
        self._ensure_trusted_directory(source_root)
        for current_root, directory_names, file_names in os.walk(
            source_root,
            topdown=True,
            followlinks=False,
        ):
            self._ensure_trusted_directory(current_root)
            for directory_name in list(directory_names):
                candidate = os.path.join(current_root, directory_name)
                candidate_stat = os.lstat(candidate)
                if stat.S_ISLNK(candidate_stat.st_mode):
                    raise RuntimeError("symlink found in protected source")
                if not stat.S_ISDIR(candidate_stat.st_mode):
                    raise RuntimeError("invalid directory entry")
            for file_name in sorted(file_names):
                if (
                    current_root == source_root
                    and file_name in excluded_names
                ):
                    continue
                source = os.path.join(current_root, file_name)
                source_stat = os.lstat(source)
                if not stat.S_ISREG(source_stat.st_mode):
                    raise RuntimeError("non-regular protected file found")
                relative_path = os.path.relpath(
                    source,
                    self.project_dir,
                ).replace(os.sep, "/")
                self._validate_relative_path(relative_path)
                self._copy_regular_source(
                    source,
                    self._payload_path(payload_dir, relative_path),
                )
                self._add_payload_entry(
                    payload_dir,
                    relative_path,
                    entries,
                    totals,
                )

    def _add_payload_entry(
        self,
        payload_dir,
        relative_path,
        entries,
        totals,
        kind="regular",
    ):
        payload_path = self._payload_path(payload_dir, relative_path)
        payload_stat = os.lstat(payload_path)
        if not stat.S_ISREG(payload_stat.st_mode):
            raise RuntimeError("backup payload is not a regular file")
        file_size = int(payload_stat.st_size)
        if len(entries) + 1 > self.max_files:
            raise RuntimeError("backup file count exceeds limit")
        if totals["bytes"] + file_size > self.max_bytes:
            raise RuntimeError("backup bytes exceed limit")
        entries.append(
            {
                "path": relative_path,
                "bytes": file_size,
                "sha256": self._sha256_file(payload_path),
                "kind": kind,
            }
        )
        totals["file_count"] += 1
        totals["bytes"] += file_size

    def _copy_sqlite_snapshot(self, source_path, destination_path):
        parent = os.path.dirname(destination_path)
        self._ensure_trusted_directory(parent, create=True)
        source = sqlite3.connect(source_path, timeout=30.0)
        destination = sqlite3.connect(destination_path)
        try:
            backup_method = getattr(source, "backup", None)
            if callable(backup_method):
                backup_method(destination)
            else:
                source.execute("BEGIN")
                script = "\n".join(source.iterdump())
                destination.executescript(script)
                source.rollback()
            integrity = destination.execute(
                "PRAGMA integrity_check"
            ).fetchone()
            if not integrity or str(integrity[0]).lower() != "ok":
                raise RuntimeError("SQLite backup integrity check failed")
            destination.commit()
        finally:
            destination.close()
            source.close()

    def _load_verified_manifest(self, backup_id):
        backup_id = str(backup_id)
        if not self.BACKUP_ID_PATTERN.match(backup_id):
            raise ValueError("invalid disaster recovery backup id")
        backup_dir = os.path.join(self.backups_dir, backup_id)
        self._ensure_trusted_directory(backup_dir)
        manifest_path = os.path.join(backup_dir, self.MANIFEST_NAME)
        hash_path = os.path.join(backup_dir, self.MANIFEST_HASH_NAME)
        self._validate_regular_target(manifest_path)
        self._validate_regular_target(hash_path)
        with open(hash_path, "r", encoding="ascii") as hash_file:
            expected_digest = hash_file.read(128).strip().lower()
        actual_digest = self._sha256_file(manifest_path)
        if (
            not re.match(r"^[0-9a-f]{64}$", expected_digest)
            or expected_digest != actual_digest
        ):
            raise RuntimeError("backup manifest integrity mismatch")
        with open(manifest_path, "r", encoding="utf-8") as manifest_file:
            manifest = json.load(manifest_file)
        self._validate_manifest(manifest, backup_id)
        payload_dir = os.path.join(backup_dir, self.PAYLOAD_DIRECTORY)
        self._ensure_trusted_directory(payload_dir)
        expected_paths = set()
        for entry in manifest["files"]:
            relative_path = entry["path"]
            expected_paths.add(relative_path)
            payload_path = self._payload_path(payload_dir, relative_path)
            self._validate_regular_target(payload_path)
            if int(os.lstat(payload_path).st_size) != entry["bytes"]:
                raise RuntimeError("backup payload size mismatch")
            if self._sha256_file(payload_path) != entry["sha256"]:
                raise RuntimeError("backup payload integrity mismatch")
            if entry["kind"] == "sqlite_snapshot":
                self._verify_sqlite_file(payload_path)
        actual_paths = set()
        for current_root, directory_names, file_names in os.walk(
            payload_dir,
            followlinks=False,
        ):
            self._ensure_trusted_directory(current_root)
            for directory_name in directory_names:
                candidate = os.path.join(current_root, directory_name)
                if stat.S_ISLNK(os.lstat(candidate).st_mode):
                    raise RuntimeError("backup payload contains symlink")
            for file_name in file_names:
                candidate = os.path.join(current_root, file_name)
                self._validate_regular_target(candidate)
                actual_paths.add(
                    os.path.relpath(candidate, payload_dir).replace(
                        os.sep,
                        "/",
                    )
                )
        if actual_paths != expected_paths:
            raise RuntimeError("backup payload inventory mismatch")
        return manifest, actual_digest

    def _validate_manifest(self, manifest, backup_id):
        if not isinstance(manifest, dict):
            raise RuntimeError("backup manifest is invalid")
        if (
            manifest.get("schema_version") != self.SCHEMA_VERSION
            or manifest.get("backup_id") != backup_id
            or manifest.get("status") != "COMPLETE"
            or manifest.get("credentials_included") is not False
            or manifest.get("absolute_paths_included") is not False
        ):
            raise RuntimeError("backup manifest metadata is invalid")
        files = manifest.get("files")
        totals = manifest.get("totals")
        if not isinstance(files, list) or not isinstance(totals, dict):
            raise RuntimeError("backup manifest inventory is invalid")
        if len(files) > self.max_files:
            raise RuntimeError("backup manifest file limit exceeded")
        seen = set()
        byte_total = 0
        for entry in files:
            if not isinstance(entry, dict):
                raise RuntimeError("backup manifest entry is invalid")
            path = self._validate_relative_path(entry.get("path"))
            if not any(
                path == allowed
                or path.startswith(allowed.rstrip("/") + "/")
                for allowed in self.PROTECTED_SOURCES
            ):
                raise RuntimeError(
                    "backup manifest path is outside recovery policy"
                )
            if path in seen:
                raise RuntimeError("backup manifest contains duplicates")
            seen.add(path)
            size = int(entry.get("bytes"))
            digest = str(entry.get("sha256") or "").lower()
            if size < 0 or not re.match(r"^[0-9a-f]{64}$", digest):
                raise RuntimeError("backup manifest fingerprint is invalid")
            if entry.get("kind") not in ("regular", "sqlite_snapshot"):
                raise RuntimeError("backup manifest kind is invalid")
            byte_total += size
        if byte_total > self.max_bytes:
            raise RuntimeError("backup manifest byte limit exceeded")
        if (
            int(totals.get("file_count", -1)) != len(files)
            or int(totals.get("bytes", -1)) != byte_total
        ):
            raise RuntimeError("backup manifest totals are invalid")

    def _rollback_restore(
        self,
        rollback_payload,
        rollback_entries,
        created_paths,
    ):
        for relative_path in rollback_entries:
            source = self._payload_path(
                rollback_payload,
                relative_path,
            )
            target = self._project_path(relative_path)
            self._atomic_replace_from(source, target)
        for relative_path in created_paths:
            target = self._project_path(relative_path)
            if os.path.isfile(target) and not os.path.islink(target):
                os.unlink(target)

    def _atomic_replace_from(self, source, target):
        self._validate_regular_target(source)
        parent = os.path.dirname(target)
        self._ensure_trusted_directory(parent, create=True)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".restore-",
            suffix=".tmp",
            dir=parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as output_file:
                with open(source, "rb") as input_file:
                    shutil.copyfileobj(input_file, output_file, 1024 * 1024)
                output_file.flush()
                os.fsync(output_file.fileno())
            os.replace(temporary_path, target)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def _copy_regular_source(self, source, destination):
        self._validate_regular_target(source)
        before = os.lstat(source)
        parent = os.path.dirname(destination)
        self._ensure_trusted_directory(parent, create=True)
        with open(source, "rb") as input_file:
            with open(destination, "wb") as output_file:
                shutil.copyfileobj(input_file, output_file, 1024 * 1024)
                output_file.flush()
                os.fsync(output_file.fileno())
        after = os.lstat(source)
        if (
            int(before.st_size) != int(after.st_size)
            or float(before.st_mtime) != float(after.st_mtime)
        ):
            raise RuntimeError("protected source changed during backup")

    def _current_fingerprint(self, target):
        if not os.path.lexists(target):
            return "MISSING"
        self._validate_regular_target(target)
        return self._sha256_file(target)

    def _project_path(self, relative_path):
        relative_path = self._validate_relative_path(relative_path)
        path = os.path.abspath(
            os.path.join(self.project_dir, *relative_path.split("/"))
        )
        if not self._is_within(path, self.project_dir):
            raise ValueError("path escaped project")
        return path

    def _payload_path(self, payload_dir, relative_path):
        relative_path = self._validate_relative_path(relative_path)
        path = os.path.abspath(
            os.path.join(payload_dir, *relative_path.split("/"))
        )
        if not self._is_within(path, os.path.abspath(payload_dir)):
            raise ValueError("payload path escaped backup")
        return path

    @staticmethod
    def _validate_relative_path(value):
        value = str(value or "").replace("\\", "/")
        if (
            not value
            or value.startswith("/")
            or "\x00" in value
            or any(part in ("", ".", "..") for part in value.split("/"))
        ):
            raise ValueError("invalid relative recovery path")
        return value

    def _ensure_trusted_directory(self, path, create=False):
        path = os.path.abspath(path)
        if create and not os.path.lexists(path):
            ancestor = path
            while not os.path.lexists(ancestor):
                parent = os.path.dirname(ancestor)
                if parent == ancestor:
                    raise RuntimeError("trusted directory has no ancestor")
                ancestor = parent
            ancestor_stat = os.lstat(ancestor)
            if (
                stat.S_ISLNK(ancestor_stat.st_mode)
                or not stat.S_ISDIR(ancestor_stat.st_mode)
                or os.path.realpath(ancestor) != ancestor
                or not self._is_within(ancestor, self.project_dir)
            ):
                raise RuntimeError(
                    "trusted directory ancestor is not trusted"
                )
            os.makedirs(path)
        if not os.path.lexists(path):
            raise OSError("trusted directory does not exist")
        path_stat = os.lstat(path)
        if (
            stat.S_ISLNK(path_stat.st_mode)
            or not stat.S_ISDIR(path_stat.st_mode)
            or os.path.realpath(path) != path
        ):
            raise RuntimeError("directory is not trusted")
        if not self._is_within(path, self.project_dir):
            raise RuntimeError("trusted directory escaped project")

    def _validate_regular_target(self, path):
        path = os.path.abspath(path)
        path_stat = os.lstat(path)
        if (
            stat.S_ISLNK(path_stat.st_mode)
            or not stat.S_ISREG(path_stat.st_mode)
            or os.path.realpath(path) != path
        ):
            raise RuntimeError("path is not a trusted regular file")
        if not self._is_within(path, self.project_dir):
            raise RuntimeError("regular file escaped project")

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with open(path, "rb") as input_file:
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _verify_sqlite_file(path):
        connection = sqlite3.connect(path, timeout=10.0)
        try:
            connection.execute("PRAGMA query_only=ON")
            result = connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()
            if not result or str(result[0]).lower() != "ok":
                raise RuntimeError("SQLite payload integrity check failed")
        finally:
            connection.close()

    @staticmethod
    def _write_json_file(path, payload):
        with open(path, "w", encoding="utf-8") as output_file:
            json.dump(
                payload,
                output_file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            output_file.write("\n")
            output_file.flush()
            os.fsync(output_file.fileno())

    @staticmethod
    def _write_text_file(path, value):
        with open(path, "w", encoding="ascii") as output_file:
            output_file.write(value)
            output_file.flush()
            os.fsync(output_file.fileno())

    @staticmethod
    def _public_backup_summary(manifest, manifest_sha256):
        return {
            "schema_version": "1.0",
            "status": manifest["status"],
            "backup_id": manifest["backup_id"],
            "created_at": manifest["created_at"],
            "file_count": manifest["totals"]["file_count"],
            "bytes": manifest["totals"]["bytes"],
            "manifest_sha256": manifest_sha256,
            "sqlite_consistent": manifest["sqlite_consistent"],
            "credentials_included": False,
            "absolute_paths_included": False,
            "read_only": False,
        }

    @staticmethod
    def _is_within(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except (AttributeError, ValueError):
            prefix = root.rstrip(os.sep) + os.sep
            return path == root or path.startswith(prefix)
