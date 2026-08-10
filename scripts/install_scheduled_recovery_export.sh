#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runner_source="$project_dir/scripts/run_scheduled_recovery_export.sh"
capacity_source="$project_dir/scripts/recovery_capacity_manager.py"
service_source="$project_dir/deploy/edgesentinel-recovery-export.service"
timer_source="$project_dir/deploy/edgesentinel-recovery-export.timer"
runner_target="/usr/local/libexec/edgesentinel-scheduled-recovery-export"
capacity_target="/usr/local/libexec/edgesentinel-recovery-capacity-manager"
service_target="/etc/systemd/system/edgesentinel-recovery-export.service"
timer_target="/etc/systemd/system/edgesentinel-recovery-export.timer"
credential_path="/etc/edgesentinel-visionops/recovery-export.key"

if [[ -f /.dockerenv ]]; then
    echo "ERROR: scheduled recovery export installer must run on the Jetson host." >&2
    exit 1
fi
bash -n "$runner_source"
python3 - "$capacity_source" <<'PY'
from __future__ import print_function
import sys

with open(sys.argv[1], encoding="utf-8") as source:
    compile(source.read(), sys.argv[1], "exec")
PY
if ! sudo test -f "$credential_path" ||
    sudo test -L "$credential_path" ||
    [[ "$(sudo stat -c '%U:%G %a' "$credential_path")" != "root:root 600" ]]; then
    echo "ERROR: configure the root-owned recovery export key first." >&2
    exit 1
fi
grep -Fq 'NoNewPrivileges=true' "$service_source"
grep -Fq 'ProtectSystem=strict' "$service_source"
grep -Fq 'Persistent=true' "$timer_source"
grep -Fq 'RandomizedDelaySec=300' "$timer_source"
grep -Fq 'OnCalendar=Sun *-*-* 02:00:00 Asia/Shanghai' "$timer_source"

temporary="$(mktemp -d)"
cleanup() {
    rm -f -- \
        "$temporary/edgesentinel-scheduled-recovery-export" \
        "$temporary/edgesentinel-recovery-export.service" \
        "$temporary/edgesentinel-recovery-export.timer"
    rmdir -- "$temporary"
}
trap cleanup EXIT
cp "$runner_source" "$temporary/edgesentinel-scheduled-recovery-export"
chmod 0755 "$temporary/edgesentinel-scheduled-recovery-export"
sed \
    "s#^ExecStart=/usr/local/libexec/edgesentinel-scheduled-recovery-export\$#ExecStart=$temporary/edgesentinel-scheduled-recovery-export#" \
    "$service_source" > "$temporary/edgesentinel-recovery-export.service"
cp "$timer_source" "$temporary/edgesentinel-recovery-export.timer"
grep -Fq \
    "ExecStart=$temporary/edgesentinel-scheduled-recovery-export" \
    "$temporary/edgesentinel-recovery-export.service"
sudo systemd-analyze verify \
    "$temporary/edgesentinel-recovery-export.service" \
    "$temporary/edgesentinel-recovery-export.timer"
sudo install -d -o root -g root -m 0755 /usr/local/libexec
sudo install -o root -g root -m 0755 "$runner_source" "$runner_target"
sudo install -o root -g root -m 0755 "$capacity_source" "$capacity_target"
sudo install -o root -g root -m 0644 "$service_source" "$service_target"
sudo install -o root -g root -m 0644 "$timer_source" "$timer_target"
sudo systemctl daemon-reload
sudo systemctl enable --now edgesentinel-recovery-export.timer

echo "Scheduled encrypted recovery export installed."
echo "Runner: $runner_target (root:root 0755)"
echo "Capacity preview: $capacity_target (root:root 0755)"
echo "Service: $service_target (root:root 0644)"
echo "Timer: $timer_target (root:root 0644)"
echo "Profile: DEMO_WEEKLY"
echo "Schedule: Sunday 02:00 Asia/Shanghai + bounded random delay"
echo "Persistent catch-up: enabled"
echo "Automatic deletion: disabled"
echo "Credential exposed: False"
echo "Current runtime restarted: False"
