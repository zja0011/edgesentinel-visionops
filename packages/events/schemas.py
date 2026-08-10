"""Dependency-free structured event contract."""

import uuid


class Event(object):
    SCHEMA_VERSION = "1.2"

    def __init__(
        self,
        event_type,
        timestamp,
        frame_id,
        camera_id,
        zone_id,
        zone_name,
        track_id,
        object_class,
        severity="INFO",
        details=None,
        event_id=None,
        evidence_path=None,
    ):
        self.event_id = event_id or "evt_{0}".format(uuid.uuid4().hex)
        self.event_type = str(event_type)
        self.timestamp = str(timestamp)
        self.frame_id = int(frame_id)
        self.camera_id = str(camera_id)
        self.zone_id = str(zone_id)
        self.zone_name = str(zone_name)
        self.track_id = int(track_id) if track_id is not None else None
        self.object_class = str(object_class)
        self.severity = str(severity)
        self.details = dict(details) if details is not None else {}
        self.evidence_path = (
            str(evidence_path) if evidence_path is not None else None
        )

    def to_dict(self):
        return {
            "schema_version": self.SCHEMA_VERSION,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "severity": self.severity,
            "timestamp": self.timestamp,
            "frame_id": self.frame_id,
            "camera_id": self.camera_id,
            "zone_id": self.zone_id,
            "zone_name": self.zone_name,
            "track_id": self.track_id,
            "object_class": self.object_class,
            "evidence_path": self.evidence_path,
            "details": self.details,
        }
