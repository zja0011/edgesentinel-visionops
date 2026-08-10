"""Bounded, privacy-conscious track-history summaries."""

import math


def _clamp(value):
    return max(0.0, min(1.0, float(value)))


def _sample_points(points, maximum):
    points = list(points)
    if len(points) <= maximum:
        return points
    if maximum <= 1:
        return [points[-1]]
    indexes = []
    for index in range(maximum):
        source_index = int(
            round(index * (len(points) - 1) / float(maximum - 1))
        )
        if source_index not in indexes:
            indexes.append(source_index)
    return [points[index] for index in indexes]


def _movement_label(delta_x, delta_y, threshold=0.03):
    horizontal = ""
    vertical = ""
    if delta_x >= threshold:
        horizontal = "right"
    elif delta_x <= -threshold:
        horizontal = "left"
    if delta_y >= threshold:
        vertical = "down"
    elif delta_y <= -threshold:
        vertical = "up"
    if horizontal and vertical:
        return "{0}_{1}".format(vertical, horizontal)
    return horizontal or vertical or "stationary"


def build_track_history(
    tracks,
    detections,
    width,
    height,
    max_points=30,
):
    """Return bounded normalized centers for current retained tracks."""
    width = float(width)
    height = float(height)
    max_points = int(max_points)
    if width <= 0 or height <= 0:
        raise ValueError("frame dimensions must be positive")
    if max_points < 2 or max_points > 100:
        raise ValueError("max_points must be between 2 and 100")

    zones_by_track = {}
    for detection in detections:
        track_id = getattr(detection, "track_id", None)
        if track_id is None:
            continue
        zones_by_track[int(track_id)] = sorted(
            {
                str(zone_id)
                for zone_id in (
                    getattr(detection, "zone_ids", None) or []
                )
                if str(zone_id)
            }
        )

    summaries = []
    for track in sorted(
        tracks,
        key=lambda item: int(item.get("track_id", 0)),
    ):
        raw_points = track.get("trajectory") or []
        normalized = [
            {
                "frame_id": int(point["frame_id"]),
                "x": round(
                    _clamp(float(point["center_x"]) / width),
                    4,
                ),
                "y": round(
                    _clamp(float(point["center_y"]) / height),
                    4,
                ),
            }
            for point in raw_points
        ]
        sampled = _sample_points(normalized, max_points)
        if sampled:
            delta_x = sampled[-1]["x"] - sampled[0]["x"]
            delta_y = sampled[-1]["y"] - sampled[0]["y"]
        else:
            delta_x = 0.0
            delta_y = 0.0
        track_id = int(track["track_id"])
        summaries.append(
            {
                "track_id": track_id,
                "class_name": str(track["class_name"]),
                "confidence": round(
                    float(track.get("confidence", 0.0)),
                    6,
                ),
                "visible": int(
                    track.get("missed_frames", 0)
                ) == 0,
                "hits": int(track.get("hits", 0)),
                "missed_frames": int(
                    track.get("missed_frames", 0)
                ),
                "first_seen_frame": int(
                    track.get("first_seen_frame", 0)
                ),
                "last_seen_frame": int(
                    track.get("last_seen_frame", 0)
                ),
                "observation_count": len(normalized),
                "sampled_point_count": len(sampled),
                "movement": _movement_label(delta_x, delta_y),
                "displacement": round(
                    math.sqrt(
                        delta_x * delta_x + delta_y * delta_y
                    ),
                    4,
                ),
                "current_zone_ids": zones_by_track.get(
                    track_id,
                    [],
                ),
                "points": sampled,
            }
        )
    return {
        "retained_track_count": len(summaries),
        "visible_track_count": sum(
            1 for item in summaries if item["visible"]
        ),
        "max_points_per_track": max_points,
        "tracks": summaries,
    }
