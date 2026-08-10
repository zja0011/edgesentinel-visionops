import os
import sqlite3
import tempfile
import unittest
from datetime import datetime

from packages.api.event_service import EventQueryService
from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.vision.schemas import BEIJING_TIMEZONE


def make_event(
    event_id,
    object_class="bottle",
    severity="INFO",
):
    return Event(
        event_type="OBJECT_APPEARED",
        timestamp="2026-07-24T16:00:00.000+08:00",
        frame_id=10,
        camera_id="camera_01",
        zone_id="global",
        zone_name="Global Scene",
        track_id=None,
        object_class=object_class,
        severity=severity,
        details={"previous_count": 0, "current_count": 1},
        event_id=event_id,
    )


class EventQueryServiceTests(unittest.TestCase):
    def test_health_reports_database_count(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_one"))
            store.close()

            payload = EventQueryService(path).health()

            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["database"]["status"], "ok")
            self.assertEqual(payload["database"]["event_count"], 1)
            self.assertTrue(payload["timestamp"].endswith("+08:00"))

    def test_health_is_degraded_when_database_is_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "missing.db")

            payload = EventQueryService(path).health()

            self.assertEqual(payload["status"], "degraded")
            self.assertEqual(
                payload["database"]["status"],
                "unavailable",
            )

    def test_lists_filtered_events(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_bottle", "bottle"))
            store.append(make_event("evt_cup", "cup"))
            store.close()

            payload = EventQueryService(path).list_events(
                object_class="bottle",
            )

            self.assertEqual(payload["count"], 1)
            self.assertEqual(
                payload["events"][0]["event_id"],
                "evt_bottle",
            )
            self.assertTrue(payload["read_only"])

    def test_lists_events_by_validated_disposition(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_open"))
            store.append(make_event("evt_acknowledged"))
            store.acknowledge(
                "evt_acknowledged",
                "2026-07-28T20:30:00.000+08:00",
                acknowledged_by="tester",
            )
            store.close()
            service = EventQueryService(path)

            open_payload = service.list_events(status="open")
            acknowledged = service.list_events(
                status="ACKNOWLEDGED"
            )

            self.assertEqual(open_payload["count"], 1)
            self.assertEqual(
                open_payload["events"][0]["event_id"],
                "evt_open",
            )
            self.assertEqual(
                open_payload["filters"]["status"],
                "OPEN",
            )
            self.assertEqual(acknowledged["count"], 1)
            self.assertEqual(
                acknowledged["events"][0]["event_id"],
                "evt_acknowledged",
            )

    def test_rejects_unknown_disposition_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.close()

            with self.assertRaises(ValueError):
                EventQueryService(path).list_events(
                    status="DELETED"
                )

    def test_lists_events_by_validated_severity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_info"))
            store.append(
                make_event("evt_medium", severity="MEDIUM")
            )
            store.close()

            payload = EventQueryService(path).list_events(
                severity="medium"
            )

            self.assertEqual(payload["count"], 1)
            self.assertEqual(
                payload["events"][0]["event_id"],
                "evt_medium",
            )
            self.assertEqual(
                payload["filters"]["severity"],
                "MEDIUM",
            )

    def test_rejects_unknown_severity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.close()

            with self.assertRaises(ValueError):
                EventQueryService(path).list_events(
                    severity="UNKNOWN"
                )

    def test_pages_without_duplicates_using_signed_cursor(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            for event_id in (
                "evt_a",
                "evt_b",
                "evt_c",
                "evt_d",
                "evt_e",
            ):
                store.append(make_event(event_id))
            store.close()
            service = EventQueryService(
                path,
                cursor_secret=b"fixed-test-cursor-secret",
            )

            first = service.list_events(
                limit=2,
                status="OPEN",
                severity="INFO",
            )
            second = service.list_events(
                limit=2,
                status="OPEN",
                severity="INFO",
                cursor=first["pagination"]["next_cursor"],
            )
            third = service.list_events(
                limit=2,
                status="OPEN",
                severity="INFO",
                cursor=second["pagination"]["next_cursor"],
            )

            self.assertEqual(
                [event["event_id"] for event in first["events"]],
                ["evt_e", "evt_d"],
            )
            self.assertEqual(
                [event["event_id"] for event in second["events"]],
                ["evt_c", "evt_b"],
            )
            self.assertEqual(
                [event["event_id"] for event in third["events"]],
                ["evt_a"],
            )
            self.assertTrue(first["pagination"]["has_more"])
            self.assertTrue(second["pagination"]["has_more"])
            self.assertFalse(third["pagination"]["has_more"])
            self.assertIsNone(
                third["pagination"]["next_cursor"]
            )

    def test_cursor_rejects_tampering_and_filter_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_a"))
            store.append(make_event("evt_b"))
            store.close()
            service = EventQueryService(
                path,
                cursor_secret=b"fixed-test-cursor-secret",
            )
            first = service.list_events(
                limit=1,
                object_class="bottle",
            )
            cursor = first["pagination"]["next_cursor"]
            replacement = "0" if cursor[-1] != "0" else "1"

            with self.assertRaises(ValueError):
                service.list_events(
                    limit=1,
                    object_class="bottle",
                    cursor=cursor[:-1] + replacement,
                )
            with self.assertRaises(ValueError):
                service.list_events(
                    limit=1,
                    object_class="cup",
                    cursor=cursor,
                )

    def test_cursor_reuses_original_beijing_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            for event_id in ("evt_a", "evt_b", "evt_c"):
                event = make_event(event_id)
                event.timestamp = (
                    "2026-07-28T15:59:00.000+08:00"
                )
                store.append(event)
            store.close()
            now_values = [
                datetime(
                    2026,
                    7,
                    28,
                    16,
                    0,
                    tzinfo=BEIJING_TIMEZONE,
                ),
                datetime(
                    2026,
                    7,
                    28,
                    16,
                    5,
                    tzinfo=BEIJING_TIMEZONE,
                ),
            ]
            service = EventQueryService(
                path,
                now_provider=lambda: now_values.pop(0),
                cursor_secret=b"fixed-test-cursor-secret",
            )

            first = service.list_events(limit=1, minutes=10)
            second = service.list_events(
                limit=1,
                minutes=10,
                cursor=first["pagination"]["next_cursor"],
            )

            self.assertEqual(second["window"], first["window"])
            self.assertEqual(len(now_values), 1)

    def test_lists_events_in_bounded_beijing_time_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            recent = make_event("evt_recent")
            recent.timestamp = "2026-07-28T15:55:01.000+08:00"
            old = make_event("evt_old")
            old.timestamp = "2026-07-28T15:54:59.000+08:00"
            store.append(recent)
            store.append(old)
            store.close()
            service = EventQueryService(
                path,
                now_provider=lambda: datetime(
                    2026,
                    7,
                    28,
                    16,
                    0,
                    tzinfo=BEIJING_TIMEZONE,
                ),
            )

            payload = service.list_events(minutes=5)

            self.assertEqual(payload["count"], 1)
            self.assertEqual(
                payload["events"][0]["event_id"],
                "evt_recent",
            )
            self.assertEqual(payload["window"]["minutes"], 5)
            self.assertEqual(
                payload["window"]["since_timestamp"],
                "2026-07-28T15:55:00.000+08:00",
            )
            self.assertEqual(
                payload["window"]["queried_at"],
                "2026-07-28T16:00:00.000+08:00",
            )
            self.assertEqual(
                payload["window"]["timezone"],
                "Asia/Shanghai",
            )

    def test_rejects_event_window_outside_one_day(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.close()
            service = EventQueryService(path)

            for minutes in (0, 1441):
                with self.assertRaises(ValueError):
                    service.list_events(minutes=minutes)

    def test_gets_one_event_by_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_one"))
            store.close()

            event = EventQueryService(path).get_event("evt_one")

            self.assertEqual(event["event_id"], "evt_one")
            self.assertIsNone(
                EventQueryService(path).get_event("evt_missing")
            )

    def test_read_only_store_rejects_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events.db")
            store = SqliteEventStore(path)
            store.close()
            read_only_store = SqliteEventStore(path, read_only=True)

            with self.assertRaises(sqlite3.OperationalError):
                read_only_store.append(make_event("evt_forbidden"))
            read_only_store.close()


if __name__ == "__main__":
    unittest.main()
