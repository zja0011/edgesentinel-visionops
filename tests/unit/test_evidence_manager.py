import os
import tempfile
import unittest

from packages.evidence.manager import EvidenceManager
from packages.events.schemas import Event


def make_event(event_id="evt_test"):
    return Event(
        "ZONE_ENTER",
        "2026-07-22T12:00:00.000Z",
        10,
        "camera_01",
        "left",
        "Left",
        7,
        "person",
        event_id=event_id,
    )


def make_removed_event(event_id="evt_removed"):
    return Event(
        "OBJECT_REMOVED",
        "2026-07-22T12:01:00.000Z",
        40,
        "camera_01",
        "global",
        "Global Scene",
        None,
        "bottle",
        details={"previous_count": 1, "current_count": 0},
        event_id=event_id,
    )


class EvidenceManagerTests(unittest.TestCase):
    def test_saves_image_and_attaches_absolute_path(self):
        calls = []

        def save_image(path, image, quality):
            calls.append((path, image, quality))
            with open(path, "wb") as image_file:
                image_file.write(b"jpeg")

        with tempfile.TemporaryDirectory() as directory:
            event = make_event()
            image = object()
            manager = EvidenceManager(directory, save_image, quality=85)
            path = manager.save(event, image)

            self.assertEqual(path, event.evidence_path)
            self.assertTrue(os.path.isabs(path))
            self.assertEqual(
                os.path.basename(path),
                (
                    "2026-07-22T12_00_00_000Z_f000000010_"
                    "ZONE_ENTER_person_left_track7_evt_test.jpg"
                ),
            )
            self.assertEqual(calls, [(path, image, 85)])
            self.assertTrue(os.path.isfile(path))

    def test_sanitizes_event_id_before_using_it_as_filename(self):
        def save_image(path, image, quality):
            with open(path, "wb") as image_file:
                image_file.write(b"jpeg")

        with tempfile.TemporaryDirectory() as directory:
            event = make_event("../event one")
            manager = EvidenceManager(directory, save_image)
            path = manager.save(event, object())

            self.assertTrue(
                os.path.basename(path).endswith("___event_one.jpg")
            )
            self.assertEqual(os.path.dirname(path), os.path.abspath(directory))

    def test_rejects_invalid_quality(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                EvidenceManager(directory, lambda *args, **kwargs: None, 0)

    def test_aggregate_event_uses_readable_track_name(self):
        def save_image(path, image, quality):
            with open(path, "wb") as image_file:
                image_file.write(b"jpeg")

        with tempfile.TemporaryDirectory() as directory:
            event = make_event()
            event.track_id = None
            manager = EvidenceManager(directory, save_image)
            path = manager.save(event, object())

            self.assertIn("_trackaggregate_", os.path.basename(path))

    def test_removed_event_archives_last_stable_frame_as_before(self):
        def save_image(path, image, quality):
            with open(path, "wb") as image_file:
                image_file.write(image)

        with tempfile.TemporaryDirectory() as directory:
            manager = EvidenceManager(
                directory,
                save_image,
                checkpoint_interval_frames=1,
            )
            stable_inventory = {
                "current_counts": {"bottle": 1},
                "visible_counts": {"bottle": 1},
            }
            manager.update_inventory_snapshot(
                stable_inventory,
                b"last-visible",
                10,
            )
            manager.update_inventory_snapshot(
                {
                    "current_counts": {"bottle": 1},
                    "visible_counts": {"bottle": 0},
                },
                b"temporary-miss",
                11,
            )

            event = make_removed_event()
            after_path = manager.save(event, b"after-removal")
            before_path = event.details["before_evidence_path"]

            with open(before_path, "rb") as before_file:
                self.assertEqual(before_file.read(), b"last-visible")
            with open(after_path, "rb") as after_file:
                self.assertEqual(after_file.read(), b"after-removal")
            self.assertTrue(event.details["evidence_pair_complete"])
            self.assertEqual(
                event.details["after_evidence_path"],
                after_path,
            )
            self.assertTrue(before_path.endswith("_before.jpg"))
            self.assertTrue(after_path.endswith("_after.jpg"))

    def test_removed_event_records_incomplete_pair_without_checkpoint(self):
        def save_image(path, image, quality):
            with open(path, "wb") as image_file:
                image_file.write(b"jpeg")

        with tempfile.TemporaryDirectory() as directory:
            manager = EvidenceManager(directory, save_image)
            event = make_removed_event()
            manager.save(event, object())

            self.assertIsNone(event.details["before_evidence_path"])
            self.assertFalse(event.details["evidence_pair_complete"])

    def test_records_portable_path_relative_to_project_root(self):
        def save_image(path, image, quality):
            with open(path, "wb") as image_file:
                image_file.write(b"jpeg")

        with tempfile.TemporaryDirectory() as directory:
            evidence_directory = os.path.join(
                directory,
                "data",
                "evidence",
            )
            manager = EvidenceManager(
                evidence_directory,
                save_image,
                path_root=directory,
            )
            event = make_event()
            event.timestamp = "2026-07-22T20:00:00.000+08:00"
            path = manager.save(event, object())

            self.assertEqual(
                path,
                "data/evidence/"
                "2026-07-22T20_00_00_000+08_00_f000000010_"
                "ZONE_ENTER_person_left_track7_evt_test.jpg",
            )
            self.assertFalse(os.path.isabs(event.evidence_path))


if __name__ == "__main__":
    unittest.main()
