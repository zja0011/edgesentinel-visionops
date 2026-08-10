#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
AUDIT_LOG="$PROJECT_DIR/data/harness/tool-calls-$RUN_ID.jsonl"

mkdir -p "$PROJECT_DIR/data/harness"
cd "$PROJECT_DIR"

echo "Registered tools:"
python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  list-tools

echo
echo "Invoking event.query for the latest two bottle events:"
python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  invoke event.query \
  --arguments '{"object_class":"bottle","limit":2}'

echo
echo "Audit log: $AUDIT_LOG"
echo "Audit summary:"
python3 - "$AUDIT_LOG" <<'PY'
import json
import sys

with open(sys.argv[1], "r", encoding="utf-8") as audit_file:
    records = [json.loads(line) for line in audit_file]

for record in records:
    print(
        record["started_at"],
        record["call_id"],
        record["tool_name"],
        record["status"],
        "latency_ms={0}".format(record["latency_ms"]),
        "result_summary={0}".format(record["result_summary"]),
    )

print("Audit records:", len(records))
PY
