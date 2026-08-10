import json
import os
import tempfile
import unittest

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.monitoring.camera_events import (
    CameraLifecycleEvents,
    CameraLifecycleEventWriter,
)


def supervisor_state(
    timestamp,
    frame_id=0,
    generation=1,
    restart_count=0,
):
    return {
        "updated_at": timestamp,
        "device": "/dev/video0",
        "generation": generation,
        "restart_count": restart_count,
        "last_exit_code": None,
        "vision": {"frame_id": frame_id},
    }


class MemoryWriter(object):
    def __init__(self):
        self.events = []

    def append(self, event):
        payload = event.to_dict()
        if not any(
            item["event_id"] == payload["event_id"]
            for item in self.events
        ):
            self.events.append(payload)
        return payload


class CameraLifecycleEventTests(unittest.TestCase):
    def test_emits_one_linked_event_pair_per_outage(self):
        writer = MemoryWriter()
        clock_values = iter((100.0, 112.5, 200.0, 204.0))
        lifecycle = CameraLifecycleEvents(
            writer,
            clock=lambda: next(clock_values),
        )

        lifecycle.on_status(
            "WAITING_FOR_CAMERA",
            supervisor_state("startup"),
        )
        lifecycle.on_status(
            "RUNNING",
            supervisor_state("running", frame_id=10),
        )
        lifecycle.on_status(
            "CAMERA_OFFLINE",
            supervisor_state("offline", frame_id=10),
        )
        lifecycle.on_status(
            "RESTARTING",
            supervisor_state("retrying", frame_id=10),
        )
        lifecycle.on_status(
            "WAITING_FOR_CAMERA",
            supervisor_state("waiting", frame_id=10),
        )
        lifecycle.on_status(
            "RUNNING",
            supervisor_state(
                "recovered",
                frame_id=20,
                generation=2,
                restart_count=1,
            ),
        )
        lifecycle.on_status(
            "RUNNING",
            supervisor_state("still-running", frame_id=21),
        )

        self.assertEqual(len(writer.events), 2)
        offline, recovered = writer.events
        self.assertEqual(offline["event_type"], "CAMERA_OFFLINE")
        self.assertEqual(offline["severity"], "HIGH")
        self.assertEqual(offline["object_class"], "camera")
        self.assertEqual(
            recovered["event_type"],
            "CAMERA_RECOVERED",
        )
        self.assertEqual(recovered["severity"], "INFO")
        self.assertEqual(
            recovered["details"]["offline_event_id"],
            offline["event_id"],
        )
        self.assertEqual(
            recovered["details"]["outage_duration_seconds"],
            12.5,
        )

        lifecycle.on_status(
            "VISION_STALLED",
            supervisor_state("offline-2", frame_id=21),
        )
        lifecycle.on_status(
            "RUNNING",
            supervisor_state(
                "recovered-2",
                frame_id=30,
                generation=3,
                restart_count=2,
            ),
        )
        self.assertEqual(len(writer.events), 4)
        self.assertNotEqual(
            writer.events[0]["event_id"],
            writer.events[2]["event_id"],
        )

    def test_persists_idempotently_to_jsonl_and_sqlite(self):
        with tempfile.TemporaryDirectory() as directory:
            jsonl_path = os.path.join(directory, "events.jsonl")
            database_path = os.path.join(directory, "events.db")
            writer = CameraLifecycleEventWriter(
                jsonl_path,
                database_path,
            )
            lifecycle = CameraLifecycleEvents(
                writer,
                clock=iter((10.0, 15.0)).__next__,
            )

            lifecycle.on_status(
                "RUNNING",
                supervisor_state("running", frame_id=1),
            )
            offline_payload = lifecycle.on_status(
                "CAMERA_OFFLINE",
                supervisor_state("offline", frame_id=2),
            )
            lifecycle.on_status(
                "RUNNING",
                supervisor_state("recovered", frame_id=3),
            )
            writer.append(
                Event(
                    event_type=offline_payload["event_type"],
                    severity=offline_payload["severity"],
                    timestamp=offline_payload["timestamp"],
                    frame_id=offline_payload["frame_id"],
                    camera_id=offline_payload["camera_id"],
                    zone_id=offline_payload["zone_id"],
                    zone_name=offline_payload["zone_name"],
                    track_id=offline_payload["track_id"],
                    object_class=offline_payload["object_class"],
                    details=offline_payload["details"],
                    event_id=offline_payload["event_id"],
                )
            )

            with open(
                jsonl_path,
                "r",
                encoding="utf-8",
            ) as event_file:
                jsonl_events = [
                    json.loads(line) for line in event_file
                ]
            store = SqliteEventStore(
                database_path,
                read_only=True,
            )
            try:
                sqlite_events = store.query(
                    object_class="camera",
                    limit=10,
                )
            finally:
                store.close()

            self.assertEqual(len(jsonl_events), 2)
            self.assertEqual(len(sqlite_events), 2)
            self.assertEqual(
                {
                    event["event_type"]
                    for event in sqlite_events
                },
                {"CAMERA_OFFLINE", "CAMERA_RECOVERED"},
            )

    def test_retries_a_transient_persistence_failure(self):
        class FlakyWriter(MemoryWriter):
            def __init__(self):
                super(FlakyWriter, self).__init__()
                self.failures_remaining = 1

            def append(self, event):
                if self.failures_remaining:
                    self.failures_remaining -= 1
                    raise OSError("temporary failure")
                return super(FlakyWriter, self).append(event)

        writer = FlakyWriter()
        lifecycle = CameraLifecycleEvents(
            writer,
            clock=iter((10.0, 20.0)).__next__,
        )
        lifecycle.on_status(
            "RUNNING",
            supervisor_state("running"),
        )
        failed = lifecycle.on_status(
            "CAMERA_OFFLINE",
            supervisor_state("offline"),
        )
        self.assertIn("persistence_error", failed)
        self.assertEqual(len(lifecycle.pending_events), 1)

        lifecycle.on_status(
            "RESTARTING",
            supervisor_state("retry"),
        )
        lifecycle.on_status(
            "RUNNING",
            supervisor_state("recovered"),
        )

        self.assertEqual(len(writer.events), 2)
        self.assertEqual(len(lifecycle.pending_events), 0)
        self.assertIsNone(lifecycle.last_error)


if __name__ == "__main__":
    unittest.main()
