import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import types
import unittest


class RecoveryCapacityManagerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        path = os.path.join(root, "scripts", "recovery_capacity_manager.py")
        fake_fcntl = types.ModuleType("fcntl")
        fake_fcntl.LOCK_EX = 1
        fake_fcntl.LOCK_NB = 2
        fake_fcntl.flock = lambda *unused: None
        original = sys.modules.get("fcntl")
        sys.modules["fcntl"] = fake_fcntl
        try:
            specification = importlib.util.spec_from_file_location(
                "test_recovery_capacity_manager_module",
                path,
            )
            cls.manager = importlib.util.module_from_spec(specification)
            specification.loader.exec_module(cls.manager)
        finally:
            if original is None:
                sys.modules.pop("fcntl", None)
            else:
                sys.modules["fcntl"] = original

    def create_backup(self, directory, backup_id, payload_bytes):
        backup = os.path.join(directory, backup_id)
        os.makedirs(os.path.join(backup, "files", "data"))
        with open(
            os.path.join(backup, "files", "data", "payload.bin"),
            "wb",
        ) as output_file:
            output_file.write(b"x" * payload_bytes)
        manifest = {
            "schema_version": "1.0",
            "status": "COMPLETE",
            "backup_id": backup_id,
            "credentials_included": False,
        }
        manifest_path = os.path.join(backup, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as output_file:
            json.dump(manifest, output_file, sort_keys=True)
        digest = hashlib.sha256()
        with open(manifest_path, "rb") as input_file:
            digest.update(input_file.read())
        with open(
            os.path.join(backup, "manifest.sha256"),
            "w",
            encoding="ascii",
        ) as output_file:
            output_file.write(digest.hexdigest() + "\n")

    def create_export(self, directory, backup_id, created_at, payload_bytes):
        artifact_name = backup_id + ".esdr"
        artifact_path = os.path.join(directory, artifact_name)
        with open(artifact_path, "wb") as output_file:
            output_file.write(b"e" * payload_bytes)
        metadata = {
            "backup_id": backup_id,
            "created_at": created_at,
            "artifact_file": artifact_name,
            "artifact_bytes": payload_bytes,
            "artifact_sha256": "a" * 64,
            "credentials_included": False,
            "plaintext_persisted": False,
        }
        with open(
            artifact_path + ".json",
            "w",
            encoding="utf-8",
        ) as output_file:
            json.dump(metadata, output_file)

    def test_plan_gates_and_deletes_only_unretained_local_backups(self):
        with tempfile.TemporaryDirectory() as directory:
            backups = os.path.join(directory, "backups")
            exports = os.path.join(directory, "exports")
            os.makedirs(backups)
            os.makedirs(exports)
            backup_ids = [
                "dr_" + ("{0:032x}".format(index))
                for index in range(1, 6)
            ]
            for backup_id in backup_ids:
                self.create_backup(backups, backup_id, 128)
            self.create_export(
                exports,
                backup_ids[4],
                "2026-08-10T17:55:56.069+08:00",
                256,
            )
            self.create_export(
                exports,
                backup_ids[3],
                "2026-08-03T17:55:56.069+08:00",
                256,
            )
            plan = self.manager.build_plan(
                backups,
                exports,
                keep_count=4,
                maximum_bytes=536870912,
            )
            self.assertRegex(plan["plan_id"], r"^rcp_[0-9a-f]{32}$")
            self.assertEqual(len(plan["retained_exports"]), 2)
            self.assertEqual(len(plan["local_candidates"]), 3)

            audit_path = os.path.join(directory, "audit.jsonl")
            with self.assertRaises(self.manager.CapacityError):
                self.manager.apply_plan(
                    plan,
                    "rcp_" + "0" * 32,
                    self.manager.CONFIRMATION,
                    backups,
                    audit_path,
                )
            self.assertEqual(len(os.listdir(backups)), 5)

            result = self.manager.apply_plan(
                plan,
                plan["plan_id"],
                self.manager.CONFIRMATION,
                backups,
                audit_path,
            )
            self.assertEqual(result["deleted_local_backups"], 3)
            self.assertEqual(set(os.listdir(backups)), set(backup_ids[3:]))
            retained_artifacts = sorted(
                name for name in os.listdir(exports) if name.endswith(".esdr")
            )
            self.assertEqual(
                retained_artifacts,
                sorted([
                    backup_ids[3] + ".esdr",
                    backup_ids[4] + ".esdr",
                ]),
            )
            with open(audit_path, "r", encoding="utf-8") as input_file:
                audit = [json.loads(line) for line in input_file]
            self.assertEqual(
                [item["status"] for item in audit],
                ["PREPARED", "COMPLETED"],
            )
            self.assertTrue(
                all(item["encrypted_exports_deleted"] == 0 for item in audit)
            )


if __name__ == "__main__":
    unittest.main()
