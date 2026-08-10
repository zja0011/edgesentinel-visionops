from datetime import datetime
import os
import tempfile
import unittest

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.harness.inventory_tools import InventoryHistoryTools
from packages.vision.schemas import BEIJING_TIMEZONE


def append_event(
    store,
    event_id,
    timestamp,
    object_class="bottle",
    event_type="OBJECT_REMOVED",
    previous_count=1,
    current_count=0,
):
    store.append(
        Event(
            event_id=event_id,
            event_type=event_type,
            timestamp=timestamp,
            frame_id=10,
            camera_id="camera_01",
            zone_id="global",
            zone_name="Global Scene",
            track_id=None,
            object_class=object_class,
            evidence_path=(
                "data/evidence/{0}.jpg".format(event_id)
            ),
            details={
                "previous_count": previous_count,
                "current_count": current_count,
                "count_change": current_count - previous_count,
                "previous_track_ids": [7, 8],
                "current_track_ids": [],
            },
        )
    )


class InventoryHistoryToolsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.database_path = os.path.join(
            self.temporary.name,
            "events.db",
        )
        self.fixed_now = datetime(
            2026,
            7,
            27,
            16,
            0,
            0,
            tzinfo=BEIJING_TIMEZONE,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def create_events(self):
        store = SqliteEventStore(self.database_path)
        append_event(
            store,
            "evt_old",
            "2026-07-27T15:40:00.000+08:00",
        )
        append_event(
            store,
            "evt_bottle",
            "2026-07-27T15:55:00.000+08:00",
            previous_count=2,
            current_count=0,
        )
        append_event(
            store,
            "evt_cup",
            "2026-07-27T15:58:00.000+08:00",
            object_class="cup",
        )
        append_event(
            store,
            "evt_appeared",
            "2026-07-27T15:59:00.000+08:00",
            event_type="OBJECT_APPEARED",
            previous_count=0,
            current_count=1,
        )
        store.close()

    def build_tools(self):
        return InventoryHistoryTools(
            self.temporary.name,
            self.database_path,
            clock=lambda: self.fixed_now,
        )

    def test_returns_only_recent_confirmed_removals(self):
        self.create_events()

        result = self.build_tools().get_removed_items(
            {"minutes": 10, "limit": 20}
        )

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["total_removed_units"], 3)
        self.assertEqual(
            [item["event_id"] for item in result["removals"]],
            ["evt_cup", "evt_bottle"],
        )
        self.assertEqual(
            result["removals"][1]["removed_units"],
            2,
        )
        self.assertEqual(
            result["removals"][1]["previous_track_ids"],
            [7, 8],
        )
        self.assertIn(
            "primary",
            result["removals"][0]["evidence_urls"],
        )
        self.assertTrue(result["read_only"])

    def test_filters_exact_object_class(self):
        self.create_events()

        result = self.build_tools().get_removed_items(
            {
                "minutes": 10,
                "object_class": "bottle",
                "limit": 20,
            }
        )

        self.assertEqual(result["count"], 1)
        self.assertEqual(
            result["selected_object_class"],
            "bottle",
        )
        self.assertEqual(
            result["removed_classes"],
            [
                {
                    "class_name": "bottle",
                    "event_count": 1,
                    "removed_units": 2,
                }
            ],
        )

    def test_missing_database_fails_closed(self):
        with self.assertRaises(RuntimeError):
            self.build_tools().get_removed_items({})


if __name__ == "__main__":
    unittest.main()
