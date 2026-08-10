#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
FRAME_LOG="$PROJECT_DIR/data/logs/live-state-frames-$RUN_ID.jsonl"
STATE_FILE="$PROJECT_DIR/data/state/current-vision.json"
AUDIT_LOG="$PROJECT_DIR/data/harness/live-tool-calls-$RUN_ID.jsonl"

mkdir -p \
  "$PROJECT_DIR/data/logs" \
  "$PROJECT_DIR/data/state" \
  "$PROJECT_DIR/data/harness"
# Do not let a failed camera start accidentally reuse a previous run's state.
rm -f "$STATE_FILE"
cd "$PROJECT_DIR"

echo "Live Harness state test"
echo "State file: $STATE_FILE"
echo "Frame log: $FRAME_LOG"
echo "Audit log: $AUDIT_LOG"
echo "Keep one person and one supported object visible for at least 5 seconds."
echo "Supported objects: backpack, bottle, cup, laptop, cell phone, book, mouse"
echo "Press Ctrl+C while they are still visible."

python3 -m apps.vision_probe \
  --input /dev/video0 \
  --output display://0 \
  --network ssd-mobilenet-v2 \
  --threshold 0.5 \
  --width 640 \
  --height 480 \
  --json-every 30 \
  --json-output "$FRAME_LOG" \
  --state-output "$STATE_FILE" \
  --state-every 5 \
  --tracker-iou 0.3 \
  --tracker-max-missed 10 \
  --people-min-hits 3 \
  --people-grace-frames 10 \
  --zones "" \
  --event-output "" \
  --event-db "" \
  --evidence-dir "" \
  --inventory-classes \
    "backpack,bottle,cup,laptop,cell phone,book,mouse" \
  --inventory-min-hits 3 \
  --inventory-appear-confirm 15 \
  --inventory-remove-confirm 30 \
  --left-behind-classes ""

echo
echo "Immediate people tool result:"
python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  invoke vision.get_people_count

echo
echo "Immediate object tool result:"
python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  invoke vision.get_current_objects

echo
echo "Waiting 6 seconds to verify stale-state protection..."
sleep 6

echo
echo "Stale people tool result:"
python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  invoke vision.get_people_count

echo
echo "Audit log: $AUDIT_LOG"
echo "Expected: two immediate results with stale=false, then stale=true."
