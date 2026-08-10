#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
RESULT_FILE="$PROJECT_DIR/data/harness/model-gateway-$RUN_ID.json"

mkdir -p "$PROJECT_DIR/data/harness"
cd "$PROJECT_DIR"

echo "Running offline model gateway contract probe..."
python3 -m apps.model_gateway_probe \
  --output "$RESULT_FILE"

echo
echo "Model Gateway acceptance summary:"
python3 -c \
  "import json,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); calls=x['parsed_response']['tool_calls']; assert x['gateway']=='chat-completions-compatible' and x['network_used'] is False; assert x['request']['https'] and x['request']['tools_sent']==26 and x['request']['authorization_header_present']; assert x['api_key_exposed'] is False and calls[0]['name']=='event.query'; print('Gateway:',x['gateway']); print('Network used:',x['network_used']); print('HTTPS request:',x['request']['https']); print('Tools sent:',x['request']['tools_sent']); print('Parsed tool:',calls[0]['name']); print('Parsed arguments:',calls[0]['arguments']); print('API key exposed:',x['api_key_exposed'])" \
  "$RESULT_FILE"

echo "Result file: $RESULT_FILE"
