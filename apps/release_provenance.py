"""Build or verify EdgeSentinel software release provenance."""

import argparse
import os
import sys

from packages.harness.release_provenance import (
    ReleaseProvenance,
    ReleaseProvenanceError,
)
from packages.harness.utf8 import print_json_utf8


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir)
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Build or verify release provenance and a CycloneDX SBOM."
    )
    subparsers = parser.add_subparsers(dest="command")

    build = subparsers.add_parser("build")
    build.add_argument("--version", default=None)
    build.add_argument(
        "--output-dir",
        default=os.path.join(PROJECT_DIR, "dist", "releases"),
    )

    verify = subparsers.add_parser("verify")
    verify.add_argument("--manifest", required=True)
    return parser


def main():
    args = build_parser().parse_args()
    if args.command not in ("build", "verify"):
        raise SystemExit("a command is required")
    service = ReleaseProvenance(PROJECT_DIR)
    try:
        if args.command == "build":
            result = service.write(args.output_dir, args.version)
        else:
            result = service.verify(args.manifest)
    except ReleaseProvenanceError as error:
        print_json_utf8({
            "schema_version": "1.0",
            "status": "FAILED",
            "error": str(error),
            "credentials_included": False,
            "absolute_paths_included": False,
        })
        return 1
    print_json_utf8(result)
    return 0 if result.get("status") != "FAIL" else 1


if __name__ == "__main__":
    sys.exit(main())
