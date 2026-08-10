"""Small adapter around the jetson-inference Python bindings."""

from packages.vision.schemas import Detection


class JetsonDetector(object):
    def __init__(self, network, threshold):
        try:
            import jetson_inference
            import jetson_utils
        except ImportError as error:
            raise RuntimeError(
                "jetson_inference and jetson_utils are required inside the "
                "Jetson container: {0}".format(error)
            )

        self._jetson_utils = jetson_utils
        # Use the positional network argument for compatibility with the
        # Python bindings shipped in the JetPack 4.6.1 container.
        self._network = jetson_inference.detectNet(network, threshold=threshold)

    def create_source(self, uri, width, height):
        return self._jetson_utils.videoSource(
            uri,
            argv=[
                "--input-width={0}".format(width),
                "--input-height={0}".format(height),
            ],
        )

    def create_output(self, uri):
        return self._jetson_utils.videoOutput(uri)

    def create_zone_renderer(self, zones):
        from packages.vision.visualization import ZoneOverlayRenderer

        return ZoneOverlayRenderer(self._jetson_utils, zones)

    def save_image(self, path, image, quality=90):
        self._jetson_utils.saveImage(path, image, quality=int(quality))

    def detect(self, image):
        raw_detections = self._network.Detect(image, overlay="box,labels,conf")
        results = []
        for item in raw_detections:
            results.append(
                Detection(
                    class_id=item.ClassID,
                    class_name=self._network.GetClassDesc(item.ClassID),
                    confidence=item.Confidence,
                    x1=item.Left,
                    y1=item.Top,
                    x2=item.Right,
                    y2=item.Bottom,
                )
            )
        return results

    def network_fps(self):
        return float(self._network.GetNetworkFPS())
