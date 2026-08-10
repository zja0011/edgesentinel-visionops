#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
UNIT_NAME="edgesentinel-visionops.service"

if [ -f /.dockerenv ]; then
  echo "ERROR: this command must run on the Jetson host, not inside Docker." >&2
  exit 1
fi

cd "$PROJECT_DIR"
sudo -v

if [ "$(sudo systemctl is-enabled "$UNIT_NAME")" != "enabled" ]; then
  echo "ERROR: $UNIT_NAME is not enabled." >&2
  exit 1
fi
if [ "$(sudo systemctl is-active "$UNIT_NAME" 2>/dev/null || true)" = "active" ]; then
  echo "ERROR: $UNIT_NAME is already active." >&2
  echo "Run scripts/check_systemd_runtime.sh instead." >&2
  exit 1
fi

echo "Stopping the current manually-started runtime..."
bash "$SCRIPT_DIR/host_edgesentinel.sh" stop

echo "Starting the credential-free systemd runtime..."
sudo systemctl reset-failed "$UNIT_NAME" 2>/dev/null || true
if ! sudo systemctl start "$UNIT_NAME"; then
  echo
  echo "ERROR: systemd start failed. Recent unit log:" >&2
  sudo journalctl \
    --unit "$UNIT_NAME" \
    --lines 80 \
    --no-pager >&2
  exit 1
fi

bash "$SCRIPT_DIR/check_systemd_runtime.sh"
