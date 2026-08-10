"""Run the local EdgeSentinel MCP server over stdio."""

import argparse
import os
import sys

from packages.harness.default_tools import build_default_registry
from packages.harness.audit import JsonlToolAuditRecorder
from packages.mcp.prompts import EdgeSentinelPrompts
from packages.mcp.resources import EdgeSentinelResources
from packages.mcp.server import EdgeSentinelMcpServer, StdioTransport


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Expose EdgeSentinel L0 read-only tools over MCP stdio."
        )
    )
    parser.add_argument(
        "--project-dir",
        default=os.getcwd(),
    )
    parser.add_argument(
        "--database",
        default="data/events/edgesentinel.db",
    )
    parser.add_argument(
        "--audit-output",
        default="data/harness/mcp-tool-calls.jsonl",
    )
    return parser


def resolve_path(project_dir, path):
    if os.path.isabs(path):
        return os.path.abspath(path)
    return os.path.abspath(os.path.join(project_dir, path))


def main():
    args = build_parser().parse_args()
    project_dir = os.path.abspath(args.project_dir)
    database_path = resolve_path(project_dir, args.database)
    audit_path = resolve_path(
        project_dir,
        args.audit_output,
    )
    registry = build_default_registry(
        project_dir,
        database_path,
        audit_path=audit_path,
    )
    catalog_audit = JsonlToolAuditRecorder(audit_path)
    resources = EdgeSentinelResources(
        project_dir,
        database_path,
        audit_recorder=catalog_audit,
    )
    prompts = EdgeSentinelPrompts(
        audit_recorder=catalog_audit,
    )
    server = EdgeSentinelMcpServer(
        registry,
        resource_provider=resources,
        prompt_provider=prompts,
    )
    return StdioTransport(server).run()


if __name__ == "__main__":
    sys.exit(main())
