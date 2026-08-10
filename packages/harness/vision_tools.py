"""Read-only Harness tools backed by the latest atomic vision state."""

from packages.vision.state_store import CurrentVisionStateStore


class VisionStateTools(object):
    def __init__(self, state_path, max_age_seconds=5.0):
        self.store = CurrentVisionStateStore(state_path)
        self.max_age_seconds = float(max_age_seconds)

    def get_people_count(self, unused_arguments):
        state = self.store.read(self.max_age_seconds)
        snapshot = state["snapshot"]
        people = snapshot.get("analytics", {}).get("people")
        if not isinstance(people, dict):
            raise RuntimeError("people analytics are unavailable")
        result = {
            "frame_id": snapshot["frame_id"],
            "timestamp": snapshot["timestamp"],
            "camera_id": snapshot["camera_id"],
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "max_age_seconds": state["max_age_seconds"],
            "current_people": int(people.get("current_people", 0)),
            "visible_people": int(people.get("visible_people", 0)),
            "active_track_ids": list(
                people.get("active_track_ids") or []
            ),
        }
        zone_config = snapshot.get("analytics", {}).get(
            "zone_config"
        )
        if isinstance(zone_config, dict):
            result["zone_config"] = {
                key: zone_config.get(key)
                for key in (
                    "enabled",
                    "status",
                    "version",
                    "zone_count",
                    "reload_count",
                    "last_reload_frame",
                    "check_interval_frames",
                    "last_error",
                )
                if key in zone_config
            }
        return result

    def get_current_objects(self, unused_arguments):
        state = self.store.read(self.max_age_seconds)
        snapshot = state["snapshot"]
        inventory = snapshot.get("analytics", {}).get("inventory")
        if not isinstance(inventory, dict):
            raise RuntimeError("inventory analytics are unavailable")
        current_counts = inventory.get("current_counts") or {}
        objects = [
            {
                "class_name": class_name,
                "count": int(count),
            }
            for class_name, count in sorted(current_counts.items())
            if int(count) > 0
        ]
        return {
            "frame_id": snapshot["frame_id"],
            "timestamp": snapshot["timestamp"],
            "camera_id": snapshot["camera_id"],
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "max_age_seconds": state["max_age_seconds"],
            "total_current": sum(
                item["count"] for item in objects
            ),
            "objects": objects,
            "visible_counts": dict(
                inventory.get("visible_counts") or {}
            ),
        }

    def get_performance(self, unused_arguments):
        state = self.store.read(self.max_age_seconds)
        snapshot = state["snapshot"]
        performance = snapshot.get("analytics", {}).get(
            "performance"
        )
        if not isinstance(performance, dict):
            raise RuntimeError(
                "vision performance metrics are unavailable"
            )
        latency = performance.get(
            "pipeline_latency_ms"
        ) or {}
        targets = performance.get("targets") or {}
        return {
            "frame_id": snapshot["frame_id"],
            "timestamp": snapshot["timestamp"],
            "camera_id": snapshot["camera_id"],
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "max_age_seconds": state["max_age_seconds"],
            "status": performance.get("status"),
            "total_frames": int(
                performance.get("total_frames", 0)
            ),
            "sample_count": int(
                performance.get("sample_count", 0)
            ),
            "window_size_frames": int(
                performance.get("window_size_frames", 0)
            ),
            "processing_fps": float(
                performance.get("processing_fps", 0.0)
            ),
            "frame_interval_ms": performance.get(
                "frame_interval_ms"
            ),
            "pipeline_latency_ms": {
                key: latency.get(key)
                for key in (
                    "latest",
                    "average",
                    "p50",
                    "p95",
                    "maximum",
                )
            },
            "targets": {
                "minimum_fps": targets.get("minimum_fps"),
                "maximum_p95_ms": targets.get(
                    "maximum_p95_ms"
                ),
                "fps_met": bool(targets.get("fps_met")),
                "p95_met": bool(targets.get("p95_met")),
                "all_met": bool(targets.get("all_met")),
            },
            "read_only": True,
        }

    def get_inventory_state(self, arguments):
        state = self.store.read(self.max_age_seconds)
        snapshot = state["snapshot"]
        inventory = snapshot.get("analytics", {}).get("inventory")
        if not isinstance(inventory, dict):
            raise RuntimeError("inventory analytics are unavailable")

        current_counts = inventory.get("current_counts") or {}
        visible_counts = inventory.get("visible_counts") or {}
        active_track_ids = inventory.get("active_track_ids") or {}
        target_classes = inventory.get("target_classes") or []
        configured_classes = []
        for value in target_classes:
            class_name = str(value).strip()
            if class_name and class_name not in configured_classes:
                configured_classes.append(class_name)
        for source in (
            current_counts,
            visible_counts,
            active_track_ids,
        ):
            for value in source:
                class_name = str(value).strip()
                if (
                    class_name
                    and class_name not in configured_classes
                ):
                    configured_classes.append(class_name)
        configured_classes.sort()
        if not configured_classes:
            raise RuntimeError(
                "inventory target classes are unavailable"
            )

        selected_object_class = (arguments or {}).get(
            "object_class"
        )
        if selected_object_class:
            selected_object_class = str(
                selected_object_class
            ).strip()
            if selected_object_class not in configured_classes:
                raise RuntimeError(
                    "configured inventory class does not exist: "
                    "{0}".format(selected_object_class)
                )
            returned_classes = [selected_object_class]
        else:
            selected_object_class = None
            returned_classes = configured_classes

        items = []
        for class_name in returned_classes:
            track_ids = []
            for track_id in active_track_ids.get(
                class_name,
                [],
            ) or []:
                try:
                    normalized_track_id = int(track_id)
                except (TypeError, ValueError):
                    continue
                if normalized_track_id not in track_ids:
                    track_ids.append(normalized_track_id)
            items.append(
                {
                    "class_name": class_name,
                    "current_count": int(
                        current_counts.get(class_name, 0)
                    ),
                    "visible_count": int(
                        visible_counts.get(class_name, 0)
                    ),
                    "active_track_ids": sorted(track_ids)[:100],
                }
            )

        return {
            "frame_id": snapshot["frame_id"],
            "timestamp": snapshot["timestamp"],
            "camera_id": snapshot["camera_id"],
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "max_age_seconds": state["max_age_seconds"],
            "selected_object_class": selected_object_class,
            "target_class_count": len(items),
            "total_current": sum(
                item["current_count"] for item in items
            ),
            "total_visible": sum(
                item["visible_count"] for item in items
            ),
            "nonzero_current_class_count": sum(
                1 for item in items if item["current_count"] > 0
            ),
            "items": items,
            "read_only": True,
        }

    def compare_inventory_state(self, arguments):
        expected_counts = (arguments or {}).get("expected_counts")
        if not isinstance(expected_counts, dict) or not expected_counts:
            raise ValueError("expected_counts must not be empty")
        inventory = self.get_inventory_state({})
        current_items = {
            item["class_name"]: item
            for item in inventory["items"]
        }

        comparisons = []
        for raw_class_name in sorted(expected_counts):
            class_name = str(raw_class_name).strip()
            if class_name not in current_items:
                raise RuntimeError(
                    "configured inventory class does not exist: "
                    "{0}".format(class_name)
                )
            expected_count = int(expected_counts[raw_class_name])
            if expected_count < 0 or expected_count > 100:
                raise ValueError(
                    "expected inventory count is out of range"
                )
            current_item = current_items[class_name]
            current_count = int(current_item["current_count"])
            delta = current_count - expected_count
            comparisons.append(
                {
                    "class_name": class_name,
                    "expected_count": expected_count,
                    "current_count": current_count,
                    "visible_count": int(
                        current_item["visible_count"]
                    ),
                    "delta": delta,
                    "missing_count": max(0, -delta),
                    "extra_count": max(0, delta),
                    "matches": delta == 0,
                    "active_track_ids": list(
                        current_item["active_track_ids"]
                    )[:100],
                }
            )

        total_expected = sum(
            item["expected_count"] for item in comparisons
        )
        total_current = sum(
            item["current_count"] for item in comparisons
        )
        return {
            "frame_id": inventory["frame_id"],
            "timestamp": inventory["timestamp"],
            "camera_id": inventory["camera_id"],
            "age_seconds": inventory["age_seconds"],
            "stale": inventory["stale"],
            "max_age_seconds": inventory["max_age_seconds"],
            "compared_class_count": len(comparisons),
            "total_expected": total_expected,
            "total_current": total_current,
            "total_missing": sum(
                item["missing_count"] for item in comparisons
            ),
            "total_extra": sum(
                item["extra_count"] for item in comparisons
            ),
            "matches": all(
                item["matches"] for item in comparisons
            ),
            "comparisons": comparisons,
            "read_only": True,
        }

    def count_objects(self, arguments):
        arguments = arguments or {}
        raw_classes = arguments.get("classes") or []
        classes = []
        for value in raw_classes:
            class_name = str(value).strip()
            if not class_name:
                raise ValueError(
                    "object classes must not be blank"
                )
            if class_name in classes:
                raise ValueError(
                    "object classes must be unique"
                )
            classes.append(class_name)
        if not classes:
            raise ValueError("classes must not be empty")
        if len(classes) > 20:
            raise ValueError("at most 20 classes may be counted")

        minimum_confidence = float(
            arguments.get("minimum_confidence", 0.0)
        )
        if minimum_confidence < 0.0 or minimum_confidence > 1.0:
            raise ValueError(
                "minimum_confidence must be between 0 and 1"
            )
        selected_zone_id = arguments.get("zone_id")
        if selected_zone_id:
            selected_zone_id = str(selected_zone_id)

        state = self.store.read(self.max_age_seconds)
        snapshot = state["snapshot"]
        if selected_zone_id:
            configured_zone_ids = {
                str(zone.get("zone_id"))
                for zone in (
                    snapshot.get("analytics", {}).get("zones")
                    or []
                )
                if isinstance(zone, dict) and zone.get("zone_id")
            }
            if selected_zone_id not in configured_zone_ids:
                raise RuntimeError(
                    "configured zone does not exist: {0}".format(
                        selected_zone_id
                    )
                )

        counts = {class_name: 0 for class_name in classes}
        for detection in snapshot.get("detections") or []:
            if not isinstance(detection, dict):
                continue
            class_name = detection.get("class_name")
            if class_name not in counts:
                continue
            try:
                confidence = float(detection.get("confidence", 0.0))
            except (TypeError, ValueError):
                continue
            if confidence < minimum_confidence:
                continue
            if selected_zone_id and selected_zone_id not in (
                detection.get("zone_ids") or []
            ):
                continue
            counts[class_name] += 1

        items = [
            {
                "class_name": class_name,
                "count": counts[class_name],
            }
            for class_name in classes
        ]
        return {
            "frame_id": snapshot["frame_id"],
            "timestamp": snapshot["timestamp"],
            "camera_id": snapshot["camera_id"],
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "max_age_seconds": state["max_age_seconds"],
            "requested_classes": classes,
            "selected_zone_id": selected_zone_id,
            "minimum_confidence": minimum_confidence,
            "class_count": len(items),
            "detected_class_count": sum(
                1 for item in items if item["count"] > 0
            ),
            "total_count": sum(
                item["count"] for item in items
            ),
            "counts": items,
            "read_only": True,
        }

    def get_track_history(self, arguments):
        arguments = arguments or {}
        selected_track_id = arguments.get("track_id")
        selected_object_class = arguments.get("object_class")
        if selected_track_id is None and not selected_object_class:
            raise ValueError(
                "track_id or object_class is required"
            )
        if selected_track_id is not None:
            selected_track_id = int(selected_track_id)
        if selected_object_class:
            selected_object_class = str(
                selected_object_class
            ).strip()
        else:
            selected_object_class = None
        limit = int(arguments.get("limit", 10))
        if limit < 1 or limit > 20:
            raise ValueError("limit must be between 1 and 20")

        state = self.store.read(self.max_age_seconds)
        snapshot = state["snapshot"]
        history = snapshot.get("analytics", {}).get(
            "track_history"
        )
        if not isinstance(history, dict):
            raise RuntimeError("track history is unavailable")

        tracks = []
        for raw_track in history.get("tracks") or []:
            if not isinstance(raw_track, dict):
                continue
            track_id = int(raw_track.get("track_id", 0))
            class_name = str(raw_track.get("class_name") or "")
            if (
                selected_track_id is not None
                and track_id != selected_track_id
            ):
                continue
            if (
                selected_object_class is not None
                and class_name != selected_object_class
            ):
                continue
            points = []
            for raw_point in (raw_track.get("points") or [])[:30]:
                if not isinstance(raw_point, dict):
                    continue
                points.append(
                    {
                        "frame_id": int(
                            raw_point.get("frame_id", 0)
                        ),
                        "x": round(
                            float(raw_point.get("x", 0.0)),
                            4,
                        ),
                        "y": round(
                            float(raw_point.get("y", 0.0)),
                            4,
                        ),
                    }
                )
            tracks.append(
                {
                    "track_id": track_id,
                    "class_name": class_name,
                    "confidence": round(
                        float(
                            raw_track.get("confidence", 0.0)
                        ),
                        6,
                    ),
                    "visible": bool(
                        raw_track.get("visible", False)
                    ),
                    "hits": int(raw_track.get("hits", 0)),
                    "missed_frames": int(
                        raw_track.get("missed_frames", 0)
                    ),
                    "first_seen_frame": int(
                        raw_track.get("first_seen_frame", 0)
                    ),
                    "last_seen_frame": int(
                        raw_track.get("last_seen_frame", 0)
                    ),
                    "observation_count": int(
                        raw_track.get("observation_count", 0)
                    ),
                    "sampled_point_count": len(points),
                    "movement": str(
                        raw_track.get("movement") or "stationary"
                    ),
                    "displacement": round(
                        float(
                            raw_track.get("displacement", 0.0)
                        ),
                        4,
                    ),
                    "current_zone_ids": [
                        str(zone_id)
                        for zone_id in (
                            raw_track.get("current_zone_ids") or []
                        )[:10]
                    ],
                    "points": points,
                }
            )
            if len(tracks) >= limit:
                break

        return {
            "frame_id": snapshot["frame_id"],
            "timestamp": snapshot["timestamp"],
            "camera_id": snapshot["camera_id"],
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "max_age_seconds": state["max_age_seconds"],
            "selected_track_id": selected_track_id,
            "selected_object_class": selected_object_class,
            "track_count": len(tracks),
            "tracks": tracks,
            "read_only": True,
        }

    def get_zone_status(self, arguments):
        state = self.store.read(self.max_age_seconds)
        snapshot = state["snapshot"]
        analytics = snapshot.get("analytics") or {}
        raw_zones = analytics.get("zones")
        if not isinstance(raw_zones, list):
            raise RuntimeError("zone analytics are unavailable")

        zones = []
        for raw_zone in raw_zones:
            if not isinstance(raw_zone, dict):
                continue
            zone_id = raw_zone.get("zone_id")
            if not zone_id:
                continue
            track_ids = list(raw_zone.get("track_ids") or [])
            zones.append(
                {
                    "zone_id": str(zone_id),
                    "name": str(
                        raw_zone.get("name") or zone_id
                    ),
                    "current_count": int(
                        raw_zone.get("current_count", 0)
                    ),
                    "track_ids": track_ids[:100],
                }
            )

        selected_zone_id = (arguments or {}).get("zone_id")
        if selected_zone_id:
            selected_zone_id = str(selected_zone_id)
            zones = [
                zone
                for zone in zones
                if zone["zone_id"] == selected_zone_id
            ]
            if not zones:
                raise RuntimeError(
                    "configured zone does not exist: {0}".format(
                        selected_zone_id
                    )
                )

        unique_track_ids = sorted(
            {
                int(track_id)
                for zone in zones
                for track_id in zone["track_ids"]
            }
        )
        return {
            "frame_id": snapshot["frame_id"],
            "timestamp": snapshot["timestamp"],
            "camera_id": snapshot["camera_id"],
            "age_seconds": state["age_seconds"],
            "stale": state["stale"],
            "max_age_seconds": state["max_age_seconds"],
            "selected_zone_id": selected_zone_id,
            "zone_count": len(zones),
            "occupied_zone_count": sum(
                1 for zone in zones if zone["current_count"] > 0
            ),
            "unique_current_count": len(unique_track_ids),
            "unique_track_ids": unique_track_ids,
            "zones": zones,
        }
