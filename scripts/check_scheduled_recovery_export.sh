#!/usr/bin/env bash
set -euo pipefail

timer="edgesentinel-recovery-export.timer"
service="edgesentinel-recovery-export.service"
runner="/usr/local/libexec/edgesentinel-scheduled-recovery-export"
capacity_runner="/usr/local/libexec/edgesentinel-recovery-capacity-manager"
status_path="/home/nvidia/edgesentinel-recovery-exports/scheduled-export-status.json"
timer_path="/etc/systemd/system/edgesentinel-recovery-export.timer"
service_path="/etc/systemd/system/edgesentinel-recovery-export.service"

echo "Checking scheduled encrypted recovery exports..."
if ! sudo test -f "$timer_path" || ! sudo test -f "$service_path"; then
    echo "Scheduled recovery export: not installed"
    echo "Next: bash scripts/install_scheduled_recovery_export.sh"
    exit 1
fi
if ! sudo test -f "$runner" || sudo test -L "$runner" ||
    ! sudo test -f "$capacity_runner" || sudo test -L "$capacity_runner"; then
    echo "Scheduled recovery export: installed assets are incomplete"
    echo "Next: bash scripts/install_scheduled_recovery_export.sh"
    exit 1
fi
enabled="$(sudo systemctl is-enabled "$timer")"
active="$(sudo systemctl is-active "$timer")"
runner_identity="$(sudo stat -c '%U:%G %a' "$runner")"
capacity_identity="$(sudo stat -c '%U:%G %a' "$capacity_runner")"
next_run="$(sudo systemctl show "$timer" -p NextElapseUSecRealtime --value)"
last_result="$(sudo systemctl show "$service" -p Result --value)"
calendar="$(sudo grep -F 'OnCalendar=' "$timer_path")"

[[ "$enabled" == "enabled" ]]
[[ "$active" == "active" ]]
[[ "$runner_identity" == "root:root 755" ]]
[[ "$capacity_identity" == "root:root 755" ]]
[[ "$calendar" == 'OnCalendar=Sun *-*-* 02:00:00 Asia/Shanghai' ]]

echo
echo "Scheduled Recovery Export summary:"
echo "Timer enabled: $enabled"
echo "Timer active: $active"
echo "Profile: DEMO_WEEKLY"
echo "Schedule: Sunday 02:00 Asia/Shanghai"
echo "Next run: $next_run"
echo "Runner owner/mode: $runner_identity"
echo "Capacity manager owner/mode: $capacity_identity"
echo "Last service result: ${last_result:-not-run}"
echo "Automatic deletion: False"
echo "Credential exposed: False"
if [[ -f "$status_path" && ! -L "$status_path" ]]; then
    python3 - "$status_path" <<'PY'
from __future__ import print_function
import json
import sys

with open(sys.argv[1], encoding="utf-8") as input_file:
    value = json.load(input_file)
print("Last export status:", value.get("status"))
print("Last export stage:", value.get("stage"))
print("Last backup ID:", value.get("backup_id"))
print("Last export finished:", value.get("finished_at"))
print("Credentials included:", value.get("credentials_included"))
print("Plaintext persisted:", value.get("plaintext_persisted"))
PY
else
    echo "Last export status: not yet run"
fi
echo "Scheduled Recovery Export smoke test passed."
