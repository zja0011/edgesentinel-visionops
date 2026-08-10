import json
import os
import tempfile
import unittest

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.harness.default_tools import build_default_registry
from packages.harness.event_detail_tools import (
    EventDetailTools,
    EventDetailUnavailable,
)


EVENT_ID = "evt_44444444444444444444444444444444"


def create_database(path):
    store = SqliteEventStore(path)
    store.append(
        Event(
            event_type="OBJECT_REMOVED",
            timestamp="2026-07-27T15:00:00.000+08:00",
            frame_id=50,
            camera_id="camera_01",
            zone_id="global",
            zone_name="Global Scene",
            track_id=None,
            object_class="bottle",
            evidence_path="data/evidence/removed_after.jpg",
            details={
                "previous_count": 1,
                "current_count": 0,
                "before_evidence_path": (
                    "data/evidence/removed_before.jpg"
                ),
            },
            event_id=EVENT_ID,
        )
    )
    store.close()


class EventDetailToolsTests(unittest.TestCase):
    def test_reads_one_exact_event_without_modifying_it(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            create_database(database)

            result = EventDetailTools(
                directory,
                database,
            ).get_detail({"event_id": EVENT_ID})

            self.assertEqual(result["event_id"], EVENT_ID)
            self.assertEqual(result["event_type"], "OBJECT_REMOVED")
            self.assertEqual(result["status"], "OPEN")
            self.assertTrue(result["read_only"])
            self.assertEqual(
                set(result["evidence_urls"]),
                {"primary", "before"},
            )
            store = SqliteEventStore(database, read_only=True)
            self.assertEqual(store.get(EVENT_ID)["status"], "OPEN")
            store.close()

    def test_rejects_invalid_and_unknown_event_ids(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            create_database(database)
            tools = EventDetailTools(directory, database)

            with self.assertRaises(EventDetailUnavailable):
                tools.get_detail({"event_id": "../events.db"})
            with self.assertRaises(EventDetailUnavailable):
                tools.get_detail(
                    {
                        "event_id": (
                            "evt_55555555555555555555555555555555"
                        )
                    }
                )

    def test_registry_exposes_l0_tool_and_audits_bounded_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            audit_path = os.path.join(directory, "audit.jsonl")
            create_database(database)
            registry = build_default_registry(
                directory,
                database,
                audit_path=audit_path,
            )
            schemas = {
                item["name"]: item
                for item in registry.schemas()
            }
            annotations = schemas["event.get_detail"]["annotations"]

            self.assertTrue(annotations["readOnlyHint"])
            self.assertEqual(annotations["riskLevel"], "L0")
            self.assertTrue(annotations["autoExecute"])
            self.assertFalse(annotations["requiresConfirmation"])
            response = registry.invoke(
                "event.get_detail",
                {"event_id": EVENT_ID},
            )
            self.assertEqual(response["status"], "SUCCEEDED")
            with open(
                audit_path,
                "r",
                encoding="utf-8",
            ) as audit_file:
                record = json.loads(audit_file.readline())
            self.assertEqual(
                record["result_summary"]["event_id"],
                EVENT_ID,
            )
            self.assertTrue(
                record["result_summary"]["has_evidence"]
            )


if __name__ == "__main__":
    unittest.main()
