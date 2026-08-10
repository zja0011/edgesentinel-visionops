#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
AUDIT_LOG="$PROJECT_DIR/data/harness/policy-calls-$RUN_ID.jsonl"

mkdir -p "$PROJECT_DIR/data/harness"
cd "$PROJECT_DIR"

echo "Registered tools and policy annotations:"
python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  list-tools

echo
echo "Allowed L0 call:"
python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  invoke event.query \
  --arguments '{"limit":1}'

echo
echo "Denied unallowlisted call:"
if python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  invoke system.shell \
  --arguments '{}'
then
  echo "ERROR: system.shell was unexpectedly allowed"
  exit 1
else
  echo "Policy denial was expected."
fi

echo
echo "Audit summary:"
python3 -c \
  "import json,sys; rows=list(map(json.loads,open(sys.argv[1],encoding='utf-8'))); [print(x['tool_name'],x['status'],'policy=',x.get('policy',{}).get('reason')) for x in rows]; print('Audit records:',len(rows))" \
  "$AUDIT_LOG"

echo "Audit log: $AUDIT_LOG"
