import json
import os
import tempfile
import unittest

from packages.harness.release_provenance import (
    ReleaseProvenance,
    ReleaseProvenanceError,
)


class ReleaseProvenanceTests(unittest.TestCase):
    def build_fixture(self, directory):
        files = {
            "VERSION": "0.1.0-dev.1\n",
            "requirements-api-py36.txt": (
                "# pinned\nfastapi==0.83.0\nuvicorn==0.16.0\n"
            ),
            "README.md": "# Fixture\n",
            "apps/main.py": "print('fixture')\n",
            "packages/example.py": "VALUE = 1\n",
            "configs/zones.default.json": "{}\n",
            "configs/zones.json": "{\"runtime\": true}\n",
            "vendor/wheels/fastapi-0.83.0-py3-none-any.whl": "wheel-a",
            "vendor/wheels/uvicorn-0.16.0-py3-none-any.whl": "wheel-b",
        }
        for relative_path, content in files.items():
            path = os.path.join(directory, *relative_path.split("/"))
            parent = os.path.dirname(path)
            if not os.path.isdir(parent):
                os.makedirs(parent)
            with open(path, "w", encoding="utf-8") as output_file:
                output_file.write(content)
        return ReleaseProvenance(directory)

    def test_build_is_deterministic_and_excludes_runtime_data(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_fixture(directory)

            first_manifest, first_sbom = service.build()
            second_manifest, second_sbom = service.build()

            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual(first_sbom, second_sbom)
            self.assertRegex(
                first_manifest["release_id"],
                r"^esv_0_1_0_dev_1_[0-9a-f]{16}$",
            )
            paths = [item["path"] for item in first_manifest["files"]]
            self.assertIn("configs/zones.default.json", paths)
            self.assertNotIn("configs/zones.json", paths)
            self.assertFalse(
                first_manifest["security"]["credentials_included"]
            )
            self.assertNotIn(directory, json.dumps(first_manifest))

    def test_sbom_lists_pinned_packages_and_distribution_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_fixture(directory)
            unused_manifest, sbom = service.build()

            self.assertEqual(sbom["bomFormat"], "CycloneDX")
            self.assertEqual(sbom["specVersion"], "1.7")
            self.assertTrue(sbom["serialNumber"].startswith("urn:uuid:"))
            libraries = [
                item for item in sbom["components"]
                if item["type"] == "library"
            ]
            distributions = [
                item for item in sbom["components"]
                if item["type"] == "file"
            ]
            self.assertEqual(len(libraries), 2)
            self.assertEqual(len(distributions), 2)
            self.assertTrue(all(item["scope"] == "required" for item in libraries))
            self.assertTrue(all(len(item["hashes"][0]["content"]) == 64 for item in distributions))

    def test_written_release_verifies_and_detects_source_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_fixture(directory)
            output_root = os.path.join(directory, "release-output")
            created = service.write(output_root)
            manifest_path = os.path.join(
                output_root,
                *created["manifest"].split("/"),
            )

            matched = service.verify(manifest_path)
            with open(
                os.path.join(directory, "packages", "example.py"),
                "a",
                encoding="utf-8",
            ) as source_file:
                source_file.write("CHANGED = True\n")
            mismatched = service.verify(manifest_path)

            self.assertEqual(matched["status"], "PASS")
            self.assertTrue(matched["sbom_verified"])
            self.assertEqual(mismatched["status"], "FAIL")
            self.assertIn(
                "FILE_SIZE_MISMATCH:packages/example.py",
                mismatched["issues"],
            )

    def test_verification_detects_new_allowlisted_source(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_fixture(directory)
            output_root = os.path.join(directory, "release-output")
            created = service.write(output_root)
            manifest_path = os.path.join(
                output_root,
                *created["manifest"].split("/"),
            )
            with open(
                os.path.join(directory, "apps", "unexpected.py"),
                "w",
                encoding="utf-8",
            ) as source_file:
                source_file.write("VALUE = 2\n")

            result = service.verify(manifest_path)

            self.assertEqual(result["status"], "FAIL")
            self.assertIn(
                "UNEXPECTED_FILE:apps/unexpected.py",
                result["issues"],
            )

    def test_rejects_unpinned_dependency(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_fixture(directory)
            with open(
                os.path.join(directory, "requirements-api-py36.txt"),
                "w",
                encoding="utf-8",
            ) as requirement_file:
                requirement_file.write("fastapi>=0.83.0\n")

            with self.assertRaises(ReleaseProvenanceError):
                service.build()

    @unittest.skipUnless(hasattr(os, "symlink"), "symlink unavailable")
    def test_rejects_symlinked_release_source(self):
        with tempfile.TemporaryDirectory() as directory:
            service = self.build_fixture(directory)
            target = os.path.join(directory, "outside.py")
            with open(target, "w", encoding="utf-8") as target_file:
                target_file.write("secret = True\n")
            link = os.path.join(directory, "apps", "linked.py")
            try:
                os.symlink(target, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlink creation is unavailable")

            with self.assertRaises(ReleaseProvenanceError):
                service.build()


if __name__ == "__main__":
    unittest.main()
