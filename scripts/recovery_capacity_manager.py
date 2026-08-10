#!/usr/bin/python3
"""Root-owned, plan-gated local disaster-recovery capacity manager."""

from __future__ import print_function

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import stat
import sys


BACKUP_DIRECTORY = "/home/nvidia/projects/edgesentinel-visionops/data/recovery/backups"
EXPORT_DIRECTORY = "/home/nvidia/edgesentinel-recovery-exports/encrypted"
AUDIT_PATH = "/home/nvidia/edgesentinel-recovery-exports/recovery-capacity-audit.jsonl"
LOCK_PATH = "/run/lock/edgesentinel-recovery-export.lock"
CONFIRMATION = "DELETE_PREVIEWED_LOCAL_RECOVERY_BACKUPS"
BACKUP_PATTERN = re.compile(r"^dr_[0-9a-f]{32}$")
METADATA_PATTERN = re.compile(r"^(dr_[0-9a-f]{32})\.esdr\.json$")
HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
TIMESTAMP_PATTERN = re.compile(
    r"^20[0-9]{2}-[0-9]{2}-[0-9]{2}T[0-9:.]+[+]08:00$"
)


class CapacityError(RuntimeError):
    pass


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def trusted_directory(path):
    path = os.path.abspath(path)
    value = os.lstat(path)
    if (
        not stat.S_ISDIR(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or os.path.realpath(path) != path
    ):
        raise CapacityError("recovery capacity directory is unsafe")
    return path


def trusted_file(path):
    path = os.path.abspath(path)
    value = os.lstat(path)
    if (
        not stat.S_ISREG(value.st_mode)
        or stat.S_ISLNK(value.st_mode)
        or os.path.realpath(path) != path
    ):
        raise CapacityError("recovery capacity file is unsafe")
    return path


def directory_bytes(path):
    total = 0

    def fail_walk(error):
        raise error

    for current, directories, files in os.walk(
        trusted_directory(path),
        topdown=True,
        onerror=fail_walk,
        followlinks=False,
    ):
        for name in list(directories):
            trusted_directory(os.path.join(current, name))
        for name in files:
            candidate = trusted_file(os.path.join(current, name))
            total += os.lstat(candidate).st_size
    return total


def scan_exports(export_directory):
    export_directory = trusted_directory(export_directory)
    records = []
    for name in os.listdir(export_directory):
        match = METADATA_PATTERN.match(name)
        if not match:
            continue
        backup_id = match.group(1)
        metadata_path = trusted_file(os.path.join(export_directory, name))
        artifact_path = trusted_file(
            os.path.join(export_directory, backup_id + ".esdr")
        )
        if os.path.getsize(metadata_path) > 65536:
            raise CapacityError("recovery export metadata is oversized")
        with open(metadata_path, encoding="utf-8") as input_file:
            metadata = json.load(input_file)
        created_at = str(metadata.get("created_at") or "")
        artifact_sha256 = str(metadata.get("artifact_sha256") or "")
        if (
            metadata.get("backup_id") != backup_id
            or metadata.get("artifact_file") != backup_id + ".esdr"
            or metadata.get("credentials_included") is not False
            or metadata.get("plaintext_persisted") is not False
            or not TIMESTAMP_PATTERN.match(created_at)
            or not HASH_PATTERN.match(artifact_sha256)
            or int(metadata.get("artifact_bytes") or -1)
            != os.path.getsize(artifact_path)
        ):
            raise CapacityError("recovery export metadata is invalid")
        records.append(
            {
                "backup_id": backup_id,
                "created_at": created_at,
                "bytes": int(metadata["artifact_bytes"]),
                "artifact_sha256": artifact_sha256,
            }
        )
    records.sort(key=lambda item: item["created_at"], reverse=True)
    if not records:
        raise CapacityError("no encrypted recovery export is available")
    return records


def scan_local_backups(backup_directory):
    backup_directory = trusted_directory(backup_directory)
    records = []
    for backup_id in os.listdir(backup_directory):
        if not BACKUP_PATTERN.match(backup_id):
            continue
        directory = trusted_directory(os.path.join(backup_directory, backup_id))
        manifest_path = trusted_file(os.path.join(directory, "manifest.json"))
        hash_path = trusted_file(os.path.join(directory, "manifest.sha256"))
        with open(hash_path, encoding="ascii") as input_file:
            expected_hash = input_file.read(128).strip().lower()
        actual_hash = sha256_file(manifest_path)
        if not HASH_PATTERN.match(expected_hash) or expected_hash != actual_hash:
            raise CapacityError("local backup manifest integrity mismatch")
        with open(manifest_path, encoding="utf-8") as input_file:
            manifest = json.load(input_file)
        if (
            manifest.get("backup_id") != backup_id
            or manifest.get("status") != "COMPLETE"
            or manifest.get("credentials_included") is not False
        ):
            raise CapacityError("local backup manifest is invalid")
        records.append(
            {
                "backup_id": backup_id,
                "bytes": directory_bytes(directory),
                "manifest_sha256": actual_hash,
            }
        )
    records.sort(key=lambda item: item["backup_id"])
    return records


def build_plan(backup_directory, export_directory, keep_count, maximum_bytes):
    if keep_count < 1 or keep_count > 52:
        raise CapacityError("keep count must be between 1 and 52")
    if maximum_bytes < 104857600 or maximum_bytes > 10737418240:
        raise CapacityError("maximum bytes must be between 100 MiB and 10 GiB")
    exports = scan_exports(export_directory)
    local_backups = scan_local_backups(backup_directory)
    retained_exports = []
    candidate_exports = []
    running_bytes = 0
    for index, record in enumerate(exports):
        fits = (
            len(retained_exports) < keep_count
            and running_bytes + record["bytes"] <= maximum_bytes
        )
        if index == 0 or fits:
            retained_exports.append(record)
            running_bytes += record["bytes"]
        else:
            candidate_exports.append(record)
    retained_ids = set(item["backup_id"] for item in retained_exports)
    local_candidates = [
        item for item in local_backups if item["backup_id"] not in retained_ids
    ]
    canonical = {
        "schema_version": "1.0",
        "keep_count": keep_count,
        "maximum_bytes": maximum_bytes,
        "exports": exports,
        "local_backups": local_backups,
        "retained_export_ids": sorted(retained_ids),
        "local_candidate_ids": sorted(
            item["backup_id"] for item in local_candidates
        ),
    }
    encoded = json.dumps(
        canonical,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")
    plan_id = "rcp_" + hashlib.sha256(encoded).hexdigest()[:32]
    return {
        "plan_id": plan_id,
        "keep_count": keep_count,
        "maximum_bytes": maximum_bytes,
        "exports": exports,
        "retained_exports": retained_exports,
        "candidate_exports": candidate_exports,
        "local_backups": local_backups,
        "local_candidates": local_candidates,
    }


def append_audit(audit_path, payload):
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(audit_path, flags, 0o600)
    try:
        os.write(
            descriptor,
            (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"),
        )
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def apply_plan(plan, expected_plan_id, confirmation, backup_directory, audit_path):
    if expected_plan_id != plan["plan_id"]:
        raise CapacityError("recovery capacity plan is stale or does not match")
    if confirmation != CONFIRMATION:
        raise CapacityError("recovery capacity confirmation phrase is invalid")
    prepared = {
        "schema_version": "1.0",
        "status": "PREPARED",
        "plan_id": plan["plan_id"],
        "candidate_count": len(plan["local_candidates"]),
        "candidate_bytes": sum(item["bytes"] for item in plan["local_candidates"]),
        "encrypted_exports_deleted": 0,
        "credentials_exposed": False,
    }
    append_audit(audit_path, prepared)
    deleted_count = 0
    deleted_bytes = 0
    backup_directory = trusted_directory(backup_directory)
    for record in plan["local_candidates"]:
        candidate = os.path.abspath(
            os.path.join(backup_directory, record["backup_id"])
        )
        if (
            os.path.dirname(candidate) != backup_directory
            or os.path.basename(candidate) != record["backup_id"]
        ):
            raise CapacityError("local cleanup path escaped backup directory")
        trusted_directory(candidate)
        manifest_path = trusted_file(os.path.join(candidate, "manifest.json"))
        if sha256_file(manifest_path) != record["manifest_sha256"]:
            raise CapacityError("local cleanup plan became stale")
        shutil.rmtree(candidate)
        deleted_count += 1
        deleted_bytes += record["bytes"]
    completed = {
        "schema_version": "1.0",
        "status": "COMPLETED",
        "plan_id": plan["plan_id"],
        "deleted_local_backups": deleted_count,
        "deleted_local_bytes": deleted_bytes,
        "encrypted_exports_deleted": 0,
        "credentials_exposed": False,
    }
    append_audit(audit_path, completed)
    return completed


def print_preview(plan):
    latest_bytes = plan["exports"][0]["bytes"]
    print()
    print("Recovery Capacity Preview summary:")
    print("Status: PASS")
    print("Profile: DEMO_WEEKLY")
    print("Plan ID:", plan["plan_id"])
    print("Encrypted backups:", len(plan["exports"]))
    print("Encrypted bytes:", sum(item["bytes"] for item in plan["exports"]))
    print("Estimated annual growth bytes:", latest_bytes * 52)
    print("Retention keep count:", plan["keep_count"])
    print("Retention maximum bytes:", plan["maximum_bytes"])
    print("Retained encrypted backups:", len(plan["retained_exports"]))
    print("Retention candidate exports:", len(plan["candidate_exports"]))
    print("Local backups:", len(plan["local_backups"]))
    print("Local backup bytes:", sum(item["bytes"] for item in plan["local_backups"]))
    print("Local cleanup candidates:", len(plan["local_candidates"]))
    print("Local cleanup candidate bytes:", sum(
        item["bytes"] for item in plan["local_candidates"]
    ))
    print("Delete performed: False")
    print("Encrypted exports protected: True")
    print("Credentials exposed: False")
    print("Recovery Capacity Preview smoke test passed.")


def build_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    preview = subparsers.add_parser("preview")
    preview.add_argument("--keep-count", type=int, default=4)
    preview.add_argument("--maximum-bytes", type=int, default=536870912)
    apply = subparsers.add_parser("apply")
    apply.add_argument("--plan-id", required=True)
    return parser


def main(argv=None):
    if os.geteuid() != 0:
        raise CapacityError("recovery capacity manager must run as root")
    arguments = build_parser().parse_args(argv)
    if arguments.command not in ("preview", "apply"):
        raise CapacityError("a recovery capacity command is required")
    lock_descriptor = os.open(LOCK_PATH, os.O_WRONLY | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except IOError:
            raise CapacityError("scheduled recovery export is currently running")
        plan = build_plan(
            BACKUP_DIRECTORY,
            EXPORT_DIRECTORY,
            4 if arguments.command == "apply" else arguments.keep_count,
            536870912 if arguments.command == "apply" else arguments.maximum_bytes,
        )
        if arguments.command == "preview":
            print_preview(plan)
            return 0
        print("Plan:", plan["plan_id"])
        print("Local backups to delete:", len(plan["local_candidates"]))
        print("Local bytes to delete:", sum(
            item["bytes"] for item in plan["local_candidates"]
        ))
        print("Encrypted exports to delete: 0")
        confirmation = input(
            "Type {0} to continue: ".format(CONFIRMATION)
        )
        result = apply_plan(
            plan,
            arguments.plan_id,
            confirmation,
            BACKUP_DIRECTORY,
            AUDIT_PATH,
        )
        print()
        print("Recovery Capacity Cleanup summary:")
        print("Status:", result["status"])
        print("Plan ID:", result["plan_id"])
        print("Deleted local backups:", result["deleted_local_backups"])
        print("Deleted local bytes:", result["deleted_local_bytes"])
        print("Encrypted exports deleted: 0")
        print("Credentials exposed: False")
        print("Recovery Capacity Cleanup passed.")
        return 0
    finally:
        os.close(lock_descriptor)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (CapacityError, OSError, ValueError, json.JSONDecodeError) as error:
        sys.stderr.write("Recovery capacity operation failed: {0}\n".format(error))
        sys.exit(1)
