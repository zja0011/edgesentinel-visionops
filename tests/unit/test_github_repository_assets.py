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

    def test_readme_is_a_navigable_project_homepage(self):
        readme = self.read("README.md")

        self.assertIn("EdgeSentinel「边缘智哨」", readme)
        self.assertIn("## 目录", readme)
        self.assertIn("## 系统架构", readme)
        self.assertIn("```mermaid", readme)
        self.assertIn("docs/media-capture-guide.md", readme)
        self.assertIn("docs/implementation-journal.md", readme)
        self.assertLess(len(readme.splitlines()), 500)

    def test_media_capture_plan_requires_real_evidence(self):
        guide = self.read("docs/media-capture-guide.md")
        checklist = self.read("docs/media/shot-checklist.md")
        media_readme = self.read("docs/media/README.md")
        readme = self.read("README.md")
        overview = os.path.join(
            PROJECT_DIR,
            "docs",
            "media",
            "hardware",
            "rig-overview.jpg",
        )

        self.assertIn("P0：发布首页前必须有", guide)
        self.assertIn("一镜到底视频脚本", guide)
        self.assertIn("不要使用生成图片替代实拍", guide)
        self.assertIn("API Key", guide)
        self.assertIn("GitHub Release", media_readme)
        self.assertIn("真实实验过程", media_readme)
        self.assertIn("video-gallery.html", media_readme)
        self.assertIn("全功能素材拍摄清单", guide)
        for token in (
            "硬件实物照片",
            "Dashboard 核心截图",
            "视觉与事件闭环截图",
            "Agent Harness、MCP 与安全证明",
            "运维、恢复与发布截图",
            "全功能视频清单",
            "V20",
            "DEMO_WEEKLY",
            "公开前脱敏检查",
        ):
            self.assertIn(token, checklist)
        self.assertIn("docs/media/hardware/rig-overview.jpg", readme)
        self.assertIn("docs/media/dashboard/overview.png", readme)
        self.assertIn("在线播放 8 段原始演示", readme)
        self.assertIn("video-original-manifest.json", readme)
        self.assertNotIn("统一处理为 H.264 720p", readme)
        self.assertIn("## 硬件与器材", readme)
        self.assertIn("USB Wi‑Fi 适配器", readme)
        self.assertIn("PC 电脑", readme)
        self.assertTrue(os.path.isfile(overview))
        self.assertGreater(os.path.getsize(overview), 100000)

    def test_public_documentation_uses_reader_facing_placeholders(self):
        public_documents = (
            "README.md",
            "docs/media/README.md",
            "docs/media-capture-guide.md",
            "docs/media/shot-checklist.md",
            "docs/implementation-journal.md",
            "docs/tls-operations.md",
            "docs/disaster-recovery.md",
        )
        prohibited_fragments = (
            "H:" + "\\AI_learning",
            "192." + "168.1.101",
            "nvidia" + "@",
            "/home/" + "nvidia",
            "按维护者" + "决定",
            "交付给 " + "Codex",
            "Codex " + "会检查",
            "字节" + "一致",
        )

        for relative_path in public_documents:
            content = self.read(relative_path)
            for fragment in prohibited_fragments:
                self.assertNotIn(
                    fragment,
                    content,
                    "{} contains a private environment value or internal "
                    "handoff phrase".format(relative_path),
                )

        readme = self.read("README.md")
        self.assertIn("便于访客直接核对系统的运行形态与工程闭环", readme)
        self.assertIn("总览长图依次展示实时视觉", readme)

    def test_github_pages_discovery_assets_are_machine_readable(self):
        homepage = self.read("docs/index.html")
        gallery = self.read("docs/video-gallery.html")
        robots = self.read("docs/robots.txt")
        sitemap = self.read("docs/sitemap.xml")
        llms = self.read("docs/llms.txt")
        citation = self.read("CITATION.cff")

        self.assertIn('rel="canonical"', homepage)
        self.assertIn('"@type": "SoftwareSourceCode"', homepage)
        self.assertIn('property="og:image"', homepage)
        self.assertIn("Jetson Nano 视觉 Agent Harness", homepage)
        self.assertIn('href="video-gallery.html"', homepage)
        self.assertIn('rel="canonical"', gallery)
        self.assertIn("OAI-SearchBot", robots)
        self.assertIn("User-agent: GPTBot\nDisallow: /", robots)
        self.assertIn("sitemap.xml", robots)
        self.assertIn(
            "https://zja0011.github.io/edgesentinel-visionops/",
            sitemap,
        )
        self.assertIn("## Authoritative links", llms)
        self.assertIn("## Important limitations", llms)
        self.assertIn("credentials", llms.lower())
        self.assertIn("cff-version: 1.2.0", citation)
        self.assertIn("Apache-2.0", citation)
        self.assertIn("repository-code:", citation)


if __name__ == "__main__":
    unittest.main()
