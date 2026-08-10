#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
CONTEXT_FILE="$PROJECT_DIR/data/harness/context-$RUN_ID.json"

mkdir -p "$PROJECT_DIR/data/harness"
cd "$PROJECT_DIR"

echo "Building compact Agent context..."
python3 -m apps.build_context \
  --message "最近是否有人拿走瓶子？" \
  --max-events 5 \
  --output "$CONTEXT_FILE"

echo
echo "Context acceptance summary:"
python3 -c \
  "import json,sys; x=json.load(open(sys.argv[1],encoding='utf-8')); raw=json.dumps(x); forbidden=['\"detections\"','\"bbox\"','\"evidence_path\"','\"details\"']; assert not any(k in raw for k in forbidden); print('Vision status:',x['vision']['status'],'stale=',x['vision']['stale']); print('Recent events:',x['recent_events']['count']); print('Available tools:',len(x['available_tools'])); print('Arbitrary shell:',x['permissions']['arbitrary_shell']); print('Forbidden fields absent: True')" \
  "$CONTEXT_FILE"

echo "Context file: $CONTEXT_FILE"
