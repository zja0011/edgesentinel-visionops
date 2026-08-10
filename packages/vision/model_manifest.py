"""Vision model provenance and read-only integrity verification."""

import hashlib
import json
import os
import platform
import re
import tempfile

from packages.vision.schemas import beijing_timestamp


class ModelManifestUnavailable(RuntimeError):
    pass


class VisionModelManifestStore(object):
    def __init__(self, path):
        self.path = os.path.abspath(path)

    def write(self, payload):
        payload = dict(payload)
        parent = os.path.dirname(self.path)
        if not os.path.isdir(parent):
            os.makedirs(parent)
        descriptor, temporary_path = tempfile.mkstemp(
            prefix=".current-model-",
            suffix=".tmp",
            dir=parent,
        )
        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as manifest_file:
                json.dump(
                    payload,
                    manifest_file,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                manifest_file.write("\n")
                manifest_file.flush()
            os.replace(temporary_path, self.path)
        finally:
            if os.path.exists(temporary_path):
                os.unlink(temporary_path)

    def read(self):
        if not os.path.isfile(self.path):
            raise ModelManifestUnavailable(
                "vision model manifest does not exist"
            )
        try:
            with open(
                self.path,
                "r",
                encoding="utf-8",
            ) as manifest_file:
                payload = json.load(manifest_file)
        except (OSError, UnicodeError, ValueError) as error:
            raise ModelManifestUnavailable(
                "vision model manifest is unavailable"
            ) from error
        if not isinstance(payload, dict):
            raise ModelManifestUnavailable(
                "vision model manifest must be an object"
            )
        for key in (
            "schema_version",
            "manifest_id",
            "network",
            "backend",
            "integrity",
        ):
            if key not in payload:
                raise ModelManifestUnavailable(
                    "vision model manifest is missing {0}".format(
                        key
                    )
                )
        return payload


def build_vision_model_manifest(
    network,
    threshold,
    engine_path,
    model_root,
):
    network = str(network).strip()
    if not network or len(network) > 128:
        raise ValueError("network is invalid")
    model_root = os.path.realpath(os.path.abspath(model_root))
    resolved_engine = (
        os.path.realpath(os.path.abspath(engine_path))
        if engine_path
        else None
    )
    artifact = None
    integrity_status = "UNAVAILABLE"
    digest = None
    if (
        resolved_engine
        and _is_within(resolved_engine, model_root)
        and os.path.isfile(resolved_engine)
    ):
        digest = sha256_file(resolved_engine)
        relative_path = os.path.relpath(
            resolved_engine,
            model_root,
        ).replace(os.sep, "/")
        artifact = {
            "name": os.path.basename(resolved_engine),
            "relative_path": relative_path,
            "size_bytes": int(os.path.getsize(resolved_engine)),
            "sha256": digest,
            "precision": infer_precision(resolved_engine),
        }
        integrity_status = "VERIFIED"
    manifest_suffix = (
        digest[:16] if digest else "unavailable"
    )
    return {
        "schema_version": "1.0",
        "manifest_id": "mdl_{0}".format(manifest_suffix),
        "generated_at": beijing_timestamp(),
        "network": network,
        "backend": "TensorRT",
        "runtime": "jetson-inference",
        "threshold": round(float(threshold), 6),
        "artifact": artifact,
        "platform": {
            "architecture": platform.machine() or "unknown",
            "l4t_release": read_l4t_release(),
        },
        "integrity": {
            "status": integrity_status,
            "algorithm": "sha256",
        },
        "absolute_paths_included": False,
        "read_only": True,
    }


def verify_vision_model_manifest(payload, model_root):
    payload = dict(payload)
    artifact = payload.get("artifact")
    expected_digest = (
        artifact.get("sha256")
        if isinstance(artifact, dict)
        else None
    )
    relative_path = (
        artifact.get("relative_path")
        if isinstance(artifact, dict)
        else None
    )
    status = "UNAVAILABLE"
    current_digest = None
    size_bytes = None
    if expected_digest and relative_path:
        model_root = os.path.realpath(os.path.abspath(model_root))
        candidate = os.path.realpath(os.path.abspath(
            os.path.join(
                model_root,
                str(relative_path).replace("/", os.sep),
            )
        ))
        if not _is_within(candidate, model_root):
            status = "INVALID_PATH"
        elif not os.path.isfile(candidate):
            status = "MISSING"
        else:
            current_digest = sha256_file(candidate)
            size_bytes = int(os.path.getsize(candidate))
            status = (
                "MATCH"
                if current_digest == expected_digest
                else "MISMATCH"
            )
    result = dict(payload)
    result["verification"] = {
        "status": status,
        "checked_at": beijing_timestamp(),
        "expected_sha256": expected_digest,
        "current_sha256": current_digest,
        "size_bytes": size_bytes,
    }
    result["read_only"] = True
    return result


def sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as artifact_file:
        while True:
            chunk = artifact_file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def infer_precision(path):
    name = os.path.basename(path).upper()
    for precision in ("INT8", "FP16", "FP32"):
        if precision in name:
            return precision
    return "UNKNOWN"


def read_l4t_release(path="/etc/nv_tegra_release"):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as release_file:
            first_line = release_file.readline(512)
    except OSError:
        return None
    match = re.search(
        r"#\s*R(\d+).*REVISION:\s*([0-9.]+)",
        first_line,
    )
    if match is None:
        return None
    return "R{0}.{1}".format(
        match.group(1),
        match.group(2),
    )


def _is_within(path, root):
    path = os.path.realpath(os.path.abspath(path))
    root = os.path.realpath(os.path.abspath(root))
    try:
        return os.path.commonpath([path, root]) == root
    except (AttributeError, ValueError):
        root_prefix = root.rstrip(os.sep) + os.sep
        return path == root or path.startswith(root_prefix)
