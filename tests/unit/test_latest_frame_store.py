import os
import tempfile
import unittest

from packages.vision.frame_store import LatestFrameStore


class LatestFrameStoreTests(unittest.TestCase):
    def test_atomically_writes_latest_frame(self):
        calls = []

        def save_image(path, image, quality):
            calls.append((path, image, quality))
            with open(path, "wb") as image_file:
                image_file.write(b"\xff\xd8new-jpeg")

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state", "frame.jpg")
            store = LatestFrameStore(path, save_image, quality=75)

            result = store.write(b"image")

            self.assertEqual(result, os.path.abspath(path))
            with open(path, "rb") as frame_file:
                self.assertEqual(frame_file.read(), b"\xff\xd8new-jpeg")
            self.assertEqual(calls[0][1:], (b"image", 75))
            self.assertNotEqual(calls[0][0], path)
            self.assertEqual(
                [
                    name
                    for name in os.listdir(os.path.dirname(path))
                    if name.startswith(".latest-frame-")
                ],
                [],
            )

    def test_failed_write_preserves_previous_frame(self):
        def fail_after_partial_write(path, image, quality):
            with open(path, "wb") as image_file:
                image_file.write(b"partial")
            raise RuntimeError("save failed")

        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "frame.jpg")
            with open(path, "wb") as frame_file:
                frame_file.write(b"\xff\xd8previous")
            store = LatestFrameStore(path, fail_after_partial_write)

            with self.assertRaises(RuntimeError):
                store.write(object())

            with open(path, "rb") as frame_file:
                self.assertEqual(frame_file.read(), b"\xff\xd8previous")

    def test_rejects_invalid_configuration(self):
        with self.assertRaises(ValueError):
            LatestFrameStore("", lambda *args, **kwargs: None)
        with self.assertRaises(ValueError):
            LatestFrameStore("frame.jpg", None)
        with self.assertRaises(ValueError):
            LatestFrameStore(
                "frame.jpg",
                lambda *args, **kwargs: None,
                quality=101,
            )


if __name__ == "__main__":
    unittest.main()
