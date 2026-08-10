"""Debounced state machine for zone enter and exit events."""

import time

from packages.events.schemas import Event


class ZoneEventEngine(object):
    def __init__(
        self,
        enter_confirm_frames=3,
        exit_confirm_frames=5,
        dwell_seconds=0.0,
        clock=None,
    ):
        if int(enter_confirm_frames) <= 0:
            raise ValueError("enter_confirm_frames must be positive")
        if int(exit_confirm_frames) <= 0:
            raise ValueError("exit_confirm_frames must be positive")
        if float(dwell_seconds) < 0:
            raise ValueError("dwell_seconds must be non-negative")
        self.enter_confirm_frames = int(enter_confirm_frames)
        self.exit_confirm_frames = int(exit_confirm_frames)
        self.dwell_seconds = float(dwell_seconds)
        self.clock = clock or time.monotonic
        self._states = {}

    def update(
        self,
        zone_snapshots,
        active_tracks,
        frame_id,
        timestamp,
        camera_id,
        monotonic_time=None,
    ):
        events = []
        now = float(
            self.clock()
            if monotonic_time is None
            else monotonic_time
        )
        track_classes = {
            int(track["track_id"]): track["class_name"]
            for track in active_tracks
        }
        zone_names = {
            snapshot["zone_id"]: snapshot.get("name", snapshot["zone_id"])
            for snapshot in zone_snapshots
        }
        present_keys = set()

        for snapshot in zone_snapshots:
            zone_id = snapshot["zone_id"]
            zone_name = snapshot.get("name", zone_id)
            for track_id_value in snapshot.get("track_ids", []):
                track_id = int(track_id_value)
                key = (zone_id, track_id)
                present_keys.add(key)
                state = self._states.get(key)

                if state is None:
                    state = {
                        "phase": "entering",
                        "presence_frames": 0,
                        "absence_frames": 0,
                        "class_name": track_classes.get(track_id, "unknown"),
                        "entered_frame_id": None,
                        "entered_at": None,
                        "dwell_emitted": False,
                    }
                    self._states[key] = state

                state["presence_frames"] += 1
                state["absence_frames"] = 0
                if track_id in track_classes:
                    state["class_name"] = track_classes[track_id]

                if (
                    state["phase"] == "entering"
                    and state["presence_frames"] >= self.enter_confirm_frames
                ):
                    state["phase"] = "inside"
                    state["entered_frame_id"] = int(frame_id)
                    state["entered_at"] = now
                    events.append(
                        self._make_event(
                            "ZONE_ENTER",
                            timestamp,
                            frame_id,
                            camera_id,
                            zone_id,
                            zone_name,
                            track_id,
                            state["class_name"],
                            self.enter_confirm_frames,
                        )
                    )
                if (
                    self.dwell_seconds > 0
                    and state["phase"] == "inside"
                    and not state["dwell_emitted"]
                    and now - state["entered_at"]
                    >= self.dwell_seconds
                ):
                    observed_seconds = max(
                        0.0,
                        now - state["entered_at"],
                    )
                    state["dwell_emitted"] = True
                    events.append(
                        Event(
                            event_type="ZONE_DWELL",
                            timestamp=timestamp,
                            frame_id=frame_id,
                            camera_id=camera_id,
                            zone_id=zone_id,
                            zone_name=zone_name,
                            track_id=track_id,
                            object_class=state["class_name"],
                            severity="MEDIUM",
                            details={
                                "dwell_seconds_threshold": (
                                    self.dwell_seconds
                                ),
                                "observed_dwell_seconds": round(
                                    observed_seconds,
                                    3,
                                ),
                                "entered_frame_id": (
                                    state["entered_frame_id"]
                                ),
                            },
                        )
                    )

        for key, state in list(self._states.items()):
            if key in present_keys:
                continue
            zone_id, track_id = key

            if state["phase"] == "entering":
                del self._states[key]
                continue

            state["absence_frames"] += 1
            if state["absence_frames"] >= self.exit_confirm_frames:
                events.append(
                    self._make_event(
                        "ZONE_EXIT",
                        timestamp,
                        frame_id,
                        camera_id,
                        zone_id,
                        zone_names.get(zone_id, zone_id),
                        track_id,
                        state["class_name"],
                        self.exit_confirm_frames,
                    )
                )
                del self._states[key]

        return events

    @staticmethod
    def _make_event(
        event_type,
        timestamp,
        frame_id,
        camera_id,
        zone_id,
        zone_name,
        track_id,
        object_class,
        confirmation_frames,
    ):
        return Event(
            event_type=event_type,
            timestamp=timestamp,
            frame_id=frame_id,
            camera_id=camera_id,
            zone_id=zone_id,
            zone_name=zone_name,
            track_id=track_id,
            object_class=object_class,
            severity="INFO",
            details={"confirmation_frames": confirmation_frames},
        )
