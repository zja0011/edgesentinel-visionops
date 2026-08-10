"""Bounded read-only verification of evidence referenced by events."""

import hashlib
import os
import re
import stat
from urllib.parse import quote

from packages.api.event_service import EventQueryService
from packages.vision.schemas import beijing_timestamp


EVENT_ID_PATTERN = re.compile(r"^evt_[0-9a-f]{32}$")


class EvidenceIntegrityUnavailable(RuntimeError):
    """Raised when exact evidence status cannot be read safely."""


class EvidenceIntegrityService(object):
    MAX_EVENTS = 100
    MAX_ISSUES = 20
    MAX_HASH_BYTES = 16 * 1024 * 1024
    VALID_KINDS = ("primary", "before", "after")

    def __init__(self, project_dir, database_path):
        self.project_dir = os.path.realpath(
            os.path.abspath(project_dir)
        )
        self.evidence_dir = os.path.realpath(
            os.path.join(
                self.project_dir,
                "data",
                "evidence",
            )
        )
        if not self._is_within(
            self.evidence_dir,
            self.project_dir,
        ):
            raise ValueError("evidence directory escaped project")
        self.events = EventQueryService(database_path)

    def verify_recent(self, arguments):
        limit = int(arguments.get("limit", 50))
        if limit < 1 or limit > self.MAX_EVENTS:
            raise ValueError("limit must be between 1 and 100")
        minutes = arguments.get("minutes")
        if minutes is not None:
            minutes = int(minutes)
            if minutes < 1 or minutes > 1440:
                raise ValueError(
                    "minutes must be between 1 and 1440"
                )

        event_result = self.events.list_events(
            limit=limit,
            minutes=minutes,
        )
        events = event_result.get("events") or []
        reference_count = 0
        valid_count = 0
        events_with_evidence = 0
        unique_valid_files = set()
        issues = []
        issue_count = 0

        for event in events:
            references = self._references(event)
            if references:
                events_with_evidence += 1
            for kind, stored_path in references:
                reference_count += 1
                code, resolved = self._verify_file(stored_path)
                if code is None:
                    valid_count += 1
                    unique_valid_files.add(resolved)
                    continue
                issue_count += 1
                if len(issues) < self.MAX_ISSUES:
                    issues.append(
                        {
                            "event_id": event.get("event_id"),
                            "evidence_kind": kind,
                            "code": code,
                        }
                    )

        payload = {
            "schema_version": "1.0",
            "status": "PASS" if issue_count == 0 else "WARN",
            "generated_at": beijing_timestamp(),
            "requested_event_limit": limit,
            "checked_event_count": len(events),
            "events_with_evidence": events_with_evidence,
            "events_without_evidence": (
                len(events) - events_with_evidence
            ),
            "referenced_evidence_count": reference_count,
            "valid_evidence_count": valid_count,
            "unique_valid_file_count": len(unique_valid_files),
            "issue_count": issue_count,
            "issues": issues,
            "issues_truncated": issue_count > len(issues),
            "max_issues": self.MAX_ISSUES,
            "jpeg_signature_checked": True,
            "paths_included": False,
            "absolute_paths_included": False,
            "read_only": True,
        }
        if event_result.get("window") is not None:
            payload["window"] = event_result["window"]
        return payload

    def verify_event(self, arguments):
        event_id = str(
            arguments.get("event_id") or ""
        ).lower()
        if not EVENT_ID_PATTERN.match(event_id):
            raise EvidenceIntegrityUnavailable(
                "event_id must be evt_ followed by 32 hex characters"
            )
        event = self.events.get_event(event_id)
        if event is None:
            raise EvidenceIntegrityUnavailable(
                "event does not exist"
            )

        evidence = []
        valid_count = 0
        issue_count = 0
        for kind, stored_path in self._references(event):
            code, resolved = self._verify_file(stored_path)
            record = {"kind": kind}
            if code is None:
                hash_code, size, digest = self._hash_file(
                    resolved
                )
                if hash_code is not None:
                    record["status"] = hash_code
                    issue_count += 1
                else:
                    record.update(
                        {
                            "status": "VALID",
                            "bytes": int(size),
                            "sha256": digest,
                            "url": (
                                "/api/v1/events/{0}/evidence/{1}"
                            ).format(
                                quote(event_id, safe=""),
                                kind,
                            ),
                        }
                    )
                    valid_count += 1
            else:
                record["status"] = code
                issue_count += 1
            evidence.append(record)

        if not evidence:
            status = "NO_EVIDENCE"
        elif issue_count:
            status = "WARN"
        else:
            status = "PASS"
        return {
            "schema_version": "1.0",
            "status": status,
            "generated_at": beijing_timestamp(),
            "event": {
                "event_id": event["event_id"],
                "event_type": event["event_type"],
                "timestamp": event["timestamp"],
                "camera_id": event["camera_id"],
                "zone_id": event["zone_id"],
                "object_class": event["object_class"],
            },
            "referenced_evidence_count": len(evidence),
            "valid_evidence_count": valid_count,
            "issue_count": issue_count,
            "evidence": evidence,
            "maximum_hash_bytes": self.MAX_HASH_BYTES,
            "jpeg_signature_checked": True,
            "sha256_checked": bool(valid_count),
            "paths_included": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    @staticmethod
    def _references(event):
        references = []
        primary = event.get("evidence_path")
        if primary:
            references.append(("primary", primary))
        details = event.get("details") or {}
        for kind in ("before", "after"):
            value = details.get(
                "{0}_evidence_path".format(kind)
            )
            if value:
                references.append((kind, value))
        return references

    def _verify_file(self, stored_path):
        if (
            not isinstance(stored_path, str)
            or not stored_path
            or os.path.isabs(stored_path)
        ):
            return "UNSAFE_PATH", None
        candidate = os.path.abspath(
            os.path.join(self.project_dir, stored_path)
        )
        resolved = os.path.realpath(candidate)
        if (
            candidate != resolved
            or not self._is_within(
                resolved,
                self.evidence_dir,
            )
        ):
            return "UNSAFE_PATH", None
        try:
            stat_result = os.lstat(candidate)
        except OSError:
            return "MISSING_FILE", None
        if (
            stat.S_ISLNK(stat_result.st_mode)
            or not stat.S_ISREG(stat_result.st_mode)
        ):
            return "UNSAFE_PATH", None
        if os.path.splitext(candidate)[1].lower() not in (
            ".jpg",
            ".jpeg",
        ):
            return "UNSUPPORTED_TYPE", None
        if int(stat_result.st_size) < 4:
            return "INVALID_JPEG", None
        try:
            with open(candidate, "rb") as evidence_file:
                start = evidence_file.read(2)
                evidence_file.seek(-2, os.SEEK_END)
                end = evidence_file.read(2)
        except OSError:
            return "UNREADABLE_FILE", None
        if start != b"\xff\xd8" or end != b"\xff\xd9":
            return "INVALID_JPEG", None
        return None, resolved

    def _hash_file(self, path):
        digest = hashlib.sha256()
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
        flags |= getattr(os, "O_NOFOLLOW", 0)
        descriptor = None
        try:
            descriptor = os.open(path, flags)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode):
                return "UNSAFE_PATH", None, None
            if int(metadata.st_size) > self.MAX_HASH_BYTES:
                return "FILE_TOO_LARGE", None, None
            first = b""
            last = b""
            total = 0
            while True:
                chunk = os.read(descriptor, 65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > self.MAX_HASH_BYTES:
                    return "FILE_TOO_LARGE", None, None
                if len(first) < 2:
                    first = (first + chunk)[:2]
                last = (last + chunk)[-2:]
                digest.update(chunk)
        except OSError:
            return "UNREADABLE_FILE", None, None
        finally:
            if descriptor is not None:
                os.close(descriptor)
        if first != b"\xff\xd8" or last != b"\xff\xd9":
            return "INVALID_JPEG", None, None
        return None, total, digest.hexdigest()

    @staticmethod
    def _is_within(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except (AttributeError, ValueError):
            prefix = root.rstrip(os.sep) + os.sep
            return path == root or path.startswith(prefix)
