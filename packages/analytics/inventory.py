"""Debounced, class-aggregated object inventory state."""

from collections import Counter

from packages.events.schemas import Event


class InventoryEngine(object):
    def __init__(
        self,
        target_classes,
        minimum_hits=3,
        appear_confirm_frames=15,
        remove_confirm_frames=30,
    ):
        classes = []
        for value in target_classes:
            class_name = str(value).strip()
            if class_name and class_name not in classes:
                classes.append(class_name)
        if not classes:
            raise ValueError("target_classes must not be empty")
        if int(minimum_hits) <= 0:
            raise ValueError("minimum_hits must be positive")
        if int(appear_confirm_frames) <= 0:
            raise ValueError("appear_confirm_frames must be positive")
        if int(remove_confirm_frames) <= 0:
            raise ValueError("remove_confirm_frames must be positive")

        self.target_classes = classes
        self.minimum_hits = int(minimum_hits)
        self.appear_confirm_frames = int(appear_confirm_frames)
        self.remove_confirm_frames = int(remove_confirm_frames)
        self._states = {
            class_name: {
                "stable_count": 0,
                "stable_track_ids": [],
                "candidate_count": None,
                "candidate_frames": 0,
                "candidate_track_ids": [],
            }
            for class_name in self.target_classes
        }

    def update(self, tracks, frame_id, timestamp, camera_id):
        visible_track_ids = {
            class_name: [] for class_name in self.target_classes
        }
        for track in tracks:
            class_name = track["class_name"]
            if class_name not in self._states:
                continue
            if int(track.get("hits", 0)) < self.minimum_hits:
                continue
            if int(track.get("missed_frames", 0)) != 0:
                continue
            visible_track_ids[class_name].append(int(track["track_id"]))

        events = []
        for class_name in self.target_classes:
            track_ids = sorted(visible_track_ids[class_name])
            raw_count = len(track_ids)
            state = self._states[class_name]

            if raw_count == state["stable_count"]:
                state["stable_track_ids"] = track_ids
                state["candidate_count"] = None
                state["candidate_frames"] = 0
                state["candidate_track_ids"] = []
                continue

            if state["candidate_count"] == raw_count:
                state["candidate_frames"] += 1
                state["candidate_track_ids"] = track_ids
            else:
                state["candidate_count"] = raw_count
                state["candidate_frames"] = 1
                state["candidate_track_ids"] = track_ids

            previous_count = state["stable_count"]
            confirmation_frames = (
                self.appear_confirm_frames
                if raw_count > previous_count
                else self.remove_confirm_frames
            )
            if state["candidate_frames"] < confirmation_frames:
                continue

            previous_track_ids = list(state["stable_track_ids"])
            state["stable_count"] = raw_count
            state["stable_track_ids"] = track_ids
            state["candidate_count"] = None
            state["candidate_frames"] = 0
            state["candidate_track_ids"] = []

            event_type = (
                "OBJECT_APPEARED"
                if raw_count > previous_count
                else "OBJECT_REMOVED"
            )
            events.append(
                Event(
                    event_type=event_type,
                    timestamp=timestamp,
                    frame_id=frame_id,
                    camera_id=camera_id,
                    zone_id="global",
                    zone_name="Global Scene",
                    track_id=None,
                    object_class=class_name,
                    severity="INFO",
                    details={
                        "previous_count": previous_count,
                        "current_count": raw_count,
                        "count_change": raw_count - previous_count,
                        "previous_track_ids": previous_track_ids,
                        "current_track_ids": track_ids,
                        "confirmation_frames": confirmation_frames,
                    },
                )
            )

        return self.snapshot(visible_track_ids), events

    def snapshot(self, visible_track_ids=None):
        if visible_track_ids is None:
            visible_track_ids = {
                class_name: [] for class_name in self.target_classes
            }
        current_counts = {
            class_name: self._states[class_name]["stable_count"]
            for class_name in self.target_classes
        }
        visible_counts = Counter()
        for class_name, track_ids in visible_track_ids.items():
            visible_counts[class_name] = len(track_ids)
        return {
            "target_classes": list(self.target_classes),
            "current_counts": current_counts,
            "visible_counts": {
                class_name: visible_counts[class_name]
                for class_name in self.target_classes
            },
            "total_current": sum(current_counts.values()),
            "active_track_ids": {
                class_name: list(
                    self._states[class_name]["stable_track_ids"]
                )
                for class_name in self.target_classes
                if self._states[class_name]["stable_count"] > 0
            },
        }
