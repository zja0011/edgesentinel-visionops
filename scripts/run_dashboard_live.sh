#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
FRAME_LOG="$PROJECT_DIR/data/logs/dashboard-live-$RUN_ID.jsonl"
EVENT_LOG="$PROJECT_DIR/data/events/dashboard-live-$RUN_ID.jsonl"
EVENT_DB="$PROJECT_DIR/data/events/edgesentinel.db"
EVIDENCE_DIR="$PROJECT_DIR/data/evidence/dashboard-live-$RUN_ID"
LIVE_FRAME="$PROJECT_DIR/data/state/current-frame.jpg"
SUPERVISOR_STATE="$PROJECT_DIR/data/runtime/vision-supervisor.json"
API_PID=""
TLS_PID=""
CONFIG_READ_ONLY="${EDGESENTINEL_CONFIG_READ_ONLY:-0}"
TLS_ENABLED="${EDGESENTINEL_TLS_ENABLED:-0}"
TLS_PORT="${EDGESENTINEL_TLS_PORT:-8443}"
TLS_CERTIFICATE="${EDGESENTINEL_TLS_CERTIFICATE:-/dev/shm/edgesentinel-tls/server.crt}"
TLS_PRIVATE_KEY="${EDGESENTINEL_TLS_PRIVATE_KEY:-/dev/shm/edgesentinel-tls/server.key}"

cleanup() {
  if [ -n "$TLS_PID" ] && kill -0 "$TLS_PID" 2>/dev/null; then
    kill "$TLS_PID" 2>/dev/null || true
    wait "$TLS_PID" 2>/dev/null || true
  fi
  if [ -n "$API_PID" ] && kill -0 "$API_PID" 2>/dev/null; then
    kill "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
}

trap cleanup EXIT

mkdir -p \
  "$PROJECT_DIR/data/logs" \
  "$PROJECT_DIR/data/events" \
  "$PROJECT_DIR/data/runtime" \
  "$PROJECT_DIR/data/state" \
  "$EVIDENCE_DIR"
cd "$PROJECT_DIR"

if [ -z "${EDGESENTINEL_CONFIG_TOKEN:-}" ]; then
  if [ "$CONFIG_READ_ONLY" = "1" ]; then
    echo "Zone configuration saving: disabled (read-only boot mode)"
  else
    echo "Create a temporary Dashboard configuration token."
    echo "Use at least 16 ASCII characters; input is hidden."
    IFS= read -r -s -p "Zone administrator token: " \
      EDGESENTINEL_CONFIG_TOKEN
    echo ""
    export EDGESENTINEL_CONFIG_TOKEN
  fi
fi
if [ "$CONFIG_READ_ONLY" != "1" ] &&
  [ "${#EDGESENTINEL_CONFIG_TOKEN}" -lt 16 ]; then
  echo "The zone administrator token must contain at least 16 characters." >&2
  exit 1
fi

MODEL_MODE="${EDGESENTINEL_MODEL_MODE:-offline}"
MODEL_PROVIDER="${EDGESENTINEL_MODEL_PROVIDER:-offline}"
echo "Starting the Agent API in the background..."
echo "Agent model mode: $MODEL_MODE"
echo "Agent model provider: $MODEL_PROVIDER"
bash "$SCRIPT_DIR/run_api_server.sh" &
API_PID=$!
sleep 2
if ! kill -0 "$API_PID" 2>/dev/null; then
  echo "The API stopped during startup. Is port 8000 already in use?" >&2
  exit 1
fi

if [ "$TLS_ENABLED" = "1" ]; then
  echo "Starting the TLS reverse proxy..."
  python3 -m apps.tls_proxy \
    --listen-host 0.0.0.0 \
    --listen-port "$TLS_PORT" \
    --upstream-host 127.0.0.1 \
    --upstream-port 8000 \
    --certificate "$TLS_CERTIFICATE" \
    --private-key "$TLS_PRIVATE_KEY" &
  TLS_PID=$!
  sleep 1
  if ! kill -0 "$TLS_PID" 2>/dev/null; then
    echo "The TLS proxy stopped during startup." >&2
    exit 1
  fi
fi

echo "Starting headless camera inference..."
if [ "$TLS_ENABLED" = "1" ]; then
  echo "Dashboard: https://192.168.1.101:${TLS_PORT}/dashboard"
  echo "Direct external HTTP authentication: disabled"
else
  echo "Dashboard: http://192.168.1.101:8000/dashboard"
fi
echo "Latest frame: $LIVE_FRAME"
echo "Frame log: $FRAME_LOG"
echo "Event log: $EVENT_LOG"
echo "Evidence directory: $EVIDENCE_DIR"
echo "Camera supervisor: $SUPERVISOR_STATE"
echo "Press Ctrl+C to stop vision and API together."

python3 -m apps.vision_supervisor \
  --device /dev/video0 \
  --state-output "$SUPERVISOR_STATE" \
  --vision-state data/state/current-vision.json \
  --control-input data/runtime/vision-control.json \
  --retry-seconds 3 \
  --poll-seconds 1 \
  --fresh-seconds 5 \
  --startup-timeout-seconds 120 \
  --event-output "$EVENT_LOG" \
  --event-db "$EVENT_DB" \
  --camera-id camera_01 \
  -- \
  python3 -m apps.vision_probe \
  --input /dev/video0 \
  --output "" \
  --network ssd-mobilenet-v2 \
  --threshold 0.5 \
  --model-engine /jetson-inference/data/networks/SSD-Mobilenet-v2/ssd_mobilenet_v2_coco.uff.1.1.8201.GPU.FP16.engine \
  --model-root /jetson-inference/data/networks \
  --model-manifest-output data/state/current-model.json \
  --width 640 \
  --height 480 \
  --json-every 30 \
  --json-output "$FRAME_LOG" \
  --state-output data/state/current-vision.json \
  --state-every 5 \
  --live-frame-output "$LIVE_FRAME" \
  --live-frame-every 5 \
  --live-frame-quality 80 \
  --tracker-iou 0.3 \
  --tracker-max-missed 10 \
  --people-min-hits 3 \
  --people-grace-frames 10 \
  --zones configs/zones.json \
  --zone-reload-every 30 \
  --zone-enter-confirm 15 \
  --zone-exit-confirm 30 \
  --zone-dwell-seconds 20 \
  --event-output "$EVENT_LOG" \
  --event-db "$EVENT_DB" \
  --evidence-dir "$EVIDENCE_DIR" \
  --evidence-quality 90 \
  --evidence-checkpoint-every 15 \
  --inventory-classes \
    "backpack,handbag,suitcase,bottle,cup,laptop,cell phone,book,mouse" \
  --inventory-min-hits 3 \
  --inventory-appear-confirm 15 \
  --inventory-remove-confirm 30 \
  --left-behind-classes "backpack,handbag,suitcase,bottle" \
  --left-behind-confirm 200 \
  --left-behind-rearm-people 15

echo "Dashboard live run stopped."
echo "Frame log: $FRAME_LOG"
echo "Event log: $EVENT_LOG"
echo "Evidence directory: $EVIDENCE_DIR"
