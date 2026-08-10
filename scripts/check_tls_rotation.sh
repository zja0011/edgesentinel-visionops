#!/usr/bin/env bash

set -eu
set -o pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CONTAINER_NAME="edgesentinel-visionops"
CERTIFICATE="/etc/edgesentinel-visionops/tls/server.crt"
BACKUP_ROOT="/etc/edgesentinel-visionops/tls/backups"
MARKER="$PROJECT_DIR/data/runtime/tls/rotation-latest.json"
RESULT_FILE="$(mktemp)"
VALIDATED_FILE="$(mktemp)"

cleanup() {
  rm -f -- "$RESULT_FILE" "$VALIDATED_FILE"
}
trap cleanup EXIT

if [ "$#" -ne 0 ]; then
  echo "Usage: bash scripts/check_tls_rotation.sh" >&2
  exit 1
fi
if [ -f /.dockerenv ]; then
  echo "ERROR: run this check on the Jetson host." >&2
  exit 1
fi
if [ -L "$MARKER" ] || [ ! -f "$MARKER" ]; then
  echo "ERROR: safe TLS rotation marker is unavailable." >&2
  exit 1
fi

cd "$PROJECT_DIR"
echo "Checking the restarted TLS certificate rotation..."
sudo -v
bash "$SCRIPT_DIR/check_tls_systemd_runtime.sh"

current_fingerprint="$(sudo openssl x509 -in "$CERTIFICATE" -outform DER |
  sha256sum | cut -d' ' -f1)"
runtime_fingerprint="$(sudo docker exec "$CONTAINER_NAME" python3 -c \
  "import hashlib,ssl; pem=open('/dev/shm/edgesentinel-tls/server.crt','r').read(); print(hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest())")"
public_fingerprint="$(openssl x509 \
  -in data/runtime/tls/edgesentinel-server.crt -outform DER |
  sha256sum | cut -d' ' -f1)"
service_started_after="$(sudo docker exec "$CONTAINER_NAME" python3 -c \
  "import json; print(json.load(open('/workspace/edgesentinel/data/runtime/service.json',encoding='utf-8')).get('started_at') or '')")"

rotation_id="$(python3 -c \
  "import json,re,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); value=x.get('rotation_id',''); assert re.match(r'^tls-[0-9]{8}T[0-9]{6}[+-][0-9]{4}$',value); print(value)" \
  "$MARKER")"
backup_directory="$BACKUP_ROOT/$rotation_id"
sudo test -d "$backup_directory"
sudo cp "$backup_directory/rotation.json" "$RESULT_FILE"
sudo chown "$(id -u):$(id -g)" "$RESULT_FILE"
[ "$(sha256sum "$MARKER" | cut -d' ' -f1)" = \
  "$(sha256sum "$RESULT_FILE" | cut -d' ' -f1)" ]
python3 -c \
  "import json,re,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); raw=json.dumps(x).lower(); assert x.get('rotation_id') == sys.argv[6]; assert re.match(r'^tls-[0-9]{8}T[0-9]{6}[+-][0-9]{4}$',x['rotation_id']); assert x.get('contains_secret') is False; assert x.get('restart_required') is True; assert x.get('old_certificate_sha256') != x.get('new_certificate_sha256'); assert x.get('new_certificate_sha256') == sys.argv[2] == sys.argv[3] == sys.argv[4]; assert x.get('service_started_before') and x.get('service_started_before') != sys.argv[5]; assert 1 <= int(x.get('backup_count',0)) <= 5; assert 'private_key' not in raw and 'password' not in raw and 'token' not in raw; print(x['old_certificate_sha256']); print(x['new_certificate_sha256']); print(x['backup_count'])" \
  "$RESULT_FILE" "$current_fingerprint" "$runtime_fingerprint" \
  "$public_fingerprint" "$service_started_after" "$rotation_id" \
  > "$VALIDATED_FILE"

old_fingerprint="$(sed -n '1p' "$VALIDATED_FILE")"
new_fingerprint="$(sed -n '2p' "$VALIDATED_FILE")"
backup_count="$(sed -n '3p' "$VALIDATED_FILE")"
[ "$(sudo stat -c '%U:%G|%a' "$backup_directory/server.key")" = \
  "root:root|600" ]
backup_fingerprint="$(sudo openssl x509 \
  -in "$backup_directory/server.crt" -outform DER |
  sha256sum | cut -d' ' -f1)"
[ "$backup_fingerprint" = "$old_fingerprint" ]

echo
echo "TLS Rotation acceptance summary:"
echo "Status: PASS"
echo "Rotation ID: $rotation_id"
echo "Old SHA-256: $old_fingerprint"
echo "New SHA-256: $new_fingerprint"
echo "Runtime certificate match: True"
echo "Public certificate match: True"
echo "Service restarted: True"
echo "Protected backups: $backup_count/5"
echo "Backup private key: root:root 600"
echo "Private key exposed: False"
echo "TLS Rotation smoke test passed."
