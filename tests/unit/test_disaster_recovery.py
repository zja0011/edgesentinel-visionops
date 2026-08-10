import hashlib
import json
import os
import sqlite3
import tempfile
import unittest

from packages.harness.disaster_recovery import DisasterRecoveryStore


def write_file(path, content):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    mode = "wb" if isinstance(content, bytes) else "w"
    kwargs = {} if mode == "wb" else {"encoding": "utf-8"}
    with open(path, mode, **kwargs) as output_file:
        output_file.write(content)


def create_project(directory):
    write_file(
        os.path.join(directory, "configs", "zones.json"),
        '{"zones": []}\n',
    )
    write_file(
        os.path.join(directory, "data", "evidence", "event.jpg"),
        b"\xff\xd8evidence\xff\xd9",
    )
    write_file(
        os.path.join(
            directory,
            "data",
            "harness",
            "long-term-memory",
            "memory.json",
        ),
        '{"records": []}\n',
    )
    write_file(
        os.path.join(directory, "data", "runtime", "tls", "key.pem"),
        "DO-NOT-BACK-UP",
    )
    database_path = os.path.join(
        directory,
        "data",
        "events",
        "edgesentinel.db",
    )
    parent = os.path.dirname(database_path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    connection = sqlite3.connect(database_path)
    with connection:
        connection.execute(
            "CREATE TABLE events (event_id TEXT PRIMARY KEY, value TEXT)"
        )
        connection.execute(
            "INSERT INTO events VALUES (?, ?)",
            ("evt_1", "present"),
        )
    connection.close()
    return database_path


class DisasterRecoveryStoreTests(unittest.TestCase):
    def test_creates_consistent_bounded_backup_without_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            create_project(directory)
            store = DisasterRecoveryStore(directory)

            result = store.create_backup()
            self.assertEqual(result["status"], "COMPLETE")
            self.assertTrue(result["sqlite_consistent"])
            self.assertFalse(result["credentials_included"])
            self.assertFalse(result["absolute_paths_included"])

            backup_dir = os.path.join(
                directory,
                "data",
                "recovery",
                "backups",
                result["backup_id"],
            )
            with open(
                os.path.join(backup_dir, "manifest.json"),
                "r",
                encoding="utf-8",
            ) as manifest_file:
                manifest = json.load(manifest_file)
            paths = {entry["path"] for entry in manifest["files"]}
            self.assertIn("configs/zones.json", paths)
            self.assertIn("data/events/edgesentinel.db", paths)
            self.assertIn("data/evidence/event.jpg", paths)
            self.assertNotIn("data/runtime/tls/key.pem", paths)
            self.assertFalse(manifest["credentials_included"])

            snapshot_path = os.path.join(
                backup_dir,
                "files",
                "data",
                "events",
                "edgesentinel.db",
            )
            connection = sqlite3.connect(snapshot_path)
            row = connection.execute(
                "SELECT value FROM events WHERE event_id = 'evt_1'"
            ).fetchone()
            connection.close()
            self.assertEqual(row[0], "present")

    def test_status_and_preview_verify_every_payload_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            create_project(directory)
            store = DisasterRecoveryStore(directory)
            result = store.create_backup()

            status = store.get_status({"limit": 5})
            self.assertEqual(status["status"], "COMPLETE")
            self.assertEqual(status["backup_count"], 1)
            preview = store.preview_restore(
                {"backup_id": result["backup_id"]}
            )
            self.assertEqual(preview["status"], "COMPLETE")
            # A consistent SQLite snapshot may differ byte-for-byte from
            # the live WAL database even when its logical rows match.
            self.assertLessEqual(preview["changed_file_count"], 1)
            self.assertTrue(preview["read_only"])

            payload = os.path.join(
                directory,
                "data",
                "recovery",
                "backups",
                result["backup_id"],
                "files",
                "configs",
                "zones.json",
            )
            with open(payload, "ab") as output_file:
                output_file.write(b"tampered")
            with self.assertRaises(RuntimeError):
                store.preview_restore(
                    {"backup_id": result["backup_id"]}
                )

    def test_manifest_cannot_redirect_restore_outside_allowlist(self):
        with tempfile.TemporaryDirectory() as directory:
            create_project(directory)
            store = DisasterRecoveryStore(directory)
            result = store.create_backup()
            backup_dir = os.path.join(
                directory,
                "data",
                "recovery",
                "backups",
                result["backup_id"],
            )
            manifest_path = os.path.join(backup_dir, "manifest.json")
            with open(manifest_path, "r", encoding="utf-8") as input_file:
                manifest = json.load(input_file)
            manifest["files"][0]["path"] = "packages/owned.py"
            with open(manifest_path, "w", encoding="utf-8") as output_file:
                json.dump(manifest, output_file)
            with open(manifest_path, "rb") as input_file:
                digest = hashlib.sha256(input_file.read()).hexdigest()
            write_file(
                os.path.join(backup_dir, "manifest.sha256"),
                digest + "\n",
            )
            with self.assertRaises((ValueError, RuntimeError)):
                store.preview_restore(
                    {"backup_id": result["backup_id"]}
                )

    def test_restore_requires_maintenance_exact_phrase_and_current_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = create_project(directory)
            store = DisasterRecoveryStore(directory)
            result = store.create_backup()
            zones_path = os.path.join(directory, "configs", "zones.json")
            write_file(zones_path, '{"zones": ["changed"]}\n')
            connection = sqlite3.connect(database_path)
            with connection:
                connection.execute(
                    "UPDATE events SET value = 'changed'"
                )
            connection.close()
            preview = store.preview_restore(
                {"backup_id": result["backup_id"]}
            )
            self.assertGreaterEqual(preview["changed_file_count"], 2)

            with self.assertRaises(RuntimeError):
                store.apply_restore(
                    result["backup_id"],
                    preview["plan_id"],
                    store.RESTORE_PHRASE,
                    maintenance_mode=False,
                )
            with self.assertRaises(ValueError):
                store.apply_restore(
                    result["backup_id"],
                    preview["plan_id"],
                    "yes",
                    maintenance_mode=True,
                )
            write_file(zones_path, '{"zones": ["stale"]}\n')
            with self.assertRaises(RuntimeError):
                store.apply_restore(
                    result["backup_id"],
                    preview["plan_id"],
                    store.RESTORE_PHRASE,
                    maintenance_mode=True,
                )

            current_preview = store.preview_restore(
                {"backup_id": result["backup_id"]}
            )
            restored = store.apply_restore(
                result["backup_id"],
                current_preview["plan_id"],
                store.RESTORE_PHRASE,
                maintenance_mode=True,
            )
            self.assertEqual(restored["status"], "COMPLETED")
            self.assertTrue(restored["rollback_available"])
            with open(zones_path, "r", encoding="utf-8") as input_file:
                self.assertEqual(input_file.read(), '{"zones": []}\n')
            connection = sqlite3.connect(database_path)
            value = connection.execute(
                "SELECT value FROM events WHERE event_id = 'evt_1'"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(value, "present")

    def test_rejects_symlinks_in_protected_source(self):
        with tempfile.TemporaryDirectory() as directory:
            create_project(directory)
            target = os.path.join(directory, "outside.txt")
            write_file(target, "outside")
            link = os.path.join(
                directory,
                "data",
                "evidence",
                "link.jpg",
            )
            try:
                os.symlink(target, link)
            except (AttributeError, NotImplementedError, OSError):
                self.skipTest("file symlinks are unavailable")
            store = DisasterRecoveryStore(directory)
            with self.assertRaises(RuntimeError):
                store.create_backup()

    def test_failed_restore_rolls_back_every_preoperation_file(self):
        with tempfile.TemporaryDirectory() as directory:
            database_path = create_project(directory)
            store = DisasterRecoveryStore(directory)
            result = store.create_backup()
            zones_path = os.path.join(directory, "configs", "zones.json")
            evidence_path = os.path.join(
                directory,
                "data",
                "evidence",
                "event.jpg",
            )
            write_file(zones_path, '{"zones": ["before-failure"]}\n')
            write_file(evidence_path, b"before-failure-evidence")
            connection = sqlite3.connect(database_path)
            with connection:
                connection.execute(
                    "UPDATE events SET value = 'before-failure'"
                )
            connection.close()
            preview = store.preview_restore(
                {"backup_id": result["backup_id"]}
            )

            original_replace = store._atomic_replace_from

            def fail_on_backup_evidence(source, target):
                normalized = source.replace(os.sep, "/")
                if (
                    "/backups/" in normalized
                    and target == evidence_path
                ):
                    raise RuntimeError("injected restore failure")
                return original_replace(source, target)

            store._atomic_replace_from = fail_on_backup_evidence
            with self.assertRaises(RuntimeError):
                store.apply_restore(
                    result["backup_id"],
                    preview["plan_id"],
                    store.RESTORE_PHRASE,
                    maintenance_mode=True,
                )

            with open(zones_path, "r", encoding="utf-8") as input_file:
                self.assertEqual(
                    input_file.read(),
                    '{"zones": ["before-failure"]}\n',
                )
            with open(evidence_path, "rb") as input_file:
                self.assertEqual(
                    input_file.read(),
                    b"before-failure-evidence",
                )
            connection = sqlite3.connect(database_path)
            value = connection.execute(
                "SELECT value FROM events WHERE event_id = 'evt_1'"
            ).fetchone()[0]
            connection.close()
            self.assertEqual(value, "before-failure")

    def test_enforces_backup_size_bound_before_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            create_project(directory)
            store = DisasterRecoveryStore(directory, max_bytes=10)
            with self.assertRaises(RuntimeError):
                store.create_backup()
            backups_dir = os.path.join(
                directory,
                "data",
                "recovery",
                "backups",
            )
            self.assertEqual(os.listdir(backups_dir), [])


if __name__ == "__main__":
    unittest.main()
