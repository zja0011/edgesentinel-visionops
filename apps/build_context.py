"""Build and optionally persist a compact Agent Harness context."""

import argparse
import os
import sys

from packages.harness.context import ContextEngine
from packages.harness.default_tools import build_default_registry
from packages.harness.utf8 import (
    normalize_cli_text,
    print_json_utf8,
    write_json_atomic,
)


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Build a bounded EdgeSentinel Agent context."
    )
    parser.add_argument("--message", required=True)
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
        "--state",
        default=os.path.join(
            PROJECT_DIR,
            "data",
            "state",
            "current-vision.json",
        ),
    )
    parser.add_argument("--max-events", type=int, default=5)
    parser.add_argument("--output", default="")
    return parser


def main():
    args = build_parser().parse_args()
    registry = build_default_registry(
        PROJECT_DIR,
        args.database,
    )
    engine = ContextEngine(
        database_path=args.database,
        state_path=args.state,
        max_events=args.max_events,
    )
    payload = engine.build(
        normalize_cli_text(args.message),
        registry.schemas(),
    )
    if args.output:
        write_json_atomic(args.output, payload)
    print_json_utf8(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
