import io
import json
import os
import tempfile
import unittest

from packages.harness.default_tools import build_default_registry
from packages.harness.utf8 import write_json_atomic
from packages.mcp.server import EdgeSentinelMcpServer, StdioTransport


def camera_state():
    return {
        "schema_version": "1.0",
        "status": "RUNNING",
        "device": "/dev/video0",
        "device_available": True,
        "worker_running": True,
        "worker_pid": 55,
        "generation": 3,
        "restart_count": 1,
        "last_exit_code": 0,
        "started_at": "start",
        "updated_at": "update",
        "vision": {
            "available": True,
            "age_seconds": 0.1,
            "frame_id": 88,
            "timestamp": "frame",
        },
    }


class McpServerTests(unittest.TestCase):
    def build_server(self, directory):
        runtime = os.path.join(directory, "data", "runtime")
        os.makedirs(runtime)
        state_path = os.path.join(
            runtime,
            "vision-supervisor.json",
        )
        write_json_atomic(state_path, camera_state())
        registry = build_default_registry(
            directory,
            os.path.join(directory, "missing.db"),
            audit_path=os.path.join(directory, "mcp-audit.jsonl"),
            camera_state_path=state_path,
        )
        return EdgeSentinelMcpServer(registry)

    @staticmethod
    def initialize(server, protocol="2025-11-25"):
        initialized = server.handle_message(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": protocol,
                    "capabilities": {},
                    "clientInfo": {
                        "name": "unit-test",
                        "version": "1.0",
                    },
                },
            }
        )
        server.handle_message(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )
        return initialized

    def test_lifecycle_lists_only_l0_read_only_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            server = self.build_server(directory)
            initialized = self.initialize(server)
            response = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {},
                }
            )

            self.assertEqual(
                initialized["result"]["protocolVersion"],
                "2025-11-25",
            )
            self.assertEqual(
                initialized["result"]["serverInfo"]["name"],
                "edgesentinel-visionops",
            )
            tools = response["result"]["tools"]
            names = [tool["name"] for tool in tools]
            self.assertEqual(len(names), 25)
            self.assertIn("memory.search", names)
            self.assertIn("event.summarize", names)
            self.assertIn("camera.get_status", names)
            self.assertIn("evidence.verify_event", names)
            self.assertIn("evidence.verify_recent", names)
            self.assertIn("vision.get_track_history", names)
            self.assertIn("vision.get_model_info", names)
            self.assertIn("vision.get_performance", names)
            self.assertIn("system.get_runtime_benchmark", names)
            self.assertIn(
                "system.get_retention_cleanup_history",
                names,
            )
            self.assertIn("system.get_storage_usage", names)
            self.assertIn("weather.get_current", names)
            self.assertIn(
                "system.preview_data_retention",
                names,
            )
            self.assertNotIn("camera.capture_snapshot", names)
            self.assertNotIn("camera.restart", names)
            self.assertNotIn("event.acknowledge", names)
            self.assertNotIn("report.generate", names)
            for tool in tools:
                annotations = tool["annotations"]
                self.assertTrue(annotations["readOnlyHint"])
                self.assertFalse(annotations["destructiveHint"])
                self.assertEqual(
                    annotations["openWorldHint"],
                    tool["name"] == "weather.get_current",
                )

    def test_calls_read_only_tool_and_denies_l2_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            server = self.build_server(directory)
            self.initialize(server)
            status = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "camera.get_status",
                        "arguments": {},
                    },
                }
            )
            denied = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "camera.restart",
                        "arguments": {},
                    },
                }
            )

            result = status["result"]
            self.assertFalse(result["isError"])
            self.assertEqual(
                result["structuredContent"]["generation"],
                3,
            )
            self.assertEqual(
                json.loads(result["content"][0]["text"])[
                    "vision"
                ]["frame_id"],
                88,
            )
            self.assertTrue(denied["result"]["isError"])
            self.assertEqual(
                denied["result"]["structuredContent"]["error"][
                    "code"
                ],
                "POLICY_DENIED",
            )
            self.assertFalse(
                os.path.exists(
                    os.path.join(
                        directory,
                        "data",
                        "runtime",
                        "vision-control.json",
                    )
                )
            )
            with open(
                os.path.join(directory, "mcp-audit.jsonl"),
                "r",
                encoding="utf-8",
            ) as audit_file:
                audit = [json.loads(line) for line in audit_file]
            self.assertEqual(len(audit), 2)
            self.assertEqual(audit[1]["policy"]["risk"], "L2")
            self.assertEqual(
                audit[1]["policy"]["reason"],
                "CONFIRMATION_REQUIRED",
            )

    def test_rejects_requests_before_initialized_and_unknown_tools(self):
        with tempfile.TemporaryDirectory() as directory:
            server = self.build_server(directory)
            early = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/list",
                }
            )
            self.initialize(server, protocol="unsupported")
            unknown = server.handle_message(
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "system.shell",
                        "arguments": {},
                    },
                }
            )

            self.assertEqual(early["error"]["code"], -32002)
            self.assertEqual(unknown["error"]["code"], -32601)

    def test_stdio_uses_newline_delimited_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            server = self.build_server(directory)
            messages = [
                {
                    "jsonrpc": "2.0",
                    "id": "init",
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {
                            "name": "\u9a8c\u6536\u5ba2\u6237\u7aef",
                            "version": "1.0",
                        },
                    },
                },
                {
                    "jsonrpc": "2.0",
                    "method": "notifications/initialized",
                },
                {
                    "jsonrpc": "2.0",
                    "id": "list",
                    "method": "tools/list",
                    "params": {},
                },
            ]
            input_bytes = b"".join(
                (
                    json.dumps(
                        item,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    + "\n"
                ).encode("utf-8")
                for item in messages
            )
            output = io.BytesIO()

            result = StdioTransport(
                server,
                input_stream=io.BytesIO(input_bytes),
                output_stream=output,
            ).run()

            responses = [
                json.loads(line.decode("utf-8"))
                for line in output.getvalue().splitlines()
            ]
            self.assertEqual(result, 0)
            self.assertEqual(len(responses), 2)
            self.assertEqual(responses[0]["id"], "init")
            self.assertEqual(responses[1]["id"], "list")
            self.assertEqual(
                len(responses[1]["result"]["tools"]),
                25,
            )


if __name__ == "__main__":
    unittest.main()
