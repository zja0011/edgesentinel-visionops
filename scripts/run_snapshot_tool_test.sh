#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
RUN_ID="$(TZ=Asia/Shanghai date +%Y%m%dT%H%M%S%z)"
HARNESS_DIR="$PROJECT_DIR/data/harness"
SNAPSHOT_DIR="$PROJECT_DIR/data/evidence/manual-snapshots"
AUDIT_LOG="$HARNESS_DIR/snapshot-tools-$RUN_ID.jsonl"
TOOLS_FILE="$HARNESS_DIR/snapshot-tool-schemas-$RUN_ID.json"
DENIED_FILE="$HARNESS_DIR/snapshot-denied-$RUN_ID.json"
RESULT_FILE="$HARNESS_DIR/snapshot-confirmed-$RUN_ID.json"
BEFORE_FILE="$HARNESS_DIR/snapshot-before-$RUN_ID.json"

mkdir -p "$HARNESS_DIR"
cd "$PROJECT_DIR"

python3 - "$SNAPSHOT_DIR" "$BEFORE_FILE" <<'PY'
import json
import os
import sys

directory = sys.argv[1]
names = (
    sorted(os.listdir(directory))
    if os.path.isdir(directory)
    else []
)
with open(sys.argv[2], "w", encoding="utf-8") as output:
    json.dump(names, output)
PY

python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  list-tools > "$TOOLS_FILE"

echo "Verifying that an unconfirmed snapshot is denied..."
if python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  invoke camera.capture_snapshot \
  --arguments '{}' > "$DENIED_FILE"
then
  echo "ERROR: unconfirmed snapshot was unexpectedly allowed." >&2
  exit 1
fi

echo "Capturing one explicitly confirmed snapshot..."
python3 -m apps.harness_cli \
  --audit-output "$AUDIT_LOG" \
  invoke camera.capture_snapshot \
  --arguments '{}' \
  --confirm > "$RESULT_FILE"

python3 - \
  "$PROJECT_DIR" \
  "$SNAPSHOT_DIR" \
  "$TOOLS_FILE" \
  "$DENIED_FILE" \
  "$RESULT_FILE" \
  "$AUDIT_LOG" \
  "$BEFORE_FILE" <<'PY'
import hashlib
import json
import os
import sys

project = os.path.realpath(sys.argv[1])
snapshot_dir = os.path.realpath(sys.argv[2])
tools = json.load(open(sys.argv[3], encoding="utf-8"))["tools"]
denied = json.load(open(sys.argv[4], encoding="utf-8"))
confirmed = json.load(open(sys.argv[5], encoding="utf-8"))
audit = list(map(json.loads, open(sys.argv[6], encoding="utf-8")))
before = set(json.load(open(sys.argv[7], encoding="utf-8")))

schema = next(
    item for item in tools
    if item["name"] == "camera.capture_snapshot"
)
annotations = schema["annotations"]
assert annotations["readOnlyHint"] is False
assert annotations["riskLevel"] == "L1"
assert annotations["autoExecute"] is False
assert annotations["requiresConfirmation"] is True

assert denied["status"] == "FAILED"
assert denied["error"]["code"] == "POLICY_DENIED"
assert denied["error"]["message"] == "CONFIRMATION_REQUIRED"
assert confirmed["status"] == "SUCCEEDED"
result = confirmed["result"]
path = os.path.realpath(
    os.path.join(project, *result["evidence_path"].split("/"))
)
assert os.path.commonpath([path, snapshot_dir]) == snapshot_dir
assert os.path.isfile(path)
content = open(path, "rb").read()
assert content[:2] == b"\xff\xd8" and content[-2:] == b"\xff\xd9"
assert len(content) == result["bytes"]
assert hashlib.sha256(content).hexdigest() == result["sha256"]
after = set(os.listdir(snapshot_dir))
assert after - before == {os.path.basename(path)}
assert len(audit) == 2
assert audit[0]["policy"]["reason"] == "CONFIRMATION_REQUIRED"
assert audit[0]["status"] == "FAILED"
assert audit[1]["policy"]["reason"] == "ALLOWED"
assert audit[1]["status"] == "SUCCEEDED"

print()
print("Snapshot Tool acceptance summary:")
print("Tool:", schema["name"])
print("Risk:", annotations["riskLevel"])
print("Requires confirmation:", annotations["requiresConfirmation"])
print("Unconfirmed call:", denied["status"], denied["error"]["message"])
print("Confirmed call:", confirmed["status"])
print("Snapshot ID:", result["snapshot_id"])
print("Camera:", result["camera_id"])
print("Vision frame:", result["vision_frame_id"])
print("JPEG bytes:", result["bytes"])
print("Evidence path:", result["evidence_path"])
print("Audit records:", len(audit))
print("Snapshot Tool smoke test passed.")
PY

echo "Audit log: $AUDIT_LOG"
