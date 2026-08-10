import os
import sqlite3
import tempfile
import unittest

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore


def make_event(
    event_id,
    event_type="OBJECT_APPEARED",
    object_class="bottle",
    timestamp="2026-07-23T12:00:00.000Z",
    severity="INFO",
):
    return Event(
        event_type=event_type,
        timestamp=timestamp,
        frame_id=10,
        camera_id="camera_01",
        zone_id="global",
        zone_name="Global Scene",
        track_id=None,
        object_class=object_class,
        severity=severity,
        details={"previous_count": 0, "current_count": 1},
        event_id=event_id,
        evidence_path="/data/evidence/{0}.jpg".format(event_id),
    )


class SqliteEventStoreTests(unittest.TestCase):
    def test_migrates_legacy_event_table_without_replacing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            connection = sqlite3.connect(path)
            connection.execute(
                """
                CREATE TABLE events (
                    event_id TEXT PRIMARY KEY,
                    schema_version TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    frame_id INTEGER NOT NULL,
                    camera_id TEXT NOT NULL,
                    zone_id TEXT NOT NULL,
                    zone_name TEXT NOT NULL,
                    track_id INTEGER,
                    object_class TEXT NOT NULL,
                    evidence_path TEXT,
                    details_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                INSERT INTO events VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "evt_legacy",
                    "1.2",
                    "ZONE_ENTER",
                    "INFO",
                    "2026-07-27T10:00:00.000+08:00",
                    1,
                    "camera_01",
                    "left_zone",
                    "Left Zone",
                    2,
                    "person",
                    None,
                    "{}",
                ),
            )
            connection.commit()
            connection.close()

            store = SqliteEventStore(path)
            event = store.get("evt_legacy")
            columns = {
                row["name"]
                for row in store._connection.execute(
                    "PRAGMA table_info(events)"
                ).fetchall()
            }
            store.close()

            self.assertEqual(event["status"], "OPEN")
            self.assertIsNone(event["acknowledged_at"])
            self.assertTrue(
                {
                    "status",
                    "acknowledged_at",
                    "acknowledged_by",
                }.issubset(columns)
            )

    def test_appends_and_queries_structured_event(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events", "edgesentinel.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_one"))

            events = store.query()
            store.close()

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_id"], "evt_one")
            self.assertIsNone(events[0]["track_id"])
            self.assertEqual(
                events[0]["details"],
                {"previous_count": 0, "current_count": 1},
            )
            self.assertEqual(events[0]["status"], "OPEN")
            self.assertIsNone(events[0]["acknowledged_at"])

    def test_query_filters_and_orders_newest_first(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            store = SqliteEventStore(path)
            store.append(
                make_event(
                    "evt_old",
                    object_class="cup",
                    timestamp="2026-07-23T12:00:00.000Z",
                )
            )
            store.append(
                make_event(
                    "evt_new",
                    event_type="OBJECT_REMOVED",
                    object_class="bottle",
                    timestamp="2026-07-23T12:01:00.000Z",
                )
            )

            events = store.query(
                event_type="OBJECT_REMOVED",
                object_class="bottle",
            )
            store.close()

            self.assertEqual(
                [event["event_id"] for event in events],
                ["evt_new"],
            )

    def test_query_filters_by_iso_timestamp_window(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            store = SqliteEventStore(path)
            store.append(
                make_event(
                    "evt_before",
                    event_type="OBJECT_REMOVED",
                    timestamp="2026-07-27T15:49:59.000+08:00",
                )
            )
            store.append(
                make_event(
                    "evt_inside",
                    event_type="OBJECT_REMOVED",
                    timestamp="2026-07-27T15:50:01.000+08:00",
                )
            )

            events = store.query(
                event_type="OBJECT_REMOVED",
                since_timestamp=(
                    "2026-07-27T15:50:00.000+08:00"
                ),
            )
            store.close()

            self.assertEqual(
                [event["event_id"] for event in events],
                ["evt_inside"],
            )

    def test_query_filters_exact_disposition_status(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_open"))
            store.append(make_event("evt_acknowledged"))
            store.acknowledge(
                "evt_acknowledged",
                "2026-07-28T20:30:00.000+08:00",
                acknowledged_by="tester",
            )

            open_events = store.query(status="OPEN")
            acknowledged = store.query(
                status="ACKNOWLEDGED"
            )
            store.close()

            self.assertEqual(
                [event["event_id"] for event in open_events],
                ["evt_open"],
            )
            self.assertEqual(
                [event["event_id"] for event in acknowledged],
                ["evt_acknowledged"],
            )

    def test_query_filters_exact_severity(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_info"))
            store.append(
                make_event("evt_medium", severity="MEDIUM")
            )

            events = store.query(severity="MEDIUM")
            store.close()

            self.assertEqual(
                [event["event_id"] for event in events],
                ["evt_medium"],
            )

    def test_query_uses_stable_three_field_cursor_order(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            store = SqliteEventStore(path)
            for event_id in ("evt_a", "evt_b", "evt_c"):
                store.append(make_event(event_id))

            first = store.query(limit=2)
            second = store.query(
                limit=2,
                before=(
                    first[-1]["timestamp"],
                    first[-1]["frame_id"],
                    first[-1]["event_id"],
                ),
            )
            store.close()

            self.assertEqual(
                [event["event_id"] for event in first],
                ["evt_c", "evt_b"],
            )
            self.assertEqual(
                [event["event_id"] for event in second],
                ["evt_a"],
            )

    def test_duplicate_event_id_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_duplicate"))

            with self.assertRaises(sqlite3.IntegrityError):
                store.append(make_event("evt_duplicate"))
            store.close()

    def test_counts_selected_event_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            store = SqliteEventStore(path)
            store.append(make_event("evt_one"))
            store.append(make_event("evt_two"))

            self.assertEqual(
                store.count_event_ids(["evt_two", "missing"]),
                1,
            )
            self.assertEqual(store.count_event_ids([]), 0)
            store.close()

    def test_queries_one_beijing_calendar_day(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "edgesentinel.db")
            store = SqliteEventStore(path)
            store.append(
                make_event(
                    "evt_day",
                    timestamp="2026-07-27T00:00:01.000+08:00",
                )
            )
            store.append(
                make_event(
                    "evt_other_day",
                    timestamp="2026-07-26T23:59:59.000+08:00",
                )
            )

            events = store.query_day("2026-07-27")
            store.close()

            self.assertEqual(
                [event["event_id"] for event in events],
                ["evt_day"],
            )


if __name__ == "__main__":
    unittest.main()
