import os
import tempfile
import unittest

from packages.monitoring.storage import ProjectStorageInventory


def write_bytes(path, size):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as output:
        output.write(b"x" * size)


class ProjectStorageInventoryTests(unittest.TestCase):
    def test_counts_only_fixed_data_categories(self):
        with tempfile.TemporaryDirectory() as directory:
            write_bytes(
                os.path.join(
                    directory,
                    "data",
                    "evidence",
                    "frame.jpg",
                ),
                11,
            )
            write_bytes(
                os.path.join(
                    directory,
                    "data",
                    "events",
                    "events.db",
                ),
                7,
            )
            write_bytes(
                os.path.join(
                    directory,
                    "data",
                    "custom",
                    "record.bin",
                ),
                5,
            )
            write_bytes(
                os.path.join(directory, "outside.bin"),
                101,
            )

            result = ProjectStorageInventory(
                directory,
                cache_seconds=0,
            ).snapshot()
            categories = {
                item["name"]: item
                for item in result["categories"]
            }

            self.assertEqual(result["status"], "COMPLETE")
            self.assertEqual(result["root"], "data")
            self.assertEqual(result["totals"]["file_count"], 3)
            self.assertEqual(result["totals"]["bytes"], 23)
            self.assertEqual(categories["evidence"]["bytes"], 11)
            self.assertEqual(categories["events"]["bytes"], 7)
            self.assertEqual(categories["other"]["bytes"], 5)
            self.assertEqual(len(categories), 9)
            self.assertFalse(result["absolute_paths_included"])
            self.assertTrue(result["read_only"])

    def test_file_limit_returns_partial_bounded_result(self):
        with tempfile.TemporaryDirectory() as directory:
            for index in range(3):
                write_bytes(
                    os.path.join(
                        directory,
                        "data",
                        "logs",
                        "{0}.jsonl".format(index),
                    ),
                    2,
                )

            result = ProjectStorageInventory(
                directory,
                max_files=2,
                cache_seconds=0,
            ).snapshot()

            self.assertEqual(result["status"], "PARTIAL")
            self.assertTrue(result["truncated"])
            self.assertEqual(result["totals"]["file_count"], 2)
            self.assertEqual(result["max_files"], 2)

    def test_cache_avoids_repeated_scans_until_expiry(self):
        with tempfile.TemporaryDirectory() as directory:
            clock = [100.0]
            first_path = os.path.join(
                directory,
                "data",
                "state",
                "one.json",
            )
            write_bytes(first_path, 3)
            inventory = ProjectStorageInventory(
                directory,
                cache_seconds=30,
                monotonic_clock=lambda: clock[0],
            )

            first = inventory.snapshot()
            write_bytes(
                os.path.join(
                    directory,
                    "data",
                    "state",
                    "two.json",
                ),
                4,
            )
            cached = inventory.snapshot()
            clock[0] = 131.0
            refreshed = inventory.snapshot()

            self.assertEqual(first["totals"]["file_count"], 1)
            self.assertEqual(cached["totals"]["file_count"], 1)
            self.assertEqual(refreshed["totals"]["file_count"], 2)

    def test_symlink_is_skipped_without_following_target(self):
        with tempfile.TemporaryDirectory() as directory:
            outside = os.path.join(directory, "outside")
            write_bytes(os.path.join(outside, "secret.bin"), 19)
            data_dir = os.path.join(directory, "data")
            os.makedirs(data_dir)
            link = os.path.join(data_dir, "linked")
            try:
                os.symlink(outside, link)
            except (AttributeError, NotImplementedError, OSError):
                self.skipTest("symlink creation is unavailable")

            result = ProjectStorageInventory(
                directory,
                cache_seconds=0,
            ).snapshot()

            self.assertEqual(result["totals"]["file_count"], 0)
            self.assertEqual(result["totals"]["bytes"], 0)
            self.assertEqual(result["skipped_symlinks"], 1)


if __name__ == "__main__":
    unittest.main()
