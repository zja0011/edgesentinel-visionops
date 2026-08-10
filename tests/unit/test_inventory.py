import unittest

from packages.analytics.inventory import InventoryEngine


def track(
    track_id,
    class_name,
    hits=3,
    missed_frames=0,
):
    return {
        "track_id": track_id,
        "class_name": class_name,
        "hits": hits,
        "missed_frames": missed_frames,
    }


class InventoryEngineTests(unittest.TestCase):
    def update(self, engine, frame_id, tracks):
        return engine.update(
            tracks,
            frame_id,
            "2026-07-23T12:00:00.000Z",
            "camera_01",
        )

    def test_appearance_requires_consecutive_confirmation(self):
        engine = InventoryEngine(["bottle"], appear_confirm_frames=2)

        snapshot, events = self.update(engine, 1, [track(7, "bottle")])
        self.assertEqual(snapshot["current_counts"]["bottle"], 0)
        self.assertEqual(events, [])

        snapshot, events = self.update(engine, 2, [track(7, "bottle")])
        self.assertEqual(snapshot["current_counts"]["bottle"], 1)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "OBJECT_APPEARED")
        self.assertEqual(events[0].details["previous_count"], 0)
        self.assertEqual(events[0].details["current_count"], 1)
        self.assertIsNone(events[0].to_dict()["track_id"])
        self.assertEqual(events[0].to_dict()["schema_version"], "1.2")

    def test_short_appearance_does_not_change_inventory(self):
        engine = InventoryEngine(["bottle"], appear_confirm_frames=2)
        self.update(engine, 1, [track(7, "bottle")])
        snapshot, events = self.update(engine, 2, [])

        self.assertEqual(snapshot["current_counts"]["bottle"], 0)
        self.assertEqual(events, [])

    def test_removal_requires_consecutive_confirmation(self):
        engine = InventoryEngine(
            ["bottle"],
            appear_confirm_frames=1,
            remove_confirm_frames=2,
        )
        self.update(engine, 1, [track(7, "bottle")])
        snapshot, events = self.update(engine, 2, [])
        self.assertEqual(snapshot["current_counts"]["bottle"], 1)
        self.assertEqual(events, [])

        snapshot, events = self.update(engine, 3, [])
        self.assertEqual(snapshot["current_counts"]["bottle"], 0)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "OBJECT_REMOVED")
        self.assertEqual(events[0].details["previous_track_ids"], [7])

    def test_short_miss_does_not_generate_removal(self):
        engine = InventoryEngine(
            ["bottle"],
            appear_confirm_frames=1,
            remove_confirm_frames=2,
        )
        self.update(engine, 1, [track(7, "bottle")])
        self.update(engine, 2, [])
        snapshot, events = self.update(engine, 3, [track(7, "bottle")])

        self.assertEqual(snapshot["current_counts"]["bottle"], 1)
        self.assertEqual(events, [])

    def test_ignores_people_unconfirmed_and_missed_tracks(self):
        engine = InventoryEngine(["bottle"], appear_confirm_frames=1)
        snapshot, events = self.update(
            engine,
            1,
            [
                track(1, "person"),
                track(2, "bottle", hits=2),
                track(3, "bottle", missed_frames=1),
            ],
        )

        self.assertEqual(snapshot["visible_counts"]["bottle"], 0)
        self.assertEqual(events, [])

    def test_id_switch_with_same_count_does_not_generate_event(self):
        engine = InventoryEngine(["bottle"], appear_confirm_frames=1)
        self.update(engine, 1, [track(7, "bottle")])
        snapshot, events = self.update(engine, 2, [track(9, "bottle")])

        self.assertEqual(snapshot["current_counts"]["bottle"], 1)
        self.assertEqual(events, [])
        self.assertEqual(snapshot["active_track_ids"]["bottle"], [9])


if __name__ == "__main__":
    unittest.main()
