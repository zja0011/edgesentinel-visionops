import hashlib
import os
import tempfile
import unittest

from packages.harness.default_tools import build_default_registry
from packages.vision.model_manifest import (
    VisionModelManifestStore,
    build_vision_model_manifest,
    infer_precision,
    verify_vision_model_manifest,
)


class VisionModelManifestTests(unittest.TestCase):
    def build_fixture(self, directory):
        model_root = os.path.join(directory, "networks")
        model_dir = os.path.join(
            model_root,
            "SSD-Mobilenet-v2",
        )
        os.makedirs(model_dir)
        engine_path = os.path.join(
            model_dir,
            "ssd.GPU.FP16.engine",
        )
        engine_bytes = b"deterministic-tensorrt-engine"
        with open(engine_path, "wb") as engine_file:
            engine_file.write(engine_bytes)
        manifest = build_vision_model_manifest(
            "ssd-mobilenet-v2",
            0.5,
            engine_path,
            model_root,
        )
        manifest_path = os.path.join(
            directory,
            "data",
            "state",
            "current-model.json",
        )
        VisionModelManifestStore(manifest_path).write(manifest)
        return (
            model_root,
            engine_path,
            engine_bytes,
            manifest_path,
            manifest,
        )

    def test_builds_safe_verified_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            (
                model_root,
                engine_path,
                engine_bytes,
                manifest_path,
                manifest,
            ) = self.build_fixture(directory)

            expected = hashlib.sha256(engine_bytes).hexdigest()
            self.assertEqual(
                manifest["integrity"]["status"],
                "VERIFIED",
            )
            self.assertEqual(
                manifest["artifact"]["sha256"],
                expected,
            )
            self.assertEqual(
                manifest["artifact"]["relative_path"],
                "SSD-Mobilenet-v2/ssd.GPU.FP16.engine",
            )
            self.assertEqual(
                manifest["artifact"]["precision"],
                "FP16",
            )
            self.assertFalse(
                manifest["absolute_paths_included"]
            )
            self.assertNotIn(directory, str(manifest))

    def test_verification_detects_match_and_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            (
                model_root,
                engine_path,
                unused_engine_bytes,
                unused_manifest_path,
                manifest,
            ) = self.build_fixture(directory)

            matched = verify_vision_model_manifest(
                manifest,
                model_root,
            )
            with open(engine_path, "ab") as engine_file:
                engine_file.write(b"-changed")
            mismatched = verify_vision_model_manifest(
                manifest,
                model_root,
            )

            self.assertEqual(
                matched["verification"]["status"],
                "MATCH",
            )
            self.assertEqual(
                mismatched["verification"]["status"],
                "MISMATCH",
            )
            self.assertNotEqual(
                mismatched["verification"]["expected_sha256"],
                mismatched["verification"]["current_sha256"],
            )

    def test_engine_outside_trusted_root_is_not_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            model_root = os.path.join(directory, "trusted")
            os.makedirs(model_root)
            outside = os.path.join(directory, "outside.engine")
            with open(outside, "wb") as engine_file:
                engine_file.write(b"outside")

            manifest = build_vision_model_manifest(
                "ssd-mobilenet-v2",
                0.5,
                outside,
                model_root,
            )

            self.assertIsNone(manifest["artifact"])
            self.assertEqual(
                manifest["integrity"]["status"],
                "UNAVAILABLE",
            )

    def test_registry_exposes_read_only_verified_model_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            (
                model_root,
                unused_engine_path,
                unused_engine_bytes,
                manifest_path,
                unused_manifest,
            ) = self.build_fixture(directory)
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                audit_path=os.path.join(
                    directory,
                    "audit.jsonl",
                ),
                model_manifest_path=manifest_path,
                model_root=model_root,
            )

            response = registry.invoke(
                "vision.get_model_info",
                {},
            )
            schema = {
                item["name"]: item
                for item in registry.schemas()
            }["vision.get_model_info"]

            self.assertEqual(response["status"], "SUCCEEDED")
            self.assertEqual(
                response["result"]["verification"]["status"],
                "MATCH",
            )
            self.assertTrue(
                schema["annotations"]["readOnlyHint"]
            )
            self.assertEqual(
                schema["annotations"]["riskLevel"],
                "L0",
            )

    def test_precision_inference_is_bounded(self):
        self.assertEqual(infer_precision("model.INT8.engine"), "INT8")
        self.assertEqual(infer_precision("model.engine"), "UNKNOWN")


if __name__ == "__main__":
    unittest.main()
