import json
import os
import subprocess
import sys
import tempfile
import unittest

from packages.events.sqlite_store import SqliteEventStore
from packages.harness.disaster_recovery import DisasterRecoveryStore
from packages.harness.recovery_export import (
    EncryptedRecoveryExport,
    RecoveryExportError,
)


class EncryptedRecoveryExportTests(unittest.TestCase):
    def build_project(self, directory):
        config_dir = os.path.join(directory, "configs")
        os.makedirs(config_dir)
        with open(
            os.path.join(config_dir, "zones.json"),
            "w",
            encoding="utf-8",
        ) as output_file:
            output_file.write('{"zones": []}\n')
        database = os.path.join(
            directory,
            "data",
            "events",
            "edgesentinel.db",
        )
        SqliteEventStore(database).close()
        return DisasterRecoveryStore(directory).create_backup()

    def test_encrypts_authenticates_and_verifies_without_plaintext(self):
        with tempfile.TemporaryDirectory() as directory:
            created = self.build_project(directory)
            output_dir = os.path.join(directory, "exports")
            service = EncryptedRecoveryExport()
            secret = b"correct horse battery staple"

            exported = service.create(
                directory,
                created["backup_id"],
                output_dir,
                secret,
            )
            artifact = os.path.join(output_dir, exported["artifact_file"])
            metadata_path = artifact + ".json"
            verified = service.verify(artifact, metadata_path, secret)

            self.assertEqual(exported["status"], "VERIFIED")
            self.assertEqual(verified["status"], "VERIFIED")
            self.assertEqual(
                verified["backup"]["manifest_sha256"],
                created["manifest_sha256"],
            )
            self.assertFalse(exported["plaintext_persisted"])
            self.assertEqual(
                [name for name in os.listdir(output_dir) if name.endswith(".tar.gz")],
                [],
            )
            with open(metadata_path, "r", encoding="utf-8") as input_file:
                metadata = json.load(input_file)
            self.assertEqual(metadata["encryption"], "AES-256-CBC")
            self.assertEqual(metadata["authentication"], "HMAC-SHA256")
            self.assertNotIn(secret.decode("ascii"), str(metadata))

    def test_wrong_secret_and_tampered_artifact_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            created = self.build_project(directory)
            output_dir = os.path.join(directory, "exports")
            service = EncryptedRecoveryExport()
            secret = b"correct horse battery staple"
            exported = service.create(
                directory,
                created["backup_id"],
                output_dir,
                secret,
            )
            artifact = os.path.join(output_dir, exported["artifact_file"])
            metadata = artifact + ".json"
            with self.assertRaises(RecoveryExportError):
                service.verify(
                    artifact,
                    metadata,
                    b"this is the wrong passphrase",
                )
            with open(artifact, "r+b") as output_file:
                first = output_file.read(1)
                output_file.seek(0)
                output_file.write(bytes([first[0] ^ 1]))
            with self.assertRaises(RecoveryExportError):
                service.verify(artifact, metadata, secret)

    def test_drill_restores_only_into_disposable_project(self):
        with tempfile.TemporaryDirectory() as directory:
            created = self.build_project(directory)
            source_database = os.path.join(
                directory,
                "data",
                "events",
                "edgesentinel.db",
            )
            source_digest = EncryptedRecoveryExport._sha256_file(
                source_database
            )
            output_dir = os.path.join(directory, "exports")
            service = EncryptedRecoveryExport()
            secret = b"correct horse battery staple"
            exported = service.create(
                directory,
                created["backup_id"],
                output_dir,
                secret,
            )
            artifact = os.path.join(output_dir, exported["artifact_file"])

            result = service.drill(
                artifact,
                artifact + ".json",
                secret,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["mode"], "ISOLATED_RESTORE_DRILL")
            self.assertEqual(
                result["restored_file_count"],
                result["file_count"],
            )
            self.assertEqual(
                result["post_restore_verified_files"],
                result["file_count"],
            )
            self.assertTrue(result["sqlite_consistent"])
            self.assertTrue(result["isolated"])
            self.assertFalse(result["production_modified"])
            self.assertFalse(result["plaintext_persisted"])
            self.assertEqual(
                EncryptedRecoveryExport._sha256_file(source_database),
                source_digest,
            )

    def test_operator_scripts_keep_key_out_of_arguments_and_plaintext(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        with open(
            os.path.join(root, "scripts", "configure_recovery_export_key.sh"),
            "r",
            encoding="utf-8",
        ) as input_file:
            configure = input_file.read()
        with open(
            os.path.join(root, "scripts", "export_encrypted_recovery_backup.sh"),
            "r",
            encoding="utf-8",
        ) as input_file:
            export = input_file.read()
        self.assertIn("root:root 600", configure)
        self.assertIn("read -r -s", configure)
        self.assertIn("credential already exists", configure)
        self.assertIn("--key-file", export)
        self.assertIn('cd "$project_dir"', export)
        self.assertIn("Private plaintext archive persisted: False", export)
        self.assertNotIn("--passphrase", export)

    def test_cli_reports_invalid_passphrase_without_traceback(self):
        root = os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..")
        )
        with tempfile.TemporaryDirectory() as directory:
            key_file = os.path.join(directory, "test.key")
            with open(key_file, "wb") as output_file:
                output_file.write(b"too-short\n")
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "apps.recovery_export",
                    "verify",
                    "--artifact",
                    "missing.esdr",
                    "--metadata",
                    "missing.esdr.json",
                    "--key-file",
                    key_file,
                ],
                cwd=root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = process.communicate()
            self.assertEqual(process.returncode, 1)
            self.assertEqual(stdout, b"")
            self.assertIn(b"Recovery export failed:", stderr)
            self.assertNotIn(b"Traceback", stderr)


if __name__ == "__main__":
    unittest.main()
