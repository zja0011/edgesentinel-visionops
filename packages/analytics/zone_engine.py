"""Resolution-independent polygon zone membership and occupancy."""

import json


def _point_on_segment(point, start, end, epsilon=1e-9):
    px, py = point
    x1, y1 = start
    x2, y2 = end
    cross = (px - x1) * (y2 - y1) - (py - y1) * (x2 - x1)
    if abs(cross) > epsilon:
        return False
    return (
        min(x1, x2) - epsilon <= px <= max(x1, x2) + epsilon
        and min(y1, y2) - epsilon <= py <= max(y1, y2) + epsilon
    )


def point_in_polygon(point, polygon):
    """Return True when a normalized point is inside or on the boundary."""
    if len(polygon) < 3:
        return False

    inside = False
    previous = polygon[-1]
    for current in polygon:
        if _point_on_segment(point, previous, current):
            return True

        x1, y1 = previous
        x2, y2 = current
        crosses = (y1 > point[1]) != (y2 > point[1])
        if crosses:
            intersection_x = (x2 - x1) * (point[1] - y1) / (y2 - y1) + x1
            if point[0] < intersection_x:
                inside = not inside
        previous = current
    return inside


def normalized_anchor(bbox, width, height, anchor):
    if int(width) <= 0 or int(height) <= 0:
        raise ValueError("frame width and height must be positive")
    x1, y1, x2, y2 = [float(value) for value in bbox]
    center_x = (x1 + x2) / 2.0
    if anchor == "center":
        pixel_point = (center_x, (y1 + y2) / 2.0)
    elif anchor == "bottom_center":
        pixel_point = (center_x, y2)
    else:
        raise ValueError("unsupported zone anchor: {0}".format(anchor))
    return (pixel_point[0] / float(width), pixel_point[1] / float(height))


class Zone(object):
    VALID_ANCHORS = ("center", "bottom_center")

    def __init__(
        self,
        zone_id,
        name,
        polygon,
        target_classes,
        anchor="center",
        minimum_hits=1,
        max_missed_frames=0,
    ):
        if not zone_id:
            raise ValueError("zone id is required")
        if len(polygon) < 3:
            raise ValueError("zone polygon requires at least three points")
        if anchor not in self.VALID_ANCHORS:
            raise ValueError("unsupported zone anchor: {0}".format(anchor))
        if int(minimum_hits) <= 0:
            raise ValueError("minimum_hits must be positive")
        if int(max_missed_frames) < 0:
            raise ValueError("max_missed_frames must be non-negative")

        normalized_polygon = []
        for point in polygon:
            if len(point) != 2:
                raise ValueError("zone polygon points must have two values")
            x, y = float(point[0]), float(point[1])
            if not 0.0 <= x <= 1.0 or not 0.0 <= y <= 1.0:
                raise ValueError("normalized zone coordinates must be 0..1")
            normalized_polygon.append((x, y))

        self.zone_id = str(zone_id)
        self.name = str(name or zone_id)
        self.polygon = normalized_polygon
        self.target_classes = set(str(item) for item in target_classes)
        self.anchor = anchor
        self.minimum_hits = int(minimum_hits)
        self.max_missed_frames = int(max_missed_frames)

    def accepts_class(self, class_name):
        return not self.target_classes or class_name in self.target_classes

    def contains_bbox(self, class_name, bbox, width, height):
        if not self.accepts_class(class_name):
            return False
        point = normalized_anchor(bbox, width, height, self.anchor)
        return point_in_polygon(point, self.polygon)


class ZoneEngine(object):
    def __init__(self, zones):
        self.zones = list(zones)
        zone_ids = [zone.zone_id for zone in self.zones]
        if len(zone_ids) != len(set(zone_ids)):
            raise ValueError("zone ids must be unique")

    @classmethod
    def from_file(cls, path):
        with open(path, "r", encoding="utf-8") as config_file:
            payload = json.load(config_file)
        if payload.get("coordinate_space") != "normalized":
            raise ValueError("only normalized zone coordinates are supported")

        zones = []
        for item in payload.get("zones", []):
            zones.append(
                Zone(
                    zone_id=item["id"],
                    name=item.get("name", item["id"]),
                    polygon=item["polygon"],
                    target_classes=item.get("target_classes", []),
                    anchor=item.get("anchor", "center"),
                    minimum_hits=item.get("minimum_hits", 1),
                    max_missed_frames=item.get("max_missed_frames", 0),
                )
            )
        return cls(zones)

    def annotate_detections(self, detections, width, height):
        for detection in detections:
            detection.zone_ids = [
                zone.zone_id
                for zone in self.zones
                if zone.contains_bbox(
                    detection.class_name, detection.bbox, width, height
                )
            ]
        return detections

    def snapshot(self, tracks, width, height):
        snapshots = []
        for zone in self.zones:
            track_ids = []
            for track in tracks:
                if int(track["hits"]) < zone.minimum_hits:
                    continue
                if int(track["missed_frames"]) > zone.max_missed_frames:
                    continue
                if zone.contains_bbox(
                    track["class_name"], track["bbox"], width, height
                ):
                    track_ids.append(int(track["track_id"]))
            snapshots.append(
                {
                    "zone_id": zone.zone_id,
                    "name": zone.name,
                    "current_count": len(set(track_ids)),
                    "track_ids": sorted(set(track_ids)),
                }
            )
        return snapshots
