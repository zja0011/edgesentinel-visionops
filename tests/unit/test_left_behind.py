import unittest

from packages.analytics.left_behind import LeftBehindEngine


def inventory(count=1):
    return {
        "current_counts": {"bottle": count},
        "active_track_ids": {"bottle": [7]} if count else {},
    }


def people(count):
    return {"current_people": count}


class LeftBehindEngineTests(unittest.TestCase):
    def update(self, engine, frame_id, object_count=1, people_count=0):
        return engine.update(
            inventory(object_count),
            people(people_count),
            frame_id,
            "2026-07-23T20:00:00.000+08:00",
            "camera_01",
        )

    def test_requires_consecutive_no_person_confirmation(self):
        engine = LeftBehindEngine(["bottle"], confirm_frames=2)
        snapshot, events = self.update(engine, 1)
        self.assertEqual(events, [])
        self.assertEqual(snapshot["candidate_frames"]["bottle"], 1)

        snapshot, events = self.update(engine, 2)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event_type, "OBJECT_LEFT_BEHIND")
        self.assertEqual(events[0].details["current_people"], 0)
        self.assertEqual(events[0].details["current_count"], 1)
        self.assertEqual(snapshot["alerted_classes"], ["bottle"])

    def test_does_not_alert_while_person_is_present(self):
        engine = LeftBehindEngine(["bottle"], confirm_frames=1)
        snapshot, events = self.update(engine, 1, people_count=1)

        self.assertEqual(events, [])
        self.assertEqual(snapshot["candidate_frames"], {})

    def test_does_not_duplicate_while_object_remains(self):
        engine = LeftBehindEngine(["bottle"], confirm_frames=1)
        first = self.update(engine, 1)[1]
        second = self.update(engine, 2)[1]

        self.assertEqual(len(first), 1)
        self.assertEqual(second, [])

    def test_object_removal_resets_alert(self):
        engine = LeftBehindEngine(["bottle"], confirm_frames=1)
        self.update(engine, 1)
        self.update(engine, 2, object_count=0)
        events = self.update(engine, 3)[1]

        self.assertEqual(len(events), 1)

    def test_brief_person_detection_does_not_rearm(self):
        engine = LeftBehindEngine(
            ["bottle"],
            confirm_frames=1,
            rearm_people_frames=2,
        )
        self.update(engine, 1)
        self.update(engine, 2, people_count=1)
        events = self.update(engine, 3)[1]

        self.assertEqual(events, [])

    def test_confirmed_person_return_rearms_alert(self):
        engine = LeftBehindEngine(
            ["bottle"],
            confirm_frames=1,
            rearm_people_frames=2,
        )
        self.update(engine, 1)
        self.update(engine, 2, people_count=1)
        self.update(engine, 3, people_count=1)
        events = self.update(engine, 4)[1]

        self.assertEqual(len(events), 1)


if __name__ == "__main__":
    unittest.main()
