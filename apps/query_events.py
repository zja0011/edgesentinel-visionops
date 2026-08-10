"""Query recent EdgeSentinel events from SQLite."""

import argparse
import json
import sys

from packages.events.sqlite_store import SqliteEventStore


def build_parser():
    parser = argparse.ArgumentParser(
        description="Query structured events from the local SQLite database."
    )
    parser.add_argument(
        "--database",
        default="data/events/edgesentinel.db",
        help="SQLite event database path",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--type", dest="event_type", default="")
    parser.add_argument("--object-class", default="")
    parser.add_argument("--camera-id", default="")
    parser.add_argument(
        "--status",
        choices=("OPEN", "ACKNOWLEDGED"),
        default="",
    )
    parser.add_argument(
        "--severity",
        choices=("INFO", "MEDIUM", "HIGH", "CRITICAL"),
        default="",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print one complete JSON object per line",
    )
    return parser


def format_event(event):
    details = event["details"]
    count_change = ""
    if (
        "previous_count" in details
        and "current_count" in details
    ):
        count_change = " {0}->{1}".format(
            details["previous_count"],
            details["current_count"],
        )
    track = (
        "aggregate"
        if event["track_id"] is None
        else str(event["track_id"])
    )
    return "{0} {1} {2}{3} zone={4} track={5}".format(
        event["timestamp"],
        event["event_type"],
        event["object_class"],
        count_change,
        event["zone_id"],
        track,
    )


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.limit <= 0:
        parser.error("--limit must be positive")

    store = SqliteEventStore(args.database)
    try:
        events = store.query(
            limit=args.limit,
            event_type=args.event_type or None,
            object_class=args.object_class or None,
            camera_id=args.camera_id or None,
            status=args.status or None,
            severity=args.severity or None,
        )
    finally:
        store.close()

    for event in events:
        if args.json:
            print(
                json.dumps(
                    event,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
        else:
            print(format_event(event))
    return 0


if __name__ == "__main__":
    sys.exit(main())
