import unittest

from packages.tracking.iou_tracker import IoUTracker, bbox_iou
from packages.vision.schemas import Detection


def detection(class_id=1, class_name="person", bbox=(10, 10, 30, 30)):
    return Detection(
        class_id=class_id,
        class_name=class_name,
        confidence=0.9,
        x1=bbox[0],
        y1=bbox[1],
        x2=bbox[2],
        y2=bbox[3],
    )


class IoUTrackerTests(unittest.TestCase):
    def test_iou(self):
        self.assertEqual(bbox_iou((0, 0, 10, 10), (20, 20, 30, 30)), 0.0)
        self.assertAlmostEqual(
            bbox_iou((0, 0, 10, 10), (5, 5, 15, 15)), 25.0 / 175.0
        )
        self.assertEqual(bbox_iou((0, 0, 10, 10), (0, 0, 10, 10)), 1.0)

    def test_preserves_id_for_overlapping_detection(self):
        tracker = IoUTracker(iou_threshold=0.3, max_missed_frames=2)
        first = tracker.update([detection()], frame_id=1)[0]
        second = tracker.update(
            [detection(bbox=(11, 10, 31, 30))], frame_id=2
        )[0]

        self.assertEqual(first.track_id, second.track_id)
        self.assertEqual(second.track_id, 1)

    def test_never_matches_different_classes(self):
        tracker = IoUTracker()
        person = tracker.update([detection()], frame_id=1)[0]
        chair = tracker.update(
            [detection(62, "chair", (10, 10, 30, 30))], frame_id=2
        )[0]

        self.assertNotEqual(person.track_id, chair.track_id)

    def test_expires_track_after_missed_frame_limit(self):
        tracker = IoUTracker(iou_threshold=0.3, max_missed_frames=1)
        original = tracker.update([detection()], frame_id=1)[0]
        tracker.update([], frame_id=2)
        tracker.update([], frame_id=3)
        replacement = tracker.update([detection()], frame_id=4)[0]

        self.assertNotEqual(original.track_id, replacement.track_id)
        self.assertEqual(replacement.track_id, 2)

    def test_assigns_each_detection_to_only_one_track(self):
        tracker = IoUTracker(iou_threshold=0.1)
        initial = tracker.update(
            [
                detection(bbox=(0, 0, 20, 20)),
                detection(bbox=(30, 0, 50, 20)),
            ],
            frame_id=1,
        )
        updated = tracker.update(
            [
                detection(bbox=(1, 0, 21, 20)),
                detection(bbox=(31, 0, 51, 20)),
            ],
            frame_id=2,
        )

        self.assertEqual(
            [item.track_id for item in initial],
            [item.track_id for item in updated],
        )
        self.assertEqual(len(set(item.track_id for item in updated)), 2)

    def test_keeps_bounded_center_point_trajectory(self):
        tracker = IoUTracker(
            iou_threshold=0.1,
            trajectory_limit=3,
        )
        for frame_id in range(1, 6):
            tracker.update(
                [
                    detection(
                        bbox=(
                            frame_id,
                            0,
                            frame_id + 20,
                            20,
                        )
                    )
                ],
                frame_id=frame_id,
            )

        track = tracker.active_tracks(
            include_trajectory=True
        )[0]
        self.assertEqual(
            [point["frame_id"] for point in track["trajectory"]],
            [3, 4, 5],
        )
        self.assertEqual(track["trajectory"][-1]["center_x"], 15.0)


if __name__ == "__main__":
    unittest.main()
