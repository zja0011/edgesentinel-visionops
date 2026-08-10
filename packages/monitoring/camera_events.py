"""Debounced camera lifecycle events from supervisor transitions."""

import json
import os
import time

from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore
from packages.events.store import JsonlEventStore


class CameraLifecycleEventWriter(object):
    def __init__(self, jsonl_path, database_path):
        self.jsonl_path = jsonl_path
        self.database_path = database_path

    def append(self, event):
        sqlite_store = SqliteEventStore(self.database_path)
        try:
            if sqlite_store.count_event_ids([event.event_id]) == 0:
                sqlite_store.append(event)
        finally:
            sqlite_store.close()
        if not self._jsonl_contains(event.event_id):
            jsonl_store = JsonlEventStore(self.jsonl_path)
            try:
                jsonl_store.append(event)
            finally:
                jsonl_store.close()
        return event.to_dict()

    def _jsonl_contains(self, event_id):
        path = os.path.abspath(self.jsonl_path)
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as event_file:
                for line in event_file:
                    try:
                        payload = json.loads(line)
                    except ValueError:
                        continue
                    if payload.get("event_id") == event_id:
                        return True
        except OSError:
            return False
        return False


class CameraLifecycleEvents(object):
    OUTAGE_STATUSES = (
        "CAMERA_OFFLINE",
        "VISION_STALLED",
        "RESTARTING",
        "WAITING_FOR_CAMERA",
    )

    def __init__(self, writer, camera_id="camera_01", clock=None):
        self.writer = writer
        self.camera_id = str(camera_id)
        self.clock = clock or time.time
        self.ever_running = False
        self.outage_active = False
        self.outage_started_at = None
        self.offline_event_id = None
        self.last_error = None
        self.pending_events = []

    def on_status(self, status, supervisor_state):
        self._retry_pending()
        status = str(status)
        if status == "RUNNING":
            if not self.ever_running:
                self.ever_running = True
                return None
            if self.outage_active:
                return self._emit_recovered(supervisor_state)
            return None
        if (
            status in self.OUTAGE_STATUSES
            and self.ever_running
            and not self.outage_active
        ):
            return self._emit_offline(
                status,
                supervisor_state,
            )
        return None

    def _emit_offline(self, status, state):
        self.outage_active = True
        self.outage_started_at = float(self.clock())
        event = Event(
            event_type="CAMERA_OFFLINE",
            severity="HIGH",
            timestamp=state["updated_at"],
            frame_id=self._frame_id(state),
            camera_id=self.camera_id,
            zone_id="global",
            zone_name="Global Scene",
            track_id=None,
            object_class="camera",
            details={
                "transition_status": status,
                "device": state.get("device"),
                "generation": int(
                    state.get("generation") or 0
                ),
                "restart_count": int(
                    state.get("restart_count") or 0
                ),
                "last_exit_code": state.get("last_exit_code"),
            },
        )
        self.offline_event_id = event.event_id
        return self._persist(event)

    def _emit_recovered(self, state):
        duration = max(
            0.0,
            float(self.clock()) - self.outage_started_at,
        )
        event = Event(
            event_type="CAMERA_RECOVERED",
            severity="INFO",
            timestamp=state["updated_at"],
            frame_id=self._frame_id(state),
            camera_id=self.camera_id,
            zone_id="global",
            zone_name="Global Scene",
            track_id=None,
            object_class="camera",
            details={
                "offline_event_id": self.offline_event_id,
                "outage_duration_seconds": round(duration, 3),
                "generation": int(
                    state.get("generation") or 0
                ),
                "restart_count": int(
                    state.get("restart_count") or 0
                ),
            },
        )
        result = self._persist(event)
        self.outage_active = False
        self.outage_started_at = None
        self.offline_event_id = None
        return result

    def _persist(self, event):
        try:
            result = self.writer.append(event)
            self.last_error = None
            return result
        except Exception as error:
            self.last_error = str(error)
            if not any(
                pending.event_id == event.event_id
                for pending in self.pending_events
            ):
                self.pending_events.append(event)
            return {
                "event_id": event.event_id,
                "event_type": event.event_type,
                "persistence_error": self.last_error,
            }

    def _retry_pending(self):
        for event in list(self.pending_events):
            try:
                self.writer.append(event)
            except Exception as error:
                self.last_error = str(error)
                return
            self.pending_events.remove(event)
            self.last_error = None

    @staticmethod
    def _frame_id(state):
        vision = state.get("vision") or {}
        try:
            return max(0, int(vision.get("frame_id") or 0))
        except (TypeError, ValueError):
            return 0
