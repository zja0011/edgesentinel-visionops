import os
import tempfile
import unittest

from packages.api.evidence_service import (
    EvidenceNotFound,
    EvidenceService,
)


def make_event(primary=None, before=None, after=None):
    return {
        "event_id": "evt_test",
        "evidence_path": primary,
        "details": {
            "before_evidence_path": before,
            "after_evidence_path": after,
        },
    }


class EvidenceServiceTests(unittest.TestCase):
    def test_adds_urls_only_for_recorded_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            service = EvidenceService(directory)
            event = make_event(
                primary="data/evidence/primary.jpg",
                before="data/evidence/before.jpg",
            )

            payload = service.add_urls(event)

            self.assertEqual(
                payload["evidence_urls"],
                {
                    "primary": (
                        "/api/v1/events/evt_test/evidence/primary"
                    ),
                    "before": (
                        "/api/v1/events/evt_test/evidence/before"
                    ),
                },
            )

    def test_resolves_primary_before_and_after_jpegs(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_dir = os.path.join(directory, "data", "evidence")
            os.makedirs(evidence_dir)
            for name in ("primary.jpg", "before.jpg", "after.jpeg"):
                with open(
                    os.path.join(evidence_dir, name),
                    "wb",
                ) as evidence_file:
                    evidence_file.write(b"jpeg")
            service = EvidenceService(directory)
            event = make_event(
                primary="data/evidence/primary.jpg",
                before="data/evidence/before.jpg",
                after="data/evidence/after.jpeg",
            )

            self.assertTrue(
                service.resolve(event, "primary").endswith("primary.jpg")
            )
            self.assertTrue(
                service.resolve(event, "before").endswith("before.jpg")
            )
            self.assertTrue(
                service.resolve(event, "after").endswith("after.jpeg")
            )

    def test_rejects_parent_directory_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            outside_path = os.path.join(directory, "outside.jpg")
            with open(outside_path, "wb") as evidence_file:
                evidence_file.write(b"jpeg")
            service = EvidenceService(directory)
            event = make_event(
                primary="data/evidence/../../outside.jpg",
            )

            with self.assertRaises(EvidenceNotFound):
                service.resolve(event, "primary")

    def test_rejects_absolute_and_non_jpeg_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            evidence_dir = os.path.join(directory, "data", "evidence")
            os.makedirs(evidence_dir)
            text_path = os.path.join(evidence_dir, "secret.txt")
            with open(text_path, "wb") as evidence_file:
                evidence_file.write(b"secret")
            service = EvidenceService(directory)

            with self.assertRaises(EvidenceNotFound):
                service.resolve(
                    make_event(primary=text_path),
                    "primary",
                )
            with self.assertRaises(EvidenceNotFound):
                service.resolve(
                    make_event(primary="data/evidence/secret.txt"),
                    "primary",
                )

    def test_rejects_missing_file_and_unknown_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            service = EvidenceService(directory)
            event = make_event(
                primary="data/evidence/missing.jpg",
            )

            with self.assertRaises(EvidenceNotFound):
                service.resolve(event, "primary")
            with self.assertRaises(EvidenceNotFound):
                service.resolve(event, "thumbnail")


if __name__ == "__main__":
    unittest.main()
