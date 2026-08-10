"""Verify the active TensorRT model manifest through the Harness."""

import argparse
import os
import sys

from packages.harness.default_tools import build_default_registry
from packages.harness.utf8 import write_json_atomic


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=os.getcwd())
    parser.add_argument(
        "--database",
        default="data/events/edgesentinel.db",
    )
    parser.add_argument(
        "--manifest",
        default="data/state/current-model.json",
    )
    parser.add_argument(
        "--model-root",
        default="/jetson-inference/data/networks",
    )
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--result-output", required=True)
    return parser


def resolve(project_dir, path):
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(project_dir, path))


def main():
    args = build_parser().parse_args()
    project_dir = os.path.abspath(args.project_dir)
    registry = build_default_registry(
        project_dir,
        resolve(project_dir, args.database),
        audit_path=resolve(project_dir, args.audit_output),
        model_manifest_path=resolve(
            project_dir,
            args.manifest,
        ),
        model_root=os.path.abspath(args.model_root),
    )
    response = registry.invoke("vision.get_model_info", {})
    if response.get("status") != "SUCCEEDED":
        raise SystemExit(
            "model info tool failed: {0}".format(
                response.get("error")
            )
        )
    model = response.get("result") or {}
    artifact = model.get("artifact") or {}
    verification = model.get("verification") or {}
    relative_path = artifact.get("relative_path") or ""
    expected_sha256 = verification.get("expected_sha256")
    current_sha256 = verification.get("current_sha256")
    if (
        model.get("network") != "ssd-mobilenet-v2"
        or model.get("backend") != "TensorRT"
        or artifact.get("precision") != "FP16"
        or int(artifact.get("size_bytes") or 0) <= 0
        or len(expected_sha256 or "") != 64
        or expected_sha256 != current_sha256
        or verification.get("status") != "MATCH"
        or not relative_path
        or os.path.isabs(relative_path)
        or ".." in relative_path.split("/")
        or model.get("absolute_paths_included")
        or not model.get("read_only")
    ):
        raise SystemExit("vision model manifest is invalid")
    result = {
        "schema_version": "1.0",
        "tool": "vision.get_model_info",
        "risk": "L0",
        "read_only": True,
        "manifest_id": model.get("manifest_id"),
        "network": model.get("network"),
        "backend": model.get("backend"),
        "precision": artifact.get("precision"),
        "engine": relative_path,
        "engine_bytes": artifact.get("size_bytes"),
        "sha256": expected_sha256,
        "integrity": verification.get("status"),
        "l4t_release": (
            model.get("platform") or {}
        ).get("l4t_release"),
        "architecture": (
            model.get("platform") or {}
        ).get("architecture"),
        "absolute_paths_included": False,
    }
    write_json_atomic(args.result_output, result)
    print("")
    print("Vision Model acceptance summary:")
    print("Tool: vision.get_model_info SUCCEEDED")
    print("Risk: L0")
    print("Read only: True")
    print("Manifest ID: {0}".format(result["manifest_id"]))
    print("Network: {0}".format(result["network"]))
    print("Backend: {0}".format(result["backend"]))
    print("Precision: {0}".format(result["precision"]))
    print("Engine: {0}".format(result["engine"]))
    print("Engine bytes: {0}".format(result["engine_bytes"]))
    print("SHA-256: {0}".format(result["sha256"]))
    print("Integrity: MATCH")
    print("L4T: {0}".format(result["l4t_release"]))
    print("Architecture: {0}".format(result["architecture"]))
    print("Absolute paths exposed: False")
    print("Result file: {0}".format(args.result_output))
    print("Audit log: {0}".format(args.audit_output))
    print("Vision Model smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
