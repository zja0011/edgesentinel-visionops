"""Bounded read-only MCP resources for EdgeSentinel."""

import os

from packages.api.camera_service import CameraStatusService
from packages.api.event_service import EventQueryService
from packages.harness.system_tools import SystemHealthTools
from packages.harness.model_tools import VisionModelTools
from packages.vision.schemas import beijing_timestamp
from packages.vision.state_store import CurrentVisionStateStore


class McpResourceError(RuntimeError):
    def __init__(self, message, not_found=False):
        super(McpResourceError, self).__init__(message)
        self.not_found = bool(not_found)


class EdgeSentinelResources(object):
    VISION_URI = "edgesentinel://vision/current"
    CAMERA_URI = "edgesentinel://camera/status"
    EVENTS_URI = "edgesentinel://events/recent"
    HEALTH_URI = "edgesentinel://system/health"
    MODEL_URI = "edgesentinel://vision/model"

    RESOURCE_DEFINITIONS = (
        {
            "uri": VISION_URI,
            "name": "current-vision",
            "title": "Current bounded vision state",
            "description": (
                "Latest people, stable object, and zone counts. "
                "Raw detections and image data are excluded."
            ),
            "mimeType": "application/json",
            "annotations": {
                "audience": ["assistant", "user"],
                "priority": 1.0,
            },
        },
        {
            "uri": CAMERA_URI,
            "name": "camera-status",
            "title": "Camera supervisor status",
            "description": (
                "Current camera availability, worker state, and "
                "freshness metadata."
            ),
            "mimeType": "application/json",
            "annotations": {
                "audience": ["assistant", "user"],
                "priority": 0.9,
            },
        },
        {
            "uri": EVENTS_URI,
            "name": "recent-events",
            "title": "Recent vision events",
            "description": (
                "At most ten recent event summaries without evidence "
                "paths or unbounded event details."
            ),
            "mimeType": "application/json",
            "annotations": {
                "audience": ["assistant", "user"],
                "priority": 0.8,
            },
        },
        {
            "uri": MODEL_URI,
            "name": "vision-model",
            "title": "Vision model provenance",
            "description": (
                "Active TensorRT engine identity and current SHA-256 "
                "integrity verification."
            ),
            "mimeType": "application/json",
            "annotations": {
                "audience": ["assistant", "user"],
                "priority": 0.9,
            },
        },
        {
            "uri": HEALTH_URI,
            "name": "system-health",
            "title": "Jetson health summary",
            "description": (
                "Bounded read-only load, memory, disk, and temperature "
                "health summary."
            ),
            "mimeType": "application/json",
            "annotations": {
                "audience": ["assistant", "user"],
                "priority": 0.7,
            },
        },
    )

    def __init__(
        self,
        project_dir,
        database_path,
        state_path=None,
        camera_state_path=None,
        state_max_age_seconds=5.0,
        camera_state_max_age_seconds=10.0,
        model_manifest_path=None,
        model_root="/jetson-inference/data/networks",
        audit_recorder=None,
    ):
        self.project_dir = os.path.abspath(project_dir)
        self.state_store = CurrentVisionStateStore(
            state_path
            or os.path.join(
                self.project_dir,
                "data",
                "state",
                "current-vision.json",
            )
        )
        self.state_max_age_seconds = float(
            state_max_age_seconds
        )
        self.camera_service = CameraStatusService(
            camera_state_path
            or os.path.join(
                self.project_dir,
                "data",
                "runtime",
                "vision-supervisor.json",
            ),
            max_state_age_seconds=(
                camera_state_max_age_seconds
            ),
        )
        self.event_service = EventQueryService(database_path)
        self.system_tools = SystemHealthTools(self.project_dir)
        self.model_tools = VisionModelTools(
            model_manifest_path
            or os.path.join(
                self.project_dir,
                "data",
                "state",
                "current-model.json",
            ),
            model_root,
        )
        self.audit_recorder = audit_recorder
        self._readers = {
            self.VISION_URI: self._read_vision,
            self.CAMERA_URI: self._read_camera,
            self.EVENTS_URI: self._read_events,
            self.HEALTH_URI: self._read_health,
            self.MODEL_URI: self._read_model,
        }

    def list_resources(self):
        return [
            dict(definition)
            for definition in self.RESOURCE_DEFINITIONS
        ]

    def read(self, uri):
        if not isinstance(uri, str) or not uri or len(uri) > 256:
            raise McpResourceError(
                "resource URI is invalid",
                not_found=True,
            )
        reader = self._readers.get(uri)
        if reader is None:
            self._audit(uri, "FAILED", "RESOURCE_NOT_FOUND")
            raise McpResourceError(
                "resource not found",
                not_found=True,
            )
        try:
            payload = reader()
        except Exception:
            self._audit(uri, "FAILED", "RESOURCE_UNAVAILABLE")
            raise McpResourceError("resource is unavailable")
        self._audit(uri, "SUCCEEDED", None)
        return payload

    def _read_vision(self):
        state = self.state_store.read(
            self.state_max_age_seconds
        )
        snapshot = state["snapshot"]
        analytics = snapshot.get("analytics") or {}
        people = analytics.get("people") or {}
        inventory = analytics.get("inventory") or {}
        raw_counts = inventory.get("current_counts") or {}
        objects = [
            {
                "class_name": str(class_name),
                "count": int(count),
            }
            for class_name, count in sorted(raw_counts.items())
            if int(count) > 0
        ][:32]
        zones = []
        for raw_zone in (analytics.get("zones") or [])[:32]:
            if not isinstance(raw_zone, dict):
                continue
            zone_id = raw_zone.get("zone_id")
            if not zone_id:
                continue
            zones.append(
                {
                    "zone_id": str(zone_id),
                    "name": str(
                        raw_zone.get("name") or zone_id
                    ),
                    "current_count": int(
                        raw_zone.get("current_count", 0)
                    ),
                }
            )
        raw_performance = analytics.get("performance") or {}
        raw_latency = raw_performance.get(
            "pipeline_latency_ms"
        ) or {}
        raw_targets = raw_performance.get("targets") or {}
        performance = {
            "status": raw_performance.get("status"),
            "sample_count": int(
                raw_performance.get("sample_count", 0)
            ),
            "processing_fps": raw_performance.get(
                "processing_fps"
            ),
            "pipeline_latency_ms": {
                "average": raw_latency.get("average"),
                "p95": raw_latency.get("p95"),
            },
            "targets": {
                "minimum_fps": raw_targets.get("minimum_fps"),
                "maximum_p95_ms": raw_targets.get(
                    "maximum_p95_ms"
                ),
                "all_met": bool(raw_targets.get("all_met")),
            },
        }
        return {
            "schema_version": "1.0",
            "resource": self.VISION_URI,
            "timestamp": snapshot.get("timestamp"),
            "camera_id": snapshot.get("camera_id"),
            "frame_id": int(snapshot.get("frame_id", 0)),
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "max_age_seconds": state["max_age_seconds"],
            "people": {
                "current": int(
                    people.get("current_people", 0)
                ),
                "visible": int(
                    people.get("visible_people", 0)
                ),
            },
            "objects": objects,
            "zones": zones,
            "performance": performance,
            "bounded": True,
            "raw_detections_included": False,
        }

    def _read_camera(self):
        payload = self.camera_service.get_status()
        return {
            "schema_version": "1.0",
            "resource": self.CAMERA_URI,
            "status": payload.get("status"),
            "device_available": bool(
                payload.get("device_available")
            ),
            "worker_running": bool(payload.get("worker_running")),
            "generation": int(payload.get("generation") or 0),
            "restart_count": int(
                payload.get("restart_count") or 0
            ),
            "state_age_seconds": payload.get(
                "state_age_seconds"
            ),
            "state_stale": bool(payload.get("state_stale")),
            "vision": dict(payload.get("vision") or {}),
            "read_only": True,
        }

    def _read_events(self):
        payload = self.event_service.list_events(limit=10)
        events = []
        for event in payload.get("events") or []:
            events.append(
                {
                    "event_id": event.get("event_id"),
                    "event_type": event.get("event_type"),
                    "severity": event.get("severity"),
                    "timestamp": event.get("timestamp"),
                    "camera_id": event.get("camera_id"),
                    "zone_id": event.get("zone_id"),
                    "zone_name": event.get("zone_name"),
                    "object_class": event.get("object_class"),
                    "status": event.get("status", "OPEN"),
                }
            )
        return {
            "schema_version": "1.0",
            "resource": self.EVENTS_URI,
            "count": len(events),
            "limit": 10,
            "events": events,
            "evidence_paths_included": False,
            "event_details_included": False,
            "read_only": True,
        }

    def _read_health(self):
        payload = self.system_tools.get_health({})
        payload = dict(payload)
        payload["resource"] = self.HEALTH_URI
        return payload

    def _read_model(self):
        payload = self.model_tools.get_model_info({})
        payload = dict(payload)
        payload["resource"] = self.MODEL_URI
        return payload

    def _audit(self, uri, status, error_code):
        if self.audit_recorder is None:
            return
        record = {
            "schema_version": "1.0",
            "record_type": "mcp_resource_read",
            "timestamp": beijing_timestamp(),
            "uri": str(uri)[:256],
            "status": status,
            "read_only": True,
        }
        if error_code:
            record["error"] = {"code": error_code}
        self.audit_recorder.append(record)
