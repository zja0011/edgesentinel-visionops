#!/usr/bin/env bash
set -euo pipefail

readonly manager="/usr/local/libexec/edgesentinel-recovery-capacity-manager"

if [[ -f /.dockerenv ]]; then
    echo "ERROR: run recovery capacity cleanup on the Jetson host." >&2
    exit 1
fi
if [[ "$#" -ne 1 || ! "$1" =~ ^rcp_[0-9a-f]{32}$ ]]; then
    echo "Usage: bash scripts/cleanup_recovery_capacity.sh PLAN_ID" >&2
    exit 2
fi
if ! sudo test -f "$manager" || sudo test -L "$manager" ||
    [[ "$(sudo stat -c '%U:%G %a' "$manager")" != "root:root 755" ]]; then
    echo "ERROR: reinstall the root-owned scheduled recovery assets first." >&2
    exit 1
fi
exec sudo "$manager" apply --plan-id "$1"
