"""Exercise the reusable EdgeSentinel MCP Client and Host."""

import argparse
import os
import sys

from packages.harness.utf8 import write_json_atomic
from packages.mcp.client import McpClientError, McpStdioClient
from packages.mcp.host import EdgeSentinelMcpHost


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=os.getcwd())
    parser.add_argument(
        "--database",
        default="data/events/edgesentinel.db",
    )
    parser.add_argument("--audit-output", required=True)
    parser.add_argument("--result-output", required=True)
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
    )
    return parser


def main():
    args = build_parser().parse_args()
    project_dir = os.path.abspath(args.project_dir)
    command = [
        sys.executable,
        "-m",
        "apps.mcp_server",
        "--project-dir",
        project_dir,
        "--database",
        args.database,
        "--audit-output",
        args.audit_output,
    ]
    client = McpStdioClient(
        command,
        cwd=project_dir,
        timeout_seconds=args.timeout_seconds,
        client_name="edgesentinel-host-acceptance",
    )
    try:
        initialized = client.start()
        host = EdgeSentinelMcpHost(client)
        discovery = host.discover()
        camera = host.call_tool("camera.get_status", {})
        vision = host.read_resource(
            "edgesentinel://vision/current"
        )
        model_info = host.call_tool(
            "vision.get_model_info",
            {},
        )
        performance = host.call_tool(
            "vision.get_performance",
            {},
        )
        benchmark = host.call_tool(
            "system.get_runtime_benchmark",
            {},
        )
        prompt = host.get_prompt(
            "current_scene_summary",
            {},
        )
        ping = client.ping()
        denied_tool = None
        try:
            host.call_tool("camera.restart", {})
        except McpClientError as error:
            denied_tool = error.code
        denied_resource = None
        try:
            host.read_resource("file:///etc/passwd")
        except McpClientError as error:
            denied_resource = error.code
    finally:
        client.close()

    if client.stderr_text:
        raise SystemExit(
            "MCP server wrote unexpected stderr: {0}".format(
                client.stderr_text
            )
        )
    messages = prompt.get("messages") or []
    prompt_text = (
        (messages[0].get("content") or {}).get("text")
        if messages
        else ""
    )
    if (
        initialized.get("protocolVersion") != "2025-11-25"
        or discovery.get("tool_count") != 22
        or discovery.get("resource_count") != 5
        or discovery.get("prompt_count") != 3
        or camera.get("status") != "RUNNING"
        or camera.get("state_stale")
        or not (camera.get("vision") or {}).get("available")
        or vision.get("stale")
        or vision.get("raw_detections_included")
        or model_info.get("network") != "ssd-mobilenet-v2"
        or (model_info.get("verification") or {}).get(
            "status"
        )
        != "MATCH"
        or performance.get("stale")
        or float(performance.get("processing_fps") or 0) <= 0
        or int(performance.get("sample_count") or 0) < 2
        or benchmark.get("status") != "PASS"
        or benchmark.get("samples_included")
        or benchmark.get("contains_secret")
        or benchmark.get("absolute_paths_included")
        or len(messages) != 1
        or "vision.get_people_count" not in prompt_text
        or ping != {}
        or denied_tool != "HOST_POLICY_DENIED"
        or denied_resource != "HOST_POLICY_DENIED"
    ):
        raise SystemExit("MCP Host acceptance contract failed")

    result = {
        "schema_version": "1.0",
        "protocol_version": initialized["protocolVersion"],
        "server_name": initialized["serverInfo"]["name"],
        "transport": "stdio",
        "shell_used": False,
        "discovery": discovery,
        "camera": {
            "status": camera.get("status"),
            "generation": camera.get("generation"),
            "vision_frame_id": (
                camera.get("vision") or {}
            ).get("frame_id"),
            "state_stale": camera.get("state_stale"),
        },
        "vision_resource": {
            "frame_id": vision.get("frame_id"),
            "stale": vision.get("stale"),
            "people": vision.get("people"),
        },
        "model": {
            "manifest_id": model_info.get("manifest_id"),
            "network": model_info.get("network"),
            "precision": (
                model_info.get("artifact") or {}
            ).get("precision"),
            "integrity": (
                model_info.get("verification") or {}
            ).get("status"),
        },
        "performance": {
            "status": performance.get("status"),
            "processing_fps": performance.get(
                "processing_fps"
            ),
            "p95_ms": (
                performance.get("pipeline_latency_ms") or {}
            ).get("p95"),
            "sample_count": performance.get("sample_count"),
        },
        "runtime_benchmark": {
            "status": benchmark.get("status"),
            "sample_count": benchmark.get("sample_count"),
            "minimum_fps": (
                benchmark.get("performance") or {}
            ).get("minimum_fps"),
            "maximum_p95_ms": (
                benchmark.get("performance") or {}
            ).get("maximum_observed_p95_ms"),
        },
        "prompt": {
            "name": "current_scene_summary",
            "message_count": len(messages),
            "validated": True,
        },
        "host_denials": {
            "camera.restart": denied_tool,
            "file:///etc/passwd": denied_resource,
        },
        "ping": "SUCCEEDED",
        "stderr_empty": True,
    }
    write_json_atomic(args.result_output, result)
    print("")
    print("MCP Host acceptance summary:")
    print("Protocol: {0}".format(result["protocol_version"]))
    print("Transport: stdio")
    print("Server: {0}".format(result["server_name"]))
    print("Shell used: False")
    print(
        "Discovery: {0} tools, {1} resources, {2} prompts".format(
            discovery["tool_count"],
            discovery["resource_count"],
            discovery["prompt_count"],
        )
    )
    print("Tool: camera.get_status SUCCEEDED")
    print(
        "Model: {0} {1} integrity={2}".format(
            result["model"]["network"],
            result["model"]["precision"],
            result["model"]["integrity"],
        )
    )
    print(
        "Performance: {0} FPS P95={1} ms status={2}".format(
            result["performance"]["processing_fps"],
            result["performance"]["p95_ms"],
            result["performance"]["status"],
        )
    )
    print(
        "Runtime benchmark: {0} samples={1}".format(
            result["runtime_benchmark"]["status"],
            result["runtime_benchmark"]["sample_count"],
        )
    )
    print(
        "Vision resource: frame={0} stale=False".format(
            result["vision_resource"]["frame_id"]
        )
    )
    print("Prompt: current_scene_summary VALIDATED")
    print("Host denied camera.restart: HOST_POLICY_DENIED")
    print("Host denied file URI: HOST_POLICY_DENIED")
    print("Ping: SUCCEEDED")
    print("Stderr empty: True")
    print("Result file: {0}".format(args.result_output))
    print("Audit log: {0}".format(args.audit_output))
    print("MCP Host smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
