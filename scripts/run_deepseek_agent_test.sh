#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
AUDIT_LOG="$PROJECT_DIR/data/harness/deepseek-agent-tools-$RUN_ID.jsonl"
TRACE_LOG="$PROJECT_DIR/data/harness/deepseek-agent-trace-$RUN_ID.jsonl"
CHECKPOINT_DIR="$PROJECT_DIR/data/harness/deepseek-agent-checkpoints-$RUN_ID"
RESULT_FILE="$PROJECT_DIR/data/harness/deepseek-agent-result-$RUN_ID.json"

mkdir -p "$PROJECT_DIR/data/harness" "$CHECKPOINT_DIR"
cd "$PROJECT_DIR"

if [ -z "${EDGESENTINEL_MODEL_API_KEY:-}" ]; then
  printf "DeepSeek API Key (input hidden): "
  IFS= read -r -s EDGESENTINEL_MODEL_API_KEY
  printf "\n"
  export EDGESENTINEL_MODEL_API_KEY
fi

if [ -z "$EDGESENTINEL_MODEL_API_KEY" ]; then
  echo "DeepSeek API Key must not be empty." >&2
  exit 1
fi

echo "Running one real DeepSeek Agent tool loop..."
EDGESENTINEL_MODEL_MODE=remote \
EDGESENTINEL_MODEL_PROVIDER=deepseek \
EDGESENTINEL_MODEL_TIMEOUT_SECONDS=30 \
EDGESENTINEL_MODEL_MAX_TOKENS=256 \
python3 -m apps.agent_cli \
  --message "请调用事件查询工具查询最近2条瓶子事件。工具参数必须使用英文 object_class=bottle 和 limit=2，然后根据真实工具结果用中文回答。" \
  --max-steps 3 \
  --audit-output "$AUDIT_LOG" \
  --trace-output "$TRACE_LOG" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  --output "$RESULT_FILE"

echo
echo "DeepSeek Agent acceptance summary:"
PYTHONIOENCODING=utf-8 python3 -c \
  "import json,sys,os; result=json.load(open(sys.argv[1],encoding='utf-8')); audit=list(map(json.loads,open(sys.argv[2],encoding='utf-8'))); trace=list(map(json.loads,open(sys.argv[3],encoding='utf-8'))); checkpoint=json.load(open(os.path.join(sys.argv[4],result['task_id']+'.json'),encoding='utf-8')); tools=result['tool_results']; history=checkpoint['model_history']; secret=os.environ['EDGESENTINEL_MODEL_API_KEY']; exposed=any(secret in open(path,encoding='utf-8').read() for path in (sys.argv[1],sys.argv[2],sys.argv[3],os.path.join(sys.argv[4],result['task_id']+'.json'))); roles=[x['role'] for x in history]; types=[x['record_type'] for x in trace]; assert result['status']=='COMPLETED' and result['steps'] in (2,3) and result['answer'].strip(); assert len(tools) in (1,2) and all(x['tool_name']=='event.query' and x['status']=='SUCCEEDED' for x in tools); assert len(audit)==len(tools) and all(x['tool_name']=='event.query' and x['status']=='SUCCEEDED' for x in audit); assert audit[-1]['arguments'].get('object_class')=='bottle' and audit[-1]['arguments'].get('limit')==2; assert types.count('TASK_RESULT')==1 and types.count('MODEL_DECISION')==result['steps'] and types.count('TOOL_RESULT')==len(tools) and types.count('HOOK_RESULT')>=6; assert roles[0]=='user' and roles.count('assistant')==len(tools) and roles.count('tool')==len(tools); assert checkpoint['model_identity']=='chat-completions-compatible:deepseek-v4-flash'; assert exposed is False; print('Task:',result['status']); print('Model identity:',checkpoint['model_identity']); print('Steps:',result['steps']); print('Tool:',tools[-1]['tool_name'],tools[-1]['status']); print('Tool calls:',len(tools)); print('Self-corrections:',len(tools)-1); print('Event count:',tools[-1]['result']['count']); print('Answer:',result['answer']); print('Tool audit records:',len(audit)); print('Agent trace records:',len(trace)); print('Hook trace records:',types.count('HOOK_RESULT')); print('Conversation roles:',roles); print('API key exposed:',exposed)" \
  "$RESULT_FILE" \
  "$AUDIT_LOG" \
  "$TRACE_LOG" \
  "$CHECKPOINT_DIR"

unset EDGESENTINEL_MODEL_API_KEY

echo "Result: $RESULT_FILE"
echo "Checkpoint directory: $CHECKPOINT_DIR"
echo "Tool audit: $AUDIT_LOG"
echo "Agent trace: $TRACE_LOG"
