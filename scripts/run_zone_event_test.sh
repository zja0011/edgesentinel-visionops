#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"

FRAME_LOG="$PROJECT_DIR/data/logs/zone-frames-$RUN_ID.jsonl"
EVENT_LOG="$PROJECT_DIR/data/events/zone-events-$RUN_ID.jsonl"
EVENT_DB="$PROJECT_DIR/data/events/edgesentinel.db"
EVIDENCE_DIR="$PROJECT_DIR/data/evidence/$RUN_ID"

mkdir -p \
  "$PROJECT_DIR/data/logs" \
  "$PROJECT_DIR/data/events" \
  "$EVIDENCE_DIR"
cd "$PROJECT_DIR"

echo "Frame log: $FRAME_LOG"
echo "Event log: $EVENT_LOG"
echo "Event database: $EVENT_DB"
echo "Evidence directory: $EVIDENCE_DIR"
echo "Press Ctrl+C to stop the test."

python3 -m apps.vision_probe \
  --input /dev/video0 \
  --output display://0 \
  --network ssd-mobilenet-v2 \
  --threshold 0.5 \
  --width 640 \
  --height 480 \
  --json-every 5 \
  --json-output "$FRAME_LOG" \
  --tracker-iou 0.3 \
  --tracker-max-missed 10 \
  --people-min-hits 3 \
  --people-grace-frames 10 \
  --zones configs/zones.json \
  --zone-enter-confirm 15 \
  --zone-exit-confirm 30 \
  --zone-dwell-seconds 5 \
  --event-output "$EVENT_LOG" \
  --event-db "$EVENT_DB" \
  --evidence-dir "$EVIDENCE_DIR" \
  --evidence-quality 90 \
  --inventory-classes "" \
  --left-behind-classes ""

echo "Test stopped."
echo "Frame log: $FRAME_LOG"
echo "Event log: $EVENT_LOG"
echo "Event database: $EVENT_DB"
echo "Evidence directory: $EVIDENCE_DIR"

if [ -s "$EVENT_LOG" ]; then
  echo "Zone events from this run:"
  python3 - "$EVENT_LOG" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as event_file:
    for line in event_file:
        event = json.loads(line)
        print(
            event["timestamp"],
            event["event_type"],
            event["zone_id"],
            "track=",
            event["track_id"],
            "evidence=",
            event.get("evidence_path"),
        )
PY
else
  echo "No zone events were recorded in this run."
fi

echo "Evidence images: $(find "$EVIDENCE_DIR" -maxdepth 1 -type f -name '*.jpg' | wc -l)"

python3 - "$EVENT_DB" "$EVENT_LOG" <<'PY'
import json
import sqlite3
import sys

event_ids = []
if __import__("os").path.isfile(sys.argv[2]):
    with open(sys.argv[2], "r", encoding="utf-8") as event_file:
        event_ids = [json.loads(line)["event_id"] for line in event_file]

if event_ids:
    placeholders = ",".join("?" for unused in event_ids)
    connection = sqlite3.connect(sys.argv[1])
    count = connection.execute(
        "SELECT COUNT(*) FROM events WHERE event_id IN ({0})".format(
            placeholders
        ),
        event_ids,
    ).fetchone()[0]
    connection.close()
else:
    count = 0

print("SQLite events from this run:", count)
print("JSONL events from this run:", len(event_ids))
PY
