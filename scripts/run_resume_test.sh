#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
AUDIT_LOG="$PROJECT_DIR/data/harness/resume-tools-$RUN_ID.jsonl"
TRACE_LOG="$PROJECT_DIR/data/harness/resume-trace-$RUN_ID.jsonl"
CHECKPOINT_DIR="$PROJECT_DIR/data/harness/resume-checkpoints-$RUN_ID"
PAUSED_RESULT="$PROJECT_DIR/data/harness/resume-paused-$RUN_ID.json"
COMPLETED_RESULT="$PROJECT_DIR/data/harness/resume-completed-$RUN_ID.json"

mkdir -p "$PROJECT_DIR/data/harness" "$CHECKPOINT_DIR"
cd "$PROJECT_DIR"

echo "Starting a task and pausing after its first tool step..."
python3 -m apps.agent_cli \
  --message "最近是否有人拿走瓶子？" \
  --pause-after-step 1 \
  --audit-output "$AUDIT_LOG" \
  --trace-output "$TRACE_LOG" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  --output "$PAUSED_RESULT"

TASK_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8'))['task_id'])" "$PAUSED_RESULT")"

echo
echo "Resuming task: $TASK_ID"
python3 -m apps.agent_cli \
  --resume-task-id "$TASK_ID" \
  --audit-output "$AUDIT_LOG" \
  --trace-output "$TRACE_LOG" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  --output "$COMPLETED_RESULT"

echo
echo "Resume acceptance summary:"
python3 -c \
  "import json,sys,os; p=json.load(open(sys.argv[1],encoding='utf-8')); c=json.load(open(sys.argv[2],encoding='utf-8')); a=list(map(json.loads,open(sys.argv[3],encoding='utf-8'))); t=list(map(json.loads,open(sys.argv[4],encoding='utf-8'))); cp=json.load(open(os.path.join(sys.argv[5],c['task_id']+'.json'),encoding='utf-8')); assert p['status']=='PAUSED' and c['status']=='COMPLETED' and p['task_id']==c['task_id']; assert len(a)==1 and a[0]['tool_name']=='event.query' and a[0]['status']=='SUCCEEDED'; assert cp['status']=='COMPLETED' and cp['answer']==c['answer']; print('Paused task:',p['status'],'steps=',p['steps']); print('Resumed task:',c['status'],'steps=',c['steps']); print('Same task ID:',p['task_id']==c['task_id']); print('Tool audit records:',len(a)); print('Agent trace records:',len(t)); print('Final checkpoint:',cp['status'])" \
  "$PAUSED_RESULT" \
  "$COMPLETED_RESULT" \
  "$AUDIT_LOG" \
  "$TRACE_LOG" \
  "$CHECKPOINT_DIR"

echo "Checkpoint directory: $CHECKPOINT_DIR"
echo "Tool audit: $AUDIT_LOG"
echo "Agent trace: $TRACE_LOG"
