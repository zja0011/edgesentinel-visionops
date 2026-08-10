"""Exercise the EdgeSentinel MCP stdio server as a real subprocess."""

import argparse
import json
import os
import subprocess
import sys

from packages.harness.utf8 import write_json_atomic


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-dir", default=os.getcwd())
    parser.add_argument(
        "--database",
        default="data/events/edgesentinel.db",
    )
    parser.add_argument(
        "--audit-output",
        required=True,
    )
    parser.add_argument(
        "--result-output",
        required=True,
    )
    return parser


def request_messages():
    return [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {
                    "name": "edgesentinel-acceptance",
                    "version": "1.0.0",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "camera.get_status",
                "arguments": {},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "camera.restart",
                "arguments": {},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {
                "name": "system.shell",
                "arguments": {},
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "resources/list",
            "params": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "resources/read",
            "params": {
                "uri": "edgesentinel://vision/current",
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "resources/read",
            "params": {
                "uri": "edgesentinel://events/recent",
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "prompts/list",
            "params": {},
        },
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "prompts/get",
            "params": {
                "name": "inventory_check",
                "arguments": {
                    "object_class": "bottle",
                    "expected_count": "2",
                },
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "resources/read",
            "params": {
                "uri": "file:///etc/passwd",
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "resources/read",
            "params": {
                "uri": "edgesentinel://vision/model",
            },
        },
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {
                "name": "system.get_runtime_benchmark",
                "arguments": {},
            },
        },
    ]


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
    input_data = "".join(
        json.dumps(
            message,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
        for message in request_messages()
    ).encode("utf-8")
    process = subprocess.Popen(
        command,
        cwd=project_dir,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate(
        input=input_data,
        timeout=30,
    )
    if process.returncode != 0:
        raise SystemExit(
            "MCP server exited with code {0}: {1}".format(
                process.returncode,
                stderr.decode("utf-8", "replace"),
            )
        )
    if stderr:
        raise SystemExit(
            "MCP server wrote unexpected stderr: {0}".format(
                stderr.decode("utf-8", "replace")
            )
        )
    responses = [
        json.loads(line.decode("utf-8"))
        for line in stdout.splitlines()
        if line.strip()
    ]
    by_id = {
        response.get("id"): response
        for response in responses
    }
    if len(responses) != 13:
        raise SystemExit("unexpected MCP response count")
    initialized = by_id[1]["result"]
    tools = by_id[2]["result"]["tools"]
    names = [tool["name"] for tool in tools]
    camera = by_id[3]["result"]
    denied = by_id[4]["result"]
    unknown = by_id[5]["error"]
    resources = by_id[6]["result"]["resources"]
    resource_uris = [
        resource["uri"] for resource in resources
    ]
    vision_resource = json.loads(
        by_id[7]["result"]["contents"][0]["text"]
    )
    events_resource = json.loads(
        by_id[8]["result"]["contents"][0]["text"]
    )
    prompts = by_id[9]["result"]["prompts"]
    prompt_names = [prompt["name"] for prompt in prompts]
    inventory_prompt = by_id[10]["result"]
    invalid_resource = by_id[11]["error"]
    model_resource = json.loads(
        by_id[12]["result"]["contents"][0]["text"]
    )
    benchmark = (
        by_id[13]["result"].get("structuredContent") or {}
    )
    if (
        initialized.get("protocolVersion") != "2025-11-25"
        or len(names) != 25
        or "camera.get_status" not in names
        or "evidence.verify_event" not in names
        or "evidence.verify_recent" not in names
        or "event.summarize" not in names
        or "system.get_runtime_benchmark" not in names
        or "system.get_retention_cleanup_history" not in names
        or "system.get_storage_usage" not in names
        or "system.preview_data_retention" not in names
        or "weather.get_current" not in names
        or "camera.restart" in names
        or "camera.capture_snapshot" in names
        or "event.acknowledge" in names
        or "report.generate" in names
    ):
        raise SystemExit("MCP tool discovery contract failed")
    capabilities = initialized.get("capabilities") or {}
    if (
        "resources" not in capabilities
        or "prompts" not in capabilities
        or len(resource_uris) != 5
        or "edgesentinel://vision/current" not in resource_uris
        or "edgesentinel://events/recent" not in resource_uris
        or "edgesentinel://vision/model" not in resource_uris
        or len(prompt_names) != 3
        or "inventory_check" not in prompt_names
    ):
        raise SystemExit("MCP catalog discovery contract failed")
    camera_state = camera.get("structuredContent") or {}
    if (
        camera.get("isError")
        or camera_state.get("status") != "RUNNING"
        or not camera_state.get("device_available")
        or not camera_state.get("worker_running")
        or camera_state.get("state_stale")
        or not (camera_state.get("vision") or {}).get("available")
    ):
        raise SystemExit("MCP camera status call failed")
    denial = (denied.get("structuredContent") or {}).get(
        "error"
    ) or {}
    if (
        not denied.get("isError")
        or denial.get("code") != "POLICY_DENIED"
        or unknown.get("code") != -32601
    ):
        raise SystemExit("MCP fail-closed policy check failed")
    prompt_messages = inventory_prompt.get("messages") or []
    prompt_text = (
        (prompt_messages[0].get("content") or {}).get("text")
        if prompt_messages
        else ""
    )
    if (
        vision_resource.get("resource")
        != "edgesentinel://vision/current"
        or vision_resource.get("stale")
        or vision_resource.get("raw_detections_included")
        or "detections" in vision_resource
        or events_resource.get("count", 0) > 10
        or events_resource.get("evidence_paths_included")
        or events_resource.get("event_details_included")
        or len(prompt_messages) != 1
        or "inventory.compare_state" not in prompt_text
        or "bottle" not in prompt_text
        or invalid_resource.get("code") != -32002
        or model_resource.get("network") != "ssd-mobilenet-v2"
        or (model_resource.get("verification") or {}).get(
            "status"
        )
        != "MATCH"
        or model_resource.get("absolute_paths_included")
        or float(
            (
                vision_resource.get("performance") or {}
            ).get("processing_fps")
            or 0
        )
        <= 0
        or benchmark.get("status") != "PASS"
        or benchmark.get("samples_included")
        or benchmark.get("contains_secret")
        or benchmark.get("absolute_paths_included")
    ):
        raise SystemExit("MCP bounded catalog check failed")
    result = {
        "schema_version": "1.0",
        "protocol_version": initialized["protocolVersion"],
        "server_name": initialized["serverInfo"]["name"],
        "transport": "stdio",
        "response_count": len(responses),
        "tool_count": len(names),
        "tools": names,
        "resource_count": len(resource_uris),
        "resources": resource_uris,
        "vision_resource": {
            "frame_id": vision_resource.get("frame_id"),
            "stale": vision_resource.get("stale"),
            "people": vision_resource.get("people"),
            "object_class_count": len(
                vision_resource.get("objects") or []
            ),
            "zone_count": len(
                vision_resource.get("zones") or []
            ),
            "performance": vision_resource.get("performance"),
        },
        "recent_event_resource_count": (
            events_resource.get("count")
        ),
        "model_resource": {
            "manifest_id": model_resource.get("manifest_id"),
            "network": model_resource.get("network"),
            "precision": (
                model_resource.get("artifact") or {}
            ).get("precision"),
            "integrity": (
                model_resource.get("verification") or {}
            ).get("status"),
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
            "sha256": benchmark.get("report_sha256"),
        },
        "prompt_count": len(prompt_names),
        "prompts": prompt_names,
        "rendered_prompt": {
            "name": "inventory_check",
            "message_count": len(prompt_messages),
            "contains_expected_tool": (
                "inventory.compare_state" in prompt_text
            ),
        },
        "invalid_resource_error": (
            invalid_resource.get("code")
        ),
        "camera_status": {
            "status": camera_state.get("status"),
            "generation": camera_state.get("generation"),
            "restart_count": camera_state.get(
                "restart_count"
            ),
            "vision_frame_id": (
                camera_state.get("vision") or {}
            ).get("frame_id"),
            "state_stale": camera_state.get("state_stale"),
        },
        "gated_tool": {
            "name": "camera.restart",
            "is_error": denied.get("isError"),
            "code": denial.get("code"),
            "message": denial.get("message"),
        },
        "unknown_tool_error": unknown.get("code"),
        "stderr_empty": not bool(stderr),
    }
    write_json_atomic(args.result_output, result)
    print("")
    print("MCP Server acceptance summary:")
    print("Protocol: {0}".format(result["protocol_version"]))
    print("Transport: {0}".format(result["transport"]))
    print("Server: {0}".format(result["server_name"]))
    print("Read-only tools: {0}".format(result["tool_count"]))
    print(
        "Bounded resources: {0}".format(
            result["resource_count"]
        )
    )
    print(
        "User-controlled prompts: {0}".format(
            result["prompt_count"]
        )
    )
    print("Camera tool: camera.get_status SUCCEEDED")
    print(
        "Camera generation: {0}".format(
            result["camera_status"]["generation"]
        )
    )
    print(
        "Vision frame: {0}".format(
            result["camera_status"]["vision_frame_id"]
        )
    )
    print("Camera state stale: False")
    print(
        "Runtime benchmark: {0} samples={1}".format(
            result["runtime_benchmark"]["status"],
            result["runtime_benchmark"]["sample_count"],
        )
    )
    print("Gated tool: camera.restart POLICY_DENIED")
    print("Unknown tool: system.shell JSON-RPC -32601")
    print(
        "Vision resource: frame={0} stale=False".format(
            result["vision_resource"]["frame_id"]
        )
    )
    print(
        "Vision performance: {0} FPS".format(
            (
                result["vision_resource"].get("performance")
                or {}
            ).get("processing_fps")
        )
    )
    print(
        "Recent event resource: {0} bounded records".format(
            result["recent_event_resource_count"]
        )
    )
    print(
        "Prompt: inventory_check VALIDATED"
    )
    print(
        "Model resource: {0} {1} integrity={2}".format(
            result["model_resource"]["network"],
            result["model_resource"]["precision"],
            result["model_resource"]["integrity"],
        )
    )
    print(
        "Arbitrary file URI: JSON-RPC -32002"
    )
    print("Stderr empty: True")
    print("Result file: {0}".format(args.result_output))
    print("Audit log: {0}".format(args.audit_output))
    print("MCP Server smoke test passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
