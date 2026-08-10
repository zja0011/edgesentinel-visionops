"""Command-line interface for the lightweight Agent Harness tool runtime."""

import argparse
import json
import os
import sys

from packages.harness.default_tools import build_default_registry
from packages.harness.registry import ToolInvocationError


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="List and invoke allowlisted EdgeSentinel tools."
    )
    parser.add_argument(
        "--database",
        default=os.path.join(
            PROJECT_DIR,
            "data",
            "events",
            "edgesentinel.db",
        ),
    )
    parser.add_argument(
        "--audit-output",
        default=os.path.join(
            PROJECT_DIR,
            "data",
            "harness",
            "tool-calls.jsonl",
        ),
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser(
        "list-tools",
        help="print registered tool schemas",
    )
    invoke_parser = subparsers.add_parser(
        "invoke",
        help="invoke one allowlisted tool",
    )
    invoke_parser.add_argument("tool_name")
    invoke_parser.add_argument(
        "--arguments",
        default="{}",
        help="tool arguments as one JSON object",
    )
    invoke_parser.add_argument(
        "--confirm",
        action="store_true",
        help="explicitly confirm this one tool invocation",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if not args.command:
        parser.error("a command is required")

    registry = build_default_registry(
        PROJECT_DIR,
        args.database,
        args.audit_output,
    )
    if args.command == "list-tools":
        payload = {"tools": registry.schemas()}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    try:
        arguments = json.loads(args.arguments)
    except ValueError:
        parser.error("--arguments must be valid JSON")

    try:
        result = registry.invoke(
            args.tool_name,
            arguments,
            confirmation_granted=args.confirm,
        )
    except ToolInvocationError as error:
        print(
            json.dumps(
                error.to_dict(),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
