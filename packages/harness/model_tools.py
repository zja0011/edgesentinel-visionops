"""Read-only Harness tool for vision model provenance."""

from packages.vision.model_manifest import (
    VisionModelManifestStore,
    verify_vision_model_manifest,
)


class VisionModelTools(object):
    def __init__(self, manifest_path, model_root):
        self.store = VisionModelManifestStore(manifest_path)
        self.model_root = model_root

    def get_model_info(self, unused_arguments):
        manifest = self.store.read()
        return verify_vision_model_manifest(
            manifest,
            self.model_root,
        )
