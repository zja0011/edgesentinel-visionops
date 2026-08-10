"""Operator CLI for authenticated encrypted recovery exports."""

import argparse
import getpass
import os
import sys

from packages.harness.recovery_export import (
    EncryptedRecoveryExport,
    RecoveryExportError,
)
from packages.harness.utf8 import print_json_utf8


def build_parser():
    parser = argparse.ArgumentParser(
        description=(
            "Create, verify, or drill an encrypted EdgeSentinel recovery export."
        )
    )
    subparsers = parser.add_subparsers(dest="command")
    create = subparsers.add_parser("create")
    create.add_argument("--project-dir", default=os.getcwd())
    create.add_argument("--backup-id", required=True)
    create.add_argument("--output-dir", required=True)
    create.add_argument("--key-file", required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("--artifact", required=True)
    verify.add_argument("--metadata", required=True)
    verify.add_argument("--key-file")
    drill = subparsers.add_parser("drill")
    drill.add_argument("--artifact", required=True)
    drill.add_argument("--metadata", required=True)
    drill.add_argument("--key-file")
    return parser


def read_secret(key_file=None):
    if key_file:
        path = os.path.abspath(key_file)
        if not os.path.isfile(path) or os.path.islink(path):
            raise RuntimeError("recovery export key file is unavailable")
        with open(path, "rb") as input_file:
            return input_file.readline().rstrip(b"\r\n")
    return getpass.getpass("Recovery export passphrase: ").encode("utf-8")


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.command:
        raise SystemExit("a recovery export command is required")
    service = EncryptedRecoveryExport()
    secret = read_secret(getattr(args, "key_file", None))
    if args.command == "create":
        result = service.create(
            args.project_dir,
            args.backup_id,
            args.output_dir,
            secret,
        )
    elif args.command == "verify":
        result = service.verify(args.artifact, args.metadata, secret)
    else:
        result = service.drill(args.artifact, args.metadata, secret)
    print_json_utf8(result)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except RecoveryExportError as error:
        sys.stderr.write("Recovery export failed: {0}\n".format(error))
        sys.exit(1)
