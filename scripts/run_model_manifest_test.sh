#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

STAMP="$(
  python3 -c "
import datetime
zone = datetime.timezone(datetime.timedelta(hours=8))
print(datetime.datetime.now(zone).strftime('%Y%m%dT%H%M%S+0800'))
"
)"
AUDIT_OUTPUT="$PROJECT_DIR/data/harness/model-tools-$STAMP.jsonl"
RESULT_OUTPUT="$PROJECT_DIR/data/harness/model-result-$STAMP.json"

echo "Checking active TensorRT model provenance and integrity..."
python3 -m apps.model_manifest_smoke_test \
  --project-dir "$PROJECT_DIR" \
  --database data/events/edgesentinel.db \
  --manifest data/state/current-model.json \
  --model-root /jetson-inference/data/networks \
  --audit-output "$AUDIT_OUTPUT" \
  --result-output "$RESULT_OUTPUT"
