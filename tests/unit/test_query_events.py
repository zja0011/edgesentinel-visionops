import unittest

from apps.query_events import format_event


class QueryEventsTests(unittest.TestCase):
    def test_formats_aggregate_inventory_event(self):
        event = {
            "timestamp": "2026-07-23T12:00:00.000Z",
            "event_type": "OBJECT_REMOVED",
            "object_class": "bottle",
            "zone_id": "global",
            "track_id": None,
            "details": {"previous_count": 1, "current_count": 0},
        }

        self.assertEqual(
            format_event(event),
            (
                "2026-07-23T12:00:00.000Z OBJECT_REMOVED "
                "bottle 1->0 zone=global track=aggregate"
            ),
        )

    def test_formats_tracked_zone_event(self):
        event = {
            "timestamp": "2026-07-23T12:00:00.000Z",
            "event_type": "ZONE_ENTER",
            "object_class": "person",
            "zone_id": "left_zone",
            "track_id": 7,
            "details": {"confirmation_frames": 15},
        }

        self.assertEqual(
            format_event(event),
            (
                "2026-07-23T12:00:00.000Z ZONE_ENTER "
                "person zone=left_zone track=7"
            ),
        )


if __name__ == "__main__":
    unittest.main()
