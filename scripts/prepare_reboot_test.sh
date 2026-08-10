#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CONTAINER_NAME="edgesentinel-visionops"

if [ -f /.dockerenv ]; then
  echo "ERROR: this command must run on the Jetson host, not inside Docker." >&2
  exit 1
fi

cd "$PROJECT_DIR"
echo "Running the final pre-reboot health check..."
bash "$SCRIPT_DIR/check_boot_service.sh"
if sudo test -f /etc/edgesentinel-visionops/tls-runtime.env; then
  bash "$SCRIPT_DIR/check_tls_systemd_runtime.sh"
else
  bash "$SCRIPT_DIR/check_systemd_runtime.sh"
fi

echo
echo "Writing the reboot preflight marker..."
sudo docker exec "$CONTAINER_NAME" \
  python3 -m apps.reboot_marker prepare

echo
echo "Reboot preflight passed."
echo "Next command: sudo reboot"
echo "After reconnecting, run:"
echo "  cd $PROJECT_DIR"
echo "  bash scripts/check_reboot_recovery.sh"
