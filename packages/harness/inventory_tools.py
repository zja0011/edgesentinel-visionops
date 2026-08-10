"""Read-only inventory history tools backed by the local event store."""

from datetime import datetime, timedelta
import os
import sqlite3

from packages.api.evidence_service import EvidenceService
from packages.events.sqlite_store import SqliteEventStore
from packages.vision.schemas import BEIJING_TIMEZONE


class InventoryHistoryTools(object):
    def __init__(self, project_dir, database_path, clock=None):
        self.project_dir = os.path.abspath(project_dir)
        self.database_path = os.path.abspath(database_path)
        self.evidence_service = EvidenceService(self.project_dir)
        self.clock = clock or (
            lambda: datetime.now(BEIJING_TIMEZONE)
        )

    def get_removed_items(self, arguments):
        arguments = arguments or {}
        minutes = int(arguments.get("minutes", 10))
        limit = int(arguments.get("limit", 20))
        if minutes < 1 or minutes > 1440:
            raise ValueError(
                "minutes must be between 1 and 1440"
            )
        if limit < 1 or limit > 50:
            raise ValueError("limit must be between 1 and 50")

        queried_at_value = self.clock()
        if queried_at_value.tzinfo is None:
            queried_at_value = queried_at_value.replace(
                tzinfo=BEIJING_TIMEZONE
            )
        queried_at_value = queried_at_value.astimezone(
            BEIJING_TIMEZONE
        )
        since_value = queried_at_value - timedelta(minutes=minutes)
        queried_at = self._timestamp(queried_at_value)
        since_timestamp = self._timestamp(since_value)

        try:
            store = SqliteEventStore(
                self.database_path,
                read_only=True,
            )
            try:
                events = store.query(
                    limit=limit,
                    event_type="OBJECT_REMOVED",
                    object_class=arguments.get("object_class"),
                    camera_id=arguments.get("camera_id"),
                    since_timestamp=since_timestamp,
                )
            finally:
                store.close()
        except (OSError, sqlite3.Error) as error:
            raise RuntimeError(
                "inventory event database is unavailable"
            ) from error

        removals = []
        summary = {}
        for event in events:
            details = event.get("details") or {}
            previous_count = self._integer(
                details.get("previous_count"),
                0,
            )
            current_count = self._integer(
                details.get("current_count"),
                0,
            )
            count_change = self._integer(
                details.get("count_change"),
                current_count - previous_count,
            )
            removed_units = max(
                1,
                previous_count - current_count,
                -count_change,
            )
            previous_track_ids = self._track_ids(
                details.get("previous_track_ids")
            )
            current_track_ids = self._track_ids(
                details.get("current_track_ids")
            )
            event_with_urls = self.evidence_service.add_urls(event)
            object_class = str(
                event.get("object_class") or "unknown"
            )
            aggregate = summary.setdefault(
                object_class,
                {"event_count": 0, "removed_units": 0},
            )
            aggregate["event_count"] += 1
            aggregate["removed_units"] += removed_units
            removals.append(
                {
                    "event_id": event.get("event_id"),
                    "timestamp": event.get("timestamp"),
                    "camera_id": event.get("camera_id"),
                    "zone_id": event.get("zone_id"),
                    "zone_name": event.get("zone_name"),
                    "object_class": object_class,
                    "previous_count": previous_count,
                    "current_count": current_count,
                    "count_change": count_change,
                    "removed_units": removed_units,
                    "previous_track_ids": previous_track_ids,
                    "current_track_ids": current_track_ids,
                    "disposition_status": event.get("status"),
                    "evidence_urls": dict(
                        event_with_urls.get("evidence_urls") or {}
                    ),
                }
            )

        removed_classes = [
            {
                "class_name": class_name,
                "event_count": summary[class_name]["event_count"],
                "removed_units": summary[class_name][
                    "removed_units"
                ],
            }
            for class_name in sorted(summary)
        ]
        return {
            "queried_at": queried_at,
            "since_timestamp": since_timestamp,
            "window_minutes": minutes,
            "selected_object_class": arguments.get("object_class"),
            "selected_camera_id": arguments.get("camera_id"),
            "count": len(removals),
            "total_removed_units": sum(
                item["removed_units"] for item in removals
            ),
            "removed_classes": removed_classes,
            "removals": removals,
            "read_only": True,
        }

    @staticmethod
    def _timestamp(value):
        return (
            value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "+08:00"
        )

    @staticmethod
    def _integer(value, default):
        try:
            return int(value)
        except (TypeError, ValueError):
            return int(default)

    @staticmethod
    def _track_ids(values):
        result = []
        for value in values or []:
            try:
                track_id = int(value)
            except (TypeError, ValueError):
                continue
            if track_id not in result:
                result.append(track_id)
        return sorted(result)[:100]
