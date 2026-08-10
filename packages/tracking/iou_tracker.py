"""A small, deterministic class-aware IoU tracker.

This tracker intentionally has no NumPy dependency so that it runs unchanged
with Python 3.6 on the Jetson Nano.  It is a baseline lifecycle implementation,
not a replacement for motion-aware trackers like SORT or ByteTrack.
"""


def bbox_iou(left, right):
    """Return intersection-over-union for two (x1, y1, x2, y2) boxes."""
    intersection_x1 = max(float(left[0]), float(right[0]))
    intersection_y1 = max(float(left[1]), float(right[1]))
    intersection_x2 = min(float(left[2]), float(right[2]))
    intersection_y2 = min(float(left[3]), float(right[3]))

    intersection_width = max(0.0, intersection_x2 - intersection_x1)
    intersection_height = max(0.0, intersection_y2 - intersection_y1)
    intersection_area = intersection_width * intersection_height

    left_area = max(0.0, float(left[2]) - float(left[0])) * max(
        0.0, float(left[3]) - float(left[1])
    )
    right_area = max(0.0, float(right[2]) - float(right[0])) * max(
        0.0, float(right[3]) - float(right[1])
    )
    union_area = left_area + right_area - intersection_area
    if union_area <= 0.0:
        return 0.0
    return intersection_area / union_area


class Track(object):
    __slots__ = (
        "track_id",
        "class_id",
        "class_name",
        "bbox",
        "confidence",
        "hits",
        "age",
        "missed_frames",
        "first_seen_frame",
        "last_seen_frame",
        "trajectory",
        "trajectory_limit",
    )

    def __init__(
        self,
        track_id,
        detection,
        frame_id,
        trajectory_limit=300,
    ):
        self.track_id = int(track_id)
        self.class_id = detection.class_id
        self.class_name = detection.class_name
        self.bbox = detection.bbox
        self.confidence = detection.confidence
        self.hits = 1
        self.age = 1
        self.missed_frames = 0
        self.first_seen_frame = int(frame_id)
        self.last_seen_frame = int(frame_id)
        self.trajectory = []
        self.trajectory_limit = int(trajectory_limit)
        self._append_trajectory(frame_id, detection.bbox)

    def update(self, detection, frame_id):
        self.bbox = detection.bbox
        self.confidence = detection.confidence
        self.hits += 1
        self.age += 1
        self.missed_frames = 0
        self.last_seen_frame = int(frame_id)
        self._append_trajectory(frame_id, detection.bbox)
        detection.track_id = self.track_id

    def mark_missed(self):
        self.age += 1
        self.missed_frames += 1

    def _append_trajectory(self, frame_id, bbox):
        center_x = (float(bbox[0]) + float(bbox[2])) / 2.0
        center_y = (float(bbox[1]) + float(bbox[3])) / 2.0
        self.trajectory.append(
            {
                "frame_id": int(frame_id),
                "center_x": center_x,
                "center_y": center_y,
            }
        )
        if len(self.trajectory) > self.trajectory_limit:
            self.trajectory = self.trajectory[
                -self.trajectory_limit:
            ]

    def to_dict(self, include_trajectory=False):
        result = {
            "track_id": self.track_id,
            "class_id": self.class_id,
            "class_name": self.class_name,
            "bbox": [round(value, 2) for value in self.bbox],
            "confidence": round(self.confidence, 6),
            "hits": self.hits,
            "age": self.age,
            "missed_frames": self.missed_frames,
            "first_seen_frame": self.first_seen_frame,
            "last_seen_frame": self.last_seen_frame,
        }
        if include_trajectory:
            result["trajectory"] = [
                {
                    "frame_id": point["frame_id"],
                    "center_x": round(point["center_x"], 2),
                    "center_y": round(point["center_y"], 2),
                }
                for point in self.trajectory
            ]
        return result


class IoUTracker(object):
    """Assign stable IDs using greedy, class-aware IoU matching."""

    def __init__(
        self,
        iou_threshold=0.3,
        max_missed_frames=10,
        trajectory_limit=300,
    ):
        if not 0.0 <= float(iou_threshold) <= 1.0:
            raise ValueError("iou_threshold must be between 0 and 1")
        if int(max_missed_frames) < 0:
            raise ValueError("max_missed_frames must be non-negative")
        if int(trajectory_limit) <= 0:
            raise ValueError("trajectory_limit must be positive")

        self.iou_threshold = float(iou_threshold)
        self.max_missed_frames = int(max_missed_frames)
        self.trajectory_limit = int(trajectory_limit)
        self._next_track_id = 1
        self._tracks = {}

    def update(self, detections, frame_id):
        detections = list(detections)
        candidates = []

        for track_id, track in self._tracks.items():
            for detection_index, detection in enumerate(detections):
                if track.class_id != detection.class_id:
                    continue
                score = bbox_iou(track.bbox, detection.bbox)
                if score >= self.iou_threshold:
                    candidates.append((score, track_id, detection_index))

        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        matched_tracks = set()
        matched_detections = set()

        for score, track_id, detection_index in candidates:
            if track_id in matched_tracks or detection_index in matched_detections:
                continue
            self._tracks[track_id].update(
                detections[detection_index], frame_id
            )
            matched_tracks.add(track_id)
            matched_detections.add(detection_index)

        for track_id, track in list(self._tracks.items()):
            if track_id not in matched_tracks:
                track.mark_missed()
                if track.missed_frames > self.max_missed_frames:
                    del self._tracks[track_id]

        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detections:
                continue
            track = Track(
                self._next_track_id,
                detection,
                frame_id,
                trajectory_limit=self.trajectory_limit,
            )
            detection.track_id = track.track_id
            self._tracks[track.track_id] = track
            self._next_track_id += 1

        return detections

    def active_tracks(
        self,
        include_missed=False,
        include_trajectory=False,
    ):
        tracks = []
        for track_id in sorted(self._tracks):
            track = self._tracks[track_id]
            if include_missed or track.missed_frames == 0:
                tracks.append(
                    track.to_dict(
                        include_trajectory=include_trajectory
                    )
                )
        return tracks
