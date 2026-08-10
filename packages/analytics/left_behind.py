"""Detect objects that remain after confirmed people have left."""

from packages.events.schemas import Event


class LeftBehindEngine(object):
    def __init__(
        self,
        target_classes,
        confirm_frames=200,
        rearm_people_frames=15,
    ):
        classes = []
        for value in target_classes:
            class_name = str(value).strip()
            if class_name and class_name not in classes:
                classes.append(class_name)
        if not classes:
            raise ValueError("target_classes must not be empty")
        if int(confirm_frames) <= 0:
            raise ValueError("confirm_frames must be positive")
        if int(rearm_people_frames) <= 0:
            raise ValueError("rearm_people_frames must be positive")

        self.target_classes = classes
        self.confirm_frames = int(confirm_frames)
        self.rearm_people_frames = int(rearm_people_frames)
        self._people_present_frames = 0
        self._states = {
            class_name: {
                "candidate_frames": 0,
                "alerted": False,
                "last_count": 0,
            }
            for class_name in classes
        }

    def update(
        self,
        inventory,
        people,
        frame_id,
        timestamp,
        camera_id,
    ):
        current_people = int(people.get("current_people", 0))
        current_counts = inventory.get("current_counts", {})
        active_track_ids = inventory.get("active_track_ids", {})

        if current_people > 0:
            self._people_present_frames += 1
            for class_name, state in self._states.items():
                state["candidate_frames"] = 0
                state["last_count"] = int(
                    current_counts.get(class_name, 0)
                )
                if (
                    self._people_present_frames
                    >= self.rearm_people_frames
                ):
                    state["alerted"] = False
            return self.snapshot(current_people), []

        self._people_present_frames = 0
        events = []

        for class_name, state in self._states.items():
            current_count = int(current_counts.get(class_name, 0))

            if current_count <= 0:
                state["candidate_frames"] = 0
                state["alerted"] = False
                state["last_count"] = 0
                continue

            if current_count != state["last_count"]:
                state["candidate_frames"] = 0
                state["alerted"] = False
                state["last_count"] = current_count

            if state["alerted"]:
                continue

            state["candidate_frames"] += 1
            if state["candidate_frames"] < self.confirm_frames:
                continue

            state["alerted"] = True
            events.append(
                Event(
                    event_type="OBJECT_LEFT_BEHIND",
                    timestamp=timestamp,
                    frame_id=frame_id,
                    camera_id=camera_id,
                    zone_id="global",
                    zone_name="Global Scene",
                    track_id=None,
                    object_class=class_name,
                    severity="MEDIUM",
                    details={
                        "current_count": current_count,
                        "current_people": current_people,
                        "current_track_ids": list(
                            active_track_ids.get(class_name, [])
                        ),
                        "confirmation_frames": self.confirm_frames,
                    },
                )
            )

        return self.snapshot(current_people), events

    def snapshot(self, current_people=0):
        return {
            "target_classes": list(self.target_classes),
            "current_people": int(current_people),
            "confirmation_frames": self.confirm_frames,
            "rearm_people_frames": self.rearm_people_frames,
            "candidate_frames": {
                class_name: state["candidate_frames"]
                for class_name, state in self._states.items()
                if state["candidate_frames"] > 0
                and not state["alerted"]
            },
            "alerted_classes": [
                class_name
                for class_name, state in self._states.items()
                if state["alerted"]
            ],
        }
