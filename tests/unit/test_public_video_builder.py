import os
import unittest

from scripts import build_public_videos


class PublicVideoBuilderTests(unittest.TestCase):
    def test_release_profiles_are_bounded_unique_and_outside_git(self):
        profiles = build_public_videos.PROFILES

        self.assertEqual(len(profiles), 8)
        self.assertEqual(len({item["id"] for item in profiles}), 8)
        self.assertEqual(len({item["output"] for item in profiles}), 8)
        for item in profiles:
            self.assertTrue(item["source"].endswith(".mp4"))
            self.assertTrue(item["output"].endswith("-720p.mp4"))
            self.assertFalse(os.path.isabs(item["source"]))
            self.assertNotIn("docs/media", item["output"])

    def test_filters_crop_browser_chrome_and_apply_named_redactions(self):
        filters = {
            item["id"]: build_public_videos._filter(item)
            for item in build_public_videos.PROFILES
        }

        self.assertIn("crop=1706:960:107:120", filters["V01"])
        self.assertIn("crop=1138:640:71:70", filters["V08"])
        self.assertIn("drawbox", filters["V03"])
        self.assertIn("gte(t,28)", filters["V08"])
        self.assertIn("between(t,50,59)", filters["V07"])


if __name__ == "__main__":
    unittest.main()
