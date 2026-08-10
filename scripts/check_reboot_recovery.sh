#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
UNIT_NAME="edgesentinel-visionops.service"
CONTAINER_NAME="edgesentinel-visionops"
RESULT_FILE="$(mktemp)"

cleanup() {
  if [ -f "$RESULT_FILE" ]; then
    rm -f -- "$RESULT_FILE"
  fi
}

trap cleanup EXIT

if [ -f /.dockerenv ]; then
  echo "ERROR: this check must run on the Jetson host, not inside Docker." >&2
  exit 1
fi

cd "$PROJECT_DIR"
echo "Waiting for the post-reboot EdgeSentinel runtime..."
sudo -v

attempt=0
while [ "$attempt" -lt 60 ]; do
  active="$(sudo systemctl is-active "$UNIT_NAME" 2>/dev/null || true)"
  if [ "$active" = "active" ]; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 2
done

active="$(sudo systemctl is-active "$UNIT_NAME" 2>/dev/null || true)"
if [ "$active" != "active" ]; then
  echo "ERROR: systemd runtime did not become active: $active" >&2
  sudo journalctl \
    --boot \
    --unit "$UNIT_NAME" \
    --lines 100 \
    --no-pager >&2
  exit 1
fi

if sudo test -f /etc/edgesentinel-visionops/tls-runtime.env; then
  bash "$SCRIPT_DIR/check_tls_systemd_runtime.sh"
else
  bash "$SCRIPT_DIR/check_systemd_runtime.sh"
fi
sudo docker exec "$CONTAINER_NAME" \
  python3 -m apps.reboot_marker verify > "$RESULT_FILE"

python3 -c \
  "import json,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='verified'; assert x['boot_changed'] is True; assert x['service_restarted'] is True; assert x['tls_recovered'] is True; assert x['tls_certificate_unchanged'] is True; assert x['contains_secret'] is False; print(); print('Reboot Recovery acceptance summary:'); print('Status:',x['status']); print('Boot ID changed:',x['boot_changed']); print('Service restarted:',x['service_restarted']); print('Uptime reset:',x['uptime_reset']); print('Previous boot ID:',x['before']['boot_id']); print('Current boot ID:',x['after']['boot_id']); print('Previous service start:',x['before']['service_started_at']); print('Current service start:',x['after']['service_started_at']); print('Current uptime seconds:',x['after']['uptime_seconds']); print('Current frame ID:',x['after']['vision_frame_id']); print('TLS recovered:',x['tls_recovered']); print('TLS certificate unchanged:',x['tls_certificate_unchanged']); print('TLS public origin:',x['after']['tls_public_origin'] or 'disabled'); print('Persistent credential:',x['contains_secret']); print('Reboot Recovery smoke test passed.')" \
  "$RESULT_FILE"
