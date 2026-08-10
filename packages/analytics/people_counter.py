"""Debounced people counting based on confirmed tracker state."""


class PeopleCounter(object):
    """Maintain current and cumulative confirmed person-track counts.

    A person track is confirmed only after ``min_confirmed_hits`` detections.
    Once confirmed, it remains in the current occupancy during short detector
    gaps up to ``occupancy_grace_frames``.  These are track lifecycle counts,
    not physical entrance/exit counts (which require a zone or crossing line).
    """

    def __init__(
        self,
        person_class_name="person",
        min_confirmed_hits=3,
        occupancy_grace_frames=10,
    ):
        if int(min_confirmed_hits) <= 0:
            raise ValueError("min_confirmed_hits must be positive")
        if int(occupancy_grace_frames) < 0:
            raise ValueError("occupancy_grace_frames must be non-negative")

        self.person_class_name = str(person_class_name)
        self.min_confirmed_hits = int(min_confirmed_hits)
        self.occupancy_grace_frames = int(occupancy_grace_frames)
        self._confirmed_ever = set()
        self._current_ids = set()

    def update(self, tracks, frame_id):
        confirmed_current = set()
        visible_current = set()

        for track in tracks:
            if track["class_name"] != self.person_class_name:
                continue
            if int(track["hits"]) < self.min_confirmed_hits:
                continue

            track_id = int(track["track_id"])
            missed_frames = int(track["missed_frames"])
            self._confirmed_ever.add(track_id)

            if missed_frames <= self.occupancy_grace_frames:
                confirmed_current.add(track_id)
            if missed_frames == 0:
                visible_current.add(track_id)

        self._current_ids = confirmed_current

        return {
            "frame_id": int(frame_id),
            "current_people": len(confirmed_current),
            "visible_people": len(visible_current),
            "confirmed_tracks_total": len(self._confirmed_ever),
            "active_track_ids": sorted(confirmed_current),
        }
