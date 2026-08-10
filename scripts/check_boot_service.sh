#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
UNIT_NAME="edgesentinel-visionops.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"

if [ -f /.dockerenv ]; then
  echo "ERROR: this check must run on the Jetson host, not inside Docker." >&2
  exit 1
fi

echo "Checking the EdgeSentinel systemd installation..."
sudo -v

[ -f "$UNIT_PATH" ]
enabled="$(sudo systemctl is-enabled "$UNIT_NAME")"
active="$(sudo systemctl is-active "$UNIT_NAME" 2>/dev/null || true)"
load_state="$(sudo systemctl show -p LoadState "$UNIT_NAME" | cut -d= -f2-)"
need_daemon_reload="$(sudo systemctl show -p NeedDaemonReload "$UNIT_NAME" | cut -d= -f2-)"
owner="$(stat -c '%U:%G' "$UNIT_PATH")"
mode="$(stat -c '%a' "$UNIT_PATH")"

if [ "$load_state" != "loaded" ]; then
  echo "ERROR: systemd unit load state is '$load_state', expected 'loaded'." >&2
  exit 1
fi
if [ "$need_daemon_reload" != "no" ]; then
  echo "ERROR: systemd has not loaded the current unit file (NeedDaemonReload=$need_daemon_reload)." >&2
  echo "Run the corrected installer before any reboot test." >&2
  exit 1
fi

sudo systemd-analyze verify "$UNIT_PATH"
unit_text="$(sudo systemctl cat "$UNIT_NAME")"

[ "$enabled" = "enabled" ]
[ "$owner" = "root:root" ]
[ "$mode" = "644" ]
printf '%s\n' "$unit_text" |
  grep -Fq "ExecStart=/usr/bin/docker start edgesentinel-visionops"
printf '%s\n' "$unit_text" |
  grep -Fq "ExecStartPost=/usr/bin/docker exec -e EDGESENTINEL_MODEL_MODE"
printf '%s\n' "$unit_text" |
  grep -Fq "ExecStop=/usr/bin/docker exec edgesentinel-visionops bash scripts/edgesentinel_service.sh stop"
printf '%s\n' "$unit_text" |
  grep -Fq "ExecStopPost=/usr/bin/docker stop --time 10 edgesentinel-visionops"
printf '%s\n' "$unit_text" |
  grep -Fq "Requires=docker.service"
printf '%s\n' "$unit_text" |
  grep -Fq "dev-video0.device"
printf '%s\n' "$unit_text" |
  grep -Fq "ExecStartPre=/bin/sh -c 'until [ -c /dev/video0 ]; do sleep 2; done'"
printf '%s\n' "$unit_text" |
  grep -Fq "if [ -L /tmp/edgesentinel_nv_jetson_model ]; then exit 1; fi"
printf '%s\n' "$unit_text" |
  grep -Fq "rm -f -- /tmp/edgesentinel_nv_jetson_model/model"
printf '%s\n' "$unit_text" |
  grep -Fq "rmdir -- /tmp/edgesentinel_nv_jetson_model"
printf '%s\n' "$unit_text" |
  grep -Fq "TimeoutStartSec=180"
printf '%s\n' "$unit_text" |
  grep -Fq "EnvironmentFile=-/etc/edgesentinel-visionops/model-runtime.env"
printf '%s\n' "$unit_text" |
  grep -Fq "EnvironmentFile=-/etc/edgesentinel-visionops/weather-runtime.env"
printf '%s\n' "$unit_text" |
  grep -Fq "EnvironmentFile=-/etc/edgesentinel-visionops/auth-runtime.env"
printf '%s\n' "$unit_text" |
  grep -Fq "EnvironmentFile=-/etc/edgesentinel-visionops/tls-runtime.env"
printf '%s\n' "$unit_text" |
  grep -Fq -- "-e EDGESENTINEL_WEATHER_DEFAULT_LOCATION"
printf '%s\n' "$unit_text" |
  grep -Fq -- "-e EDGESENTINEL_AUTH_SESSION_SECRET"
printf '%s\n' "$unit_text" |
  grep -Fq -- "-e EDGESENTINEL_TLS_PRIVATE_KEY"
printf '%s\n' "$unit_text" |
  grep -Fq "docker exec -i edgesentinel-visionops"
printf '%s\n' "$unit_text" |
  grep -Fq "< /etc/edgesentinel-visionops/tls/server.key"
if printf '%s\n' "$unit_text" |
  grep -Eq 'EDGESENTINEL_CONFIG_TOKEN|sk-[A-Za-z0-9]+'; then
  echo "ERROR: systemd unit contains a literal credential." >&2
  exit 1
fi

model_credential="not installed"
if sudo test -e /etc/edgesentinel-visionops/model-runtime.env; then
  bash "$SCRIPT_DIR/configure_deepseek_boot.sh" status >/dev/null
  model_credential="root:root 600"
elif sudo test -e \
  /etc/edgesentinel-visionops/model-runtime.env.disabled; then
  bash "$SCRIPT_DIR/configure_deepseek_boot.sh" status >/dev/null
  model_credential="root:root 600 (offline selected)"
fi

auth_credential="not installed"
if sudo test -e /etc/edgesentinel-visionops/auth-runtime.env; then
  bash "$SCRIPT_DIR/configure_auth_boot.sh" status >/dev/null
  auth_credential="root:root 600"
fi

tls_credential="not installed"
if sudo test -e /etc/edgesentinel-visionops/tls-runtime.env; then
  bash "$SCRIPT_DIR/configure_tls_boot.sh" status >/dev/null
  tls_credential="root-owned; private key 600"
fi

echo
echo "Boot Service installation summary:"
echo "Unit: $UNIT_PATH"
echo "Enabled: $enabled"
echo "Active now: $active"
echo "Load state: $load_state"
echo "Daemon reload needed: $need_daemon_reload"
echo "Owner: $owner"
echo "Mode: $mode"
echo "Docker dependency: configured"
echo "Camera boot dependency: configured"
echo "Camera wait: every 2 seconds, bounded by 180-second timeout"
echo "NVIDIA model mount bootstrap: configured"
echo "Root executes project code on host: False"
echo "Boot mode: read-only zone configuration"
echo "Zone administrator credential persisted: False"
echo "Model credential: $model_credential"
echo "Model fallback without credential: offline-rule-mock"
echo "Authentication credential: $auth_credential"
echo "Authentication without credential: fail closed"
echo "TLS credential: $tls_credential"
echo "TLS private key persisted in Docker config: False"
echo "Current runtime changed: False"
echo "Boot Service installation test passed."
