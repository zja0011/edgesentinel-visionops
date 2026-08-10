#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
VENDOR_PYTHON="$PROJECT_DIR/vendor/python"
EVENT_DB="${EDGESENTINEL_EVENT_DB:-$PROJECT_DIR/data/events/edgesentinel.db}"
API_HOST="${EDGESENTINEL_API_HOST:-0.0.0.0}"
API_PORT="${EDGESENTINEL_API_PORT:-8000}"
MODEL_MODE="${EDGESENTINEL_MODEL_MODE:-offline}"
MODEL_PROVIDER="${EDGESENTINEL_MODEL_PROVIDER:-offline}"
CONFIG_TOKEN="${EDGESENTINEL_CONFIG_TOKEN:-}"

if [ ! -d "$VENDOR_PYTHON/fastapi" ]; then
  echo "FastAPI is not installed in $VENDOR_PYTHON" >&2
  echo "Run: bash scripts/install_api_dependencies.sh" >&2
  exit 1
fi

if [ ! -f "$EVENT_DB" ]; then
  echo "WARNING: event database does not exist yet: $EVENT_DB" >&2
  echo "The API will start, but /health will report degraded." >&2
fi

cd "$PROJECT_DIR"

echo "EdgeSentinel local API"
echo "Database: $EVENT_DB"
echo "Listen: $API_HOST:$API_PORT"
echo "Agent model mode: $MODEL_MODE"
echo "Agent model provider: $MODEL_PROVIDER"
if [ "${#CONFIG_TOKEN}" -ge 16 ]; then
  echo "Zone configuration saving: enabled"
else
  echo "Zone configuration saving: disabled"
fi
echo "Health: http://127.0.0.1:$API_PORT/health"
echo "Events: http://127.0.0.1:$API_PORT/api/v1/events"
echo "Dashboard: http://127.0.0.1:$API_PORT/dashboard"
echo "Docs: http://127.0.0.1:$API_PORT/docs"
echo "Press Ctrl+C to stop."

PYTHONPATH="$VENDOR_PYTHON:$PROJECT_DIR${PYTHONPATH:+:$PYTHONPATH}" \
exec python3 -m apps.api_server \
  --host "$API_HOST" \
  --port "$API_PORT" \
  --database "$EVENT_DB"
