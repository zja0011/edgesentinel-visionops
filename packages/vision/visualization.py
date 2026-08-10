"""Jetson CUDA overlays for zones and live analytics."""


class ZoneOverlayRenderer(object):
    COLORS = (
        (0, 255, 80, 220),
        (0, 150, 255, 220),
        (255, 190, 0, 220),
        (220, 80, 255, 220),
    )

    def __init__(self, jetson_utils, zones):
        self._jetson_utils = jetson_utils
        self._zones = list(zones)
        self._font = jetson_utils.cudaFont()

    def update_zones(self, zones):
        self._zones = list(zones)

    def render(self, image, snapshots):
        snapshots_by_id = {
            snapshot["zone_id"]: snapshot for snapshot in snapshots
        }
        for index, zone in enumerate(self._zones):
            color = self.COLORS[index % len(self.COLORS)]
            points = [
                (
                    int(round(point[0] * image.width)),
                    int(round(point[1] * image.height)),
                )
                for point in zone.polygon
            ]
            for point_index, start in enumerate(points):
                end = points[(point_index + 1) % len(points)]
                self._jetson_utils.cudaDrawLine(
                    image, start, end, color, 3
                )

            snapshot = snapshots_by_id.get(zone.zone_id, {})
            count = int(snapshot.get("current_count", 0))
            label = "{0}: {1}".format(zone.name, count)
            label_x = min(point[0] for point in points) + 6
            label_y = min(point[1] for point in points) + 6
            self._font.OverlayText(
                image,
                image.width,
                image.height,
                label,
                label_x,
                label_y,
                self._font.White,
                self._font.Gray40,
            )
