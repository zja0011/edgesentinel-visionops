#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
RESULT_FILE="$PROJECT_DIR/data/harness/deepseek-live-$RUN_ID.json"

mkdir -p "$PROJECT_DIR/data/harness"
cd "$PROJECT_DIR"

KEY_ENTERED_HERE=false
if [ -z "${EDGESENTINEL_MODEL_API_KEY:-}" ]; then
  printf "DeepSeek API Key (input hidden): "
  IFS= read -r -s EDGESENTINEL_MODEL_API_KEY
  printf "\n"
  export EDGESENTINEL_MODEL_API_KEY
  KEY_ENTERED_HERE=true
fi

if [ -z "$EDGESENTINEL_MODEL_API_KEY" ]; then
  echo "DeepSeek API Key must not be empty." >&2
  exit 1
fi

echo "Sending one bounded request to the official DeepSeek API..."
EDGESENTINEL_MODEL_MODE=remote \
EDGESENTINEL_MODEL_PROVIDER=deepseek \
EDGESENTINEL_MODEL_TIMEOUT_SECONDS=30 \
EDGESENTINEL_MODEL_MAX_TOKENS=128 \
python3 -m apps.deepseek_live_probe \
  --output "$RESULT_FILE"

if [ "$KEY_ENTERED_HERE" = true ]; then
  unset EDGESENTINEL_MODEL_API_KEY
fi

echo
echo "DeepSeek live acceptance summary:"
python3 -c \
  "import json,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); calls=x['response']['tool_calls']; assert x['runtime']['provider']=='deepseek' and x['runtime']['model']=='deepseek-v4-flash'; assert x['network_used'] is True and x['api_key_exposed'] is False; assert x['request_limits']['max_tokens']==128 and calls and calls[0]['name']=='event.query'; args=calls[0]['arguments']; assert args.get('object_class')=='bottle' and args.get('limit')==2; print('Provider:',x['runtime']['provider']); print('Model:',x['runtime']['model']); print('Network used:',x['network_used']); print('Max output tokens:',x['request_limits']['max_tokens']); print('Parsed tool:',calls[0]['name']); print('Parsed arguments:',args); print('Usage:',x['usage']); print('API key exposed:',x['api_key_exposed'])" \
  "$RESULT_FILE"

echo "Result file: $RESULT_FILE"
