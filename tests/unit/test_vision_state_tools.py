import json
import os
import tempfile
import time
import unittest

from packages.harness.default_tools import build_default_registry
from packages.harness.registry import ToolInvocationError
from packages.vision.state_store import (
    CurrentVisionStateStore,
    VisionStateUnavailable,
)


def make_state():
    return {
        "schema_version": "1.6",
        "frame_id": 25,
        "timestamp": "2026-07-25T16:00:00.000+08:00",
        "camera_id": "camera_01",
        "source": "/dev/video0",
        "width": 640,
        "height": 480,
        "inference_ms": 40.0,
        "detections": [
            {
                "class_name": "bottle",
                "confidence": 0.91,
                "bbox": [10, 20, 30, 40],
                "zone_ids": ["left_zone"],
            },
            {
                "class_name": "bottle",
                "confidence": 0.45,
                "bbox": [50, 60, 70, 80],
                "zone_ids": ["right_zone"],
            },
            {
                "class_name": "chair",
                "confidence": 0.88,
                "bbox": [90, 100, 110, 120],
                "zone_ids": ["right_zone"],
            },
        ],
        "analytics": {
            "people": {
                "current_people": 1,
                "visible_people": 1,
                "active_track_ids": [7],
            },
            "zone_config": {
                "enabled": True,
                "status": "active",
                "version": "b" * 64,
                "zone_count": 2,
                "reload_count": 0,
                "last_reload_frame": 0,
                "check_interval_frames": 30,
                "last_error": None,
            },
            "zones": [
                {
                    "zone_id": "left_zone",
                    "name": "Left Zone",
                    "current_count": 1,
                    "track_ids": [7],
                },
                {
                    "zone_id": "right_zone",
                    "name": "Right Zone",
                    "current_count": 0,
                    "track_ids": [],
                },
            ],
            "inventory": {
                "target_classes": [
                    "bottle",
                    "cup",
                    "laptop",
                ],
                "current_counts": {
                    "bottle": 1,
                    "cup": 0,
                    "laptop": 2,
                },
                "visible_counts": {
                    "bottle": 1,
                    "cup": 0,
                    "laptop": 2,
                },
                "active_track_ids": {
                    "bottle": [11],
                    "laptop": [20, 21],
                },
            },
            "track_history": {
                "retained_track_count": 1,
                "visible_track_count": 1,
                "max_points_per_track": 30,
                "tracks": [
                    {
                        "track_id": 7,
                        "class_name": "person",
                        "confidence": 0.93,
                        "visible": True,
                        "hits": 20,
                        "missed_frames": 0,
                        "first_seen_frame": 1,
                        "last_seen_frame": 25,
                        "observation_count": 20,
                        "sampled_point_count": 2,
                        "movement": "right",
                        "displacement": 0.5,
                        "current_zone_ids": ["left_zone"],
                        "points": [
                            {"frame_id": 1, "x": 0.1, "y": 0.8},
                            {"frame_id": 25, "x": 0.6, "y": 0.8},
                        ],
                    }
                ],
            },
            "performance": {
                "schema_version": "1.0",
                "status": "MEETS_TARGET",
                "total_frames": 25,
                "sample_count": 25,
                "window_size_frames": 120,
                "processing_fps": 12.5,
                "frame_interval_ms": 80.0,
                "pipeline_latency_ms": {
                    "latest": 41.0,
                    "average": 42.0,
                    "p50": 41.5,
                    "p95": 48.0,
                    "maximum": 50.0,
                },
                "targets": {
                    "minimum_fps": 5.0,
                    "maximum_p95_ms": 200.0,
                    "fps_met": True,
                    "p95_met": True,
                    "all_met": True,
                },
                "read_only": True,
            },
        },
    }


class CurrentVisionStateStoreTests(unittest.TestCase):
    def test_atomically_writes_and_reads_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "state", "current.json")
            store = CurrentVisionStateStore(path)

            store.write(make_state())
            result = store.read(max_age_seconds=5)

            self.assertEqual(result["snapshot"]["frame_id"], 25)
            self.assertFalse(result["stale"])
            self.assertEqual(
                [
                    name
                    for name in os.listdir(os.path.dirname(path))
                    if name.endswith(".tmp")
                ],
                [],
            )

    def test_marks_old_state_as_stale(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "current.json")
            store = CurrentVisionStateStore(path)
            store.write(make_state())
            old_time = time.time() - 10
            os.utime(path, (old_time, old_time))

            result = store.read(max_age_seconds=5)

            self.assertTrue(result["stale"])
            self.assertGreaterEqual(result["age_seconds"], 9)

    def test_rejects_missing_and_invalid_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "current.json")
            store = CurrentVisionStateStore(path)
            with self.assertRaises(VisionStateUnavailable):
                store.read()
            with open(path, "w", encoding="utf-8") as state_file:
                json.dump({"frame_id": 1}, state_file)
            with self.assertRaises(VisionStateUnavailable):
                store.read()


class VisionStateHarnessToolTests(unittest.TestCase):
    def test_registers_thirty_three_tools_with_writes_gated(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
            )

            names = [
                tool["name"] for tool in registry.schemas()
            ]

            self.assertEqual(
                names,
                [
                    "camera.capture_snapshot",
                    "camera.get_status",
                    "camera.restart",
                    "event.acknowledge",
                    "event.get_detail",
                    "event.query",
                    "event.summarize",
                    "evidence.verify_event",
                    "evidence.verify_recent",
                    "inventory.compare_state",
                    "inventory.get_current_state",
                    "inventory.get_removed_items",
                    "memory.forget",
                    "memory.remember",
                    "memory.search",
                    "recovery.create_backup",
                    "recovery.get_status",
                    "recovery.preview_restore",
                    "report.generate",
                    "system.cleanup_retained_data",
                    "system.get_health",
                    "system.get_retention_cleanup_history",
                    "system.get_runtime_benchmark",
                    "system.get_storage_usage",
                    "system.preview_data_retention",
                    "vision.count_objects",
                    "vision.get_current_objects",
                    "vision.get_model_info",
                    "vision.get_people_count",
                    "vision.get_performance",
                    "vision.get_track_history",
                    "vision.get_zone_status",
                    "weather.get_current",
                ],
            )
            schemas = {
                tool["name"]: tool
                for tool in registry.schemas()
            }
            snapshot = schemas["camera.capture_snapshot"][
                "annotations"
            ]
            self.assertFalse(snapshot["readOnlyHint"])
            self.assertEqual(snapshot["riskLevel"], "L1")
            self.assertFalse(snapshot["autoExecute"])
            self.assertTrue(snapshot["requiresConfirmation"])
            restart = schemas["camera.restart"]["annotations"]
            self.assertFalse(restart["readOnlyHint"])
            weather = schemas["weather.get_current"]["annotations"]
            self.assertTrue(weather["readOnlyHint"])
            self.assertTrue(weather["openWorldHint"])
            self.assertEqual(weather["riskLevel"], "L0")
            self.assertTrue(weather["autoExecute"])
            self.assertFalse(weather["requiresConfirmation"])
            memory_search = schemas["memory.search"]["annotations"]
            self.assertTrue(memory_search["readOnlyHint"])
            self.assertEqual(memory_search["riskLevel"], "L0")
            memory_write = schemas["memory.remember"]["annotations"]
            self.assertFalse(memory_write["readOnlyHint"])
            self.assertEqual(memory_write["riskLevel"], "L1")
            self.assertTrue(memory_write["requiresConfirmation"])
            self.assertEqual(restart["riskLevel"], "L2")
            self.assertFalse(restart["autoExecute"])
            self.assertTrue(restart["requiresConfirmation"])
            model_info = schemas["vision.get_model_info"][
                "annotations"
            ]
            self.assertTrue(model_info["readOnlyHint"])
            self.assertEqual(model_info["riskLevel"], "L0")
            self.assertTrue(model_info["autoExecute"])
            self.assertFalse(model_info["requiresConfirmation"])
            performance = schemas["vision.get_performance"][
                "annotations"
            ]
            self.assertTrue(performance["readOnlyHint"])
            self.assertEqual(performance["riskLevel"], "L0")
            self.assertTrue(performance["autoExecute"])
            self.assertFalse(
                performance["requiresConfirmation"]
            )
            report = schemas["report.generate"]["annotations"]
            self.assertFalse(report["readOnlyHint"])
            self.assertEqual(report["riskLevel"], "L1")
            self.assertFalse(report["autoExecute"])
            self.assertTrue(report["requiresConfirmation"])
            acknowledgement = schemas["event.acknowledge"][
                "annotations"
            ]
            self.assertFalse(acknowledgement["readOnlyHint"])
            self.assertEqual(acknowledgement["riskLevel"], "L1")
            self.assertFalse(acknowledgement["autoExecute"])
            self.assertTrue(
                acknowledgement["requiresConfirmation"]
            )
            self.assertTrue(
                schemas["event.query"]["annotations"][
                    "readOnlyHint"
                ]
            )
            evidence = schemas["evidence.verify_recent"][
                "annotations"
            ]
            self.assertTrue(evidence["readOnlyHint"])
            self.assertEqual(evidence["riskLevel"], "L0")
            self.assertTrue(evidence["autoExecute"])
            self.assertFalse(
                evidence["requiresConfirmation"]
            )
            exact_evidence = schemas["evidence.verify_event"][
                "annotations"
            ]
            self.assertTrue(exact_evidence["readOnlyHint"])
            self.assertEqual(exact_evidence["riskLevel"], "L0")
            self.assertTrue(exact_evidence["autoExecute"])
            self.assertFalse(
                exact_evidence["requiresConfirmation"]
            )
            system = schemas["system.get_health"]["annotations"]
            self.assertTrue(system["readOnlyHint"])
            self.assertEqual(system["riskLevel"], "L0")
            self.assertTrue(system["autoExecute"])
            self.assertFalse(system["requiresConfirmation"])
            benchmark = schemas[
                "system.get_runtime_benchmark"
            ]["annotations"]
            self.assertTrue(benchmark["readOnlyHint"])
            self.assertEqual(benchmark["riskLevel"], "L0")
            self.assertTrue(benchmark["autoExecute"])
            self.assertFalse(
                benchmark["requiresConfirmation"]
            )
            retention_history = schemas[
                "system.get_retention_cleanup_history"
            ]["annotations"]
            self.assertTrue(
                retention_history["readOnlyHint"]
            )
            self.assertEqual(
                retention_history["riskLevel"],
                "L0",
            )
            self.assertTrue(
                retention_history["autoExecute"]
            )
            self.assertFalse(
                retention_history["requiresConfirmation"]
            )
            storage = schemas[
                "system.get_storage_usage"
            ]["annotations"]
            self.assertTrue(storage["readOnlyHint"])
            self.assertEqual(storage["riskLevel"], "L0")
            self.assertTrue(storage["autoExecute"])
            self.assertFalse(storage["requiresConfirmation"])
            retention = schemas[
                "system.preview_data_retention"
            ]["annotations"]
            self.assertTrue(retention["readOnlyHint"])
            self.assertEqual(retention["riskLevel"], "L0")
            self.assertTrue(retention["autoExecute"])
            self.assertFalse(retention["requiresConfirmation"])
            cleanup = schemas[
                "system.cleanup_retained_data"
            ]["annotations"]
            self.assertFalse(cleanup["readOnlyHint"])
            self.assertEqual(cleanup["riskLevel"], "L2")
            self.assertFalse(cleanup["autoExecute"])
            self.assertTrue(cleanup["requiresConfirmation"])
            zones = schemas["vision.get_zone_status"][
                "annotations"
            ]
            self.assertTrue(zones["readOnlyHint"])
            self.assertEqual(zones["riskLevel"], "L0")
            self.assertTrue(zones["autoExecute"])
            self.assertFalse(zones["requiresConfirmation"])
            inventory = schemas[
                "inventory.get_current_state"
            ]["annotations"]
            self.assertTrue(inventory["readOnlyHint"])
            self.assertEqual(inventory["riskLevel"], "L0")
            self.assertTrue(inventory["autoExecute"])
            self.assertFalse(inventory["requiresConfirmation"])
            removed = schemas[
                "inventory.get_removed_items"
            ]["annotations"]
            self.assertTrue(removed["readOnlyHint"])
            self.assertEqual(removed["riskLevel"], "L0")
            self.assertTrue(removed["autoExecute"])
            self.assertFalse(removed["requiresConfirmation"])
            comparison = schemas[
                "inventory.compare_state"
            ]["annotations"]
            self.assertTrue(comparison["readOnlyHint"])
            self.assertEqual(comparison["riskLevel"], "L0")
            self.assertTrue(comparison["autoExecute"])
            self.assertFalse(
                comparison["requiresConfirmation"]
            )
            count_objects = schemas[
                "vision.count_objects"
            ]["annotations"]
            self.assertTrue(count_objects["readOnlyHint"])
            self.assertEqual(count_objects["riskLevel"], "L0")
            self.assertTrue(count_objects["autoExecute"])
            self.assertFalse(
                count_objects["requiresConfirmation"]
            )
            track_history = schemas[
                "vision.get_track_history"
            ]["annotations"]
            self.assertTrue(track_history["readOnlyHint"])
            self.assertEqual(track_history["riskLevel"], "L0")
            self.assertTrue(track_history["autoExecute"])
            self.assertFalse(
                track_history["requiresConfirmation"]
            )

    def test_performance_tool_returns_bounded_fresh_metrics(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            response = registry.invoke(
                "vision.get_performance",
                {},
            )

            self.assertEqual(response["status"], "SUCCEEDED")
            result = response["result"]
            self.assertEqual(result["processing_fps"], 12.5)
            self.assertEqual(
                result["pipeline_latency_ms"]["p95"],
                48.0,
            )
            self.assertTrue(result["targets"]["all_met"])
            self.assertTrue(result["read_only"])
            self.assertNotIn("detections", result)

    def test_people_tool_returns_count_and_freshness(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "vision.get_people_count",
                {},
            )["result"]

            self.assertEqual(result["current_people"], 1)
            self.assertEqual(result["active_track_ids"], [7])
            self.assertFalse(result["stale"])
            self.assertEqual(
                result["zone_config"]["version"],
                "b" * 64,
            )

    def test_objects_tool_returns_only_nonzero_stable_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "vision.get_current_objects",
                {},
            )["result"]

            self.assertEqual(result["total_current"], 3)
            self.assertEqual(
                result["objects"],
                [
                    {"class_name": "bottle", "count": 1},
                    {"class_name": "laptop", "count": 2},
                ],
            )

    def test_count_objects_filters_latest_frame_by_confidence(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "vision.count_objects",
                {
                    "classes": ["bottle", "chair"],
                    "minimum_confidence": 0.5,
                },
            )["result"]

            self.assertEqual(result["total_count"], 2)
            self.assertEqual(result["detected_class_count"], 2)
            self.assertEqual(
                result["counts"],
                [
                    {"class_name": "bottle", "count": 1},
                    {"class_name": "chair", "count": 1},
                ],
            )
            self.assertNotIn("detections", result)
            self.assertNotIn("bbox", json.dumps(result))
            self.assertTrue(result["read_only"])

    def test_count_objects_filters_zone_and_rejects_bad_input(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "vision.count_objects",
                {
                    "classes": ["bottle", "chair"],
                    "zone_id": "right_zone",
                },
            )["result"]

            self.assertEqual(result["selected_zone_id"], "right_zone")
            self.assertEqual(result["total_count"], 2)
            self.assertEqual(result["counts"][0]["count"], 1)
            self.assertEqual(result["counts"][1]["count"], 1)
            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "vision.count_objects",
                    {"classes": ["bottle", "bottle"]},
                )
            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "vision.count_objects",
                    {
                        "classes": ["bottle"],
                        "minimum_confidence": 1.1,
                    },
                )
            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "vision.count_objects",
                    {
                        "classes": ["bottle"],
                        "zone_id": "missing_zone",
                    },
                )

    def test_track_history_filters_and_excludes_boxes(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "vision.get_track_history",
                {"track_id": 7},
            )["result"]

            self.assertEqual(result["selected_track_id"], 7)
            self.assertEqual(result["track_count"], 1)
            self.assertEqual(result["tracks"][0]["movement"], "right")
            self.assertEqual(
                result["tracks"][0]["current_zone_ids"],
                ["left_zone"],
            )
            self.assertEqual(
                result["tracks"][0]["points"][-1],
                {"frame_id": 25, "x": 0.6, "y": 0.8},
            )
            self.assertNotIn("bbox", json.dumps(result))
            self.assertTrue(result["read_only"])

    def test_track_history_requires_a_bounded_selector(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            with self.assertRaises(ToolInvocationError):
                registry.invoke("vision.get_track_history", {})
            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "vision.get_track_history",
                    {"track_id": 0},
                )
            empty = registry.invoke(
                "vision.get_track_history",
                {"object_class": "bottle"},
            )["result"]
            self.assertEqual(empty["track_count"], 0)

    def test_inventory_tool_returns_zero_and_nonzero_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "inventory.get_current_state",
                {},
            )["result"]

            self.assertEqual(result["target_class_count"], 3)
            self.assertEqual(result["total_current"], 3)
            self.assertEqual(result["total_visible"], 3)
            self.assertEqual(
                [item["class_name"] for item in result["items"]],
                ["bottle", "cup", "laptop"],
            )
            self.assertEqual(result["items"][1]["current_count"], 0)
            self.assertEqual(
                result["items"][2]["active_track_ids"],
                [20, 21],
            )
            self.assertTrue(result["read_only"])

    def test_inventory_tool_filters_and_rejects_unknown_class(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "inventory.get_current_state",
                {"object_class": "bottle"},
            )["result"]

            self.assertEqual(
                result["selected_object_class"],
                "bottle",
            )
            self.assertEqual(result["target_class_count"], 1)
            self.assertEqual(result["total_current"], 1)
            self.assertEqual(result["total_visible"], 1)
            self.assertEqual(
                result["items"][0]["active_track_ids"],
                [11],
            )
            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "inventory.get_current_state",
                    {"object_class": "unknown_class"},
                )

    def test_inventory_comparison_reports_missing_and_matching(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "inventory.compare_state",
                {
                    "expected_counts": {
                        "bottle": 2,
                        "cup": 0,
                    }
                },
            )["result"]

            self.assertFalse(result["matches"])
            self.assertEqual(result["compared_class_count"], 2)
            self.assertEqual(result["total_expected"], 2)
            self.assertEqual(result["total_current"], 1)
            self.assertEqual(result["total_missing"], 1)
            self.assertEqual(result["total_extra"], 0)
            self.assertEqual(
                result["comparisons"][0]["missing_count"],
                1,
            )
            self.assertTrue(result["comparisons"][1]["matches"])
            self.assertTrue(result["read_only"])

    def test_inventory_comparison_rejects_bad_baseline(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "inventory.compare_state",
                    {"expected_counts": {"bottle": -1}},
                )
            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "inventory.compare_state",
                    {"expected_counts": {"unknown": 1}},
                )

    def test_zone_tool_returns_all_bounded_current_zones(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "vision.get_zone_status",
                {},
            )["result"]

            self.assertEqual(result["zone_count"], 2)
            self.assertEqual(result["occupied_zone_count"], 1)
            self.assertEqual(result["unique_current_count"], 1)
            self.assertEqual(result["unique_track_ids"], [7])
            self.assertEqual(
                [zone["zone_id"] for zone in result["zones"]],
                ["left_zone", "right_zone"],
            )

    def test_zone_tool_filters_exact_zone_and_rejects_unknown(self):
        with tempfile.TemporaryDirectory() as directory:
            state_path = os.path.join(directory, "current.json")
            CurrentVisionStateStore(state_path).write(make_state())
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
                state_path=state_path,
            )

            result = registry.invoke(
                "vision.get_zone_status",
                {"zone_id": "right_zone"},
            )["result"]

            self.assertEqual(result["selected_zone_id"], "right_zone")
            self.assertEqual(result["zone_count"], 1)
            self.assertEqual(result["zones"][0]["current_count"], 0)
            with self.assertRaises(ToolInvocationError):
                registry.invoke(
                    "vision.get_zone_status",
                    {"zone_id": "missing_zone"},
                )


if __name__ == "__main__":
    unittest.main()
