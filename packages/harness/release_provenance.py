"""Deterministic software release provenance and SBOM generation."""

import hashlib
import json
import os
import re
import tempfile
import uuid

class ReleaseProvenanceError(RuntimeError):
    pass


class ReleaseProvenance(object):
    SCHEMA_VERSION = "1.0"
    CYCLONEDX_VERSION = "1.7"
    MAX_FILES = 4096
    MAX_TOTAL_BYTES = 256 * 1024 * 1024
    MAX_ISSUES = 50
    ROOT_FILES = (
        ".gitattributes",
        ".gitignore",
        "README.md",
        "VERSION",
        "requirements-api-py36.txt",
    )
    ROOT_DIRECTORIES = (
        ".github",
        "apps",
        "deploy",
        "docs",
        "evals",
        "packages",
        "scripts",
        "skills",
        "tests",
        "vendor/wheels",
    )
    EXPLICIT_FILES = (
        "configs/zones.default.json",
    )
    EXCLUDED_NAMES = (
        "__pycache__",
        ".pytest_cache",
    )
    EXCLUDED_SUFFIXES = (
        ".pyc",
        ".pyo",
        ".tmp",
    )
    SECRET_SUFFIXES = (
        ".env",
        ".key",
        ".pem",
        ".p12",
        ".pfx",
    )
    VERSION_PATTERN = re.compile(
        r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?$"
    )
    REQUIREMENT_PATTERN = re.compile(
        r"^([A-Za-z0-9][A-Za-z0-9._-]*)==([^\s;]+)$"
    )
    HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")

    def __init__(self, project_dir):
        self.project_dir = os.path.realpath(os.path.abspath(project_dir))
        if not os.path.isdir(self.project_dir):
            raise ReleaseProvenanceError("project directory does not exist")

    def build(self, version=None):
        version = self._read_version(version)
        files = self._collect_files()
        source_sha256 = self._aggregate_hash(files)
        release_id = "esv_{0}_{1}".format(
            version.replace(".", "_").replace("-", "_"),
            source_sha256[:16],
        )
        requirements = self._load_requirements()
        sbom = self._build_sbom(
            version,
            release_id,
            source_sha256,
            requirements,
            files,
        )
        sbom_sha256 = hashlib.sha256(
            self._json_bytes(sbom)
        ).hexdigest()
        manifest = {
            "schema_version": self.SCHEMA_VERSION,
            "release_id": release_id,
            "version": version,
            "source": {
                "algorithm": "sha256",
                "sha256": source_sha256,
                "file_count": len(files),
                "total_bytes": sum(item["bytes"] for item in files),
            },
            "requirements": {
                "path": "requirements-api-py36.txt",
                "sha256": self._entry_by_path(
                    files,
                    "requirements-api-py36.txt",
                )["sha256"],
                "component_count": len(requirements),
                "all_versions_pinned": True,
            },
            "sbom": {
                "path": "bom.cdx.json",
                "format": "CycloneDX",
                "spec_version": self.CYCLONEDX_VERSION,
                "sha256": sbom_sha256,
            },
            "files": files,
            "security": {
                "allowlisted_sources_only": True,
                "symlinks_included": False,
                "credentials_included": False,
                "absolute_paths_included": False,
                "runtime_data_included": False,
            },
        }
        return manifest, sbom

    def write(self, output_root, version=None):
        manifest, sbom = self.build(version)
        output_root = os.path.abspath(output_root)
        if os.path.lexists(output_root) and os.path.islink(output_root):
            raise ReleaseProvenanceError(
                "release output root must not be a symlink"
            )
        release_dir = os.path.join(output_root, manifest["release_id"])
        if os.path.lexists(release_dir) and os.path.islink(release_dir):
            raise ReleaseProvenanceError(
                "release output directory must not be a symlink"
            )
        if not os.path.isdir(release_dir):
            os.makedirs(release_dir)
        manifest_path = os.path.join(
            release_dir,
            "release-manifest.json",
        )
        sbom_path = os.path.join(release_dir, "bom.cdx.json")
        self._write_json_atomic(sbom_path, sbom)
        self._write_json_atomic(manifest_path, manifest)
        manifest_sha256 = self._sha256_file(manifest_path)
        self._write_text_atomic(
            os.path.join(release_dir, "release-manifest.sha256"),
            manifest_sha256 + "  release-manifest.json\n",
        )
        pointer = {
            "schema_version": self.SCHEMA_VERSION,
            "release_id": manifest["release_id"],
            "manifest": (
                manifest["release_id"] + "/release-manifest.json"
            ),
            "manifest_sha256": manifest_sha256,
            "credentials_included": False,
            "absolute_paths_included": False,
        }
        self._write_json_atomic(
            os.path.join(output_root, "current-release.json"),
            pointer,
        )
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": "CREATED",
            "release_id": manifest["release_id"],
            "version": manifest["version"],
            "manifest": self._portable_output_path(
                manifest_path,
                output_root,
            ),
            "manifest_sha256": manifest_sha256,
            "sbom": self._portable_output_path(sbom_path, output_root),
            "sbom_sha256": manifest["sbom"]["sha256"],
            "file_count": manifest["source"]["file_count"],
            "total_bytes": manifest["source"]["total_bytes"],
            "credentials_included": False,
            "absolute_paths_included": False,
        }

    def verify(self, manifest_path):
        manifest_path = os.path.abspath(manifest_path)
        issues = []
        manifest = self._load_json_regular_file(
            manifest_path,
            "release manifest",
        )
        self._validate_manifest(manifest)
        release_dir = os.path.dirname(manifest_path)
        sidecar_path = os.path.join(
            release_dir,
            "release-manifest.sha256",
        )
        if not os.path.isfile(sidecar_path) or os.path.islink(sidecar_path):
            issues.append("MANIFEST_HASH_MISSING")
        else:
            expected_manifest_hash = self._read_sidecar(sidecar_path)
            if expected_manifest_hash != self._sha256_file(manifest_path):
                issues.append("MANIFEST_HASH_MISMATCH")
        sbom_path = os.path.join(release_dir, manifest["sbom"]["path"])
        if not os.path.isfile(sbom_path) or os.path.islink(sbom_path):
            issues.append("SBOM_MISSING")
        elif self._sha256_file(sbom_path) != manifest["sbom"]["sha256"]:
            issues.append("SBOM_HASH_MISMATCH")
        else:
            sbom = self._load_json_regular_file(sbom_path, "SBOM")
            if (
                sbom.get("bomFormat") != "CycloneDX"
                or sbom.get("specVersion") != self.CYCLONEDX_VERSION
            ):
                issues.append("SBOM_SCHEMA_MISMATCH")
        expected_paths = set()
        for entry in manifest["files"]:
            relative_path = entry["path"]
            expected_paths.add(relative_path)
            lexical_candidate = self._lexical_project_file(relative_path)
            candidate = self._resolve_project_file(relative_path)
            if (
                not os.path.isfile(lexical_candidate)
                or self._path_contains_symlink(relative_path)
            ):
                issues.append("FILE_MISSING:{0}".format(relative_path))
                continue
            if int(os.path.getsize(candidate)) != entry["bytes"]:
                issues.append("FILE_SIZE_MISMATCH:{0}".format(relative_path))
                continue
            if self._sha256_file(candidate) != entry["sha256"]:
                issues.append("FILE_HASH_MISMATCH:{0}".format(relative_path))
        current_paths = set(
            item["path"] for item in self._collect_files()
        )
        for relative_path in sorted(current_paths - expected_paths):
            issues.append("UNEXPECTED_FILE:{0}".format(relative_path))
        for relative_path in sorted(expected_paths - current_paths):
            marker = "FILE_MISSING:{0}".format(relative_path)
            if marker not in issues:
                issues.append(marker)
        aggregate_hash = self._aggregate_hash(manifest["files"])
        if aggregate_hash != manifest["source"]["sha256"]:
            issues.append("SOURCE_AGGREGATE_MISMATCH")
        expected_release_id = "esv_{0}_{1}".format(
            manifest["version"].replace(".", "_").replace("-", "_"),
            aggregate_hash[:16],
        )
        if expected_release_id != manifest["release_id"]:
            issues.append("RELEASE_ID_MISMATCH")
        issues = issues[:self.MAX_ISSUES]
        source_issue = any(
            issue.startswith((
                "FILE_",
                "UNEXPECTED_FILE:",
                "SOURCE_",
                "RELEASE_ID_",
            ))
            for issue in issues
        )
        sbom_issue = any(issue.startswith("SBOM_") for issue in issues)
        return {
            "schema_version": self.SCHEMA_VERSION,
            "status": "PASS" if not issues else "FAIL",
            "release_id": manifest["release_id"],
            "version": manifest["version"],
            "source_integrity": "MISMATCH" if source_issue else "MATCH",
            "checked_files": len(manifest["files"]),
            "issue_count": len(issues),
            "issues": issues,
            "sbom_verified": not sbom_issue,
            "credentials_included": False,
            "absolute_paths_included": False,
            "read_only": True,
        }

    def _collect_files(self):
        paths = []
        for relative_path in self.ROOT_FILES + self.EXPLICIT_FILES:
            lexical_candidate = self._lexical_project_file(relative_path)
            if os.path.lexists(lexical_candidate) and os.path.islink(
                lexical_candidate
            ):
                raise ReleaseProvenanceError(
                    "release sources must not contain symlinks"
                )
            candidate = self._resolve_project_file(relative_path)
            if not os.path.exists(candidate):
                if relative_path == "requirements-api-py36.txt" or (
                    relative_path == "VERSION"
                ):
                    raise ReleaseProvenanceError(
                        "required release file is missing: {0}".format(
                            relative_path
                        )
                    )
                continue
            paths.append(relative_path)
        for relative_root in self.ROOT_DIRECTORIES:
            lexical_root = self._lexical_project_file(relative_root)
            if os.path.lexists(lexical_root) and os.path.islink(lexical_root):
                raise ReleaseProvenanceError(
                    "release source root must not be a symlink"
                )
            root = self._resolve_project_file(relative_root)
            if not os.path.exists(root):
                continue
            if os.path.islink(root):
                raise ReleaseProvenanceError(
                    "release source root must not be a symlink"
                )
            for current_root, directories, filenames in os.walk(root):
                directories[:] = sorted(
                    item
                    for item in directories
                    if item not in self.EXCLUDED_NAMES
                )
                for directory in directories:
                    if os.path.islink(os.path.join(current_root, directory)):
                        raise ReleaseProvenanceError(
                            "release sources must not contain symlinks"
                        )
                for filename in sorted(filenames):
                    if self._is_excluded_file(filename):
                        continue
                    candidate = os.path.join(current_root, filename)
                    if os.path.islink(candidate):
                        raise ReleaseProvenanceError(
                            "release sources must not contain symlinks"
                        )
                    relative_path = self._relative_path(candidate)
                    self._reject_secret_path(relative_path)
                    paths.append(relative_path)
        unique_paths = sorted(set(paths))
        if len(unique_paths) > self.MAX_FILES:
            raise ReleaseProvenanceError("release file limit exceeded")
        entries = []
        total_bytes = 0
        for relative_path in unique_paths:
            candidate = self._resolve_project_file(relative_path)
            if not os.path.isfile(candidate) or os.path.islink(candidate):
                raise ReleaseProvenanceError(
                    "release source is not a regular file"
                )
            size_bytes = int(os.path.getsize(candidate))
            total_bytes += size_bytes
            if total_bytes > self.MAX_TOTAL_BYTES:
                raise ReleaseProvenanceError("release byte limit exceeded")
            entries.append({
                "path": relative_path,
                "category": self._category(relative_path),
                "bytes": size_bytes,
                "sha256": self._sha256_file(candidate),
            })
        return entries

    def _load_requirements(self):
        path = self._resolve_project_file("requirements-api-py36.txt")
        requirements = []
        names = set()
        with open(path, "r", encoding="utf-8") as requirement_file:
            for raw_line in requirement_file:
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                match = self.REQUIREMENT_PATTERN.match(line)
                if match is None:
                    raise ReleaseProvenanceError(
                        "every runtime requirement must use name==version"
                    )
                name = match.group(1)
                normalized = self._normalize_package_name(name)
                if normalized in names:
                    raise ReleaseProvenanceError(
                        "duplicate runtime requirement"
                    )
                names.add(normalized)
                requirements.append({
                    "name": name,
                    "normalized_name": normalized,
                    "version": match.group(2),
                })
        if not requirements:
            raise ReleaseProvenanceError("runtime requirements are empty")
        return sorted(
            requirements,
            key=lambda item: item["normalized_name"],
        )

    def _build_sbom(
        self,
        version,
        release_id,
        source_sha256,
        requirements,
        files,
    ):
        artifacts = self._distribution_artifacts(files)
        components = []
        dependency_rows = []
        root_dependencies = []
        matched_artifacts = set()
        for requirement in requirements:
            name = requirement["name"]
            normalized = requirement["normalized_name"]
            package_version = requirement["version"]
            package_ref = "pkg:pypi/{0}@{1}".format(
                normalized,
                package_version,
            )
            root_dependencies.append(package_ref)
            package_artifacts = []
            for artifact in artifacts:
                if (
                    artifact["normalized_name"] == normalized
                    and artifact["version"] == package_version
                ):
                    package_artifacts.append(artifact["bom_ref"])
                    matched_artifacts.add(artifact["path"])
            components.append({
                "type": "library",
                "bom-ref": package_ref,
                "name": name,
                "version": package_version,
                "scope": "required",
                "purl": package_ref,
                "properties": [{
                    "name": "edgesentinel:requirement:pinned",
                    "value": "true",
                }],
            })
            dependency_rows.append({
                "ref": package_ref,
                "dependsOn": sorted(package_artifacts),
            })
        for artifact in artifacts:
            components.append({
                "type": "file",
                "bom-ref": artifact["bom_ref"],
                "name": os.path.basename(artifact["path"]),
                "scope": (
                    "required"
                    if artifact["path"] in matched_artifacts
                    else "optional"
                ),
                "hashes": [{
                    "alg": "SHA-256",
                    "content": artifact["sha256"],
                }],
                "properties": [{
                    "name": "edgesentinel:distribution:path",
                    "value": artifact["path"],
                }],
            })
            if artifact["path"] not in matched_artifacts:
                root_dependencies.append(artifact["bom_ref"])
        root_ref = "pkg:generic/edgesentinel-visionops@{0}".format(version)
        dependency_rows.insert(0, {
            "ref": root_ref,
            "dependsOn": sorted(root_dependencies),
        })
        return {
            "$schema": (
                "https://cyclonedx.org/schema/bom-{0}.schema.json".format(
                    self.CYCLONEDX_VERSION
                )
            ),
            "bomFormat": "CycloneDX",
            "specVersion": self.CYCLONEDX_VERSION,
            "serialNumber": "urn:uuid:{0}".format(
                uuid.uuid5(
                    uuid.NAMESPACE_URL,
                    "urn:edgesentinel:release:{0}".format(release_id),
                )
            ),
            "version": 1,
            "metadata": {
                "component": {
                    "type": "application",
                    "bom-ref": root_ref,
                    "name": "edgesentinel-visionops",
                    "version": version,
                    "hashes": [{
                        "alg": "SHA-256",
                        "content": source_sha256,
                    }],
                    "properties": [{
                        "name": "edgesentinel:release:id",
                        "value": release_id,
                    }],
                },
                "properties": [
                    {
                        "name": "edgesentinel:credentials:included",
                        "value": "false",
                    },
                    {
                        "name": "edgesentinel:absolute-paths:included",
                        "value": "false",
                    },
                ],
            },
            "components": sorted(
                components,
                key=lambda item: item["bom-ref"],
            ),
            "dependencies": dependency_rows,
        }

    def _distribution_artifacts(self, files):
        artifacts = []
        for entry in files:
            relative_path = entry["path"]
            if not relative_path.startswith("vendor/wheels/"):
                continue
            filename = os.path.basename(relative_path)
            parsed = self._parse_distribution_filename(filename)
            if parsed is None:
                continue
            name, version = parsed
            artifact_ref = "urn:edgesentinel:distribution:{0}".format(
                entry["sha256"]
            )
            artifacts.append({
                "path": relative_path,
                "sha256": entry["sha256"],
                "normalized_name": self._normalize_package_name(name),
                "version": version,
                "bom_ref": artifact_ref,
            })
        return sorted(artifacts, key=lambda item: item["path"])

    @staticmethod
    def _parse_distribution_filename(filename):
        if filename.endswith(".whl"):
            parts = filename[:-4].split("-")
            if len(parts) >= 2:
                return parts[0], parts[1]
        if filename.endswith(".tar.gz"):
            stem = filename[:-7]
            if "-" in stem:
                return tuple(stem.rsplit("-", 1))
        return None

    def _read_version(self, supplied_version):
        if supplied_version is None:
            version_path = self._resolve_project_file("VERSION")
            if not os.path.isfile(version_path):
                raise ReleaseProvenanceError("VERSION file is missing")
            with open(version_path, "r", encoding="utf-8") as version_file:
                supplied_version = version_file.read(128).strip()
        version = str(supplied_version or "").strip()
        if self.VERSION_PATTERN.match(version) is None:
            raise ReleaseProvenanceError("release version is invalid")
        return version

    def _validate_manifest(self, manifest):
        if not isinstance(manifest, dict):
            raise ReleaseProvenanceError("release manifest must be an object")
        if manifest.get("schema_version") != self.SCHEMA_VERSION:
            raise ReleaseProvenanceError("release manifest schema is invalid")
        if not re.match(r"^esv_[A-Za-z0-9_]+_[0-9a-f]{16}$", str(
            manifest.get("release_id") or ""
        )):
            raise ReleaseProvenanceError("release ID is invalid")
        self._read_version(manifest.get("version"))
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise ReleaseProvenanceError("release file list is invalid")
        if len(files) > self.MAX_FILES:
            raise ReleaseProvenanceError("release file limit exceeded")
        previous_path = None
        for entry in files:
            if not isinstance(entry, dict):
                raise ReleaseProvenanceError("release file entry is invalid")
            relative_path = self._validate_relative_path(entry.get("path"))
            if previous_path is not None and relative_path <= previous_path:
                raise ReleaseProvenanceError(
                    "release file list must be unique and sorted"
                )
            previous_path = relative_path
            if not isinstance(entry.get("bytes"), int) or entry["bytes"] < 0:
                raise ReleaseProvenanceError("release file size is invalid")
            if self.HASH_PATTERN.match(str(entry.get("sha256") or "")) is None:
                raise ReleaseProvenanceError("release file hash is invalid")
        source = manifest.get("source")
        if (
            not isinstance(source, dict)
            or source.get("algorithm") != "sha256"
            or self.HASH_PATTERN.match(str(source.get("sha256") or "")) is None
            or source.get("file_count") != len(files)
            or source.get("total_bytes") != sum(item["bytes"] for item in files)
        ):
            raise ReleaseProvenanceError("release source summary is invalid")
        sbom = manifest.get("sbom")
        if not isinstance(sbom, dict):
            raise ReleaseProvenanceError("SBOM descriptor is invalid")
        self._validate_relative_path(sbom.get("path"))
        if self.HASH_PATTERN.match(str(sbom.get("sha256") or "")) is None:
            raise ReleaseProvenanceError("SBOM hash is invalid")
        security = manifest.get("security")
        if not isinstance(security, dict) or any((
            security.get("credentials_included") is not False,
            security.get("absolute_paths_included") is not False,
            security.get("runtime_data_included") is not False,
            security.get("symlinks_included") is not False,
        )):
            raise ReleaseProvenanceError("release security boundary is invalid")

    def _resolve_project_file(self, relative_path):
        candidate = os.path.realpath(
            self._lexical_project_file(relative_path)
        )
        if not self._is_within(candidate, self.project_dir):
            raise ReleaseProvenanceError("release path escaped project root")
        return candidate

    def _lexical_project_file(self, relative_path):
        relative_path = self._validate_relative_path(relative_path)
        candidate = os.path.abspath(os.path.join(
            self.project_dir,
            relative_path.replace("/", os.sep),
        ))
        if not self._is_within(candidate, self.project_dir):
            raise ReleaseProvenanceError("release path escaped project root")
        return candidate

    def _path_contains_symlink(self, relative_path):
        relative_path = self._validate_relative_path(relative_path)
        candidate = self.project_dir
        for part in relative_path.split("/"):
            candidate = os.path.join(candidate, part)
            if os.path.lexists(candidate) and os.path.islink(candidate):
                return True
        return False

    @staticmethod
    def _validate_relative_path(relative_path):
        relative_path = str(relative_path or "").replace("\\", "/")
        if (
            not relative_path
            or relative_path.startswith("/")
            or re.match(r"^[A-Za-z]:", relative_path)
            or "\x00" in relative_path
            or any(part in ("", ".", "..") for part in relative_path.split("/"))
        ):
            raise ReleaseProvenanceError("release path is invalid")
        return relative_path

    def _relative_path(self, path):
        return os.path.relpath(path, self.project_dir).replace(os.sep, "/")

    def _reject_secret_path(self, relative_path):
        lower_path = relative_path.lower()
        basename = os.path.basename(lower_path)
        if lower_path.endswith(self.SECRET_SUFFIXES) or basename in (
            "authorized_keys",
            "id_rsa",
            "id_ed25519",
        ):
            raise ReleaseProvenanceError(
                "credential-like file is not eligible for a release"
            )

    def _is_excluded_file(self, filename):
        return filename.endswith(self.EXCLUDED_SUFFIXES)

    @staticmethod
    def _category(relative_path):
        if "/" not in relative_path:
            return "project"
        return relative_path.split("/", 1)[0]

    @staticmethod
    def _normalize_package_name(name):
        return re.sub(r"[-_.]+", "-", str(name)).lower()

    @staticmethod
    def _aggregate_hash(files):
        digest = hashlib.sha256()
        for entry in files:
            digest.update(entry["path"].encode("utf-8"))
            digest.update(b"\0")
            digest.update(str(entry["bytes"]).encode("ascii"))
            digest.update(b"\0")
            digest.update(entry["sha256"].encode("ascii"))
            digest.update(b"\n")
        return digest.hexdigest()

    @staticmethod
    def _entry_by_path(files, relative_path):
        for entry in files:
            if entry["path"] == relative_path:
                return entry
        raise ReleaseProvenanceError(
            "required release entry is missing: {0}".format(relative_path)
        )

    @staticmethod
    def _json_bytes(payload):
        return (
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")

    @classmethod
    def _write_json_atomic(cls, path, payload):
        path = os.path.abspath(path)
        parent = os.path.dirname(path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".release-json-",
            suffix=".tmp",
            dir=parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as output_file:
                output_file.write(cls._json_bytes(payload))
                output_file.flush()
            os.replace(temporary_path, path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with open(path, "rb") as input_file:
            while True:
                chunk = input_file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _write_text_atomic(path, content):
        parent = os.path.dirname(os.path.abspath(path))
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".release-text-",
            suffix=".tmp",
            dir=parent,
        )
        try:
            with os.fdopen(descriptor, "wb") as output_file:
                output_file.write(content.encode("ascii"))
                output_file.flush()
            os.replace(temporary_path, path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    @staticmethod
    def _read_sidecar(path):
        with open(path, "r", encoding="ascii") as input_file:
            first_line = input_file.readline(256).strip()
        digest = first_line.split(None, 1)[0].lower() if first_line else ""
        if re.match(r"^[0-9a-f]{64}$", digest) is None:
            raise ReleaseProvenanceError("manifest hash sidecar is invalid")
        return digest

    @staticmethod
    def _load_json_regular_file(path, label):
        if not os.path.isfile(path) or os.path.islink(path):
            raise ReleaseProvenanceError("{0} is not a regular file".format(label))
        try:
            with open(path, "r", encoding="utf-8") as input_file:
                payload = json.load(input_file)
        except (OSError, UnicodeError, ValueError) as error:
            raise ReleaseProvenanceError(
                "{0} is invalid".format(label)
            ) from error
        return payload

    @staticmethod
    def _portable_output_path(path, output_root):
        return os.path.relpath(path, output_root).replace(os.sep, "/")

    @staticmethod
    def _is_within(path, root):
        try:
            return os.path.commonpath([path, root]) == root
        except (AttributeError, ValueError):
            return path == root or path.startswith(root.rstrip(os.sep) + os.sep)
