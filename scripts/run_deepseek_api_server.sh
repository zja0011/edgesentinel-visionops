#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"

if [ -z "${EDGESENTINEL_MODEL_API_KEY:-}" ]; then
  printf "DeepSeek API Key (input hidden): "
  IFS= read -r -s EDGESENTINEL_MODEL_API_KEY
  printf "\n"
fi

if [ -z "$EDGESENTINEL_MODEL_API_KEY" ]; then
  echo "DeepSeek API Key must not be empty." >&2
  exit 1
fi

export EDGESENTINEL_MODEL_API_KEY
export EDGESENTINEL_MODEL_MODE=remote
export EDGESENTINEL_MODEL_PROVIDER=deepseek
export EDGESENTINEL_MODEL_TIMEOUT_SECONDS="${EDGESENTINEL_MODEL_TIMEOUT_SECONDS:-30}"
export EDGESENTINEL_MODEL_MAX_TOKENS="${EDGESENTINEL_MODEL_MAX_TOKENS:-256}"

echo "Starting the trusted-LAN DeepSeek Agent API."
echo "The API Key stays only in this server process environment."
echo "Only the existing L0 read-only tools are registered."
echo "Do not expose port ${EDGESENTINEL_API_PORT:-8000} to the Internet."

exec bash "$SCRIPT_DIR/run_api_server.sh"
