"""Save event images and attach their paths to structured events."""

import os
import shutil


class EvidenceManager(object):
    def __init__(
        self,
        directory,
        image_saver,
        quality=90,
        checkpoint_interval_frames=15,
        path_root=None,
    ):
        if not directory:
            raise ValueError("directory must not be empty")
        if image_saver is None:
            raise ValueError("image_saver is required")
        if not 1 <= int(quality) <= 100:
            raise ValueError("quality must be between 1 and 100")
        if int(checkpoint_interval_frames) <= 0:
            raise ValueError(
                "checkpoint_interval_frames must be positive"
            )

        self.directory = os.path.abspath(directory)
        self.image_saver = image_saver
        self.quality = int(quality)
        self.checkpoint_interval_frames = int(
            checkpoint_interval_frames
        )
        self.path_root = (
            os.path.abspath(path_root) if path_root is not None else None
        )
        self.checkpoint_directory = os.path.join(
            self.directory,
            ".checkpoints",
        )
        self._last_checkpoint_frames = {}

        if not os.path.isdir(self.directory):
            os.makedirs(self.directory)
        if not os.path.isdir(self.checkpoint_directory):
            os.makedirs(self.checkpoint_directory)

    def save(self, event, image):
        stem = self._build_stem(event)
        is_removed = event.event_type == "OBJECT_REMOVED"
        filename = stem + ("_after.jpg" if is_removed else ".jpg")
        path = os.path.join(self.directory, filename)
        self.image_saver(path, image, quality=self.quality)
        event.evidence_path = self._record_path(path)

        if is_removed:
            before_absolute_path = self._archive_checkpoint(event, stem)
            before_path = (
                self._record_path(before_absolute_path)
                if before_absolute_path is not None
                else None
            )
            event.details["before_evidence_path"] = before_path
            event.details["after_evidence_path"] = event.evidence_path
            event.details["evidence_pair_complete"] = (
                before_path is not None
            )
        return event.evidence_path

    @classmethod
    def _build_stem(cls, event):
        timestamp = cls._safe_component(event.timestamp)
        event_type = cls._safe_component(event.event_type)
        object_class = cls._safe_component(event.object_class)
        zone_id = cls._safe_component(event.zone_id)
        event_id = cls._safe_component(event.event_id)
        track_id = (
            str(int(event.track_id))
            if event.track_id is not None
            else "aggregate"
        )
        return "{0}_f{1:09d}_{2}_{3}_{4}_track{5}_{6}".format(
            timestamp,
            int(event.frame_id),
            event_type,
            object_class,
            zone_id,
            track_id,
            event_id,
        )

    def update_inventory_snapshot(self, inventory, image, frame_id):
        current_counts = inventory.get("current_counts", {})
        visible_counts = inventory.get("visible_counts", {})

        for class_name, current_count in current_counts.items():
            current_count = int(current_count)
            visible_count = int(visible_counts.get(class_name, 0))
            if current_count <= 0 or visible_count != current_count:
                continue

            last_frame = self._last_checkpoint_frames.get(class_name)
            if (
                last_frame is not None
                and int(frame_id) - last_frame
                < self.checkpoint_interval_frames
            ):
                continue

            checkpoint_path = self._checkpoint_path(class_name)
            self.image_saver(
                checkpoint_path,
                image,
                quality=self.quality,
            )
            self._last_checkpoint_frames[class_name] = int(frame_id)

    def _archive_checkpoint(self, event, stem):
        checkpoint_path = self._checkpoint_path(event.object_class)
        if not os.path.isfile(checkpoint_path):
            return None
        before_path = os.path.join(
            self.directory,
            stem + "_before.jpg",
        )
        shutil.copy2(checkpoint_path, before_path)
        return before_path

    def _checkpoint_path(self, object_class):
        return os.path.join(
            self.checkpoint_directory,
            self._safe_component(object_class) + ".jpg",
        )

    def _record_path(self, absolute_path):
        absolute_path = os.path.abspath(absolute_path)
        if self.path_root is None:
            return absolute_path
        try:
            relative_path = os.path.relpath(
                absolute_path,
                self.path_root,
            )
        except ValueError:
            return absolute_path
        if relative_path == os.pardir or relative_path.startswith(
            os.pardir + os.sep
        ):
            return absolute_path
        return relative_path.replace(os.sep, "/")

    @staticmethod
    def _safe_component(value):
        safe = "".join(
            character
            if character.isalnum() or character in ("-", "_", "+")
            else "_"
            for character in str(value)
        )
        if not safe:
            raise ValueError("filename component must not be empty")
        return safe
