#!/usr/bin/env bash
set -euo pipefail

export PATH=/usr/sbin:/usr/bin:/sbin:/bin
export LC_ALL=C
umask 077

readonly project_dir="/home/nvidia/projects/edgesentinel-visionops"
readonly container_name="edgesentinel-visionops"
readonly managed_label="com.edgesentinel.managed"
readonly credential_path="/etc/edgesentinel-visionops/recovery-export.key"
readonly export_root="/home/nvidia/edgesentinel-recovery-exports"
readonly output_dir="$export_root/encrypted"
readonly status_path="$export_root/scheduled-export-status.json"
readonly lock_path="/run/lock/edgesentinel-recovery-export.lock"

if [[ "$(id -u)" -ne 0 ]]; then
    echo "ERROR: scheduled recovery export must run as root." >&2
    exit 1
fi
if [[ -L "$project_dir" || -L "$export_root" || -L "$output_dir" ]]; then
    echo "ERROR: scheduled recovery export path cannot be a symlink." >&2
    exit 1
fi
if [[ ! -f "$credential_path" || -L "$credential_path" ]] ||
    [[ "$(stat -c '%U:%G %a' "$credential_path")" != "root:root 600" ]]; then
    echo "ERROR: recovery export credential is unavailable or unsafe." >&2
    exit 1
fi

mkdir -p -- "$output_dir"
chown nvidia:nvidia -- "$export_root" "$output_dir"
chmod 0700 -- "$export_root" "$output_dir"

started_at="$(date --iso-8601=seconds)"
pipeline_status="FAILED"
pipeline_stage="PRECHECK"
sqlite_consistent="false"
backup_id=""
artifact_sha256=""
manifest_sha256=""
create_result="$(mktemp)"
verify_result="$(mktemp)"
status_temporary="$(mktemp "$export_root/.scheduled-export-status.XXXXXX")"

finalize() {
    exit_code="$1"
    trap - EXIT
    finished_at="$(date --iso-8601=seconds)"
    python3 - "$status_temporary" "$pipeline_status" "$pipeline_stage" "$started_at" \
        "$finished_at" "$backup_id" "$artifact_sha256" \
        "$manifest_sha256" "$sqlite_consistent" "$exit_code" <<'PY'
from __future__ import print_function
import json
import os
import sys

path, status, stage, started, finished, backup_id, artifact_hash, manifest_hash, sqlite_ok, code = sys.argv[1:]
payload = {
    "schema_version": "1.0",
    "status": status,
    "stage": stage,
    "started_at": started,
    "finished_at": finished,
    "backup_id": backup_id or None,
    "artifact_sha256": artifact_hash or None,
    "manifest_sha256": manifest_hash or None,
    "exit_code": int(code),
    "sqlite_consistent": sqlite_ok == "true",
    "credentials_included": False,
    "plaintext_persisted": False,
}
with open(path, "w", encoding="utf-8") as output:
    json.dump(payload, output, sort_keys=True, indent=2)
    output.write("\n")
PY
    chown nvidia:nvidia -- "$status_temporary"
    chmod 0644 -- "$status_temporary"
    mv -f -- "$status_temporary" "$status_path"
    rm -f -- "$create_result" "$verify_result"
    exit "$exit_code"
}
trap 'finalize $?' EXIT

exec 9>"$lock_path"
if ! flock -n 9; then
    echo "ERROR: another scheduled recovery export is running." >&2
    exit 75
fi

if [[ "$(docker inspect --format "{{index .Config.Labels \"$managed_label\"}}" \
    "$container_name" 2>/dev/null || true)" != "true" ]]; then
    echo "ERROR: managed EdgeSentinel container is unavailable." >&2
    exit 1
fi
mounted_project="$(docker inspect --format \
    '{{range .Mounts}}{{if eq .Destination "/workspace/edgesentinel"}}{{.Source}}{{end}}{{end}}' \
    "$container_name")"
if [[ "$mounted_project" != "$project_dir" ]]; then
    echo "ERROR: managed container project mount is invalid." >&2
    exit 1
fi
if [[ "$(docker inspect --format '{{.State.Running}}' "$container_name")" != "true" ]]; then
    echo "ERROR: managed EdgeSentinel container is not running." >&2
    exit 1
fi

cd "$project_dir"

docker exec "$container_name" bash -c \
    'cd /workspace/edgesentinel && python3 -m apps.disaster_recovery create' \
    >"$create_result"
backup_id="$(python3 - "$create_result" <<'PY'
from __future__ import print_function
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as input_file:
    value = json.load(input_file)
backup_id = str(value.get("backup_id", ""))
if value.get("status") != "COMPLETE" or not value.get("sqlite_consistent"):
    raise SystemExit("created recovery backup is incomplete")
if value.get("credentials_included") or not re.match(r"^dr_[0-9a-f]{32}$", backup_id):
    raise SystemExit("created recovery backup violates the security contract")
print(backup_id)
PY
)"
pipeline_stage="BACKUP_CREATED"
sqlite_consistent="true"

artifact_path="$output_dir/$backup_id.esdr"
metadata_path="$artifact_path.json"
python3 -m apps.recovery_export create \
    --project-dir "$project_dir" \
    --backup-id "$backup_id" \
    --output-dir "$output_dir" \
    --key-file "$credential_path" >"$verify_result"
pipeline_stage="EXPORT_CREATED"
chown nvidia:nvidia -- "$artifact_path" "$metadata_path"
chmod 0600 -- "$artifact_path" "$metadata_path"

python3 -m apps.recovery_export verify \
    --artifact "$artifact_path" \
    --metadata "$metadata_path" \
    --key-file "$credential_path" >"$verify_result"
readarray -t verified_fields < <(python3 - "$verify_result" <<'PY'
from __future__ import print_function
import json
import re
import sys

with open(sys.argv[1], encoding="utf-8") as input_file:
    value = json.load(input_file)
if value.get("status") != "VERIFIED" or not value.get("verified"):
    raise SystemExit("encrypted recovery export verification failed")
if value.get("credentials_included") or value.get("plaintext_persisted"):
    raise SystemExit("encrypted recovery export violates the security contract")
for key in ("artifact_sha256", "manifest_sha256"):
    digest = str(value.get(key, ""))
    if not re.match(r"^[0-9a-f]{64}$", digest):
        raise SystemExit("encrypted recovery digest is invalid")
    print(digest)
PY
)
artifact_sha256="${verified_fields[0]}"
manifest_sha256="${verified_fields[1]}"
pipeline_stage="VERIFIED"
pipeline_status="SUCCEEDED"

echo "Scheduled Recovery Export acceptance summary:"
echo "Status: $pipeline_status"
echo "Stage: $pipeline_stage"
echo "Backup ID: $backup_id"
echo "Artifact SHA-256: $artifact_sha256"
echo "Manifest SHA-256: $manifest_sha256"
echo "Credentials included: False"
echo "Plaintext persisted: False"
