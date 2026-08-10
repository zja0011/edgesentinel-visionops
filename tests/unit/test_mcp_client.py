import os
import sys
import tempfile
import unittest

from packages.harness.utf8 import write_json_atomic
from packages.mcp.client import McpClientError, McpStdioClient
from packages.mcp.host import EdgeSentinelMcpHost
from packages.vision.state_store import CurrentVisionStateStore


def vision_state():
    return {
        "schema_version": "1.6",
        "frame_id": 91,
        "timestamp": "2026-07-28T13:00:00.000+08:00",
        "camera_id": "camera_01",
        "detections": [],
        "analytics": {
            "people": {
                "current_people": 0,
                "visible_people": 0,
            },
            "inventory": {
                "current_counts": {"bottle": 0},
            },
            "zones": [
                {
                    "zone_id": "left_zone",
                    "name": "Left Zone",
                    "current_count": 0,
                }
            ],
            "performance": {
                "status": "MEETS_TARGET",
                "sample_count": 91,
                "processing_fps": 10.0,
                "pipeline_latency_ms": {
                    "average": 45.0,
                    "p95": 60.0,
                },
                "targets": {
                    "minimum_fps": 5.0,
                    "maximum_p95_ms": 200.0,
                    "all_met": True,
                },
            },
        },
    }


def supervisor_state():
    return {
        "schema_version": "1.0",
        "status": "RUNNING",
        "device": "/dev/video0",
        "device_available": True,
        "worker_running": True,
        "generation": 4,
        "restart_count": 2,
        "vision": {
            "available": True,
            "age_seconds": 0.1,
            "frame_id": 91,
            "timestamp": "2026-07-28T13:00:00.000+08:00",
        },
    }


class UnsafeDiscoveryClient(object):
    def list_tools(self):
        return [
            {
                "name": "system.shell",
                "annotations": {
                    "readOnlyHint": False,
                    "destructiveHint": True,
                    "idempotentHint": False,
                    "openWorldHint": True,
                },
            }
        ]

    def list_resources(self):
        return []

    def list_prompts(self):
        return []


class WeatherDiscoveryClient(object):
    def list_tools(self):
        return [
            {
                "name": "weather.get_current",
                "annotations": {
                    "readOnlyHint": True,
                    "destructiveHint": False,
                    "idempotentHint": True,
                    "openWorldHint": True,
                },
            }
        ]

    def list_resources(self):
        return []

    def list_prompts(self):
        return []

    def call_tool(self, name, arguments):
        return {
            "isError": False,
            "structuredContent": {
                "provider": "open-meteo",
                "location": arguments.get("location"),
                "read_only": True,
            },
        }


class McpClientTests(unittest.TestCase):
    def test_host_allows_only_the_fixed_open_world_weather_tool(self):
        client = WeatherDiscoveryClient()
        host = EdgeSentinelMcpHost(client)

        discovery = host.discover()
        result = host.call_tool(
            "weather.get_current",
            {"location": "Shenzhen"},
        )

        self.assertEqual(discovery["tool_count"], 1)
        self.assertEqual(result["provider"], "open-meteo")
        self.assertTrue(result["read_only"])

        denied_host = EdgeSentinelMcpHost(
            client,
            allowed_open_world_tools=(),
        )
        denied_host.discover()
        with self.assertRaises(McpClientError) as denied:
            denied_host.call_tool(
                "weather.get_current",
                {"location": "Shenzhen"},
            )
        self.assertEqual(
            denied.exception.code,
            "HOST_POLICY_DENIED",
        )

    def build_client(self, directory):
        state_path = os.path.join(
            directory,
            "data",
            "state",
            "current-vision.json",
        )
        CurrentVisionStateStore(state_path).write(vision_state())
        supervisor_path = os.path.join(
            directory,
            "data",
            "runtime",
            "vision-supervisor.json",
        )
        write_json_atomic(supervisor_path, supervisor_state())
        audit_path = os.path.join(directory, "host-audit.jsonl")
        command = [
            sys.executable,
            "-m",
            "apps.mcp_server",
            "--project-dir",
            directory,
            "--database",
            os.path.join(directory, "missing.db"),
            "--audit-output",
            audit_path,
        ]
        return McpStdioClient(
            command,
            cwd=os.getcwd(),
            timeout_seconds=5.0,
            client_name="unit-host",
        )

    def test_real_client_and_host_complete_the_stdio_lifecycle(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.build_client(directory)
            with client:
                host = EdgeSentinelMcpHost(client)
                discovery = host.discover()
                camera = host.call_tool("camera.get_status")
                vision = host.read_resource(
                    "edgesentinel://vision/current"
                )
                prompt = host.get_prompt(
                    "current_scene_summary"
                )
                ping = client.ping()

            self.assertEqual(client.protocol_version, "2025-11-25")
            self.assertEqual(discovery["tool_count"], 25)
            self.assertEqual(discovery["resource_count"], 5)
            self.assertEqual(discovery["prompt_count"], 3)
            self.assertEqual(camera["generation"], 4)
            self.assertEqual(vision["frame_id"], 91)
            self.assertEqual(
                prompt["messages"][0]["role"],
                "user",
            )
            self.assertEqual(ping, {})
            self.assertEqual(client.stderr_text, "")

    def test_host_denies_items_outside_discovery(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.build_client(directory)
            with client:
                host = EdgeSentinelMcpHost(client)
                host.discover()
                with self.assertRaises(McpClientError) as tool_error:
                    host.call_tool("camera.restart")
                with self.assertRaises(
                    McpClientError
                ) as resource_error:
                    host.read_resource("file:///etc/passwd")

            self.assertEqual(
                tool_error.exception.code,
                "HOST_POLICY_DENIED",
            )
            self.assertEqual(
                resource_error.exception.code,
                "HOST_POLICY_DENIED",
            )

    def test_client_preserves_server_jsonrpc_error_codes(self):
        with tempfile.TemporaryDirectory() as directory:
            client = self.build_client(directory)
            with client:
                with self.assertRaises(McpClientError) as error:
                    client.read_resource("file:///etc/passwd")

            self.assertEqual(error.exception.code, -32002)
            self.assertNotIn("Traceback", error.exception.message)

    def test_host_rejects_unsafe_discovery_schema(self):
        host = EdgeSentinelMcpHost(UnsafeDiscoveryClient())

        with self.assertRaises(McpClientError) as error:
            host.discover()

        self.assertEqual(
            error.exception.code,
            "UNSAFE_DISCOVERY",
        )


if __name__ == "__main__":
    unittest.main()
