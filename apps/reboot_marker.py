"""Create and verify a safe EdgeSentinel host-reboot marker."""

import argparse
import hashlib
import json
import os
import stat
import sys

from apps.service_manager import timestamp_text
from packages.harness.utf8 import print_json_utf8, write_json_atomic


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)
DEFAULT_MARKER_PATH = os.path.join(
    PROJECT_DIR,
    "data",
    "runtime",
    "reboot-preflight.json",
)
DEFAULT_TLS_CERTIFICATE_PATH = (
    "/dev/shm/edgesentinel-tls/server.crt"
)
MAX_CERTIFICATE_BYTES = 1024 * 1024


class RebootMarkerError(RuntimeError):
    """Raised when reboot evidence is missing or inconsistent."""


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as input_file:
            value = input_file.read().strip()
    except OSError as error:
        raise RebootMarkerError(
            "required system value is unavailable: {}".format(path)
        ) from error
    if not value:
        raise RebootMarkerError(
            "required system value is empty: {}".format(path)
        )
    return value


def read_json(path):
    try:
        with open(path, "r", encoding="utf-8") as input_file:
            payload = json.load(input_file)
    except (OSError, ValueError) as error:
        raise RebootMarkerError(
            "required JSON is unavailable: {}".format(path)
        ) from error
    if not isinstance(payload, dict):
        raise RebootMarkerError(
            "required JSON must contain an object: {}".format(path)
        )
    return payload


def read_uptime(path="/proc/uptime"):
    value = read_text(path).split()[0]
    try:
        return round(float(value), 3)
    except ValueError as error:
        raise RebootMarkerError("system uptime is invalid") from error


def certificate_fingerprint(path):
    try:
        metadata = os.lstat(path)
    except OSError as error:
        raise RebootMarkerError(
            "TLS certificate is unavailable"
        ) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(
        metadata.st_mode
    ):
        raise RebootMarkerError(
            "TLS certificate path is unsafe"
        )
    if metadata.st_size <= 0 or metadata.st_size > MAX_CERTIFICATE_BYTES:
        raise RebootMarkerError("TLS certificate size is invalid")
    try:
        with open(path, "rb") as certificate_file:
            certificate = certificate_file.read(
                MAX_CERTIFICATE_BYTES + 1
            )
    except OSError as error:
        raise RebootMarkerError(
            "TLS certificate cannot be read"
        ) from error
    if len(certificate) > MAX_CERTIFICATE_BYTES:
        raise RebootMarkerError("TLS certificate size is invalid")
    return hashlib.sha256(certificate).hexdigest()


def runtime_snapshot(
    project_dir=PROJECT_DIR,
    boot_id_path="/proc/sys/kernel/random/boot_id",
    uptime_path="/proc/uptime",
    tls_certificate_path=DEFAULT_TLS_CERTIFICATE_PATH,
):
    state = read_json(
        os.path.join(
            project_dir,
            "data",
            "runtime",
            "service.json",
        )
    )
    vision = read_json(
        os.path.join(
            project_dir,
            "data",
            "state",
            "current-vision.json",
        )
    )
    if state.get("status") != "running":
        raise RebootMarkerError("managed runtime is not running")
    if state.get("config_save_enabled") is not False:
        raise RebootMarkerError(
            "managed runtime is not in read-only boot mode"
        )
    tls_enabled = state.get("tls_enabled") is True
    tls_public_origin = state.get("tls_public_origin")
    if tls_enabled and not str(tls_public_origin or "").startswith(
        "https://"
    ):
        raise RebootMarkerError("managed TLS origin is invalid")
    return {
        "boot_id": read_text(boot_id_path),
        "uptime_seconds": read_uptime(uptime_path),
        "service_started_at": state.get("started_at"),
        "service_pid": state.get("pid"),
        "vision_frame_id": vision.get("frame_id"),
        "vision_timestamp": vision.get("timestamp"),
        "model_mode": state.get("model_mode"),
        "tls_enabled": tls_enabled,
        "tls_public_origin": (
            tls_public_origin if tls_enabled else None
        ),
        "tls_certificate_sha256": (
            certificate_fingerprint(tls_certificate_path)
            if tls_enabled
            else None
        ),
    }


def prepare_marker(
    marker_path=DEFAULT_MARKER_PATH,
    project_dir=PROJECT_DIR,
    boot_id_path="/proc/sys/kernel/random/boot_id",
    uptime_path="/proc/uptime",
    tls_certificate_path=DEFAULT_TLS_CERTIFICATE_PATH,
):
    snapshot = runtime_snapshot(
        project_dir=project_dir,
        boot_id_path=boot_id_path,
        uptime_path=uptime_path,
        tls_certificate_path=tls_certificate_path,
    )
    payload = {
        "schema_version": "1.0",
        "prepared_at": timestamp_text(),
        "purpose": "host_reboot_acceptance",
        "before": snapshot,
        "contains_secret": False,
    }
    write_json_atomic(marker_path, payload)
    try:
        os.sync()
    except AttributeError:
        pass
    return payload


def verify_reboot(
    marker_path=DEFAULT_MARKER_PATH,
    project_dir=PROJECT_DIR,
    boot_id_path="/proc/sys/kernel/random/boot_id",
    uptime_path="/proc/uptime",
    tls_certificate_path=DEFAULT_TLS_CERTIFICATE_PATH,
):
    marker = read_json(marker_path)
    before = marker.get("before")
    if (
        marker.get("purpose") != "host_reboot_acceptance"
        or not isinstance(before, dict)
        or marker.get("contains_secret") is not False
    ):
        raise RebootMarkerError("reboot marker is invalid")
    after = runtime_snapshot(
        project_dir=project_dir,
        boot_id_path=boot_id_path,
        uptime_path=uptime_path,
        tls_certificate_path=tls_certificate_path,
    )
    boot_changed = before.get("boot_id") != after.get("boot_id")
    service_restarted = (
        bool(before.get("service_started_at"))
        and bool(after.get("service_started_at"))
        and before.get("service_started_at")
        != after.get("service_started_at")
    )
    if not boot_changed:
        raise RebootMarkerError(
            "host boot ID did not change; reboot is not proven"
        )
    if not service_restarted:
        raise RebootMarkerError(
            "managed service start time did not change"
        )
    tls_recovered = before.get("tls_enabled") == after.get(
        "tls_enabled"
    )
    if not tls_recovered:
        raise RebootMarkerError("managed TLS mode changed after reboot")
    tls_certificate_unchanged = True
    if before.get("tls_enabled"):
        tls_certificate_unchanged = (
            before.get("tls_public_origin")
            == after.get("tls_public_origin")
            and before.get("tls_certificate_sha256")
            == after.get("tls_certificate_sha256")
        )
        if not tls_certificate_unchanged:
            raise RebootMarkerError(
                "managed TLS identity changed after reboot"
            )
    return {
        "schema_version": "1.0",
        "status": "verified",
        "boot_changed": True,
        "service_restarted": True,
        "uptime_reset": (
            after["uptime_seconds"] < before["uptime_seconds"]
        ),
        "tls_recovered": tls_recovered,
        "tls_certificate_unchanged": tls_certificate_unchanged,
        "before": before,
        "after": after,
        "contains_secret": False,
    }


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Prepare or verify the EdgeSentinel host reboot marker."
        )
    )
    parser.add_argument("command", choices=("prepare", "verify"))
    parser.add_argument("--marker", default=DEFAULT_MARKER_PATH)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        payload = (
            prepare_marker(marker_path=args.marker)
            if args.command == "prepare"
            else verify_reboot(marker_path=args.marker)
        )
        print_json_utf8(payload)
        return 0
    except RebootMarkerError as error:
        print("ERROR: {}".format(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
