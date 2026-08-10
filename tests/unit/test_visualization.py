import unittest

from packages.analytics.zone_engine import Zone
from packages.vision.visualization import ZoneOverlayRenderer


class FakeFont(object):
    White = (255, 255, 255, 255)
    Gray40 = (40, 40, 40, 255)

    def __init__(self):
        self.calls = []

    def OverlayText(self, *args):
        self.calls.append(args)


class FakeJetsonUtils(object):
    def __init__(self):
        self.font = FakeFont()
        self.lines = []

    def cudaFont(self):
        return self.font

    def cudaDrawLine(self, *args):
        self.lines.append(args)


class FakeImage(object):
    width = 640
    height = 480


class VisualizationTests(unittest.TestCase):
    def test_renders_polygon_and_count_label(self):
        utils = FakeJetsonUtils()
        zone = Zone(
            "left",
            "Left",
            [(0, 0), (0.5, 0), (0.5, 1), (0, 1)],
            ["person"],
        )
        renderer = ZoneOverlayRenderer(utils, [zone])

        renderer.render(
            FakeImage(),
            [{"zone_id": "left", "current_count": 2}],
        )

        self.assertEqual(len(utils.lines), 4)
        self.assertEqual(utils.lines[1][1], (320, 0))
        self.assertEqual(len(utils.font.calls), 1)
        self.assertEqual(utils.font.calls[0][3], "Left: 2")

    def test_updates_zone_geometry_without_recreating_renderer(self):
        utils = FakeJetsonUtils()
        original = Zone(
            "left",
            "Left",
            [(0, 0), (0.5, 0), (0.5, 1), (0, 1)],
            ["person"],
        )
        replacement = Zone(
            "left",
            "Left",
            [(0, 0), (0.4, 0), (0.4, 1), (0, 1)],
            ["person"],
        )
        renderer = ZoneOverlayRenderer(utils, [original])
        renderer.update_zones([replacement])

        renderer.render(
            FakeImage(),
            [{"zone_id": "left", "current_count": 1}],
        )

        self.assertEqual(utils.lines[1][1], (256, 0))
        self.assertEqual(len(utils.font.calls), 1)


if __name__ == "__main__":
    unittest.main()
