import json
import os
import tempfile
import unittest

from packages.harness.retention_tools import RetentionCleanupTools
from packages.monitoring.retention import DataRetentionPreview


NOW = 2000000000.0


def write_old_file(path, size=1, age_days=20):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as output:
        output.write(b"x" * size)
    modified = NOW - float(age_days) * 86400.0
    os.utime(path, (modified, modified))


class RetentionCleanupToolsTests(unittest.TestCase):
    def build_tools(self, directory):
        previewer = DataRetentionPreview(
            directory,
            cache_seconds=0,
            epoch_clock=lambda: NOW,
            monotonic_clock=lambda: 1.0,
        )
        return previewer, RetentionCleanupTools(
            directory,
            previewer=previewer,
        )

    def create_candidates(self, directory):
        paths = []
        for index in range(7):
            path = os.path.join(
                directory,
                "data",
                "logs",
                "{0}.jsonl".format(index),
            )
            write_old_file(
                path,
                size=index + 1,
                age_days=30 - index,
            )
            paths.append(path)
        return paths

    def test_deletes_only_exact_confirmed_plan_and_audits(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.create_candidates(directory)
            previewer, tools = self.build_tools(directory)
            preview = previewer.preview()
            candidate_paths = [
                item["path"]
                for item in preview["candidate_files"]
            ]

            result = tools.cleanup(
                {
                    "plan_id": preview["plan_id"],
                    "candidate_paths": candidate_paths,
                }
            )

            self.assertEqual(result["status"], "COMPLETED")
            self.assertEqual(result["deleted_file_count"], 2)
            self.assertEqual(result["deleted_bytes"], 3)
            self.assertEqual(result["failed_file_count"], 0)
            self.assertTrue(result["delete_performed"])
            self.assertFalse(result["read_only"])
            self.assertFalse(result["absolute_paths_included"])
            self.assertFalse(os.path.exists(paths[0]))
            self.assertFalse(os.path.exists(paths[1]))
            self.assertTrue(
                all(os.path.isfile(path) for path in paths[2:])
            )

            audit_path = os.path.join(
                directory,
                *result["audit_path"].split("/"),
            )
            with open(
                audit_path,
                "r",
                encoding="utf-8",
            ) as audit_file:
                records = [
                    json.loads(line) for line in audit_file
                ]
            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["status"], "PREPARED")
            self.assertEqual(records[1]["status"], "COMPLETED")
            self.assertEqual(
                records[0]["cleanup_id"],
                records[1]["cleanup_id"],
            )

    def test_rejects_wrong_plan_without_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.create_candidates(directory)
            previewer, tools = self.build_tools(directory)
            preview = previewer.preview()

            with self.assertRaises(RuntimeError):
                tools.cleanup(
                    {
                        "plan_id": "ret_" + "0" * 32,
                        "candidate_paths": [
                            item["path"]
                            for item in preview[
                                "candidate_files"
                            ]
                        ],
                    }
                )

            self.assertTrue(all(os.path.isfile(path) for path in paths))
            self.assertFalse(os.path.exists(tools.audit_path))

    def test_rejects_changed_candidate_without_deleting(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.create_candidates(directory)
            previewer, tools = self.build_tools(directory)
            preview = previewer.preview()
            with open(paths[0], "ab") as changed:
                changed.write(b"changed")

            with self.assertRaises(RuntimeError):
                tools.cleanup(
                    {
                        "plan_id": preview["plan_id"],
                        "candidate_paths": [
                            item["path"]
                            for item in preview[
                                "candidate_files"
                            ]
                        ],
                    }
                )

            self.assertTrue(all(os.path.isfile(path) for path in paths))
            self.assertFalse(os.path.exists(tools.audit_path))

    def test_rejects_parent_directory_replaced_by_symlink(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self.create_candidates(directory)
            previewer, tools = self.build_tools(directory)
            preview = previewer.preview()
            logs_path = os.path.join(directory, "data", "logs")
            moved_path = os.path.join(
                directory,
                "data",
                "logs-original",
            )
            os.rename(logs_path, moved_path)
            try:
                os.symlink(moved_path, logs_path)
            except (AttributeError, NotImplementedError, OSError):
                os.rename(moved_path, logs_path)
                self.skipTest(
                    "directory symlinks are unavailable"
                )

            with self.assertRaises((RuntimeError, ValueError)):
                tools.cleanup(
                    {
                        "plan_id": preview["plan_id"],
                        "candidate_paths": [
                            item["path"]
                            for item in preview[
                                "candidate_files"
                            ]
                        ],
                    }
                )

            self.assertTrue(
                all(
                    os.path.isfile(
                        os.path.join(
                            moved_path,
                            os.path.basename(path),
                        )
                    )
                    for path in paths
                )
            )
            self.assertFalse(os.path.exists(tools.audit_path))

    def test_rejects_protected_and_unlisted_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            self.create_candidates(directory)
            protected = os.path.join(
                directory,
                "data",
                "evidence",
                "important.jpg",
            )
            write_old_file(protected, size=50, age_days=100)
            previewer, tools = self.build_tools(directory)
            preview = previewer.preview()

            with self.assertRaises(RuntimeError):
                tools.cleanup(
                    {
                        "plan_id": preview["plan_id"],
                        "candidate_paths": [
                            "data/evidence/important.jpg"
                        ],
                    }
                )

            self.assertTrue(os.path.isfile(protected))
            self.assertFalse(os.path.exists(tools.audit_path))


if __name__ == "__main__":
    unittest.main()
