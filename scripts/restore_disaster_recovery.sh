#!/usr/bin/env bash

set -eu

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
PROJECT_DIR="$(dirname -- "$SCRIPT_DIR")"
CONTAINER_NAME="edgesentinel-visionops"
UNIT_NAME="edgesentinel-visionops.service"

if [ -f /.dockerenv ]; then
  echo "ERROR: run disaster recovery on the Jetson host." >&2
  exit 1
fi
if [ "$#" -ne 1 ]; then
  echo "Usage: bash scripts/restore_disaster_recovery.sh BACKUP_ID" >&2
  exit 2
fi

backup_id="$1"
case "$backup_id" in
  dr_[0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f][0-9a-f]) ;;
  *) echo "ERROR: invalid backup ID." >&2; exit 2 ;;
esac
cd "$PROJECT_DIR"
echo "DANGER: this will enter maintenance mode for backup $backup_id."
echo "Root-owned DeepSeek, authentication, and TLS credentials are not restored."
printf '%s' "Type ENTER_RECOVERY_MAINTENANCE to stop EdgeSentinel: "
IFS= read -r confirmation
if [ "$confirmation" != "ENTER_RECOVERY_MAINTENANCE" ]; then
  echo "ERROR: maintenance confirmation did not match." >&2
  exit 1
fi

sudo -v
restart_needed=0
recover_service() {
  if [ "$restart_needed" -eq 1 ]; then
    sudo docker stop --time 10 "$CONTAINER_NAME" >/dev/null 2>&1 || true
    sudo systemctl reset-failed "$UNIT_NAME" >/dev/null 2>&1 || true
    sudo systemctl start "$UNIT_NAME" >/dev/null 2>&1 || true
  fi
}
trap recover_service EXIT

sudo systemctl stop "$UNIT_NAME"
restart_needed=1
sudo docker start "$CONTAINER_NAME" >/dev/null

preview_file="$(mktemp)"
trap 'rm -f -- "$preview_file"; recover_service' EXIT
sudo docker exec "$CONTAINER_NAME" \
  python3 -m apps.disaster_recovery preview \
  --backup-id "$backup_id" > "$preview_file"
plan_id="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1],encoding='utf-8'))['plan_id'])" "$preview_file")"
python3 -c \
  "import json,sys; p=json.load(open(sys.argv[1],encoding='utf-8')); print(); print('Maintenance restore preview:'); print('Backup:',p['backup_id']); print('Plan:',p['plan_id']); print('Files:',p['file_count']); print('Changed files:',p['changed_file_count']); print('Unchanged files:',p['unchanged_file_count']); print('Manifest SHA-256:',p['manifest_sha256']); print('Restore performed:',p['restore_performed'])" \
  "$preview_file"
printf '%s' "Type RESTORE_DISASTER_RECOVERY to apply this exact plan: "
IFS= read -r confirmation
if [ "$confirmation" != "RESTORE_DISASTER_RECOVERY" ]; then
  echo "ERROR: restore confirmation did not match; restarting the unchanged service." >&2
  exit 1
fi

sudo docker exec \
  -e EDGESENTINEL_RESTORE_MAINTENANCE=1 \
  "$CONTAINER_NAME" \
  python3 -m apps.disaster_recovery restore \
  --backup-id "$backup_id" \
  --plan-id "$plan_id" \
  --confirmation RESTORE_DISASTER_RECOVERY
sudo docker stop --time 10 "$CONTAINER_NAME" >/dev/null
sudo systemctl reset-failed "$UNIT_NAME"
sudo systemctl start "$UNIT_NAME"
restart_needed=0
rm -f -- "$preview_file"
trap - EXIT

bash "$SCRIPT_DIR/check_systemd_runtime.sh"
echo "Disaster recovery restore and post-restore health check passed."
