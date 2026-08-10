import os
import tempfile
import unittest

from packages.evidence.integrity import (
    EvidenceIntegrityService,
    EvidenceIntegrityUnavailable,
)
from packages.events.schemas import Event
from packages.events.sqlite_store import SqliteEventStore


def append_event(
    database,
    event_id,
    evidence_path=None,
    details=None,
    frame_id=1,
):
    store = SqliteEventStore(database)
    try:
        store.append(
            Event(
                event_type="OBJECT_APPEARED",
                timestamp=(
                    "2026-07-28T20:00:{0:02d}+08:00".format(
                        frame_id
                    )
                ),
                frame_id=frame_id,
                camera_id="camera_01",
                zone_id="global",
                zone_name="Global Scene",
                track_id=None,
                object_class="bottle",
                event_id=event_id,
                evidence_path=evidence_path,
                details=details,
            )
        )
    finally:
        store.close()


def write_file(path, content):
    parent = os.path.dirname(path)
    if not os.path.isdir(parent):
        os.makedirs(parent)
    with open(path, "wb") as output:
        output.write(content)


class EvidenceIntegrityServiceTests(unittest.TestCase):
    def test_validates_jpeg_references_without_modifying_files(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            relative = "data/evidence/valid.jpg"
            evidence = os.path.join(
                directory,
                *relative.split("/"),
            )
            write_file(
                evidence,
                b"\xff\xd8valid-jpeg\xff\xd9",
            )
            append_event(
                database,
                "evt_" + "1" * 32,
                evidence_path=relative,
                details={"after_evidence_path": relative},
            )
            before = os.path.getsize(evidence)

            result = EvidenceIntegrityService(
                directory,
                database,
            ).verify_recent({"limit": 10})

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["checked_event_count"], 1)
            self.assertEqual(
                result["referenced_evidence_count"],
                2,
            )
            self.assertEqual(result["valid_evidence_count"], 2)
            self.assertEqual(
                result["unique_valid_file_count"],
                1,
            )
            self.assertEqual(result["issue_count"], 0)
            self.assertEqual(os.path.getsize(evidence), before)
            self.assertFalse(result["paths_included"])
            self.assertFalse(result["absolute_paths_included"])
            self.assertTrue(result["read_only"])

    def test_reports_missing_invalid_and_unsupported_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            invalid = "data/evidence/invalid.jpg"
            text = "data/evidence/not-image.txt"
            write_file(
                os.path.join(directory, *invalid.split("/")),
                b"not-a-jpeg",
            )
            write_file(
                os.path.join(directory, *text.split("/")),
                b"\xff\xd8text\xff\xd9",
            )
            append_event(
                database,
                "evt_" + "2" * 32,
                evidence_path="data/evidence/missing.jpg",
                frame_id=1,
            )
            append_event(
                database,
                "evt_" + "3" * 32,
                evidence_path=invalid,
                frame_id=2,
            )
            append_event(
                database,
                "evt_" + "4" * 32,
                evidence_path=text,
                frame_id=3,
            )

            result = EvidenceIntegrityService(
                directory,
                database,
            ).verify_recent({"limit": 10})

            self.assertEqual(result["status"], "WARN")
            self.assertEqual(result["issue_count"], 3)
            self.assertEqual(
                {item["code"] for item in result["issues"]},
                {
                    "MISSING_FILE",
                    "INVALID_JPEG",
                    "UNSUPPORTED_TYPE",
                },
            )

    def test_rejects_absolute_and_escaping_paths_without_echoing_them(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            append_event(
                database,
                "evt_" + "5" * 32,
                evidence_path="/etc/passwd",
                frame_id=1,
            )
            append_event(
                database,
                "evt_" + "6" * 32,
                evidence_path="../outside.jpg",
                frame_id=2,
            )

            result = EvidenceIntegrityService(
                directory,
                database,
            ).verify_recent({"limit": 10})

            self.assertEqual(result["issue_count"], 2)
            self.assertTrue(
                all(
                    item["code"] == "UNSAFE_PATH"
                    for item in result["issues"]
                )
            )
            serialized = str(result)
            self.assertNotIn("/etc/passwd", serialized)
            self.assertNotIn("outside.jpg", serialized)

    def test_rejects_symlinked_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            external = os.path.join(directory, "external.jpg")
            write_file(external, b"\xff\xd8external\xff\xd9")
            evidence_dir = os.path.join(
                directory,
                "data",
                "evidence",
            )
            os.makedirs(evidence_dir)
            linked = os.path.join(evidence_dir, "linked.jpg")
            try:
                os.symlink(external, linked)
            except (AttributeError, NotImplementedError, OSError):
                self.skipTest("file symlinks are unavailable")
            append_event(
                database,
                "evt_" + "7" * 32,
                evidence_path="data/evidence/linked.jpg",
            )

            result = EvidenceIntegrityService(
                directory,
                database,
            ).verify_recent({"limit": 10})

            self.assertEqual(result["status"], "WARN")
            self.assertEqual(result["issue_count"], 1)
            self.assertEqual(
                result["issues"][0]["code"],
                "UNSAFE_PATH",
            )

    def test_rejects_unbounded_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            append_event(
                database,
                "evt_" + "8" * 32,
                evidence_path=None,
            )
            service = EvidenceIntegrityService(
                directory,
                database,
            )

            with self.assertRaises(ValueError):
                service.verify_recent({"limit": 101})
            with self.assertRaises(ValueError):
                service.verify_recent(
                    {"limit": 10, "minutes": 1441}
                )

    def test_verifies_one_exact_event_with_hashes_and_urls(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            relative = "data/evidence/exact.jpg"
            content = b"\xff\xd8exact-jpeg\xff\xd9"
            write_file(
                os.path.join(directory, *relative.split("/")),
                content,
            )
            event_id = "evt_" + "9" * 32
            append_event(
                database,
                event_id,
                evidence_path=relative,
                details={"after_evidence_path": relative},
            )

            result = EvidenceIntegrityService(
                directory,
                database,
            ).verify_event({"event_id": event_id})

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(
                result["event"]["event_id"],
                event_id,
            )
            self.assertEqual(
                result["referenced_evidence_count"],
                2,
            )
            self.assertEqual(result["valid_evidence_count"], 2)
            self.assertEqual(result["issue_count"], 0)
            self.assertEqual(
                [item["kind"] for item in result["evidence"]],
                ["primary", "after"],
            )
            for item in result["evidence"]:
                self.assertEqual(item["status"], "VALID")
                self.assertEqual(item["bytes"], len(content))
                self.assertEqual(len(item["sha256"]), 64)
                self.assertIn(event_id, item["url"])
                self.assertNotIn("exact.jpg", str(item))
            self.assertTrue(result["sha256_checked"])
            self.assertFalse(result["paths_included"])

    def test_exact_event_without_evidence_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            event_id = "evt_" + "a" * 32
            append_event(database, event_id)

            result = EvidenceIntegrityService(
                directory,
                database,
            ).verify_event({"event_id": event_id})

            self.assertEqual(result["status"], "NO_EVIDENCE")
            self.assertEqual(result["evidence"], [])
            self.assertEqual(
                result["referenced_evidence_count"],
                0,
            )
            self.assertFalse(result["sha256_checked"])

    def test_exact_event_reports_issue_without_path(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            event_id = "evt_" + "b" * 32
            append_event(
                database,
                event_id,
                evidence_path="data/evidence/missing.jpg",
            )

            result = EvidenceIntegrityService(
                directory,
                database,
            ).verify_event({"event_id": event_id})

            self.assertEqual(result["status"], "WARN")
            self.assertEqual(
                result["evidence"],
                [
                    {
                        "kind": "primary",
                        "status": "MISSING_FILE",
                    }
                ],
            )
            self.assertNotIn("missing.jpg", str(result))

    def test_exact_event_rejects_invalid_or_unknown_id(self):
        with tempfile.TemporaryDirectory() as directory:
            database = os.path.join(directory, "events.db")
            event_id = "evt_" + "c" * 32
            append_event(database, event_id)
            service = EvidenceIntegrityService(
                directory,
                database,
            )

            with self.assertRaises(EvidenceIntegrityUnavailable):
                service.verify_event({"event_id": "../bad"})
            with self.assertRaises(EvidenceIntegrityUnavailable):
                service.verify_event(
                    {"event_id": "evt_" + "d" * 32}
                )


if __name__ == "__main__":
    unittest.main()
