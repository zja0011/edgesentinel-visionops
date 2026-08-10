#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
TEMPLATE="$PROJECT_DIR/deploy/edgesentinel-visionops.service.template"
UNIT_NAME="edgesentinel-visionops.service"
UNIT_PATH="/etc/systemd/system/$UNIT_NAME"
CONTAINER_NAME="edgesentinel-visionops"
MANAGED_LABEL="com.edgesentinel.managed"
TEMPORARY_DIR=""
TEMPORARY_UNIT=""

cleanup() {
  if [ -n "$TEMPORARY_UNIT" ] &&
    [ -f "$TEMPORARY_UNIT" ]; then
    rm -f -- "$TEMPORARY_UNIT"
  fi
  if [ -n "$TEMPORARY_DIR" ] &&
    [ -d "$TEMPORARY_DIR" ]; then
    rmdir -- "$TEMPORARY_DIR"
  fi
}

trap cleanup EXIT

if [ -f /.dockerenv ]; then
  echo "ERROR: installer must run on the Jetson host, not inside Docker." >&2
  exit 1
fi
if [ ! -f "$TEMPLATE" ]; then
  echo "ERROR: systemd unit template is missing: $TEMPLATE" >&2
  exit 1
fi
sudo -v
if [ "$(sudo docker inspect \
  --format "{{index .Config.Labels \"$MANAGED_LABEL\"}}" \
  "$CONTAINER_NAME" 2>/dev/null || true)" != "true" ]; then
  echo "ERROR: the validated managed container does not exist." >&2
  echo "Run and accept host_edgesentinel.sh start first." >&2
  exit 1
fi
if [ "$(command -v docker)" != "/usr/bin/docker" ]; then
  echo "ERROR: expected Docker executable at /usr/bin/docker." >&2
  exit 1
fi

TEMPORARY_DIR="$(mktemp -d)"
TEMPORARY_UNIT="$TEMPORARY_DIR/$UNIT_NAME"
cp "$TEMPLATE" "$TEMPORARY_UNIT"

if grep -Eq 'EDGESENTINEL_CONFIG_TOKEN|sk-[A-Za-z0-9]+' \
  "$TEMPORARY_UNIT"; then
  echo "ERROR: generated unit unexpectedly contains a literal credential." >&2
  exit 1
fi
grep -Fq \
  "EnvironmentFile=-/etc/edgesentinel-visionops/model-runtime.env" \
  "$TEMPORARY_UNIT"
grep -Fq \
  "EnvironmentFile=-/etc/edgesentinel-visionops/model-cost-runtime.env" \
  "$TEMPORARY_UNIT"
grep -Fq \
  "EnvironmentFile=-/etc/edgesentinel-visionops/weather-runtime.env" \
  "$TEMPORARY_UNIT"
grep -Fq \
  "EnvironmentFile=-/etc/edgesentinel-visionops/auth-runtime.env" \
  "$TEMPORARY_UNIT"
grep -Fq \
  "EnvironmentFile=-/etc/edgesentinel-visionops/tls-runtime.env" \
  "$TEMPORARY_UNIT"
grep -Fq -- "-e EDGESENTINEL_AUTH_SESSION_SECRET" \
  "$TEMPORARY_UNIT"
grep -Fq -- "-e EDGESENTINEL_TLS_PRIVATE_KEY" \
  "$TEMPORARY_UNIT"
grep -Fq \
  "docker exec -i edgesentinel-visionops" \
  "$TEMPORARY_UNIT"
grep -Fq \
  "< /etc/edgesentinel-visionops/tls/server.key" \
  "$TEMPORARY_UNIT"

# Validate the candidate under its real unit filename before replacing the
# installed unit.  A validation failure leaves the last known-good file intact.
sudo systemd-analyze verify "$TEMPORARY_UNIT"
sudo install \
  --owner root \
  --group root \
  --mode 0644 \
  "$TEMPORARY_UNIT" \
  "$UNIT_PATH"
sudo systemctl daemon-reload
sudo systemctl enable "$UNIT_NAME"

echo
echo "EdgeSentinel boot service installed."
echo "Unit: $UNIT_PATH"
echo "Enabled: $(sudo systemctl is-enabled "$UNIT_NAME")"
echo "Boot mode: read-only zone configuration"
echo "Model mode: persistent DeepSeek when root credential exists;"
echo "            offline fallback otherwise"
echo "Model budget: 16384 tokens; optional root-owned cost rate card"
echo "Weather city: optional root-owned boot configuration"
echo "Authentication: fail-closed root-owned Dashboard credential"
echo "                (configure_auth_boot.sh install)"
echo "HTTPS: optional root-owned TLS certificate and memory-only key injection"
echo "Current runtime was not restarted."
