#!/usr/bin/env bash

set -eu
set -o pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CONFIG_DIR="/etc/edgesentinel-visionops"
TLS_DIR="$CONFIG_DIR/tls"
ENV_FILE="$CONFIG_DIR/tls-runtime.env"
CERTIFICATE="$TLS_DIR/server.crt"
PRIVATE_KEY="$TLS_DIR/server.key"
BACKUP_ROOT="$TLS_DIR/backups"
PUBLIC_EXPORT="$PROJECT_DIR/data/runtime/tls/edgesentinel-server.crt"
ROTATION_MARKER="$PROJECT_DIR/data/runtime/tls/rotation-latest.json"
UNIT_NAME="edgesentinel-visionops.service"
CONTAINER_NAME="edgesentinel-visionops"
CONFIRMATION_PHRASE="ROTATE_TLS_CERTIFICATE"
CALLER_UID="${SUDO_UID:-$(id -u)}"
CALLER_GID="${SUDO_GID:-$(id -g)}"
BACKUP_DIRECTORY=""
BACKUP_READY=0
COMMITTED=0
MARKER_TEMP=""

cleanup() {
  if [ "$BACKUP_READY" = "1" ] && [ "$COMMITTED" != "1" ]; then
    echo "ERROR: TLS rotation failed; restoring the previous credential." >&2
    sudo install --owner root --group root --mode 0644 \
      "$BACKUP_DIRECTORY/server.crt" "$CERTIFICATE"
    sudo install --owner root --group root --mode 0600 \
      "$BACKUP_DIRECTORY/server.key" "$PRIVATE_KEY"
    sudo install --owner root --group root --mode 0600 \
      "$BACKUP_DIRECTORY/tls-runtime.env" "$ENV_FILE"
    sudo install --owner "$CALLER_UID" --group "$CALLER_GID" \
      --mode 0644 "$BACKUP_DIRECTORY/server.crt" "$PUBLIC_EXPORT"
    sudo rm -f -- \
      "$BACKUP_DIRECTORY/server.crt" \
      "$BACKUP_DIRECTORY/server.key" \
      "$BACKUP_DIRECTORY/tls-runtime.env"
    sudo rmdir -- "$BACKUP_DIRECTORY"
  fi
  if [ -n "$MARKER_TEMP" ] && [ -f "$MARKER_TEMP" ]; then
    rm -f -- "$MARKER_TEMP"
  fi
}
trap cleanup EXIT

if [ "$#" -ne 0 ]; then
  echo "Usage: bash scripts/rotate_tls_boot.sh" >&2
  exit 1
fi
if [ -f /.dockerenv ]; then
  echo "ERROR: run this command on the Jetson host, not inside Docker." >&2
  exit 1
fi

cd "$PROJECT_DIR"
sudo -v
bash "$SCRIPT_DIR/configure_tls_boot.sh" status >/dev/null
if [ "$(sudo systemctl is-active "$UNIT_NAME" 2>/dev/null || true)" != "active" ]; then
  echo "ERROR: rotate TLS only while the managed runtime is healthy." >&2
  exit 1
fi

public_origin="$(sudo sed -n \
  's/^EDGESENTINEL_TLS_PUBLIC_ORIGIN=//p' "$ENV_FILE")"
lan_ip="$(python3 -c \
  "import sys; from urllib.parse import urlsplit; print(urlsplit(sys.argv[1]).hostname or '')" \
  "$public_origin")"
dns_name="$(sudo openssl x509 -in "$CERTIFICATE" -noout \
  -subject -nameopt RFC2253 | sed -n \
  's/^subject=.*CN=\([^,]*\).*$/\1/p')"
dns_name="${dns_name:-$(hostname)}"

echo "Rotate the active EdgeSentinel TLS certificate."
echo "The current private key will be backed up as root:root 0600."
echo "The running service keeps the old in-memory key until restart."
printf 'Type %s to continue: ' "$CONFIRMATION_PHRASE"
IFS= read -r confirmation
if [ "$confirmation" != "$CONFIRMATION_PHRASE" ]; then
  echo "ERROR: TLS rotation confirmation phrase does not match." >&2
  exit 1
fi

sudo install --directory --owner root --group root --mode 0700 \
  "$BACKUP_ROOT"
backup_count="$(sudo find "$BACKUP_ROOT" -mindepth 1 -maxdepth 1 \
  -type d | wc -l | tr -d ' ')"
if [ "$backup_count" -ge 5 ]; then
  echo "ERROR: five protected TLS backups already exist." >&2
  echo "Archive or explicitly remove an old backup before rotating." >&2
  exit 1
fi

rotation_id="tls-$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
BACKUP_DIRECTORY="$BACKUP_ROOT/$rotation_id"
if sudo test -e "$BACKUP_DIRECTORY" || sudo test -L "$BACKUP_DIRECTORY"; then
  echo "ERROR: protected TLS backup ID already exists." >&2
  exit 1
fi
sudo install --directory --owner root --group root --mode 0700 \
  "$BACKUP_DIRECTORY"
sudo install --owner root --group root --mode 0644 \
  "$CERTIFICATE" "$BACKUP_DIRECTORY/server.crt"
sudo install --owner root --group root --mode 0600 \
  "$PRIVATE_KEY" "$BACKUP_DIRECTORY/server.key"
sudo install --owner root --group root --mode 0600 \
  "$ENV_FILE" "$BACKUP_DIRECTORY/tls-runtime.env"
BACKUP_READY=1

old_fingerprint="$(sudo openssl x509 -in "$CERTIFICATE" -outform DER |
  sha256sum | cut -d' ' -f1)"
service_started_before="$(sudo docker exec "$CONTAINER_NAME" python3 -c \
  "import json; print(json.load(open('/workspace/edgesentinel/data/runtime/service.json',encoding='utf-8')).get('started_at') or '')")"
if [ -z "$service_started_before" ]; then
  echo "ERROR: managed service start identity is unavailable." >&2
  exit 1
fi

if ! printf '%s\n%s\n' "$lan_ip" "$dns_name" |
  bash "$SCRIPT_DIR/configure_tls_boot.sh" install; then
  exit 1
fi
new_fingerprint="$(sudo openssl x509 -in "$CERTIFICATE" -outform DER |
  sha256sum | cut -d' ' -f1)"
if [ "$new_fingerprint" = "$old_fingerprint" ]; then
  echo "ERROR: rotated certificate fingerprint did not change." >&2
  exit 1
fi

MARKER_TEMP="$(mktemp)"
python3 -c \
  "import json,sys; from packages.harness.utf8 import write_json_atomic; write_json_atomic(sys.argv[1], {'schema_version':'1.0','rotation_id':sys.argv[2],'rotated_at':sys.argv[3],'public_origin':sys.argv[4],'old_certificate_sha256':sys.argv[5],'new_certificate_sha256':sys.argv[6],'service_started_before':sys.argv[7],'backup_count':int(sys.argv[8]),'restart_required':True,'contains_secret':False})" \
  "$MARKER_TEMP" "$rotation_id" \
  "$(TZ=Asia/Shanghai date --iso-8601=seconds)" "$public_origin" \
  "$old_fingerprint" "$new_fingerprint" "$service_started_before" \
  "$((backup_count + 1))"
sudo install --owner root --group root --mode 0600 \
  "$MARKER_TEMP" "$BACKUP_DIRECTORY/rotation.json"
sudo install --owner "$CALLER_UID" --group "$CALLER_GID" --mode 0644 \
  "$MARKER_TEMP" "$ROTATION_MARKER"

COMMITTED=1
echo
echo "TLS certificate rotation prepared."
echo "Rotation ID: $rotation_id"
echo "Old SHA-256: $old_fingerprint"
echo "New SHA-256: $new_fingerprint"
echo "Protected backups: $((backup_count + 1))/5"
echo "Private key exposed: False"
echo "Running certificate changed: False"
echo "Next command: sudo systemctl restart $UNIT_NAME"
echo "Then run: bash scripts/check_tls_rotation.sh"
