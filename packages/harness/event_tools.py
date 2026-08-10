"""Confirmation-gated event disposition tools."""

import os
import re
import sqlite3

from packages.events.sqlite_store import SqliteEventStore
from packages.vision.schemas import beijing_timestamp


EVENT_ID_PATTERN = re.compile(r"^evt_[0-9a-f]{32}$")


class EventAcknowledgementUnavailable(RuntimeError):
    """Raised when an event cannot be acknowledged safely."""


class EventDispositionTools(object):
    def __init__(self, database_path, clock=None):
        self.database_path = os.path.abspath(database_path)
        self.clock = clock or beijing_timestamp

    def acknowledge(self, arguments):
        event_id = str(arguments.get("event_id") or "").lower()
        if not EVENT_ID_PATTERN.match(event_id):
            raise EventAcknowledgementUnavailable(
                "event_id must be evt_ followed by 32 hex characters"
            )
        acknowledged_at = self.clock()
        try:
            store = SqliteEventStore(self.database_path)
            try:
                event = store.acknowledge(
                    event_id,
                    acknowledged_at,
                    acknowledged_by="agent_operator",
                )
            finally:
                store.close()
        except (OSError, sqlite3.Error) as error:
            raise EventAcknowledgementUnavailable(
                "event database is unavailable"
            ) from error
        if event is None:
            raise EventAcknowledgementUnavailable(
                "event does not exist"
            )
        return {
            "schema_version": "1.0",
            "event_id": event["event_id"],
            "event_type": event["event_type"],
            "object_class": event["object_class"],
            "status": event["status"],
            "acknowledged_at": event["acknowledged_at"],
            "acknowledged_by": event["acknowledged_by"],
            "already_acknowledged": bool(
                event["already_acknowledged"]
            ),
        }
