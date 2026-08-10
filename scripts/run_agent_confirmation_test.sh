#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
HARNESS_DIR="$PROJECT_DIR/data/harness"
SNAPSHOT_DIR="$PROJECT_DIR/data/evidence/manual-snapshots"
AUDIT_LOG="$HARNESS_DIR/confirmation-tools-$RUN_ID.jsonl"
TRACE_LOG="$HARNESS_DIR/confirmation-trace-$RUN_ID.jsonl"
CHECKPOINT_DIR="$HARNESS_DIR/confirmation-checkpoints-$RUN_ID"
PENDING_RESULT="$HARNESS_DIR/confirmation-pending-$RUN_ID.json"
COMPLETED_RESULT="$HARNESS_DIR/confirmation-completed-$RUN_ID.json"
BEFORE_FILE="$HARNESS_DIR/confirmation-before-$RUN_ID.json"
UNCONFIRMED_ERROR="$HARNESS_DIR/confirmation-required-$RUN_ID.txt"

mkdir -p "$HARNESS_DIR" "$CHECKPOINT_DIR"
cd "$PROJECT_DIR"

python3 - "$SNAPSHOT_DIR" "$BEFORE_FILE" <<'PY'
import json
import os
import sys

names = (
    sorted(os.listdir(sys.argv[1]))
    if os.path.isdir(sys.argv[1])
    else []
)
with open(sys.argv[2], "w", encoding="utf-8") as output:
    json.dump(names, output)
PY

echo "Requesting a snapshot through the natural-language Agent..."
python3 -m apps.agent_cli \
  --message "capture snapshot" \
  --audit-output "$AUDIT_LOG" \
  --trace-output "$TRACE_LOG" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  --output "$PENDING_RESULT"

TASK_ID="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8'))['task_id'])" "$PENDING_RESULT")"

python3 - \
  "$PENDING_RESULT" \
  "$CHECKPOINT_DIR" \
  "$SNAPSHOT_DIR" \
  "$BEFORE_FILE" \
  "$AUDIT_LOG" <<'PY'
import json
import os
import sys

pending = json.load(open(sys.argv[1], encoding="utf-8"))
checkpoint = json.load(
    open(
        os.path.join(sys.argv[2], pending["task_id"] + ".json"),
        encoding="utf-8",
    )
)
after_pending = (
    set(os.listdir(sys.argv[3]))
    if os.path.isdir(sys.argv[3])
    else set()
)
before = set(json.load(open(sys.argv[4], encoding="utf-8")))
assert pending["status"] == "AWAITING_CONFIRMATION"
assert pending["tool_results"] == []
assert pending["pending_confirmation"]["tool_name"] == (
    "camera.capture_snapshot"
)
assert pending["pending_confirmation"]["risk"] == "L1"
assert checkpoint["status"] == "AWAITING_CONFIRMATION"
assert after_pending == before
assert not os.path.exists(sys.argv[5])
PY

echo "Verifying that resume without confirmation is rejected..."
if python3 -m apps.agent_cli \
  --resume-task-id "$TASK_ID" \
  --audit-output "$AUDIT_LOG" \
  --trace-output "$TRACE_LOG" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  > /dev/null 2> "$UNCONFIRMED_ERROR"
then
  echo "ERROR: pending tool resumed without confirmation." >&2
  exit 1
fi

echo "Confirming only the stored pending tool..."
python3 -m apps.agent_cli \
  --resume-task-id "$TASK_ID" \
  --confirm-pending-tool \
  --audit-output "$AUDIT_LOG" \
  --trace-output "$TRACE_LOG" \
  --checkpoint-dir "$CHECKPOINT_DIR" \
  --output "$COMPLETED_RESULT"

python3 - \
  "$PROJECT_DIR" \
  "$SNAPSHOT_DIR" \
  "$PENDING_RESULT" \
  "$COMPLETED_RESULT" \
  "$CHECKPOINT_DIR" \
  "$AUDIT_LOG" \
  "$TRACE_LOG" \
  "$BEFORE_FILE" \
  "$UNCONFIRMED_ERROR" <<'PY'
import json
import os
import sys

project = os.path.realpath(sys.argv[1])
snapshot_dir = os.path.realpath(sys.argv[2])
pending = json.load(open(sys.argv[3], encoding="utf-8"))
completed = json.load(open(sys.argv[4], encoding="utf-8"))
checkpoint = json.load(
    open(
        os.path.join(sys.argv[5], completed["task_id"] + ".json"),
        encoding="utf-8",
    )
)
audit = list(map(json.loads, open(sys.argv[6], encoding="utf-8")))
trace = list(map(json.loads, open(sys.argv[7], encoding="utf-8")))
before = set(json.load(open(sys.argv[8], encoding="utf-8")))
error_text = open(sys.argv[9], encoding="utf-8").read()

assert "explicit confirmation is required" in error_text
assert pending["task_id"] == completed["task_id"]
assert completed["status"] == "COMPLETED"
assert completed["steps"] == 2
assert len(completed["tool_results"]) == 1
tool = completed["tool_results"][0]
assert tool["tool_name"] == "camera.capture_snapshot"
assert tool["status"] == "SUCCEEDED"
result = tool["result"]
path = os.path.realpath(
    os.path.join(project, *result["evidence_path"].split("/"))
)
assert os.path.commonpath([path, snapshot_dir]) == snapshot_dir
assert os.path.isfile(path)
after = set(os.listdir(snapshot_dir))
assert after - before == {os.path.basename(path)}
assert result["evidence_path"] in completed["answer"]
assert len(audit) == 1
assert audit[0]["tool_name"] == "camera.capture_snapshot"
assert audit[0]["status"] == "SUCCEEDED"
assert audit[0]["policy"]["reason"] == "ALLOWED"
types = [record["record_type"] for record in trace]
assert types == [
    "MODEL_DECISION",
    "CONFIRMATION_REQUIRED",
    "TASK_RESUMED",
    "CONFIRMATION_GRANTED",
    "TOOL_RESULT",
    "MODEL_DECISION",
    "TASK_RESULT",
]
assert checkpoint["status"] == "COMPLETED"
assert checkpoint["pending_confirmation"] is None

print()
print("Agent Confirmation acceptance summary:")
print("Pending task:", pending["status"])
print("Pending tool:", pending["pending_confirmation"]["tool_name"])
print("Pending risk:", pending["pending_confirmation"]["risk"])
print("Unconfirmed resume: REJECTED")
print("Confirmed task:", completed["status"])
print("Same task ID:", pending["task_id"] == completed["task_id"])
print("Steps:", completed["steps"])
print("Tool:", tool["tool_name"], tool["status"])
print("Snapshot:", result["evidence_path"])
print("Tool audit records:", len(audit))
print("Agent trace records:", len(trace))
print("Final checkpoint:", checkpoint["status"])
print("Agent Confirmation smoke test passed.")
PY

echo "Checkpoint directory: $CHECKPOINT_DIR"
echo "Tool audit: $AUDIT_LOG"
echo "Agent trace: $TRACE_LOG"
