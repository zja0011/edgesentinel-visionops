"""Dependency-free service layer for the read-only event API."""

import base64
import hashlib
import hmac
import json
import os
import sqlite3
from datetime import datetime, timedelta

from packages.events.sqlite_store import SqliteEventStore
from packages.vision.schemas import (
    BEIJING_TIMEZONE,
    beijing_timestamp,
)


class EventDatabaseUnavailable(RuntimeError):
    """Raised when the event database cannot be queried."""


class EventQueryService(object):
    API_SCHEMA_VERSION = "1.0"
    SERVICE_NAME = "edgesentinel-visionops"
    VALID_STATUSES = ("OPEN", "ACKNOWLEDGED")
    VALID_SEVERITIES = ("INFO", "MEDIUM", "HIGH", "CRITICAL")

    def __init__(
        self,
        database_path,
        now_provider=None,
        cursor_secret=None,
    ):
        self.database_path = os.path.abspath(database_path)
        self.now_provider = now_provider or (
            lambda: datetime.now(BEIJING_TIMEZONE)
        )
        self._cursor_secret = cursor_secret or os.urandom(32)

    def health(self):
        try:
            store = self._open_store()
            try:
                event_count = store.count()
            finally:
                store.close()
        except (EventDatabaseUnavailable, sqlite3.Error):
            return {
                "schema_version": self.API_SCHEMA_VERSION,
                "service": self.SERVICE_NAME,
                "status": "degraded",
                "timestamp": beijing_timestamp(),
                "database": {
                    "status": "unavailable",
                    "event_count": None,
                },
            }

        return {
            "schema_version": self.API_SCHEMA_VERSION,
            "service": self.SERVICE_NAME,
            "status": "ok",
            "timestamp": beijing_timestamp(),
            "database": {
                "status": "ok",
                "event_count": event_count,
            },
        }

    def list_events(
        self,
        limit=20,
        event_type=None,
        object_class=None,
        camera_id=None,
        minutes=None,
        status=None,
        severity=None,
        cursor=None,
    ):
        limit = int(limit)
        if limit < 1 or limit > 100:
            raise ValueError("limit must be between 1 and 100")
        status = self._validate_status(status)
        severity = self._validate_severity(severity)
        filters = {
            "event_type": self._optional_text(event_type),
            "object_class": self._optional_text(object_class),
            "camera_id": self._optional_text(camera_id),
            "status": status,
            "severity": severity,
            "minutes": self._validate_minutes(minutes),
        }
        before = None
        if cursor is not None and str(cursor).strip() != "":
            cursor_state = self._decode_cursor(str(cursor).strip())
            if cursor_state["filters"] != filters:
                raise ValueError(
                    "cursor does not match current event filters"
                )
            window = cursor_state["window"]
            before = cursor_state["sort"]
        else:
            window = self._query_window(filters["minutes"])
        try:
            store = self._open_store()
            try:
                events = store.query(
                    limit=limit + 1,
                    event_type=filters["event_type"],
                    object_class=filters["object_class"],
                    camera_id=filters["camera_id"],
                    status=status,
                    severity=severity,
                    before=before,
                    since_timestamp=(
                        window["since_timestamp"]
                        if window is not None
                        else None
                    ),
                )
            finally:
                store.close()
        except sqlite3.Error as error:
            raise EventDatabaseUnavailable(
                "event database is unavailable"
            ) from error

        has_more = len(events) > limit
        events = events[:limit]
        next_cursor = None
        if has_more and events:
            last_event = events[-1]
            next_cursor = self._encode_cursor(
                {
                    "version": 1,
                    "filters": filters,
                    "window": window,
                    "sort": [
                        last_event["timestamp"],
                        int(last_event["frame_id"]),
                        last_event["event_id"],
                    ],
                }
            )

        payload = {
            "schema_version": self.API_SCHEMA_VERSION,
            "count": len(events),
            "events": events,
            "read_only": True,
            "pagination": {
                "order": (
                    "timestamp_desc,frame_id_desc,event_id_desc"
                ),
                "has_more": has_more,
                "next_cursor": next_cursor,
            },
        }
        if window is not None:
            payload["window"] = window
        payload["filters"] = {
            "event_type": filters["event_type"],
            "object_class": filters["object_class"],
            "camera_id": filters["camera_id"],
            "status": status,
            "severity": severity,
        }
        return payload

    def get_event(self, event_id):
        try:
            store = self._open_store()
            try:
                return store.get(event_id)
            finally:
                store.close()
        except sqlite3.Error as error:
            raise EventDatabaseUnavailable(
                "event database is unavailable"
            ) from error

    def _open_store(self):
        try:
            return SqliteEventStore(
                self.database_path,
                read_only=True,
            )
        except (OSError, sqlite3.Error) as error:
            raise EventDatabaseUnavailable(
                "event database is unavailable"
            ) from error

    def _query_window(self, minutes):
        if minutes is None:
            return None
        queried_at = self.now_provider()
        if queried_at.tzinfo is None:
            queried_at = queried_at.replace(
                tzinfo=BEIJING_TIMEZONE
            )
        queried_at = queried_at.astimezone(BEIJING_TIMEZONE)
        since = queried_at - timedelta(minutes=minutes)
        return {
            "minutes": minutes,
            "since_timestamp": self._format_timestamp(since),
            "queried_at": self._format_timestamp(queried_at),
            "timezone": "Asia/Shanghai",
        }

    def _validate_status(self, status):
        if status is None or str(status).strip() == "":
            return None
        normalized = str(status).strip().upper()
        if normalized not in self.VALID_STATUSES:
            raise ValueError(
                "status must be OPEN or ACKNOWLEDGED"
            )
        return normalized

    @staticmethod
    def _optional_text(value):
        if value is None or str(value).strip() == "":
            return None
        return str(value).strip()

    @staticmethod
    def _validate_minutes(minutes):
        if minutes is None or str(minutes).strip() == "":
            return None
        minutes = int(minutes)
        if minutes < 1 or minutes > 1440:
            raise ValueError(
                "minutes must be between 1 and 1440"
            )
        return minutes

    def _encode_cursor(self, state):
        raw = json.dumps(
            state,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        payload = base64.urlsafe_b64encode(raw).decode(
            "ascii"
        ).rstrip("=")
        signature = hmac.new(
            self._cursor_secret,
            payload.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        return payload + "." + signature

    def _decode_cursor(self, cursor):
        if len(cursor) > 2048 or cursor.count(".") != 1:
            raise ValueError("invalid event cursor")
        payload, signature = cursor.split(".", 1)
        try:
            payload_bytes = payload.encode("ascii")
        except UnicodeError:
            raise ValueError("invalid event cursor")
        expected = hmac.new(
            self._cursor_secret,
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("invalid event cursor")
        try:
            padding = "=" * (-len(payload) % 4)
            decoded = base64.urlsafe_b64decode(
                payload_bytes + padding.encode("ascii")
            )
            state = json.loads(decoded.decode("ascii"))
        except (TypeError, ValueError, UnicodeError):
            raise ValueError("invalid event cursor")
        if (
            not isinstance(state, dict)
            or state.get("version") != 1
            or not isinstance(state.get("filters"), dict)
            or not isinstance(state.get("sort"), list)
            or len(state["sort"]) != 3
            or not isinstance(state["sort"][0], str)
            or not isinstance(state["sort"][1], int)
            or not isinstance(state["sort"][2], str)
            or (
                state.get("window") is not None
                and not isinstance(state.get("window"), dict)
            )
        ):
            raise ValueError("invalid event cursor")
        return state

    def _validate_severity(self, severity):
        if severity is None or str(severity).strip() == "":
            return None
        normalized = str(severity).strip().upper()
        if normalized not in self.VALID_SEVERITIES:
            raise ValueError(
                "severity must be INFO, MEDIUM, HIGH, or CRITICAL"
            )
        return normalized

    @staticmethod
    def _format_timestamp(value):
        return (
            value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "+08:00"
        )
