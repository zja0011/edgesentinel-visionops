"""Dependency-free data contracts compatible with Python 3.6."""

from datetime import datetime, timedelta, timezone


BEIJING_TIMEZONE = timezone(timedelta(hours=8))


def beijing_timestamp():
    """Return ISO-8601 Beijing time with millisecond precision."""
    value = datetime.now(BEIJING_TIMEZONE)
    return value.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "+08:00"


class Detection(object):
    __slots__ = (
        "class_id",
        "class_name",
        "confidence",
        "x1",
        "y1",
        "x2",
        "y2",
        "track_id",
        "zone_ids",
    )

    def __init__(
        self,
        class_id,
        class_name,
        confidence,
        x1,
        y1,
        x2,
        y2,
        track_id=None,
        zone_ids=None,
    ):
        self.class_id = int(class_id)
        self.class_name = str(class_name)
        self.confidence = float(confidence)
        self.x1 = float(x1)
        self.y1 = float(y1)
        self.x2 = float(x2)
        self.y2 = float(y2)
        self.track_id = int(track_id) if track_id is not None else None
        self.zone_ids = list(zone_ids) if zone_ids is not None else []

    @property
    def bbox(self):
        return (self.x1, self.y1, self.x2, self.y2)

    def to_dict(self):
        return {
            "track_id": self.track_id,
            "zone_ids": list(self.zone_ids),
            "class_id": self.class_id,
            "class_name": self.class_name,
            "confidence": round(self.confidence, 6),
            "bbox": [
                round(self.x1, 2),
                round(self.y1, 2),
                round(self.x2, 2),
                round(self.y2, 2),
            ],
        }


class FrameResult(object):
    SCHEMA_VERSION = "1.6"

    def __init__(
        self,
        frame_id,
        timestamp,
        camera_id,
        source,
        width,
        height,
        inference_ms,
        detections,
        analytics=None,
    ):
        self.frame_id = int(frame_id)
        self.timestamp = str(timestamp)
        self.camera_id = str(camera_id)
        self.source = str(source)
        self.width = int(width)
        self.height = int(height)
        self.inference_ms = float(inference_ms)
        self.detections = list(detections)
        self.analytics = dict(analytics) if analytics is not None else {}

    def to_dict(self):
        return {
            "schema_version": self.SCHEMA_VERSION,
            "frame_id": self.frame_id,
            "timestamp": self.timestamp,
            "camera_id": self.camera_id,
            "source": self.source,
            "width": self.width,
            "height": self.height,
            "inference_ms": round(self.inference_ms, 3),
            "detections": [item.to_dict() for item in self.detections],
            "analytics": self.analytics,
        }
