import os
import unittest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


class GitHubRepositoryAssetTests(unittest.TestCase):
    def read(self, relative_path):
        with open(
            os.path.join(PROJECT_DIR, *relative_path.split("/")),
            "r",
            encoding="utf-8",
        ) as input_file:
            return input_file.read()

    def test_license_and_governance_assets_are_present(self):
        license_text = self.read("LICENSE")
        security = self.read("SECURITY.md")
        contributing = self.read("CONTRIBUTING.md")
        notices = self.read("THIRD_PARTY_NOTICES.md")

        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0", license_text)
        self.assertIn("GitHub Security Advisory", security)
        self.assertIn("Python 3.6", contributing)
        self.assertIn("Metadata-reported license", notices)

    def test_ci_is_read_only_and_runs_all_release_gates(self):
        workflow = self.read(".github/workflows/ci.yml")

        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertIn("actions/checkout@v6", workflow)
        self.assertIn("actions/setup-python@v6", workflow)
        self.assertIn("actions/upload-artifact@v7", workflow)
        self.assertIn("apps.repository_publication_gate", workflow)
        self.assertIn("unittest discover -s tests -q", workflow)
        self.assertIn("run_release_provenance_test.sh", workflow)
        self.assertIn("check_release_integrity.sh", workflow)

    def test_python36_backports_are_gated_out_of_newer_ci_runtimes(self):
        requirements = self.read("requirements-api-py36.txt")

        for package in ("dataclasses", "contextvars", "immutables"):
            self.assertIn(
                '{}=='.format(package),
                requirements,
            )
            self.assertIn(
                'python_version < "3.7"',
                next(
                    line
                    for line in requirements.splitlines()
                    if line.startswith('{}=='.format(package))
                ),
            )

    def test_release_requires_annotated_matching_tag_and_bounded_token(self):
        workflow = self.read(".github/workflows/release.yml")

        self.assertIn("contents: write", workflow)
        self.assertIn('test "$GITHUB_REF_NAME" = "v$version"', workflow)
        self.assertIn("git cat-file -t", workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("gh release create", workflow)
        self.assertIn("--verify-tag", workflow)
        self.assertIn("--prerelease", workflow)
        self.assertNotIn("pull_request:", workflow)
        self.assertNotIn("softprops/", workflow)

    def test_ignore_rules_exclude_operational_and_secret_material(self):
        ignore = self.read(".gitignore")

        self.assertIn("data/", ignore)
        self.assertIn("dist/", ignore)
        self.assertIn("configs/zones.json", ignore)
        self.assertIn("*.key", ignore)
        self.assertIn("*.engine", ignore)

    def test_publication_runbook_is_private_first(self):
        runbook = self.read("docs/github-release.md")

        self.assertIn("private repository", runbook)
        self.assertIn("annotated tag", runbook)
        self.assertIn("branch protection", runbook)
        self.assertIn("Git Credential Manager", runbook)


if __name__ == "__main__":
    unittest.main()
