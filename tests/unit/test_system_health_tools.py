import os
import tempfile
import unittest

from packages.harness.default_tools import build_default_registry
from packages.harness.system_tools import SystemHealthTools


def snapshot(
    load=25.0,
    memory=60.0,
    disk=70.0,
    temperature=50.0,
):
    return {
        "schema_version": "1.0",
        "status": "ok",
        "timestamp": "2026-07-27T14:00:00.000+08:00",
        "load_average": (
            None
            if load is None
            else {
                "one_minute": 1.0,
                "cpu_count": 4,
                "normalized_percent": load,
            }
        ),
        "memory": (
            None
            if memory is None
            else {
                "used_percent": memory,
                "available_bytes": 1000000,
            }
        ),
        "disk": (
            None
            if disk is None
            else {
                "used_percent": disk,
                "available_bytes": 2000000,
            }
        ),
        "temperature": {
            "status": (
                "unavailable"
                if temperature is None
                else "available"
            ),
            "max_celsius": temperature,
            "sensors": [],
        },
        "uptime_seconds": 3600.0,
    }


class FakeMonitor(object):
    def __init__(self, payload):
        self.payload = payload

    def snapshot(self):
        return self.payload


class SystemHealthToolsTests(unittest.TestCase):
    def tool(self, payload):
        return SystemHealthTools(
            ".",
            monitor=FakeMonitor(payload),
        )

    def test_returns_ok_for_healthy_metrics(self):
        result = self.tool(snapshot()).get_health({})

        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["issues"], [])
        self.assertTrue(result["read_only"])
        self.assertEqual(
            result["checks"]["temperature"]["max_celsius"],
            50.0,
        )

    def test_warns_for_high_memory_and_disk_usage(self):
        result = self.tool(
            snapshot(memory=85.0, disk=90.0)
        ).get_health({})

        self.assertEqual(result["status"], "WARNING")
        self.assertEqual(
            result["checks"]["memory"]["status"],
            "WARNING",
        )
        self.assertEqual(
            result["checks"]["disk"]["status"],
            "WARNING",
        )
        self.assertIn("disk:WARNING", result["issues"])

    def test_marks_critical_temperature(self):
        result = self.tool(
            snapshot(temperature=86.0)
        ).get_health({})

        self.assertEqual(result["status"], "CRITICAL")
        self.assertEqual(
            result["checks"]["temperature"]["status"],
            "CRITICAL",
        )

    def test_marks_missing_metrics_as_degraded(self):
        result = self.tool(
            snapshot(load=None, temperature=None)
        ).get_health({})

        self.assertEqual(result["status"], "DEGRADED")
        self.assertEqual(
            result["checks"]["load"]["status"],
            "UNKNOWN",
        )
        self.assertEqual(
            result["checks"]["temperature"]["status"],
            "UNKNOWN",
        )

    def test_default_registry_exposes_auto_executed_l0_tool(self):
        with tempfile.TemporaryDirectory() as directory:
            registry = build_default_registry(
                directory,
                os.path.join(directory, "missing.db"),
            )
            schemas = {
                item["name"]: item
                for item in registry.schemas()
            }
            annotations = schemas["system.get_health"][
                "annotations"
            ]

            self.assertTrue(annotations["readOnlyHint"])
            self.assertEqual(annotations["riskLevel"], "L0")
            self.assertTrue(annotations["autoExecute"])
            self.assertFalse(
                annotations["requiresConfirmation"]
            )


if __name__ == "__main__":
    unittest.main()
