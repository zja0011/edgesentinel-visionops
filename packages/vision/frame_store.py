"""Atomic persistence for the latest annotated dashboard frame."""

import os
import tempfile


class LatestFrameStore(object):
    def __init__(self, path, image_saver, quality=80):
        if not path:
            raise ValueError("path must not be empty")
        if image_saver is None:
            raise ValueError("image_saver is required")
        if not 1 <= int(quality) <= 100:
            raise ValueError("quality must be between 1 and 100")
        self.path = os.path.abspath(path)
        self.image_saver = image_saver
        self.quality = int(quality)

    def write(self, image):
        parent = os.path.dirname(self.path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".latest-frame-",
            suffix=".jpg",
            dir=parent,
        )
        os.close(descriptor)
        try:
            self.image_saver(
                temporary_path,
                image,
                quality=self.quality,
            )
            if os.path.getsize(temporary_path) <= 0:
                raise RuntimeError("image saver produced an empty frame")
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)
        return self.path
