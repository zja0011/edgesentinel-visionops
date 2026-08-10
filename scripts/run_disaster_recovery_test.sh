#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"

cd "$PROJECT_DIR"
echo "Checking bounded disaster-recovery backup and restore preview..."
python3 -m unittest tests.unit.test_disaster_recovery -q

result_file="$(mktemp)"
status_file="$(mktemp)"
preview_file="$(mktemp)"
cleanup() {
  rm -f -- "$result_file" "$status_file" "$preview_file"
}
trap cleanup EXIT

python3 -m apps.disaster_recovery create > "$result_file"
backup_id="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8'))['backup_id'])" "$result_file")"
python3 -m apps.disaster_recovery status --limit 5 > "$status_file"
python3 -m apps.disaster_recovery preview --backup-id "$backup_id" > "$preview_file"

python3 -c \
  "import json,sys; created=json.load(open(sys.argv[1],encoding='utf-8')); status=json.load(open(sys.argv[2],encoding='utf-8')); preview=json.load(open(sys.argv[3],encoding='utf-8')); assert created['status']=='COMPLETE'; assert created['sqlite_consistent'] is True; assert created['credentials_included'] is False; assert status['backup_count']>=1; assert status['backups'][0]['backup_id']==created['backup_id']; assert preview['status']=='COMPLETE'; assert preview['mode']=='PREVIEW_ONLY'; assert preview['restore_performed'] is False; assert preview['credentials_included'] is False; print(); print('Disaster Recovery acceptance summary:'); print('Backup:',created['backup_id']); print('Files:',created['file_count']); print('Bytes:',created['bytes']); print('SQLite consistent:',created['sqlite_consistent']); print('Manifest SHA-256:',created['manifest_sha256']); print('Verified backups:',status['backup_count']); print('Restore plan:',preview['plan_id']); print('Changed files:',preview['changed_file_count']); print('Restore performed:',preview['restore_performed']); print('Credentials included:',created['credentials_included'])" \
  "$result_file" "$status_file" "$preview_file"

echo "Disaster Recovery smoke test passed."
