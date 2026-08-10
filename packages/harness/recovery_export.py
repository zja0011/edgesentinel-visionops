"""Authenticated encrypted exports for off-device disaster recovery."""

import hashlib
import hmac
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile

from packages.harness.disaster_recovery import DisasterRecoveryStore
from packages.harness.utf8 import write_json_atomic
from packages.vision.schemas import beijing_timestamp


BACKUP_ID_PATTERN = re.compile(r"^dr_[0-9a-f]{32}$")


class RecoveryExportError(RuntimeError):
    pass


class EncryptedRecoveryExport(object):
    SCHEMA_VERSION = "1.0"
    ENCRYPTION = "AES-256-CBC"
    AUTHENTICATION = "HMAC-SHA256"
    KDF = "PBKDF2-HMAC-SHA256"
    ITERATIONS = 200000
    HMAC_DOMAIN = b"EdgeSentinel recovery export HMAC v1"
    HMAC_PREFIX = b"EdgeSentinelRecoveryExportV1\x00"
    METADATA_FIELDS = {
        "schema_version",
        "backup_id",
        "created_at",
        "encryption",
        "authentication",
        "kdf",
        "iterations",
        "artifact_file",
        "artifact_bytes",
        "artifact_sha256",
        "archive_sha256",
        "manifest_sha256",
        "file_count",
        "source_bytes",
        "sqlite_consistent",
        "credentials_included",
        "absolute_paths_included",
        "plaintext_persisted",
        "hmac_sha256",
    }

    def __init__(self, openssl_path=None):
        self.openssl_path = openssl_path or shutil.which("openssl")
        if not self.openssl_path:
            raise RecoveryExportError("OpenSSL is unavailable")

    def create(self, project_dir, backup_id, output_dir, secret):
        project_dir = os.path.abspath(project_dir)
        backup_id = self._validate_backup_id(backup_id)
        secret = self._validate_secret(secret)
        output_dir = self._trusted_directory(output_dir, create=True)
        artifact_name = backup_id + ".esdr"
        metadata_name = backup_id + ".esdr.json"
        artifact_path = os.path.join(output_dir, artifact_name)
        metadata_path = os.path.join(output_dir, metadata_name)
        if os.path.lexists(artifact_path) or os.path.lexists(metadata_path):
            raise RecoveryExportError("recovery export already exists")

        store = DisasterRecoveryStore(project_dir)
        preview = store.preview_restore({"backup_id": backup_id})
        backup_dir = os.path.join(
            project_dir,
            "data",
            "recovery",
            "backups",
            backup_id,
        )
        stage_dir = tempfile.mkdtemp(prefix=".recovery-export-", dir=output_dir)
        os.chmod(stage_dir, 0o700)
        archive_path = os.path.join(stage_dir, backup_id + ".tar.gz")
        staged_artifact = os.path.join(stage_dir, artifact_name)
        committed = False
        try:
            self._create_archive(backup_dir, backup_id, archive_path)
            archive_sha256 = self._sha256_file(archive_path)
            self._openssl(
                [
                    "enc",
                    "-aes-256-cbc",
                    "-salt",
                    "-pbkdf2",
                    "-iter",
                    str(self.ITERATIONS),
                    "-md",
                    "sha256",
                    "-in",
                    archive_path,
                    "-out",
                    staged_artifact,
                    "-pass",
                    "stdin",
                ],
                secret,
            )
            os.chmod(staged_artifact, 0o600)
            metadata = {
                "schema_version": self.SCHEMA_VERSION,
                "backup_id": backup_id,
                "created_at": beijing_timestamp(),
                "encryption": self.ENCRYPTION,
                "authentication": self.AUTHENTICATION,
                "kdf": self.KDF,
                "iterations": self.ITERATIONS,
                "artifact_file": artifact_name,
                "artifact_bytes": os.path.getsize(staged_artifact),
                "artifact_sha256": self._sha256_file(staged_artifact),
                "archive_sha256": archive_sha256,
                "manifest_sha256": preview["manifest_sha256"],
                "file_count": int(preview["file_count"]),
                "source_bytes": int(preview["bytes"]),
                "sqlite_consistent": True,
                "credentials_included": False,
                "absolute_paths_included": False,
                "plaintext_persisted": False,
            }
            metadata["hmac_sha256"] = self._artifact_hmac(
                staged_artifact,
                metadata,
                secret,
            )
            os.replace(staged_artifact, artifact_path)
            os.chmod(artifact_path, 0o600)
            write_json_atomic(metadata_path, metadata)
            os.chmod(metadata_path, 0o600)
            result = self.verify(artifact_path, metadata_path, secret)
            committed = True
            return result
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)
            if not committed:
                for path in (artifact_path, metadata_path):
                    try:
                        if os.path.isfile(path) and not os.path.islink(path):
                            os.remove(path)
                    except OSError:
                        pass

    def verify(self, artifact_path, metadata_path, secret):
        prepared = self._prepare_verified_backup(
            artifact_path,
            metadata_path,
            secret,
            "edgesentinel-recovery-verify-",
        )
        try:
            result = self._public_summary(
                prepared["metadata"],
                verified=True,
            )
            result["backup"] = prepared["backup"]
            return result
        finally:
            shutil.rmtree(prepared["temporary"], ignore_errors=True)

    def drill(self, artifact_path, metadata_path, secret):
        """Apply an export into a disposable project and verify the result."""
        prepared = self._prepare_verified_backup(
            artifact_path,
            metadata_path,
            secret,
            "edgesentinel-recovery-drill-",
        )
        try:
            metadata = prepared["metadata"]
            store = DisasterRecoveryStore(prepared["project_dir"])
            preview = store.preview_restore(
                {"backup_id": metadata["backup_id"]}
            )
            if (
                int(preview["changed_file_count"])
                != int(preview["file_count"])
                or int(preview["missing_file_count"])
                != int(preview["file_count"])
                or int(preview["unchanged_file_count"]) != 0
            ):
                raise RecoveryExportError(
                    "isolated recovery target is not empty"
                )
            restored = store.apply_restore(
                metadata["backup_id"],
                preview["plan_id"],
                store.RESTORE_PHRASE,
                maintenance_mode=True,
            )
            post_restore = store.preview_restore(
                {"backup_id": metadata["backup_id"]}
            )
            file_count = int(preview["file_count"])
            if (
                restored.get("status") != "COMPLETED"
                or int(restored["restored_file_count"]) != file_count
                or int(post_restore["unchanged_file_count"]) != file_count
                or int(post_restore["changed_file_count"]) != 0
            ):
                raise RecoveryExportError(
                    "isolated recovery post-restore verification failed"
                )
            return {
                "schema_version": self.SCHEMA_VERSION,
                "status": "PASS",
                "mode": "ISOLATED_RESTORE_DRILL",
                "backup_id": metadata["backup_id"],
                "artifact_sha256": metadata["artifact_sha256"],
                "manifest_sha256": metadata["manifest_sha256"],
                "file_count": file_count,
                "source_bytes": int(metadata["source_bytes"]),
                "restored_file_count": int(
                    restored["restored_file_count"]
                ),
                "post_restore_verified_files": int(
                    post_restore["unchanged_file_count"]
                ),
                "sqlite_consistent": bool(
                    prepared["backup"].get("sqlite_consistent")
                ),
                "isolated": True,
                "production_modified": False,
                "credentials_included": False,
                "absolute_paths_included": False,
                "plaintext_persisted": False,
            }
        finally:
            shutil.rmtree(prepared["temporary"], ignore_errors=True)

    def _prepare_verified_backup(
        self,
        artifact_path,
        metadata_path,
        secret,
        temporary_prefix,
    ):
        artifact_path = self._regular_file(artifact_path)
        metadata_path = self._regular_file(metadata_path)
        secret = self._validate_secret(secret)
        metadata = self._load_metadata(metadata_path)
        if os.path.basename(artifact_path) != metadata["artifact_file"]:
            raise RecoveryExportError("artifact filename does not match metadata")
        if os.path.getsize(artifact_path) != int(metadata["artifact_bytes"]):
            raise RecoveryExportError("encrypted artifact size mismatch")
        if not hmac.compare_digest(
            self._sha256_file(artifact_path),
            metadata["artifact_sha256"],
        ):
            raise RecoveryExportError("encrypted artifact SHA-256 mismatch")
        actual_hmac = self._artifact_hmac(
            artifact_path,
            metadata,
            secret,
        )
        if not hmac.compare_digest(actual_hmac, metadata["hmac_sha256"]):
            raise RecoveryExportError("recovery export authentication failed")

        temporary = tempfile.mkdtemp(prefix=temporary_prefix)
        archive_path = os.path.join(temporary, "verified.tar.gz")
        project_dir = os.path.join(temporary, "project")
        backups_dir = os.path.join(
            project_dir,
            "data",
            "recovery",
            "backups",
        )
        os.makedirs(backups_dir)
        try:
            self._openssl(
                [
                    "enc",
                    "-d",
                    "-aes-256-cbc",
                    "-pbkdf2",
                    "-iter",
                    str(self.ITERATIONS),
                    "-md",
                    "sha256",
                    "-in",
                    artifact_path,
                    "-out",
                    archive_path,
                    "-pass",
                    "stdin",
                ],
                secret,
            )
            if not hmac.compare_digest(
                self._sha256_file(archive_path),
                metadata["archive_sha256"],
            ):
                raise RecoveryExportError("decrypted archive SHA-256 mismatch")
            self._safe_extract(archive_path, backups_dir)
            status = DisasterRecoveryStore(project_dir).get_status({"limit": 2})
            backups = list(status.get("backups") or [])
            if (
                status.get("status") != "COMPLETE"
                or int(status.get("backup_count") or 0) != 1
                or len(backups) != 1
                or backups[0].get("backup_id") != metadata["backup_id"]
                or backups[0].get("manifest_sha256")
                != metadata["manifest_sha256"]
            ):
                raise RecoveryExportError("decrypted backup verification failed")
            return {
                "temporary": temporary,
                "project_dir": project_dir,
                "metadata": metadata,
                "backup": backups[0],
            }
        except Exception:
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    def _load_metadata(self, path):
        if os.path.getsize(path) > 65536:
            raise RecoveryExportError("recovery export metadata is oversized")
        try:
            with open(path, "r", encoding="utf-8") as input_file:
                metadata = json.load(input_file)
        except (OSError, ValueError) as error:
            raise RecoveryExportError("recovery export metadata is invalid") from error
        if not isinstance(metadata, dict) or set(metadata) != self.METADATA_FIELDS:
            raise RecoveryExportError("recovery export metadata schema is invalid")
        self._validate_backup_id(metadata.get("backup_id"))
        if (
            metadata.get("schema_version") != self.SCHEMA_VERSION
            or metadata.get("encryption") != self.ENCRYPTION
            or metadata.get("authentication") != self.AUTHENTICATION
            or metadata.get("kdf") != self.KDF
            or int(metadata.get("iterations") or 0) != self.ITERATIONS
            or metadata.get("credentials_included") is not False
            or metadata.get("absolute_paths_included") is not False
            or metadata.get("plaintext_persisted") is not False
            or metadata.get("artifact_file")
            != metadata.get("backup_id") + ".esdr"
            or int(metadata.get("artifact_bytes") or 0) <= 0
            or int(metadata.get("file_count") or 0) <= 0
            or int(metadata.get("source_bytes") or 0) <= 0
            or not re.match(r"^[0-9a-f]{64}$", str(metadata.get("hmac_sha256") or ""))
        ):
            raise RecoveryExportError("recovery export security metadata is invalid")
        return metadata

    def _artifact_hmac(self, artifact_path, metadata, secret):
        authenticated_metadata = dict(metadata)
        authenticated_metadata.pop("hmac_sha256", None)
        encoded = json.dumps(
            authenticated_metadata,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        mac_key = hashlib.pbkdf2_hmac(
            "sha256",
            secret,
            self.HMAC_DOMAIN,
            self.ITERATIONS,
            dklen=32,
        )
        digest = hmac.new(mac_key, digestmod=hashlib.sha256)
        digest.update(self.HMAC_PREFIX)
        digest.update(encoded)
        digest.update(b"\x00")
        with open(artifact_path, "rb") as input_file:
            for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _openssl(self, arguments, secret):
        process = subprocess.Popen(
            [self.openssl_path] + list(arguments),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        stdout, stderr = process.communicate(secret + b"\n")
        if process.returncode != 0:
            raise RecoveryExportError(
                "OpenSSL recovery export operation failed"
            )
        return stdout

    @staticmethod
    def _create_archive(backup_dir, backup_id, archive_path):
        if not os.path.isdir(backup_dir) or os.path.islink(backup_dir):
            raise RecoveryExportError("verified backup directory is unavailable")
        with tarfile.open(archive_path, "w:gz") as archive:
            archive.add(backup_dir, arcname=backup_id, recursive=True)
        os.chmod(archive_path, 0o600)

    @staticmethod
    def _safe_extract(archive_path, destination):
        destination = os.path.abspath(destination)
        with tarfile.open(archive_path, "r:gz") as archive:
            members = archive.getmembers()
            for member in members:
                target = os.path.abspath(os.path.join(destination, member.name))
                if (
                    target != destination
                    and not target.startswith(destination + os.sep)
                ):
                    raise RecoveryExportError("archive path escapes destination")
                if member.issym() or member.islnk() or member.isdev():
                    raise RecoveryExportError("archive contains an unsafe entry")
                if not (member.isdir() or member.isfile()):
                    raise RecoveryExportError("archive entry type is unsupported")
            archive.extractall(destination, members=members)

    @staticmethod
    def _validate_backup_id(backup_id):
        backup_id = str(backup_id or "")
        if not BACKUP_ID_PATTERN.match(backup_id):
            raise RecoveryExportError("invalid disaster recovery backup id")
        return backup_id

    @staticmethod
    def _validate_secret(secret):
        if isinstance(secret, str):
            secret = secret.encode("utf-8")
        if not isinstance(secret, bytes) or len(secret) < 16 or len(secret) > 1024:
            raise RecoveryExportError(
                "recovery export passphrase must contain 16 to 1024 bytes"
            )
        if b"\x00" in secret or b"\n" in secret or b"\r" in secret:
            raise RecoveryExportError("recovery export passphrase is invalid")
        return secret

    @staticmethod
    def _regular_file(path):
        path = os.path.abspath(path)
        if not os.path.isfile(path) or os.path.islink(path):
            raise RecoveryExportError("recovery export file is unavailable")
        return path

    @staticmethod
    def _trusted_directory(path, create=False):
        path = os.path.abspath(path)
        if create and not os.path.isdir(path):
            os.makedirs(path)
        if not os.path.isdir(path) or os.path.islink(path):
            raise RecoveryExportError("recovery export directory is unavailable")
        return path

    @staticmethod
    def _sha256_file(path):
        digest = hashlib.sha256()
        with open(path, "rb") as input_file:
            for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _public_summary(metadata, verified):
        return {
            "schema_version": metadata["schema_version"],
            "status": "VERIFIED" if verified else "CREATED",
            "backup_id": metadata["backup_id"],
            "artifact_file": metadata["artifact_file"],
            "artifact_bytes": int(metadata["artifact_bytes"]),
            "artifact_sha256": metadata["artifact_sha256"],
            "manifest_sha256": metadata["manifest_sha256"],
            "file_count": int(metadata["file_count"]),
            "source_bytes": int(metadata["source_bytes"]),
            "encryption": metadata["encryption"],
            "authentication": metadata["authentication"],
            "kdf": metadata["kdf"],
            "iterations": int(metadata["iterations"]),
            "credentials_included": False,
            "absolute_paths_included": False,
            "plaintext_persisted": False,
            "verified": bool(verified),
        }
