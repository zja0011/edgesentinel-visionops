import json
import os
import tempfile
import unittest

from packages.events.engine import ZoneEventEngine
from packages.events.schemas import Event
from packages.events.store import JsonlEventStore


def zones(track_ids):
    return [
        {
            "zone_id": "left",
            "name": "Left",
            "current_count": len(track_ids),
            "track_ids": list(track_ids),
        }
    ]


def tracks(track_ids):
    return [
        {"track_id": track_id, "class_name": "person"}
        for track_id in track_ids
    ]


class ZoneEventEngineTests(unittest.TestCase):
    def update(
        self,
        engine,
        frame_id,
        track_ids,
        monotonic_time=None,
    ):
        return engine.update(
            zones(track_ids),
            tracks(track_ids),
            frame_id,
            "2026-07-22T12:00:00.000Z",
            "camera_01",
            monotonic_time=monotonic_time,
        )

    def test_enter_requires_consecutive_confirmation(self):
        engine = ZoneEventEngine(enter_confirm_frames=3, exit_confirm_frames=2)

        self.assertEqual(self.update(engine, 1, [7]), [])
        self.assertEqual(self.update(engine, 2, [7]), [])
        events = self.update(engine, 3, [7])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "ZONE_ENTER")
        self.assertEqual(events[0].track_id, 7)

    def test_short_presence_creates_no_event(self):
        engine = ZoneEventEngine(enter_confirm_frames=3, exit_confirm_frames=2)
        self.update(engine, 1, [7])
        self.update(engine, 2, [])
        self.assertEqual(self.update(engine, 3, []), [])

    def test_short_absence_does_not_exit(self):
        engine = ZoneEventEngine(enter_confirm_frames=1, exit_confirm_frames=2)
        self.update(engine, 1, [7])
        self.assertEqual(self.update(engine, 2, []), [])
        self.assertEqual(self.update(engine, 3, [7]), [])

    def test_exit_requires_consecutive_confirmation(self):
        engine = ZoneEventEngine(enter_confirm_frames=1, exit_confirm_frames=2)
        self.update(engine, 1, [7])
        self.assertEqual(self.update(engine, 2, []), [])
        events = self.update(engine, 3, [])

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "ZONE_EXIT")
        self.assertEqual(events[0].track_id, 7)

    def test_does_not_duplicate_enter_while_track_stays_inside(self):
        engine = ZoneEventEngine(enter_confirm_frames=1, exit_confirm_frames=2)
        first = self.update(engine, 1, [7])
        second = self.update(engine, 2, [7])
        third = self.update(engine, 3, [7])

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])
        self.assertEqual(third, [])

    def test_dwell_uses_elapsed_seconds_and_emits_once(self):
        engine = ZoneEventEngine(
            enter_confirm_frames=1,
            exit_confirm_frames=2,
            dwell_seconds=10,
        )

        entered = self.update(engine, 1, [7], 100.0)
        before = self.update(engine, 2, [7], 109.9)
        dwell = self.update(engine, 3, [7], 110.0)
        repeated = self.update(engine, 4, [7], 130.0)

        self.assertEqual(entered[0].event_type, "ZONE_ENTER")
        self.assertEqual(before, [])
        self.assertEqual(len(dwell), 1)
        self.assertEqual(dwell[0].event_type, "ZONE_DWELL")
        self.assertEqual(dwell[0].severity, "MEDIUM")
        self.assertEqual(
            dwell[0].details["dwell_seconds_threshold"],
            10.0,
        )
        self.assertEqual(
            dwell[0].details["observed_dwell_seconds"],
            10.0,
        )
        self.assertEqual(dwell[0].details["entered_frame_id"], 1)
        self.assertEqual(repeated, [])

    def test_short_absence_does_not_reset_dwell_timer(self):
        engine = ZoneEventEngine(
            enter_confirm_frames=1,
            exit_confirm_frames=2,
            dwell_seconds=10,
        )

        self.update(engine, 1, [7], 100.0)
        self.assertEqual(
            self.update(engine, 2, [], 105.0),
            [],
        )
        events = self.update(engine, 3, [7], 110.0)

        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "ZONE_DWELL")

    def test_exit_and_reentry_rearm_dwell(self):
        engine = ZoneEventEngine(
            enter_confirm_frames=1,
            exit_confirm_frames=2,
            dwell_seconds=5,
        )

        self.update(engine, 1, [7], 100.0)
        first_dwell = self.update(engine, 2, [7], 105.0)
        self.update(engine, 3, [], 106.0)
        exited = self.update(engine, 4, [], 107.0)
        reentered = self.update(engine, 5, [7], 110.0)
        second_dwell = self.update(engine, 6, [7], 115.0)

        self.assertEqual(first_dwell[0].event_type, "ZONE_DWELL")
        self.assertEqual(exited[0].event_type, "ZONE_EXIT")
        self.assertEqual(reentered[0].event_type, "ZONE_ENTER")
        self.assertEqual(second_dwell[0].event_type, "ZONE_DWELL")
        self.assertNotEqual(
            first_dwell[0].event_id,
            second_dwell[0].event_id,
        )

    def test_rejects_negative_dwell_threshold(self):
        with self.assertRaises(ValueError):
            ZoneEventEngine(dwell_seconds=-1)


class EventStoreTests(unittest.TestCase):
    def test_appends_json_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "events", "events.jsonl")
            store = JsonlEventStore(path)
            event = Event(
                "ZONE_ENTER",
                "2026-07-22T12:00:00.000Z",
                10,
                "camera_01",
                "left",
                "Left",
                7,
                "person",
                event_id="evt_test",
            )
            store.append(event)
            store.close()

            with open(path, "r", encoding="utf-8") as event_file:
                payload = json.loads(event_file.readline())
            self.assertEqual(payload["event_id"], "evt_test")
            self.assertEqual(payload["event_type"], "ZONE_ENTER")
            self.assertIsNone(payload["evidence_path"])


if __name__ == "__main__":
    unittest.main()
