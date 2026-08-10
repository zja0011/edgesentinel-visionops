#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
UNIT_NAME="edgesentinel-visionops.service"
CONTAINER_NAME="edgesentinel-visionops"
STATUS_FILE="$(mktemp)"
HEALTH_FILE="$(mktemp)"
STATE_FILE="$(mktemp)"

cleanup() {
  if [ -f "$STATUS_FILE" ]; then
    rm -f -- "$STATUS_FILE"
  fi
  if [ -f "$HEALTH_FILE" ]; then
    rm -f -- "$HEALTH_FILE"
  fi
  if [ -f "$STATE_FILE" ]; then
    rm -f -- "$STATE_FILE"
  fi
}

trap cleanup EXIT

if [ -f /.dockerenv ]; then
  echo "ERROR: this check must run on the Jetson host, not inside Docker." >&2
  exit 1
fi

cd "$PROJECT_DIR"
echo "Checking the active systemd-managed runtime..."
sudo -v

enabled="$(sudo systemctl is-enabled "$UNIT_NAME")"
active="$(sudo systemctl is-active "$UNIT_NAME")"
container_running="$(sudo docker inspect \
  --format '{{.State.Running}}' \
  "$CONTAINER_NAME")"
container_environment="$(sudo docker inspect \
  --format '{{range .Config.Env}}{{println .}}{{end}}' \
  "$CONTAINER_NAME")"

[ "$enabled" = "enabled" ]
[ "$active" = "active" ]
[ "$container_running" = "true" ]
if printf '%s\n' "$container_environment" |
  grep -q '^EDGESENTINEL_CONFIG_TOKEN='; then
  echo "ERROR: configuration token was persisted in Docker." >&2
  exit 1
fi

sudo docker exec "$CONTAINER_NAME" \
  bash scripts/check_service_manager.sh
sudo docker exec "$CONTAINER_NAME" \
  python3 -m apps.service_manager status --json > "$STATUS_FILE"
sudo docker exec "$CONTAINER_NAME" \
  python3 -c \
    "from urllib.request import urlopen; print(urlopen('http://127.0.0.1:8000/health',timeout=3).read().decode('utf-8'))" \
    > "$HEALTH_FILE"
sudo docker exec "$CONTAINER_NAME" \
  python3 -c \
    "import json; print(json.dumps(json.load(open('/workspace/edgesentinel/data/runtime/service.json',encoding='utf-8'))))" \
    > "$STATE_FILE"

write_status="$(sudo docker exec "$CONTAINER_NAME" \
  python3 -c \
    "from urllib.error import HTTPError; from urllib.request import Request,urlopen; request=Request('http://127.0.0.1:8000/api/v1/zones',data=b'{}',headers={'Content-Type':'application/json'},method='PUT'); code=0
try:
 urlopen(request,timeout=3)
except HTTPError as error:
 code=error.code
print(code)")"

python3 -c \
  "import json,sys; status=json.load(open(sys.argv[1],encoding='utf-8')); health=json.load(open(sys.argv[2],encoding='utf-8')); state=json.load(open(sys.argv[3],encoding='utf-8')); raw=json.dumps(state).lower(); auth=health['authentication']; assert status['status']=='running'; assert status['process']['verified'] is True; assert status['api']['status']=='ok'; assert status['vision']['status']=='available'; assert status['vision']['stale'] is False; assert status['config_save_enabled'] is False; assert auth['enabled'] is True and auth['ready'] is True; assert auth['credentials_exposed'] is False; assert 'token' not in raw and 'secret' not in raw; print(); print('Systemd Runtime acceptance summary:'); print('Unit enabled: enabled'); print('Unit active:',sys.argv[4]); print('Container running: true'); print('Runtime status:',status['status']); print('Process verified:',status['process']['verified']); print('API status:',status['api']['status']); print('Vision stale:',status['vision']['stale']); print('Frame ID:',status['vision']['frame_id']); print('Zone configuration saving:',status['config_save_enabled']); print('Authentication enabled:',auth['enabled']); print('Authentication ready:',auth['ready']); print('Zone administrator credential persisted:',status['secret_persisted']); print('Model mode:',status['model_mode']); print('Model credential persisted:',status['model_credential_persisted']); print('TLS enabled:',status.get('tls_enabled',False)); print('TLS public origin:',status.get('tls_public_origin') or 'disabled')" \
  "$STATUS_FILE" \
  "$HEALTH_FILE" \
  "$STATE_FILE" \
  "$active"

tls_enabled="$(python3 -c \
  "import json,sys; print('true' if json.load(open(sys.argv[1],encoding='utf-8')).get('tls_enabled',False) else 'false')" \
  "$STATUS_FILE")"
if [ "$tls_enabled" = "true" ]; then
  expected_write_status="426"
  write_rejection="Plaintext zone write rejected"
else
  expected_write_status="401"
  write_rejection="Unauthenticated zone write rejected"
fi
[ "$write_status" = "$expected_write_status" ]
echo "$write_rejection: HTTP $write_status"
echo "Systemd Runtime smoke test passed."
