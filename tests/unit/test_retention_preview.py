import os
import tempfile
import unittest

from packages.monitoring.retention import DataRetentionPreview


NOW = 2000000000.0


def write_aged_file(path, size, age_days):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as output:
        output.write(b"x" * size)
    modified = NOW - float(age_days) * 86400.0
    os.utime(path, (modified, modified))


class DataRetentionPreviewTests(unittest.TestCase):
    def build_preview(self, directory, **kwargs):
        return DataRetentionPreview(
            directory,
            cache_seconds=0,
            epoch_clock=lambda: NOW,
            monotonic_clock=lambda: 1.0,
            **kwargs
        ).preview()

    def test_previews_old_files_but_keeps_newest_five(self):
        with tempfile.TemporaryDirectory() as directory:
            for index in range(7):
                write_aged_file(
                    os.path.join(
                        directory,
                        "data",
                        "logs",
                        "frame-{0}.jsonl".format(index),
                    ),
                    index + 1,
                    10 - index,
                )

            result = self.build_preview(directory)
            candidates = result["candidate_files"]

            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["mode"], "PREVIEW_ONLY")
            self.assertEqual(
                result["candidates"]["file_count"],
                2,
            )
            self.assertEqual(
                [item["path"] for item in candidates],
                [
                    "data/logs/frame-0.jsonl",
                    "data/logs/frame-1.jsonl",
                ],
            )
            self.assertEqual(result["candidates"]["bytes"], 3)
            self.assertFalse(result["delete_performed"])
            self.assertTrue(result["read_only"])
            self.assertTrue(
                os.path.isfile(
                    os.path.join(
                        directory,
                        "data",
                        "logs",
                        "frame-0.jsonl",
                    )
                )
            )

    def test_protects_evidence_events_and_runtime_control(self):
        with tempfile.TemporaryDirectory() as directory:
            write_aged_file(
                os.path.join(
                    directory,
                    "data",
                    "evidence",
                    "old.jpg",
                ),
                101,
                100,
            )
            write_aged_file(
                os.path.join(
                    directory,
                    "data",
                    "events",
                    "edgesentinel.db",
                ),
                103,
                100,
            )
            write_aged_file(
                os.path.join(
                    directory,
                    "data",
                    "runtime",
                    "service.json",
                ),
                107,
                100,
            )

            result = self.build_preview(directory)

            self.assertEqual(
                result["candidates"]["file_count"],
                0,
            )
            self.assertEqual(result["candidates"]["bytes"], 0)
            self.assertIn(
                "data/evidence",
                result["protected_scopes"],
            )
            self.assertIn(
                "data/runtime/service.json",
                result["protected_scopes"],
            )
            self.assertFalse(result["absolute_paths_included"])

    def test_runtime_only_matches_managed_log_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            for index in range(7):
                write_aged_file(
                    os.path.join(
                        directory,
                        "data",
                        "runtime",
                        "edgesentinel-{0}.log".format(index),
                    ),
                    5,
                    20 - index,
                )
            write_aged_file(
                os.path.join(
                    directory,
                    "data",
                    "runtime",
                    "unrelated.log",
                ),
                99,
                100,
            )

            result = self.build_preview(directory)

            self.assertEqual(
                result["candidates"]["file_count"],
                2,
            )
            self.assertTrue(
                all(
                    item["path"].startswith(
                        "data/runtime/edgesentinel-"
                    )
                    for item in result["candidate_files"]
                )
            )
            self.assertFalse(
                any(
                    item["path"].endswith("unrelated.log")
                    for item in result["candidate_files"]
                )
            )

    def test_bounds_scan_and_returned_candidate_list(self):
        with tempfile.TemporaryDirectory() as directory:
            for index in range(9):
                write_aged_file(
                    os.path.join(
                        directory,
                        "data",
                        "logs",
                        "{0}.log".format(index),
                    ),
                    1,
                    30 - index,
                )

            result = self.build_preview(
                directory,
                candidate_limit=2,
            )

            self.assertEqual(
                result["candidates"]["file_count"],
                4,
            )
            self.assertEqual(
                result["candidates"]["returned_count"],
                2,
            )
            self.assertTrue(
                result["candidate_files_truncated"]
            )
            self.assertEqual(len(result["candidate_files"]), 2)

            bounded = self.build_preview(
                directory,
                max_files=3,
            )
            self.assertEqual(bounded["status"], "PARTIAL")
            self.assertTrue(bounded["truncated"])
            self.assertEqual(
                bounded["scanned"]["file_count"],
                3,
            )

    def test_skips_symlink_without_following_target(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = os.path.join(directory, "outside")
            write_aged_file(
                os.path.join(outside, "secret.log"),
                100,
                100,
            )
            logs = os.path.join(directory, "data", "logs")
            os.makedirs(logs)
            link = os.path.join(logs, "linked")
            try:
                os.symlink(outside, link)
            except (AttributeError, NotImplementedError, OSError):
                self.skipTest("symlink creation is unavailable")

            result = self.build_preview(directory)

            self.assertEqual(result["scanned"]["file_count"], 0)
            self.assertEqual(
                result["candidates"]["file_count"],
                0,
            )
            self.assertEqual(result["skipped_symlinks"], 1)


if __name__ == "__main__":
    unittest.main()
