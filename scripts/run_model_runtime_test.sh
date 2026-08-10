#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
RESULT_FILE="$PROJECT_DIR/data/harness/model-runtime-$RUN_ID.json"

mkdir -p "$PROJECT_DIR/data/harness"
cd "$PROJECT_DIR"

echo "Running offline model runtime configuration probe..."
python3 -m apps.model_runtime_probe \
  --output "$RESULT_FILE"

echo
echo "Model Runtime acceptance summary:"
python3 -c \
  "import json,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); assert x['default']['mode']=='offline' and x['default']['external_requests_enabled'] is False; assert x['configured']['mode']=='remote' and x['configured']['gateway']=='chat-completions-compatible'; assert x['configured']['credential_source']=='environment'; assert x['network_used'] is False and x['injected_transport_calls']==1 and x['authorization_header_present'] is True; assert x['missing_key_rejected'] is True and x['api_key_exposed'] is False; print('Default mode:',x['default']['mode']); print('Configured mode:',x['configured']['mode']); print('Configured gateway:',x['configured']['gateway']); print('Credential source:',x['configured']['credential_source']); print('Network used:',x['network_used']); print('Missing key rejected:',x['missing_key_rejected']); print('API key exposed:',x['api_key_exposed'])" \
  "$RESULT_FILE"

echo "Result file: $RESULT_FILE"
