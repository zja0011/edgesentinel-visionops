"""Operator CLI for bounded EdgeSentinel disaster recovery."""

import argparse
import os
import sys

from packages.harness.disaster_recovery import DisasterRecoveryStore
from packages.harness.utf8 import print_json_utf8


def build_parser():
    parser = argparse.ArgumentParser(
        description="Create, verify, preview, or apply local DR backups."
    )
    parser.add_argument("--project-dir", default=os.getcwd())
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("create")
    status = subparsers.add_parser("status")
    status.add_argument("--limit", type=int, default=10)
    preview = subparsers.add_parser("preview")
    preview.add_argument("--backup-id", required=True)
    restore = subparsers.add_parser("restore")
    restore.add_argument("--backup-id", required=True)
    restore.add_argument("--plan-id", required=True)
    restore.add_argument("--confirmation", required=True)
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    if not args.command:
        raise SystemExit("a disaster recovery command is required")
    store = DisasterRecoveryStore(os.path.abspath(args.project_dir))
    if args.command == "create":
        result = store.create_backup()
    elif args.command == "status":
        result = store.get_status({"limit": args.limit})
    elif args.command == "preview":
        result = store.preview_restore(
            {"backup_id": args.backup_id}
        )
    else:
        result = store.apply_restore(
            args.backup_id,
            args.plan_id,
            args.confirmation,
            maintenance_mode=(
                os.environ.get(
                    "EDGESENTINEL_RESTORE_MAINTENANCE",
                    "0",
                )
                == "1"
            ),
        )
    print_json_utf8(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
