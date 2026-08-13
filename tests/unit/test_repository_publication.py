import os
import tempfile
import unittest

from packages.harness.repository_publication import RepositoryPublicationGate


class RepositoryPublicationGateTests(unittest.TestCase):
    def write(self, directory, relative_path, content):
        path = os.path.join(directory, *relative_path.split("/"))
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        mode = "wb" if isinstance(content, bytes) else "w"
        kwargs = {} if mode == "wb" else {"encoding": "utf-8"}
        with open(path, mode, **kwargs) as output_file:
            output_file.write(content)
        return path

    def test_safe_bounded_sources_pass_without_exposing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "apps/main.py", "VALUE = 'safe'\n")
            self.write(
                directory,
                "vendor/wheels/example-1.0-py3-none-any.whl",
                b"PK\x03\x04\x00binary",
            )
            gate = RepositoryPublicationGate(directory)

            result = gate.check(
                paths=(
                    "apps/main.py",
                    "vendor/wheels/example-1.0-py3-none-any.whl",
                ),
                require_governance=False,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertFalse(result["credentials_exposed"])
            self.assertFalse(result["secret_values_exposed"])
            self.assertFalse(result["absolute_paths_included"])

    def test_allows_reviewed_public_documentation_images(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(
                directory,
                "docs/media/dashboard/overview.png",
                b"\x89PNG\r\n\x1a\n\x00public-media",
            )
            self.write(
                directory,
                "docs/media/hardware/rig-overview.jpg",
                b"\xff\xd8\xff\x00public-media",
            )
            gate = RepositoryPublicationGate(directory)

            result = gate.check(
                paths=(
                    "docs/media/dashboard/overview.png",
                    "docs/media/hardware/rig-overview.jpg",
                ),
                require_governance=False,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["binary_files"], 2)

    def test_rejects_binary_images_outside_public_media_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "private/capture.png", b"\x89PNG\x00private")
            gate = RepositoryPublicationGate(directory)

            result = gate.check(
                paths=("private/capture.png",),
                require_governance=False,
            )

            self.assertEqual(result["status"], "FAIL")
            self.assertIn(
                "UNEXPECTED_BINARY:private/capture.png",
                result["issues"],
            )

    def test_detects_secret_pattern_without_returning_secret(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = "sk-" + "A" * 32
            self.write(directory, "apps/bad.py", "TOKEN = '{0}'\n".format(secret))
            gate = RepositoryPublicationGate(directory)

            result = gate.check(
                paths=("apps/bad.py",),
                require_governance=False,
            )

            self.assertEqual(result["status"], "FAIL")
            self.assertIn(
                "SECRET_PATTERN_OPENAI_STYLE_API_KEY:apps/bad.py",
                result["issues"],
            )
            self.assertNotIn(secret, str(result))

    def test_rejects_runtime_data_and_credential_files(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "data/events/live.db", b"database")
            self.write(directory, ".env", "KEY=value\n")
            gate = RepositoryPublicationGate(directory)

            result = gate.check(
                paths=("data/events/live.db", ".env"),
                require_governance=False,
            )

            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("FORBIDDEN_PATH:data/" in issue for issue in result["issues"]))
            self.assertIn(
                "FORBIDDEN_CREDENTIAL_FILE:.env",
                result["issues"],
            )

    def test_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "apps/large.py", "12345")
            gate = RepositoryPublicationGate(directory)
            gate.MAX_FILE_BYTES = 4

            result = gate.check(
                paths=("apps/large.py",),
                require_governance=False,
            )

            self.assertIn("FILE_TOO_LARGE:apps/large.py", result["issues"])

    def test_invalid_path_fails_closed_without_crashing_or_exposing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "apps/main.py", "VALUE = 'safe'\n")
            invalid_path = "private\\\\..\\\\secret"
            gate = RepositoryPublicationGate(directory)

            result = gate.check(
                paths=("apps/main.py", invalid_path),
                require_governance=False,
            )

            self.assertEqual(result["status"], "FAIL")
            self.assertIn("INVALID_REPOSITORY_PATH", result["issues"])
            self.assertNotIn(invalid_path, str(result))

    def test_fallback_ignores_gitignored_deployment_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            self.write(directory, "apps/main.py", "VALUE = 'safe'\n")
            self.write(directory, "vendor/pip/launcher.exe", b"MZ\x00binary")
            self.write(directory, "vendor/python/runtime.so", b"\x7fELF\x00binary")
            gate = RepositoryPublicationGate(directory)

            result = gate.check(require_governance=False)

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["scanned_files"], 1)
            self.assertEqual(result["binary_files"], 0)


if __name__ == "__main__":
    unittest.main()
