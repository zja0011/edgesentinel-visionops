import json
import os
import tempfile
import unittest

from packages.harness.retention_tools import (
    RetentionCleanupHistoryTools,
)


class RetentionCleanupHistoryToolsTests(unittest.TestCase):
    def write_records(self, directory, records):
        path = os.path.join(
            directory,
            "data",
            "runtime",
            "retention-cleanup-audit.jsonl",
        )
        os.makedirs(os.path.dirname(path))
        with open(path, "w", encoding="utf-8") as output:
            for record in records:
                output.write(
                    json.dumps(
                        record,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                )
                output.write("\n")
        return path

    def test_missing_audit_returns_empty_complete_history(self):
        with tempfile.TemporaryDirectory() as directory:
            result = RetentionCleanupHistoryTools(
                directory
            ).get_history({"limit": 5})

            self.assertEqual(result["status"], "COMPLETE")
            self.assertFalse(result["audit_exists"])
            self.assertEqual(result["record_count"], 0)
            self.assertEqual(result["records"], [])
            self.assertFalse(result["paths_included"])
            self.assertFalse(result["absolute_paths_included"])
            self.assertTrue(result["read_only"])

    def test_returns_bounded_final_records_without_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            records = []
            for index in range(3):
                cleanup_id = "clean_{0:032x}".format(index + 1)
                records.extend(
                    [
                        {
                            "cleanup_id": cleanup_id,
                            "timestamp": "2026-07-28T19:00:00+08:00",
                            "status": "PREPARED",
                            "plan_id": "ret_" + "a" * 32,
                            "candidate_file_count": index + 2,
                            "candidate_bytes": 100 + index,
                            "candidate_paths": [
                                "data/logs/private-{0}".format(index)
                            ],
                        },
                        {
                            "cleanup_id": cleanup_id,
                            "timestamp": (
                                "2026-07-28T19:00:0{0}+08:00".format(
                                    index
                                )
                            ),
                            "status": (
                                "PARTIAL"
                                if index == 1
                                else "COMPLETED"
                            ),
                            "plan_id": "ret_" + "a" * 32,
                            "deleted_file_count": index + 1,
                            "deleted_bytes": 50 + index,
                            "deleted_paths": [
                                "data/logs/private-{0}".format(index)
                            ],
                            "failed_file_count": (
                                1 if index == 1 else 0
                            ),
                            "failed_paths": [],
                        },
                    ]
                )
            path = self.write_records(directory, records)
            before = os.path.getsize(path)

            result = RetentionCleanupHistoryTools(
                directory
            ).get_history({"limit": 2})

            self.assertEqual(result["status"], "COMPLETE")
            self.assertTrue(result["audit_exists"])
            self.assertEqual(result["record_count"], 3)
            self.assertEqual(result["returned_count"], 2)
            self.assertEqual(
                result["records"][0]["cleanup_id"],
                "clean_{0:032x}".format(3),
            )
            self.assertEqual(
                result["totals"]["deleted_file_count"],
                6,
            )
            self.assertEqual(
                result["totals"]["failed_file_count"],
                1,
            )
            self.assertNotIn(
                "candidate_paths",
                result["records"][0],
            )
            self.assertNotIn(
                "deleted_paths",
                result["records"][0],
            )
            self.assertEqual(os.path.getsize(path), before)

    def test_rejects_symlinked_audit_file(self):
        with tempfile.TemporaryDirectory() as directory:
            external = os.path.join(directory, "external.jsonl")
            with open(external, "w", encoding="utf-8") as output:
                output.write("{}\n")
            runtime = os.path.join(directory, "data", "runtime")
            os.makedirs(runtime)
            audit = os.path.join(
                runtime,
                "retention-cleanup-audit.jsonl",
            )
            try:
                os.symlink(external, audit)
            except (AttributeError, NotImplementedError, OSError):
                self.skipTest("file symlinks are unavailable")

            tools = RetentionCleanupHistoryTools(directory)
            with self.assertRaises(RuntimeError):
                tools.get_history({"limit": 10})


if __name__ == "__main__":
    unittest.main()
