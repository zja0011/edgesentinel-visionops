import os
import unittest

from scripts import build_original_video_manifest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


class OriginalVideoManifestTests(unittest.TestCase):
    def test_profiles_publish_eight_original_mp4_assets(self):
        profiles = build_original_video_manifest.PROFILES

        self.assertEqual(8, len(profiles))
        self.assertEqual(8, len(set(item[0] for item in profiles)))
        self.assertEqual(8, len(set(item[2] for item in profiles)))
        for video_id, source, asset in profiles:
            self.assertTrue(video_id.startswith("V"))
            self.assertTrue(source.endswith(".mp4"))
            self.assertTrue(asset.startswith("edgesentinel-original-"))
            self.assertTrue(asset.endswith(".mp4"))
            self.assertNotIn("720p", asset)

    def test_gallery_references_every_original_release_asset(self):
        gallery_path = os.path.join(PROJECT_DIR, "docs", "video-gallery.html")
        with open(gallery_path, "r", encoding="utf-8") as input_file:
            gallery = input_file.read()

        self.assertEqual(8, gallery.count("<video controls"))
        for _, _, asset in build_original_video_manifest.PROFILES:
            self.assertIn("/releases/download/v0.1.0-dev.1/" + asset, gallery)
        self.assertIn("没有二次压缩、裁剪、转码或遮挡", gallery)


if __name__ == "__main__":
    unittest.main()
