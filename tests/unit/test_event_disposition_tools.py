import json
import os
import tempfile
import unittest

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.harness.default_tools import build_default_registry
from packages.harness.event_tools import (
    EventAcknowledgementUnavailable,
    EventDispositionTools,
)
from packages.harness.registry import ToolInvocationError


EVENT_ID = "evt_11111111111111111111111111111111"


def create_database(path):
    store = SqliteEventStore(path)
    store.append(
        Event(
            event_type="OBJECT_REMOVED",
            timestamp="2026-07-27T10:00:00.000+08:00",
            frame_id=10,
            camera_id="camera_01",
            zone_id="global",
            zone_name="Global Scene",
            track_id=None,
            object_class="bottle",
            event_id=EVENT_ID,
        )
    )
    store.close()


class EventDispositionToolsTests(unittest.TestCase):
    def test_new_events_start_open_and_can_be_acknowledged(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            create_database(database)
            before = SqliteEventStore(
                database,
                read_only=True,
            )
            self.assertEqual(before.get(EVENT_ID)["status"], "OPEN")
            before.close()

            result = EventDispositionTools(
                database,
                clock=lambda: "2026-07-27T10:05:00.000+08:00",
            ).acknowledge({"event_id": EVENT_ID})

            self.assertEqual(result["status"], "ACKNOWLEDGED")
            self.assertFalse(result["already_acknowledged"])
            self.assertEqual(
                result["acknowledged_at"],
                "2026-07-27T10:05:00.000+08:00",
            )
            self.assertEqual(
                result["acknowledged_by"],
                "agent_operator",
            )

    def test_repeated_acknowledgement_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            create_database(database)
            first = EventDispositionTools(
                database,
                clock=lambda: "2026-07-27T10:05:00.000+08:00",
            ).acknowledge({"event_id": EVENT_ID})
            second = EventDispositionTools(
                database,
                clock=lambda: "2026-07-27T11:00:00.000+08:00",
            ).acknowledge({"event_id": EVENT_ID})

            self.assertFalse(first["already_acknowledged"])
            self.assertTrue(second["already_acknowledged"])
            self.assertEqual(
                second["acknowledged_at"],
                first["acknowledged_at"],
            )

    def test_rejects_invalid_or_unknown_event_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            create_database(database)
            tools = EventDispositionTools(database)

            with self.assertRaises(EventAcknowledgementUnavailable):
                tools.acknowledge({"event_id": "../events.db"})
            with self.assertRaises(EventAcknowledgementUnavailable):
                tools.acknowledge(
                    {
                        "event_id": (
                            "evt_22222222222222222222222222222222"
                        )
                    }
                )

    def test_registry_requires_confirmation_and_audits_result(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            audit = os.path.join(directory, "audit.jsonl")
            create_database(database)
            registry = build_default_registry(
                directory,
                database,
                audit_path=audit,
            )

            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "event.acknowledge",
                    {"event_id": EVENT_ID},
                )
            store = SqliteEventStore(database, read_only=True)
            self.assertEqual(store.get(EVENT_ID)["status"], "OPEN")
            store.close()

            completed = registry.invoke(
                "event.acknowledge",
                {"event_id": EVENT_ID},
                confirmation_granted=True,
            )

            self.assertEqual(completed["status"], "SUCCEEDED")
            self.assertEqual(
                completed["result"]["status"],
                "ACKNOWLEDGED",
            )
            with open(audit, "r", encoding="utf-8") as audit_file:
                records = [
                    json.loads(line) for line in audit_file
                ]
            self.assertEqual(len(records), 2)
            self.assertEqual(
                records[1]["result_summary"]["event_id"],
                EVENT_ID,
            )


if __name__ == "__main__":
    unittest.main()
