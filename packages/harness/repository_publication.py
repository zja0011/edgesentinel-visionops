"""Fail-closed checks for publishing the repository."""

import os
import re
import subprocess


class RepositoryPublicationGate(object):
    SCHEMA_VERSION = "1.0"
    MAX_FILES = 4096
    MAX_TOTAL_BYTES = 100 * 1024 * 1024
    MAX_FILE_BYTES = 25 * 1024 * 1024
    MAX_TEXT_SCAN_BYTES = 2 * 1024 * 1024
    MAX_ISSUES = 100
    REQUIRED_FILES = (
        "LICENSE",
        "NOTICE",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "THIRD_PARTY_NOTICES.md",
        ".github/workflows/ci.yml",
        ".github/workflows/release.yml",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/ISSUE_TEMPLATE/config.yml",
        ".github/pull_request_template.md",
    )
    FORBIDDEN_PREFIXES = (
        "data/",
        "dist/",
        ".venv/",
        ".codex/",
        ".agents/",
    )
    FORBIDDEN_PATHS = (
        "configs/zones.json",
    )
    FORBIDDEN_SUFFIXES = (
        ".engine",
        ".db",
        ".sqlite",
        ".sqlite3",
        ".jsonl",
        ".log",
        ".key",
        ".pem",
        ".p12",
        ".pfx",
        ".crt",
    )
    SECRET_PATTERNS = (
        (
            "PRIVATE_KEY",
            re.compile(
                br"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"
            ),
        ),
        (
            "OPENAI_STYLE_API_KEY",
            re.compile(br"\bsk-[A-Za-z0-9_-]{20,}\b"),
        ),
        (
            "GITHUB_CLASSIC_TOKEN",
            re.compile(br"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
        ),
        (
            "GITHUB_FINE_GRAINED_TOKEN",
            re.compile(br"\bgithub_pat_[A-Za-z0-9_]{30,}\b"),
        ),
        (
            "AWS_ACCESS_KEY",
            re.compile(br"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
        ),
        (
            "EDGESENTINEL_PASSWORD_HASH",
            re.compile(
                br"EDGESENTINEL_AUTH_ADMIN_PASSWORD_HASH="
                br"pbkdf2_sha256\$[0-9]{5,7}\$[0-9a-f]{32}\$"
                br"[0-9a-f]{64}"
            ),
        ),
    )

    def __init__(self, project_dir):
        self.project_dir = os.path.realpath(os.path.abspath(project_dir))
        if not os.path.isdir(self.project_dir):
            raise ValueError("project directory does not exist")

    def check(self, paths=None, require_governance=True):
        git_repository = self._is_git_repository()
        tracked_files_only = False
        if paths is None:
            paths = self._git_files() if git_repository else None
            if paths:
                tracked_files_only = True
            else:
                paths = self._fallback_files()
        normalized_paths = sorted(set(
            self._normalize_relative_path(path) for path in paths
        ))
        issues = []
        if len(normalized_paths) > self.MAX_FILES:
            issues.append("FILE_COUNT_LIMIT_EXCEEDED")
        total_bytes = 0
        scanned_files = 0
        binary_files = 0
        for relative_path in normalized_paths[:self.MAX_FILES]:
            path_issues = self._path_issues(relative_path)
            issues.extend(path_issues)
            lexical_path = os.path.abspath(os.path.join(
                self.project_dir,
                relative_path.replace("/", os.sep),
            ))
            if not self._is_within(lexical_path, self.project_dir):
                issues.append("PATH_ESCAPE:{0}".format(relative_path))
                continue
            if os.path.islink(lexical_path):
                issues.append("SYMLINK:{0}".format(relative_path))
                continue
            if not os.path.isfile(lexical_path):
                issues.append("MISSING_FILE:{0}".format(relative_path))
                continue
            size_bytes = int(os.path.getsize(lexical_path))
            total_bytes += size_bytes
            scanned_files += 1
            if size_bytes > self.MAX_FILE_BYTES:
                issues.append("FILE_TOO_LARGE:{0}".format(relative_path))
            if size_bytes <= self.MAX_TEXT_SCAN_BYTES:
                with open(lexical_path, "rb") as input_file:
                    content = input_file.read(self.MAX_TEXT_SCAN_BYTES + 1)
                if b"\x00" in content:
                    binary_files += 1
                    if not self._allowed_binary(relative_path):
                        issues.append(
                            "UNEXPECTED_BINARY:{0}".format(relative_path)
                        )
                else:
                    for secret_name, pattern in self.SECRET_PATTERNS:
                        if pattern.search(content):
                            issues.append(
                                "SECRET_PATTERN_{0}:{1}".format(
                                    secret_name,
                                    relative_path,
                                )
                            )
        if total_bytes > self.MAX_TOTAL_BYTES:
            issues.append("REPOSITORY_SIZE_LIMIT_EXCEEDED")
        if require_governance:
            for required_path in self.REQUIRED_FILES:
                if required_path not in normalized_paths:
                    issues.append(
                        "GOVERNANCE_FILE_MISSING:{0}".format(required_path)
                    )
            license_path = os.path.join(self.project_dir, "LICENSE")
            if os.path.isfile(license_path):
                with open(license_path, "r", encoding="utf-8") as license_file:
                    license_text = license_file.read(4096)
                if "Apache License" not in license_text or "Version 2.0" not in license_text:
                    issues.append("LICENSE_IS_NOT_APACHE_2_0")
        issues = sorted(set(issues))[:self.MAX_ISSUES]
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": "PASS" if not issues else "FAIL",
            "git_repository": git_repository,
            "tracked_files_only": tracked_files_only,
            "scanned_files": scanned_files,
            "binary_files": binary_files,
            "total_bytes": total_bytes,
            "maximum_file_bytes": self.MAX_FILE_BYTES,
            "maximum_repository_bytes": self.MAX_TOTAL_BYTES,
            "issue_count": len(issues),
            "issues": issues,
            "credentials_exposed": False,
            "secret_values_exposed": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    def _git_files(self):
        try:
            process = subprocess.run(
                ["git", "ls-files", "-z"],
                cwd=self.project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError:
            return []
        if process.returncode != 0:
            return []
        return [
            item.decode("utf-8", "strict")
            for item in process.stdout.split(b"\x00")
            if item
        ]

    def _is_git_repository(self):
        try:
            process = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                cwd=self.project_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        except OSError:
            return False
        return process.returncode == 0 and process.stdout.strip() == b"true"

    def _fallback_files(self):
        files = []
        for root, directories, filenames in os.walk(self.project_dir):
            relative_root = os.path.relpath(root, self.project_dir)
            relative_root = "" if relative_root == "." else relative_root.replace(
                os.sep,
                "/",
            )
            directories[:] = sorted(
                directory
                for directory in directories
                if directory not in (
                    ".git",
                    ".venv",
                    "__pycache__",
                    ".pytest_cache",
                    "data",
                    "dist",
                )
            )
            for filename in sorted(filenames):
                if filename.endswith((".pyc", ".pyo", ".tmp")):
                    continue
                relative_path = (
                    relative_root + "/" + filename
                    if relative_root
                    else filename
                )
                if self._fallback_ignored(relative_path):
                    continue
                files.append(relative_path)
        return files

    def _fallback_ignored(self, relative_path):
        lower_path = relative_path.lower()
        basename = os.path.basename(lower_path)
        if relative_path in self.FORBIDDEN_PATHS:
            return True
        if lower_path.startswith(self.FORBIDDEN_PREFIXES):
            return True
        if lower_path.endswith(self.FORBIDDEN_SUFFIXES):
            return True
        if basename == ".env" or basename.startswith(".env."):
            return True
        if lower_path.endswith((".tar", ".tar.gz")):
            return not lower_path.startswith("vendor/wheels/")
        return False

    def _path_issues(self, relative_path):
        issues = []
        lower_path = relative_path.lower()
        basename = os.path.basename(lower_path)
        if relative_path in self.FORBIDDEN_PATHS:
            issues.append("FORBIDDEN_PATH:{0}".format(relative_path))
        if lower_path.startswith(self.FORBIDDEN_PREFIXES):
            issues.append("FORBIDDEN_PATH:{0}".format(relative_path))
        if lower_path.endswith(self.FORBIDDEN_SUFFIXES):
            issues.append("FORBIDDEN_FILE_TYPE:{0}".format(relative_path))
        if basename == ".env" or basename.startswith(".env."):
            issues.append("FORBIDDEN_CREDENTIAL_FILE:{0}".format(relative_path))
        if basename in ("authorized_keys", "id_rsa", "id_ed25519"):
            issues.append("FORBIDDEN_CREDENTIAL_FILE:{0}".format(relative_path))
        return issues

    @staticmethod
    def _allowed_binary(relative_path):
        return relative_path.startswith("vendor/wheels/") and relative_path.endswith(
            (".whl", ".tar.gz")
        )

    @staticmethod
    def _normalize_relative_path(path):
        path = str(path or "").replace("\\", "/")
        if (
            not path
            or path.startswith("/")
            or re.match(r"^[A-Za-z]:", path)
            or "\x00" in path
            or any(part in ("", ".", "..") for part in path.split("/"))
        ):
            raise ValueError("repository path is invalid")
        return path

    @staticmethod
    def _is_within(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except (AttributeError, ValueError):
            return path == root or path.startswith(root.rstrip(os.sep) + os.sep)
