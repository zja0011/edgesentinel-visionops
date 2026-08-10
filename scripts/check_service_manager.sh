#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
STATUS_FILE="$PROJECT_DIR/data/runtime/service-status-check.json"

cd "$PROJECT_DIR"

echo "Checking the managed EdgeSentinel runtime..."
attempt=0
while [ "$attempt" -lt 30 ]; do
  bash "$SCRIPT_DIR/edgesentinel_service.sh" status --json > "$STATUS_FILE"
  if python3 -c \
    "import json,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['status']=='running'; assert x['api']['status']=='ok'; assert x['vision']['status']=='available'; assert x['vision']['stale'] is False" \
    "$STATUS_FILE" 2>/dev/null; then
    break
  fi
  attempt=$((attempt + 1))
  sleep 2
done

python3 -c \
  "import json,os,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); state=json.load(open(x['state_path'],encoding='utf-8')); raw=json.dumps(state).lower(); assert x['status']=='running'; assert x['process']['running'] is True; assert x['process']['verified'] is True; assert x['api']['status']=='ok'; assert x['vision']['status']=='available'; assert x['vision']['stale'] is False; assert x['secret_persisted'] is False; assert 'token' not in raw and 'secret' not in raw; assert os.path.isfile(x['log_path']); print(); print('Service Manager acceptance summary:'); print('Status:',x['status']); print('PID:',x['process']['pid']); print('Process verified:',x['process']['verified']); print('API status:',x['api']['status']); print('Vision stale:',x['vision']['stale']); print('Frame ID:',x['vision']['frame_id']); print('Log:',x['log_path']); print('Zone administrator credential persisted:',x['secret_persisted']); print('Model mode:',x['model_mode']); print('Model credential persisted:',x['model_credential_persisted']); print('TLS enabled:',x.get('tls_enabled',False)); print('TLS public origin:',x.get('tls_public_origin') or 'disabled'); print('Service Manager smoke test passed.')" \
  "$STATUS_FILE"
