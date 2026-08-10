import os
import unittest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


class ReleaseProvenanceScriptTests(unittest.TestCase):
    def read(self, relative_path):
        with open(
            os.path.join(PROJECT_DIR, *relative_path.split("/")),
            "r",
            encoding="utf-8",
        ) as input_file:
            return input_file.read()

    def test_build_and_verify_wrappers_are_bounded(self):
        build = self.read("scripts/build_release_artifacts.sh")
        verify = self.read("scripts/check_release_integrity.sh")

        self.assertIn("apps.release_provenance build", build)
        self.assertIn("dist/releases", build)
        self.assertIn("apps.release_provenance verify", verify)
        self.assertIn("current release pointer is invalid", verify)
        self.assertNotIn("/etc/edgesentinel-visionops", build)

    def test_acceptance_script_checks_security_boundaries(self):
        script = self.read("scripts/run_release_provenance_test.sh")

        self.assertIn("CycloneDX 1.7 VERIFIED", script)
        self.assertIn("credentials_included", script)
        self.assertIn("absolute_paths_included", script)
        self.assertIn("source_integrity", script)

    def test_release_documentation_covers_publication_boundary(self):
        document = self.read("docs/release-provenance.md")

        self.assertIn("GitHub boundary", document)
        self.assertIn("LICENSE", document)
        self.assertIn("secret scan", document)
        self.assertIn("data/", document)


if __name__ == "__main__":
    unittest.main()
